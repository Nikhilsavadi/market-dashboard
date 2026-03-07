"""
Find additional filters on top of gap 30%+ to reduce trade count
while maintaining edge. Uses be10_trail15 strategy returns.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from ep_backtest import _detect_ep_day
from stockbee_ep import EP_CONFIG

LOOKBACK = 365
MIN_GAP = 30
BE_TRIGGER = 10
TRAIL_PCT = 15

print("=== EP Trade Reduction Analysis ===\n")

from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars...")
if os.environ.get("POLYGON_API_KEY"):
    from polygon_client import fetch_bars as pg_bars
    bars_data = pg_bars(stock_tickers, days=max(500, LOOKBACK + 150),
                        interval="day", min_rows=50, label="ep-reduce")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got {len(bars_data)} stocks\n")
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
            return round((exit_price - entry_price) / entry_price * 100, 2), hold_days, "stop"

        if day_close > highest:
            highest = day_close
        if not breakeven_hit and highest >= entry_price * (1 + BE_TRIGGER / 100):
            stop = max(stop, entry_price * 1.005)
            breakeven_hit = True
        if breakeven_hit:
            stop = max(stop, highest * (1 - TRAIL_PCT / 100))
        exit_price = day_close

    return round((exit_price - entry_price) / entry_price * 100, 2), hold_days, "open"


# Collect all trades with rich metadata
print("Scanning all gap 30%+ EP events with detailed metadata...")
trades = []

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    closes = df["close"]
    volumes = df["volume"]
    highs = df["high"]

    for idx in range(start_idx, n - 1):
        ep = _detect_ep_day(df, idx, cfg)
        if ep is None or ep["gap_pct"] < MIN_GAP:
            continue
        entry_idx = idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(df["open"].iloc[entry_idx])
        if entry_price <= 0:
            continue
        initial_stop = ep["day_low"] * 0.99

        pnl_pct, hold_days, exit_reason = sim_be_trail(df, entry_idx, entry_price, initial_stop)
        if exit_reason == "open":
            continue  # skip open for clean stats

        # Rich metadata
        prior_close = float(closes.iloc[idx - 1])
        day_close = float(closes.iloc[idx])
        day_open = float(df["open"].iloc[idx])

        # Price level
        price_bucket = "penny" if prior_close < 5 else "low" if prior_close < 20 else "mid" if prior_close < 50 else "high"

        # Gap held? (close > 70% of gap from prior close)
        gap_amount = day_open - prior_close
        gap_held_70 = day_close > prior_close + gap_amount * 0.7
        gap_held_50 = day_close > prior_close + gap_amount * 0.5

        # Bullish close (close > open)
        bullish = day_close > day_open

        # Volume
        adv_start = max(0, idx - 50)
        adv = float(volumes.iloc[adv_start:idx].mean())
        vol_ratio = ep["vol_ratio"]
        dollar_vol = float(closes.iloc[adv_start:idx].mean() * volumes.iloc[adv_start:idx].mean()) if adv > 0 else 0

        # Stop distance as % of entry
        stop_dist_pct = (entry_price - initial_stop) / entry_price * 100

        # Prior trend: 20d return before EP
        if idx >= 20:
            prior_20d_ret = (prior_close - float(closes.iloc[idx - 20])) / float(closes.iloc[idx - 20]) * 100
        else:
            prior_20d_ret = 0

        # 52w range position
        if idx >= 252:
            w52_high = float(highs.iloc[idx - 252:idx].max())
            w52_low = float(df["low"].iloc[idx - 252:idx].min())
            pct_of_range = (prior_close - w52_low) / (w52_high - w52_low) * 100 if w52_high > w52_low else 50
        else:
            pct_of_range = 50

        # Market cap proxy: avg dollar volume (rough)
        is_micro = dollar_vol < 5_000_000
        is_small = 5_000_000 <= dollar_vol < 50_000_000

        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        trades.append({
            "ticker": ticker, "ep_date": ep["date"], "ep_type": ep_type,
            "gap_pct": ep["gap_pct"], "vol_ratio": vol_ratio,
            "pnl_pct": pnl_pct, "hold_days": hold_days,
            "price": prior_close, "price_bucket": price_bucket,
            "gap_held_70": gap_held_70, "gap_held_50": gap_held_50,
            "bullish": bullish, "stop_dist_pct": round(stop_dist_pct, 1),
            "dollar_vol": round(dollar_vol), "is_micro": is_micro, "is_small": is_small,
            "prior_20d_ret": round(prior_20d_ret, 1),
            "pct_of_52w_range": round(pct_of_range, 1),
            "above_50ma": ep.get("above_50ma"),
            "neglected": ep.get("neglected"),
            "is_9m": ep.get("is_9m"),
        })

print(f"Total closed trades: {len(trades)}\n")
df = pd.DataFrame(trades)


def stats(subset, label=""):
    if len(subset) == 0:
        return {"n": 0}
    wins = subset[subset["pnl_pct"] > 0]
    losses = subset[subset["pnl_pct"] <= 0]
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0
    wr = len(wins) / len(subset) * 100
    pf = abs(avg_w * len(wins)) / abs(avg_l * len(losses)) if len(losses) > 0 and avg_l != 0 else 999
    exp = (len(wins)/len(subset) * avg_w) + (len(losses)/len(subset) * avg_l)
    return {"n": len(subset), "wr": round(wr, 1), "avg": round(float(subset["pnl_pct"].mean()), 2),
            "med": round(float(subset["pnl_pct"].median()), 2), "pf": round(pf, 2),
            "exp": round(exp, 2), "trades_per_yr": round(len(subset) / (LOOKBACK / 365), 1)}

base = stats(df)
print(f"BASELINE (gap 30%+): {base['n']} trades, {base['wr']}% WR, {base['avg']}% avg, "
      f"{base['exp']}% exp, ~{base['trades_per_yr']}/yr\n")

# ── Test every filter ────────────────────────────────────────────────────────
FILTERS = {
    # Gap size
    "gap_40+": lambda r: r["gap_pct"] >= 40,
    "gap_50+": lambda r: r["gap_pct"] >= 50,
    "gap_75+": lambda r: r["gap_pct"] >= 75,
    "gap_100+": lambda r: r["gap_pct"] >= 100,

    # Gap quality
    "gap_held_70%": lambda r: r["gap_held_70"],
    "gap_held_50%": lambda r: r["gap_held_50"],
    "bullish_close": lambda r: r["bullish"],
    "gap_held_50+bull": lambda r: r["gap_held_50"] and r["bullish"],

    # Volume
    "vol_3x+": lambda r: r["vol_ratio"] >= 3,
    "vol_5x+": lambda r: r["vol_ratio"] >= 5,
    "vol_10x+": lambda r: r["vol_ratio"] >= 10,
    "9m_shares": lambda r: r["is_9m"],

    # Price level
    "price_5+": lambda r: r["price"] >= 5,
    "price_10+": lambda r: r["price"] >= 10,
    "price_20+": lambda r: r["price"] >= 20,
    "penny_only(<5)": lambda r: r["price"] < 5,

    # Dollar volume (liquidity)
    "dolvol_5m+": lambda r: r["dollar_vol"] >= 5_000_000,
    "dolvol_10m+": lambda r: r["dollar_vol"] >= 10_000_000,
    "micro_cap(<5m)": lambda r: r["dollar_vol"] < 5_000_000,

    # Stop distance (risk per share)
    "stop_<15%": lambda r: r["stop_dist_pct"] < 15,
    "stop_<20%": lambda r: r["stop_dist_pct"] < 20,
    "stop_<25%": lambda r: r["stop_dist_pct"] < 25,
    "stop_>20%": lambda r: r["stop_dist_pct"] > 20,

    # Prior trend
    "prior_flat(<10%)": lambda r: abs(r["prior_20d_ret"]) < 10,
    "prior_down(<0%)": lambda r: r["prior_20d_ret"] < 0,
    "prior_up(>0%)": lambda r: r["prior_20d_ret"] > 0,

    # 52w position
    "low_in_range(<30%)": lambda r: r["pct_of_52w_range"] < 30,
    "mid_range(30-70%)": lambda r: 30 <= r["pct_of_52w_range"] <= 70,
    "high_range(>70%)": lambda r: r["pct_of_52w_range"] > 70,

    # Technical
    "above_50ma": lambda r: r["above_50ma"],
    "below_50ma": lambda r: not r["above_50ma"],
    "neglected": lambda r: r["neglected"],

    # EP type
    "classic_only": lambda r: r["ep_type"] == "CLASSIC",
    "story_only": lambda r: r["ep_type"] == "STORY",
}

print("=" * 95)
print("INDIVIDUAL FILTERS (on top of gap 30%+)")
print("=" * 95)
print(f"{'Filter':<25} {'N':>4} {'Trd/yr':>7} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7}")
print("-" * 95)

filter_results = {}
for fname, ffunc in FILTERS.items():
    mask = df.apply(ffunc, axis=1)
    subset = df[mask]
    s = stats(subset)
    filter_results[fname] = s
    if s["n"] < 2:
        continue
    flag = " <--" if s["n"] >= 3 and s["exp"] > base["exp"] and s["n"] <= base["n"] * 0.6 else ""
    print(f"{fname:<25} {s['n']:>4} {s['trades_per_yr']:>7} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} "
          f"{s['pf']:>6} {s['exp']:>7}{flag}")

# ── Combo search: pairs that cut trades to <40/yr while improving edge ───────
import itertools

print(f"\n{'='*95}")
print("BEST 2-FILTER COMBOS (target: <40 trades/yr, better exp than baseline)")
print(f"{'='*95}")

# Only viable singles
viable = [f for f, s in filter_results.items()
          if s.get("n", 0) >= 3 and s.get("exp", -999) > 0]

EXCLUSIVE = [
    {"above_50ma", "below_50ma"},
    {"classic_only", "story_only"},
    {"price_5+", "price_10+", "price_20+", "penny_only(<5)"},
    {"prior_down(<0%)", "prior_up(>0%)"},
]

def is_compat(combo):
    s = set(combo)
    for excl in EXCLUSIVE:
        if len(s & excl) > 1:
            return False
    return True

combos = []
for c in itertools.combinations(viable, 2):
    if not is_compat(c):
        continue
    mask = pd.Series(True, index=df.index)
    for f in c:
        mask &= df.apply(FILTERS[f], axis=1)
    subset = df[mask]
    if len(subset) < 3:
        continue
    s = stats(subset)
    s["filters"] = " + ".join(c)
    combos.append(s)

# Sort by exp * sqrt(n)
combos.sort(key=lambda x: x["exp"] * (x["n"] ** 0.5), reverse=True)

print(f"\n{'Filters':<50} {'N':>4} {'Trd/yr':>7} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7}")
print("-" * 95)
for c in combos[:25]:
    flag = " ***" if c["trades_per_yr"] <= 40 and c["exp"] > base["exp"] else ""
    print(f"{c['filters']:<50} {c['n']:>4} {c['trades_per_yr']:>7} {c['wr']:>6} {c['avg']:>7} {c['med']:>7} "
          f"{c['pf']:>6} {c['exp']:>7}{flag}")


# ── Final recommendations ────────────────────────────────────────────────────
print(f"\n{'='*95}")
print("RECOMMENDED FILTER SETS (fewer trades, better or equal edge)")
print(f"{'='*95}")

# Find combos with: trades_per_yr <= 40 AND exp >= baseline exp
recs = [c for c in combos if c["trades_per_yr"] <= 40 and c["exp"] >= base["exp"] and c["n"] >= 5]
# Also add strong singles
for fname, s in filter_results.items():
    if s.get("n", 0) >= 5 and s.get("exp", 0) >= base["exp"] and s.get("trades_per_yr", 999) <= 40:
        s_copy = dict(s)
        s_copy["filters"] = fname
        recs.append(s_copy)

recs.sort(key=lambda x: x["exp"], reverse=True)

print(f"\nBaseline: {base['n']} trades ({base['trades_per_yr']}/yr), {base['wr']}% WR, {base['exp']}% exp\n")

for i, r in enumerate(recs[:10], 1):
    reduction = (1 - r["n"] / base["n"]) * 100
    print(f"  {i}. {r['filters']}")
    print(f"     {r['n']} trades ({r['trades_per_yr']}/yr) = {reduction:.0f}% fewer trades")
    print(f"     WR {r['wr']}%, Avg {r['avg']}%, Exp {r['exp']}%, PF {r['pf']}")
    print()
