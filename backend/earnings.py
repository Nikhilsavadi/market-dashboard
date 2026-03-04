"""
earnings.py
-----------
Fetches next earnings dates for tickers.
Uses yfinance as fallback (free, no API key needed).
Flags stocks with earnings within N days.
"""

import time
from datetime import datetime, date
from typing import Optional
import requests

# Cache in memory for the session — earnings dates don't change intraday
_earnings_cache: dict[str, Optional[date]] = {}


def get_earnings_date(ticker: str) -> Optional[date]:
    """
    Returns the next earnings date for a ticker, or None if unknown.
    Tries yfinance fast endpoint first, falls back gracefully.
    """
    if ticker in _earnings_cache:
        return _earnings_cache[ticker]

    result = _fetch_via_yfinance(ticker)
    _earnings_cache[ticker] = result
    return result


def _fetch_via_yfinance(ticker: str) -> Optional[date]:
    """Pull next earnings date from yfinance calendar endpoint."""
    try:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        params = {"modules": "calendarEvents"}
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        earnings = (
            data.get("quoteSummary", {})
                .get("result", [{}])[0]
                .get("calendarEvents", {})
                .get("earnings", {})
                .get("earningsDate", [])
        )

        if not earnings:
            return None

        # earnings is a list of {raw: unix_ts, fmt: "YYYY-MM-DD"}
        dates = []
        today = date.today()
        for e in earnings:
            raw = e.get("raw")
            if raw:
                d = date.fromtimestamp(raw)
                if d >= today:
                    dates.append(d)

        return min(dates) if dates else None

    except Exception:
        return None


def days_to_earnings(ticker: str) -> Optional[int]:
    """
    Returns number of days until next earnings, or None if unknown.
    Negative = earnings already passed.
    """
    ed = get_earnings_date(ticker)
    if ed is None:
        return None
    return (ed - date.today()).days


def earnings_risk_flag(days: Optional[int], threshold: int = 7) -> str:
    """
    Returns a risk flag string based on proximity to earnings.
    threshold: warn if earnings within N days.
    """
    if days is None:
        return "unknown"
    if days < 0:
        return "passed"
    if days <= 2:
        return "imminent"   # do not enter
    if days <= threshold:
        return "warning"    # be cautious
    return "clear"


def batch_earnings(tickers: list[str], delay: float = 0.15) -> dict[str, dict]:
    """
    Fetch earnings dates for multiple tickers.
    Returns dict of ticker -> {date, days, flag}
    """
    results = {}
    for ticker in tickers:
        days = days_to_earnings(ticker)
        ed = get_earnings_date(ticker)
        results[ticker] = {
            "earnings_date": ed.isoformat() if ed else None,
            "days_to_earnings": days,
            "earnings_flag": earnings_risk_flag(days),
        }
        time.sleep(delay)  # avoid hammering Yahoo

    return results
