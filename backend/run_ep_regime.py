"""
Analyze whether market regime at entry impacts EP trade outcomes.

Regime signals tested:
  1. SPY above/below 50-day MA
  2. SPY above/below 200-day MA
  3. SPY 1-month return (up vs down)
  4. VIX level (using VIX ETF proxy VIXY or computed from SPY volatility)
  5. Breadth proxy: % of universe above 50MA at trade date

Uses the same 5-year EP dataset and BE10+Trail15% exit.
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

LOOKBACK = 1825
TRAIN_DAYS = 1095
BE_TRIGGER = 10
TRAIL_PCT = 15

print("=== EP Market Regime Impact Analysis ===\n")

# ── Fetch bars ────────────────────────────────────────────────────────────────
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks + SPY...")

if not os.environ.get("POLYGON_API_KEY"):
    print("ERROR: Need Polygon API key")
    sys.exit(1)

from polygon_client import fetch_bars as pg_bars

bars_data = pg_bars(stock_tickers, days=LOOKBACK + 200,
                    interval="day", min_rows=50, label="ep-regime")
spy_bars = pg_bars(["SPY"], days=LOOKBACK + 200,
                   interval="day", min_rows=50, label="ep-regime-spy")

spy_df = spy_bars.get("SPY")
if spy_df is None:
    print("ERROR: Could not fetch SPY bars")
    sys.exit(1)

print(f"Got bars for {len(bars_data)} stocks, SPY has {len(spy_df)} bars\n")
cfg = dict(EP_CONFIG)


def sim_be_trail(df, entry_idx, entry_price, initial_stop):
    n = len(df)
    highest = entry_price
    stop = initial_stop
    breakeven_hit = False
    exit_price = entry_price
    hold_days = 0

    for i in range(entry_idx + 1, n):
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            return {
                "pnl_pct": round((stop - entry_price) / entry_price * 100, 2),
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


def get_spy_regime_at_date(ep_date_str):
    """Compute SPY regime indicators at a given date."""
    ep_dt = pd.Timestamp(ep_date_str)
    spy_dates = spy_df.index if isinstance(spy_df.index, pd.DatetimeIndex) else pd.to_datetime(spy_df.index)
    mask = spy_dates <= ep_dt
    if mask.sum() < 200:
        idx = mask.sum() - 1
        if idx < 50:
            return None
    else:
        idx = mask.sum() - 1

    spy_close = float(spy_df["close"].iloc[idx])

    # 50MA
    if idx >= 50:
        ma50 = float(spy_df["close"].iloc[idx-49:idx+1].mean())
        above_50ma = spy_close > ma50
    else:
        ma50 = None
        above_50ma = None

    # 200MA
    if idx >= 200:
        ma200 = float(spy_df["close"].iloc[idx-199:idx+1].mean())
        above_200ma = spy_close > ma200
    else:
        ma200 = None
        above_200ma = None

    # 1-month return
    if idx >= 21:
        spy_ret_1m = (spy_close / float(spy_df["close"].iloc[idx - 21]) - 1) * 100
    else:
        spy_ret_1m = 0

    # 20-day realized volatility (annualized) as VIX proxy
    if idx >= 21:
        rets = spy_df["close"].iloc[idx-20:idx+1].pct_change().dropna()
        vol_20d = float(rets.std() * np.sqrt(252) * 100)
    else:
        vol_20d = None

    # Distance from 50MA
    pct_from_50ma = round((spy_close - ma50) / ma50 * 100, 2) if ma50 else None

    return {
        "above_50ma": above_50ma,
        "above_200ma": above_200ma,
        "spy_ret_1m": round(spy_ret_1m, 2),
        "vol_20d": round(vol_20d, 1) if vol_20d else None,
        "pct_from_50ma": pct_from_50ma,
    }


# ── Scan all EPs ─────────────────────────────────────────────────────────────
print("Scanning all EP events over 5 years + computing regime at entry...")
trades = []

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    closes = df["close"]
    volumes = df["volume"]

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

        regime = get_spy_regime_at_date(ep["date"])
        if regime is None:
            continue

        trades.append({
            "ticker": ticker, "ep_date": ep["date"], "ep_type": ep_type,
            "gap_pct": ep["gap_pct"], "pnl_pct": result["pnl_pct"],
            "hold_days": result["hold_days"],
            "is_micro": is_micro, "dollar_vol": dollar_vol,
            **regime,
        })

print(f"Total closed trades: {len(trades)}\n")
tdf = pd.DataFrame(trades)
tdf["ep_date_dt"] = pd.to_datetime(tdf["ep_date"])


def stats(subset):
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


def print_split(label, all_t, group_a, label_a, group_b, label_b):
    s_all = stats(all_t)
    s_a = stats(group_a)
    s_b = stats(group_b)
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  {'':30s} {'N':>6s} {'WR':>7s} {'Avg':>8s} {'Med':>8s} {'PF':>7s}")
    print(f"  {'All':30s} {s_all['n']:6d} {s_all['wr']:6.1f}% {s_all['avg']:+7.2f}% {s_all['med']:+7.2f}% {s_all['pf']:7.2f}")
    print(f"  {label_a:30s} {s_a['n']:6d} {s_a['wr']:6.1f}% {s_a['avg']:+7.2f}% {s_a['med']:+7.2f}% {s_a['pf']:7.2f}")
    print(f"  {label_b:30s} {s_b['n']:6d} {s_b['wr']:6.1f}% {s_b['avg']:+7.2f}% {s_b['med']:+7.2f}% {s_b['pf']:7.2f}")
    wr_d = s_a["wr"] - s_b["wr"]
    avg_d = s_a["avg"] - s_b["avg"]
    print(f"\n  Delta ({label_a[:10]} - {label_b[:10]}):  WR {wr_d:+.1f}%  |  Avg {avg_d:+.2f}%")


# ──────────────────────────────────────────────────────────────────────────────
# Test each regime filter across 3 universes: All gap 10%+, Gap 30%+, Tier 1
# ──────────────────────────────────────────────────────────────────────────────

for universe_label, subset in [
    ("ALL EPs (gap 10%+)", tdf),
    ("Gap 30%+", tdf[tdf["gap_pct"] >= 30]),
    ("TIER 1: Gap 30% + Micro-cap", tdf[(tdf["gap_pct"] >= 30) & (tdf["is_micro"])]),
]:
    print(f"\n\n{'#'*70}")
    print(f"  UNIVERSE: {universe_label}  (N={len(subset)})")
    print(f"{'#'*70}")

    # 1. SPY above/below 50MA
    above = subset[subset["above_50ma"] == True]
    below = subset[subset["above_50ma"] == False]
    print_split(f"{universe_label} - SPY vs 50MA",
                subset, above, "SPY above 50MA", below, "SPY below 50MA")

    # 2. SPY above/below 200MA
    above200 = subset[subset["above_200ma"] == True]
    below200 = subset[subset["above_200ma"] == False]
    print_split(f"{universe_label} - SPY vs 200MA",
                subset, above200, "SPY above 200MA", below200, "SPY below 200MA")

    # 3. SPY 1-month momentum
    up_1m = subset[subset["spy_ret_1m"] > 0]
    dn_1m = subset[subset["spy_ret_1m"] <= 0]
    print_split(f"{universe_label} - SPY 1M return",
                subset, up_1m, "SPY 1M positive", dn_1m, "SPY 1M negative")

    # 4. Volatility (VIX proxy): low vs high
    if subset["vol_20d"].notna().sum() > 10:
        med_vol = subset["vol_20d"].median()
        lo_vol = subset[subset["vol_20d"] <= med_vol]
        hi_vol = subset[subset["vol_20d"] > med_vol]
        print_split(f"{universe_label} - Volatility (20d ann., median={med_vol:.0f}%)",
                    subset, lo_vol, f"Low vol (<={med_vol:.0f}%)", hi_vol, f"High vol (>{med_vol:.0f}%)")

    # 5. SPY distance from 50MA buckets
    if subset["pct_from_50ma"].notna().sum() > 10:
        print(f"\n{'='*70}")
        print(f"  {universe_label} - SPY distance from 50MA buckets")
        print(f"{'='*70}")
        print(f"  {'Bucket':25s} {'N':>6s} {'WR':>7s} {'Avg':>8s} {'PF':>7s}")
        for lo, hi, label in [
            (-999, -5, "Deeply below (<-5%)"),
            (-5, -2, "Below (-5% to -2%)"),
            (-2, 2, "Near 50MA (-2% to +2%)"),
            (2, 5, "Above (+2% to +5%)"),
            (5, 999, "Well above (>+5%)"),
        ]:
            bucket = subset[(subset["pct_from_50ma"] >= lo) & (subset["pct_from_50ma"] < hi)]
            s = stats(bucket)
            if s["n"] > 0:
                print(f"  {label:25s} {s['n']:6d} {s['wr']:6.1f}% {s['avg']:+7.2f}% {s['pf']:7.2f}")


# ── Walk-forward validation ──────────────────────────────────────────────────
print(f"\n\n{'#'*70}")
print(f"  WALK-FORWARD: Best regime filter on Gap 30%+ (3yr train / 2yr test)")
print(f"{'#'*70}")

g30 = tdf[tdf["gap_pct"] >= 30].copy()
cutoff = g30["ep_date_dt"].min() + timedelta(days=TRAIN_DAYS)
train = g30[g30["ep_date_dt"] <= cutoff]
test = g30[g30["ep_date_dt"] > cutoff]

for period_label, period_data in [("Train (3yr)", train), ("Test (2yr)", test)]:
    print(f"\n  --- {period_label} ---")
    for filter_label, pos, neg in [
        ("SPY > 50MA",
         period_data[period_data["above_50ma"] == True],
         period_data[period_data["above_50ma"] == False]),
        ("SPY > 200MA",
         period_data[period_data["above_200ma"] == True],
         period_data[period_data["above_200ma"] == False]),
        ("SPY 1M up",
         period_data[period_data["spy_ret_1m"] > 0],
         period_data[period_data["spy_ret_1m"] <= 0]),
    ]:
        s_pos = stats(pos)
        s_neg = stats(neg)
        print(f"    {filter_label:15s}  YES: N={s_pos['n']:3d} WR={s_pos['wr']:.1f}% Avg={s_pos['avg']:+.2f}% PF={s_pos['pf']:.2f}"
              f"  |  NO: N={s_neg['n']:3d} WR={s_neg['wr']:.1f}% Avg={s_neg['avg']:+.2f}% PF={s_neg['pf']:.2f}")

# ── Correlation ──────────────────────────────────────────────────────────────
print(f"\n\n{'='*70}")
print(f"  CORRELATION with trade P&L")
print(f"{'='*70}")
for label, subset in [("All gap 10%+", tdf), ("Gap 30%+", g30),
                       ("Tier 1", tdf[(tdf["gap_pct"] >= 30) & (tdf["is_micro"])])]:
    if len(subset) > 10:
        cols = ["spy_ret_1m", "vol_20d", "pct_from_50ma"]
        corrs = []
        for c in cols:
            if subset[c].notna().sum() > 10:
                r = subset[c].corr(subset["pnl_pct"])
                corrs.append(f"{c}={r:+.4f}")
        print(f"  {label:25s}  {', '.join(corrs)}")

# ── Save ─────────────────────────────────────────────────────────────────────
out = Path(__file__).parent / "ep_regime_results.json"
results = {}
for label, subset in [("all", tdf), ("gap30", g30),
                       ("tier1", tdf[(tdf["gap_pct"] >= 30) & (tdf["is_micro"])])]:
    results[label] = {
        "spy_above_50ma": stats(subset[subset["above_50ma"] == True]),
        "spy_below_50ma": stats(subset[subset["above_50ma"] == False]),
        "spy_above_200ma": stats(subset[subset["above_200ma"] == True]),
        "spy_below_200ma": stats(subset[subset["above_200ma"] == False]),
        "spy_1m_up": stats(subset[subset["spy_ret_1m"] > 0]),
        "spy_1m_down": stats(subset[subset["spy_ret_1m"] <= 0]),
    }
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out}")
