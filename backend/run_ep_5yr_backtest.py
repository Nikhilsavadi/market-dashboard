"""
5-year EP backtest with the filters we identified:
  - Gap 30%+ baseline
  - Gap 50%+ STORY (Option A)
  - Gap 75%+ price $10+ (Option B)
  - be10_trail15 exit strategy
  - Walk-forward: first 3 years train, last 2 years test
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

LOOKBACK = 1825  # ~5 years
TRAIN_DAYS = 1095  # ~3 years
BE_TRIGGER = 10
TRAIL_PCT = 15

print(f"=== 5-Year EP Backtest ===")
print(f"Period     : {LOOKBACK} days (~5 years)")
print(f"Train      : first {TRAIN_DAYS} days (~3 years)")
print(f"Test       : remaining ~{LOOKBACK - TRAIN_DAYS} days (~2 years)\n")

# ── Fetch bars ────────────────────────────────────────────────────────────────
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks (5yr daily)...")
if os.environ.get("POLYGON_API_KEY"):
    from polygon_client import fetch_bars as pg_bars
    bars_data = pg_bars(stock_tickers, days=LOOKBACK + 150,
                        interval="day", min_rows=50, label="ep-5yr")
else:
    print("ERROR: Need Polygon API key for 5yr data")
    sys.exit(1)

print(f"Got bars for {len(bars_data)} stocks\n")
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
                "exit_price": round(exit_price, 2), "highest": round(highest, 2),
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
        "exit_price": round(exit_price, 2), "highest": round(highest, 2),
    }


# ── Scan all EPs ─────────────────────────────────────────────────────────────
print("Scanning all EP events over 5 years...")
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
        if ep is None or ep["gap_pct"] < 10:  # scan from 10%+ so we can filter later
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

        # Metadata
        adv_start = max(0, idx - 50)
        adv = float(volumes.iloc[adv_start:idx].mean())
        dollar_vol = float(closes.iloc[adv_start:idx].mean() * volumes.iloc[adv_start:idx].mean()) if adv > 0 else 0
        is_micro = dollar_vol < 5_000_000

        # Gap held
        gap_amount = day_open - prior_close
        gap_held_50 = day_close > prior_close + gap_amount * 0.5

        # Prior trend
        if idx >= 20:
            prior_20d_ret = (prior_close - float(closes.iloc[idx - 20])) / float(closes.iloc[idx - 20]) * 100
        else:
            prior_20d_ret = 0

        # 52w range
        if idx >= 252:
            w52_high = float(highs.iloc[idx - 252:idx].max())
            w52_low = float(df["low"].iloc[idx - 252:idx].min())
            pct_of_range = (prior_close - w52_low) / (w52_high - w52_low) * 100 if w52_high > w52_low else 50
        else:
            pct_of_range = 50

        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        stop_dist_pct = (entry_price - initial_stop) / entry_price * 100

        trades.append({
            "ticker": ticker, "ep_date": ep["date"], "ep_type": ep_type,
            "gap_pct": ep["gap_pct"], "vol_ratio": ep["vol_ratio"],
            "pnl_pct": result["pnl_pct"], "hold_days": result["hold_days"],
            "exit_reason": result["exit_reason"],
            "price": prior_close, "is_micro": is_micro,
            "dollar_vol": dollar_vol,
            "above_50ma": ep.get("above_50ma"),
            "neglected": ep.get("neglected"),
            "is_9m": ep.get("is_9m"),
            "stop_dist_pct": round(stop_dist_pct, 1),
            "prior_20d_ret": round(prior_20d_ret, 1),
            "pct_of_52w_range": round(pct_of_range, 1),
            "gap_held_50": gap_held_50,
            "bullish": day_close > day_open,
        })

print(f"Total closed trades (gap 10%+): {len(trades)}\n")

tdf = pd.DataFrame(trades)
tdf["ep_date_dt"] = pd.to_datetime(tdf["ep_date"])


def stats(subset):
    if len(subset) == 0:
        return {"n": 0, "wr": 0, "avg": 0, "med": 0, "pf": 0, "exp": 0, "per_yr": 0}
    wins = subset[subset["pnl_pct"] > 0]
    losses = subset[subset["pnl_pct"] <= 0]
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0
    wr = len(wins) / len(subset) * 100
    pf = abs(avg_w * len(wins)) / abs(avg_l * len(losses)) if len(losses) > 0 and avg_l != 0 else 999
    exp = (len(wins)/len(subset) * avg_w) + (len(losses)/len(subset) * avg_l)
    # Compute per year
    date_range = (subset["ep_date_dt"].max() - subset["ep_date_dt"].min()).days
    per_yr = len(subset) / (date_range / 365) if date_range > 30 else len(subset)
    return {"n": len(subset), "wr": round(wr, 1), "avg": round(float(subset["pnl_pct"].mean()), 2),
            "med": round(float(subset["pnl_pct"].median()), 2), "pf": round(pf, 2),
            "exp": round(exp, 2), "per_yr": round(per_yr, 1)}


# ── Split train/test ─────────────────────────────────────────────────────────
cutoff = tdf["ep_date_dt"].min() + timedelta(days=TRAIN_DAYS)
train = tdf[tdf["ep_date_dt"] < cutoff]
test = tdf[tdf["ep_date_dt"] >= cutoff]

print(f"Date range : {tdf['ep_date_dt'].min().date()} to {tdf['ep_date_dt'].max().date()}")
print(f"Cutoff     : {cutoff.date()}")
print(f"Train      : {train['ep_date_dt'].min().date()} to {cutoff.date()} ({len(train)} trades)")
print(f"Test       : {cutoff.date()} to {test['ep_date_dt'].max().date()} ({len(test)} trades)")
print()

# ── Define filter sets ───────────────────────────────────────────────────────
FILTER_SETS = {
    "ALL (gap 10%+)": lambda r: True,
    "Gap 30%+": lambda r: r["gap_pct"] >= 30,
    "Gap 50%+": lambda r: r["gap_pct"] >= 50,
    "Gap 75%+": lambda r: r["gap_pct"] >= 75,
    "Gap 100%+": lambda r: r["gap_pct"] >= 100,
    "Gap30 + STORY": lambda r: r["gap_pct"] >= 30 and r["ep_type"] == "STORY",
    "Gap50 + STORY": lambda r: r["gap_pct"] >= 50 and r["ep_type"] == "STORY",
    "Gap75 + price$10+": lambda r: r["gap_pct"] >= 75 and r["price"] >= 10,
    "Gap50 + price$20+": lambda r: r["gap_pct"] >= 50 and r["price"] >= 20,
    "Gap30 + micro_cap": lambda r: r["gap_pct"] >= 30 and r["is_micro"],
    "Gap30 + micro + down": lambda r: r["gap_pct"] >= 30 and r["is_micro"] and r["prior_20d_ret"] < 0,
    "STORY + prior_down": lambda r: r["gap_pct"] >= 30 and r["ep_type"] == "STORY" and r["prior_20d_ret"] < 0,
    "Gap30 + STORY + micro": lambda r: r["gap_pct"] >= 30 and r["ep_type"] == "STORY" and r["is_micro"],
    "Gap50 + stop>20%": lambda r: r["gap_pct"] >= 50 and r["stop_dist_pct"] > 20,
}

# ── Full period stats ────────────────────────────────────────────────────────
print("=" * 105)
print("FULL 5-YEAR PERIOD")
print("=" * 105)
print(f"{'Filter':<30} {'N':>5} {'N/yr':>6} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7}")
print("-" * 105)

for fname, ffunc in FILTER_SETS.items():
    mask = tdf.apply(ffunc, axis=1)
    s = stats(tdf[mask])
    print(f"{fname:<30} {s['n']:>5} {s['per_yr']:>6} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} "
          f"{s['pf']:>6} {s['exp']:>7}")

# ── Walk-forward: train vs test ──────────────────────────────────────────────
print(f"\n{'='*120}")
print("WALK-FORWARD: TRAIN (3yr) vs TEST (2yr)")
print(f"{'='*120}")
print(f"{'Filter':<30} {'--- TRAIN (3yr) ---':>30} {'|':>2} {'--- TEST (2yr) ---':>45}")
print(f"{'':<30} {'N':>5} {'N/yr':>6} {'WR%':>6} {'Exp%':>7} {'|':>2} "
      f"{'N':>5} {'N/yr':>6} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7}  {'OK?':>4}")
print("-" * 120)

for fname, ffunc in FILTER_SETS.items():
    tr_mask = train.apply(ffunc, axis=1)
    te_mask = test.apply(ffunc, axis=1)
    tr_s = stats(train[tr_mask])
    te_s = stats(test[te_mask])

    ok = "YES" if te_s["exp"] > 0 and te_s["wr"] > 35 and te_s["n"] >= 3 else " no"
    print(f"{fname:<30} {tr_s['n']:>5} {tr_s['per_yr']:>6} {tr_s['wr']:>6} {tr_s['exp']:>7} | "
          f"{te_s['n']:>5} {te_s['per_yr']:>6} {te_s['wr']:>6} {te_s['avg']:>7} {te_s['med']:>7} "
          f"{te_s['pf']:>6} {te_s['exp']:>7}  {ok:>4}")


# ── Year-by-year breakdown for top filters ───────────────────────────────────
print(f"\n{'='*100}")
print("YEAR-BY-YEAR BREAKDOWN")
print(f"{'='*100}")

tdf["year"] = tdf["ep_date_dt"].dt.year
years = sorted(tdf["year"].unique())

for fname in ["Gap 30%+", "Gap50 + STORY", "Gap75 + price$10+", "STORY + prior_down", "Gap30 + micro_cap"]:
    ffunc = FILTER_SETS[fname]
    mask = tdf.apply(ffunc, axis=1)
    subset = tdf[mask]
    if len(subset) < 3:
        continue

    print(f"\n--- {fname} ---")
    print(f"  {'Year':<6} {'N':>5} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} {'Best':>8} {'Worst':>8}")
    print(f"  {'-'*70}")

    for yr in years:
        yr_sub = subset[subset["year"] == yr]
        if len(yr_sub) == 0:
            continue
        s = stats(yr_sub)
        best = float(yr_sub["pnl_pct"].max())
        worst = float(yr_sub["pnl_pct"].min())
        print(f"  {yr:<6} {s['n']:>5} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} "
              f"{s['pf']:>6} {s['exp']:>7} {best:>+7.1f}% {worst:>+7.1f}%")

    total = stats(subset)
    print(f"  {'TOTAL':<6} {total['n']:>5} {total['wr']:>6} {total['avg']:>7} {total['med']:>7} "
          f"{total['pf']:>6} {total['exp']:>7}")


# ── Distribution of returns for key filters ──────────────────────────────────
print(f"\n{'='*100}")
print("RETURN DISTRIBUTION BY FILTER")
print(f"{'='*100}")

for fname in ["Gap 30%+", "Gap50 + STORY", "Gap75 + price$10+", "STORY + prior_down"]:
    ffunc = FILTER_SETS[fname]
    mask = tdf.apply(ffunc, axis=1)
    vals = tdf[mask]["pnl_pct"].values
    if len(vals) < 3:
        continue

    pcts = [5, 10, 25, 50, 75, 90, 95]
    print(f"\n  {fname} (n={len(vals)}):")
    print(f"    Mean: {vals.mean():+.1f}%, Std: {vals.std():.1f}%")
    print(f"    " + "  ".join(f"P{p}: {np.percentile(vals, p):+.0f}%" for p in pcts))
    # Count big winners
    for thresh in [50, 100, 200]:
        c = (vals >= thresh).sum()
        print(f"    {thresh}%+ winners: {c} ({c/len(vals)*100:.1f}%)")


# ── Save results ─────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "ep_5yr_results.json"
summary = {}
for fname, ffunc in FILTER_SETS.items():
    mask = tdf.apply(ffunc, axis=1)
    s = stats(tdf[mask])
    tr_mask = train.apply(ffunc, axis=1)
    te_mask = test.apply(ffunc, axis=1)
    tr_s = stats(train[tr_mask])
    te_s = stats(test[te_mask])
    summary[fname] = {"full": s, "train": tr_s, "test": te_s}

out_path.write_text(json.dumps(summary, indent=2, default=str))
print(f"\nResults saved to {out_path.name}")
