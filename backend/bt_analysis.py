"""
bt_analysis.py
--------------
All analysis on top of historical_trades:
- compute_stats: core stats from a list of trades
- drill_down: filter trades by any combination of params
- sector_analysis: performance by sector
- market_regime_analysis: performance by market score bucket
- vcs_analysis: performance by VCS bucket
- rs_analysis: performance by RS bucket
- base_score_analysis: performance by base quality
- build_equity_curve: simulated portfolio equity over time
- monthly_returns: month-by-month breakdown
"""

import numpy as np
import pandas as pd
from datetime import date
from collections import defaultdict
from typing import Optional

from database import get_historical_trades, save_equity_curve


# ── Core stats ────────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> Optional[dict]:
    """Compute full performance stats from a list of trade dicts."""
    if not trades:
        return None

    pnls     = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
    pnl_rs   = [t["pnl_r"]   for t in trades if t.get("pnl_r")   is not None]
    holds    = [t["hold_days"] for t in trades if t.get("hold_days")]

    if not pnls:
        return None

    wins     = [p for p in pnls if p > 0]
    losses   = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100

    avg_win  = np.mean(wins)  if wins   else 0
    avg_loss = np.mean(losses) if losses else 0

    # Profit factor = gross profit / gross loss
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses)) if losses else 1
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0

    # Sharpe (annualised, using avg hold as period)
    avg_hold = np.mean(holds) if holds else 5
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = round(np.mean(pnls) / np.std(pnls) * np.sqrt(252 / avg_hold), 2)
    else:
        sharpe = 0

    # Max drawdown on sorted-by-date equity
    max_dd = _max_drawdown(trades)

    # Exit breakdown
    exit_counts = defaultdict(int)
    for t in trades:
        exit_counts[t.get("exit_reason", "unknown")] += 1

    # Consecutive stats
    max_consec_wins, max_consec_losses = _consecutive_streaks(pnls)

    return {
        "total_trades":     len(pnls),
        "win_rate":         round(win_rate, 1),
        "avg_pnl_pct":      round(np.mean(pnls), 2),
        "avg_pnl_r":        round(np.mean(pnl_rs), 2) if pnl_rs else 0,
        "avg_hold_days":    round(avg_hold, 1),
        "best_trade_pct":   round(max(pnls), 2),
        "worst_trade_pct":  round(min(pnls), 2),
        "avg_win_pct":      round(avg_win, 2),
        "avg_loss_pct":     round(avg_loss, 2),
        "win_loss_ratio":   round(abs(avg_win / avg_loss), 2) if avg_loss else 0,
        "profit_factor":    profit_factor,
        "sharpe":           sharpe,
        "max_drawdown_pct": round(max_dd, 2),
        "gross_profit_pct": round(gross_profit, 2),
        "gross_loss_pct":   round(sum(losses), 2),
        "exit_breakdown":   dict(exit_counts),
        "max_consec_wins":  max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "expectancy":       round(win_rate/100 * avg_win + (1 - win_rate/100) * avg_loss, 2),
    }


def _max_drawdown(trades: list[dict]) -> float:
    """Calculate max drawdown from a running equity curve."""
    sorted_trades = sorted(trades, key=lambda t: t.get("signal_date", ""))
    equity = 100.0
    peak = equity
    max_dd = 0.0
    for t in sorted_trades:
        pnl = t.get("pnl_pct", 0) or 0
        equity *= (1 + pnl / 100)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _consecutive_streaks(pnls: list[float]) -> tuple[int, int]:
    """Return (max_wins_in_a_row, max_losses_in_a_row)."""
    max_w, max_l = 0, 0
    cur_w, cur_l = 0, 0
    for p in pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
            max_w = max(max_w, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            max_l = max(max_l, cur_l)
    return max_w, max_l


# ── Drill-down ────────────────────────────────────────────────────────────────

def drill_down(
    signal_type: str = None,
    max_vcs: float = None,
    min_vcs: float = None,
    min_rs: int = None,
    min_base_score: int = None,
    sector: str = None,
    min_market_score: int = None,
    max_market_score: int = None,
    entry_type: str = None,
    sector_rs_positive: bool = None,
    sector_rs_confirmed: bool = None,
) -> dict:
    """
    Filter historical trades by any combination of criteria
    and return performance stats for that subset.
    """
    trades = get_historical_trades(
        signal_type=signal_type,
        min_vcs=min_vcs,
        max_vcs=max_vcs,
        min_rs=min_rs,
        min_base_score=min_base_score,
        sector=sector,
        min_market_score=min_market_score,
        max_market_score=max_market_score,
        entry_type=entry_type,
        sector_rs_positive=sector_rs_positive,
        sector_rs_confirmed=sector_rs_confirmed,
    )

    stats = compute_stats(trades)
    return {
        "filters": {
            "signal_type": signal_type,
            "max_vcs": max_vcs,
            "min_vcs": min_vcs,
            "min_rs": min_rs,
            "min_base_score": min_base_score,
            "sector": sector,
            "min_market_score": min_market_score,
            "max_market_score": max_market_score,
            "entry_type": entry_type,
            "sector_rs_positive": sector_rs_positive,
            "sector_rs_confirmed": sector_rs_confirmed,
        },
        "stats": stats,
        "trades": trades[:100],  # return sample
    }


# ── Dimensional analyses ──────────────────────────────────────────────────────

def sector_analysis(signal_type: str = None) -> list[dict]:
    """Performance breakdown by sector."""
    all_trades = get_historical_trades(signal_type=signal_type, limit=None)
    sectors = defaultdict(list)
    for t in all_trades:
        sectors[t.get("sector") or "Unknown"].append(t)

    results = []
    for sector, trades in sectors.items():
        stats = compute_stats(trades)
        if stats and stats["total_trades"] >= 5:
            results.append({"sector": sector, **stats})

    return sorted(results, key=lambda x: -x["sharpe"])


def market_regime_analysis(signal_type: str = None) -> list[dict]:
    """
    Performance bucketed by market score at signal time.
    Buckets: Negative (<45), Neutral (45-65), Positive (>65)
    """
    buckets = {
        "negative":  {"label": "Market <45 (Negative)", "min": 0,  "max": 44},
        "neutral":   {"label": "Market 45-65 (Neutral)", "min": 45, "max": 64},
        "positive":  {"label": "Market >65 (Positive)", "min": 65, "max": 100},
    }

    results = []
    for key, b in buckets.items():
        trades = get_historical_trades(
            signal_type=signal_type,
            min_market_score=b["min"],
            max_market_score=b["max"],
        )
        stats = compute_stats(trades)
        if stats and stats["total_trades"] >= 5:
            results.append({"regime": key, "label": b["label"], **stats})

    return results


def vcs_analysis(signal_type: str = None) -> list[dict]:
    """Performance bucketed by VCS score."""
    buckets = [
        ("coiled",   "VCS 1-3 (Coiled)",    None, 3.0),
        ("tight",    "VCS 3-5 (Tight)",      3.0,  5.0),
        ("moderate", "VCS 5-7 (Moderate)",   5.0,  7.0),
        ("loose",    "VCS 7+ (Loose)",        7.0, None),
    ]
    results = []
    for key, label, min_v, max_v in buckets:
        trades = get_historical_trades(
            signal_type=signal_type,
            min_vcs=min_v,
            max_vcs=max_v,
        )
        stats = compute_stats(trades)
        if stats and stats["total_trades"] >= 5:
            results.append({"bucket": key, "label": label, **stats})
    return results



# ── MAE / MFE Analysis ────────────────────────────────────────────────────────

def mae_mfe_analysis(signal_type: str = None) -> dict:
    """
    Analyse Maximum Adverse Excursion and Maximum Favourable Excursion.

    MAE tells you whether your stop is getting hit by noise or real reversals:
    - If most stopped trades had MAE < 1R → stop is fine, just bad luck
    - If stopped trades typically went 1.5-2R against you → stop too tight

    MFE tells you whether you're leaving money on the table:
    - If winning trades had MFE >> exit point → consider wider targets or trailing
    """
    trades = get_historical_trades(signal_type=signal_type, limit=None)
    if not trades:
        return {"error": "No trades found"}

    all_mae_r  = [t["mae_r"]  for t in trades if t.get("mae_r")  is not None]
    all_mfe_r  = [t["mfe_r"]  for t in trades if t.get("mfe_r")  is not None]
    all_mae_pct = [t["mae_pct"] for t in trades if t.get("mae_pct") is not None]
    all_mfe_pct = [t["mfe_pct"] for t in trades if t.get("mfe_pct") is not None]

    stopped = [t for t in trades if t.get("exit_reason") == "stop"]
    winners = [t for t in trades if (t.get("pnl_pct") or 0) > 0]

    # MAE distribution for stopped trades — was the stop hit by noise?
    stopped_mae = [t["mae_r"] for t in stopped if t.get("mae_r") is not None]
    noise_stops   = [m for m in stopped_mae if m <= 1.0]
    moderate_stops = [m for m in stopped_mae if 1.0 < m <= 1.5]
    clean_stops   = [m for m in stopped_mae if m > 1.5]

    # MFE for winners — how much further could we have held?
    winner_mfe = [t["mfe_r"] for t in winners if t.get("mfe_r") is not None]
    winner_exit_r = [abs(t["pnl_r"]) for t in winners if t.get("pnl_r") is not None]

    # Efficiency: how much of MFE did we actually capture?
    efficiencies = []
    for t in winners:
        if t.get("mfe_r") and t.get("pnl_r") and t["mfe_r"] > 0:
            eff = min(t["pnl_r"] / t["mfe_r"] * 100, 100)
            efficiencies.append(eff)

    def pct(lst, total):
        return round(len(lst) / total * 100, 1) if total else 0

    return {
        "signal_type": signal_type or "ALL",
        "total_trades": len(trades),
        "mae": {
            "avg_r":    round(np.mean(all_mae_r),  2) if all_mae_r  else 0,
            "median_r": round(float(np.median(all_mae_r)), 2) if all_mae_r else 0,
            "avg_pct":  round(np.mean(all_mae_pct), 2) if all_mae_pct else 0,
        },
        "mfe": {
            "avg_r":    round(np.mean(all_mfe_r),  2) if all_mfe_r  else 0,
            "median_r": round(float(np.median(all_mfe_r)), 2) if all_mfe_r else 0,
            "avg_pct":  round(np.mean(all_mfe_pct), 2) if all_mfe_pct else 0,
        },
        "stop_analysis": {
            "total_stopped": len(stopped),
            "noise_stops":   len(noise_stops),   # MAE ≤ 1R: stop hit with minimal adverse move
            "moderate_stops": len(moderate_stops), # 1R < MAE ≤ 1.5R
            "clean_stops":   len(clean_stops),   # MAE > 1.5R: real reversal
            "noise_pct":     pct(noise_stops, len(stopped)),
            "interpretation": (
                "Stops are well-placed — most hits are genuine reversals"
                if pct(noise_stops, len(stopped)) < 35
                else "High noise-stop rate — consider widening stops by 0.25-0.5×ATR"
            ),
        },
        "capture_efficiency": {
            "avg_winner_mfe_r": round(np.mean(winner_mfe), 2) if winner_mfe else 0,
            "avg_exit_r":       round(np.mean(winner_exit_r), 2) if winner_exit_r else 0,
            "avg_efficiency_pct": round(np.mean(efficiencies), 1) if efficiencies else 0,
            "interpretation": (
                "Good capture efficiency — targets are well-calibrated"
                if (efficiencies and np.mean(efficiencies) > 60)
                else "Low capture efficiency — consider trailing stops or wider targets"
            ),
        },
        "mae_distribution": {
            "under_0.5R":  pct([m for m in stopped_mae if m <= 0.5], len(stopped)),
            "0.5_to_1R":   pct([m for m in stopped_mae if 0.5 < m <= 1.0], len(stopped)),
            "1R_to_1.5R":  pct([m for m in stopped_mae if 1.0 < m <= 1.5], len(stopped)),
            "over_1.5R":   pct([m for m in stopped_mae if m > 1.5], len(stopped)),
        },
    }


def rs_analysis(signal_type: str = None) -> list[dict]:
    """Performance bucketed by RS rank."""
    buckets = [
        ("elite",    "RS 90-99",  90, None),
        ("strong",   "RS 80-89",  80, 89),
        ("good",     "RS 70-79",  70, 79),
        ("average",  "RS 60-69",  60, 69),
        ("weak",     "RS <60",    None, 59),
    ]
    results = []
    for key, label, min_r, max_r in buckets:
        trades = get_historical_trades(signal_type=signal_type, min_rs=min_r, limit=None)
        if max_r:
            trades = [t for t in trades if (t.get("rs") or 0) <= max_r]
        stats = compute_stats(trades)
        if stats and stats["total_trades"] >= 5:
            results.append({"bucket": key, "label": label, **stats})
    return results


def base_score_analysis(signal_type: str = None) -> list[dict]:
    """Performance bucketed by base quality score."""
    buckets = [
        ("premium",  "Base score 80+",   80, None),
        ("quality",  "Base score 60-79", 60, 79),
        ("average",  "Base score 40-59", 40, 59),
        ("weak",     "Base score <40",   None, 39),
    ]
    results = []
    for key, label, min_b, max_b in buckets:
        trades = get_historical_trades(signal_type=signal_type, min_base_score=min_b, limit=None)
        if max_b:
            trades = [t for t in trades if (t.get("base_score") or 0) <= max_b]
        stats = compute_stats(trades)
        if stats and stats["total_trades"] >= 5:
            results.append({"bucket": key, "label": label, **stats})
    return results


# ── Equity curve ──────────────────────────────────────────────────────────────

def build_equity_curve(
    trades: list[dict],
    starting_capital: float = 10000.0,
    risk_per_trade: float = 100.0,   # £ risked per trade (1R)
    max_positions: int = 5,
    run_id: int = None,
) -> list[dict]:
    """
    Simulate a portfolio equity curve.
    Position sizing: risk_per_trade / (stop_atr_mult * ATR / price)
    Max concurrent positions: max_positions
    """
    sorted_trades = sorted(trades, key=lambda t: t.get("signal_date", ""))

    # Group by date
    by_date = defaultdict(list)
    for t in sorted_trades:
        by_date[t.get("signal_date", "unknown")].append(t)

    equity   = starting_capital
    peak     = equity
    curve    = []
    open_pos = 0

    for d in sorted(by_date.keys()):
        day_trades = by_date[d]
        daily_pnl  = 0.0

        for t in day_trades:
            if open_pos >= max_positions:
                continue

            atr   = t.get("atr", 0)
            price = t.get("entry_price", 0)
            pnl   = t.get("pnl_pct", 0) or 0

            if atr and price:
                # Position size = risk_per_trade / (stop distance in £)
                stop_dist_pct = 1.5 * atr / price  # 1.5x ATR
                if stop_dist_pct > 0:
                    pos_value = risk_per_trade / stop_dist_pct
                    pos_pnl   = pos_value * (pnl / 100)
                    daily_pnl += pos_pnl
                    open_pos  = min(max_positions, open_pos + 1)
            else:
                # Flat risk
                daily_pnl += risk_per_trade * (pnl / 100)

            # Closed position
            open_pos = max(0, open_pos - 1)

        equity  += daily_pnl
        drawdown = (peak - equity) / peak * 100 if equity < peak else 0
        if equity > peak:
            peak = equity

        curve.append({
            "curve_date":      d,
            "portfolio_value": round(equity, 2),
            "daily_pnl":       round(daily_pnl, 2),
            "open_positions":  open_pos,
            "drawdown_pct":    round(drawdown, 2),
        })

    if run_id and curve:
        save_equity_curve(run_id, curve)

    return curve


# ── Monthly returns ───────────────────────────────────────────────────────────

def monthly_returns(trades: list[dict]) -> list[dict]:
    """Month-by-month return breakdown."""
    by_month = defaultdict(list)
    for t in trades:
        d = t.get("signal_date", "")
        if len(d) >= 7:
            month_key = d[:7]  # YYYY-MM
            by_month[month_key].append(t.get("pnl_pct", 0) or 0)

    results = []
    for month in sorted(by_month.keys()):
        pnls = by_month[month]
        wins = [p for p in pnls if p > 0]
        results.append({
            "month":       month,
            "trades":      len(pnls),
            "wins":        len(wins),
            "win_rate":    round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
            "total_pnl":  round(sum(pnls), 2),
            "avg_pnl":    round(np.mean(pnls), 2) if pnls else 0,
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
        })

    return results


# ── Sector RS filter analysis ─────────────────────────────────────────────────

def weekly_vs_daily_analysis() -> dict:
    """
    Compare W_EMA10 (weekly touch) signals vs daily MA touch signals.
    Key questions:
      - Do weekly touches have higher win rates than daily?
      - Better R:R (avg_pnl_r)?
      - Longer hold times (as expected)?
      - Worth the reduced signal frequency?
    """
    all_trades = get_historical_trades(limit=None)

    weekly = [t for t in all_trades if t.get("signal_type") == "W_EMA10"]
    daily  = [t for t in all_trades if t.get("signal_type") in ("MA10", "MA21", "MA50")
              and not t.get("is_short")]

    def _row(trades, label):
        s = compute_stats(trades)
        if not s:
            return {"label": label, "count": 0}
        return {
            "label":         label,
            "count":         len(trades),
            "win_rate":      s.get("win_rate"),
            "avg_pnl_pct":   s.get("avg_pnl_pct"),
            "avg_pnl_r":     s.get("avg_pnl_r"),
            "profit_factor": s.get("profit_factor"),
            "expectancy":    s.get("expectancy"),
            "avg_hold_days": s.get("avg_hold_days"),
            "max_drawdown":  s.get("max_drawdown_pct"),
        }

    rows = [
        _row(weekly, "Weekly wEMA10 touch (W_EMA10)"),
        _row(daily,  "Daily MA touch (MA10/21/50)"),
    ]

    verdict = "GREY"
    text    = "Not enough weekly signals yet."
    if weekly and len(weekly) >= 10:
        ws = compute_stats(weekly)
        ds = compute_stats(daily)
        if ws and ds:
            wr_delta = ws.get("win_rate") - ds.get("win_rate")
            r_delta  = ws.get("avg_pnl_r") - ds.get("avg_pnl_r")
            if wr_delta >= 5 and r_delta > 0:
                verdict = "GREEN"
                text = (f"Weekly signals outperform daily: +{wr_delta:.1f}% WR, "
                        f"+{r_delta:.2f}R avg. Add weekly scanner to live alerts.")
            elif wr_delta >= 0 or r_delta > 0:
                verdict = "YELLOW"
                text = f"Weekly signals comparable to daily. Worth monitoring separately."
            else:
                verdict = "ORANGE"
                text = f"Weekly signals underperform daily in this period. May need longer lookback."

    return {
        "description": (
            "Weekly wEMA10 touches fire ~1-3x per month per stock vs daily signals. "
            "Expectation: fewer signals, higher win rate, longer hold times, cleaner R:R. "
            "If weekly outperforms, add W_EMA10 as a separate alert tier."
        ),
        "comparison": rows,
        "weekly_signal_count_per_week": round(len(weekly) / 52, 1) if weekly else 0,
        "verdict": {"colour": verdict, "text": text},
    }


def sector_rs_filter_analysis(signal_type: str = None) -> dict:
    """
    Compares performance across three populations of longs:
      1. All longs (no filter)
      2. Longs where sector outperforms SPY on 1m basis (sector_rs_1m > 0)
      3. Longs where sector outperforms SPY on 1m confirmed

    Tells you whether restricting to leading sectors improves your edge,
    and by how much it reduces signal count (the noise reduction effect).
    """
    all_trades    = get_historical_trades(signal_type=signal_type, limit=None)
    longs_all     = [t for t in all_trades if not t.get("is_short")]

    longs_rs_pos  = [t for t in get_historical_trades(
                        signal_type=signal_type, sector_rs_positive=True, limit=None)
                     if not t.get("is_short")]

    longs_rs_conf = [t for t in get_historical_trades(
                        signal_type=signal_type, sector_rs_confirmed=True, limit=None)
                     if not t.get("is_short")]

    def _row(trades, label):
        s = compute_stats(trades)
        if not s:
            return {"label": label, "count": 0}
        return {
            "label":         label,
            "count":         len(trades),
            "win_rate":      s.get("win_rate"),
            "avg_pnl_pct":   s.get("avg_pnl_pct"),
            "avg_pnl_r":     s.get("avg_pnl_r"),
            "profit_factor": s.get("profit_factor"),
            "expectancy":    s.get("expectancy"),
            "max_drawdown":  s.get("max_drawdown_pct"),
        }

    rows = [
        _row(longs_all,     "All longs (no sector filter)"),
        _row(longs_rs_pos,  "Sector outperforming SPY (1m > 0)"),
        _row(longs_rs_conf, "Sector outperforming SPY (1m confirmed)"),
    ]

    all_count  = len(longs_all)
    pos_count  = len(longs_rs_pos)
    conf_count = len(longs_rs_conf)

    return {
        "description": (
            "Does restricting longs to leading sectors improve your edge? "
            "Compare win rate, expectancy and profit factor across the three groups. "
            "Also shows how many signals survive each filter."
        ),
        "filter_comparison": rows,
        "signal_reduction": {
            "all_longs":           all_count,
            "sector_rs_positive":  pos_count,
            "sector_rs_confirmed": conf_count,
            "pct_surviving_pos":   round(pos_count  / all_count * 100, 1) if all_count else 0,
            "pct_surviving_conf":  round(conf_count / all_count * 100, 1) if all_count else 0,
        },
        "verdict": _sector_rs_verdict(rows),
    }


def _sector_rs_verdict(rows: list) -> dict:
    """Plain-English verdict on whether sector RS filtering adds edge."""
    if len(rows) < 2 or rows[0].get("count", 0) < 20:
        return {"colour": "GREY", "text": "Not enough trades yet to draw conclusions."}

    base_wr  = rows[0].get("win_rate", 0)
    base_exp = rows[0].get("expectancy", 0)
    filt_wr  = rows[1].get("win_rate", 0)
    filt_exp = rows[1].get("expectancy", 0)

    wr_delta  = filt_wr  - base_wr
    exp_delta = filt_exp - base_exp

    if wr_delta >= 5 and exp_delta > 0:
        colour = "GREEN"
        text   = (f"Sector RS filter adds clear edge: +{wr_delta:.1f}% win rate, "
                  f"+{exp_delta:.2f}% expectancy. Apply this gate to live signals.")
    elif wr_delta >= 2 or exp_delta > 0:
        colour = "YELLOW"
        text   = (f"Modest improvement with sector filter (+{wr_delta:.1f}% WR). "
                  f"Worth applying but monitor for consistency.")
    elif wr_delta >= -2:
        colour = "ORANGE"
        text   = (f"Sector RS filter makes little difference ({wr_delta:+.1f}% WR). "
                  f"Individual stock RS may already be sufficient.")
    else:
        colour = "RED"
        text   = (f"Sector RS filter hurts performance ({wr_delta:+.1f}% WR). "
                  f"Leading sectors may be crowded/extended — don't apply this gate.")

    return {"colour": colour, "text": text}


# ── Full analysis report ──────────────────────────────────────────────────────

def weekly_signal_analysis(signal_type: str = None) -> dict:
    """
    Compares performance of signals that also qualify as weekly setups
    vs signals that are daily-only.

    A weekly signal = stock touching wEMA10 with positive slope on the weekly
    timeframe, in addition to triggering a daily MA touch.

    Weekly signals represent higher-timeframe confluence — they should have:
    - Higher win rate (weekly trend confirming daily entry)
    - Longer hold times (weekly moves take longer to play out)
    - Larger average R (weekly trend has more room to run)
    """
    from database import get_conn

    def _get_trades_with_weekly_flag(weekly_only: bool):
        flag = 1 if weekly_only else 0
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT t.*, s.is_weekly_signal, s.w_stack_ok,
                       s.w_ema10_slope, s.within_1atr_wema10
                FROM historical_trades t
                LEFT JOIN historical_signals s ON t.signal_id = s.id
                WHERE t.is_short = 0
                  AND s.is_weekly_signal = ?
                  {}
                ORDER BY t.signal_date DESC
                LIMIT 5000
            """.format("AND t.signal_type = ?" if signal_type else ""),
            (flag, signal_type) if signal_type else (flag,)
            ).fetchall()
            return [dict(r) for r in rows]

    weekly_trades  = _get_trades_with_weekly_flag(weekly_only=True)
    daily_trades   = _get_trades_with_weekly_flag(weekly_only=False)

    ws = compute_stats(weekly_trades)
    ds = compute_stats(daily_trades)

    def _row(trades, label, stats):
        if not stats:
            return {"label": label, "count": 0}
        return {
            "label":         label,
            "count":         len(trades),
            "win_rate":      stats.get("win_rate"),
            "avg_pnl_pct":   stats.get("avg_pnl_pct"),
            "avg_pnl_r":     stats.get("avg_pnl_r"),
            "avg_hold_days": stats.get("avg_hold_days"),
            "profit_factor": stats.get("profit_factor"),
            "expectancy":    stats.get("expectancy"),
            "max_drawdown":  stats.get("max_drawdown_pct"),
        }

    rows = [
        _row(weekly_trades, "Weekly confluence signals (wEMA10 touch + positive slope)", ws),
        _row(daily_trades,  "Daily-only signals (no weekly confirmation)", ds),
    ]

    # Verdict
    verdict = {"colour": "GREY", "text": "Not enough weekly signals yet."}
    if ws and ds and len(weekly_trades) >= 10:
        wr_delta  = ws.get("win_rate")  - ds.get("win_rate")
        exp_delta = ws.get("expectancy") - ds.get("expectancy")
        if wr_delta >= 5 and exp_delta > 0:
            verdict = {"colour": "GREEN",
                       "text": f"Weekly confluence adds clear edge: +{wr_delta:.1f}% WR, "
                               f"+{exp_delta:.2f}% expectancy. Prioritise these setups."}
        elif wr_delta >= 2 or exp_delta > 0:
            verdict = {"colour": "YELLOW",
                       "text": f"Weekly confluence helps modestly (+{wr_delta:.1f}% WR). "
                               f"Worth weighting these signals higher."}
        elif wr_delta >= -2:
            verdict = {"colour": "ORANGE",
                       "text": f"Weekly confluence makes little difference ({wr_delta:+.1f}% WR). "
                               f"Daily signal quality may already be sufficient."}
        else:
            verdict = {"colour": "RED",
                       "text": f"Weekly signals underperform daily ({wr_delta:+.1f}% WR). "
                               f"May be catching extended moves — review entries."}

    return {
        "description": (
            "Do signals with weekly wEMA10 confluence outperform daily-only signals? "
            "Weekly signals = daily MA touch AND price hugging wEMA10 with positive weekly slope. "
            "Higher timeframe confluence should mean fewer but higher-quality entries."
        ),
        "comparison": rows,
        "weekly_signal_count": len(weekly_trades),
        "daily_only_count":    len(daily_trades),
        "pct_weekly": round(len(weekly_trades) / (len(weekly_trades) + len(daily_trades)) * 100, 1)
                      if (weekly_trades or daily_trades) else 0,
        "verdict": verdict,
    }


def day_of_week_analysis(signal_type: str = None) -> dict:
    """
    Performance breakdown by signal day (MON-FRI).
    Tells you whether certain days produce better entries.
    Common patterns to look for:
      - Monday signals: early-week momentum, can be volatile after weekend gap
      - Tuesday/Wednesday: mid-week setups after market finds direction
      - Thursday: pre-Friday positioning, often strong
      - Friday: low conviction — many traders avoid new entries before weekend
    """
    DAY_ORDER = ["MON", "TUE", "WED", "THU", "FRI"]

    trades = get_historical_trades(signal_type=signal_type, limit=None)
    longs  = [t for t in trades if not t.get("is_short")]

    by_day = {}
    for t in longs:
        day = t.get("day_of_week") or "UNKNOWN"
        by_day.setdefault(day, []).append(t)

    rows = []
    for day in DAY_ORDER:
        day_trades = by_day.get(day, [])
        if not day_trades:
            rows.append({"day": day, "count": 0})
            continue
        s = compute_stats(day_trades)
        if not s:
            rows.append({"day": day, "count": 0})
            continue
        rows.append({
            "day":           day,
            "count":         len(day_trades),
            "win_rate":      s.get("win_rate"),
            "avg_pnl_pct":   s.get("avg_pnl_pct"),
            "avg_pnl_r":     s.get("avg_pnl_r"),
            "avg_hold_days": s.get("avg_hold_days"),
            "profit_factor": s.get("profit_factor"),
            "expectancy":    s.get("expectancy"),
        })

    # Best and worst days by expectancy
    scored = [r for r in rows if r.get("count", 0) >= 10]
    best  = max(scored, key=lambda r: r.get("expectancy", -99)) if scored else None
    worst = min(scored, key=lambda r: r.get("expectancy", 99))  if scored else None

    verdict = "Not enough trades per day to draw conclusions."
    if best and worst and best["day"] != worst["day"]:
        delta = (best.get("expectancy", 0) or 0) - (worst.get("expectancy", 0) or 0)
        verdict = (
            f"{best['day']} is your best entry day "
            f"({best.get('win_rate', 0):.0f}% WR, {best.get('expectancy', 0):.2f}% expectancy). "
            f"{worst['day']} is weakest "
            f"({worst.get('win_rate', 0):.0f}% WR, {worst.get('expectancy', 0):.2f}% expectancy). "
            f"Spread: {delta:.2f}% expectancy."
        )

    return {
        "description": (
            "Does the day you enter matter? "
            "Breakdown of win rate, expectancy and hold time by signal day. "
            "Use this to avoid low-probability entry days or weight your position sizing."
        ),
        "by_day": rows,
        "best_day":  best["day"]  if best  else None,
        "worst_day": worst["day"] if worst else None,
        "verdict": verdict,
    }


_analysis_cache: dict = {}   # signal_type → (trade_count, result)

def full_analysis_report(signal_type: str = None) -> dict:
    """
    One call to get everything: stats, all dimensional cuts, equity curve, monthly.
    Used by the /api/backtest/analysis endpoint.
    Caches result in memory — invalidated when trade count changes.
    """
    global _analysis_cache

    # Check cache — reuse if trade count hasn't changed
    try:
        from database import get_conn
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM historical_trades").fetchone()[0]
        cache_key = f"{signal_type}:{count}"
        if cache_key in _analysis_cache:
            return _analysis_cache[cache_key]
    except Exception:
        count = 0
        cache_key = f"{signal_type}:0"

    trades = get_historical_trades(signal_type=signal_type, entry_type="next_open", limit=None)

    # Fallback to all trades if no next_open entries found
    if not trades:
        trades = get_historical_trades(signal_type=signal_type, limit=None)

    if not trades:
        return {"error": "No historical trades found. Run reconstruction first."}

    # ── All trades (unfiltered) ───────────────────────────────────────────────
    base_stats = compute_stats(trades)
    curve      = build_equity_curve(trades)
    mae_mfe    = mae_mfe_analysis(signal_type)

    # ── Regime-gated stats (market_score >= 48, same as live NEUTRAL gate) ───
    # These are trades that would actually have been taken under the live strategy
    gated_trades = [t for t in trades if (t.get("market_score") or 0) >= 48]
    gated_stats  = compute_stats(gated_trades) if gated_trades else None
    gated_curve  = build_equity_curve(gated_trades) if gated_trades else []

    # ── How many signals were filtered out by regime ──────────────────────────
    try:
        from database import get_conn
        with get_conn() as conn:
            filtered_count = conn.execute(
                "SELECT COUNT(*) FROM historical_signals WHERE regime_filtered = 1"
            ).fetchone()[0]
            total_signals = conn.execute(
                "SELECT COUNT(*) FROM historical_signals"
            ).fetchone()[0]
    except Exception:
        filtered_count = 0
        total_signals  = len(trades)

    regime_summary = {
        "total_signals":     total_signals,
        "filtered_signals":  filtered_count,
        "traded_signals":    total_signals - filtered_count,
        "filter_pct":        round(filtered_count / total_signals * 100, 1) if total_signals else 0,
        "gate_threshold":    48,
    }

    result = {
        "signal_type":          signal_type or "ALL",
        "total_trades":         len(trades),
        "base_stats":           base_stats,
        # ── Regime-gated — the stats that matter for live trading ────────────
        "gated_trades":         len(gated_trades),
        "gated_stats":          gated_stats,
        "gated_equity_curve":   gated_curve,
        "regime_summary":       regime_summary,
        # ── Full dimensional cuts ────────────────────────────────────────────
        "by_sector":            sector_analysis(signal_type),
        "by_market_regime":     market_regime_analysis(signal_type),
        "by_vcs":               vcs_analysis(signal_type),
        "by_rs":                rs_analysis(signal_type),
        "by_base_score":        base_score_analysis(signal_type),
        "mae_mfe_analysis":     mae_mfe,
        "sector_rs_filter":     sector_rs_filter_analysis(signal_type),
        "weekly_signals":       weekly_signal_analysis(signal_type),
        "by_day_of_week":       day_of_week_analysis(signal_type),
        "equity_curve":         curve,
        "monthly_returns":      monthly_returns(trades),
        "entry_type_comparison": {
            "close_entry":     compute_stats(get_historical_trades(signal_type=signal_type, entry_type="close")),
            "next_open_entry": compute_stats(get_historical_trades(signal_type=signal_type, entry_type="next_open")),
        },
    }

    _analysis_cache[cache_key] = result
    return result


# ── In-sample / Out-of-sample split analysis ─────────────────────────────────

def split_analysis(
    signal_type: str = None,
    split_date: str = None,
    in_sample_months: int = 18,
) -> dict:
    """
    Splits historical trades into in-sample and out-of-sample periods
    and computes stats for each independently.

    This is the key test for whether your edge is real or overfitted:
    - In-sample: the period you tuned your parameters against (expect good numbers)
    - Out-of-sample: the period you never touched (tells you if the edge is genuine)

    If out-of-sample stats are similar to in-sample → edge is real.
    If out-of-sample collapses → parameters were overfit to history.

    Args:
        signal_type: filter by MA10/MA21/MA50/SHORT or None for all
        split_date: "YYYY-MM-DD" boundary between in/out-of-sample.
                    Defaults to (today - out_of_sample_months) ago.
        in_sample_months: how many recent months to treat as out-of-sample
                          (default 4 = roughly Nov 2024 onward)
    """
    from datetime import date, timedelta

    # Default split: last 4 months = out-of-sample
    if not split_date:
        oos_days   = in_sample_months * 30   # approx
        split_date = (date.today() - timedelta(days=oos_days)).isoformat()

    # Fetch all trades, then split by date
    all_trades = get_historical_trades(signal_type=signal_type, limit=None)

    in_sample  = [t for t in all_trades if t.get("signal_date", "") <  split_date]
    out_sample = [t for t in all_trades if t.get("signal_date", "") >= split_date]

    if not all_trades:
        return {"error": "No historical trades found. Run reconstruction first."}

    is_stats  = compute_stats(in_sample)
    oos_stats = compute_stats(out_sample)

    # Verdict: compare win rate and expectancy between the two periods
    verdict = _split_verdict(is_stats, oos_stats, len(in_sample), len(out_sample))

    # Per-signal-type breakdown for each period
    def _by_type(trades):
        by_type = {}
        for t in trades:
            st = t.get("signal_type") or "UNKNOWN"
            by_type.setdefault(st, []).append(t)
        return {
            st: compute_stats(ts)
            for st, ts in by_type.items()
            if len(ts) >= 5
        }

    # Monthly win rates for each period — shows if there's a single lucky streak
    def _monthly_wr(trades):
        from collections import defaultdict
        by_month = defaultdict(list)
        for t in trades:
            d = t.get("signal_date", "")
            if len(d) >= 7:
                by_month[d[:7]].append(t.get("pnl_pct", 0) or 0)
        return [
            {
                "month":    m,
                "trades":   len(pnls),
                "win_rate": round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 1),
                "avg_pnl":  round(sum(pnls) / len(pnls), 2),
            }
            for m, pnls in sorted(by_month.items())
            if pnls
        ]

    return {
        "split_date":        split_date,
        "explanation": (
            f"In-sample: trades before {split_date} — period used for tuning. "
            f"Out-of-sample: trades from {split_date} onward — never tuned against. "
            f"Compare the two to check whether your edge is real or overfit."
        ),
        "in_sample": {
            "label":          f"In-sample (before {split_date})",
            "trade_count":    len(in_sample),
            "stats":          is_stats,
            "by_signal_type": _by_type(in_sample),
            "monthly":        _monthly_wr(in_sample),
        },
        "out_of_sample": {
            "label":          f"Out-of-sample (from {split_date} onward)",
            "trade_count":    len(out_sample),
            "stats":          oos_stats,
            "by_signal_type": _by_type(out_sample),
            "monthly":        _monthly_wr(out_sample),
        },
        "verdict": verdict,
    }


def _split_verdict(is_stats: dict, oos_stats: dict, is_count: int, oos_count: int) -> dict:
    """
    Plain-English verdict on whether the edge held up out-of-sample.
    Uses win rate and expectancy as the two primary tests.
    """
    if not is_stats or not oos_stats:
        if oos_count < 10:
            return {
                "result":  "insufficient_data",
                "colour":  "grey",
                "summary": f"Only {oos_count} out-of-sample trades — need at least 10 for a meaningful test. Keep collecting data.",
                "detail":  [],
            }
        return {
            "result":  "insufficient_data",
            "colour":  "grey",
            "summary": "Not enough data in one or both periods to compare.",
            "detail":  [],
        }

    is_wr    = is_stats.get("win_rate", 0)
    oos_wr   = oos_stats.get("win_rate", 0)
    is_exp   = is_stats.get("avg_pnl_pct", 0)
    oos_exp  = oos_stats.get("avg_pnl_pct", 0)
    is_pf    = is_stats.get("profit_factor", 0)
    oos_pf   = oos_stats.get("profit_factor", 0)

    wr_drop  = is_wr  - oos_wr     # positive = OOS worse
    exp_drop = is_exp - oos_exp    # positive = OOS worse

    detail = [
        f"In-sample win rate: {is_wr:.1f}%  →  Out-of-sample: {oos_wr:.1f}%  (drop: {wr_drop:+.1f}pp)",
        f"In-sample avg return: {is_exp:+.2f}%  →  Out-of-sample: {oos_exp:+.2f}%  (drop: {exp_drop:+.2f}pp)",
        f"In-sample profit factor: {is_pf:.2f}  →  Out-of-sample: {oos_pf:.2f}",
        f"Trade counts: {is_count} in-sample, {oos_count} out-of-sample",
    ]

    # Thresholds for pass/warn/fail
    # Win rate allowed to drop up to 8pp before concern
    # Expectancy allowed to drop up to 0.5pp before concern
    oos_positive = oos_exp > 0 and oos_wr > 45

    if oos_count < 10:
        result, colour = "insufficient_data", "grey"
        summary = f"Only {oos_count} OOS trades — too few to conclude. Keep running the scanner."

    elif wr_drop <= 5 and exp_drop <= 0.3 and oos_positive:
        result, colour = "strong", "green"
        summary = (
            f"Edge held up well out-of-sample. Win rate dropped only {wr_drop:.1f}pp "
            f"and expectancy is still positive ({oos_exp:+.2f}%). "
            f"This is a good sign — the system isn't just fitting history."
        )

    elif wr_drop <= 10 and oos_positive:
        result, colour = "acceptable", "yellow"
        summary = (
            f"Edge partially held — win rate dropped {wr_drop:.1f}pp but remains positive. "
            f"Some degradation is normal. Paper trade before real money to confirm. "
            f"Watch whether the drop stabilises or keeps widening as more OOS data comes in."
        )

    elif oos_positive:
        result, colour = "degraded", "orange"
        summary = (
            f"Edge degraded significantly out-of-sample (win rate -{wr_drop:.1f}pp, "
            f"expectancy {oos_exp:+.2f}%). System may be partially overfit. "
            f"Do not increase position size. Review whether recent market conditions "
            f"differ from your tuning period."
        )

    else:
        result, colour = "failed", "red"
        summary = (
            f"Edge did not hold out-of-sample — negative expectancy ({oos_exp:+.2f}%) "
            f"and/or win rate below 45% ({oos_wr:.1f}%). "
            f"The parameters are likely overfit to historical data. "
            f"Do not trade this with real money yet. Re-examine your signal criteria."
        )

    return {
        "result":  result,
        "colour":  colour,
        "summary": summary,
        "detail":  detail,
        "metrics": {
            "in_sample_win_rate":      round(is_wr, 1),
            "out_of_sample_win_rate":  round(oos_wr, 1),
            "win_rate_drop_pp":        round(wr_drop, 1),
            "in_sample_expectancy":    round(is_exp, 2),
            "out_of_sample_expectancy": round(oos_exp, 2),
            "expectancy_drop_pp":      round(exp_drop, 2),
            "in_sample_profit_factor": round(is_pf, 2),
            "oos_profit_factor":       round(oos_pf, 2),
        },
    }



def entry_comparison_analysis() -> dict:
    """
    Compare MA Bounce (close entry) vs Breakout entry performance.
    Returns side-by-side stats including R-multiple, win rate, and
    % of signals that never trigger a breakout.
    """
    from database import get_conn

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT entry_type, pnl_pct, pnl_r, exit_reason, signal_type,
                   hold_days, stop_price, entry_price
            FROM historical_trades
            WHERE is_short = 0
        """).fetchall()

    if not rows:
        return {"error": "No trade data available"}

    from collections import defaultdict
    buckets = defaultdict(list)
    for row in rows:
        entry_type, pnl_pct, pnl_r, exit_reason, signal_type, hold_days, stop_price, entry_price = row
        buckets[entry_type or "close"].append({
            "pnl_pct": pnl_pct or 0,
            "pnl_r": pnl_r or 0,
            "exit_reason": exit_reason,
            "signal_type": signal_type,
            "hold_days": hold_days or 0,
        })

    def stats(trades):
        if not trades:
            return {}
        triggered = [t for t in trades if t["exit_reason"] != "no_trigger"]
        wins   = [t for t in triggered if t["pnl_pct"] > 0]
        losses = [t for t in triggered if t["pnl_pct"] <= 0]
        n = len(triggered)
        if n == 0:
            return {}
        win_rate    = len(wins) / n * 100
        avg_win     = sum(t["pnl_pct"] for t in wins)   / len(wins)   if wins   else 0
        avg_loss    = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
        avg_r       = sum(t["pnl_r"]   for t in triggered) / n
        avg_hold    = sum(t["hold_days"] for t in triggered) / n
        expectancy  = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss
        profit_factor = (
            abs(sum(t["pnl_pct"] for t in wins)) /
            abs(sum(t["pnl_pct"] for t in losses))
            if losses and wins else None
        )
        no_trigger_pct = (len(trades) - len(triggered)) / len(trades) * 100 if trades else 0

        # By signal type
        by_type = defaultdict(list)
        for t in triggered:
            by_type[t["signal_type"]].append(t["pnl_r"])
        signal_breakdown = {
            k: round(sum(v) / len(v), 2)
            for k, v in sorted(by_type.items(), key=lambda x: -sum(x[1]) / len(x[1]))
        }

        return {
            "n_signals":        len(trades),
            "n_triggered":      n,
            "no_trigger_pct":   round(no_trigger_pct, 1),
            "win_rate":         round(win_rate, 1),
            "avg_win_pct":      round(avg_win, 2),
            "avg_loss_pct":     round(avg_loss, 2),
            "avg_r":            round(avg_r, 2),
            "expectancy_pct":   round(expectancy, 2),
            "profit_factor":    round(profit_factor, 2) if profit_factor else None,
            "avg_hold_days":    round(avg_hold, 1),
            "signal_breakdown": signal_breakdown,
        }

    close_stats    = stats(buckets.get("close", []))
    breakout_stats = stats(buckets.get("breakout", []))

    # Verdict
    verdict = "insufficient_data"
    if close_stats and breakout_stats:
        c_r = close_stats.get("avg_r", 0)
        b_r = breakout_stats.get("avg_r", 0)
        b_nt = breakout_stats.get("no_trigger_pct", 0)
        if b_r > c_r and b_nt < 40:
            verdict = "breakout_better"
        elif c_r > b_r:
            verdict = "ma_bounce_better"
        else:
            verdict = "similar"

    return {
        "ma_bounce":  close_stats,
        "breakout":   breakout_stats,
        "verdict":    verdict,
    }
