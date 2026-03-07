"""
Monte Carlo simulation for EP strategy risk of ruin analysis.
Uses the actual trade return distribution from backtest to simulate
thousands of possible equity paths.
"""
import os, sys, json, random
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import numpy as np

# ── Load actual trade results from trailing stop backtest ─────────────────────
trailing_path = Path(__file__).parent / "ep_trailing_results.json"
equity_path = Path(__file__).parent / "ep_equity_curve.json"

# We need the actual per-trade return distribution
# Re-run the strategy to get individual trade returns
print("=== EP Monte Carlo Risk of Ruin Analysis ===\n")

# ── First, collect actual trade returns from the backtest ────────────────────
print("Collecting actual trade returns from backtest data...")

import pandas as pd
from ep_backtest import _detect_ep_day
from stockbee_ep import EP_CONFIG
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

LOOKBACK = 365
MIN_GAP = 30
BE_TRIGGER = 10
TRAIL_PCT = 15

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks...")
if os.environ.get("POLYGON_API_KEY"):
    from polygon_client import fetch_bars as pg_bars
    bars_data = pg_bars(stock_tickers, days=max(500, LOOKBACK + 150),
                        interval="day", min_rows=50, label="ep-montecarlo")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got bars for {len(bars_data)} stocks\n")
cfg = dict(EP_CONFIG)


def sim_be_trail(df, entry_idx, entry_price, initial_stop):
    """BE 10% then trail 15% - returns pct return."""
    n = len(df)
    highest = entry_price
    stop = initial_stop
    breakeven_hit = False
    exit_price = entry_price
    hold_days = 0
    exit_reason = "open"

    for i in range(entry_idx + 1, n):
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_close = float(df["close"].iloc[i])
        hold_days = i - entry_idx

        if day_low <= stop:
            exit_price = stop
            exit_reason = "stop"
            break

        if day_close > highest:
            highest = day_close

        if not breakeven_hit and highest >= entry_price * (1 + BE_TRIGGER / 100):
            stop = max(stop, entry_price * 1.005)
            breakeven_hit = True

        if breakeven_hit:
            new_stop = highest * (1 - TRAIL_PCT / 100)
            stop = max(stop, new_stop)

        exit_price = day_close

    pnl_pct = (exit_price - entry_price) / entry_price * 100
    return {"pnl_pct": round(pnl_pct, 2), "hold_days": hold_days, "exit_reason": exit_reason}


# Collect all trade returns
print("Running strategy on all EP events...")
trade_returns = []  # list of pnl_pct values
trade_details = []

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
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

        result = sim_be_trail(df, entry_idx, entry_price, initial_stop)
        if result["exit_reason"] == "open":
            continue  # skip still-open trades for clean distribution

        trade_returns.append(result["pnl_pct"])
        trade_details.append({
            "ticker": ticker, "pnl_pct": result["pnl_pct"],
            "hold_days": result["hold_days"], "exit_reason": result["exit_reason"],
        })

print(f"Collected {len(trade_returns)} closed trade returns\n")

if len(trade_returns) < 10:
    print("Not enough trades for Monte Carlo. Exiting.")
    sys.exit(1)

returns = np.array(trade_returns)

# ── Distribution stats ───────────────────────────────────────────────────────
print("=" * 70)
print("TRADE RETURN DISTRIBUTION")
print("=" * 70)
print(f"  N trades      : {len(returns)}")
print(f"  Mean return    : {returns.mean():+.2f}%")
print(f"  Median return  : {np.median(returns):+.2f}%")
print(f"  Std dev        : {returns.std():.2f}%")
print(f"  Skewness       : {float(pd.Series(returns).skew()):.2f}")
print(f"  Min            : {returns.min():+.2f}%")
print(f"  Max            : {returns.max():+.2f}%")
print(f"  Win rate       : {(returns > 0).mean() * 100:.1f}%")
print(f"  Avg win        : {returns[returns > 0].mean():+.2f}%")
print(f"  Avg loss       : {returns[returns <= 0].mean():+.2f}%")

pcts = [5, 10, 25, 50, 75, 90, 95]
print(f"\n  Percentiles:")
for p in pcts:
    print(f"    P{p:>2}: {np.percentile(returns, p):+.1f}%")


# ── Monte Carlo Parameters ───────────────────────────────────────────────────
SIMULATIONS = 10_000
TRADES_PER_YEAR = 80  # ~94 signals, minus some skipped
YEARS = 3
TOTAL_TRADES = TRADES_PER_YEAR * YEARS

# Portfolio configs to test
CONFIGS = [
    {"name": "$10K / no lev / 3% risk", "capital": 10_000, "leverage": 1, "risk_pct": 3, "max_pos_pct": 100},
    {"name": "$10K / 5x lev / 2% risk", "capital": 10_000, "leverage": 5, "risk_pct": 2, "max_pos_pct": 25},
    {"name": "$10K / 5x lev / 3% risk", "capital": 10_000, "leverage": 5, "risk_pct": 3, "max_pos_pct": 30},
    {"name": "$10K / 5x lev / 5% risk", "capital": 10_000, "leverage": 5, "risk_pct": 5, "max_pos_pct": 40},
    {"name": "$10K / 50x lev / 1% risk", "capital": 10_000, "leverage": 50, "risk_pct": 1, "max_pos_pct": 15},
    {"name": "$10K / 50x lev / 2% risk", "capital": 10_000, "leverage": 50, "risk_pct": 2, "max_pos_pct": 20},
    {"name": "$10K / 50x lev / 3% risk", "capital": 10_000, "leverage": 50, "risk_pct": 3, "max_pos_pct": 25},
    {"name": "$10K / 50x lev / 5% risk", "capital": 10_000, "leverage": 50, "risk_pct": 5, "max_pos_pct": 30},
    {"name": "$25K / 50x lev / 2% risk", "capital": 25_000, "leverage": 50, "risk_pct": 2, "max_pos_pct": 20},
    {"name": "$25K / 50x lev / 3% risk", "capital": 25_000, "leverage": 50, "risk_pct": 3, "max_pos_pct": 25},
]

# Ruin thresholds
RUIN_LEVELS = [0.25, 0.50]  # 75% loss and 50% loss

print(f"\n{'='*70}")
print("MONTE CARLO SIMULATION")
print(f"{'='*70}")
print(f"  Simulations    : {SIMULATIONS:,}")
print(f"  Trades/year    : {TRADES_PER_YEAR}")
print(f"  Horizon        : {YEARS} years ({TOTAL_TRADES} trades)")
print(f"  Return sampling: Bootstrap from {len(returns)} actual trades")

# ── Run simulations ──────────────────────────────────────────────────────────

def run_monte_carlo(config, returns, n_sims, n_trades):
    """
    Simulate equity paths by bootstrapping from actual trade returns.
    Position sizing: risk X% of current equity at the stop.
    Since we have % returns, we scale position PnL by risk allocation.
    """
    capital = config["capital"]
    risk_pct = config["risk_pct"] / 100
    max_pos_pct = config["max_pos_pct"] / 100
    leverage = config["leverage"]

    final_equities = np.zeros(n_sims)
    max_drawdowns = np.zeros(n_sims)
    ruin_25 = 0  # hit 25% of starting
    ruin_50 = 0  # hit 50% of starting
    paths = []  # store a few sample paths

    for sim in range(n_sims):
        equity = capital
        peak = capital
        max_dd = 0
        hit_ruin_25 = False
        hit_ruin_50 = False

        # Sample trade path
        path = [equity] if sim < 20 else None  # save first 20 paths
        trade_pcts = np.random.choice(returns, size=n_trades, replace=True)

        for t_pct in trade_pcts:
            # How much of equity is at risk on the stop?
            # risk_amount = equity * risk_pct
            # If the trade returns t_pct and entry used risk_pct sizing:
            # The stop distance varies, but on average our actual stop dist
            # is ~15-20% of entry. With risk_pct of equity at that stop:
            # position_size_notional = risk_amount / (stop_dist_pct/100)
            # With leverage, margin = notional / leverage
            # PnL = position_notional * t_pct / 100

            # Approximate: avg stop distance from our data
            # For gap 30%+ EPs, stop is EP day low * 0.99
            # Entry is next-day open (which is above EP close)
            # Typical stop distance: ~15% of entry
            avg_stop_dist = 0.15
            position_notional = (equity * risk_pct) / avg_stop_dist
            # Cap at max_pos_pct
            max_notional = equity * max_pos_pct * leverage
            position_notional = min(position_notional, max_notional)

            pnl = position_notional * (t_pct / 100)
            equity += pnl

            if equity <= 0:
                equity = 0

            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

            if equity <= capital * 0.25:
                hit_ruin_25 = True
            if equity <= capital * 0.50:
                hit_ruin_50 = True

            if path is not None:
                path.append(round(equity, 2))

        final_equities[sim] = equity
        max_drawdowns[sim] = max_dd
        if hit_ruin_25:
            ruin_25 += 1
        if hit_ruin_50:
            ruin_50 += 1
        if path is not None:
            paths.append(path)

    return {
        "final_equities": final_equities,
        "max_drawdowns": max_drawdowns,
        "ruin_25_pct": ruin_25 / n_sims * 100,
        "ruin_50_pct": ruin_50 / n_sims * 100,
        "paths": paths,
    }


all_mc_results = {}

for config in CONFIGS:
    print(f"\n--- {config['name']} ---")
    result = run_monte_carlo(config, returns, SIMULATIONS, TOTAL_TRADES)
    all_mc_results[config["name"]] = result

    fe = result["final_equities"]
    mdd = result["max_drawdowns"]
    cap = config["capital"]

    median_final = np.median(fe)
    mean_final = np.mean(fe)
    median_return = (median_final / cap - 1) * 100
    mean_return = (mean_final / cap - 1) * 100

    # CAGR from median
    cagr = ((median_final / cap) ** (1 / YEARS) - 1) * 100 if median_final > 0 else -100

    print(f"  Final equity (median) : ${median_final:>12,.0f}  ({median_return:>+.0f}%)")
    print(f"  Final equity (mean)   : ${mean_final:>12,.0f}  ({mean_return:>+.0f}%)")
    print(f"  CAGR (median)         : {cagr:>+.1f}%")
    print(f"  Final equity P10      : ${np.percentile(fe, 10):>12,.0f}")
    print(f"  Final equity P25      : ${np.percentile(fe, 25):>12,.0f}")
    print(f"  Final equity P75      : ${np.percentile(fe, 75):>12,.0f}")
    print(f"  Final equity P90      : ${np.percentile(fe, 90):>12,.0f}")
    print(f"  Final equity P95      : ${np.percentile(fe, 95):>12,.0f}")
    print(f"  Final equity P99      : ${np.percentile(fe, 99):>12,.0f}")
    print(f"  Max drawdown (median) : {np.median(mdd)*100:>8.1f}%")
    print(f"  Max drawdown (P90)    : {np.percentile(mdd, 90)*100:>8.1f}%")
    print(f"  Max drawdown (P99)    : {np.percentile(mdd, 99)*100:>8.1f}%")
    print(f"  Risk of ruin (75%+)   : {result['ruin_25_pct']:>8.2f}%")
    print(f"  Risk of ruin (50%+)   : {result['ruin_50_pct']:>8.2f}%")
    print(f"  Prob of doubling      : {(fe >= cap * 2).mean() * 100:>8.1f}%")
    print(f"  Prob of 3x            : {(fe >= cap * 3).mean() * 100:>8.1f}%")
    print(f"  Prob of 5x            : {(fe >= cap * 5).mean() * 100:>8.1f}%")
    print(f"  Prob of 10x           : {(fe >= cap * 10).mean() * 100:>8.1f}%")
    print(f"  Prob of loss          : {(fe < cap).mean() * 100:>8.1f}%")


# ── Summary comparison table ─────────────────────────────────────────────────
print(f"\n{'='*120}")
print("CONFIGURATION COMPARISON")
print(f"{'='*120}")
print(f"{'Config':<30} {'Median$':>10} {'CAGR':>7} {'P10$':>10} {'P90$':>12} {'MDD_med':>8} {'MDD_P90':>8} "
      f"{'Ruin50%':>8} {'Ruin75%':>8} {'P(2x)':>7} {'P(5x)':>7} {'P(loss)':>8}")
print("-" * 120)

for config in CONFIGS:
    name = config["name"]
    r = all_mc_results[name]
    fe = r["final_equities"]
    mdd = r["max_drawdowns"]
    cap = config["capital"]
    med = np.median(fe)
    cagr = ((med / cap) ** (1/YEARS) - 1) * 100 if med > 0 else -100

    print(f"{name:<30} ${med:>9,.0f} {cagr:>+6.1f}% ${np.percentile(fe,10):>9,.0f} "
          f"${np.percentile(fe,90):>11,.0f} {np.median(mdd)*100:>7.1f}% {np.percentile(mdd,90)*100:>7.1f}% "
          f"{r['ruin_50_pct']:>7.1f}% {r['ruin_25_pct']:>7.1f}% "
          f"{(fe>=cap*2).mean()*100:>6.1f}% {(fe>=cap*5).mean()*100:>6.1f}% "
          f"{(fe<cap).mean()*100:>7.1f}%")


# ── Kelly Criterion ──────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("KELLY CRITERION ANALYSIS")
print(f"{'='*70}")

win_rate = (returns > 0).mean()
avg_win = returns[returns > 0].mean()
avg_loss = abs(returns[returns <= 0].mean())
kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss)
half_kelly = kelly / 2
quarter_kelly = kelly / 4

print(f"  Win rate        : {win_rate*100:.1f}%")
print(f"  Avg win         : +{avg_win:.2f}%")
print(f"  Avg loss        : -{avg_loss:.2f}%")
print(f"  Win/Loss ratio  : {avg_win/avg_loss:.2f}")
print(f"  Full Kelly      : {kelly*100:.1f}% of capital per trade")
print(f"  Half Kelly      : {half_kelly*100:.1f}% (recommended)")
print(f"  Quarter Kelly   : {quarter_kelly*100:.1f}% (conservative)")
print(f"\n  Recommendation  : Risk {half_kelly*100:.0f}-{kelly*100:.0f}% of equity per trade")


# ── Consecutive loss analysis ────────────────────────────────────────────────
print(f"\n{'='*70}")
print("CONSECUTIVE LOSS STREAKS (from Monte Carlo)")
print(f"{'='*70}")

# Run streak analysis on 10K sims
max_streaks = []
for _ in range(10_000):
    sampled = np.random.choice(returns, size=TOTAL_TRADES, replace=True)
    streak = 0
    max_streak = 0
    for r in sampled:
        if r <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    max_streaks.append(max_streak)

max_streaks = np.array(max_streaks)
print(f"  Over {TOTAL_TRADES} trades ({YEARS} years):")
print(f"  Avg max losing streak  : {max_streaks.mean():.1f} trades")
print(f"  Median max streak      : {np.median(max_streaks):.0f} trades")
print(f"  P90 max streak         : {np.percentile(max_streaks, 90):.0f} trades")
print(f"  P95 max streak         : {np.percentile(max_streaks, 95):.0f} trades")
print(f"  P99 max streak         : {np.percentile(max_streaks, 99):.0f} trades")
print(f"  Worst streak seen      : {max_streaks.max()} trades")

# What does a streak cost?
avg_loss_per = abs(returns[returns <= 0].mean())
for streak_len in [3, 5, 7, 10]:
    # With 3% risk and ~15% avg stop distance
    loss_per_trade = 3.0  # roughly 3% of equity per stop-out
    cumulative = (1 - loss_per_trade/100) ** streak_len
    drawdown = (1 - cumulative) * 100
    print(f"  {streak_len} consecutive stops @ 3% risk each = -{drawdown:.1f}% drawdown")


# ── Save ──────────────────────────────────────────────────────────────────────
output = {
    "trade_distribution": {
        "n": len(returns), "mean": round(float(returns.mean()), 2),
        "median": round(float(np.median(returns)), 2),
        "std": round(float(returns.std()), 2),
        "win_rate": round(float(win_rate * 100), 1),
    },
    "kelly": {"full": round(kelly * 100, 1), "half": round(half_kelly * 100, 1)},
    "configs": {},
}

for config in CONFIGS:
    name = config["name"]
    r = all_mc_results[name]
    fe = r["final_equities"]
    mdd = r["max_drawdowns"]
    cap = config["capital"]
    output["configs"][name] = {
        "median_final": round(float(np.median(fe)), 0),
        "cagr": round(((float(np.median(fe)) / cap) ** (1/YEARS) - 1) * 100, 1),
        "p10": round(float(np.percentile(fe, 10)), 0),
        "p90": round(float(np.percentile(fe, 90)), 0),
        "max_dd_median": round(float(np.median(mdd)) * 100, 1),
        "max_dd_p90": round(float(np.percentile(mdd, 90)) * 100, 1),
        "ruin_50": round(r["ruin_50_pct"], 2),
        "ruin_75": round(r["ruin_25_pct"], 2),
        "prob_2x": round(float((fe >= cap * 2).mean() * 100), 1),
        "prob_5x": round(float((fe >= cap * 5).mean() * 100), 1),
        "prob_loss": round(float((fe < cap).mean() * 100), 1),
    }

out_path = Path(__file__).parent / "ep_monte_carlo_results.json"
out_path.write_text(json.dumps(output, indent=2))
print(f"\nResults saved to {out_path.name}")
