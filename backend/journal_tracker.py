"""
journal_tracker.py
------------------
Nightly job that checks all open/watching journal entries,
manages trailing stops, and reports what happened since entry.

Exit management phases:
  Phase 0  Pre-T1   : Fixed stop at entry stop_price
  Phase 1  T1 hit   : Stop raised to breakeven; sell 1/3
  Phase 2  T2 hit   : Stop trails EMA21; sell another 1/3
  Phase 3  T3 hit   : Stop trails EMA10; consider full exit

Trailing stop rule (ratchet — never moves down):
  Phase 0: fixed stop
  Phase 1: max(current_stop, breakeven)
  Phase 2: max(current_stop, EMA21)
  Phase 3: max(current_stop, EMA10)
"""

from datetime import date, timedelta
from typing import Optional
from database import get_conn, journal_update, journal_list
from alerts import _send


# ── Phase constants ───────────────────────────────────────────────────────────
PHASE_FIXED   = 0   # pre-T1: stop stays at original stop_price
PHASE_BE      = 1   # T1 hit: stop at breakeven
PHASE_EMA21   = 2   # T2 hit: trail EMA21
PHASE_EMA10   = 3   # T3 hit: trail EMA10 (very tight)

PHASE_LABELS = {
    PHASE_FIXED: "fixed",
    PHASE_BE:    "breakeven",
    PHASE_EMA21: "trail_ema21",
    PHASE_EMA10: "trail_ema10",
}

PHASE_DESCRIPTIONS = {
    PHASE_FIXED: "Hold full position. Fixed stop at entry level.",
    PHASE_BE:    "T1 hit — sell 1/3, raise stop to breakeven.",
    PHASE_EMA21: "T2 hit — sell 1/3, trail stop below EMA21.",
    PHASE_EMA10: "T3 hit — sell final 1/3, trail stop below EMA10.",
}


def _ema(closes, span: int) -> Optional[float]:
    """Return latest EMA value for given span."""
    if closes is None or len(closes) < span // 2:
        return None
    return round(float(closes.ewm(span=span, adjust=False).mean().iloc[-1]), 4)


def _determine_phase(entry: dict, current_px: float) -> int:
    """
    Work out which exit phase this position is in based on
    which targets have been breached (ever, not just now).
    """
    t3 = entry.get("target_3")
    t2 = entry.get("target_2")
    t1 = entry.get("target_1")
    if t3 and current_px >= t3:   return PHASE_EMA10
    if t2 and current_px >= t2:   return PHASE_EMA21
    if t1 and current_px >= t1:   return PHASE_BE
    return PHASE_FIXED


def calculate_trailing_stop(entry: dict, bars_data: dict) -> dict:
    """
    Calculate the current trailing stop for an open position.

    Returns dict with:
      trailing_stop : float — the recommended stop price
      phase         : int   — exit phase (0-3)
      phase_label   : str
      phase_desc    : str   — human readable action
      stop_raised   : bool  — True if trailing > current DB stop
      ema10         : float | None
      ema21         : float | None
    """
    ticker       = entry["ticker"]
    entry_px     = entry.get("entry_price")
    current_stop = entry.get("stop_price")

    if entry_px is None or ticker not in bars_data:
        return {
            "trailing_stop": current_stop,
            "phase":         PHASE_FIXED,
            "phase_label":   "fixed",
            "phase_desc":    PHASE_DESCRIPTIONS[PHASE_FIXED],
            "stop_raised":   False,
            "ema10":         None,
            "ema21":         None,
        }

    df     = bars_data[ticker]
    closes = df["close"] if hasattr(df, "columns") and "close" in df.columns else df
    closes = closes.dropna()

    ema10_val  = _ema(closes, 10)
    ema21_val  = _ema(closes, 21)
    current_px = float(closes.iloc[-1]) if not closes.empty else None

    if current_px is None:
        return {
            "trailing_stop": current_stop,
            "phase":         PHASE_FIXED,
            "phase_label":   "fixed",
            "phase_desc":    PHASE_DESCRIPTIONS[PHASE_FIXED],
            "stop_raised":   False,
            "ema10":         ema10_val,
            "ema21":         ema21_val,
        }

    phase = _determine_phase(entry, current_px)

    if phase == PHASE_FIXED:
        trailing = current_stop
    elif phase == PHASE_BE:
        trailing = entry_px
    elif phase == PHASE_EMA21:
        trailing = ema21_val if ema21_val else entry_px
    else:  # PHASE_EMA10
        trailing = ema10_val if ema10_val else ema21_val

    # Ratchet: trailing stop never moves down
    if trailing and current_stop and trailing < current_stop:
        trailing = current_stop

    # Safety: stop must be below current price
    if trailing and current_px and trailing >= current_px:
        trailing = current_stop

    stop_raised = bool(
        trailing and current_stop and
        round(float(trailing), 2) > round(float(current_stop), 2)
    )

    return {
        "trailing_stop": round(float(trailing), 4) if trailing else current_stop,
        "phase":         phase,
        "phase_label":   PHASE_LABELS[phase],
        "phase_desc":    PHASE_DESCRIPTIONS[phase],
        "stop_raised":   stop_raised,
        "ema10":         ema10_val,
        "ema21":         ema21_val,
    }


def update_trailing_stops(bars_data: dict, dry_run: bool = False) -> list:
    """
    Sweep all open positions and ratchet trailing stops.
    Returns list of update dicts (only positions where stop was raised).
    """
    positions = journal_list(status="open")
    updates   = []

    for entry in positions:
        trail = calculate_trailing_stop(entry, bars_data)
        if not trail["stop_raised"]:
            continue

        old_stop = entry.get("stop_price")
        new_stop = trail["trailing_stop"]
        phase    = trail["phase_label"]

        updates.append({
            "ticker":   entry["ticker"],
            "old_stop": old_stop,
            "new_stop": new_stop,
            "phase":    phase,
            "ema21":    trail["ema21"],
            "ema10":    trail["ema10"],
            "entry":    entry,
        })

        if not dry_run:
            try:
                journal_update(entry["id"], {"stop_price": new_stop})
                print(f"[trail_stop] {entry['ticker']} stop "
                      f"${old_stop} → ${new_stop} ({phase})")
            except Exception as e:
                print(f"[trail_stop] Update failed for {entry['ticker']}: {e}")

    return updates


def check_open_positions(bars_data: dict) -> list:
    """
    For each watching/open journal entry, check price vs levels.
    Includes phase-aware exit recommendations.
    """
    entries = journal_list(status="watching") + journal_list(status="open")
    if not entries:
        return []

    updates = []
    today   = date.today().isoformat()

    for entry in entries:
        ticker     = entry["ticker"]
        entry_px   = entry.get("entry_price")
        stop_px    = entry.get("stop_price")
        t1_px      = entry.get("target_1")
        t2_px      = entry.get("target_2")
        t3_px      = entry.get("target_3")
        added_date = entry.get("added_date", today)

        try:
            days_held = (date.today() - date.fromisoformat(added_date)).days
        except Exception:
            days_held = 0

        current_px = None
        if ticker in bars_data:
            df     = bars_data[ticker]
            closes = df["close"] if hasattr(df, "columns") and "close" in df.columns else df
            closes = closes.dropna()
            if not closes.empty:
                current_px = round(float(closes.iloc[-1]), 2)

        if current_px is None or entry_px is None:
            updates.append({
                "entry": entry, "current_px": None, "pnl_pct": None,
                "days_held": days_held, "action": "no_data",
                "message": f"{ticker} — no price data available",
                "flags": [], "phase": PHASE_FIXED, "phase_label": "fixed",
            })
            continue

        pnl_pct = round((current_px - entry_px) / entry_px * 100, 2)

        # £ P&L — use position_size_gbp if stored, else fall back to None
        _pos_size_gbp = entry.get("position_size_gbp")
        pnl_gbp = round(_pos_size_gbp * pnl_pct / 100, 2) if _pos_size_gbp else None

        # R multiple — stop distance = 1R
        _atr     = entry.get("atr")
        _stop    = entry.get("stop_price")
        _risk_r  = abs(entry_px - _stop) if _stop else (_atr * 1.5 if _atr else None)
        pnl_r    = round(pnl_pct / (_risk_r / entry_px * 100), 2) if _risk_r and entry_px else None

        trail       = calculate_trailing_stop(entry, bars_data)
        phase       = trail["phase"]
        phase_label = trail["phase_label"]
        trail_stop  = trail["trailing_stop"]
        phase_desc  = trail["phase_desc"]

        action = "hold"
        flags  = []

        if stop_px and current_px <= stop_px:
            action = "stop_hit"
            flags.append(f"⛔ STOP HIT (${stop_px:.2f})")
        elif trail_stop and trail_stop != stop_px and current_px <= trail_stop:
            action = "trail_stop_hit"
            flags.append(f"⛔ TRAILING STOP HIT (${trail_stop:.2f} / {phase_label})")
        elif t3_px and current_px >= t3_px:
            action = "t3_hit"
            flags.append(f"🎯 T3 HIT (${t3_px:.2f}) — {PHASE_DESCRIPTIONS[PHASE_EMA10]}")
        elif t2_px and current_px >= t2_px:
            action = "t2_hit"
            flags.append(f"✅ T2 HIT (${t2_px:.2f}) — {PHASE_DESCRIPTIONS[PHASE_EMA21]}")
        elif t1_px and current_px >= t1_px:
            action = "t1_hit"
            flags.append(f"✅ T1 HIT (${t1_px:.2f}) — {PHASE_DESCRIPTIONS[PHASE_BE]}")
        elif days_held >= 10 and abs(pnl_pct) < 2:
            action = "stuck"
            flags.append(f"⏰ {days_held}d flat ({pnl_pct:+.1f}%) — review thesis")
        elif days_held >= 7 and pnl_pct < -3:
            action = "losing_old"
            flags.append(f"⚠️ {days_held}d · {pnl_pct:+.1f}% — thesis review needed")

        if trail["stop_raised"]:
            flags.append(f"📈 Stop ratcheted → ${trail_stop:.2f} ({phase_label})")

        # Add current phase guidance when holding
        if action == "hold" and phase > PHASE_FIXED:
            flags.append(f"↳ {phase_desc}")

        message = (
            f"{ticker} ${current_px:.2f} | {pnl_pct:+.1f}% | "
            f"{days_held}d | {phase_label}"
        )
        if flags:
            message += " | " + " · ".join(flags)

        updates.append({
            "entry":       entry,
            "current_px":  current_px,
            "pnl_pct":     pnl_pct,
            "pnl_gbp":     pnl_gbp,
            "pnl_r":       pnl_r,
            "days_held":   days_held,
            "action":      action,
            "message":     message,
            "flags":       flags,
            "phase":       phase,
            "phase_label": phase_label,
            "phase_desc":  phase_desc,
            "trail_stop":  trail_stop,
            "ema21":       trail["ema21"],
            "ema10":       trail["ema10"],
        })

    return updates


def auto_close_stops(updates: list, dry_run: bool = False) -> int:
    closed = 0
    for u in updates:
        if u["action"] in ("stop_hit", "trail_stop_hit"):
            entry = u["entry"]
            try:
                # Calculate £ PnL from position size
                pnl_gbp = None
                position_size_gbp = None
                pos_json = entry.get("position_json")
                if pos_json:
                    try:
                        import json as _json
                        pos = _json.loads(pos_json) if isinstance(pos_json, str) else pos_json
                        position_size_gbp = pos.get("position_size_gbp") or pos.get("position_value")
                        if position_size_gbp and u.get("pnl_pct") is not None:
                            pnl_gbp = round(position_size_gbp * u["pnl_pct"] / 100, 2)
                    except Exception:
                        pass

                if not dry_run:
                    update_fields = {
                        "status":      "closed",
                        "exit_price":  u["current_px"],
                        "exit_date":   date.today().isoformat(),
                        "exit_reason": u["action"],
                        "pnl_pct":     u["pnl_pct"],
                    }
                    if pnl_gbp is not None:
                        update_fields["pnl_gbp"] = pnl_gbp
                    if position_size_gbp is not None:
                        update_fields["position_size_gbp"] = position_size_gbp
                    journal_update(entry["id"], update_fields)
                closed += 1
            except Exception as e:
                print(f"[journal_tracker] Auto-close failed for {entry['ticker']}: {e}")
    return closed


def send_position_digest(updates: list, trailing_updates: list = None,
                         market_label: str = "", regime_gate: str = ""):
    if not updates and not trailing_updates:
        return

    lines = [f"<b>📋 POSITION CHECK — {date.today().isoformat()}</b>"]
    if market_label:
        lines.append(f"Market: {market_label}")
    if regime_gate:
        gate_emoji = {"GO": "🟢", "CAUTION": "🟡", "WARN": "🟠", "DANGER": "🔴"}.get(regime_gate, "⚪")
        lines.append(f"Regime: {gate_emoji} {regime_gate}\n")

    if trailing_updates:
        lines.append("<b>📈 STOPS RAISED</b>")
        for u in trailing_updates:
            lines.append(
                f"  {u['ticker']} stop ${u['old_stop']:.2f} → "
                f"${u['new_stop']:.2f} ({u['phase']})"
            )
        lines.append("")

    URGENT = ("stop_hit", "trail_stop_hit", "t3_hit", "t2_hit", "stuck", "losing_old")
    urgent   = [u for u in updates if u["action"] in URGENT]
    watching = [u for u in updates if u["action"] not in URGENT and u["action"] != "no_data"]

    if urgent:
        lines.append("<b>⚡ NEEDS ATTENTION</b>")
        for u in urgent:
            lines.append(f"  {u['message']}")
    if watching:
        lines.append("\n<b>👁 WATCHING</b>")
        for u in watching:
            lines.append(f"  {u['message']}")
    no_data = [u for u in updates if u["action"] == "no_data"]
    if no_data:
        tickers = ", ".join(u["entry"]["ticker"] for u in no_data)
        lines.append(f"\n⚠️ No price data: {tickers}")

    _send("\n".join(lines))



# ── Drawdown circuit breaker ──────────────────────────────────────────────────

_CIRCUIT_BREAKER_FILE = "/tmp/circuit_breaker_state.json"

def get_circuit_breaker_state() -> dict:
    """Read circuit breaker state from disk."""
    try:
        import json
        with open(_CIRCUIT_BREAKER_FILE) as f:
            return json.load(f)
    except Exception:
        return {"consecutive_losses": 0, "size_reduction": 1.0, "active": False,
                "last_updated": None, "note": ""}


def save_circuit_breaker_state(state: dict):
    """Persist circuit breaker state to disk."""
    try:
        import json
        with open(_CIRCUIT_BREAKER_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[circuit_breaker] State save failed: {e}")


def check_drawdown_circuit_breaker() -> dict:
    """
    Analyse recent closed trades for consecutive losses.
    Triggers position size reduction after N consecutive losses.

    Rules:
      3 consecutive losses → reduce size to 50%   (warning)
      5 consecutive losses → reduce size to 25%   (critical — near-stop)
      Reset to 100% after 2 consecutive wins

    Returns dict with current state and any new alert to fire.
    """
    from database import get_conn
    import json

    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT pnl_pct, pnl_gbp, position_size_gbp, exit_date, ticker, signal_type
                FROM journal
                WHERE status = 'closed' AND pnl_pct IS NOT NULL
                ORDER BY exit_date DESC
                LIMIT 20
            """).fetchall()
    except Exception as e:
        print(f"[circuit_breaker] DB read failed: {e}")
        return get_circuit_breaker_state()

    trades = [dict(r) for r in rows]
    if not trades:
        return get_circuit_breaker_state()

    # Count current streak from most recent trade
    streak_losses = 0
    streak_wins   = 0
    for t in trades:
        pnl = t.get("pnl_pct", 0) or 0
        if pnl <= 0:
            if streak_wins > 0:
                break   # streak broken
            streak_losses += 1
        else:
            if streak_losses > 0:
                break   # streak broken
            streak_wins += 1

    prev_state     = get_circuit_breaker_state()
    prev_losses    = prev_state.get("consecutive_losses", 0)
    prev_reduction = prev_state.get("size_reduction", 1.0)

    # Determine new size reduction
    if streak_wins >= 2 and prev_state.get("active"):
        size_reduction = 1.0
        active         = False
        note           = f"Circuit breaker reset after {streak_wins} consecutive wins"
    elif streak_losses >= 5:
        size_reduction = 0.25
        active         = True
        note           = f"⛔ CRITICAL: {streak_losses} consecutive losses — size at 25%"
    elif streak_losses >= 3:
        size_reduction = 0.50
        active         = True
        note           = f"⚠️ WARNING: {streak_losses} consecutive losses — size at 50%"
    else:
        size_reduction = 1.0
        active         = False
        note           = f"Normal — {streak_losses} consecutive losses (threshold: 3)"

    new_state = {
        "consecutive_losses": streak_losses,
        "consecutive_wins":   streak_wins,
        "size_reduction":     size_reduction,
        "active":             active,
        "last_updated":       date.today().isoformat(),
        "note":               note,
        "recent_trades":      [
            {
                "ticker": t["ticker"],
                "pnl_pct": t["pnl_pct"],
                "pnl_gbp": t.get("pnl_gbp"),
                "date": t.get("exit_date"),
            }
            for t in trades[:10]
        ],
    }
    save_circuit_breaker_state(new_state)

    # Fire Telegram alert on state change
    new_active  = active and not prev_state.get("active")
    state_worse = active and size_reduction < prev_reduction
    state_reset = not active and prev_state.get("active")

    if new_active or state_worse:
        try:
            from alerts import _send
            _send(
                f"🔴 <b>CIRCUIT BREAKER {note}</b>\n"
                f"Position sizing reduced to <b>{int(size_reduction*100)}%</b> of normal.\n"
                f"Last {streak_losses} trades were losers. Review your setups."
            )
        except Exception as e:
            print(f"[circuit_breaker] Alert failed: {e}")
    elif state_reset:
        try:
            from alerts import _send
            _send(
                f"✅ <b>CIRCUIT BREAKER RESET</b>\n"
                f"Position sizing back to <b>100%</b> after {streak_wins} consecutive wins."
            )
        except Exception as e:
            print(f"[circuit_breaker] Reset alert failed: {e}")

    return new_state


def run_journal_check(bars_data: dict, market_label: str = "",
                      regime_gate: str = "", auto_close: bool = True) -> dict:
    """Full journal check pipeline. Called from scanner after each scan."""
    # ── Drawdown circuit breaker ──────────────────────────────────────────────
    circuit_state = check_drawdown_circuit_breaker()
    if circuit_state.get("active"):
        print(f"[journal_tracker] ⚠️ Circuit breaker ACTIVE: {circuit_state['note']}")

    trailing_updates = update_trailing_stops(bars_data)
    updates          = check_open_positions(bars_data)

    if not updates and not trailing_updates:
        print("[journal_tracker] No open positions to check")
        return {"checked": 0, "auto_closed": 0, "needs_attention": 0, "stops_raised": 0}

    auto_closed     = auto_close_stops(updates) if auto_close else 0
    needs_attention = sum(1 for u in updates if u["action"] in
                          ("stop_hit", "trail_stop_hit", "t2_hit", "t3_hit",
                           "stuck", "losing_old"))

    send_position_digest(updates, trailing_updates, market_label, regime_gate)

    print(f"[journal_tracker] Checked {len(updates)}, raised {len(trailing_updates)} stops, "
          f"closed {auto_closed}, {needs_attention} need attention")

    return {
        "checked":          len(updates),
        "auto_closed":      auto_closed,
        "needs_attention":  needs_attention,
        "stops_raised":     len(trailing_updates),
        "updates":          updates,
        "trailing_updates": trailing_updates,
        "circuit_breaker":  circuit_state,
    }


# ── Skip outcome tracker ──────────────────────────────────────────────────────
SKIP_WINDOW_DAYS = 28

def _trading_days_since(skip_date_str: str) -> int:
    try:
        start = date.fromisoformat(skip_date_str)
        end   = date.today()
        days  = 0
        cur   = start
        while cur < end:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                days += 1
        return days
    except Exception:
        return 0


def _fetch_daily_bars(ticker: str, from_date: str) -> list:
    try:
        import yfinance as yf
        start = date.fromisoformat(from_date)
        start_str = (start - timedelta(days=1)).isoformat()
        df = yf.download(
            tickers=ticker,
            start=start_str,
            end=(date.today() + timedelta(days=1)).isoformat(),
            interval="1d", progress=False, auto_adjust=True,
        )
        if df.empty:
            return []
        closes = df["Close"].dropna()
        return [(str(idx.date()), round(float(val), 2)) for idx, val in closes.items()
                if str(idx.date()) >= from_date]
    except Exception as e:
        print(f"[skip_tracker] Bar fetch error for {ticker}: {e}")
        return []


def _calculate_skip_outcome(entry: dict, bars: list) -> dict:
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
    t1_hit = False; t1_hit_day = None
    if t1_px:
        for i, (d_str, px) in enumerate(bars):
            if px >= t1_px:
                t1_hit = True; t1_hit_day = i + 1; break
    if t1_hit:
        outcome = round((bars[t1_hit_day - 1][1] - entry_px) / entry_px * 100, 2)
    else:
        outcome = peak_pct if peak_pct > 0 else latest_pct
    trading_days = _trading_days_since(entry.get("added_date", date.today().isoformat()))
    return {
        "outcome_if_taken": outcome, "peak_pct": peak_pct,
        "trough_pct": trough_pct, "latest_pct": latest_pct,
        "t1_hit": t1_hit, "t1_hit_day": t1_hit_day,
        "trading_days": trading_days, "frozen": trading_days >= 20,
        "bars_used": len(bars), "latest_price": latest_px,
    }


def update_skip_outcomes(dry_run: bool = False) -> dict:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, ticker, added_date, entry_price, target_1, target_2,
                   skip_reason, suggestion_score, outcome_if_taken
            FROM journal
            WHERE status = 'skipped' AND entry_price IS NOT NULL AND added_date IS NOT NULL
            ORDER BY added_date DESC
        """).fetchall()
    entries = [dict(r) for r in rows]
    if not entries:
        print("[skip_tracker] No skipped entries to update")
        return {"checked": 0, "updated": 0, "frozen": 0, "errors": 0}

    checked = updated = frozen_count = errors = 0
    for entry in entries:
        try:
            age_days = (date.today() - date.fromisoformat(entry["added_date"])).days
        except Exception:
            age_days = 999
        if age_days > SKIP_WINDOW_DAYS + 3:
            frozen_count += 1; continue
        checked += 1
        try:
            bars    = _fetch_daily_bars(entry["ticker"], entry["added_date"])
            outcome = _calculate_skip_outcome(entry, bars)
            if not outcome:
                errors += 1; continue
            if not dry_run:
                update_data = {"outcome_if_taken": outcome["outcome_if_taken"]}
                detail = (
                    f"Auto: {outcome['trading_days']}d · Peak {outcome['peak_pct']:+.1f}% · "
                    f"{'T1 hit day ' + str(outcome['t1_hit_day']) if outcome['t1_hit'] else 'T1 not hit'} · "
                    f"Latest {outcome['latest_pct']:+.1f}%"
                    + (" [FROZEN]" if outcome["frozen"] else "")
                )
                with get_conn() as conn:
                    row = conn.execute("SELECT skip_note FROM journal WHERE id = ?",
                                       (entry["id"],)).fetchone()
                    existing = (row["skip_note"] or "") if row else ""
                manual = "\n".join(l for l in existing.split("\n")
                                   if not l.startswith("Auto:")).strip()
                update_data["skip_note"] = (manual + "\n" + detail).strip()
                with get_conn() as conn:
                    set_clause = ", ".join(f"{k} = ?" for k in update_data)
                    conn.execute(f"UPDATE journal SET {set_clause} WHERE id = ?",
                                 list(update_data.values()) + [entry["id"]])
            updated += 1
        except Exception as e:
            print(f"[skip_tracker] Error processing {entry['ticker']}: {e}"); errors += 1

    print(f"[skip_tracker] Done — checked {checked}, updated {updated}, "
          f"frozen {frozen_count}, errors {errors}")
    return {"checked": checked, "updated": updated, "frozen": frozen_count, "errors": errors}
