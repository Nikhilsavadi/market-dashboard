"""
EP Multi-bagger analysis:
  - For every EP event in the last 365 days, track max appreciation
    from entry over 20d, 40d, 60d, 90d, and to present
  - Find which EPs led to 2x, 3x, 5x, 10x moves
  - Identify common characteristics of multi-baggers
"""
import os, sys, json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

import numpy as np
import pandas as pd
from ep_backtest import _detect_ep_day
from stockbee_ep import EP_CONFIG

LOOKBACK = int(sys.argv[1]) if len(sys.argv) > 1 else 365

print(f"=== EP Multi-Bagger Analysis — {LOOKBACK} days ===\n")

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
                        interval="day", min_rows=50, label="ep-multibagger")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got bars for {len(bars_data)} stocks\n")

cfg = dict(EP_CONFIG)

# ── Scan every EP and track forward returns over extended periods ─────────────
results = []

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df["volume"]
    opens = df["open"]

    for idx in range(start_idx, n - 1):
        ep = _detect_ep_day(df, idx, cfg)
        if ep is None:
            continue

        entry_idx = idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(opens.iloc[entry_idx])
        if entry_price <= 0:
            continue

        # Track forward from entry
        remaining = n - entry_idx
        forward_closes = closes.iloc[entry_idx:].values.astype(float)
        forward_highs = highs.iloc[entry_idx:].values.astype(float)
        forward_lows = lows.iloc[entry_idx:].values.astype(float)

        # Max price reached at various horizons
        max_prices = {}
        max_from_entry = {}
        drawdowns = {}
        for horizon_label, horizon_days in [("20d", 20), ("40d", 40), ("60d", 60),
                                             ("90d", 90), ("120d", 120), ("180d", 180),
                                             ("max", remaining)]:
            end = min(horizon_days, remaining)
            if end <= 0:
                max_prices[horizon_label] = None
                max_from_entry[horizon_label] = None
                drawdowns[horizon_label] = None
                continue
            slice_highs = forward_highs[:end]
            slice_lows = forward_lows[:end]
            slice_close = forward_closes[:end]
            peak = float(np.max(slice_highs))
            trough = float(np.min(slice_lows))
            last_close = float(slice_close[-1])

            max_prices[horizon_label] = round(peak, 2)
            max_from_entry[horizon_label] = round((peak - entry_price) / entry_price * 100, 1)
            # Max drawdown from entry before reaching peak
            drawdowns[horizon_label] = round((trough - entry_price) / entry_price * 100, 1)

        # Current price (last available)
        current_price = float(closes.iloc[-1])
        current_return = round((current_price - entry_price) / entry_price * 100, 1)

        # Price at EP day close (for gap held check)
        ep_close = ep["day_close"]

        # Classify type
        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        # Pre-EP price (for context on how small/big the stock was)
        pre_ep_price = float(closes.iloc[idx - 1]) if idx > 0 else entry_price

        # Average dollar volume pre-EP
        vol_start = max(0, idx - 50)
        avg_dollar_vol = float((closes.iloc[vol_start:idx] * volumes.iloc[vol_start:idx]).mean()) if idx - vol_start > 0 else 0

        results.append({
            "ticker": ticker,
            "ep_date": ep["date"],
            "ep_type": ep_type,
            "gap_pct": ep["gap_pct"],
            "vol_ratio": ep["vol_ratio"],
            "volume": ep["volume"],
            "is_9m": ep["is_9m"],
            "neglected": ep.get("neglected"),
            "above_50ma": ep.get("above_50ma"),
            "near_52w_high": ep.get("near_52w_high"),
            "pre_ep_price": round(pre_ep_price, 2),
            "entry_price": round(entry_price, 2),
            "ep_close": round(ep_close, 2),
            "current_price": round(current_price, 2),
            "current_return_pct": current_return,
            "days_since_ep": remaining,
            "avg_dollar_vol": round(avg_dollar_vol),
            "max_return_20d": max_from_entry.get("20d"),
            "max_return_40d": max_from_entry.get("40d"),
            "max_return_60d": max_from_entry.get("60d"),
            "max_return_90d": max_from_entry.get("90d"),
            "max_return_120d": max_from_entry.get("120d"),
            "max_return_180d": max_from_entry.get("180d"),
            "max_return_all": max_from_entry.get("max"),
            "max_drawdown_20d": drawdowns.get("20d"),
            "max_drawdown_all": drawdowns.get("max"),
            "peak_price": max_prices.get("max"),
        })

print(f"Total EP events analyzed: {len(results)}\n")

if not results:
    print("No EP events found.")
    sys.exit(1)

df = pd.DataFrame(results)

# ── Multi-bagger thresholds ──────────────────────────────────────────────────
thresholds = [
    ("100%+ (2x)", 100),
    ("200%+ (3x)", 200),
    ("400%+ (5x)", 400),
    ("900%+ (10x)", 900),
]

print("=" * 90)
print("HOW MANY EPs BECAME MULTI-BAGGERS?")
print("=" * 90)
print(f"\nTotal EP events: {len(df)}")
print(f"{'Threshold':<20} {'Max Return (any time)':>22} {'Within 90d':>15} {'Within 60d':>15}")
print("-" * 75)

for label, pct in thresholds:
    any_time = len(df[df["max_return_all"] >= pct])
    within_90 = len(df[df["max_return_90d"].fillna(-999) >= pct])
    within_60 = len(df[df["max_return_60d"].fillna(-999) >= pct])
    print(f"{label:<20} {any_time:>10} ({any_time/len(df)*100:.1f}%) {within_90:>8} ({within_90/len(df)*100:.1f}%) {within_60:>8} ({within_60/len(df)*100:.1f}%)")


# ── Top appreciators ─────────────────────────────────────────────────────────
print()
print("=" * 90)
print("TOP 30 EP STOCKS BY MAX APPRECIATION (from entry to peak)")
print("=" * 90)
top = df.nlargest(30, "max_return_all")
print(f"\n{'Ticker':<7} {'EP Date':<12} {'Type':<8} {'Gap%':>6} {'VolR':>5} {'Entry$':>7} {'Peak$':>7} {'Now$':>7} {'MaxRet%':>8} {'NowRet%':>8} {'Days':>5} {'DDn%':>6} {'Neglect':>8} {'50MA':>6}")
print("-" * 115)
for _, r in top.iterrows():
    print(f"{r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} {r['gap_pct']:>5.0f}% {r['vol_ratio']:>5.1f} "
          f"${r['entry_price']:>6.2f} ${r['peak_price']:>6.2f} ${r['current_price']:>6.2f} "
          f"{r['max_return_all']:>+7.0f}% {r['current_return_pct']:>+7.0f}% "
          f"{r['days_since_ep']:>5} {r['max_drawdown_all']:>+5.0f}% "
          f"{'Y' if r['neglected'] else 'N':>8} {'Y' if r['above_50ma'] else 'N':>6}")


# ── Stocks still holding gains (current return > 50%) ────────────────────────
print()
print("=" * 90)
print("EP STOCKS STILL HOLDING BIG GAINS (current return > 50%)")
print("=" * 90)
holders = df[df["current_return_pct"] >= 50].sort_values("current_return_pct", ascending=False)
print(f"\n{len(holders)} stocks still up 50%+ from EP entry\n")
if len(holders) > 0:
    print(f"{'Ticker':<7} {'EP Date':<12} {'Type':<8} {'Gap%':>6} {'Entry$':>7} {'Now$':>7} {'Return%':>8} {'Peak%':>7} {'Days':>5}")
    print("-" * 80)
    for _, r in holders.head(30).iterrows():
        print(f"{r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} {r['gap_pct']:>5.0f}% "
              f"${r['entry_price']:>6.2f} ${r['current_price']:>6.2f} "
              f"{r['current_return_pct']:>+7.0f}% {r['max_return_all']:>+6.0f}% {r['days_since_ep']:>5}")


# ── What do the big winners have in common? ──────────────────────────────────
print()
print("=" * 90)
print("PROFILE OF BIG WINNERS (max return 100%+) vs REST")
print("=" * 90)

big = df[df["max_return_all"] >= 100]
rest = df[df["max_return_all"] < 100]

if len(big) >= 3:
    def profile(subset, label):
        print(f"\n  {label} ({len(subset)} trades):")
        print(f"    Avg gap %       : {subset['gap_pct'].mean():.1f}%")
        print(f"    Median gap %    : {subset['gap_pct'].median():.1f}%")
        print(f"    Avg vol ratio   : {subset['vol_ratio'].mean():.1f}x")
        print(f"    Median vol ratio: {subset['vol_ratio'].median():.1f}x")
        print(f"    % neglected     : {(subset['neglected']==True).mean()*100:.0f}%")
        print(f"    % above 50MA    : {(subset['above_50ma']==True).mean()*100:.0f}%")
        print(f"    % is 9M shares  : {(subset['is_9m']==True).mean()*100:.0f}%")
        print(f"    Avg pre-EP price: ${subset['pre_ep_price'].mean():.2f}")
        print(f"    Med pre-EP price: ${subset['pre_ep_price'].median():.2f}")
        print(f"    Avg entry price : ${subset['entry_price'].mean():.2f}")
        print(f"    Med entry price : ${subset['entry_price'].median():.2f}")
        print(f"    Avg $ volume    : ${subset['avg_dollar_vol'].mean():,.0f}")
        print(f"    Med $ volume    : ${subset['avg_dollar_vol'].median():,.0f}")
        ep_types = subset['ep_type'].value_counts()
        for t, c in ep_types.items():
            print(f"    EP type {t:<8}: {c} ({c/len(subset)*100:.0f}%)")

    profile(big, "BIG WINNERS (100%+ max return)")
    profile(rest, "REST (< 100% max return)")

    # Gap size distribution comparison
    print(f"\n  Gap size distribution:")
    for bucket, lo, hi in [("10-20%", 10, 20), ("20-30%", 20, 30), ("30-50%", 30, 50),
                            ("50-100%", 50, 100), ("100%+", 100, 9999)]:
        big_n = len(big[(big["gap_pct"] >= lo) & (big["gap_pct"] < hi)])
        rest_n = len(rest[(rest["gap_pct"] >= lo) & (rest["gap_pct"] < hi)])
        big_pct = big_n / len(big) * 100 if len(big) > 0 else 0
        rest_pct = rest_n / len(rest) * 100 if len(rest) > 0 else 0
        print(f"    {bucket:<10}: Winners {big_n:>3} ({big_pct:>5.1f}%)  |  Rest {rest_n:>3} ({rest_pct:>5.1f}%)")
else:
    print(f"\nOnly {len(big)} stocks hit 100%+ — not enough for a reliable profile.")


# ── Return distribution by holding period ────────────────────────────────────
print()
print("=" * 90)
print("RETURN DISTRIBUTION BY HOLDING PERIOD (all EPs)")
print("=" * 90)

for col, label in [("max_return_20d", "20 days"), ("max_return_60d", "60 days"),
                    ("max_return_90d", "90 days"), ("max_return_all", "Max (any time)")]:
    vals = df[col].dropna()
    if len(vals) == 0:
        continue
    pcts = [10, 25, 50, 75, 90, 95]
    percentiles = np.percentile(vals, pcts)
    print(f"\n  {label} (n={len(vals)}):")
    print(f"    Mean: {vals.mean():+.1f}%  |  ", end="")
    print("  ".join(f"P{p}: {v:+.0f}%" for p, v in zip(pcts, percentiles)))


# ── Gap 30%+ subset deep dive ────────────────────────────────────────────────
print()
print("=" * 90)
print("DEEP DIVE: GAP 30%+ EPs (your validated filter)")
print("=" * 90)

gap30 = df[df["gap_pct"] >= 30]
print(f"\n{len(gap30)} EPs with gap 30%+\n")

if len(gap30) > 0:
    for col, label in [("max_return_20d", "20d"), ("max_return_60d", "60d"),
                        ("max_return_90d", "90d"), ("max_return_all", "Max")]:
        vals = gap30[col].dropna()
        if len(vals) == 0:
            continue
        print(f"  {label}: mean {vals.mean():+.1f}%, median {vals.median():+.1f}%, "
              f"P90 {np.percentile(vals, 90):+.0f}%, P95 {np.percentile(vals, 95):+.0f}%")

    print(f"\n  Multi-bagger potential (gap 30%+):")
    for label, pct in thresholds:
        count = len(gap30[gap30["max_return_all"] >= pct])
        print(f"    {label}: {count} ({count/len(gap30)*100:.1f}%)")

    print(f"\n  Top 15 gap 30%+ EPs by max return:")
    print(f"  {'Ticker':<7} {'EP Date':<12} {'Type':<8} {'Gap%':>6} {'Entry$':>7} {'Peak$':>7} {'MaxRet%':>8} {'NowRet%':>8}")
    print(f"  {'-'*75}")
    for _, r in gap30.nlargest(15, "max_return_all").iterrows():
        print(f"  {r['ticker']:<7} {r['ep_date']:<12} {r['ep_type']:<8} {r['gap_pct']:>5.0f}% "
              f"${r['entry_price']:>6.2f} ${r['peak_price']:>6.2f} "
              f"{r['max_return_all']:>+7.0f}% {r['current_return_pct']:>+7.0f}%")


# ── Save ──────────────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "ep_multibagger_results.json"
out_path.write_text(json.dumps(results, indent=2, default=str))
print(f"\nFull data saved to {out_path.name} ({len(results)} EP events)")
