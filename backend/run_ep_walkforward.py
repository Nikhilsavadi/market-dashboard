"""
Walk-forward EP backtest:
  - Fetch 365 days of bars
  - Split into TRAIN (first 150 days) and TEST (remaining ~215 days)
  - Find best filter combos on TRAIN
  - Validate on TEST to see which filters hold up out-of-sample
"""
import os, sys, json, itertools
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

import numpy as np
import pandas as pd
from ep_backtest import _detect_ep_day, _simulate_trade
from stockbee_ep import EP_CONFIG

LOOKBACK = int(sys.argv[1]) if len(sys.argv) > 1 else 365
TRAIN_DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 150

print(f"=== Walk-Forward EP Backtest ===")
print(f"Total period : {LOOKBACK} days")
print(f"Train window : first {TRAIN_DAYS} days")
print(f"Test window  : remaining {LOOKBACK - TRAIN_DAYS} days")
print(f"Polygon key  : {bool(os.environ.get('POLYGON_API_KEY'))}")
print()

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
                        interval="day", min_rows=50, label="ep-walkforward")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got bars for {len(bars_data)} stocks\n")


# ── Scan all EP events + trades across full period ───────────────────────────
cfg = dict(EP_CONFIG)

def scan_all_trades(bars: dict, lookback: int) -> list:
    """Detect every EP and simulate its trade."""
    trades = []
    for ticker, df in bars.items():
        if df is None or len(df) < 60:
            continue
        n = len(df)
        start_idx = max(50, n - lookback)
        for idx in range(start_idx, n - 1):
            ep = _detect_ep_day(df, idx, cfg)
            if ep is None:
                continue
            ep["ticker"] = ticker

            # Classify type
            if ep["is_9m"] and ep["gap_pct"] < 5:
                ep["ep_type"] = "9M"
            elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
                ep["ep_type"] = "STORY"
            else:
                ep["ep_type"] = "CLASSIC"

            # Entry next day open
            entry_idx = idx + 1
            if entry_idx >= n:
                continue
            entry_price = float(df["open"].iloc[entry_idx])
            if entry_price <= 0:
                continue

            stop_price = ep["day_low"] * 0.99
            target_pct = max(10, ep["gap_pct"])

            trade = _simulate_trade(df, entry_idx, entry_price, stop_price,
                                    target_pct=target_pct, max_hold=20)
            trade["ticker"] = ticker
            trade["ep_date"] = ep["date"]
            trade["ep_type"] = ep["ep_type"]
            trade["gap_pct"] = ep["gap_pct"]
            trade["vol_ratio"] = ep["vol_ratio"]
            trade["neglected"] = ep.get("neglected")
            trade["above_50ma"] = ep.get("above_50ma")
            trade["near_52w_high"] = ep.get("near_52w_high")
            trade["is_9m"] = ep.get("is_9m")
            trade["volume"] = ep.get("volume", 0)

            # Compute close-above-open ratio (bullish close)
            trade["bullish_close"] = ep["day_close"] > ep["day_open"]
            # Gap held = close > prior close + 70% of gap
            prior_close = ep["day_close"] - (ep["gap_pct"] / 100 * ep["day_close"])  # approx
            trade["gap_held"] = ep["day_close"] > ep["day_open"] * 0.95  # closed within 5% of open

            trades.append(trade)
    return trades


print("Scanning all EP events across full period...")
all_trades = scan_all_trades(bars_data, LOOKBACK)
print(f"Total EP trades found: {len(all_trades)}\n")

if not all_trades:
    print("No trades found. Exiting.")
    sys.exit(1)

tdf = pd.DataFrame(all_trades)
tdf["ep_date_dt"] = pd.to_datetime(tdf["ep_date"])

# ── Split into TRAIN / TEST ─────────────────────────────────────────────────
cutoff = tdf["ep_date_dt"].min() + timedelta(days=TRAIN_DAYS)
train = tdf[tdf["ep_date_dt"] < cutoff].copy()
test = tdf[tdf["ep_date_dt"] >= cutoff].copy()

print(f"Train period : {train['ep_date_dt'].min().date()} to {cutoff.date()}  ({len(train)} trades)")
print(f"Test period  : {cutoff.date()} to {test['ep_date_dt'].max().date()}  ({len(test)} trades)")
print()


# ── Helper: compute stats for a subset ───────────────────────────────────────
def stats(df_subset):
    if len(df_subset) == 0:
        return {"n": 0, "wr": 0, "avg": 0, "med": 0, "pf": 0, "exp": 0,
                "avg_win": 0, "avg_loss": 0, "best": 0, "worst": 0}
    wins = df_subset[df_subset["pnl_pct"] > 0]
    losses = df_subset[df_subset["pnl_pct"] <= 0]
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0
    pf = round(abs(avg_w * len(wins)) / abs(avg_l * len(losses)), 2) if len(losses) > 0 and avg_l != 0 else 999
    wr = round(len(wins) / len(df_subset) * 100, 1)
    exp = round((len(wins)/len(df_subset) * avg_w) + (len(losses)/len(df_subset) * avg_l), 2)
    return {
        "n": len(df_subset),
        "wr": wr,
        "avg": round(float(df_subset["pnl_pct"].mean()), 2),
        "med": round(float(df_subset["pnl_pct"].median()), 2),
        "pf": pf,
        "exp": exp,
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "best": round(float(df_subset["pnl_pct"].max()), 2),
        "worst": round(float(df_subset["pnl_pct"].min()), 2),
    }


# ── FILTER DIMENSIONS ────────────────────────────────────────────────────────
# Each filter is a (name, function) that returns True to KEEP the trade
FILTERS = {
    "gap_15+":     lambda r: r["gap_pct"] >= 15,
    "gap_20+":     lambda r: r["gap_pct"] >= 20,
    "gap_30+":     lambda r: r["gap_pct"] >= 30,
    "gap_50+":     lambda r: r["gap_pct"] >= 50,
    "gap_skip_20_30": lambda r: not (20 <= r["gap_pct"] < 30),
    "vol_3x+":     lambda r: r["vol_ratio"] >= 3,
    "vol_5x+":     lambda r: r["vol_ratio"] >= 5,
    "vol_10x+":    lambda r: r["vol_ratio"] >= 10,
    "vol_skip_10x": lambda r: r["vol_ratio"] < 10,
    "above_50ma":  lambda r: r["above_50ma"] == True,
    "below_50ma":  lambda r: r["above_50ma"] == False,
    "neglected":   lambda r: r["neglected"] == True,
    "not_neglected": lambda r: r["neglected"] == False,
    "classic_only": lambda r: r["ep_type"] == "CLASSIC",
    "story_only":  lambda r: r["ep_type"] == "STORY",
    "bullish_close": lambda r: r["bullish_close"] == True,
    "gap_held":    lambda r: r["gap_held"] == True,
    "9m_shares":   lambda r: r["is_9m"] == True,
    "near_52w_high": lambda r: r["near_52w_high"] == True,
}

# ── Test individual filters on TRAIN ─────────────────────────────────────────
print("=" * 80)
print("PHASE 1: INDIVIDUAL FILTER PERFORMANCE (TRAIN SET)")
print("=" * 80)
print(f"{'Filter':<20} {'N':>4} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} {'AvgW':>7} {'AvgL':>7}")
print("-" * 80)

# Baseline (no filters)
base_train = stats(train)
print(f"{'[NO FILTER]':<20} {base_train['n']:>4} {base_train['wr']:>6} {base_train['avg']:>7} {base_train['med']:>7} {base_train['pf']:>6} {base_train['exp']:>7} {base_train['avg_win']:>7} {base_train['avg_loss']:>7}")
print("-" * 80)

filter_results = {}
for fname, ffunc in FILTERS.items():
    mask = train.apply(ffunc, axis=1)
    subset = train[mask]
    s = stats(subset)
    filter_results[fname] = s
    flag = " ***" if s["n"] >= 5 and s["exp"] > base_train["exp"] and s["wr"] > base_train["wr"] else ""
    print(f"{fname:<20} {s['n']:>4} {s['wr']:>6} {s['avg']:>7} {s['med']:>7} {s['pf']:>6} {s['exp']:>7} {s['avg_win']:>7} {s['avg_loss']:>7}{flag}")


# ── PHASE 2: Combo search (2-3 filter combos) on TRAIN ──────────────────────
print()
print("=" * 80)
print("PHASE 2: BEST FILTER COMBINATIONS (TRAIN SET)")
print("=" * 80)

# Only test filters that individually had positive expectancy on train
viable = [f for f, s in filter_results.items() if s["exp"] > 0 and s["n"] >= 3]
print(f"Viable filters (positive expectancy, n>=3): {len(viable)}")
print(f"  {', '.join(viable)}")
print()

# Mutually exclusive pairs — skip combos that can't co-exist
EXCLUSIVE = [
    {"above_50ma", "below_50ma"},
    {"neglected", "not_neglected"},
    {"classic_only", "story_only"},
]

def is_compatible(combo):
    s = set(combo)
    for excl in EXCLUSIVE:
        if len(s & excl) > 1:
            return False
    return True

combo_results = []

# 2-filter combos
for combo in itertools.combinations(viable, 2):
    if not is_compatible(combo):
        continue
    mask = pd.Series(True, index=train.index)
    for f in combo:
        mask &= train.apply(FILTERS[f], axis=1)
    subset = train[mask]
    if len(subset) < 3:
        continue
    s = stats(subset)
    s["filters"] = list(combo)
    s["filter_str"] = " + ".join(combo)
    combo_results.append(s)

# 3-filter combos
for combo in itertools.combinations(viable, 3):
    if not is_compatible(combo):
        continue
    mask = pd.Series(True, index=train.index)
    for f in combo:
        mask &= train.apply(FILTERS[f], axis=1)
    subset = train[mask]
    if len(subset) < 3:
        continue
    s = stats(subset)
    s["filters"] = list(combo)
    s["filter_str"] = " + ".join(combo)
    combo_results.append(s)

# Rank by expectancy * sqrt(n) to balance edge vs sample size
for c in combo_results:
    c["score"] = round(c["exp"] * (c["n"] ** 0.5), 2) if c["n"] > 0 else 0

combo_results.sort(key=lambda x: x["score"], reverse=True)

print(f"{'Rank':<5} {'Filters':<50} {'N':>4} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7} {'Score':>7}")
print("-" * 100)
for i, c in enumerate(combo_results[:30], 1):
    print(f"{i:<5} {c['filter_str']:<50} {c['n']:>4} {c['wr']:>6} {c['avg']:>7} {c['med']:>7} {c['pf']:>6} {c['exp']:>7} {c['score']:>7}")


# ── PHASE 3: Validate top combos on TEST set ────────────────────────────────
print()
print("=" * 80)
print("PHASE 3: OUT-OF-SAMPLE VALIDATION (TEST SET)")
print("=" * 80)

base_test = stats(test)
print(f"\nTest baseline: {base_test['n']} trades, {base_test['wr']}% WR, {base_test['avg']}% avg, {base_test['exp']}% exp")
print()

# Also include single filters with strong train performance
top_singles = sorted(
    [(f, s) for f, s in filter_results.items() if s["exp"] > 0 and s["n"] >= 5],
    key=lambda x: x[1]["exp"] * (x[1]["n"] ** 0.5), reverse=True
)[:10]

validation_rows = []

# Validate single filters
for fname, train_s in top_singles:
    mask = test.apply(FILTERS[fname], axis=1)
    test_subset = test[mask]
    test_s = stats(test_subset)
    held_up = test_s["exp"] > 0 and test_s["wr"] > 40
    validation_rows.append({
        "filter_str": fname,
        "train_n": train_s["n"], "train_wr": train_s["wr"], "train_exp": train_s["exp"],
        "test_n": test_s["n"], "test_wr": test_s["wr"], "test_avg": test_s["avg"],
        "test_med": test_s["med"], "test_exp": test_s["exp"], "test_pf": test_s["pf"],
        "held_up": held_up,
    })

# Validate top combos
for c in combo_results[:20]:
    mask = pd.Series(True, index=test.index)
    for f in c["filters"]:
        mask &= test.apply(FILTERS[f], axis=1)
    test_subset = test[mask]
    test_s = stats(test_subset)
    held_up = test_s["exp"] > 0 and test_s["wr"] > 40
    validation_rows.append({
        "filter_str": c["filter_str"],
        "train_n": c["n"], "train_wr": c["wr"], "train_exp": c["exp"],
        "test_n": test_s["n"], "test_wr": test_s["wr"], "test_avg": test_s["avg"],
        "test_med": test_s["med"], "test_exp": test_s["exp"], "test_pf": test_s["pf"],
        "held_up": held_up,
    })

# Sort by test expectancy
validation_rows.sort(key=lambda x: x["test_exp"], reverse=True)

print(f"{'Filter Combo':<50} {'TRAIN':>28} {'|':>2} {'TEST':>40}")
print(f"{'':<50} {'N':>4} {'WR%':>6} {'Exp%':>7} {'|':>2}   {'N':>4} {'WR%':>6} {'Avg%':>7} {'Med%':>7} {'PF':>6} {'Exp%':>7}  {'OK?':>4}")
print("-" * 115)

for r in validation_rows:
    ok = "YES" if r["held_up"] else " no"
    print(f"{r['filter_str']:<50} {r['train_n']:>4} {r['train_wr']:>6} {r['train_exp']:>7}  | {r['test_n']:>4} {r['test_wr']:>6} {r['test_avg']:>7} {r['test_med']:>7} {r['test_pf']:>6} {r['test_exp']:>7}  {ok:>4}")


# ── PHASE 4: Final recommended filter set ────────────────────────────────────
print()
print("=" * 80)
print("PHASE 4: RECOMMENDED FILTERS")
print("=" * 80)

# Pick combos that held up: positive test expectancy, test WR > 40%, test n >= 3
winners = [r for r in validation_rows if r["held_up"] and r["test_n"] >= 3]

if winners:
    print(f"\nFilters that held up out-of-sample ({len(winners)} found):\n")
    for i, w in enumerate(winners[:10], 1):
        trades_per_month = round(w["test_n"] / ((LOOKBACK - TRAIN_DAYS) / 30), 1)
        print(f"  {i}. {w['filter_str']}")
        print(f"     Train: {w['train_n']} trades, {w['train_wr']}% WR, {w['train_exp']}% exp")
        print(f"     Test : {w['test_n']} trades, {w['test_wr']}% WR, {w['test_exp']}% exp, PF {w['test_pf']}")
        print(f"     Frequency: ~{trades_per_month} trades/month")
        print()

    # Best overall: highest test expectancy with reasonable frequency
    best = winners[0]
    print(f"  >>> BEST FILTER: {best['filter_str']}")
    print(f"      Test: {best['test_n']} trades, {best['test_wr']}% WR, +{best['test_exp']}% expectancy per trade")
else:
    print("\nNo filter combos held up out-of-sample. The edge may be too small or ")
    print("market conditions changed between train and test periods.")
    print("\nBest test-period performers (may not be reliable):")
    for r in validation_rows[:5]:
        print(f"  {r['filter_str']}: test {r['test_n']} trades, {r['test_wr']}% WR, {r['test_exp']}% exp")


# ── Save full results to JSON ────────────────────────────────────────────────
output = {
    "config": {"lookback": LOOKBACK, "train_days": TRAIN_DAYS, "test_days": LOOKBACK - TRAIN_DAYS},
    "train_baseline": base_train,
    "test_baseline": base_test,
    "individual_filters": filter_results,
    "top_combos_train": combo_results[:30],
    "validation": validation_rows,
    "winners": winners[:10] if winners else [],
    "best_filter": winners[0] if winners else None,
}

out_path = Path(__file__).parent / "ep_walkforward_results.json"
out_path.write_text(json.dumps(output, indent=2, default=str))
print(f"\nFull results saved to {out_path.name}")
