"""
alerts.py - V2
--------------
V2 improvements:
- Setup of the Day (SOTD) — single best long + short, sent first
- Tier-based filtering — only alert if signal score >= tier threshold
- Duplicate suppression — don't alert on tickers already in journal
- Market regime gate — warn when market is negative
- VIX + breadth in header
"""

import os
import requests
from datetime import datetime
from typing import Optional


def _send(text: str, parse_mode: str = "HTML") -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[alerts] Telegram not configured — skipping")
        return False
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True,
        }, timeout=10)
        if resp.status_code == 200:
            print(f"[alerts] Sent ({len(text)} chars)")
            return True
        print(f"[alerts] Error {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        print(f"[alerts] Exception: {e}")
        return False


def _earn_flag(days: Optional[int]) -> str:
    if days is None: return ""
    if days <= 2:    return " ⚠️ EARN<3d"
    if days <= 7:    return f" ⚡earn{days}d"
    return ""


def _vcs_label(vcs: Optional[float]) -> str:
    if vcs is None: return "—"
    if vcs <= 2:    return f"{vcs} 🔥🔥"
    if vcs <= 3:    return f"{vcs} 🔥"
    if vcs <= 5:    return f"{vcs} ✓"
    return str(vcs)


def _score_bar(score: Optional[float]) -> str:
    """Visual score bar: ████░░ 7.2"""
    if score is None: return "?"
    filled = int(round(score))
    bar    = "█" * filled + "░" * (10 - filled)
    return f"{bar} {score}"


def _format_long(s: dict, is_sotd: bool = False) -> str:
    ticker    = s.get("ticker", "")
    price     = s.get("price", 0)
    chg       = s.get("chg", 0)
    bounce    = s.get("bouncing_from", "—")
    vcs       = _vcs_label(s.get("vcs"))
    rs        = s.get("rs", 0)
    vol_ratio = s.get("vol_ratio") or 0
    score     = s.get("signal_score")
    earn_flag = _earn_flag(s.get("days_to_earnings"))
    base_type = s.get("base_type", "none")
    base_score= s.get("base_score", 0)
    tier      = s.get("tier", 2)
    chg_str   = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    stop      = s.get("stop_price")
    t1        = s.get("target_1")
    pos       = s.get("position", {})
    shares    = pos.get("shares") if pos else None
    risk_amt  = pos.get("risk_amount") if pos else None
    is_weekly = bool(s.get("is_weekly_signal", False))

    header = f"⭐ <b>SETUP OF THE DAY</b>\n" if is_sotd else ""
    weekly_str = "\n  📅 <b>WEEKLY CONFLUENCE</b> — wEMA10 touch, slope rising" if is_weekly else ""
    base_str = ""
    if base_type and base_type != "none":
        emoji = {"flat": "📐", "cup": "☕", "vcp": "🌀"}.get(base_type, "")
        base_str = f"\n  {emoji} {base_type.upper()} base (score {base_score})"

    pos_str = ""
    if shares and risk_amt:
        pos_str = f"\n  📐 {int(shares)} shares · risk £{risk_amt:.0f}"

    tier_str = f" [T{tier}]" if tier > 1 else ""

    return (
        f"\n{header}"
        f"<b>{ticker}</b>{tier_str} ${price:.2f} ({chg_str}){earn_flag}\n"
        f"  {bounce} bounce | VCS: {vcs} | RS: {rs} | Vol: {vol_ratio:.1f}x\n"
        f"  Score: {_score_bar(score)}{base_str}{weekly_str}"
        f"{pos_str}"
        + (f"\n  Stop: ${stop:.2f} → T1: ${t1:.2f}" if stop and t1 else "")
    )


def _format_short(s: dict, is_sotd: bool = False) -> str:
    ticker    = s.get("ticker", "")
    price     = s.get("price", 0)
    chg       = s.get("chg", 0)
    score     = s.get("short_score", 0)
    rs        = s.get("rs", 0)
    earn_flag = _earn_flag(s.get("days_to_earnings"))
    failed    = "✓ failed rally" if s.get("failed_rally") else ""
    chg_str   = f"{chg:.1f}%"
    header    = f"⭐ <b>SHORT OF THE DAY</b>\n" if is_sotd else ""
    return (
        f"\n{header}"
        f"<b>{ticker}</b> ${price:.2f} ({chg_str}){earn_flag}\n"
        f"  Short score: {score} | RS: {rs} {failed}"
    )


def send_scan_alert(payload: dict, open_tickers: set = None):
    """Send scan results to Telegram. V2: SOTD first, tier filtering, regime gate."""
    import os
    open_tickers  = open_tickers or set()

    # ── Pre-flight diagnostics ────────────────────────────────────────────
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    print(f"[alerts] token_set={bool(token)} chat_id_set={bool(chat_id)}")
    if not token or not chat_id:
        print("[alerts] ✗ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing — no alert sent")
        print("[alerts]   Fix: add both as Railway environment variables")
        return
    scanned_at    = payload.get("scanned_at", "")
    total         = payload.get("total_scanned", 0)
    market        = payload.get("market", {})
    mkt_label     = market.get("label", "?")
    mkt_score     = market.get("score", 0)
    mkt_emoji     = "🟢" if mkt_label == "Positive" else "🟡" if mkt_label == "Neutral" else "🔴"
    regime_warn   = market.get("regime_warning", "")
    vix           = market.get("vix")
    breadth       = (market.get("breadth") or {}).get("breadth_50ma_pct")
    heat          = payload.get("portfolio_heat", {})
    heat_pct      = heat.get("heat_pct", 0)
    slots         = heat.get("slots_available", 5)

    settings      = payload.get("settings", {})
    alert_min     = settings.get("alert_min_score", 7)

    # ── Header ────────────────────────────────────────────────────────────
    header_lines = [
        f"<b>📊 SIGNAL DESK — {scanned_at}</b>",
        f"{mkt_emoji} Market: <b>{mkt_label}</b> ({mkt_score}) | {total} scanned",
    ]
    if vix:
        header_lines.append(f"VIX: {vix:.1f}" + (f" · Breadth: {breadth}%" if breadth else ""))
    if regime_warn:
        header_lines.append(f"⚠️ {regime_warn}")
    if heat_pct > 0:
        header_lines.append(f"Portfolio heat: {heat_pct:.1f}% · {slots} slot{'s' if slots != 1 else ''} available")

    # ── Setup of the Day ──────────────────────────────────────────────────
    sotd_long  = payload.get("sotd_long")
    sotd_short = payload.get("sotd_short")

    sotd_lines = list(header_lines)
    if sotd_long:
        sotd_lines.append(_format_long(sotd_long, is_sotd=True))
    if sotd_short:
        sotd_lines.append(_format_short(sotd_short, is_sotd=True))

    _send("\n".join(sotd_lines))

    # ── Long signals — filtered by score + tier, suppress duplicates ──────
    all_longs = (
        payload.get("ma10_bounces", []) +
        payload.get("ma21_bounces", []) +
        payload.get("ma50_bounces", [])
    )

    print(f"[alerts] alert_min_score={alert_min} | total longs={len(all_longs)}")
    for s in all_longs[:5]:
        score = s.get("signal_score") or 0
        in_journal = s.get("ticker") in open_tickers
        passes = score >= alert_min and not in_journal
        print(f"[alerts]   {s.get('ticker')}: score={score:.1f} journal={in_journal} → {'SEND' if passes else 'SKIP'}")

    alertable_longs = [
        s for s in all_longs
        if (s.get("signal_score") or 0) >= alert_min
        and s.get("ticker") not in open_tickers
        and s.get("ticker") != (sotd_long or {}).get("ticker")  # skip SOTD duplicate
    ][:8]
    print(f"[alerts] alertable_longs after filter: {len(alertable_longs)}")

    if alertable_longs:
        ma10 = payload.get("ma10_bounces", [])
        ma21 = payload.get("ma21_bounces", [])
        ma50 = payload.get("ma50_bounces", [])
        long_lines = [
            f"\n<b>▲ LONG SETUPS (score ≥{alert_min}) — "
            f"{len(ma10)} MA10 · {len(ma21)} MA21 · {len(ma50)} MA50</b>"
        ]
        for s in alertable_longs:
            long_lines.append(_format_long(s))

        # Suppressed count
        suppressed = len([s for s in all_longs if s.get("ticker") in open_tickers])
        if suppressed:
            long_lines.append(f"\n<i>+{suppressed} already in journal (suppressed)</i>")

        _send("\n".join(long_lines))

    # ── Short signals ──────────────────────────────────────────────────────
    shorts = [
        s for s in payload.get("short_signals", [])[:8]
        if s.get("ticker") != (sotd_short or {}).get("ticker")
    ]
    if shorts:
        short_lines = [f"<b>▼ SHORT SETUPS ({len(payload.get('short_signals', []))} candidates)</b>"]
        for s in shorts[:6]:
            short_lines.append(_format_short(s))
        _send("\n".join(short_lines))


def send_journal_alert(ticker: str, action: str, details: dict):
    """Alert when a journal entry is added or closed."""
    if action == "added":
        pos   = details.get("position", {}) or {}
        score = details.get("signal_score", "?")
        msg = (
            f"📝 <b>Journal: {ticker} added</b>\n"
            f"Entry: ${details.get('entry_price', '?')} | Score: {score}\n"
            f"Stop: ${details.get('stop_price', '?')}\n"
            f"T1: ${details.get('target_1', '?')} · T2: ${details.get('target_2', '?')} · T3: ${details.get('target_3', '?')}\n"
            f"Signal: {details.get('signal_type', '?')} | VCS: {details.get('vcs', '?')} | RS: {details.get('rs', '?')}"
        )
        if pos.get("shares"):
            msg += f"\n📐 Size: {int(pos['shares'])} shares · risk £{pos.get('risk_amount', 0):.0f}"
    elif action == "closed":
        pnl   = details.get("pnl_pct", 0)
        emoji = "✅" if pnl > 0 else "❌"
        msg = (
            f"{emoji} <b>Journal: {ticker} closed</b>\n"
            f"P&L: {'+' if pnl > 0 else ''}{pnl:.1f}%\n"
            f"Exit: ${details.get('exit_price', '?')} — {details.get('exit_reason', '?')}\n"
            f"Held: {details.get('days_held', '?')} days"
        )
    else:
        return
    _send(msg)


def send_position_update(ticker: str, action: str, current_px: float, pnl_pct: float, days_held: int):
    """Send individual position update (called by journal_tracker for critical events)."""
    emoji_map = {
        "stop_hit":   "⛔",
        "t3_hit":     "🎯",
        "t2_hit":     "✅",
        "t1_hit":     "✅",
        "timeout":    "⏰",
        "losing_old": "⚠️",
    }
    emoji = emoji_map.get(action, "📊")
    label = {
        "stop_hit":   "STOP HIT",
        "t3_hit":     "TARGET 3 HIT",
        "t2_hit":     "Target 2 hit",
        "t1_hit":     "Target 1 hit",
        "timeout":    "Time exit",
        "losing_old": "Review needed",
    }.get(action, action)

    _send(
        f"{emoji} <b>{ticker} — {label}</b>\n"
        f"Current: ${current_px:.2f} | P&L: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%\n"
        f"Days held: {days_held}"
    )
