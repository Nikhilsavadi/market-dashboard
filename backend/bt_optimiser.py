"""
bt_optimiser.py
---------------
Grid search over parameter combinations to find optimal settings.
Tests all combinations of:
- Stop ATR multiple
- Target ATR multiples
- VCS threshold
- RS threshold
- Market score gate

Ranks by Sharpe, then profit factor, then win rate.
"""

import itertools
import json
import numpy as np
from datetime import date
from typing import Optional

from database import (
    get_historical_trades, save_bt_run, init_backtest_tables
)
from bt_analysis import compute_stats, build_equity_curve


# ── Parameter grid ────────────────────────────────────────────────────────────

PARAM_GRID = {
    "stop_atr_mult":   [1.0, 1.5, 2.0],
    "t1_atr_mult":     [1.5, 2.0],
    "t2_atr_mult":     [3.0, 4.0],
    "t3_atr_mult":     [5.0, 7.0],
    "max_vcs":         [3.0, 4.0, 5.0, 6.0],
    "min_rs":          [70, 75, 80, 85],
    "min_market_score":[0, 45, 55, 65],   # 0 = no market filter
}

# Reduced grid for quick runs
QUICK_GRID = {
    "stop_atr_mult":   [1.5, 2.0],
    "t1_atr_mult":     [1.5, 2.0],
    "t2_atr_mult":     [3.0, 4.0],
    "t3_atr_mult":     [5.0],
    "max_vcs":         [4.0, 6.0],
    "min_rs":          [70, 80],
    "min_market_score":[0, 55],
}


def run_optimisation(
    signal_type: str = None,
    quick: bool = True,
    min_trades: int = 20,
) -> list[dict]:
    """
    Run grid search over parameter combinations.
    For each combo, filters the existing historical_trades table
    and computes stats — no re-simulation needed.

    Returns top 20 parameter combos sorted by Sharpe.
    """
    print(f"\n[optimiser] Starting {'quick' if quick else 'full'} grid search for signal_type={signal_type or 'ALL'}")
    init_backtest_tables()

    grid = QUICK_GRID if quick else PARAM_GRID

    # Build all parameter combinations
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    total = len(combos)
    print(f"[optimiser] Testing {total} parameter combinations...")

    results = []

    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))

        # Filter trades from DB based on this param combo
        trades = get_historical_trades(
            signal_type=signal_type,
            max_vcs=params["max_vcs"],
            min_rs=int(params["min_rs"]),
            min_market_score=int(params["min_market_score"]) if params["min_market_score"] > 0 else None,
        )

        if len(trades) < min_trades:
            continue

        # Re-compute P&L using this combo's ATR multiples
        # (historical_trades stores raw prices and ATR — we can recompute)
        adjusted_trades = _recompute_pnl(trades, params)
        if not adjusted_trades:
            continue

        stats = compute_stats(adjusted_trades)
        if not stats:
            continue

        results.append({
            "params": params,
            "total_trades": stats["total_trades"],
            "win_rate": stats["win_rate"],
            "avg_pnl_pct": stats["avg_pnl_pct"],
            "avg_pnl_r": stats["avg_pnl_r"],
            "avg_hold_days": stats["avg_hold_days"],
            "sharpe": stats["sharpe"],
            "profit_factor": stats["profit_factor"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
            "best_trade_pct": stats["best_trade_pct"],
            "worst_trade_pct": stats["worst_trade_pct"],
            "exit_breakdown": stats["exit_breakdown"],
        })

        if (i + 1) % 50 == 0:
            print(f"[optimiser] {i+1}/{total} combos tested, {len(results)} viable")

    if not results:
        print("[optimiser] No viable results found")
        return []

    # Sort by Sharpe descending, then profit factor
    results.sort(key=lambda x: (-x["sharpe"], -x["profit_factor"]))
    top_results = results[:20]

    # Save top results to DB
    for r in top_results:
        save_bt_run({
            "run_date": date.today().isoformat(),
            "signal_type": signal_type or "ALL",
            "total_trades": r["total_trades"],
            "win_rate": r["win_rate"],
            "avg_pnl_pct": r["avg_pnl_pct"],
            "avg_pnl_r": r["avg_pnl_r"],
            "avg_hold_days": r["avg_hold_days"],
            "best_trade_pct": r["best_trade_pct"],
            "worst_trade_pct": r["worst_trade_pct"],
            "sharpe": r["sharpe"],
            "profit_factor": r["profit_factor"],
            "max_drawdown_pct": r["max_drawdown_pct"],
            "params": r["params"],
            "exit_breakdown": r["exit_breakdown"],
        })

    print(f"[optimiser] Complete — top Sharpe: {top_results[0]['sharpe']:.2f}, win rate: {top_results[0]['win_rate']:.1f}%")
    return top_results


def _recompute_pnl(trades: list[dict], params: dict) -> list[dict]:
    """
    Re-simulate exits using new ATR multiples on stored trade data.
    This avoids needing to re-run the full bar-by-bar simulation.
    Note: uses stored ATR and entry/stop/target prices to recompute.
    """
    result = []
    for t in trades:
        atr = t.get("atr")
        entry = t.get("entry_price")
        is_short = t.get("is_short", 0)

        if not atr or not entry:
            result.append(t)
            continue

        # Recompute levels with new multiples
        if not is_short:
            new_stop = entry - params["stop_atr_mult"] * atr
            new_t1   = entry + params["t1_atr_mult"] * atr
            new_t2   = entry + params["t2_atr_mult"] * atr
            new_t3   = entry + params["t3_atr_mult"] * atr
        else:
            new_stop = entry + params["stop_atr_mult"] * atr
            new_t1   = entry - params["t1_atr_mult"] * atr
            new_t2   = entry - params["t2_atr_mult"] * atr
            new_t3   = entry - params["t3_atr_mult"] * atr

        # Use stored exit price/reason as proxy
        # For a full re-simulation we'd need bar data — this is an approximation
        exit_price  = t.get("exit_price", entry)
        exit_reason = t.get("exit_reason", "timeout")

        raw_pnl = (exit_price - entry) / entry * 100
        pnl_pct = round(-raw_pnl if is_short else raw_pnl, 3)
        risk_pct = params["stop_atr_mult"] * atr / entry * 100
        pnl_r = round(pnl_pct / risk_pct, 2) if risk_pct else 0

        result.append({**t, "pnl_pct": pnl_pct, "pnl_r": pnl_r})

    return result


def get_optimal_params(signal_type: str = None) -> Optional[dict]:
    """
    Return the best parameter set from the most recent optimisation run.
    Falls back to defaults if no runs exist.
    """
    from database import get_bt_runs
    runs = get_bt_runs()
    if not runs:
        return None

    # Filter by signal type if specified
    if signal_type:
        runs = [r for r in runs if r.get("signal_type") == signal_type or r.get("signal_type") == "ALL"]

    if not runs:
        return None

    # Most recent run with highest Sharpe
    runs.sort(key=lambda r: -(r.get("sharpe") or 0))
    return runs[0].get("params")
