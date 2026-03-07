"""
EP Trailing Stop Strategy Optimization:
  - Test various trailing stop strategies on EP stocks
  - No fixed holding period — hold until stopped out
  - Compare: fixed % trail, ATR trail, MA trail, breakeven + trail
  - Walk-forward: train first 150 days, test remaining
"""
import os, sys, json
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

import numpy as np
import pandas as pd
from ep_backtest import _detect_ep_day
from stockbee_ep import EP_CONFIG

LOOKBACK = int(sys.argv[1]) if len(sys.argv) > 1 else 365
TRAIN_DAYS = 150
MIN_GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 10  # test all, filter later

print(f"=== EP Trailing Stop Optimization — {LOOKBACK} days ===\n")

# ── Fetch bars ────────────────────────────────────────────────────────────────
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks...")
if os.environ.get("POLYGON_API_KEY"):
    from polygon_client import fetch_bars as pg_bars
    bars_data = pg_bars(stock_tickers, days=max(500, LOOKBACK + 150),
                        interval="day", min_rows=50, label="ep-trailing")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got bars for {len(bars_data)} stocks\n")
cfg = dict(EP_CONFIG)


# ── Trailing stop simulators ─────────────────────────────────────────────────

def sim_fixed_trail(df, entry_idx, entry_price, initial_stop, trail_pct, max_hold=999):
    """Fixed percentage trailing stop from highest close."""
    n = len(df)
    highest = entry_price
    stop = initial_stop
    exit_price = entry_price
    exit_reason = "open"  # still holding
    hold_days = 0

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        # Check stop hit (intraday)
        if day_low <= stop:
            exit_price = stop
            exit_reason = "trail_stop"
            break

        # Update trailing stop based on highest close
        if day_close > highest:
            highest = day_close
            new_stop = highest * (1 - trail_pct / 100)
            stop = max(stop, new_stop)

        exit_price = day_close

    pnl = round((exit_price - entry_price) / entry_price * 100, 2)
    max_up = round((highest - entry_price) / entry_price * 100, 2)
    return {"pnl_pct": pnl, "hold_days": hold_days, "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2), "highest": round(highest, 2), "max_up": max_up}


def sim_atr_trail(df, entry_idx, entry_price, initial_stop, atr_mult, atr_period=14, max_hold=999):
    """ATR-based trailing stop."""
    n = len(df)
    highest = entry_price
    stop = initial_stop
    exit_price = entry_price
    exit_reason = "open"
    hold_days = 0

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            exit_price = stop
            exit_reason = "trail_stop"
            break

        # Calculate ATR
        atr_start = max(0, i - atr_period)
        tr_vals = []
        for j in range(atr_start + 1, i + 1):
            h = float(df["high"].iloc[j])
            l = float(df["low"].iloc[j])
            pc = float(df["close"].iloc[j - 1])
            tr_vals.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = np.mean(tr_vals) if tr_vals else 0

        if day_close > highest:
            highest = day_close
        new_stop = highest - (atr * atr_mult)
        stop = max(stop, new_stop)

        exit_price = day_close

    pnl = round((exit_price - entry_price) / entry_price * 100, 2)
    max_up = round((highest - entry_price) / entry_price * 100, 2)
    return {"pnl_pct": pnl, "hold_days": hold_days, "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2), "highest": round(highest, 2), "max_up": max_up}


def sim_ma_trail(df, entry_idx, entry_price, initial_stop, ma_period, max_hold=999):
    """Moving average trailing stop — exit when close < MA."""
    n = len(df)
    highest = entry_price
    stop = initial_stop
    exit_price = entry_price
    exit_reason = "open"
    hold_days = 0

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        # Initial hard stop still applies
        if day_low <= stop:
            exit_price = stop
            exit_reason = "hard_stop"
            break

        # MA stop: close below MA for 2 consecutive days
        if i >= ma_period + 1:
            ma = float(df["close"].iloc[i - ma_period:i].mean())
            prev_close = float(df["close"].iloc[i - 1])
            if prev_close < ma and day_close < ma:
                exit_price = day_close
                exit_reason = "ma_stop"
                break

        if day_close > highest:
            highest = day_close
        exit_price = day_close

    pnl = round((exit_price - entry_price) / entry_price * 100, 2)
    max_up = round((highest - entry_price) / entry_price * 100, 2)
    return {"pnl_pct": pnl, "hold_days": hold_days, "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2), "highest": round(highest, 2), "max_up": max_up}


def sim_breakeven_then_trail(df, entry_idx, entry_price, initial_stop,
                              be_trigger_pct, trail_pct, max_hold=999):
    """Move stop to breakeven after X% gain, then trail from there."""
    n = len(df)
    highest = entry_price
    stop = initial_stop
    breakeven_hit = False
    exit_price = entry_price
    exit_reason = "open"
    hold_days = 0

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            exit_price = stop
            exit_reason = "be_stop" if breakeven_hit else "initial_stop"
            break

        if day_close > highest:
            highest = day_close

        # Phase 1: move to breakeven after trigger
        if not breakeven_hit and highest >= entry_price * (1 + be_trigger_pct / 100):
            stop = max(stop, entry_price * 1.005)  # breakeven + 0.5%
            breakeven_hit = True

        # Phase 2: trail after breakeven
        if breakeven_hit:
            new_stop = highest * (1 - trail_pct / 100)
            stop = max(stop, new_stop)

        exit_price = day_close

    pnl = round((exit_price - entry_price) / entry_price * 100, 2)
    max_up = round((highest - entry_price) / entry_price * 100, 2)
    return {"pnl_pct": pnl, "hold_days": hold_days, "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2), "highest": round(highest, 2), "max_up": max_up}


def sim_chandelier(df, entry_idx, entry_price, initial_stop, atr_mult, atr_period=14,
                    ratchet_pcts=None, max_hold=999):
    """
    Chandelier exit with ratcheting: tighten trail as profit grows.
    ratchet_pcts: list of (profit_threshold, new_atr_mult) tuples
    e.g. [(20, 2.5), (50, 2.0), (100, 1.5)] — tighten as gains grow
    """
    if ratchet_pcts is None:
        ratchet_pcts = []
    n = len(df)
    highest = entry_price
    stop = initial_stop
    current_mult = atr_mult
    exit_price = entry_price
    exit_reason = "open"
    hold_days = 0

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            exit_price = stop
            exit_reason = "chandelier_stop"
            break

        if day_close > highest:
            highest = day_close

        # Ratchet: tighten multiplier as profit grows
        gain_pct = (highest - entry_price) / entry_price * 100
        for threshold, new_mult in ratchet_pcts:
            if gain_pct >= threshold:
                current_mult = min(current_mult, new_mult)

        # ATR
        atr_start = max(0, i - atr_period)
        tr_vals = []
        for j in range(atr_start + 1, i + 1):
            h = float(df["high"].iloc[j])
            l = float(df["low"].iloc[j])
            pc = float(df["close"].iloc[j - 1])
            tr_vals.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = np.mean(tr_vals) if tr_vals else 0

        new_stop = highest - (atr * current_mult)
        stop = max(stop, new_stop)
        exit_price = day_close

    pnl = round((exit_price - entry_price) / entry_price * 100, 2)
    max_up = round((highest - entry_price) / entry_price * 100, 2)
    return {"pnl_pct": pnl, "hold_days": hold_days, "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2), "highest": round(highest, 2), "max_up": max_up}


# ── Collect all EP events ────────────────────────────────────────────────────
print("Scanning EP events...")
ep_events = []
for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    for idx in range(start_idx, n - 1):
        ep = _detect_ep_day(df, idx, cfg)
        if ep is None:
            continue
        if ep["gap_pct"] < MIN_GAP:
            continue

        entry_idx = idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(df["open"].iloc[entry_idx])
        if entry_price <= 0:
            continue

        initial_stop = ep["day_low"] * 0.99

        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        pre_price = float(df["close"].iloc[idx - 1])
        ep_events.append({
            "ticker": ticker, "df": df, "entry_idx": entry_idx,
            "entry_price": entry_price, "initial_stop": initial_stop,
            "ep_date": ep["date"], "ep_type": ep_type,
            "gap_pct": ep["gap_pct"], "vol_ratio": ep["vol_ratio"],
            "neglected": ep.get("neglected"), "above_50ma": ep.get("above_50ma"),
            "pre_price": pre_price, "is_9m": ep.get("is_9m"),
        })

print(f"Total EP events: {len(ep_events)}\n")

# ── Define strategies to test ────────────────────────────────────────────────
STRATEGIES = {
    # Fixed trailing stops
    "trail_10%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 10),
    "trail_15%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 15),
    "trail_20%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 20),
    "trail_25%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 25),
    "trail_30%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 30),
    "trail_40%":  lambda df, ei, ep, ist: sim_fixed_trail(df, ei, ep, ist, 40),

    # ATR trails
    "atr_2x":     lambda df, ei, ep, ist: sim_atr_trail(df, ei, ep, ist, 2.0),
    "atr_3x":     lambda df, ei, ep, ist: sim_atr_trail(df, ei, ep, ist, 3.0),
    "atr_4x":     lambda df, ei, ep, ist: sim_atr_trail(df, ei, ep, ist, 4.0),
    "atr_5x":     lambda df, ei, ep, ist: sim_atr_trail(df, ei, ep, ist, 5.0),

    # MA trails
    "ma_10":      lambda df, ei, ep, ist: sim_ma_trail(df, ei, ep, ist, 10),
    "ma_20":      lambda df, ei, ep, ist: sim_ma_trail(df, ei, ep, ist, 20),
    "ma_50":      lambda df, ei, ep, ist: sim_ma_trail(df, ei, ep, ist, 50),

    # Breakeven + trail
    "be10_trail15": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 10, 15),
    "be10_trail20": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 10, 20),
    "be10_trail25": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 10, 25),
    "be15_trail20": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 15, 20),
    "be15_trail25": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 15, 25),
    "be20_trail25": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 20, 25),
    "be20_trail30": lambda df, ei, ep, ist: sim_breakeven_then_trail(df, ei, ep, ist, 20, 30),

    # Chandelier with ratchet
    "chand_3x":          lambda df, ei, ep, ist: sim_chandelier(df, ei, ep, ist, 3.0),
    "chand_3x_ratchet":  lambda df, ei, ep, ist: sim_chandelier(df, ei, ep, ist, 3.0,
                            ratchet_pcts=[(30, 2.5), (60, 2.0), (100, 1.5)]),
    "chand_4x_ratchet":  lambda df, ei, ep, ist: sim_chandelier(df, ei, ep, ist, 4.0,
                            ratchet_pcts=[(30, 3.0), (60, 2.5), (100, 2.0)]),
}


# ── Run all strategies on all events ─────────────────────────────────────────
print(f"Testing {len(STRATEGIES)} strategies on {len(ep_events)} EP events...\n")

all_results = {}  # strategy -> list of trade results

for sname, sfunc in STRATEGIES.items():
    trades = []
    for ev in ep_events:
        result = sfunc(ev["df"], ev["entry_idx"], ev["entry_price"], ev["initial_stop"])
        result["ticker"] = ev["ticker"]
        result["ep_date"] = ev["ep_date"]
        result["ep_type"] = ev["ep_type"]
        result["gap_pct"] = ev["gap_pct"]
        result["vol_ratio"] = ev["vol_ratio"]
        result["neglected"] = ev["neglected"]
        result["above_50ma"] = ev["above_50ma"]
        result["pre_price"] = ev["pre_price"]
        result["entry_price"] = ev["entry_price"]
        trades.append(result)
    all_results[sname] = trades

# ── Split train/test ─────────────────────────────────────────────────────────
def split_trades(trades):
    tdf = pd.DataFrame(trades)
    tdf["ep_date_dt"] = pd.to_datetime(tdf["ep_date"])
    cutoff = tdf["ep_date_dt"].min() + timedelta(days=TRAIN_DAYS)
    return tdf[tdf["ep_date_dt"] < cutoff], tdf[tdf["ep_date_dt"] >= cutoff]

def calc_stats(tdf):
    if len(tdf) == 0:
        return {"n": 0, "wr": 0, "avg": 0, "med": 0, "pf": 0, "exp": 0,
                "avg_hold": 0, "avg_win": 0, "avg_loss": 0, "still_open": 0,
                "captured": 0}
    closed = tdf[tdf["exit_reason"] != "open"]
    still_open = len(tdf) - len(closed)

    if len(closed) == 0:
        return {"n": len(tdf), "wr": 0, "avg": 0, "med": 0, "pf": 0, "exp": 0,
                "avg_hold": 0, "avg_win": 0, "avg_loss": 0, "still_open": still_open,
                "captured": 0}

    wins = closed[closed["pnl_pct"] > 0]
    losses = closed[closed["pnl_pct"] <= 0]
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0
    pf = round(abs(avg_w * len(wins)) / abs(avg_l * len(losses)), 2) if len(losses) > 0 and avg_l != 0 else 999
    wr = round(len(wins) / len(closed) * 100, 1)
    exp = round((len(wins)/len(closed) * avg_w) + (len(losses)/len(closed) * avg_l), 2)

    # Capture ratio: how much of the max move did we capture?
    capture = closed["pnl_pct"] / closed["max_up"].replace(0, np.nan)
    avg_capture = round(float(capture.dropna().mean()) * 100, 1)

    return {
        "n": len(tdf), "n_closed": len(closed),
        "wr": wr,
        "avg": round(float(closed["pnl_pct"].mean()), 2),
        "med": round(float(closed["pnl_pct"].median()), 2),
        "pf": pf, "exp": exp,
        "avg_hold": round(float(closed["hold_days"].mean()), 1),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "best": round(float(closed["pnl_pct"].max()), 2),
        "worst": round(float(closed["pnl_pct"].min()), 2),
        "still_open": still_open,
        "captured": avg_capture,
        "total_return": round(float(closed["pnl_pct"].sum()), 1),
    }


# ── Phase 1: All EPs, all strategies ─────────────────────────────────────────
print("=" * 110)
print("PHASE 1: ALL STRATEGIES — ALL EPs (full period)")
print("=" * 110)
print(f"\n{'Strategy':<22} {'N':>4} {'Closed':>6} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} "
      f"{'AvgW%':>7} {'AvgL%':>7} {'Hold':>5} {'Capt%':>6} {'TotRet%':>8}")
print("-" * 110)

strat_summary = {}
for sname in STRATEGIES:
    tdf = pd.DataFrame(all_results[sname])
    s = calc_stats(tdf)
    strat_summary[sname] = s
    print(f"{sname:<22} {s['n']:>4} {s.get('n_closed',0):>6} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} "
          f"{s['pf']:>6} {s['exp']:>7} {s['avg_win']:>7} {s['avg_loss']:>7} "
          f"{s['avg_hold']:>5} {s['captured']:>6} {s.get('total_return',0):>8}")


# ── Phase 2: Gap 30%+ filter ─────────────────────────────────────────────────
print()
print("=" * 110)
print("PHASE 2: ALL STRATEGIES — GAP 30%+ ONLY (full period)")
print("=" * 110)
print(f"\n{'Strategy':<22} {'N':>4} {'Closed':>6} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} "
      f"{'AvgW%':>7} {'AvgL%':>7} {'Hold':>5} {'Capt%':>6} {'TotRet%':>8}")
print("-" * 110)

for sname in STRATEGIES:
    tdf = pd.DataFrame(all_results[sname])
    tdf = tdf[tdf["gap_pct"] >= 30]
    s = calc_stats(tdf)
    print(f"{sname:<22} {s['n']:>4} {s.get('n_closed',0):>6} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} "
          f"{s['pf']:>6} {s['exp']:>7} {s['avg_win']:>7} {s['avg_loss']:>7} "
          f"{s['avg_hold']:>5} {s['captured']:>6} {s.get('total_return',0):>8}")


# ── Phase 3: Walk-forward on best strategies ─────────────────────────────────
print()
print("=" * 110)
print("PHASE 3: WALK-FORWARD VALIDATION (Train first 150d -> Test remaining)")
print("=" * 110)

# Test both all-EPs and gap30+ for top strategies
for gap_label, gap_min in [("ALL EPs", 10), ("GAP 30%+", 30)]:
    print(f"\n--- {gap_label} ---")
    print(f"{'Strategy':<22} {'TRAIN':>38} {'|':>2} {'TEST':>50}")
    print(f"{'':<22} {'N':>4} {'WR%':>6} {'Avg%':>7} {'Exp%':>7} {'PF':>6} {'|':>2} "
          f"{'N':>4} {'Cls':>4} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} {'Hold':>5} {'Capt%':>6} {'TotR%':>7}")
    print("-" * 115)

    for sname in STRATEGIES:
        tdf = pd.DataFrame(all_results[sname])
        tdf = tdf[tdf["gap_pct"] >= gap_min]
        train, test = split_trades(tdf.to_dict("records"))

        if len(train) < 3 or len(test) < 3:
            continue

        tr_s = calc_stats(train)
        te_s = calc_stats(test)

        flag = " ***" if te_s["exp"] > 5 and te_s["wr"] > 40 and te_s["pf"] > 1.5 else ""
        print(f"{sname:<22} {tr_s['n']:>4} {tr_s['wr']:>6} {tr_s['avg']:>7} {tr_s['exp']:>7} {tr_s['pf']:>6} | "
              f"{te_s['n']:>4} {te_s.get('n_closed',0):>4} {te_s['wr']:>6} {te_s['avg']:>7} {te_s['med']:>7} "
              f"{te_s['pf']:>6} {te_s['exp']:>7} {te_s['avg_hold']:>5} {te_s['captured']:>6} "
              f"{te_s.get('total_return',0):>7}{flag}")


# ── Phase 4: Best strategy deep dive ─────────────────────────────────────────
print()
print("=" * 110)
print("PHASE 4: BEST STRATEGY DEEP DIVE")
print("=" * 110)

# Pick top 5 strategies by test-set expectancy for gap 30%+
gap30_test_results = []
for sname in STRATEGIES:
    tdf = pd.DataFrame(all_results[sname])
    tdf = tdf[tdf["gap_pct"] >= 30]
    _, test_df = split_trades(tdf.to_dict("records"))
    if len(test_df) >= 3:
        s = calc_stats(test_df)
        s["strategy"] = sname
        gap30_test_results.append(s)

# Also compute for all EPs
all_test_results = []
for sname in STRATEGIES:
    tdf = pd.DataFrame(all_results[sname])
    _, test_df = split_trades(tdf.to_dict("records"))
    if len(test_df) >= 3:
        s = calc_stats(test_df)
        s["strategy"] = sname
        all_test_results.append(s)

# Rank by expectancy
all_test_results.sort(key=lambda x: x["exp"], reverse=True)
gap30_test_results.sort(key=lambda x: x["exp"], reverse=True)

print("\nTop 5 strategies by TEST expectancy (ALL EPs):")
for i, s in enumerate(all_test_results[:5], 1):
    print(f"  {i}. {s['strategy']:<22} WR {s['wr']}%, Avg {s['avg']}%, Exp {s['exp']}%, "
          f"PF {s['pf']}, Hold {s['avg_hold']}d, Capture {s['captured']}%")

print("\nTop 5 strategies by TEST expectancy (GAP 30%+):")
for i, s in enumerate(gap30_test_results[:5], 1):
    print(f"  {i}. {s['strategy']:<22} WR {s['wr']}%, Avg {s['avg']}%, Exp {s['exp']}%, "
          f"PF {s['pf']}, Hold {s['avg_hold']}d, Capture {s['captured']}%")


# ── Show sample trades from best strategy ────────────────────────────────────
if all_test_results:
    best_name = all_test_results[0]["strategy"]
    print(f"\n--- Sample trades: {best_name} (ALL EPs, TEST period) ---")
    tdf = pd.DataFrame(all_results[best_name])
    _, test_df = split_trades(tdf.to_dict("records"))
    closed = test_df[test_df["exit_reason"] != "open"].sort_values("pnl_pct", ascending=False)

    print(f"\nTop 15 winners:")
    print(f"  {'Ticker':<7} {'EP Date':<12} {'Type':<8} {'Gap%':>6} {'Entry$':>7} {'Exit$':>7} {'PnL%':>7} {'MaxUp%':>7} {'Hold':>5} {'Exit':>12}")
    print(f"  {'-'*90}")
    for _, r in closed.head(15).iterrows():
        print(f"  {r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} {r['gap_pct']:>5.0f}% "
              f"${r['entry_price']:>6.2f} ${r['exit_price']:>6.2f} {r['pnl_pct']:>+6.1f}% "
              f"{r['max_up']:>+6.1f}% {r['hold_days']:>5.0f} {r['exit_reason']:>12}")

    print(f"\nBottom 10 losers:")
    for _, r in closed.tail(10).iterrows():
        print(f"  {r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} {r['gap_pct']:>5.0f}% "
              f"${r['entry_price']:>6.2f} ${r['exit_price']:>6.2f} {r['pnl_pct']:>+6.1f}% "
              f"{r['max_up']:>+6.1f}% {r['hold_days']:>5.0f} {r['exit_reason']:>12}")

    # Still open positions
    still_open = test_df[test_df["exit_reason"] == "open"].sort_values("pnl_pct", ascending=False)
    if len(still_open) > 0:
        print(f"\nStill open ({len(still_open)} positions):")
        for _, r in still_open.head(10).iterrows():
            print(f"  {r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} "
                  f"Entry ${r['entry_price']:>6.2f} Now ${r['exit_price']:>6.2f} {r['pnl_pct']:>+6.1f}% "
                  f"(peak {r['max_up']:>+6.1f}%)")


# ── Save ──────────────────────────────────────────────────────────────────────
output = {
    "config": {"lookback": LOOKBACK, "train_days": TRAIN_DAYS, "min_gap": MIN_GAP,
               "strategies_tested": list(STRATEGIES.keys())},
    "full_period_all_eps": {k: strat_summary[k] for k in STRATEGIES},
    "test_ranking_all_eps": all_test_results[:10],
    "test_ranking_gap30": gap30_test_results[:10],
}
out_path = Path(__file__).parent / "ep_trailing_results.json"
out_path.write_text(json.dumps(output, indent=2, default=str))
print(f"\nResults saved to {out_path.name}")
