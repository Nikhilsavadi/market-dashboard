"""
fetch_utils.py
--------------
Shared fetch helpers — routes to Polygon.io when POLYGON_API_KEY is set,
falls back to yfinance otherwise.

Migration path:
  1. Set POLYGON_API_KEY in Railway env vars
  2. fetch_bars_batch() automatically uses Polygon — no other code changes needed
  3. yfinance stays as fallback if key is missing

Yfinance notes (kept for fallback):

Key changes in yfinance 1.2.0 vs 0.2.x:
  - Column names are Title Case: Close, High, Low, Open, Volume (not lowercase)
  - multi_level_index=True by default — always returns MultiIndex for multi-ticker
  - Single ticker with multi_level_index=True also returns MultiIndex (ticker, field)
  - Use multi_level_index=False for single ticker to get flat columns

We normalise everything to lowercase column names so the rest of the codebase
doesn't need to change.
"""

import time
import warnings
import pandas as pd
import yfinance as yf

def _clean_ticker(t: str) -> str:
    """Normalise ticker for Yahoo Finance: dots → hyphens."""
    return t.replace(".", "-")


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, strip tz, sort index."""
    df = df.copy()
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    df.index   = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna(how="all").sort_index()


def _extract_ticker(raw: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """
    Extract a single ticker from a multi-ticker yf.download result.
    Handles both MultiIndex (new default) and flat columns (single ticker fallback).
    Returns normalised DataFrame or None if ticker not found / too short.
    """
    if raw is None or raw.empty:
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        try:
            # Level 0 = field (Close/High/...), Level 1 = ticker
            # OR Level 0 = ticker, Level 1 = field depending on group_by
            # yfinance 1.x default: level 0 = Price, level 1 = Ticker
            df = raw.xs(ticker, axis=1, level=1).copy()
            return _normalise(df)
        except (KeyError, Exception):
            return None
    else:
        # Flat columns — only valid if single ticker was requested
        df = raw.copy()
        df.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in df.columns]
        df.index   = pd.to_datetime(df.index).tz_localize(None)
        return df.dropna(how="all").sort_index()


def fetch_bars_batch(
    tickers: list,
    period: str = "380d",
    interval: str = "1d",
    start: str = None,
    end: str = None,
    min_rows: int = 20,
    batch_size: int = 50,
    sleep_between: float = 1.2,  # was 2.0 — safe floor with threads=False
    label: str = "fetch",
) -> dict:
    """
    Download OHLCV bars for a list of tickers in batches.

    Routes to Polygon.io when POLYGON_API_KEY env var is set (fast, no rate limits).
    Falls back to yfinance batch fetcher when key is absent.

    Returns dict[ticker -> DataFrame] with lowercase columns.
    """
    # ── Provider routing: Polygon → yfinance ────────────────────────────────
    # Set POLYGON_API_KEY in Railway env vars to activate Polygon.
    # Falls back to yfinance automatically if key is absent.
    import os

    if os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_bars_batch_polygon
            return fetch_bars_batch_polygon(
                tickers, period=period, interval=interval,
                start=start, end=end, min_rows=min_rows, label=label,
            )
        except Exception as e:
            print(f"[fetch_utils] Polygon fetch failed ({e}) — falling back to yfinance")

    # ── yfinance fallback ─────────────────────────────────────────────────────
    all_data      = {}
    total_batches = -(-len(tickers) // batch_size)

    download_kwargs = dict(
        interval          = interval,
        auto_adjust       = True,
        progress          = False,
        threads           = False,       # sequential within batch avoids burst throttle
        multi_level_index = True,        # always get MultiIndex for consistent parsing
    )
    if start and end:
        download_kwargs["start"] = start
        download_kwargs["end"]   = end
    else:
        download_kwargs["period"] = period

    import random

    # Normalise tickers: Yahoo uses hyphens not dots (e.g. BRK-B not BRK.B)
    tickers   = [_clean_ticker(t) for t in tickers]
    failed_rl = []   # rate-limited tickers — retried individually after all batches

    for i in range(0, len(tickers), batch_size):
        batch     = tickers[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"[{label}] Batch {batch_num}/{total_batches} ({len(batch)} tickers)...")

        raw      = None
        rate_hit = False
        for attempt in range(3):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    raw = yf.download(batch, **download_kwargs)
                if raw is not None and not raw.empty:
                    break
                wait = 8 + random.uniform(0, 4)
                print(f"[{label}]   Attempt {attempt+1}: empty — waiting {wait:.0f}s")
                time.sleep(wait)
            except Exception as e:
                err = str(e)
                if any(x in err for x in ("RateLimit", "Too Many", "429", "rate limit")):
                    rate_hit = True
                    wait = 35 + random.uniform(0, 10)
                    print(f"[{label}]   Attempt {attempt+1}: RATE LIMITED — waiting {wait:.0f}s")
                    time.sleep(wait)
                else:
                    print(f"[{label}]   Attempt {attempt+1} error: {e}")
                    time.sleep(6)

        if raw is None or raw.empty:
            if rate_hit:
                failed_rl.extend(batch)
                print(f"[{label}]   Batch {batch_num}: rate limited — {len(batch)} tickers queued for retry")
                time.sleep(15)
            else:
                print(f"[{label}]   Batch {batch_num}: failed after 3 attempts — skipping")
                time.sleep(3)
            continue

        count_before = len(all_data)
        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in batch:
                try:
                    df = raw.xs(ticker, axis=1, level=1).copy()
                    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
                    df.index   = pd.to_datetime(df.index).tz_localize(None)
                    df = df.dropna(how="all").sort_index()
                    if len(df) >= min_rows:
                        all_data[ticker] = df
                except Exception:
                    pass
        else:
            t = batch[0]
            raw.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in raw.columns]
            raw.index   = pd.to_datetime(raw.index).tz_localize(None)
            raw = raw.dropna(how="all").sort_index()
            if len(raw) >= min_rows:
                all_data[t] = raw

        added = len(all_data) - count_before
        print(f"[{label}]   Batch {batch_num}: {added}/{len(batch)} tickers OK")
        time.sleep(sleep_between + random.uniform(0, 0.8))

    # ── Individual retry for rate-limited tickers ─────────────────────────────
    if failed_rl:
        failed_rl = [t for t in dict.fromkeys(failed_rl) if t not in all_data]
        print(f"[{label}] Retrying {len(failed_rl)} rate-limited tickers individually...")
        time.sleep(20)
        for ticker in failed_rl:
            if ticker in all_data:
                continue
            try:
                kw = {**download_kwargs, "multi_level_index": False}
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df = yf.download([ticker], **kw)
                if df is not None and not df.empty:
                    df.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in df.columns]
                    df.index   = pd.to_datetime(df.index).tz_localize(None)
                    df = df.dropna(how="all").sort_index()
                    if len(df) >= min_rows:
                        all_data[ticker] = df
                        print(f"[{label}]   Retry OK: {ticker}")
            except Exception as e:
                if any(x in str(e) for x in ("RateLimit", "Too Many", "429")):
                    print(f"[{label}]   Retry {ticker}: still rate limited — skipping")
                    time.sleep(12)
                else:
                    print(f"[{label}]   Retry {ticker}: {e}")
            time.sleep(5 + random.uniform(0, 2))

    print(f"[{label}] Done: {len(all_data)}/{len(tickers)} tickers fetched")
    return all_data
