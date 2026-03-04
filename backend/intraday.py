"""
intraday.py
-----------
Fetches intraday data from Alpaca during market hours.
Calculates RVOL (relative volume at current time of day).
Runs as a supplementary scan 9:45am–3:45pm ET on weekdays.
"""

import os
from datetime import datetime, timedelta, timezone, date
import pandas as pd
from typing import Optional

import yfinance as yf
from watchlist import ALL_TICKERS


def is_market_hours() -> bool:
    """True if current time is within US market hours (9:30am–4pm ET)."""
    now_et = datetime.now(timezone.utc) - timedelta(hours=5)  # rough ET offset
    if now_et.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def calculate_rvol(client, tickers: list) -> dict:
    """
    Calculate RVOL via yfinance: today's volume vs 20-day avg.
    Uses daily bars — intraday minute data not available on yfinance free tier.
    `client` param kept for API compatibility but unused.
    """
    now_et = datetime.now(timezone.utc) - timedelta(hours=5)
    market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    elapsed_mins = max(1, int((now_et - market_open_time).total_seconds() / 60))
    total_mins = 390
    pct_of_day = round(min(elapsed_mins / total_mins, 1.0), 3)

    results = {}
    batch_size = 100

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            raw = yf.download(batch, period="25d", interval="1d",
                              auto_adjust=True, progress=False, threads=True)
            if raw.empty:
                continue

            import pandas as pd
            if isinstance(raw.columns, pd.MultiIndex):
                for ticker in batch:
                    try:
                        df = raw.xs(ticker, axis=1, level=1).dropna(how="all")
                        if len(df) < 2:
                            continue
                        today_vol     = int(df["Volume"].iloc[-1])
                        avg_daily_vol = float(df["Volume"].iloc[:-1].tail(20).mean())
                        if avg_daily_vol <= 0:
                            continue
                        expected_vol = avg_daily_vol * pct_of_day
                        rvol = round(today_vol / expected_vol, 2) if expected_vol > 0 else 0
                        results[ticker] = {
                            "rvol": rvol, "today_vol": today_vol,
                            "avg_daily_vol": int(avg_daily_vol),
                            "pct_of_day": pct_of_day, "elapsed_mins": elapsed_mins,
                        }
                    except Exception:
                        pass
            else:
                t = batch[0]
                raw = raw.dropna(how="all")
                if len(raw) >= 2:
                    today_vol     = int(raw["Volume"].iloc[-1])
                    avg_daily_vol = float(raw["Volume"].iloc[:-1].tail(20).mean())
                    if avg_daily_vol > 0:
                        expected_vol = avg_daily_vol * pct_of_day
                        rvol = round(today_vol / expected_vol, 2) if expected_vol > 0 else 0
                        results[t] = {
                            "rvol": rvol, "today_vol": today_vol,
                            "avg_daily_vol": int(avg_daily_vol),
                            "pct_of_day": pct_of_day, "elapsed_mins": elapsed_mins,
                        }
        except Exception as e:
            print(f"[intraday] RVOL batch error: {e}")

    return results


def enrich_with_rvol(stocks: list[dict], rvol_data: dict) -> list[dict]:
    """Add RVOL data to stock signal dicts."""
    for s in stocks:
        ticker = s.get("ticker")
        if ticker in rvol_data:
            s["rvol"] = rvol_data[ticker].get("rvol")
            s["rvol_pct_of_day"] = rvol_data[ticker].get("pct_of_day")
        else:
            s["rvol"] = None
            s["rvol_pct_of_day"] = None
    return stocks
