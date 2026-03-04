"""
premarket.py
------------
Fetches pre-market prices for open journal positions and top signals.
Runs at 06:15 UK (before morning brief at 06:30).
Enriches morning brief with:
  - Which setups gapped up/down overnight
  - Whether gap invalidates the setup (gapped through stop or entry)
  - Pre-market volume vs average
  - Open position status at market open
"""

import yfinance as yf
from datetime import date, datetime
from typing import Optional
from database import journal_list
from alerts import _send


def _get_premarket_data(ticker: str) -> Optional[dict]:
    """
    Fetch pre-market price, change, and volume for a single ticker.
    yfinance returns pre-market data in fast_info and history with prepost=True.
    """
    try:
        tk   = yf.Ticker(ticker)
        info = tk.fast_info

        # Live/pre-market price
        pre_price = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)

        if not pre_price or not prev_close:
            return None

        gap_pct = round((pre_price - prev_close) / prev_close * 100, 2)

        # Pre-market volume (last 1d with prepost)
        try:
            hist     = tk.history(period="1d", interval="1m", prepost=True)
            pre_rows = hist[hist.index.hour < 14]  # pre 9:30am ET = pre 14:30 UTC
            pre_vol  = int(pre_rows["Volume"].sum()) if not pre_rows.empty else 0
        except Exception:
            pre_vol = 0

        return {
            "ticker":     ticker,
            "pre_price":  round(pre_price, 2),
            "prev_close": round(prev_close, 2),
            "gap_pct":    gap_pct,
            "pre_vol":    pre_vol,
        }
    except Exception as e:
        print(f"[premarket] Error {ticker}: {e}")
        return None


def batch_premarket(tickers: list) -> dict:
    """Fetch pre-market data for multiple tickers. Returns ticker -> data dict."""
    results = {}
    for t in tickers:
        data = _get_premarket_data(t)
        if data:
            results[t] = data
    return results


def classify_gap(gap_pct: float, entry_price: Optional[float],
                 stop_price: Optional[float], current_price: float) -> str:
    """
    Classify the gap relative to the setup:
      - gap_above_entry: gapped past entry, too extended
      - gap_into_entry: gapped to entry zone, ready to trigger
      - flat: no meaningful gap
      - gap_toward_stop: gapped down, approaching stop
      - gap_through_stop: gapped below stop, setup invalidated
    """
    if stop_price and current_price <= stop_price:
        return "gap_through_stop"
    if stop_price and gap_pct < 0:
        dist = (current_price - stop_price) / current_price * 100
        if dist < 2:
            return "gap_toward_stop"
    if entry_price and current_price >= entry_price * 1.03:
        return "gap_above_entry"
    if entry_price and abs(current_price - entry_price) / entry_price < 0.02:
        return "gap_into_entry"
    if abs(gap_pct) < 0.5:
        return "flat"
    return "gap_down" if gap_pct < 0 else "gap_up"


def enrich_signals_premarket(signals: list, alert_invalidated: bool = True) -> list:
    """
    Takes list of signal dicts (from scan cache), adds pre-market data.

    Auto-invalidation: if the gap exceeds 0.5×ATR in either direction,
    the signal is flagged as invalidated and moved to the end of the list.

    Gap > 0.5×ATR up   → gap_above_entry (too extended, chasing)
    Gap > 0.5×ATR down → gap_toward_stop or gap_through_stop (setup broke)

    Returns enriched list with:
      - valid signals first (gap_into_entry / flat / small gap)
      - invalidated signals last with gap_valid=False
    """
    if not signals:
        return signals

    tickers = [s["ticker"] for s in signals]
    pm_data = batch_premarket(tickers)

    invalidated = []
    valid       = []

    for s in signals:
        t    = s["ticker"]
        data = pm_data.get(t)
        if data:
            s["pre_price"] = data["pre_price"]
            s["gap_pct"]   = data["gap_pct"]
            s["pre_vol"]   = data["pre_vol"]
            s["gap_class"] = classify_gap(
                data["gap_pct"],
                s.get("entry_pivot") or s.get("price"),
                s.get("stop_price"),
                data["pre_price"],
            )

            # Auto-invalidation: gap > 0.5×ATR makes setup stale
            atr          = s.get("atr") or 0
            price        = s.get("price") or data["pre_price"] or 1
            atr_pct      = (atr / price * 100) if price else 0
            gap_abs      = abs(data["gap_pct"])
            bad_gap      = (
                s["gap_class"] in ("gap_through_stop", "gap_above_entry")
                or (atr_pct > 0 and gap_abs > atr_pct * 0.5)
            )

            s["gap_valid"]    = not bad_gap
            s["atr_pct"]      = round(atr_pct, 2)
            s["gap_vs_atr"]   = round(gap_abs / atr_pct, 2) if atr_pct else None

            if bad_gap:
                s["gap_note"] = (
                    f"Gap of {data['gap_pct']:+.1f}% exceeds 0.5×ATR ({atr_pct*0.5:.1f}%) — setup stale"
                    if atr_pct else f"Gap class: {s['gap_class']} — setup invalidated"
                )
                invalidated.append(s)
            else:
                valid.append(s)
        else:
            s["pre_price"]  = None
            s["gap_pct"]    = None
            s["gap_class"]  = "unknown"
            s["gap_valid"]  = True   # no data = don't invalidate
            valid.append(s)

    # Alert on invalidated setups
    if alert_invalidated and invalidated:
        try:
            lines = ["⛔ <b>PRE-MARKET: Signals invalidated by gap</b>"]
            for s in invalidated[:5]:
                lines.append(
                    f"  {s['ticker']} {s.get('gap_pct', 0):+.1f}% — {s.get('gap_note', s['gap_class'])}"
                )
            _send("\n".join(lines))
        except Exception as e:
            print(f"[premarket] Alert failed: {e}")

    # Valid signals first, invalidated signals appended at end
    return valid + invalidated


def premarket_position_check() -> list:
    """
    Check all open positions for pre-market gaps.
    Returns list of position updates with gap status.
    """
    positions = journal_list(status="open") + journal_list(status="watching")
    if not positions:
        return []

    tickers = [p["ticker"] for p in positions]
    pm_data = batch_premarket(tickers)

    results = []
    for pos in positions:
        t    = pos["ticker"]
        data = pm_data.get(t)
        if not data:
            continue

        entry_px = pos.get("entry_price")
        stop_px  = pos.get("stop_price")
        t1_px    = pos.get("target_1")
        gap_c    = classify_gap(data["gap_pct"], entry_px, stop_px, data["pre_price"])

        results.append({
            "ticker":     t,
            "pre_price":  data["pre_price"],
            "gap_pct":    data["gap_pct"],
            "gap_class":  gap_c,
            "stop_price": stop_px,
            "entry_price": entry_px,
            "target_1":   t1_px,
            "status":     pos.get("status"),
            "signal_type": pos.get("signal_type"),
            "urgent":     gap_c in ("gap_through_stop", "gap_toward_stop"),
        })

    return results


def format_premarket_brief(position_updates: list, top_signals: list) -> str:
    """
    Format pre-market section for morning brief Telegram message.
    """
    lines = [f"<b>🌅 PRE-MARKET — {datetime.now().strftime('%H:%M')}</b>"]

    # Urgent position alerts
    urgent = [p for p in position_updates if p.get("urgent")]
    if urgent:
        lines.append("\n⚠️ <b>POSITION ALERTS</b>")
        for p in urgent:
            icon = "⛔" if p["gap_class"] == "gap_through_stop" else "⚠️"
            lines.append(
                f"  {icon} <b>{p['ticker']}</b> pre-mkt ${p['pre_price']:.2f} "
                f"({p['gap_pct']:+.1f}%) — {p['gap_class'].replace('_',' ').upper()}"
            )

    # Open positions summary
    non_urgent = [p for p in position_updates if not p.get("urgent")]
    if non_urgent:
        lines.append("\n📋 <b>Open positions</b>")
        for p in non_urgent:
            icon = {"gap_up": "↑", "gap_down": "↓", "flat": "→",
                    "gap_into_entry": "🎯", "gap_above_entry": "↑↑"}.get(p["gap_class"], "·")
            lines.append(
                f"  {icon} {p['ticker']} ${p['pre_price']:.2f} ({p['gap_pct']:+.1f}%)"
            )

    # Top signals gap check
    if top_signals:
        lines.append("\n📊 <b>Top setups gap check</b>")

        GAP_ICONS = {
            "gap_into_entry":   "🎯 GAP INTO ENTRY",
            "gap_above_entry":  "↑↑ GAPPED EXTENDED",
            "flat":             "→ flat",
            "gap_up":           "↑ gap up",
            "gap_down":         "↓ gap down",
            "gap_toward_stop":  "⚠️ toward stop",
            "gap_through_stop": "⛔ through stop",
        }
        for s in top_signals[:5]:
            if s.get("pre_price") is None:
                continue
            label = GAP_ICONS.get(s.get("gap_class", ""), "")
            lines.append(
                f"  {s['ticker']} ${s.get('pre_price', '?'):.2f} "
                f"({s.get('gap_pct', 0):+.1f}%) {label}"
            )

    return "\n".join(lines)
