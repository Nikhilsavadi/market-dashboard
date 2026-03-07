"""
Analyze whether sector relative strength correlates with EP trade outcomes.

For each EP trade from the 5-year backtest:
  1. Map ticker -> GICS sector -> sector ETF
  2. At the EP date, compute sector ETF's 1-month RS vs SPY
  3. Split trades: sector RS positive vs negative
  4. Compare win rates, avg returns, profit factors

Also checks: leading sectors, lagging sectors, and whether
filtering by sector RS improves edge on Tier 1/Tier 2 trades.
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
from sector_rs import SECTOR_ETFS, get_sector

LOOKBACK = 1825
TRAIN_DAYS = 1095
BE_TRIGGER = 10
TRAIL_PCT = 15

print("=== EP Sector RS Correlation Analysis ===\n")

# ── Fetch bars ────────────────────────────────────────────────────────────────
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS

all_tickers = get_scan_universe()
sector_etf_list = list(SECTOR_ETFS.values())
all_etfs = list(set(ETFS + sector_etf_list + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks + {len(sector_etf_list)} sector ETFs + SPY...")

if not os.environ.get("POLYGON_API_KEY"):
    print("ERROR: Need Polygon API key")
    sys.exit(1)

from polygon_client import fetch_bars as pg_bars

# Fetch stock bars and sector ETF bars
bars_data = pg_bars(stock_tickers, days=LOOKBACK + 150,
                    interval="day", min_rows=50, label="ep-sector-rs")

etf_bars = pg_bars(sector_etf_list + ["SPY"], days=LOOKBACK + 150,
                   interval="day", min_rows=50, label="ep-sector-etf")

print(f"Got bars for {len(bars_data)} stocks, {len(etf_bars)} ETFs\n")

cfg = dict(EP_CONFIG)


def sim_be_trail(df, entry_idx, entry_price, initial_stop):
    n = len(df)
    highest = entry_price
    stop = initial_stop
    breakeven_hit = False
    exit_price = entry_price
    hold_days = 0

    for i in range(entry_idx + 1, n):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            exit_price = stop
            return {
                "pnl_pct": round((exit_price - entry_price) / entry_price * 100, 2),
                "hold_days": hold_days, "exit_reason": "stop",
            }

        if day_close > highest:
            highest = day_close
        if not breakeven_hit and highest >= entry_price * (1 + BE_TRIGGER / 100):
            stop = max(stop, entry_price * 1.005)
            breakeven_hit = True
        if breakeven_hit:
            stop = max(stop, highest * (1 - TRAIL_PCT / 100))
        exit_price = day_close

    return {
        "pnl_pct": round((exit_price - entry_price) / entry_price * 100, 2),
        "hold_days": hold_days, "exit_reason": "open",
    }


def get_sector_rs_at_date(sector_name, ep_date_str, spy_df):
    """Compute sector ETF's 1-month RS vs SPY at a given date."""
    etf = SECTOR_ETFS.get(sector_name)
    if not etf or etf not in etf_bars:
        return None
    edf = etf_bars[etf]
    if edf is None or len(edf) < 25:
        return None
    if spy_df is None or len(spy_df) < 25:
        return None

    # Find the index closest to ep_date
    ep_dt = pd.Timestamp(ep_date_str)
    edf_dates = edf.index if isinstance(edf.index, pd.DatetimeIndex) else pd.to_datetime(edf.index)
    spy_dates = spy_df.index if isinstance(spy_df.index, pd.DatetimeIndex) else pd.to_datetime(spy_df.index)

    # Get position in ETF data
    mask_e = edf_dates <= ep_dt
    mask_s = spy_dates <= ep_dt
    if mask_e.sum() < 22 or mask_s.sum() < 22:
        return None

    e_idx = mask_e.sum() - 1
    s_idx = mask_s.sum() - 1

    # 1-month (21 trading days) return
    if e_idx < 21 or s_idx < 21:
        return None

    etf_ret = (float(edf["close"].iloc[e_idx]) / float(edf["close"].iloc[e_idx - 21]) - 1)
    spy_ret = (float(spy_df["close"].iloc[s_idx]) / float(spy_df["close"].iloc[s_idx - 21]) - 1)

    return round((etf_ret - spy_ret) * 100, 2)


# ── Scan all EPs and add sector RS ──────────────────────────────────────────
print("Scanning all EP events over 5 years + computing sector RS...")
trades = []
spy_df = etf_bars.get("SPY")

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    closes = df["close"]
    volumes = df["volume"]

    sector = get_sector(ticker)

    for idx in range(start_idx, n - 1):
        ep = _detect_ep_day(df, idx, cfg)
        if ep is None or ep["gap_pct"] < 10:
            continue
        entry_idx = idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(df["open"].iloc[entry_idx])
        if entry_price <= 0:
            continue
        initial_stop = ep["day_low"] * 0.99

        result = sim_be_trail(df, entry_idx, entry_price, initial_stop)
        if result["exit_reason"] == "open":
            continue

        prior_close = float(closes.iloc[idx - 1])
        day_close = float(closes.iloc[idx])
        day_open = float(df["open"].iloc[idx])

        adv_start = max(0, idx - 50)
        adv = float(volumes.iloc[adv_start:idx].mean())
        dollar_vol = float(closes.iloc[adv_start:idx].mean() * volumes.iloc[adv_start:idx].mean()) if adv > 0 else 0
        is_micro = dollar_vol < 5_000_000

        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        # Sector RS at time of trade
        sector_rs = get_sector_rs_at_date(sector, ep["date"], spy_df)

        trades.append({
            "ticker": ticker, "ep_date": ep["date"], "ep_type": ep_type,
            "gap_pct": ep["gap_pct"], "pnl_pct": result["pnl_pct"],
            "hold_days": result["hold_days"],
            "price": prior_close, "is_micro": is_micro,
            "dollar_vol": dollar_vol,
            "sector": sector,
            "sector_rs_1m": sector_rs,
        })

print(f"Total closed trades (gap 10%+): {len(trades)}")
tdf = pd.DataFrame(trades)
tdf["ep_date_dt"] = pd.to_datetime(tdf["ep_date"])

# Drop trades with no sector RS data
has_rs = tdf[tdf["sector_rs_1m"].notna()].copy()
no_rs = len(tdf) - len(has_rs)
print(f"Trades with sector RS data: {len(has_rs)} (missing: {no_rs})\n")


# ── Stats helper ─────────────────────────────────────────────────────────────
def stats(subset, label=""):
    if len(subset) == 0:
        return {"n": 0, "wr": 0, "avg": 0, "med": 0, "pf": 0}
    wins = subset[subset["pnl_pct"] > 0]
    losses = subset[subset["pnl_pct"] <= 0]
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0
    wr = len(wins) / len(subset) * 100
    pf = abs(avg_w * len(wins)) / abs(avg_l * len(losses)) if len(losses) > 0 and avg_l != 0 else 999
    return {"n": len(subset), "wr": round(wr, 1), "avg": round(float(subset["pnl_pct"].mean()), 2),
            "med": round(float(subset["pnl_pct"].median()), 2), "pf": round(pf, 2)}


def print_comparison(label, all_trades, pos_trades, neg_trades):
    s_all = stats(all_trades)
    s_pos = stats(pos_trades)
    s_neg = stats(neg_trades)
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  {'':30s} {'N':>6s} {'WR':>7s} {'Avg':>8s} {'Med':>8s} {'PF':>7s}")
    print(f"  {'All trades':30s} {s_all['n']:6d} {s_all['wr']:6.1f}% {s_all['avg']:+7.2f}% {s_all['med']:+7.2f}% {s_all['pf']:7.2f}")
    print(f"  {'Sector RS positive (>0)':30s} {s_pos['n']:6d} {s_pos['wr']:6.1f}% {s_pos['avg']:+7.2f}% {s_pos['med']:+7.2f}% {s_pos['pf']:7.2f}")
    print(f"  {'Sector RS negative (<0)':30s} {s_neg['n']:6d} {s_neg['wr']:6.1f}% {s_neg['avg']:+7.2f}% {s_neg['med']:+7.2f}% {s_neg['pf']:7.2f}")

    wr_delta = s_pos["wr"] - s_neg["wr"]
    avg_delta = s_pos["avg"] - s_neg["avg"]
    print(f"\n  Delta (pos - neg):  WR {wr_delta:+.1f}%  |  Avg return {avg_delta:+.2f}%")

    if wr_delta > 3 and avg_delta > 1:
        print(f"  -> SECTOR RS ADDS EDGE")
    elif wr_delta < -3 and avg_delta < -1:
        print(f"  -> SECTOR RS HURTS (contrarian signal?)")
    else:
        print(f"  -> SECTOR RS MAKES LITTLE DIFFERENCE")


# ── 1. Overall: All EPs (gap 10%+) ──────────────────────────────────────────
rs_pos = has_rs[has_rs["sector_rs_1m"] > 0]
rs_neg = has_rs[has_rs["sector_rs_1m"] <= 0]
print_comparison("ALL EPs (gap 10%+)", has_rs, rs_pos, rs_neg)

# ── 2. Gap 30%+ ──────────────────────────────────────────────────────────────
g30 = has_rs[has_rs["gap_pct"] >= 30]
print_comparison("Gap 30%+", g30, g30[g30["sector_rs_1m"] > 0], g30[g30["sector_rs_1m"] <= 0])

# ── 3. Tier 1: Gap 30% + Micro-cap ──────────────────────────────────────────
tier1 = has_rs[(has_rs["gap_pct"] >= 30) & (has_rs["is_micro"])]
print_comparison("TIER 1: Gap 30% + Micro-cap", tier1,
                 tier1[tier1["sector_rs_1m"] > 0], tier1[tier1["sector_rs_1m"] <= 0])

# ── 4. Tier 2: Gap 50% + STORY ──────────────────────────────────────────────
tier2 = has_rs[(has_rs["gap_pct"] >= 50) & (has_rs["ep_type"] == "STORY")]
print_comparison("TIER 2: Gap 50% + STORY", tier2,
                 tier2[tier2["sector_rs_1m"] > 0], tier2[tier2["sector_rs_1m"] <= 0])

# ── 5. Strong sector RS (>2%) vs weak (<-2%) ────────────────────────────────
print(f"\n{'='*70}")
print(f"  STRONG vs WEAK sector RS thresholds")
print(f"{'='*70}")
for label, subset in [("All gap 10%+", has_rs), ("Gap 30%+", g30), ("Tier 1", tier1)]:
    strong = subset[subset["sector_rs_1m"] > 2]
    weak = subset[subset["sector_rs_1m"] < -2]
    s_strong = stats(strong)
    s_weak = stats(weak)
    print(f"\n  {label}:")
    print(f"    Strong RS (>+2%):  N={s_strong['n']:4d}  WR={s_strong['wr']:.1f}%  Avg={s_strong['avg']:+.2f}%  PF={s_strong['pf']:.2f}")
    print(f"    Weak RS  (<-2%):   N={s_weak['n']:4d}  WR={s_weak['wr']:.1f}%  Avg={s_weak['avg']:+.2f}%  PF={s_weak['pf']:.2f}")

# ── 6. Sector breakdown ─────────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"  SECTOR BREAKDOWN (gap 30%+ trades)")
print(f"{'='*70}")
print(f"  {'Sector':20s} {'N':>5s} {'WR':>7s} {'Avg':>8s} {'PF':>7s} {'Avg RS':>8s}")
print(f"  {'-'*55}")

sector_stats = []
for sector_name, grp in g30.groupby("sector"):
    s = stats(grp)
    avg_rs = round(grp["sector_rs_1m"].mean(), 2)
    sector_stats.append((sector_name, s, avg_rs))

sector_stats.sort(key=lambda x: x[1]["avg"], reverse=True)
for sector_name, s, avg_rs in sector_stats:
    if s["n"] >= 3:
        print(f"  {sector_name:20s} {s['n']:5d} {s['wr']:6.1f}% {s['avg']:+7.2f}% {s['pf']:7.2f} {avg_rs:+7.2f}%")

# ── 7. Correlation coefficient ───────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"  CORRELATION: Sector RS vs Trade P&L")
print(f"{'='*70}")
for label, subset in [("All gap 10%+", has_rs), ("Gap 30%+", g30), ("Tier 1", tier1)]:
    if len(subset) > 10:
        corr = subset["sector_rs_1m"].corr(subset["pnl_pct"])
        print(f"  {label:25s}  r = {corr:+.4f}  (N={len(subset)})")

# ── 8. Walk-forward: does sector RS filter hold out-of-sample? ───────────────
print(f"\n{'='*70}")
print(f"  WALK-FORWARD: Sector RS filter (3yr train / 2yr test)")
print(f"{'='*70}")
cutoff = has_rs["ep_date_dt"].min() + timedelta(days=TRAIN_DAYS)
train = has_rs[has_rs["ep_date_dt"] <= cutoff]
test = has_rs[has_rs["ep_date_dt"] > cutoff]

for label, subset_name, subset in [("Train (3yr)", "train", train), ("Test (2yr)", "test", test)]:
    g30_sub = subset[subset["gap_pct"] >= 30]
    pos = g30_sub[g30_sub["sector_rs_1m"] > 0]
    neg = g30_sub[g30_sub["sector_rs_1m"] <= 0]
    s_pos = stats(pos)
    s_neg = stats(neg)
    print(f"\n  {label} - Gap 30%+:")
    print(f"    RS positive: N={s_pos['n']:4d}  WR={s_pos['wr']:.1f}%  Avg={s_pos['avg']:+.2f}%  PF={s_pos['pf']:.2f}")
    print(f"    RS negative: N={s_neg['n']:4d}  WR={s_neg['wr']:.1f}%  Avg={s_neg['avg']:+.2f}%  PF={s_neg['pf']:.2f}")

# ── Save results ─────────────────────────────────────────────────────────────
results = {
    "all_gap10": {
        "rs_positive": stats(rs_pos),
        "rs_negative": stats(rs_neg),
    },
    "gap30": {
        "rs_positive": stats(g30[g30["sector_rs_1m"] > 0]),
        "rs_negative": stats(g30[g30["sector_rs_1m"] <= 0]),
    },
    "tier1": {
        "rs_positive": stats(tier1[tier1["sector_rs_1m"] > 0]),
        "rs_negative": stats(tier1[tier1["sector_rs_1m"] <= 0]),
    },
    "tier2": {
        "rs_positive": stats(tier2[tier2["sector_rs_1m"] > 0]),
        "rs_negative": stats(tier2[tier2["sector_rs_1m"] <= 0]),
    },
}

out_path = Path(__file__).parent / "ep_sector_rs_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
