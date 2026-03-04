"""
morning_brief.py
----------------
Sends a focused pre-market Telegram brief at 06:30 UK time.
Reads from the overnight (21:00) scan cache — no new scan needed.

Format:
  1. Market context — regime, VIX, breadth
  2. Top 5 long setups — best scored, with entry zones
  3. Top 3 pipeline stocks — approaching MAs, watch today
  4. Any open journal positions — where they are vs stops/targets
  5. Key levels to watch — SPY/QQQ context
"""

import os
import json
from pathlib import Path
from datetime import date, datetime
from typing import Optional
import requests


CACHE_FILE = Path(os.environ.get("DATA_DIR", ".")) / "scan_cache.json"


def _send(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[morning_brief] Telegram not configured")
        return False
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id":               chat_id,
            "text":                  text,
            "parse_mode":            "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        ok = resp.status_code == 200
        print(f"[morning_brief] {'Sent' if ok else 'Failed'} ({len(text)} chars)")
        return ok
    except Exception as e:
        print(f"[morning_brief] Exception: {e}")
        return False


def _p(v, dp=2):
    """Format price."""
    if v is None: return "—"
    return f"${float(v):.{dp}f}"


def _pct(v, dp=1):
    """Format pct with sign."""
    if v is None: return "—"
    return f"{'+' if float(v) >= 0 else ''}{float(v):.{dp}f}%"


def _earn(days: Optional[int]) -> str:
    if days is None or days < 0 or days > 21: return ""
    if days <= 2:  return f" ⚠️ EARN {days}d"
    if days <= 14: return f" 📅 earn {days}d"
    return ""


def _entry_zone(s: dict) -> str:
    """Suggest entry zone based on MA and ATR."""
    price  = s.get("price") or 0
    bounce = s.get("bouncing_from") or s.get("bouncing_from", "")
    ma_key = bounce.lower().replace("ma", "ma") if bounce else None
    ma_val = s.get(ma_key) if ma_key and ma_key in s else None
    atr    = s.get("atr")

    if ma_val and atr:
        entry_low  = round(ma_val, 2)
        entry_high = round(ma_val + 0.5 * atr, 2)
        return f"Zone: {_p(entry_low)} – {_p(entry_high)}"
    if ma_val:
        return f"Near: {_p(ma_val)}"
    return f"Current: {_p(price)}"


def _rs_bar(rs: int) -> str:
    """RS strength visual."""
    if rs >= 95: return "★★★★★"
    if rs >= 90: return "★★★★☆"
    if rs >= 80: return "★★★☆☆"
    if rs >= 70: return "★★☆☆☆"
    return "★☆☆☆☆"


def _vcs_label(vcs) -> str:
    if vcs is None: return "—"
    if vcs <= 2: return f"{vcs} 🔥🔥"
    if vcs <= 3: return f"{vcs} 🔥"
    if vcs <= 5: return f"{vcs} ✓"
    return str(vcs)


def _pipeline_proximity(s: dict) -> Optional[float]:
    """Find closest MA within 25%."""
    price = s.get("price") or 0
    if not price: return None
    best = None
    for ma_key in ["ma10", "ma21", "ma50"]:
        ma = s.get(ma_key)
        if ma and price > ma:
            pct = (price - ma) / price * 100
            if 0 < pct <= 25:
                if best is None or pct < best:
                    best = pct
    return best


def send_morning_brief():
    """Main entry point — reads cache and sends brief."""
    print(f"[morning_brief] Starting {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not CACHE_FILE.exists():
        _send("☀️ <b>Morning Brief</b>\nNo scan data yet — run a scan first.")
        return

    try:
        cache = json.loads(CACHE_FILE.read_text())
    except Exception as e:
        print(f"[morning_brief] Cache read error: {e}")
        return

    scanned_at   = cache.get("scanned_at", "unknown")
    market       = cache.get("market", {})
    long_signals = cache.get("long_signals", [])
    all_stocks   = cache.get("all_stocks", [])

    mkt_score = market.get("score", 50)
    mkt_label = market.get("label", "Neutral")
    vix       = market.get("vix")
    breadth   = (market.get("breadth") or {}).get("breadth_50ma_pct")
    regime_w  = market.get("regime_warning", "")

    mkt_emoji = "🟢" if mkt_score >= 65 else "🟡" if mkt_score >= 45 else "🔴"
    day_str   = datetime.now().strftime("%A %d %b")

    # Regime gate
    if mkt_score < 35:   gate_emoji, gate_label = "🚨", "DANGER"
    elif mkt_score < 50: gate_emoji, gate_label = "⚠️", "WARN"
    elif mkt_score < 65: gate_emoji, gate_label = "🟡", "CAUTION"
    else:                gate_emoji, gate_label = "✅", "GO"

    # ── Section 1: Header + Market Context ───────────────────────────────────
    lines = [
        f"☀️ <b>MORNING BRIEF — {day_str}</b>",
        f"Based on scan: {scanned_at}",
        "",
        f"<b>Market Regime</b>: {mkt_emoji} {mkt_label} ({mkt_score}/100) · Gate: {gate_emoji} <b>{gate_label}</b>",
    ]

    # VIX with explicit options warning
    if vix:
        vix_note = ""
        if vix > 35:   vix_note = " 🚨 PANIC — spreads only, min size"
        elif vix > 25: vix_note = " ⚠️ elevated — OTM calls expensive"
        elif vix > 20: vix_note = " — above normal"
        lines.append(f"VIX: <b>{vix:.1f}</b>{vix_note}" + (f" · Breadth: {breadth}% >50MA" if breadth else ""))
    elif breadth:
        lines.append(f"Breadth: {breadth}% above 50MA")

    # Regime action guidance
    if gate_label == "DANGER":
        lines.append("🚨 High failure rate on longs — paper trade or stand aside")
    elif gate_label == "WARN":
        lines.append("⚠️ Reduce size 50% · Prefer RS90+, sector aligned · Avoid micro caps")
    elif gate_label == "CAUTION":
        lines.append("🟡 Standard filters only · Tighten VCS/RS requirements")
    if regime_w:
        lines.append(f"  {regime_w}")

    # SPY / QQQ quick levels
    indices = market.get("indices", {})
    spy = indices.get("SPY", {})
    qqq = indices.get("QQQ", {})
    if spy:
        spy_chg = spy.get("chg_1d") or spy.get("chg", 0)
        spy_ma  = "▲21EMA" if spy.get("above_ma21") else "▼21EMA"
        lines.append(f"SPY: {_p(spy.get('close'))} ({_pct(spy_chg)}) {spy_ma}")
    if qqq:
        qqq_chg = qqq.get("chg_1d") or qqq.get("chg", 0)
        qqq_ma  = "▲21EMA" if qqq.get("above_ma21") else "▼21EMA"
        lines.append(f"QQQ: {_p(qqq.get('close'))} ({_pct(qqq_chg)}) {qqq_ma}")

    _send("\n".join(lines))

    # ── Section 2: Priority Picks (TAKE / WATCH / MONITOR) ──────────────────
    from priority_rank import get_top_picks, get_top_short_picks
    sector_rs    = cache.get("sector_rs", {})
    short_signals = cache.get("short_signals", [])
    picks        = get_top_picks(long_signals, sector_rs, max_take=2)
    short_picks  = get_top_short_picks(short_signals, sector_rs, max_take=2)
    take         = picks["take"]
    watch        = picks["watch"]
    monitor      = picks["monitor"]

    def _signal_block(s, label, emoji):
        ticker = s.get("ticker", "")
        price  = s.get("price", 0)
        bounce = s.get("bouncing_from", "?")
        rs     = int(s.get("rs", 0))
        vcs    = s.get("vcs")
        stop   = s.get("stop_price")
        t1     = s.get("target_1")
        t2     = s.get("target_2")
        sector = s.get("sector", "")
        earn   = _earn(s.get("days_to_earnings"))
        vol_r  = s.get("vol_ratio") or 0
        reason = s.get("priority_reason", "")
        score  = s.get("priority_score", 0)

        return (
            f"{emoji} <b>{label}: {ticker}</b> {_p(price)}{earn}\n"
            f"   {bounce} · RS {rs} {_rs_bar(rs)} · VCS {_vcs_label(vcs)}\n"
            f"   {_entry_zone(s)}\n"
            f"   Stop {_p(stop)} → T1 {_p(t1)} · T2 {_p(t2)}\n"
            f"   {reason}\n"
            f"   Priority score: {score}/100"
        )

    # TAKE block — act on these
    if take or watch:
        pick_lines = ["<b>🎯 TODAY\'S PICKS</b>\n"]

        for s in take:
            pick_lines.append(_signal_block(s, "TAKE", "✅"))

        for s in watch:
            pick_lines.append(_signal_block(s, "WATCH", "👀"))

        # MONITOR — just tickers, no detail
        if monitor:
            mon_tickers = ", ".join(s["ticker"] for s in monitor[:8])
            pick_lines.append(f"\n<b>📋 MONITOR ({len(monitor)})</b>: {mon_tickers}")
            pick_lines.append("Review these but don\'t act until TAKE/WATCH are filled.")

        _send("\n".join(pick_lines))
    else:
        _send("📭 No long signals today — stand aside.")

    # ── Short Priority Picks ──────────────────────────────────────────────────
    short_take  = short_picks["take"]
    short_watch = short_picks["watch"]
    short_mon   = short_picks["monitor"]

    if short_take or short_watch:
        short_lines = ["<b>🔴 SHORT PICKS</b>\n"]

        for s in short_take:
            ticker = s.get("ticker", "")
            price  = s.get("price", 0)
            stop   = s.get("stop_price")
            t1     = s.get("target_1")
            rs     = int(s.get("rs", 0))
            vcs    = s.get("vcs")
            vol_r  = s.get("vol_ratio") or 0
            reason = s.get("priority_reason", "")
            score  = s.get("priority_score", 0)
            earn   = _earn(s.get("days_to_earnings"))
            short_lines.append(
                f"🔴 <b>TAKE SHORT: {ticker}</b> {_p(price)}{earn}\n"
                f"   RS {rs} {_rs_bar(rs)} · VCS {_vcs_label(vcs)} · Vol {vol_r:.1f}×\n"
                f"   Cover {_p(t1)} · Stop {_p(stop)}\n"
                f"   {reason}\n"
                f"   Priority score: {score}/100"
            )

        for s in short_watch:
            ticker = s.get("ticker", "")
            price  = s.get("price", 0)
            rs     = int(s.get("rs", 0))
            reason = s.get("priority_reason", "")
            short_lines.append(
                f"🟠 <b>WATCH SHORT: {ticker}</b> {_p(price)} · RS {rs}\n"
                f"   {reason}"
            )

        if short_mon:
            mon_str = ", ".join(s["ticker"] for s in short_mon[:6])
            short_lines.append(f"\n📋 <b>Monitor shorts</b>: {mon_str}")

        _send("\n".join(short_lines))

    # ── Section 3: Pipeline — approaching MAs ─────────────────────────────────
    pipeline = []
    for s in all_stocks:
        rs = s.get("rs", 0) or 0
        if rs < 80: continue
        price = s.get("price") or 0
        ma10, ma21, ma50 = s.get("ma10"), s.get("ma21"), s.get("ma50")
        # Must be above all 3 MAs
        if not (ma10 and ma21 and ma50): continue
        if not (price > ma10 and price > ma21 and price > ma50): continue
        # Not already a live signal
        if s.get("ma10_touch") or s.get("ma21_touch") or s.get("ma50_touch"): continue
        prox = _pipeline_proximity(s)
        if prox and prox <= 25:
            pipeline.append({**s, "_prox": prox})

    pipeline.sort(key=lambda x: x["_prox"])
    top_pipeline = pipeline[:5]

    if top_pipeline:
        pipe_lines = [f"\n<b>👀 PIPELINE — APPROACHING MAs</b>\n"]
        for s in top_pipeline:
            ticker = s.get("ticker", "")
            price  = s.get("price", 0)
            rs     = int(s.get("rs", 0))
            prox   = s["_prox"]
            earn   = _earn(s.get("days_to_earnings"))

            # Which MA is closest
            closest_label = "MA?"
            for label, ma_key in [("MA10", "ma10"), ("MA21", "ma21"), ("MA50", "ma50")]:
                ma = s.get(ma_key)
                if ma and price > ma:
                    pct = (price - ma) / price * 100
                    if abs(pct - prox) < 0.1:
                        closest_label = label
                        break

            urgency = "🔴 imminent" if prox < 3 else "🟠 close" if prox < 7 else "🟡 watch"
            pipe_lines.append(
                f"{urgency} <b>{ticker}</b> {_p(price)}{earn}\n"
                f"   {prox:.1f}% above {closest_label} · RS {rs} {_rs_bar(rs)}"
            )

        _send("\n".join(pipe_lines))

    # ── Section 4: Open journal positions with PRE-MARKET live prices ──────
    try:
        from database import journal_list
        from premarket import premarket_position_check, format_premarket_brief, enrich_signals_premarket

        # Pre-market position check (live prices)
        pm_positions = premarket_position_check()
        pm_signals   = enrich_signals_premarket(top_longs[:5] if top_longs else [])

        if pm_positions:
            urgent = [p for p in pm_positions if p.get("urgent")]
            normal = [p for p in pm_positions if not p.get("urgent")]

            pos_lines = [f"\n<b>📋 POSITIONS — PRE-MARKET</b>"]
            if urgent:
                pos_lines.append("⚠️ ALERTS:")
                for p in urgent:
                    icon = "⛔" if p["gap_class"] == "gap_through_stop" else "⚠️"
                    pos_lines.append(
                        f"  {icon} <b>{p['ticker']}</b> ${p['pre_price']:.2f} ({p['gap_pct']:+.1f}%) — "
                        f"{p['gap_class'].replace('_',' ').upper()}"
                    )
            for p in normal:
                entry = p.get("entry_price")
                curr  = p.get("pre_price")
                pnl   = ((curr - entry) / entry * 100) if curr and entry else None
                pnl_str = f"({_pct(pnl)})" if pnl is not None else ""
                gap_icon = {"gap_up": "↑", "gap_down": "↓", "flat": "→",
                            "gap_into_entry": "🎯"}.get(p.get("gap_class",""), "·")
                pos_lines.append(
                    f"  {gap_icon} <b>{p['ticker']}</b> ${curr:.2f} {pnl_str} "
                    f"({p['gap_pct']:+.1f}% gap)"
                )

            if pm_signals:
                pos_lines.append("\n📊 Setup gaps:")
                for s in pm_signals[:3]:
                    if s.get("pre_price"):
                        gl = {"gap_into_entry":"🎯 INTO ENTRY","gap_above_entry":"↑↑ EXTENDED",
                              "flat":"→","gap_up":"↑","gap_down":"↓","gap_toward_stop":"⚠️"}.get(s.get("gap_class",""),"")
                        pos_lines.append(f"  {s['ticker']} ${s['pre_price']:.2f} ({s.get('gap_pct',0):+.1f}%) {gl}")

            _send("\n".join(pos_lines))
        else:
            # No positions — just show top signal gap check
            open_pos = journal_list(status="open") + journal_list(status="watching")
            if not open_pos:
                pass  # No positions at all, skip section
    except Exception as e:
        print(f"[morning_brief] Journal/premarket section error: {e}")

    # ── Section 5: Footer ─────────────────────────────────────────────────────
    footer_lines = [
        "",
        f"<i>Market opens in ~2.5hrs (14:30 UK)</i>",
        f"<i>Next EOD scan: 21:00 UK</i>",
    ]

    # Add shorts summary if market is negative
    if mkt_score < 45:
        short_signals = cache.get("short_signals", [])[:3]
        if short_signals:
            footer_lines.insert(0, f"▼ <b>Top shorts: {', '.join(s.get('ticker','') for s in short_signals)}</b>")

    _send("\n".join(footer_lines))
    print("[morning_brief] Done")


if __name__ == "__main__":
    send_morning_brief()
