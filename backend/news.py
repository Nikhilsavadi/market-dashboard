"""
news.py
-------
Fetches recent news headlines for tickers via Alpaca News API.
Returns last 5 headlines per ticker with sentiment flag.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests

_news_cache: dict[str, list] = {}
_cache_timestamp: dict[str, datetime] = {}
CACHE_TTL_MINS = 60  # refresh news every hour


def get_news(ticker: str, limit: int = 5) -> list[dict]:
    """
    Fetch recent news for a ticker from Alpaca.
    Returns list of {headline, source, url, published_at, sentiment}
    """
    now = datetime.now(timezone.utc)

    # Return cached if fresh
    if ticker in _news_cache:
        age = (now - _cache_timestamp.get(ticker, datetime.min.replace(tzinfo=timezone.utc))).seconds / 60
        if age < CACHE_TTL_MINS:
            return _news_cache[ticker]

    token = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not token or not secret:
        return []

    try:
        url = "https://data.alpaca.markets/v1beta1/news"
        params = {
            "symbols": ticker,
            "limit": limit,
            "sort": "desc",
            "start": (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        headers = {
            "APCA-API-KEY-ID": token,
            "APCA-API-SECRET-KEY": secret,
        }
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        if resp.status_code != 200:
            return []

        articles = resp.json().get("news", [])
        results = []
        for a in articles:
            results.append({
                "headline": a.get("headline", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
                "published_at": a.get("created_at", ""),
                "summary": a.get("summary", "")[:200] if a.get("summary") else "",
                "sentiment": _simple_sentiment(a.get("headline", "")),
            })

        _news_cache[ticker] = results
        _cache_timestamp[ticker] = now
        return results

    except Exception as e:
        print(f"[news] Error fetching {ticker}: {e}")
        return []


def _simple_sentiment(headline: str) -> str:
    """
    Very basic keyword sentiment — positive/negative/neutral.
    Not a replacement for proper NLP but useful as a quick flag.
    """
    headline_lower = headline.lower()
    positive = ["beat", "beats", "record", "surge", "soar", "rally", "upgrade",
                 "growth", "profit", "raise", "raised", "breakout", "wins", "strong"]
    negative = ["miss", "misses", "cut", "cuts", "drop", "fall", "decline", "downgrade",
                 "loss", "warning", "weak", "recall", "lawsuit", "fraud", "short"]

    pos_count = sum(1 for w in positive if w in headline_lower)
    neg_count = sum(1 for w in negative if w in headline_lower)

    if pos_count > neg_count:
        return "positive"
    if neg_count > pos_count:
        return "negative"
    return "neutral"


def batch_news(tickers: list[str]) -> dict[str, list]:
    """Fetch news for multiple tickers. Returns dict of ticker -> news list."""
    return {ticker: get_news(ticker, limit=3) for ticker in tickers}
