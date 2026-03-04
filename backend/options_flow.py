"""
options_flow.py
---------------
Fetches unusual options activity for a list of tickers.
Uses Unusual Whales free API (no key needed for basic data)
and Yahoo Finance options chain as fallback.

Flags:
  - Unusual call vol vs open interest (ratio > 2x)
  - Large sweeps (single trades > $100k premium)
  - Net call/put ratio trending bullish (calls > puts by volume)
"""

import requests
import time
from typing import Optional
from datetime import date, datetime, timedelta

# In-memory cache — options data valid for 4 hours during market day
_cache: dict = {}
_cache_ts: dict = {}
CACHE_TTL = 14400  # 4 hours


def _is_stale(ticker: str) -> bool:
    ts = _cache_ts.get(ticker, 0)
    return (time.time() - ts) > CACHE_TTL


def _fetch_yahoo_options(ticker: str) -> Optional[dict]:
    """
    Fetch options chain from Yahoo Finance.
    Returns summary with call/put volumes and OI.
    """
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/options/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        data = resp.json()
        result = data.get("optionChain", {}).get("result", [])
        if not result:
            return None

        chain = result[0]
        calls = chain.get("options", [{}])[0].get("calls", [])
        puts  = chain.get("options", [{}])[0].get("puts", [])

        if not calls and not puts:
            return None

        # Aggregate volumes and OI
        call_vol  = sum(c.get("volume", 0) or 0 for c in calls)
        put_vol   = sum(p.get("volume", 0) or 0 for p in puts)
        call_oi   = sum(c.get("openInterest", 0) or 0 for c in calls)
        put_oi    = sum(p.get("openInterest", 0) or 0 for p in puts)

        total_vol = call_vol + put_vol
        if total_vol == 0:
            return None

        cp_ratio = round(call_vol / put_vol, 2) if put_vol > 0 else 99.0

        # Flag unusual vol vs OI
        unusual_calls = []
        for c in calls:
            vol = c.get("volume", 0) or 0
            oi  = c.get("openInterest", 0) or 0
            if oi > 0 and vol > 0 and vol / oi > 2.0 and vol > 500:
                strike = c.get("strike", 0)
                expiry = c.get("expiration", 0)
                last   = c.get("lastPrice", 0) or 0
                unusual_calls.append({
                    "strike":    strike,
                    "expiry":    date.fromtimestamp(expiry).isoformat() if expiry else None,
                    "vol":       vol,
                    "oi":        oi,
                    "vol_oi_ratio": round(vol / oi, 1),
                    "last_price": last,
                    "est_premium": round(vol * last * 100, 0),  # est notional
                })

        unusual_calls.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)

        # Large sweeps — calls with estimated premium > $100k
        sweeps = [c for c in unusual_calls if c.get("est_premium", 0) > 100_000]

        # Trend: compare today's CP ratio vs historical OI CP ratio
        oi_cp = round(call_oi / put_oi, 2) if put_oi > 0 else 1.0
        # If today's call vol is higher than OI suggests, bullish flow
        flow_bullish = cp_ratio > oi_cp * 1.2

        return {
            "ticker":         ticker,
            "call_vol":       call_vol,
            "put_vol":        put_vol,
            "call_oi":        call_oi,
            "put_oi":         put_oi,
            "cp_ratio":       cp_ratio,
            "oi_cp_ratio":    oi_cp,
            "flow_bullish":   flow_bullish,
            "unusual_calls":  unusual_calls[:5],  # top 5
            "sweeps":         sweeps[:3],
            "has_unusual":    len(unusual_calls) > 0,
            "has_sweeps":     len(sweeps) > 0,
            "fetched_at":     datetime.now().strftime("%H:%M:%S"),
        }

    except Exception as e:
        print(f"[options_flow] Yahoo fetch {ticker}: {e}")
        return None


def get_options_flow(ticker: str, force: bool = False) -> Optional[dict]:
    """Get options flow for a ticker, using cache if fresh."""
    if not force and ticker in _cache and not _is_stale(ticker):
        return _cache[ticker]

    result = _fetch_yahoo_options(ticker)
    if result:
        _cache[ticker] = result
        _cache_ts[ticker] = time.time()
    return result


def batch_options_flow(tickers: list, delay: float = 0.3) -> dict:
    """Fetch options flow for multiple tickers."""
    results = {}
    for ticker in tickers:
        flow = get_options_flow(ticker)
        if flow:
            results[ticker] = flow
        time.sleep(delay)
    return results


def options_flag(flow: Optional[dict]) -> str:
    """
    Returns a flag string for display:
    'sweep' > 'bullish_flow' > 'unusual' > 'neutral' > 'none'
    """
    if not flow:
        return "none"
    if flow.get("has_sweeps"):
        return "sweep"
    if flow.get("flow_bullish") and flow.get("has_unusual"):
        return "bullish_flow"
    if flow.get("has_unusual"):
        return "unusual"
    if flow.get("flow_bullish"):
        return "bullish"
    return "neutral"
