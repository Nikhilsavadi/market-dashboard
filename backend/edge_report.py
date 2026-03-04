"""
edge_report.py
--------------
Analyses closed journal trades to surface edge patterns:
  - Win rate by signal type (MA10/21/50, CUP_HANDLE, BREAKOUT etc.)
  - Avg P&L by RS band (60-70, 70-80, 80-90, 90+)
  - Avg P&L by VCS band
  - Sector breakdown (best/worst sectors)
  - Hold time analysis (best exit timing)
  - Options calibration (estimated vs actual probability)
  - Score calibration (does signal_score predict outcomes?)
  - Kelly accuracy (were position sizes appropriate?)
  - Expectancy per signal type
"""

from database import get_conn
from typing import Optional
import statistics


def _safe_mean(vals):
    clean = [v for v in vals if v is not None]
    return round(statistics.mean(clean), 2) if clean else None


def _safe_median(vals):
    clean = [v for v in vals if v is not None]
    return round(statistics.median(clean), 2) if clean else None


def _win_rate(pnls):
    if not pnls:
        return None
    wins = sum(1 for p in pnls if p > 0)
    return round(wins / len(pnls) * 100, 1)


def _expectancy(pnls):
    """Avg profit * win_rate - avg_loss * loss_rate."""
    if not pnls:
        return None
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr     = len(wins) / len(pnls)
    lr     = len(losses) / len(pnls)
    avg_w  = _safe_mean(wins) or 0
    avg_l  = abs(_safe_mean(losses) or 0)
    return round(wr * avg_w - lr * avg_l, 2)


def get_closed_trades() -> list:
    """Fetch all closed/stopped trades from journal."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, ticker, signal_type, entry_price, exit_price,
                   pnl_pct, stop_price, target_1, target_2, target_3,
                   added_date, exit_date, exit_reason, vcs, rs,
                   signal_score, sector, notes, position_json,
                   thesis, confidence, regime_score, suggestion_score,
                   suggestion_ev, suggestion_structure, outcome_if_taken
            FROM journal
            WHERE status IN ('closed', 'stopped')
              AND pnl_pct IS NOT NULL
            ORDER BY exit_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_skipped_trades() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, ticker, signal_type, entry_price, target_1,
                   added_date, vcs, rs, sector, status,
                   skip_reason, skip_note, suggestion_score,
                   suggestion_ev, suggestion_structure,
                   regime_score, outcome_if_taken, notes
            FROM journal
            WHERE status = 'skipped'
            ORDER BY added_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_all_suggestions() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, ticker, status, signal_type, entry_price,
                   exit_price, pnl_pct, target_1, added_date, exit_date,
                   vcs, rs, sector, signal_score, suggestion_score,
                   suggestion_ev, suggestion_structure,
                   skip_reason, skip_note, outcome_if_taken, regime_score
            FROM journal
            WHERE suggestion_score IS NOT NULL OR status = 'skipped'
            ORDER BY added_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def _week_label(date_str: str) -> str:
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        return f"{d.year}-W{d.isocalendar()[1]:02d}"
    except Exception:
        return "unknown"


def taken_vs_skipped_analysis(taken: list, skipped: list) -> dict:
    taken_pnls = [t["pnl_pct"] for t in taken if t.get("pnl_pct") is not None]
    skipped_outcomes = []
    for s in skipped:
        if s.get("outcome_if_taken") is not None:
            skipped_outcomes.append(s["outcome_if_taken"])
        elif s.get("target_1") and s.get("entry_price") and s["entry_price"] > 0:
            est = (s["target_1"] - s["entry_price"]) / s["entry_price"] * 100
            skipped_outcomes.append(round(est, 1))
    opp_cost = round((_safe_mean(skipped_outcomes) or 0) - (_safe_mean(taken_pnls) or 0), 2)
    return {
        "taken":  {"count": len(taken),   "win_rate": _win_rate(taken_pnls),  "avg_pnl": _safe_mean(taken_pnls),  "expectancy": _expectancy(taken_pnls), "total_pnl": round(sum(taken_pnls),2) if taken_pnls else 0},
        "skipped":{"count": len(skipped), "estimated_avg": _safe_mean(skipped_outcomes), "estimated_total": round(sum(skipped_outcomes),2) if skipped_outcomes else 0, "has_actuals": sum(1 for s in skipped if s.get("outcome_if_taken") is not None)},
        "opportunity_cost": opp_cost,
        "verdict": ("Taking was correct — taken trades outperforming skipped estimates" if (_safe_mean(taken_pnls) or 0) >= (_safe_mean(skipped_outcomes) or 0) else "Skipped trades may have outperformed — review skip reasons"),
    }


def skip_reason_analysis(skipped: list, taken: list) -> dict:
    by_reason = {}
    for s in skipped:
        reason = s.get("skip_reason") or "unspecified"
        by_reason.setdefault(reason, []).append(s)
    taken_avg = _safe_mean([t["pnl_pct"] for t in taken if t.get("pnl_pct")]) or 0
    rows = []
    for reason, entries in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        est = []
        for e in entries:
            if e.get("outcome_if_taken") is not None:
                est.append(e["outcome_if_taken"])
            elif e.get("target_1") and e.get("entry_price") and e["entry_price"] > 0:
                est.append((e["target_1"] - e["entry_price"]) / e["entry_price"] * 100)
        avg_missed = _safe_mean(est)
        cost_vs_taken = round((avg_missed or 0) - taken_avg, 2) if avg_missed is not None else None
        rows.append({"reason": reason, "count": len(entries), "avg_score": _safe_mean([e.get("suggestion_score") for e in entries]), "avg_ev": _safe_mean([e.get("suggestion_ev") for e in entries]), "avg_missed_gain": avg_missed, "cost_vs_taken": cost_vs_taken, "flag": cost_vs_taken is not None and cost_vs_taken > 5})
    rows.sort(key=lambda x: (x.get("avg_missed_gain") or 0), reverse=True)
    return {"by_reason": rows, "taken_avg_pnl": taken_avg}


def override_analysis(taken: list, skipped: list) -> dict:
    HIGH_SCORE, LOW_SCORE = 8.0, 7.0
    hs_skips = [s for s in skipped if (s.get("suggestion_score") or 0) >= HIGH_SCORE]
    ls_takes = [t for t in taken  if (t.get("suggestion_score") or 0) < LOW_SCORE and t.get("suggestion_score") is not None]
    hs_out = [s["outcome_if_taken"] for s in hs_skips if s.get("outcome_if_taken") is not None]
    for s in hs_skips:
        if s.get("outcome_if_taken") is None and s.get("target_1") and s.get("entry_price") and s["entry_price"] > 0:
            hs_out.append((s["target_1"] - s["entry_price"]) / s["entry_price"] * 100)
    ls_pnls = [t["pnl_pct"] for t in ls_takes if t.get("pnl_pct") is not None]
    return {
        "high_score_skips": {"count": len(hs_skips), "threshold": HIGH_SCORE, "avg_score": _safe_mean([s.get("suggestion_score") for s in hs_skips]), "top_reasons": list({s.get("skip_reason") for s in hs_skips if s.get("skip_reason")}), "avg_missed": _safe_mean(hs_out), "verdict": ("Good discipline — high score skips had low estimated returns" if not hs_out or (_safe_mean(hs_out) or 0) < 5 else f"Review — {len(hs_skips)} high-score setups skipped, ~{_safe_mean(hs_out):.1f}% avg estimated gain missed")},
        "low_score_takes":  {"count": len(ls_takes), "threshold": LOW_SCORE, "avg_score": _safe_mean([t.get("suggestion_score") for t in ls_takes]), "win_rate": _win_rate(ls_pnls), "avg_pnl": _safe_mean(ls_pnls), "verdict": ("No below-threshold trades taken — good discipline" if not ls_takes else f"Concern: {len(ls_takes)} trades taken below score {LOW_SCORE}, {_win_rate(ls_pnls) or 0:.0f}% win rate")},
    }


def weekly_tally(all_entries: list) -> list:
    by_week = {}
    for e in all_entries:
        week = _week_label(e.get("added_date") or "")
        if week not in by_week:
            by_week[week] = {"taken": [], "skipped": []}
        if e["status"] == "skipped":
            by_week[week]["skipped"].append(e)
        else:
            by_week[week]["taken"].append(e)
    rows = []
    for week in sorted(by_week.keys(), reverse=True)[:12]:
        data = by_week[week]
        closed_pnls = [t["pnl_pct"] for t in data["taken"] if t.get("pnl_pct") is not None and t.get("status") in ("closed","stopped")]
        rows.append({"week": week, "taken": len(data["taken"]), "skipped": len(data["skipped"]), "total": len(data["taken"])+len(data["skipped"]), "take_rate": round(len(data["taken"])/(len(data["taken"])+len(data["skipped"]))*100,0) if (data["taken"] or data["skipped"]) else None, "closed": len(closed_pnls), "win_rate": _win_rate(closed_pnls), "avg_pnl": _safe_mean(closed_pnls)})
    return rows


def _band(value, bands):
    """Return band label for a numeric value."""
    if value is None:
        return "unknown"
    for low, high, label in bands:
        if low <= value < high:
            return label
    return f">{bands[-1][1]}"


def generate_edge_report() -> dict:
    """
    Full edge analysis. Returns structured dict for API and frontend.
    """
    trades = get_closed_trades()

    if not trades:
        return {"trades": 0, "message": "No closed trades yet. Start trading and close positions to build your edge report."}

    pnls = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
    days_held = []
    for t in trades:
        try:
            from datetime import date
            d = (date.fromisoformat(t["exit_date"]) - date.fromisoformat(t["added_date"])).days
            days_held.append(d)
        except Exception:
            pass

    # ── Overall stats ────────────────────────────────────────────────────
    # £ PnL — only for trades that have position_size_gbp recorded
    gbp_pnls = [t["pnl_gbp"] for t in trades if t.get("pnl_gbp") is not None]
    gbp_sizes = [t["position_size_gbp"] for t in trades if t.get("position_size_gbp") is not None]
    has_gbp   = len(gbp_pnls) > 0

    overall = {
        "total_trades":   len(trades),
        "win_rate":       _win_rate(pnls),
        "avg_pnl":        _safe_mean(pnls),
        "median_pnl":     _safe_median(pnls),
        "expectancy":     _expectancy(pnls),
        "avg_hold_days":  _safe_mean(days_held),
        "best_trade":     max(pnls) if pnls else None,
        "worst_trade":    min(pnls) if pnls else None,
        "total_pnl":      round(sum(pnls), 2) if pnls else 0,
        "gross_wins":     round(sum(p for p in pnls if p > 0), 2),
        "gross_losses":   round(sum(p for p in pnls if p <= 0), 2),
        "profit_factor":  round(
            sum(p for p in pnls if p > 0) / abs(sum(p for p in pnls if p <= 0))
            if any(p <= 0 for p in pnls) and any(p > 0 for p in pnls) else 0, 2
        ),
        # £ figures — populated once position_size_gbp is stored on trades
        "gbp_trades_with_size": len(gbp_pnls),
        "total_pnl_gbp":  round(sum(gbp_pnls), 2) if has_gbp else None,
        "avg_pnl_gbp":    round(sum(gbp_pnls) / len(gbp_pnls), 2) if has_gbp else None,
        "avg_position_gbp": round(sum(gbp_sizes) / len(gbp_sizes), 2) if gbp_sizes else None,
        "gbp_note": (
            f"£ figures based on {len(gbp_pnls)} of {len(trades)} trades with recorded position size"
            if has_gbp else
            "Set position_size_gbp when adding journal entries to track £ PnL"
        ),
    }

    # ── By signal type ───────────────────────────────────────────────────
    by_signal = {}
    for t in trades:
        st = t.get("signal_type") or "UNKNOWN"
        by_signal.setdefault(st, []).append(t["pnl_pct"])

    signal_breakdown = []
    for st, ps in sorted(by_signal.items()):
        signal_breakdown.append({
            "signal_type": st,
            "trades":      len(ps),
            "win_rate":    _win_rate(ps),
            "avg_pnl":     _safe_mean(ps),
            "expectancy":  _expectancy(ps),
            "best":        max(ps),
            "worst":       min(ps),
        })
    signal_breakdown.sort(key=lambda x: x["expectancy"] or -99, reverse=True)

    # ── By RS band ───────────────────────────────────────────────────────
    rs_bands_def = [(0,70,"<70"), (70,80,"70-80"), (80,90,"80-90"), (90,95,"90-95"), (95,101,"95+")]
    by_rs = {}
    for t in trades:
        band = _band(t.get("rs"), rs_bands_def)
        by_rs.setdefault(band, []).append(t["pnl_pct"])

    rs_breakdown = [
        {"band": b, "trades": len(ps), "win_rate": _win_rate(ps), "avg_pnl": _safe_mean(ps), "expectancy": _expectancy(ps)}
        for b, ps in sorted(by_rs.items())
    ]

    # ── By VCS band ──────────────────────────────────────────────────────
    vcs_bands_def = [(0,2,"VCS 0-2"), (2,4,"VCS 2-4"), (4,6,"VCS 4-6"), (6,8,"VCS 6-8"), (8,100,"VCS 8+")]
    by_vcs = {}
    for t in trades:
        band = _band(t.get("vcs"), vcs_bands_def)
        by_vcs.setdefault(band, []).append(t["pnl_pct"])

    vcs_breakdown = [
        {"band": b, "trades": len(ps), "win_rate": _win_rate(ps), "avg_pnl": _safe_mean(ps)}
        for b, ps in sorted(by_vcs.items())
    ]

    # ── By sector ────────────────────────────────────────────────────────
    by_sector = {}
    for t in trades:
        s = t.get("sector") or "Unknown"
        by_sector.setdefault(s, []).append(t["pnl_pct"])

    sector_breakdown = [
        {"sector": s, "trades": len(ps), "win_rate": _win_rate(ps), "avg_pnl": _safe_mean(ps), "expectancy": _expectancy(ps)}
        for s, ps in by_sector.items()
    ]
    sector_breakdown.sort(key=lambda x: x["expectancy"] or -99, reverse=True)

    # ── Score calibration ────────────────────────────────────────────────
    score_bands_def = [(0,5,"<5"), (5,7,"5-7"), (7,8,"7-8"), (8,9,"8-9"), (9,11,"9-10")]
    by_score = {}
    for t in trades:
        band = _band(t.get("signal_score"), score_bands_def)
        by_score.setdefault(band, []).append(t["pnl_pct"])

    score_calibration = [
        {"score_band": b, "trades": len(ps), "win_rate": _win_rate(ps), "avg_pnl": _safe_mean(ps)}
        for b, ps in sorted(by_score.items())
    ]

    # ── Exit reason breakdown ─────────────────────────────────────────────
    by_exit = {}
    for t in trades:
        r = t.get("exit_reason") or "manual"
        by_exit.setdefault(r, []).append(t["pnl_pct"])

    exit_breakdown = [
        {"reason": r, "trades": len(ps), "avg_pnl": _safe_mean(ps), "win_rate": _win_rate(ps)}
        for r, ps in by_exit.items()
    ]
    exit_breakdown.sort(key=lambda x: x["avg_pnl"] or -99, reverse=True)

    # ── Hold time analysis ────────────────────────────────────────────────
    hold_bands_def = [(0,3,"1-2d"), (3,6,"3-5d"), (6,11,"6-10d"), (11,21,"11-20d"), (21,999,"21d+")]
    by_hold = {}
    for t in trades:
        try:
            from datetime import date
            d = (date.fromisoformat(t["exit_date"]) - date.fromisoformat(t["added_date"])).days
            band = _band(d, hold_bands_def)
            by_hold.setdefault(band, []).append(t["pnl_pct"])
        except Exception:
            pass

    hold_breakdown = [
        {"days": b, "trades": len(ps), "win_rate": _win_rate(ps), "avg_pnl": _safe_mean(ps)}
        for b, ps in sorted(by_hold.items())
    ]

    # ── Recent form (last 10 trades) ──────────────────────────────────────
    recent_10    = trades[:10]
    recent_pnls  = [t["pnl_pct"] for t in recent_10]
    recent_form  = {
        "trades":    len(recent_10),
        "win_rate":  _win_rate(recent_pnls),
        "avg_pnl":   _safe_mean(recent_pnls),
        "streak":    _current_streak(trades),
    }

    # ── Equity curve (cumulative P&L per trade) ───────────────────────────
    equity_curve = []
    cumulative   = 0
    for t in reversed(trades):  # chronological
        cumulative += t["pnl_pct"] or 0
        equity_curve.append({
            "date":       t.get("exit_date", ""),
            "ticker":     t.get("ticker", ""),
            "pnl":        t.get("pnl_pct", 0),
            "cumulative": round(cumulative, 2),
        })

    # ── Skip analytics ───────────────────────────────────────────────────
    skipped      = get_skipped_trades()
    all_entries  = get_all_suggestions()

    # For taken vs skipped: use closed trades as "taken" (have real outcomes)
    taken_closed = [t for t in trades]  # already closed/stopped with pnl_pct

    skip_analytics = {
        "taken_vs_skipped":  taken_vs_skipped_analysis(taken_closed, skipped),
        "skip_reason_breakdown": skip_reason_analysis(skipped, taken_closed),
        "override_tracking": override_analysis(taken_closed, skipped),
        "weekly_tally":      weekly_tally(all_entries),
        "skipped_count":     len(skipped),
        "taken_count":       len(trades),
        "take_rate": round(len(trades) / (len(trades) + len(skipped)) * 100, 1)
                     if (trades or skipped) else None,
    }

    return {
        "generated_at":      __import__("datetime").datetime.now().isoformat(),
        "overall":           overall,
        "signal_breakdown":  signal_breakdown,
        "rs_breakdown":      rs_breakdown,
        "vcs_breakdown":     vcs_breakdown,
        "sector_breakdown":  sector_breakdown,
        "score_calibration": score_calibration,
        "exit_breakdown":    exit_breakdown,
        "hold_breakdown":    hold_breakdown,
        "recent_form":       recent_form,
        "equity_curve":      equity_curve,
        "skip_analytics":    skip_analytics,
        "raw_trades":        trades[:50],
        "raw_skipped":       skipped[:50],
    }


def _current_streak(trades: list) -> dict:
    """Calculate current win/loss streak."""
    if not trades:
        return {"type": "none", "count": 0}
    streak_type = "win" if trades[0]["pnl_pct"] > 0 else "loss"
    count = 0
    for t in trades:
        if (streak_type == "win" and t["pnl_pct"] > 0) or \
           (streak_type == "loss" and t["pnl_pct"] <= 0):
            count += 1
        else:
            break
    return {"type": streak_type, "count": count}
