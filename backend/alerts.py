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
        print(f"[alerts]   {s.get('ticker')}: score={score:.1f} journal={in_journal} -> {'SEND' if passes else 'SKIP'}")

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


def send_ep_alert(ep_result: dict):
    """Send EP scan results to Telegram — replaces old Signal Desk format."""
    summary = ep_result.get("summary", {})
    breadth = ep_result.get("sp500_breadth", {})
    bear_regime = ep_result.get("bear_regime", False)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    regime = breadth.get("regime", "NEUTRAL")
    regime_emoji = {"BULLISH": "🟢", "NEUTRAL": "🟡", "BEARISH": "🔴"}.get(regime, "🟡")
    breadth_pct = breadth.get("pct_above_50ma")
    breadth_str = f" ({breadth_pct:.0f}%)" if breadth_pct is not None else ""

    # ── Header ──
    lines = [
        f"<b>📊 EP SCANNER — {now}</b>",
        f"{regime_emoji} Market: <b>{regime}</b>{breadth_str}",
    ]
    if bear_regime:
        lines.append("⚠️ <b>BEAR REGIME</b> — shorts promoted, longs selective only")
    guidance = breadth.get("trade_guidance")
    if guidance and not bear_regime:
        lines.append(f"💡 {guidance}")

    total_long = summary.get("total_long_eps", 0)
    total_short = summary.get("total_short_eps", 0)
    actionable = summary.get("actionable", 0)
    lines.append(f"Found: {total_long} long · {total_short} short · {actionable} actionable")

    _send("\n".join(lines))

    # ── Actionable Long EPs (tiers 1-3) ──
    actionable_eps = ep_result.get("actionable_eps", [])
    if actionable_eps:
        long_lines = [f"\n<b>▲ LONG EPs — {len(actionable_eps)} actionable</b>"]
        for s in actionable_eps[:5]:
            long_lines.append(_format_ep_long(s))
        _send("\n".join(long_lines))

    # ── Short EPs ──
    short_eps = ep_result.get("all_short_eps", [])
    if short_eps:
        short_lines = [f"\n<b>🔻 SHORT EPs — {len(short_eps)} found</b>"]
        for s in short_eps[:5]:
            short_lines.append(_format_ep_short(s))
        _send("\n".join(short_lines))

    # ── Sector themes ──
    theme = ep_result.get("theme_summary", {})
    hot_sectors = theme.get("hot_sectors", {})
    if hot_sectors:
        theme_lines = ["<b>🔥 HOT SECTORS</b>"]
        for sector, count in sorted(hot_sectors.items(), key=lambda x: -x[1]):
            theme_lines.append(f"  {sector}: {count} EPs")
        _send("\n".join(theme_lines))

    # ── VCP formations on watchlist ──
    vcp_list = ep_result.get("vcp_formations", [])
    if vcp_list:
        vcp_lines = [f"<b>📐 VCP FORMING — {len(vcp_list)} watchlist stocks</b>"]
        for v in vcp_list[:5]:
            vcp_lines.append(
                f"  {v['ticker']} — {v['contractions']} contractions, "
                f"tightness {v['tightness_score']}/10"
                f"{' | Pivot $' + str(v['pivot_price']) if v.get('pivot_price') else ''}"
            )
        _send("\n".join(vcp_lines))

    # If nothing actionable at all
    if not actionable_eps and not short_eps:
        _send("No actionable EP setups today. Watchlist only.")


def _format_ep_long(s: dict) -> str:
    """Format a single long EP signal for Telegram."""
    ticker = s.get("ticker", "")
    price = s.get("price", 0)
    ep_type = s.get("ep_type", "")
    tier_label = s.get("tier_label", "")
    tier_sizing = s.get("tier_sizing", "")
    gap_pct = s.get("ep_gap_pct") or s.get("gap_pct", 0)
    vol_ratio = s.get("ep_vol_ratio") or s.get("vol_ratio", 0)
    magna = s.get("magna_score", 0)
    ti65 = s.get("ti65_label", "")
    tt_score = s.get("tt_score", 0)

    intel = s.get("entry_intel", {})
    zone_lo = intel.get("entry_zone_low")
    zone_hi = intel.get("entry_zone_high")
    stop = intel.get("stop_price")
    r1 = (intel.get("r_levels") or {}).get("r1")
    quality = intel.get("entry_quality", "")

    # Tier emoji
    tier_emoji = {"MAX BET": "🥇", "STRONG": "🥈", "NORMAL": "🥉"}.get(tier_label, "")

    name = s.get("name", "")
    name_str = f" {name}" if name else ""
    line = f"\n{tier_emoji} <b>{ticker}</b>{name_str} ${price:.2f} | {ep_type} | {tier_label} ({tier_sizing})"
    line += f"\n  Gap {gap_pct:+.0f}% · Vol {vol_ratio:.0f}x · MAGNA {magna}/7"

    if ti65 and ti65 != "N/A":
        line += f" · TI65 {ti65}"
    if tt_score >= 3:
        line += f" · TT {tt_score}/7"

    if zone_lo and zone_hi and stop:
        line += f"\n  Entry: ${zone_lo}-${zone_hi} | Stop: ${stop:.2f}"
        if r1:
            line += f" | T1: ${r1:.2f}"
    if quality:
        line += f" | {quality}"

    # Sector theme
    theme_score = s.get("sector_theme_score", 0)
    if theme_score >= 2:
        line += f"\n  🔥 {s.get('sector', '')} theme ({theme_score} peers)"

    # Earnings countdown
    days_earn = s.get("days_until_earnings")
    if days_earn is not None:
        if 0 < days_earn <= 7:
            line += f" | ⚠️ Earnings in {days_earn}d"
        elif 7 < days_earn <= 42:
            line += f" | 📅 Earnings {days_earn}d"

    # Pyramid hint
    plan = s.get("pyramid_plan", {})
    if plan.get("has_plan"):
        init = plan.get("initial", {})
        line += f"\n  📈 Pyramid: {init.get('shares', 0)} shares → add at T1/T2"

    return line


def _format_ep_short(s: dict) -> str:
    """Format a single short EP signal for Telegram."""
    ticker = s.get("ticker", "")
    price = s.get("price", 0)
    ep_type = s.get("ep_type", "")
    badge = s.get("ep_badge", "SHORT EP")
    gap_pct = s.get("ep_gap_pct") or s.get("gap_pct", 0)
    vol_ratio = s.get("ep_vol_ratio") or s.get("vol_ratio", 0)
    magna = s.get("short_magna_score", 0)
    catalyst = s.get("ep_catalyst_label") or s.get("catalyst_label", "")
    catalyst_type = s.get("ep_catalyst_type") or s.get("catalyst_type", "")

    intel = s.get("entry_intel", {})
    zone_lo = intel.get("entry_zone_low")
    zone_hi = intel.get("entry_zone_high")
    stop = intel.get("stop_price")
    quality = intel.get("entry_quality", "")

    # Catalyst emoji
    cat_emoji = {
        "EARNINGS_MISS": "📉", "GUIDANCE_CUT": "📉", "DOWNGRADE": "⬇️",
        "ACCOUNTING": "🚩", "REGULATORY": "⚖️",
    }.get(catalyst_type, "❓")

    name = s.get("name", "")
    name_str = f" {name}" if name else ""
    line = f"\n🔻 <b>{ticker}</b>{name_str} ${price:.2f} | {badge}"
    line += f"\n  Gap {gap_pct:+.0f}% · Vol {vol_ratio:.0f}x · Short MAGNA {magna}/6"
    if catalyst:
        line += f"\n  {cat_emoji} {catalyst}"

    if zone_lo and zone_hi and stop:
        line += f"\n  Short: ${zone_lo}-${zone_hi} | Cover stop: ${stop:.2f}"
    if quality:
        line += f" | {quality}"

    return line


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
