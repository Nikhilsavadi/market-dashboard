"""
social_sentiment.py
-------------------
Aggregates social intelligence for micro cap tickers from three free sources:

1. Reddit (PRAW) — r/wallstreetbets, r/smallstreetbets, r/stocks, r/investing,
                    r/SecurityAnalysis, r/pennystocks
   Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET env vars
   Signals: mention count (24h vs 7d baseline), DD posts, sentiment, top post

2. StockTwits (public API, no key needed) — purpose-built stock sentiment
   Signals: message volume (24h), bull/bear ratio, trending flag

3. Alpaca News — already integrated, extended to micro caps
   Signals: headline count (7d), sentiment distribution, catalyst keywords

Composite score: 0-10
  - 3 pts StockTwits (volume + sentiment)
  - 4 pts Reddit (mentions + DD posts + sentiment)
  - 3 pts News (recency + catalyst keywords)

Cache: in-memory per ticker, TTL 4 hours (social data doesn't need to be live)
Results integrated into microcap_scanner payload.
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict[str, dict] = {}
_cache_ts: dict[str, datetime] = {}
CACHE_TTL_HOURS = 4


def _is_cached(ticker: str) -> bool:
    if ticker not in _cache:
        return False
    age = (datetime.now(timezone.utc) - _cache_ts[ticker]).total_seconds() / 3600
    return age < CACHE_TTL_HOURS


# ── StockTwits ─────────────────────────────────────────────────────────────────

def _fetch_stocktwits(ticker: str) -> dict:
    """
    Public StockTwits API — no key needed.
    Returns message count, bull/bear counts, trending flag, top messages.
    """
    try:
        url  = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data     = resp.json()
            messages = data.get("messages", [])
            symbol   = data.get("symbol", {})

            bull = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
            bear = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")
            total_sentiment = bull + bear

            # Watchlist count = proxy for interest
            watchlist_count = symbol.get("watchlist_count", 0)

            # Recent messages (last 30 from stream)
            top_messages = []
            for m in messages[:5]:
                body = m.get("body", "")
                if body:
                    top_messages.append({
                        "body":      body[:200],
                        "sentiment": m.get("entities", {}).get("sentiment", {}).get("basic", ""),
                        "created":   m.get("created_at", ""),
                        "likes":     m.get("likes", {}).get("total", 0),
                    })

            bull_pct = round(bull / total_sentiment * 100) if total_sentiment > 0 else 50

            return {
                "source":          "stocktwits",
                "msg_count_24h":   len(messages),
                "bull_count":      bull,
                "bear_count":      bear,
                "bull_pct":        bull_pct,
                "watchlist_count": watchlist_count,
                "top_messages":    top_messages,
                "trending":        watchlist_count > 5000,
                "error":           None,
            }
        elif resp.status_code == 404:
            return {"source": "stocktwits", "error": "not_found", "msg_count_24h": 0}
        else:
            return {"source": "stocktwits", "error": f"http_{resp.status_code}", "msg_count_24h": 0}
    except Exception as e:
        return {"source": "stocktwits", "error": str(e), "msg_count_24h": 0}


# ── Reddit ─────────────────────────────────────────────────────────────────────

REDDIT_SUBS = [
    "wallstreetbets",
    "smallstreetbets",
    "stocks",
    "investing",
    "SecurityAnalysis",
    "pennystocks",
    "RobinHoodPennyStocks",
]

_reddit_token: Optional[str] = None
_reddit_token_expiry: Optional[datetime] = None


def _get_reddit_token() -> Optional[str]:
    global _reddit_token, _reddit_token_expiry
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None

    now = datetime.now(timezone.utc)
    if _reddit_token and _reddit_token_expiry and now < _reddit_token_expiry:
        return _reddit_token

    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "MarketDashboard/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            data               = resp.json()
            _reddit_token      = data.get("access_token")
            expires_in         = data.get("expires_in", 3600)
            _reddit_token_expiry = now + timedelta(seconds=expires_in - 60)
            return _reddit_token
    except Exception as e:
        print(f"[social] Reddit auth error: {e}")
    return None


def _search_reddit(ticker: str, token: str, days: int = 1) -> list[dict]:
    """Search Reddit for ticker mentions in relevant subreddits."""
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "MarketDashboard/1.0",
    }
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    results  = []

    # Search across all relevant subs
    subreddits = "+".join(REDDIT_SUBS)
    query      = f"${ticker} OR \"{ticker}\""

    try:
        url  = f"https://oauth.reddit.com/r/{subreddits}/search"
        resp = requests.get(url, headers=headers, params={
            "q":          query,
            "sort":       "new",
            "limit":      25,
            "restrict_sr": True,
            "t":          "week",
        }, timeout=10)

        if resp.status_code == 200:
            posts = resp.json().get("data", {}).get("children", [])
            for p in posts:
                d = p.get("data", {})
                created = d.get("created_utc", 0)
                if created < after_ts:
                    continue
                title   = d.get("title", "")
                body    = d.get("selftext", "")[:300]
                # Filter: must actually mention the ticker
                pattern = rf'\${ticker}\b|\b{ticker}\b'
                if not re.search(pattern, title + " " + body, re.IGNORECASE):
                    continue
                results.append({
                    "title":     title,
                    "body":      body,
                    "subreddit": d.get("subreddit", ""),
                    "score":     d.get("score", 0),
                    "comments":  d.get("num_comments", 0),
                    "url":       f"https://reddit.com{d.get('permalink', '')}",
                    "created":   datetime.fromtimestamp(created, tz=timezone.utc).isoformat(),
                    "flair":     d.get("link_flair_text", ""),
                    "is_dd":     _is_dd_post(title, d.get("link_flair_text", "")),
                })
    except Exception as e:
        print(f"[social] Reddit search error for {ticker}: {e}")

    return results


def _is_dd_post(title: str, flair: str) -> bool:
    """Detect Due Diligence / research posts."""
    dd_keywords = ["dd", "due diligence", "analysis", "thesis", "research",
                   "catalyst", "why i", "bull case", "bear case", "deep dive"]
    title_lower = title.lower()
    flair_lower = (flair or "").lower()
    return any(kw in title_lower or kw in flair_lower for kw in dd_keywords)


def _sentiment_reddit(posts: list[dict]) -> str:
    """Basic keyword sentiment on Reddit posts."""
    positive = ["bull", "buy", "long", "calls", "moon", "squeeze", "breakout",
                "undervalued", "gem", "hidden", "catalyst", "beat", "growth"]
    negative = ["bear", "short", "puts", "overvalued", "dump", "avoid",
                "warning", "fraud", "dilution", "reverse split", "bankruptcy"]
    pos = neg = 0
    for p in posts:
        text = (p["title"] + " " + p["body"]).lower()
        pos += sum(1 for w in positive if w in text)
        neg += sum(1 for w in negative if w in text)
    if pos > neg * 1.5: return "bullish"
    if neg > pos * 1.5: return "bearish"
    return "neutral"


def _fetch_reddit(ticker: str) -> dict:
    token = _get_reddit_token()
    if not token:
        return {
            "source":    "reddit",
            "error":     "no_credentials",
            "mentions_24h": 0,
            "posts":     [],
        }

    try:
        posts_24h = _search_reddit(ticker, token, days=1)
        posts_7d  = _search_reddit(ticker, token, days=7)

        dd_posts   = [p for p in posts_24h if p.get("is_dd")]
        top_posts  = sorted(posts_24h, key=lambda x: x["score"], reverse=True)[:3]

        # Mention spike: 24h vs 7d daily average
        daily_avg_7d = len(posts_7d) / 7
        spike_ratio  = round(len(posts_24h) / daily_avg_7d, 1) if daily_avg_7d > 0 else 0
        is_spiking   = spike_ratio >= 3 and len(posts_24h) >= 3

        return {
            "source":        "reddit",
            "mentions_24h":  len(posts_24h),
            "mentions_7d":   len(posts_7d),
            "daily_avg_7d":  round(daily_avg_7d, 1),
            "spike_ratio":   spike_ratio,
            "is_spiking":    is_spiking,
            "dd_posts":      len(dd_posts),
            "sentiment":     _sentiment_reddit(posts_24h),
            "top_posts":     top_posts,
            "dd_post_list":  dd_posts[:2],
            "error":         None,
        }
    except Exception as e:
        return {"source": "reddit", "error": str(e), "mentions_24h": 0, "posts": []}


# ── News (Alpaca) ─────────────────────────────────────────────────────────────

CATALYST_KEYWORDS = [
    "fda", "approval", "approved", "trial", "phase", "merger", "acquisition",
    "buyout", "takeover", "partnership", "contract", "earnings", "beat",
    "guidance", "raised", "upgrade", "short squeeze", "activist", "insider",
    "patent", "breakthrough", "launch", "awarded", "deal",
]


def _fetch_news_social(ticker: str) -> dict:
    """Extended news fetch with catalyst detection."""
    from news import get_news
    articles = get_news(ticker, limit=10)

    catalysts = []
    sentiments = {"positive": 0, "negative": 0, "neutral": 0}
    for a in articles:
        headline_lower = a.get("headline", "").lower()
        found_cats = [kw for kw in CATALYST_KEYWORDS if kw in headline_lower]
        if found_cats:
            catalysts.append({
                "headline": a.get("headline", ""),
                "keywords": found_cats,
                "published": a.get("published_at", ""),
                "url":       a.get("url", ""),
            })
        s = a.get("sentiment", "neutral")
        sentiments[s] = sentiments.get(s, 0) + 1

    # Recency score — headlines in last 24h are most valuable
    now      = datetime.now(timezone.utc)
    recent   = 0
    for a in articles:
        try:
            pub = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
            if (now - pub).total_seconds() < 86400:
                recent += 1
        except Exception:
            pass

    return {
        "source":         "news",
        "headline_count": len(articles),
        "recent_24h":     recent,
        "catalysts":      catalysts[:3],
        "catalyst_count": len(catalysts),
        "sentiments":     sentiments,
        "top_headlines":  [a.get("headline") for a in articles[:3]],
        "error":          None,
    }


# ── Composite score ───────────────────────────────────────────────────────────

def _composite_score(st: dict, reddit: dict, news: dict) -> dict:
    """
    0-10 composite social intelligence score.

    StockTwits (3 pts):
      - msg_count_24h > 50: +1
      - bull_pct > 60: +1
      - trending (watchlist > 5K): +1

    Reddit (4 pts):
      - mentions_24h >= 3: +1
      - is_spiking (3x daily avg): +1.5
      - dd_posts >= 1: +1
      - sentiment == bullish: +0.5

    News (3 pts):
      - headline_count >= 3: +1
      - recent_24h >= 1: +1
      - catalyst_count >= 1: +1
    """
    score = 0.0
    breakdown = {}

    # StockTwits
    if not st.get("error") or st.get("error") == "not_found":
        st_score = 0
        if (st.get("msg_count_24h") or 0) > 50:
            st_score += 1
        if (st.get("bull_pct") or 50) > 60:
            st_score += 1
        if st.get("trending"):
            st_score += 1
        score += st_score
        breakdown["stocktwits"] = st_score

    # Reddit
    r_score = 0
    if not reddit.get("error") or reddit.get("error") == "no_credentials":
        if (reddit.get("mentions_24h") or 0) >= 3:
            r_score += 1
        if reddit.get("is_spiking"):
            r_score += 1.5
        if (reddit.get("dd_posts") or 0) >= 1:
            r_score += 1
        if reddit.get("sentiment") == "bullish":
            r_score += 0.5
    score += r_score
    breakdown["reddit"] = r_score

    # News
    n_score = 0
    if not news.get("error"):
        if (news.get("headline_count") or 0) >= 3:
            n_score += 1
        if (news.get("recent_24h") or 0) >= 1:
            n_score += 1
        if (news.get("catalyst_count") or 0) >= 1:
            n_score += 1
    score += n_score
    breakdown["news"] = n_score

    score = round(min(10.0, score), 1)

    # Label
    if score >= 7:   label = "HOT"
    elif score >= 5: label = "ACTIVE"
    elif score >= 3: label = "MODERATE"
    else:            label = "QUIET"

    # Alerts — conditions worth Telegram flagging
    alerts = []
    if reddit.get("is_spiking"):
        alerts.append(f"Reddit spike {reddit.get('spike_ratio')}x normal")
    if reddit.get("dd_posts", 0) >= 1:
        alerts.append(f"{reddit['dd_posts']} DD post(s) today")
    if news.get("catalyst_count", 0) >= 1:
        cats = [c["keywords"][0] for c in news.get("catalysts", [])[:2]]
        alerts.append(f"News catalyst: {', '.join(cats)}")
    if st.get("trending"):
        alerts.append("Trending on StockTwits")

    return {
        "score":     score,
        "label":     label,
        "breakdown": breakdown,
        "alerts":    alerts,
    }


# ── Main public function ──────────────────────────────────────────────────────

def get_social_intel(ticker: str) -> dict:
    """
    Fetch and aggregate social intelligence for a single ticker.
    Returns composite score + raw data from all three sources.
    Cached for 4 hours.
    """
    if _is_cached(ticker):
        return _cache[ticker]

    st     = _fetch_stocktwits(ticker)
    time.sleep(0.2)  # be polite to StockTwits
    reddit = _fetch_reddit(ticker)
    news   = _fetch_news_social(ticker)
    comp   = _composite_score(st, reddit, news)

    result = {
        "ticker":      ticker,
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "composite":   comp,
        "stocktwits":  st,
        "reddit":      reddit,
        "news":        news,
    }

    _cache[ticker]    = result
    _cache_ts[ticker] = datetime.now(timezone.utc)
    return result


def batch_social_intel(tickers: list[str], max_tickers: int = 30) -> dict[str, dict]:
    """
    Fetch social intel for multiple tickers.
    Capped at max_tickers to stay within rate limits.
    Prioritise by passing in tickers already sorted by signal_score.
    """
    results = {}
    for t in tickers[:max_tickers]:
        try:
            results[t] = get_social_intel(t)
            time.sleep(0.3)  # rate limit buffer
        except Exception as e:
            print(f"[social] Error fetching {t}: {e}")
    return results


def enrich_signals_with_social(signals: list[dict], max_tickers: int = 30) -> list[dict]:
    """
    Enrich a list of signal dicts with social intel.
    Fetches for top max_tickers by signal_score, marks rest as not fetched.
    """
    tickers_to_fetch = [s["ticker"] for s in signals[:max_tickers]]
    social_data      = batch_social_intel(tickers_to_fetch)

    for s in signals:
        t    = s["ticker"]
        data = social_data.get(t)
        if data:
            comp = data["composite"]
            s["social_score"]   = comp["score"]
            s["social_label"]   = comp["label"]
            s["social_alerts"]  = comp["alerts"]
            s["social_detail"]  = data
            # Combined score: 70% technical, 30% social
            tech_score   = s.get("signal_score", 5)
            s["combined_score"] = round(tech_score * 0.7 + comp["score"] * 0.3, 1)
        else:
            s["social_score"]   = None
            s["social_label"]   = None
            s["social_alerts"]  = []
            s["combined_score"] = s.get("signal_score", 5)

    # Re-sort by combined score
    signals.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
    return signals
