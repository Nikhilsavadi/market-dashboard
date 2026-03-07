"""
polygon_client.py
-----------------
Polygon.io fetch layer for the $29 Starter plan.

Key design decisions:
  - requests.Session with HTTPAdapter for connection pooling
    → reuses TCP connections across concurrent workers (big latency win)
  - Retry logic on every call: 3 attempts with backoff on 429/5xx/timeout
  - API key read at call time (not import time) so Railway env vars work
  - ThreadPoolExecutor with 15 workers — safe ceiling for Starter plan
  - Drop-in replacement for fetch_bars_batch() — same signature, same output

Environment variable:
  POLYGON_API_KEY=your_key_here   (set in Railway → Variables)

Fallback:
  If POLYGON_API_KEY is not set, fetch_utils.py falls back to yfinance.
"""

import os
import time
import random
import requests
import pandas as pd
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL    = "https://api.polygon.io"
MAX_WORKERS = 15
_MS_TO_NS   = 1_000_000   # Polygon timestamps are milliseconds UTC


# ── HTTP session with connection pooling ───────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total            = 3,
        backoff_factor   = 0.5,
        status_forcelist = [500, 502, 503, 504],
        allowed_methods  = ["GET"],
        raise_on_status  = False,
    )
    adapter = HTTPAdapter(
        max_retries      = retry,
        pool_connections = MAX_WORKERS + 2,
        pool_maxsize     = MAX_WORKERS + 2,
    )
    session.mount("https://", adapter)
    return session


_SESSION = _make_session()


# ── Core GET with application-level retry ─────────────────────────────────────

def _get(endpoint: str, params: dict = None, timeout: int = 20, retries: int = 3) -> Optional[dict]:
    """Authenticated GET to Polygon REST API with retry + backoff."""
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        return None

    url = BASE_URL + endpoint
    p   = {"apiKey": api_key, **(params or {})}

    for attempt in range(1, retries + 1):
        try:
            r = _SESSION.get(url, params=p, timeout=timeout)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                wait = 10 * attempt + random.uniform(0, 3)
                print(f"[polygon] 429 rate limit attempt {attempt} — waiting {wait:.0f}s")
                time.sleep(wait)
                continue

            if r.status_code == 403:
                print(f"[polygon] 403 Forbidden on {endpoint} — check API key / plan")
                return None

            if r.status_code >= 500:
                wait = 5 * attempt
                print(f"[polygon] {r.status_code} server error attempt {attempt} — retrying in {wait}s")
                time.sleep(wait)
                continue

            return None  # other 4xx — bad request, don't retry

        except requests.exceptions.Timeout:
            wait = 5 * attempt
            print(f"[polygon] Timeout attempt {attempt} on {endpoint} — retrying in {wait}s")
            time.sleep(wait)

        except requests.exceptions.ConnectionError as e:
            wait = 5 * attempt
            print(f"[polygon] Connection error attempt {attempt}: {e} — retrying in {wait}s")
            time.sleep(wait)

        except Exception as e:
            print(f"[polygon] Unexpected error on {endpoint}: {e}")
            return None

    print(f"[polygon] {endpoint} failed after {retries} attempts")
    return None


# ── DataFrame conversion ───────────────────────────────────────────────────────

def _to_df(results: list, min_rows: int = 1) -> Optional[pd.DataFrame]:
    """Convert Polygon aggregate bar result list → normalised DataFrame."""
    if not results or len(results) < min_rows:
        return None
    try:
        df = pd.DataFrame(results)
        df["date"] = (
            pd.to_datetime(df["t"] * _MS_TO_NS)
            .dt.tz_localize("UTC")
            .dt.tz_convert(None)
            .dt.normalize()
        )
        df = df.set_index("date").sort_index()
        df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                                 "c": "close", "v": "volume"})
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].dropna(how="all")
        return df if len(df) >= min_rows else None
    except Exception as e:
        print(f"[polygon] DataFrame conversion error: {e}")
        return None


# ── Per-ticker fetch (called concurrently) ────────────────────────────────────

def _fetch_one(ticker: str, from_date: str, to_date: str,
               interval: str = "day", min_rows: int = 20) -> tuple:
    """Fetch aggregate bars for a single ticker. Returns (ticker, df_or_None)."""
    endpoint = f"/v2/aggs/ticker/{ticker}/range/1/{interval}/{from_date}/{to_date}"
    data = _get(endpoint, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if not data or data.get("resultsCount", 0) == 0:
        return ticker, None
    return ticker, _to_df(data.get("results", []), min_rows=min_rows)


# ── Main concurrent fetch ──────────────────────────────────────────────────────

def fetch_bars(tickers: list, days: int = 380, interval: str = "day",
               min_rows: int = 20, max_workers: int = MAX_WORKERS,
               label: str = "polygon") -> dict:
    """
    Fetch OHLCV bars for a list of tickers using concurrent Polygon API calls.
    No batching, no inter-batch sleeps — connection pooling + ThreadPoolExecutor.
    Returns dict[ticker -> DataFrame], same interface as fetch_bars_batch().
    """
    if not os.environ.get("POLYGON_API_KEY"):
        raise EnvironmentError("POLYGON_API_KEY not set")

    to_date   = date.today().isoformat()
    from_date = (date.today() - timedelta(days=days + 10)).isoformat()

    all_data: dict = {}
    failed:   list = []
    t0 = time.time()

    print(f"[{label}] Fetching {len(tickers)} tickers ({interval}, {days}d) · {max_workers} workers")

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=label) as ex:
        futures = {ex.submit(_fetch_one, t, from_date, to_date, interval, min_rows): t
                   for t in tickers}
        done = 0
        for future in as_completed(futures):
            try:
                ticker, df = future.result()
            except Exception as e:
                ticker = futures[future]
                print(f"[{label}] Worker error {ticker}: {e}")
                failed.append(ticker)
                done += 1
                continue

            done += 1
            if df is not None:
                all_data[ticker] = df
            else:
                failed.append(ticker)

            if done % 200 == 0 or done == len(tickers):
                elapsed = time.time() - t0
                rate    = done / elapsed if elapsed > 0 else 0
                print(f"[{label}]   {done}/{len(tickers)} · {len(all_data)} OK "
                      f"· {len(failed)} failed · {elapsed:.0f}s · {rate:.0f}/s")

    elapsed = round(time.time() - t0, 1)
    print(f"[{label}] Done: {len(all_data)}/{len(tickers)} in {elapsed}s")
    if failed:
        print(f"[{label}] Failed ({len(failed)}): {failed[:8]}"
              + ("..." if len(failed) > 8 else ""))
    return all_data


# ── Weekly bars wrapper ────────────────────────────────────────────────────────

def fetch_weekly_bars(tickers: list, weeks: int = 104,
                      min_rows: int = 10, max_workers: int = MAX_WORKERS) -> dict:
    """Weekly OHLCV bars via Polygon week-interval aggregates."""
    return fetch_bars(tickers, days=weeks * 7 + 14, interval="week",
                      min_rows=min_rows, max_workers=max_workers,
                      label="polygon/weekly")


# ── Drop-in shim matching fetch_bars_batch() signature ────────────────────────

def fetch_bars_batch_polygon(tickers: list, period: str = "380d",
                              interval: str = "1d", start: str = None,
                              end: str = None, min_rows: int = 20,
                              **kwargs) -> dict:
    """
    Drop-in replacement for fetch_utils.fetch_bars_batch().
    Identical signature and return type — no callers need to change.
    """
    label = kwargs.get("label", "polygon")
    if start and end:
        try:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        except Exception:
            days = _period_to_days(period)
    else:
        days = _period_to_days(period)

    return fetch_bars(tickers, days=days, interval=_map_interval(interval),
                      min_rows=min_rows, label=label)


# ── Grouped daily — all US stocks in one call ─────────────────────────────────

def grouped_daily(target_date: str = None) -> dict:
    """
    Single API call returning OHLCV for every US stock on a given date.
    Returns dict[ticker -> {open, high, low, close, volume}]
    """
    if target_date is None:
        d = date.today()
        while d.weekday() >= 5:   # step back from weekend to Friday
            d -= timedelta(days=1)
        target_date = d.isoformat()

    print(f"[polygon] Grouped daily -> {target_date}")
    t0   = time.time()
    data = _get(f"/v2/aggs/grouped/locale/us/market/stocks/{target_date}",
                {"adjusted": "true"})
    if not data or not data.get("results"):
        print(f"[polygon] Grouped daily: no results for {target_date}")
        return {}

    out = {r["T"]: {"open": r.get("o"), "high": r.get("h"), "low": r.get("l"),
                     "close": r.get("c"), "volume": r.get("v")}
           for r in data["results"] if r.get("T")}

    print(f"[polygon] Grouped daily: {len(out)} tickers in {time.time()-t0:.1f}s")
    return out


# ── Health check ───────────────────────────────────────────────────────────────

def check_connection() -> dict:
    """Verify Polygon API key and connectivity. Called by /api/polygon-status."""
    if not os.environ.get("POLYGON_API_KEY"):
        return {"ok": False, "error": "POLYGON_API_KEY not set in environment"}

    from_date = (date.today() - timedelta(days=5)).isoformat()
    ticker, df = _fetch_one("SPY", from_date, date.today().isoformat(), "day", 1)

    if df is not None and not df.empty:
        return {
            "ok":     True,
            "test":   f"SPY: {len(df)} bars fetched OK",
            "latest": str(df.index[-1].date()),
            "close":  round(float(df["close"].iloc[-1]), 2),
        }
    return {"ok": False,
            "error": "SPY fetch returned no data — check API key or Polygon status"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_to_days(period: str) -> int:
    p = period.lower().strip()
    if p.endswith("d"):   return int(p[:-1])
    if p.endswith("mo"):  return int(p[:-2]) * 30
    if p.endswith("y"):   return int(p[:-1]) * 365
    return 380


def _map_interval(interval: str) -> str:
    return {"1d": "day", "1wk": "week", "1mo": "month"}.get(interval, "day")
