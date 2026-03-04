"""
weekly_report.py
----------------
Sunday digest sent to Telegram.
Summarises the week's signals, performance, market regime,
and top setups to watch next week.
Auto-generated from the signal history DB.
"""

from datetime import date, timedelta
from collections import defaultdict
from database import get_conn
from alerts import _send


def get_week_signals(days_back: int = 7) -> list:
    """Fetch all signals from the past N days."""
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM signal_history
            WHERE scan_date >= ?
            ORDER BY scan_date DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def get_week_journal_closes(days_back: int = 7) -> list:
    """Fetch all journal entries closed in the past N days."""
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM journal
            WHERE status = 'closed' AND exit_date >= ?
            ORDER BY exit_date DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def get_open_journal() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM journal WHERE status IN ('watching', 'open')
            ORDER BY added_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def build_weekly_report(cache: dict = None) -> str:
    """
    Build the weekly Telegram report.
    cache: the last scan cache dict (for market conditions + top setups).
    """
    today    = date.today()
    week_ago = today - timedelta(days=7)

    signals  = get_week_signals(7)
    closes   = get_week_journal_closes(7)
    open_pos = get_open_journal()

    # ── Signal summary ─────────────────────────────────────────────────────
    by_type = defaultdict(int)
    for s in signals:
        by_type[s.get("signal_type", "?")] += 1

    total_signals = len(signals)

    # ── Closed trades performance ──────────────────────────────────────────
    wins   = [c for c in closes if (c.get("pnl_pct") or 0) > 0]
    losses = [c for c in closes if (c.get("pnl_pct") or 0) <= 0]
    avg_pnl = round(
        sum(c.get("pnl_pct", 0) for c in closes) / len(closes), 1
    ) if closes else None

    # ── Market regime from cache ──────────────────────────────────────────
    market_label = "Unknown"
    market_score = None
    breadth_pct  = None
    vix          = None
    regime_warn  = None
    top_longs    = []
    top_shorts   = []

    if cache:
        mkt = cache.get("market", {})
        market_label = mkt.get("label", "Unknown")
        market_score = mkt.get("score")
        breadth_pct  = mkt.get("breadth", {}).get("breadth_50ma_pct")
        vix          = mkt.get("vix")
        regime_warn  = mkt.get("regime_warning")
        top_longs    = (cache.get("long_signals") or [])[:3]
        top_shorts   = (cache.get("short_signals") or [])[:3]

    # ── Build message ──────────────────────────────────────────────────────
    mkt_emoji = "🟢" if market_label == "Positive" else "🟡" if market_label == "Neutral" else "🔴"
    lines = [
        f"<b>📅 WEEKLY REPORT — w/e {today.strftime('%d %b %Y')}</b>",
        "",
        f"<b>Market Regime</b>",
        f"{mkt_emoji} {market_label}" + (f" ({market_score})" if market_score else ""),
    ]

    if breadth_pct is not None:
        breadth_emoji = "📈" if breadth_pct > 60 else "➡️" if breadth_pct > 40 else "📉"
        lines.append(f"{breadth_emoji} Breadth: {breadth_pct}% stocks above 50MA")

    if vix:
        vix_emoji = "😌" if vix < 20 else "😐" if vix < 25 else "😰"
        lines.append(f"{vix_emoji} VIX: {vix:.1f}")

    if regime_warn:
        lines.append(f"⚠️ {regime_warn}")

    # Signals fired
    lines += [
        "",
        f"<b>Signals This Week</b>",
        f"Total: {total_signals}",
    ]
    for sig_type, count in sorted(by_type.items()):
        lines.append(f"  {sig_type}: {count}")

    # Closed trades
    if closes:
        lines += [
            "",
            f"<b>Closed Trades ({len(closes)})</b>",
            f"{'✅' if (avg_pnl or 0) > 0 else '❌'} Avg P&L: {'+' if (avg_pnl or 0) > 0 else ''}{avg_pnl}%",
            f"W/L: {len(wins)}/{len(losses)}",
        ]
        for c in closes[:5]:
            pnl = c.get("pnl_pct", 0)
            emoji = "✅" if pnl > 0 else "❌"
            lines.append(f"  {emoji} {c['ticker']} {'+' if pnl >= 0 else ''}{pnl:.1f}% ({c.get('exit_reason', '?')})")
    else:
        lines.append("\nNo closed trades this week")

    # Open positions
    if open_pos:
        lines += ["", f"<b>Open Positions ({len(open_pos)})</b>"]
        for p in open_pos[:5]:
            days = (today - date.fromisoformat(p.get("added_date", today.isoformat()))).days
            lines.append(f"  {p['ticker']} — {p.get('status','?')} · {days}d · entry ${p.get('entry_price', '?')}")

    # Top setups for next week
    if top_longs:
        lines += ["", "<b>Top Setups to Watch</b>"]
        for s in top_longs:
            score = s.get("signal_score", "?")
            vcs   = s.get("vcs", "?")
            rs    = s.get("rs", "?")
            lines.append(
                f"  🔍 <b>{s['ticker']}</b> ${s.get('price', '?')} "
                f"| Score {score} | VCS {vcs} | RS {rs}"
            )

    # Closing note
    lines += [
        "",
        f"<i>Next scans: Mon 21:00 · Tue 07:00 UK</i>",
        f"<i>Signal Desk · {today.strftime('%d %b %Y')}</i>",
    ]

    return "\n".join(lines)


def send_weekly_report(cache: dict = None):
    """Build and send the weekly Telegram report."""
    print("[weekly_report] Building weekly digest...")
    try:
        report = build_weekly_report(cache)
        _send(report)
        print("[weekly_report] Sent")
    except Exception as e:
        print(f"[weekly_report] Failed: {e}")
