"""
position_monitor.py
-------------------
Intraday position monitor — runs every 15 minutes during market hours.
Fetches live prices for all open journal positions via yfinance (free, no key).
Fires immediate Telegram alerts when:
  - Stop hit → URGENT, sends stop message
  - Target 1/2/3 hit → sends level message
  - Price approaching stop (within 1.5%) → early warning
  - Position up >15% with no stop raised → trailing stop reminder
  - Stuck position: open >10 days, flat (< ±2%) → time exit nudge

State file: /tmp/position_alerts_sent.json
Tracks which alerts have already been sent per position per day
so we don't spam the same alert every 15 minutes.
"""

import os
import json
import yfinance as yf
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Optional
from database import journal_list, journal_update
from alerts import _send

STATE_FILE = "/tmp/position_alerts_sent.json"


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        # Reset if stale (different day)
        if state.get("date") != date.today().isoformat():
            return {"date": date.today().isoformat(), "sent": {}}
        return state
    except Exception:
        return {"date": date.today().isoformat(), "sent": {}}


def _save_state(state: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def _already_sent(state: dict, position_id: int, alert_key: str) -> bool:
    return alert_key in state.get("sent", {}).get(str(position_id), [])


def _mark_sent(state: dict, position_id: int, alert_key: str):
    sent = state.setdefault("sent", {})
    alerts = sent.setdefault(str(position_id), [])
    if alert_key not in alerts:
        alerts.append(alert_key)


def _fetch_live_prices(tickers: list) -> dict:
    """
    Fetch latest EOD prices for open positions.
    Routes to Polygon when POLYGON_API_KEY is set (fast, reliable).
    Falls back to yfinance (scraper) if key not present.
    """
    import os
    prices: dict = {}
    if not tickers:
        return prices

    # ── Polygon path ──────────────────────────────────────────────────────────
    if os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_bars
            bars = fetch_bars(tickers, days=5, interval="day",
                              min_rows=1, max_workers=10,
                              label="position_monitor")
            for t, df in bars.items():
                if df is not None and not df.empty:
                    prices[t] = round(float(df["close"].iloc[-1]), 2)
            print(f"[position_monitor] Polygon prices: {len(prices)}/{len(tickers)}")
            if len(prices) >= len(tickers) * 0.8:   # 80%+ hit rate → trust it
                return prices
            # else fall through to yfinance for the rest
        except Exception as e:
            print(f"[position_monitor] Polygon price fetch failed ({e}) — trying yfinance")

    # ── yfinance fallback ─────────────────────────────────────────────────────
    import warnings
    missing = [t for t in tickers if t not in prices]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = yf.download(
                tickers=missing,
                period="2d",
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
                multi_level_index=True,
            )
        if data is not None and not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                try:
                    close_df = data.xs("Close", axis=1, level=0)
                except KeyError:
                    close_df = data.xs("close", axis=1, level=0)
                for t in missing:
                    if t in close_df.columns:
                        s = close_df[t].dropna()
                        if not s.empty:
                            prices[t] = round(float(s.iloc[-1]), 2)
            else:
                col = next((c for c in data.columns if str(c).lower() == "close"), None)
                if col and missing:
                    prices[missing[0]] = round(float(data[col].dropna().iloc[-1]), 2)
    except Exception as e:
        print(f"[position_monitor] yfinance batch failed ({e}) — per-ticker fallback")
        for t in missing:
            try:
                info = yf.Ticker(t).fast_info
                px = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
                if px:
                    prices[t] = round(float(px), 2)
            except Exception:
                pass

    print(f"[position_monitor] Prices fetched: {len(prices)}/{len(tickers)} tickers")
    return prices


def _pnl(current: float, entry: float) -> float:
    if not entry or entry == 0:
        return 0.0
    return round((current - entry) / entry * 100, 2)


def _days_held(added_date: str) -> int:
    try:
        return (date.today() - date.fromisoformat(added_date)).days
    except Exception:
        return 0


def _fmt_pnl(pnl: float) -> str:
    return f"+{pnl:.1f}%" if pnl >= 0 else f"{pnl:.1f}%"


def check_positions(dry_run: bool = False) -> dict:
    """
    Main monitor function. Fetches live prices, evaluates all positions,
    sends alerts for new events. Returns summary dict.
    """
    # Only open positions (not watching — no entry price confirmed)
    positions = journal_list(status="open")
    if not positions:
        print("[position_monitor] No open positions")
        return {"checked": 0, "alerts_sent": 0}

    tickers = [p["ticker"] for p in positions]
    prices  = _fetch_live_prices(tickers)
    state   = _load_state()

    alerts_sent   = 0
    urgent_alerts = []   # Stop hits — send first
    level_alerts  = []   # Target hits
    warn_alerts   = []   # Warnings (approaching stop, trailing)
    summary_lines = []   # For digest

    for pos in positions:
        pid        = pos["id"]
        ticker     = pos["ticker"]
        entry_px   = pos.get("entry_price")
        stop_px    = pos.get("stop_price")
        t1_px      = pos.get("target_1")
        t2_px      = pos.get("target_2")
        t3_px      = pos.get("target_3")
        added      = pos.get("added_date", date.today().isoformat())
        signal_t   = pos.get("signal_type", "")
        notes      = pos.get("notes", "")

        current_px = prices.get(ticker)
        if current_px is None or entry_px is None:
            summary_lines.append(f"  {ticker} — ⚠️ no price")
            continue

        pnl      = _pnl(current_px, entry_px)
        days     = _days_held(added)
        pnl_str  = _fmt_pnl(pnl)
        px_str   = f"${current_px:.2f}"

        # ── STOP HIT ────────────────────────────────────────────────────
        if stop_px and current_px <= stop_px:
            key = "stop_hit"
            if not _already_sent(state, pid, key):
                urgent_alerts.append(
                    f"⛔ <b>STOP HIT — {ticker}</b>\n"
                    f"Price: {px_str} ≤ Stop: ${stop_px:.2f}\n"
                    f"P&L: {pnl_str} | {days}d held | {signal_t}\n"
                    f"<b>Consider closing now.</b>"
                )
                _mark_sent(state, pid, key)
                # Auto-update status in DB
                if not dry_run:
                    journal_update(pid, {
                        "status":      "stopped",
                        "exit_price":  current_px,
                        "exit_date":   date.today().isoformat(),
                        "exit_reason": "stop_hit_intraday",
                        "pnl_pct":     pnl,
                    })
                alerts_sent += 1
            summary_lines.append(f"  {ticker} ⛔ {px_str} ({pnl_str}) — STOPPED")
            continue

        # ── APPROACHING STOP (within 1.5%) ──────────────────────────────
        if stop_px and current_px > stop_px:
            dist_to_stop = (current_px - stop_px) / current_px * 100
            if dist_to_stop <= 1.5:
                key = f"near_stop_{round(dist_to_stop, 0)}"
                if not _already_sent(state, pid, key):
                    warn_alerts.append(
                        f"⚠️ <b>{ticker} approaching stop</b>\n"
                        f"Price: {px_str} | Stop: ${stop_px:.2f} ({dist_to_stop:.1f}% away)\n"
                        f"P&L: {pnl_str} | {days}d held"
                    )
                    _mark_sent(state, pid, key)
                    alerts_sent += 1

        # ── TARGET 3 ────────────────────────────────────────────────────
        if t3_px and current_px >= t3_px:
            key = "t3_hit"
            if not _already_sent(state, pid, key):
                level_alerts.append(
                    f"🎯 <b>TARGET 3 — {ticker}</b>\n"
                    f"Price: {px_str} ≥ T3: ${t3_px:.2f}\n"
                    f"P&L: {pnl_str} | {days}d held\n"
                    f"Consider full exit or very tight trailing stop."
                )
                _mark_sent(state, pid, key)
                alerts_sent += 1
            summary_lines.append(f"  {ticker} 🎯 {px_str} ({pnl_str}) — T3 HIT")
            continue

        # ── TARGET 2 ────────────────────────────────────────────────────
        elif t2_px and current_px >= t2_px:
            key = "t2_hit"
            if not _already_sent(state, pid, key):
                level_alerts.append(
                    f"✅ <b>Target 2 — {ticker}</b>\n"
                    f"Price: {px_str} ≥ T2: ${t2_px:.2f}\n"
                    f"P&L: {pnl_str} | {days}d held\n"
                    f"Consider partial exit. Raise stop to T1 (${t1_px:.2f})." if t1_px else ""
                )
                _mark_sent(state, pid, key)
                alerts_sent += 1
            summary_lines.append(f"  {ticker} ✅ {px_str} ({pnl_str}) — T2 hit")
            continue

        # ── TARGET 1 ────────────────────────────────────────────────────
        elif t1_px and current_px >= t1_px:
            key = "t1_hit"
            if not _already_sent(state, pid, key):
                level_alerts.append(
                    f"✅ <b>Target 1 — {ticker}</b>\n"
                    f"Price: {px_str} ≥ T1: ${t1_px:.2f}\n"
                    f"P&L: {pnl_str} | {days}d held\n"
                    f"Raise stop to breakeven (${entry_px:.2f})."
                )
                _mark_sent(state, pid, key)
                alerts_sent += 1
            summary_lines.append(f"  {ticker} ✅ {px_str} ({pnl_str}) — T1 hit")
            continue

        # ── PHASE-AWARE TRAILING STOP CHECK ─────────────────────────────
        t1_hit = bool(t1_px and current_px >= t1_px)
        t2_hit = bool(t2_px and current_px >= t2_px)
        t3_hit = bool(t3_px and current_px >= t3_px)

        if t3_hit:
            phase_label  = "trail_ema10"
            phase_action = "Sell final 1/3 · Trail stop below EMA10"
        elif t2_hit:
            phase_label  = "trail_ema21"
            phase_action = "Sell 1/3 · Trail stop below EMA21"
        elif t1_hit:
            phase_label  = "breakeven"
            phase_action = "Sell 1/3 · Raise stop to breakeven"
        else:
            phase_label  = "fixed"
            phase_action = None

        if phase_action:
            phase_key = f"phase_{phase_label}"
            if not _already_sent(state, pid, phase_key):
                level_alerts.append(
                    f"📊 <b>{ticker} — {phase_label.upper()}</b>\n"
                    f"Price: {px_str} | {pnl_str} | {days}d\n"
                    f"Action: {phase_action}"
                )
                _mark_sent(state, pid, phase_key)
                alerts_sent += 1

        # Alert if big winner but stop still near entry (T1 not yet hit)
        if pnl >= 15 and stop_px and stop_px < entry_px * 1.02 and not t1_hit:
            key = "trail_remind"
            if not _already_sent(state, pid, key):
                warn_alerts.append(
                    f"📈 <b>{ticker} +{pnl:.1f}% — stop still near entry</b>\n"
                    f"Price: {px_str} | Stop: ${stop_px:.2f}\n"
                    f"T1 not triggered — consider raising stop manually."
                )
                _mark_sent(state, pid, key)
                alerts_sent += 1

        # ── STUCK POSITION ───────────────────────────────────────────────
        if days >= 10 and abs(pnl) < 2:
            key = f"stuck_{days // 5}"
            if not _already_sent(state, pid, key):
                warn_alerts.append(
                    f"⏰ <b>{ticker} stuck — {days} days, {pnl_str}</b>\n"
                    f"Price: {px_str} | Entry: ${entry_px:.2f}\n"
                    f"Capital tied up. Consider time-based exit."
                )
                _mark_sent(state, pid, key)
                alerts_sent += 1

        # Normal summary line
        phase_icon = {"trail_ema10": "🎯", "trail_ema21": "✅✅", "breakeven": "✅", "fixed": ""}.get(phase_label, "")
        summary_lines.append(f"  {ticker} {px_str} ({pnl_str}) {phase_icon} | {days}d")

    # ── Send alerts ──────────────────────────────────────────────────────
    # Urgent first (stop hits)
    for msg in urgent_alerts:
        if not dry_run:
            _send(msg)

    # Level alerts (targets)
    for msg in level_alerts:
        if not dry_run:
            _send(msg)

    # Warnings batched into one message
    if warn_alerts:
        combined = "⚠️ <b>Position Warnings</b>\n\n" + "\n\n".join(warn_alerts)
        if not dry_run:
            _send(combined)

    _save_state(state)

    print(f"[position_monitor] Checked {len(positions)} positions, sent {alerts_sent} alerts")
    return {
        "checked":      len(positions),
        "alerts_sent":  alerts_sent,
        "prices":       prices,
        "summary":      summary_lines,
        "urgent":       len(urgent_alerts),
        "levels":       len(level_alerts),
        "warnings":     len(warn_alerts),
    }


def send_position_digest():
    """
    Send a full digest of all open positions with current prices.
    Called manually or at market close. Different from check_positions —
    always sends even if no new alerts.
    """
    positions = journal_list(status="open")
    if not positions:
        _send("📋 <b>Position Digest</b>\nNo open positions.")
        return

    tickers = [p["ticker"] for p in positions]
    prices  = _fetch_live_prices(tickers)

    winners = []
    losers  = []
    flat    = []

    for pos in positions:
        ticker   = pos["ticker"]
        entry_px = pos.get("entry_price")
        stop_px  = pos.get("stop_price")
        t1_px    = pos.get("target_1")
        t2_px    = pos.get("target_2")
        t3_px    = pos.get("target_3")
        added    = pos.get("added_date", date.today().isoformat())
        current  = prices.get(ticker)

        if current is None or entry_px is None:
            flat.append(f"  {ticker} — no price")
            continue

        pnl  = _pnl(current, entry_px)
        days = _days_held(added)

        # Distance to key levels
        dist_stop = f"  stop ${stop_px:.2f} ({((current-stop_px)/current*100):.1f}% away)" if stop_px else ""
        next_t = ""
        if t3_px and current >= t3_px:     next_t = f"  🎯 AT T3 ${t3_px:.2f}"
        elif t2_px and current >= t2_px:   next_t = f"  ✅ AT T2 → T3 ${t3_px:.2f}" if t3_px else f"  ✅ AT T2"
        elif t1_px and current >= t1_px:   next_t = f"  ✅ AT T1 → T2 ${t2_px:.2f}" if t2_px else f"  ✅ AT T1"
        elif t1_px:                        next_t = f"  → T1 ${t1_px:.2f} ({((t1_px-current)/current*100):.1f}% away)"

        line = f"<b>{ticker}</b> ${current:.2f} | {_fmt_pnl(pnl)} | {days}d\n{dist_stop}{next_t}"

        if pnl > 2:      winners.append(line)
        elif pnl < -2:   losers.append(line)
        else:            flat.append(line)

    lines = [f"<b>📋 Position Digest — {datetime.now().strftime('%H:%M')} ET</b>",
             f"{len(positions)} open positions\n"]

    if winners:
        lines.append("🟢 <b>Winners</b>")
        lines.extend(winners)
    if flat:
        lines.append("\n⚪ <b>Flat</b>")
        lines.extend(flat)
    if losers:
        lines.append("\n🔴 <b>Losers</b>")
        lines.extend(losers)

    total_pnl = []
    for pos in positions:
        entry = pos.get("entry_price")
        curr  = prices.get(pos["ticker"])
        if entry and curr:
            total_pnl.append(_pnl(curr, entry))
    if total_pnl:
        avg = round(sum(total_pnl) / len(total_pnl), 1)
        lines.append(f"\n<b>Avg P&L across positions: {_fmt_pnl(avg)}</b>")

    _send("\n".join(lines))


# ── Skip outcome tracker ───────────────────────────────────────────────────────
#
# Runs automatically on every position monitor cycle (every 15 min during
# market hours) and at end of day (21:30 UK / 16:30 ET).
#
# For each skipped entry within the 20-trading-day window:
#   1. Fetch daily bars from skip_date to today
#   2. Calculate peak price (best case if taken)
#   3. Check if T1 was hit within the window
#   4. Store outcome_if_taken = peak % gain (or loss if stock went straight down)
#   5. After 20 trading days: freeze the outcome (stop updating)
#
# outcome_if_taken is always the best case within the window — what the
# options trade would have made if you closed at the peak before expiry.
# This gives the most informative comparison: did your skip cost you,
# or would the trade have failed anyway?

SKIP_WINDOW_DAYS = 28   # calendar days ≈ 20 trading days


def _trading_days_since(skip_date_str: str) -> int:
    """Approximate trading days elapsed since skip date (excludes weekends)."""
    try:
        start = date.fromisoformat(skip_date_str)
        end   = date.today()
        days  = 0
        cur   = start
        while cur < end:
            cur += timedelta(days=1)
            if cur.weekday() < 5:  # Mon-Fri
                days += 1
        return days
    except Exception:
        return 0


def _fetch_daily_bars(ticker: str, from_date: str) -> list:
    """
    Fetch daily close prices from from_date to today.
    Returns list of (date_str, close_price) tuples, chronological.
    Routes to Polygon when POLYGON_API_KEY is set; falls back to yfinance.
    """
    import os
    try:
        start = date.fromisoformat(from_date)
        days  = (date.today() - start).days + 5  # small buffer

        # ── Polygon path ──────────────────────────────────────────────────────
        if os.environ.get("POLYGON_API_KEY"):
            try:
                from polygon_client import _fetch_one
                _, df = _fetch_one(
                    ticker,
                    (start - timedelta(days=2)).isoformat(),
                    (date.today() + timedelta(days=1)).isoformat(),
                    interval="day",
                    min_rows=1,
                )
                if df is not None and not df.empty:
                    return [
                        (str(idx.date()), round(float(row["close"]), 2))
                        for idx, row in df.iterrows()
                        if str(idx.date()) >= from_date
                    ]
            except Exception as e:
                print(f"[skip_tracker] Polygon bar fetch failed for {ticker}: {e}")

        # ── yfinance fallback ─────────────────────────────────────────────────
        start_str = (start - timedelta(days=1)).isoformat()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(
                tickers=ticker,
                start=start_str,
                end=(date.today() + timedelta(days=1)).isoformat(),
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
                multi_level_index=True,
            )
        if df.empty:
            return []
        if isinstance(df.columns, pd.MultiIndex):
            try:
                closes = df.xs("Close", axis=1, level=0).iloc[:, 0].dropna()
            except Exception:
                closes = df.xs("close", axis=1, level=0).iloc[:, 0].dropna()
        else:
            col = next((c for c in df.columns if str(c).lower() == "close"), None)
            if col is None:
                return []
            closes = df[col].dropna()
        return [(str(idx.date()), round(float(val), 2)) for idx, val in closes.items()
                if str(idx.date()) >= from_date]

    except Exception as e:
        print(f"[skip_tracker] Bar fetch error for {ticker}: {e}")
        return []


def _calculate_skip_outcome(entry: dict, bars: list) -> dict:
    """
    Given daily bars since skip date, calculate:
    - peak_pct: best possible % gain if exited at peak
    - outcome_pct: % gain at end of window (or today if window still open)
    - t1_hit: whether T1 was reached within the window
    - t1_hit_day: which trading day T1 was hit (1-indexed)
    - current_pct: % change from entry to latest price
    - frozen: True if window has closed (>20 trading days)
    """
    entry_px = entry.get("entry_price")
    t1_px    = entry.get("target_1")

    if not entry_px or entry_px <= 0 or not bars:
        return {}

    prices    = [p for _, p in bars]
    peak_px   = max(prices)
    trough_px = min(prices)
    latest_px = prices[-1]

    peak_pct   = round((peak_px   - entry_px) / entry_px * 100, 2)
    trough_pct = round((trough_px - entry_px) / entry_px * 100, 2)
    latest_pct = round((latest_px - entry_px) / entry_px * 100, 2)

    # T1 hit tracking
    t1_hit     = False
    t1_hit_day = None
    if t1_px:
        for i, (d_str, px) in enumerate(bars):
            if px >= t1_px:
                t1_hit     = True
                t1_hit_day = i + 1
                break

    # outcome_if_taken: peak gain if T1 was hit (most relevant for options),
    # otherwise the gain at end of window
    if t1_hit:
        # Find the close price on T1 hit day and use that as the options close
        t1_day_px = bars[t1_hit_day - 1][1]
        outcome = round((t1_day_px - entry_px) / entry_px * 100, 2)
    else:
        # No T1 — use peak if positive (best the option could have done),
        # otherwise end-of-window (loss scenario)
        outcome = peak_pct if peak_pct > 0 else latest_pct

    trading_days = _trading_days_since(entry.get("added_date", date.today().isoformat()))
    frozen = trading_days >= 20

    return {
        "outcome_if_taken": outcome,
        "peak_pct":         peak_pct,
        "trough_pct":       trough_pct,
        "latest_pct":       latest_pct,
        "t1_hit":           t1_hit,
        "t1_hit_day":       t1_hit_day,
        "trading_days":     trading_days,
        "frozen":           frozen,
        "bars_used":        len(bars),
        "latest_price":     latest_px,
    }


def update_skip_outcomes(dry_run: bool = False) -> dict:
    """
    Sweep all skipped journal entries within the 20-trading-day window.
    Fetch daily bars, calculate outcome_if_taken, update the DB.
    Skips entries where outcome is already frozen (>20 trading days old).
    Called automatically by check_positions() and by the EOD sweep job.
    """
    from database import get_conn

    # Load all skipped entries
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, ticker, added_date, entry_price, target_1, target_2,
                   skip_reason, suggestion_score, outcome_if_taken
            FROM journal
            WHERE status = 'skipped'
              AND entry_price IS NOT NULL
              AND added_date IS NOT NULL
            ORDER BY added_date DESC
        """).fetchall()
    entries = [dict(r) for r in rows]

    if not entries:
        print("[skip_tracker] No skipped entries to update")
        return {"checked": 0, "updated": 0, "frozen": 0, "errors": 0}

    checked = updated = frozen_count = errors = 0

    for entry in entries:
        skip_date = entry["added_date"]
        ticker    = entry["ticker"]

        # Skip entries older than window
        try:
            skip_dt = date.fromisoformat(skip_date)
            age_days = (date.today() - skip_dt).days
        except Exception:
            age_days = 999

        if age_days > SKIP_WINDOW_DAYS + 3:  # 3-day grace period
            frozen_count += 1
            continue

        checked += 1
        try:
            bars    = _fetch_daily_bars(ticker, skip_date)
            outcome = _calculate_skip_outcome(entry, bars)

            if not outcome:
                errors += 1
                continue

            if not dry_run:
                # Store outcome plus metadata in notes-adjacent field
                # outcome_if_taken = the key metric for edge report
                # We also store detail in skip_note if it was blank
                update_data = {
                    "outcome_if_taken": outcome["outcome_if_taken"],
                }

                # Enrich skip_note with auto-generated outcome detail
                # (only if not frozen — keep updating until frozen)
                detail = (
                    f"Auto: {outcome['trading_days']}d · "
                    f"Peak {'+' if outcome['peak_pct'] >= 0 else ''}{outcome['peak_pct']}% · "
                    f"{'T1 hit day ' + str(outcome['t1_hit_day']) if outcome['t1_hit'] else 'T1 not hit'} · "
                    f"Latest {'+' if outcome['latest_pct'] >= 0 else ''}{outcome['latest_pct']}%"
                    + (" [FROZEN]" if outcome["frozen"] else "")
                )

                # Fetch current skip_note to preserve manual content
                with get_conn() as conn:
                    row = conn.execute(
                        "SELECT skip_note FROM journal WHERE id = ?", (entry["id"],)
                    ).fetchone()
                    existing_note = (row["skip_note"] or "") if row else ""

                # Replace auto-generated portion but preserve manual note
                if "Auto:" in existing_note:
                    # Remove old auto-line
                    manual_part = "\n".join(
                        l for l in existing_note.split("\n") if not l.startswith("Auto:")
                    ).strip()
                else:
                    manual_part = existing_note.strip()

                update_data["skip_note"] = (manual_part + "\n" + detail).strip()

                with get_conn() as conn:
                    set_clause = ", ".join(f"{k} = ?" for k in update_data)
                    conn.execute(
                        f"UPDATE journal SET {set_clause} WHERE id = ?",
                        list(update_data.values()) + [entry["id"]]
                    )

            updated += 1
            print(
                f"[skip_tracker] {ticker}: outcome={outcome['outcome_if_taken']:+.1f}% "
                f"(peak {outcome['peak_pct']:+.1f}%, T1={'yes d'+str(outcome['t1_hit_day']) if outcome['t1_hit'] else 'no'}, "
                f"day {outcome['trading_days']}/{20}{'*' if outcome['frozen'] else ''})"
            )

        except Exception as e:
            print(f"[skip_tracker] Error processing {ticker}: {e}")
            errors += 1

    print(
        f"[skip_tracker] Done — checked {checked}, updated {updated}, "
        f"frozen {frozen_count}, errors {errors}"
    )
    return {
        "checked": checked,
        "updated": updated,
        "frozen":  frozen_count,
        "errors":  errors,
    }
