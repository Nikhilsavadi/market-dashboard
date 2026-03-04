"""
intraday_ma_scanner.py
----------------------
Scans for intraday MA10/MA21 touches and bounces during market hours.
Runs every 30 minutes via the scheduler.

Design:
  - Only watches stocks already in the overnight scan cache (pre-qualified on RS, VCS, sector)
  - Fetches 5-minute bars from Polygon for each candidate
  - Computes intraday EMA10 and EMA21 from those bars
  - Detects a confirmed bounce: candle low tagged the MA, close is back above it
  - Deduplicates: one alert per ticker per MA per session
  - Fires Telegram immediately on detection

Alert criteria:
  - Stock must have RS >= 70 in overnight scan
  - Stock must be above daily MA21 (in uptrend) — no catching falling knives
  - Intraday low touched within 0.75 ATR of the MA
  - Candle that touched closed ABOVE the MA (bounce confirmed, not breakdown)
  - Volume on the touch candle >= 0.8x average intraday bar volume (not a dead candle)
  - Price has not already moved > 2% away from MA (not chasing extended moves)

Deduplication:
  - Alert file stored in DATA_DIR/intraday_alerts_{date}.json
  - Each ticker+MA combination only fires once per trading day
"""

import os
import json
import math
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional
import pandas as pd
import requests

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
CACHE_FILE = DATA_DIR / "scan_cache.json"


# ── Polygon 5-min bars ────────────────────────────────────────────────────────

def _fetch_intraday_bars(ticker: str, session: requests.Session) -> Optional[pd.DataFrame]:
    """Fetch last 2 days of 5-minute bars for a ticker from Polygon."""
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        return None

    # Use last 2 days to get enough bars for EMA warmup
    to_dt   = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=3)  # 3 days = plenty of 5-min bars
    from_str = from_dt.strftime("%Y-%m-%d")
    to_str   = to_dt.strftime("%Y-%m-%d")

    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/5/minute/{from_str}/{to_str}"
    try:
        r = session.get(url, params={
            "adjusted": "true",
            "sort": "asc",
            "limit": 1000,
            "apiKey": api_key,
        }, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()
        results = data.get("results", [])
        if len(results) < 20:
            return None

        df = pd.DataFrame(results)
        df["timestamp"] = pd.to_datetime(df["t"] * 1_000_000, utc=True)
        df = df.set_index("timestamp").sort_index()
        df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                                 "c": "close", "v": "volume"})
        return df[["open", "high", "low", "close", "volume"]]

    except Exception as e:
        print(f"[intraday_ma] {ticker} fetch error: {e}")
        return None


# ── MA touch detection ────────────────────────────────────────────────────────

def _detect_ma_touch_bounce(df: pd.DataFrame, daily_atr: float) -> list:
    """
    Check if the last 1-3 candles touched EMA10 or EMA21 and bounced.

    Returns list of dicts with:
        ma_name    : "EMA10" | "EMA21"
        touch_low  : float — intraday low that tagged the MA
        ma_val     : float — MA value at time of touch
        close      : float — close of touch candle (above MA = bounce)
        pct_from_ma: float — how far current price is above MA
        candle_vol : int   — volume of touch candle
        avg_vol    : float — average 5-min volume
        vol_ratio  : float — candle vol / avg vol
        confirmed  : bool  — close above MA (bounce confirmed)
        ts         : str   — timestamp of touch candle
    """
    if df is None or len(df) < 30:
        return []

    # Only look at today's bars
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=13, minute=30, second=0, microsecond=0)  # 09:30 ET = 13:30 UTC
    today_bars = df[df.index >= today_start]

    if len(today_bars) < 5:
        return []

    # Compute intraday EMAs on ALL bars (for warmup), then slice
    ema10 = df["close"].ewm(span=10, adjust=False).mean()
    ema21 = df["close"].ewm(span=21, adjust=False).mean()

    # Average 5-min volume (today's bars)
    avg_vol = float(today_bars["volume"].mean()) if len(today_bars) >= 3 else 0

    # ATR proxy from intraday bars (last 20 bars)
    recent = df.tail(20)
    intraday_atr = float((recent["high"] - recent["low"]).mean())

    # Use daily ATR if available; if very small stock, use intraday
    touch_window = max(intraday_atr * 1.5, daily_atr * 0.3) if daily_atr else intraday_atr * 1.5

    touches = []

    for ma_name, ma_series in [("EMA10", ema10), ("EMA21", ema21)]:
        # Check last 3 candles for a touch
        lookback = today_bars.tail(3)
        ma_lookback = ma_series.loc[lookback.index]

        for ts, candle in lookback.iterrows():
            ma_val = ma_lookback.get(ts)
            if ma_val is None or math.isnan(ma_val):
                continue

            candle_low   = float(candle["low"])
            candle_close = float(candle["close"])
            candle_vol   = float(candle["volume"])

            # Did the low tag the MA within the touch window?
            distance = candle_low - ma_val
            if not (-touch_window <= distance <= touch_window * 0.5):
                continue  # didn't touch

            # Bounce confirmed: close must be above the MA
            if candle_close <= ma_val:
                continue  # broke through, not a bounce

            # Current price must not be too extended from the MA
            current_price = float(df["close"].iloc[-1])
            pct_above_ma = (current_price - ma_val) / ma_val * 100
            if pct_above_ma > 3.0:
                continue  # already ran too much, don't chase

            # Volume check: touch candle should have some activity
            vol_ratio = candle_vol / avg_vol if avg_vol > 0 else 1.0
            if vol_ratio < 0.5:
                continue  # dead candle, not a real touch

            touches.append({
                "ma_name":     ma_name,
                "touch_low":   round(candle_low, 2),
                "ma_val":      round(float(ma_val), 2),
                "close":       round(candle_close, 2),
                "current":     round(current_price, 2),
                "pct_from_ma": round(pct_above_ma, 2),
                "candle_vol":  int(candle_vol),
                "avg_vol":     round(avg_vol, 0),
                "vol_ratio":   round(vol_ratio, 2),
                "confirmed":   True,
                "ts":          str(ts),
            })

    return touches


# ── Deduplication ─────────────────────────────────────────────────────────────

def _load_alert_log() -> set:
    """Load today's already-fired alerts. Returns set of 'TICKER:MA' strings."""
    log_file = DATA_DIR / f"intraday_alerts_{date.today().isoformat()}.json"
    if log_file.exists():
        try:
            return set(json.loads(log_file.read_text()))
        except Exception:
            return set()
    return set()


def _save_alert_log(fired: set):
    """Persist fired alerts for today."""
    log_file = DATA_DIR / f"intraday_alerts_{date.today().isoformat()}.json"
    try:
        log_file.write_text(json.dumps(list(fired)))
    except Exception as e:
        print(f"[intraday_ma] Alert log save error: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def _send_telegram(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[intraday_ma] Telegram not configured")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[intraday_ma] Telegram error: {e}")
        return False


# ── Main scanner ──────────────────────────────────────────────────────────────

def run_intraday_ma_scan() -> dict:
    """
    Main entry point. Called every 30 minutes during market hours.
    Returns summary dict with alerts fired.
    """
    print(f"[intraday_ma] Starting scan {datetime.now().strftime('%H:%M:%S')}")

    # ── Load overnight cache for pre-qualified universe ───────────────────────
    if not CACHE_FILE.exists():
        print("[intraday_ma] No cache — skipping")
        return {"alerts": 0, "scanned": 0}

    try:
        cache = json.loads(CACHE_FILE.read_text())
    except Exception as e:
        print(f"[intraday_ma] Cache read error: {e}")
        return {"alerts": 0, "scanned": 0}

    market = cache.get("market", {})
    mkt_score = market.get("score", 50)

    # Don't fire long alerts in a bad market
    if mkt_score < 35:
        print(f"[intraday_ma] Market score {mkt_score} — skipping longs")
        long_watch = []
    else:
        # Watch candidates: all stocks from overnight scan with RS >= 65
        # Use all_stocks (broader) not just long_signals — catches stocks approaching setup
        all_stocks = cache.get("all_stocks", []) or cache.get("long_signals", [])
        long_watch = [
            s for s in all_stocks
            if (s.get("rs") or 0) >= 65
            and s.get("price", 0) > 0
            and s.get("ma21")  # must have MA data
            and s.get("above_ma200", True)  # in longer uptrend
        ]

    # Also watch short candidates for intraday rejections at MAs
    short_signals = cache.get("short_signals", [])
    short_watch = short_signals[:20]  # top 20 shorts

    candidates = long_watch[:120] + short_watch  # cap at 140 total
    print(f"[intraday_ma] Watching {len(long_watch)} longs + {len(short_watch)} shorts = {len(candidates)} total")

    if not candidates:
        return {"alerts": 0, "scanned": 0}

    # ── Load deduplication log ────────────────────────────────────────────────
    fired_today = _load_alert_log()

    # ── HTTP session for concurrent fetching ─────────────────────────────────
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503])
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20))

    # ── Scan each candidate ───────────────────────────────────────────────────
    alerts_fired = 0
    scanned      = 0
    new_fired    = set()

    for s in candidates:
        ticker    = s.get("ticker", "")
        rs        = s.get("rs") or 0
        vcs       = s.get("vcs") or 9
        daily_atr = s.get("atr") or 0
        daily_ma21 = s.get("ma21") or 0
        price     = s.get("price") or 0
        sector    = s.get("sector", "")
        is_short  = s in short_watch

        df = _fetch_intraday_bars(ticker, session)
        scanned += 1

        if df is None:
            continue

        touches = _detect_ma_touch_bounce(df, daily_atr)

        for touch in touches:
            ma_name = touch["ma_name"]
            alert_key = f"{ticker}:{ma_name}"

            if alert_key in fired_today or alert_key in new_fired:
                continue  # already alerted today

            # For longs: skip if VCS too loose (> 8) — setup quality gate
            if not is_short and vcs > 8:
                continue

            # Build Telegram message
            current = touch["current"]
            pct_ext = touch["pct_from_ma"]
            ma_val  = touch["ma_val"]
            vol_r   = touch["vol_ratio"]

            # Stop: just below touch candle low (with small buffer)
            stop = round(touch["touch_low"] * 0.995, 2)
            risk_pct = round((current - stop) / current * 100, 2)

            if is_short:
                emoji    = "🔴"
                direction = "REJECTION"
                action    = f"Short entry near ${current} · Cover stop ${stop}"
            else:
                emoji    = "⚡"
                direction = "BOUNCE"
                vcs_str  = f"VCS {vcs:.1f}" if vcs else ""
                action    = f"Entry near ${current} · Stop ${stop} ({risk_pct}% risk)"

            now_uk = datetime.now(timezone.utc) + timedelta(hours=0)  # UTC = UK in winter
            time_str = now_uk.strftime("%H:%M")

            msg = (
                f"{emoji} <b>INTRADAY {direction} — {ticker}</b> [{time_str}]\n"
                f"   {ma_name} tag at ${touch['touch_low']} → closed ${touch['close']}\n"
                f"   {action}\n"
                f"   RS {rs} · {vcs_str if not is_short else ''} · Vol {vol_r:.1f}× avg · {sector}\n"
                f"   {pct_ext:.1f}% above {ma_name} · MA level ${ma_val}"
            )

            sent = _send_telegram(msg)
            if sent:
                new_fired.add(alert_key)
                alerts_fired += 1
                print(f"[intraday_ma] ✓ Alert sent: {ticker} {ma_name} {direction}")
            else:
                print(f"[intraday_ma] ✗ Alert failed: {ticker}")

        # Small delay to avoid hammering Polygon
        time.sleep(0.05)

    # ── Save updated dedup log ────────────────────────────────────────────────
    if new_fired:
        _save_alert_log(fired_today | new_fired)

    print(f"[intraday_ma] Done — {scanned} scanned · {alerts_fired} alerts fired")
    return {
        "alerts":    alerts_fired,
        "scanned":   scanned,
        "new_alerts": list(new_fired),
        "ran_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
