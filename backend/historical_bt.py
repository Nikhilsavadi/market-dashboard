"""
historical_bt.py
----------------
Reconstructs historical signals day-by-day over the last N months.
Strict look-ahead bias prevention: when processing day D, only uses
data from days 0..D. Exit simulation uses only days D+1 onwards.

Pipeline:
1. For each trading day in lookback window
2. Slice all bars up to that day
3. Re-run screener exactly as live
4. If signal triggered → record it
5. Walk forward from D+1 to simulate exit
6. Store signals + trades to DB
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Optional
import time

from screener import analyse_stock, calculate_1y_return, _calculate_weighted_rs_score, is_long_signal, is_short_signal
from base_detector import detect_base, calculate_atr
from sector_rs import calculate_sector_rs, get_sector
from database import (
    init_backtest_tables, save_historical_signals,
    save_historical_trades, get_conn
)


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_PARAMS = {
    # Daily signal exits
    "stop_atr_mult":    1.5,
    "max_hold_days":    90,         # trailing MA50 exit — let winners run
    "ma21_cross_exit":  False,
    "trail_ma":         "ma50",     # exit trigger: trailing MA50 with 1% buffer
    "entry_types":      ["next_open"],  # realistic only — signal-close is look-ahead
    "slippage":         0.001,      # 0.1% per leg (0.2% round-trip)
    # Weekly signal exits — wider stops, longer rope, bigger targets
    "w_stop_atr_mult":  2.5,        # wider stop: weekly noise larger than daily
    "w_t1_atr_mult":    3.0,        # first target further out
    "w_t2_atr_mult":    6.0,        # let weekly winners run
    "w_t3_atr_mult":   10.0,        # extended target for trend continuation
    "w_max_hold_days":  50,         # weekly trends take 6-10 weeks to play out
    # Regime gate — signals below this market_score are saved but NOT traded
    # 48 = NEUTRAL threshold (same as live dashboard gate)
    # Set to 0 to disable gating and simulate all signals
    "regime_gate":      55,
    # Quality gates — signals below these thresholds are skipped entirely (not saved to DB)
    "min_rs":           85,
    "min_base_score":   2,
    "min_vol_ratio":    1.1,
    "allowed_signal_types": ["MA21", "MA50", "W_EMA10", "RECOVERY"],
}

MIN_BARS_HISTORY = 20   # need at least 20 bars before starting to scan (MA warmup)
MARKET_ETFS = ["SPY", "QQQ", "IWM"]


# ── Market score on a given day ───────────────────────────────────────────────

def _market_score_on_day(bars_data: dict, day_idx: int) -> int:
    """Calculate market health score using only data up to day_idx."""
    scores = []
    for etf in MARKET_ETFS:
        if etf not in bars_data:
            continue
        closes = bars_data[etf]["close"].iloc[:day_idx + 1]
        if len(closes) < 21:
            continue
        price = float(closes.iloc[-1])
        ma21  = float(closes.iloc[-21:].mean()) if len(closes) >= 21  else None
        ma50  = float(closes.iloc[-50:].mean()) if len(closes) >= 50  else None
        ma200 = float(closes.iloc[-200:].mean()) if len(closes) >= 200 else None
        chg_1m = (price - float(closes.iloc[-21])) / float(closes.iloc[-21]) * 100 if len(closes) > 21 else 0
        s = 50
        if ma21  and price > ma21:  s += 15
        if ma50  and price > ma50:  s += 15
        if ma200 and price > ma200: s += 20
        s += max(-10, min(10, chg_1m))
        scores.append(max(0, min(100, s)))
    return round(sum(scores) / len(scores)) if scores else 50


# ── Single day signal scan ────────────────────────────────────────────────────

def _is_weekly_signal(result: dict) -> bool:
    """
    A signal qualifies as a weekly setup when:
      1. Price is above wEMA10 (weekly uptrend intact)
      2. wEMA10 is above wEMA40 OR only wEMA10 available (trend confirmed)
      3. Price is within 1 ATR of wEMA10 (touching/hugging the weekly MA)
      4. wEMA10 slope is positive (trend accelerating, not rolling over)

    This is a higher-timeframe version of the daily MA touch.
    Weekly signals have wider natural stops (weekly ATR) and longer
    hold times — they're typically fewer but higher conviction.
    """
    if not result:
        return False
    w_stack_ok        = result.get("w_stack_ok", False)
    within_1atr_wema10 = result.get("within_1atr_wema10", False)
    w_ema10_slope      = result.get("w_ema10_slope")
    w_ema10            = result.get("w_ema10")

    if not w_stack_ok:
        return False
    if not within_1atr_wema10:
        return False
    if w_ema10 is None:
        return False
    # Slope must be positive — don't catch falling knives on the weekly
    if w_ema10_slope is not None and w_ema10_slope <= 0:
        return False
    return True


def _scan_day(
    trading_dates: pd.DatetimeIndex,
    day_idx: int,
    bars_data: dict,
    etf_tickers: set,
    params: dict,
    ticker_positions: dict = None,  # pre-computed {ticker: sorted index list} — avoids O(n²)
) -> list[dict]:
    """
    Run screener for a single historical day.
    Returns list of signals found on that day.
    STRICT: only uses bars_data sliced to [:day_idx+1]
    """
    import bisect
    signal_date = trading_dates[day_idx].date().isoformat()
    cutoff_date = trading_dates[day_idx]

    # Slice all bars up to this day (inclusive) — no future data
    sliced = {}
    for ticker, df in bars_data.items():
        if ticker_positions and ticker in ticker_positions:
            idx_list = ticker_positions[ticker]
        else:
            idx_list = df.index.tolist()
        pos = bisect.bisect_right(idx_list, cutoff_date)
        if pos >= 21:
            sliced[ticker] = df.iloc[:pos]

    if not sliced:
        return []

    # SPY closes for Mansfield RS calculation — sliced to this day
    spy_closes_sliced = None
    if "SPY" in sliced:
        spy_closes_sliced = sliced["SPY"]["close"]

    # RS universe — weighted outperformance vs SPY (matches live scanner exactly)
    all_1y_returns = []
    for ticker, df in sliced.items():
        if ticker in etf_tickers:
            continue
        if spy_closes_sliced is not None:
            score = _calculate_weighted_rs_score(df["close"], spy_closes_sliced)
        else:
            score = calculate_1y_return(df["close"])  # fallback if no SPY
        if score is not None:
            all_1y_returns.append(score)

    # Sector RS — using sliced data
    sector_rs = calculate_sector_rs(sliced)

    # Market score on this day
    market_score = _market_score_on_day(bars_data, day_idx)

    # Pre-compute next day date once
    next_date = trading_dates[day_idx + 1] if day_idx + 1 < len(trading_dates) else None

    def _analyse_one(item):
        ticker, df = item
        if ticker in etf_tickers:
            return None
        try:
            result = analyse_stock(ticker, df, all_1y_returns, spy_closes=spy_closes_sliced)
        except Exception:
            return None
        if not result:
            return None

        is_long = is_long_signal(result)
        is_short = is_short_signal(result)
        if not is_long and not is_short:
            return None

        base_info = detect_base(df)
        sector    = get_sector(ticker)
        s_data    = sector_rs.get(sector, {})

        next_open = None
        if next_date is not None and ticker in bars_data:
            next_row = bars_data[ticker][bars_data[ticker].index == next_date]
            if not next_row.empty:
                next_open = float(next_row["open"].iloc[0])

        price       = result["price"]
        signal_type = (result.get("bouncing_from") or "MA") if is_long else "SHORT"

        # Breakout entry levels — 20-day high and base low for stop
        highs_20 = df["high"].iloc[-20:] if len(df) >= 20 else df["high"]
        lows_15  = df["low"].iloc[-15:]  if len(df) >= 15 else df["low"]
        breakout_price = round(float(highs_20.max()) * 1.005, 4)  # 20d high + 0.5% buffer
        base_low       = round(float(lows_15.min()), 4)             # lowest low of base

        return {
            "_is_long": is_long, "_is_short": is_short, "_result": result,
            "ticker": ticker, "signal_date": signal_date, "signal_type": signal_type, "price": price,
            "entry_close": price, "entry_next_open": next_open,
            "breakout_price": breakout_price, "base_low": base_low,
            "ma10": result.get("ma10"), "ma21": result.get("ma21"),
            "ma50": result.get("ma50"), "vcs": result.get("vcs"),
            "rs": result.get("rs"), "vol_ratio": result.get("vol_ratio"),
            "atr": result.get("atr"), "base_score": base_info.get("base_score", 0),
            "base_type": base_info.get("base_type", "none"),
            "vcp_stages": base_info.get("vcp_stages", 0), "sector": sector,
            "sector_rs_1m": s_data.get("rs_vs_spy_1m"), "market_score": market_score,
            "pct_from_ma21": result.get("pct_from_ma21"), "is_short": is_short,
            "day_of_week":   pd.Timestamp(signal_date).strftime("%a").upper(),
            "w_stack_ok":         int(bool(result.get("w_stack_ok", False))),
            "w_ema10":            result.get("w_ema10"),
            "w_ema40":            result.get("w_ema40"),
            "w_ema10_slope":      result.get("w_ema10_slope"),
            "w_above_ema10":      int(bool(result.get("w_above_ema10", False))),
            "w_above_ema40":      int(bool(result.get("w_above_ema40", False))),
            "within_1atr_wema10": int(bool(result.get("within_1atr_wema10", False))),
            "is_weekly_signal":   int(_is_weekly_signal(result)),
        }

    from concurrent.futures import ThreadPoolExecutor
    signals_raw = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(_analyse_one, sliced.items()):
            if r is not None:
                signals_raw.append(r)

    signals = signals_raw

    # ── Weekly signal scan ────────────────────────────────────────────────────
    # Detect weekly wEMA10 touches independently of daily signals.
    # These fire ~1-2x per month per stock vs daily which fires daily.
    # Only runs on Fridays (or the last trading day of the week) — weekly candle closes.
    is_friday = trading_dates[day_idx].weekday() == 4
    is_last_day_of_week = (
        day_idx + 1 >= len(trading_dates) or
        trading_dates[day_idx + 1].weekday() == 0  # next day is Monday
    )
    if is_friday or is_last_day_of_week:
        weekly_signals = _scan_weekly_day(
            sliced, etf_tickers, all_1y_returns, spy_closes_sliced,
            signal_date, market_score, sector_rs, next_date, bars_data
        )
        signals = signals + weekly_signals

    # ── Capitulation recovery scan ─────────────────────────────────────────
    recovery_signals = _scan_recovery_day(
        sliced, etf_tickers, signal_date, market_score, next_date, bars_data
    )
    signals = signals + recovery_signals

    return signals


# ── Weekly signal scanner ─────────────────────────────────────────────────────

def _scan_weekly_day(
    sliced: dict,
    etf_tickers: set,
    all_1y_returns: list,
    spy_closes_sliced,
    signal_date: str,
    market_score: int,
    sector_rs: dict,
    next_date,
    bars_data: dict,
) -> list[dict]:
    """
    Scan for weekly wEMA10 touch signals using the Friday close.
    Each ticker's daily bars are resampled to weekly candles and checked
    for an ATR-based touch of the wEMA10, with wEMA10 > wEMA40 (uptrend).

    These are higher-conviction, lower-frequency signals (~1-3/month per stock).
    Stop is placed 1.5x weekly ATR below wEMA10 — wider than daily but cleaner R:R.
    """
    from screener import (
        calculate_mansfield_rs, _calculate_weighted_rs_score,
        detect_ma_touch_atr, calculate_atr_series
    )
    from sector_rs import get_sector

    weekly_signals = []

    for ticker, df in sliced.items():
        if ticker in etf_tickers:
            continue
        if len(df) < 60:  # need at least 12 weekly bars
            continue

        try:
            # Resample to weekly (Friday close)
            wdf = df.resample("W-FRI").agg({
                "open": "first", "high": "max",
                "low": "min", "close": "last", "volume": "sum"
            }).dropna()

            if len(wdf) < 15:
                continue

            wc = wdf["close"]
            price = float(wc.iloc[-1])

            # Weekly EMAs
            wema10_series = wc.ewm(span=10, adjust=False).mean()
            wema40_series = wc.ewm(span=40, adjust=False).mean()
            wema10 = float(wema10_series.iloc[-1])
            wema40 = float(wema40_series.iloc[-1]) if len(wc) >= 40 else None

            # Must be in weekly uptrend: price > wEMA10 > wEMA40
            if price <= wema10:
                continue
            if wema40 is not None and wema10 <= wema40:
                continue

            # wEMA10 slope must be rising
            if len(wema10_series) >= 2:
                wema10_slope = float(wema10_series.iloc[-1] - wema10_series.iloc[-2])
                if wema10_slope <= 0:
                    continue
            else:
                continue

            # Weekly ATR
            w_highs = wdf["high"] if "high" in wdf.columns else wc
            w_lows  = wdf["low"]  if "low"  in wdf.columns else wc
            w_atr_series = calculate_atr_series(wdf)
            if w_atr_series is None or len(w_atr_series) == 0:
                continue
            w_atr = float(w_atr_series.iloc[-1])
            if w_atr <= 0:
                continue

            # ATR-based touch: price within [0.2, 1.5] weekly ATRs of wEMA10
            # Tighter upper bound than daily — weekly touch must be a real pullback
            touched = detect_ma_touch_atr(price, wema10, w_atr, 0.2, 1.5)
            if not touched:
                continue

            # Volume confirmation: this week's volume should be below avg (supply dry-up)
            wv = wdf["volume"] if "volume" in wdf.columns else None
            vol_ok = True
            if wv is not None and len(wv) >= 10:
                avg_wvol = float(wv.iloc[-10:].mean())
                this_wvol = float(wv.iloc[-1])
                vol_ok = this_wvol < avg_wvol * 1.2  # not a high-volume selloff week

            if not vol_ok:
                continue

            # RS check — must still be a leading stock
            rs = calculate_mansfield_rs(df["close"], spy_closes_sliced, all_1y_returns) if spy_closes_sliced is not None else 50
            if rs < 70:
                continue

            # Next open for entry
            next_open = None
            if next_date is not None and ticker in bars_data:
                next_row = bars_data[ticker][bars_data[ticker].index == next_date]
                if not next_row.empty:
                    next_open = float(next_row["open"].iloc[0])

            sector = get_sector(ticker)
            s_data = sector_rs.get(sector, {})

            # Daily ATR for position sizing / signal compatibility
            daily_atr_series = calculate_atr_series(df)
            daily_atr = float(daily_atr_series.iloc[-1]) if daily_atr_series is not None and len(daily_atr_series) > 0 else w_atr

            weekly_signals.append({
                "_is_long":    True,
                "_is_short":   False,
                "_result":     {},
                "ticker":      ticker,
                "signal_date": signal_date,
                "signal_type": "W_EMA10",    # distinct type for analysis
                "price":       round(price, 4),
                "entry_close": round(price, 4),
                "entry_next_open": next_open,
                "ma10":  None, "ma21": None, "ma50": None,
                "vcs":   None,
                "rs":    rs,
                "vol_ratio": None,
                "atr":   round(daily_atr, 4),
                "base_score": 0, "base_type": "weekly", "vcp_stages": 0,
                "sector": sector,
                "sector_rs_1m": s_data.get("rs_vs_spy_1m"),
                "market_score": market_score,
                "pct_from_ma21": None,
                "is_short": False,
                # Weekly-specific fields
                "w_stack_ok":         1,
                "w_ema10":            round(wema10, 4),
                "w_ema40":            round(wema40, 4) if wema40 else None,
                "w_ema10_slope":      round(wema10_slope, 4),
                "w_above_ema10":      1,
                "within_1atr_wema10": 1,
                "is_weekly_signal":   1,
            })

        except Exception:
            continue

    return weekly_signals


# ── Capitulation recovery scanner ──────────────────────────────────────────────

def _scan_recovery_day(
    sliced: dict,
    etf_tickers: set,
    signal_date: str,
    market_score: int,
    next_date,
    bars_data: dict,
) -> list[dict]:
    """
    Detect capitulation recovery signals: stocks that dropped 40%+ from
    their 60-day high (capitulation), were below both MA21 and MA50,
    and NOW close back above MA21 for the first time.

    These catch the 10x mover pattern — beaten-down stocks recovering
    after a market sell-off. Entry is next-open after MA21 reclaim.
    """
    from screener import calculate_atr_series
    from sector_rs import get_sector

    recovery_signals = []

    for ticker, df in sliced.items():
        if ticker in etf_tickers:
            continue
        if len(df) < 80:  # need enough history for 60-day high + MAs
            continue

        try:
            closes = df["close"]
            highs  = df["high"]
            lows   = df["low"]
            price  = float(closes.iloc[-1])

            # MA21 and MA50
            ma21 = float(closes.iloc[-21:].mean()) if len(closes) >= 21 else None
            ma50 = float(closes.iloc[-50:].mean()) if len(closes) >= 50 else None
            if ma21 is None or ma50 is None:
                continue

            # Must be closing ABOVE MA21 today
            if price <= ma21:
                continue

            # Yesterday must have been BELOW MA21 (first reclaim)
            if len(closes) < 22:
                continue
            prev_close = float(closes.iloc[-2])
            prev_ma21  = float(closes.iloc[-22:-1].mean())
            if prev_close > prev_ma21:
                continue  # was already above — not a fresh reclaim

            # Must still be below MA50 (early recovery, not already established)
            if price > ma50:
                continue

            # Capitulation check: must have dropped 40%+ from 60-day high
            lookback_60 = highs.iloc[-60:] if len(highs) >= 60 else highs
            high_60d = float(lookback_60.max())
            drawdown = (high_60d - price) / high_60d
            if drawdown < 0.30:  # at least 30% below 60d high
                continue

            # Volume surge on reclaim day — conviction
            if "volume" in df.columns and len(df) >= 21:
                avg_vol = float(df["volume"].iloc[-21:-1].mean())
                today_vol = float(df["volume"].iloc[-1])
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0
                if vol_ratio < 1.2:  # need at least 20% above average volume
                    continue
            else:
                vol_ratio = 0

            # ATR for position sizing
            atr_raw = calculate_atr_series(df)
            if isinstance(atr_raw, (int, float)):
                atr = float(atr_raw)
            elif atr_raw is not None and hasattr(atr_raw, 'iloc') and len(atr_raw) > 0:
                atr = float(atr_raw.iloc[-1])
            else:
                atr = None
            if not atr or atr <= 0:
                continue

            # Next open for entry
            next_open = None
            if next_date is not None and ticker in bars_data:
                next_row = bars_data[ticker][bars_data[ticker].index == next_date]
                if not next_row.empty:
                    next_open = float(next_row["open"].iloc[0])

            sector = get_sector(ticker)

            recovery_signals.append({
                "_is_long":    True,
                "_is_short":   False,
                "_result":     {},
                "ticker":      ticker,
                "signal_date": signal_date,
                "signal_type": "RECOVERY",
                "price":       round(price, 4),
                "entry_close": round(price, 4),
                "entry_next_open": next_open,
                "breakout_price": None,
                "base_low":    round(float(lows.iloc[-20:].min()), 4),
                "ma10":  None,
                "ma21":  round(ma21, 4),
                "ma50":  round(ma50, 4),
                "vcs":   None,
                "rs":    0,  # RS will be low for beaten-down stocks
                "vol_ratio": round(vol_ratio, 2),
                "atr":   round(atr, 4),
                "base_score": 0,
                "base_type": "recovery",
                "vcp_stages": 0,
                "sector": sector,
                "sector_rs_1m": None,
                "market_score": market_score,
                "pct_from_ma21": round((price - ma21) / ma21 * 100, 2),
                "is_short": False,
                "day_of_week": pd.Timestamp(signal_date).strftime("%a").upper(),
                "w_stack_ok": 0,
                "w_ema10": None,
                "w_ema40": None,
                "w_ema10_slope": None,
                "w_above_ema10": 0,
                "w_above_ema40": 0,
                "within_1atr_wema10": 0,
                "is_weekly_signal": 0,
            })
        except Exception:
            continue

    return recovery_signals


# ── Exit simulator ─────────────────────────────────────────────────────────────


def _simulate_exit(
    signal: dict,
    bars_data: dict,
    signal_day_idx: int,
    trading_dates: pd.DatetimeIndex,
    params: dict,
    entry_price: float,
    entry_type: str,
) -> dict:
    """
    Walk forward from signal_day_idx+1 and find exit.
    Uses only future bars — no look-ahead.

    Stop is set below the relevant MA (not ATR-based) so it matches
    the actual signal logic. ATR is used only for targets.
    """
    ticker   = signal["ticker"]
    atr      = signal["atr"]
    is_short = signal["is_short"]
    ma21     = signal.get("ma21")
    ma10     = signal.get("ma10")
    ma50     = signal.get("ma50")

    if not atr or atr <= 0 or ticker not in bars_data:
        return None

    is_weekly = bool(signal.get("is_weekly_signal", 0))
    max_hold = params.get("w_max_hold_days", 50) if is_weekly else params["max_hold_days"]

    # ── Stop price: use MA level from signal, not ATR ─────────────────────────
    # Pick the tightest MA below entry that makes sense for the signal type
    sig_type = signal.get("signal_type", "")
    slip = params.get("slippage", 0.001)

    is_recovery = sig_type == "RECOVERY"

    if not is_short:
        if is_recovery:
            # Recovery signals: use 20-day low as stop — wider room for volatile bounces
            base_low = signal.get("base_low")
            stop_price = base_low * 0.98 if base_low else entry_price * 0.75
            # Recovery gets wider safety cap: 25% max loss
            stop_price = max(stop_price, entry_price * 0.75)
            # Recovery gets longer hold and later trail activation
            max_hold = 120
        else:
            # For MA bounce signals, stop goes just below the touched MA
            if "MA10" in sig_type and ma10:
                stop_price = ma10 * 0.99
            elif "MA21" in sig_type and ma21:
                stop_price = ma21 * 0.99
            elif "MA50" in sig_type and ma50:
                stop_price = ma50 * 0.99
            elif ma10 and ma10 < entry_price:
                stop_price = ma10 * 0.99
            elif ma21 and ma21 < entry_price:
                stop_price = ma21 * 0.99
            else:
                stop_price = entry_price * (1 - params["stop_atr_mult"] * atr / entry_price)

        if not is_recovery:
            # Safety cap: stop can't be more than 15% below entry
            stop_price = max(stop_price, entry_price * 0.85)
    else:
        if ma10 and ma10 > entry_price:
            stop_price = ma10 * 1.01
        elif ma21 and ma21 > entry_price:
            stop_price = ma21 * 1.01
        else:
            stop_price = entry_price * (1 + params["stop_atr_mult"] * atr / entry_price)

        # Safety cap: stop can't be more than 15% above entry
        stop_price = min(stop_price, entry_price * 1.15)

    df = bars_data[ticker]
    exit_price  = None
    exit_reason = None
    hold_days   = 0

    # Precompute full MA50 series once — O(n) instead of O(n²) per-bar slicing
    ma50_series = df["close"].rolling(50).mean()

    start_idx = signal_day_idx + 1
    end_idx   = min(start_idx + max_hold, len(trading_dates))

    for i in range(start_idx, end_idx):
        if i >= len(trading_dates):
            break
        bar_date = trading_dates[i]
        bar = df[df.index == bar_date]
        if bar.empty:
            continue

        bar_high  = float(bar["high"].iloc[0])
        bar_low   = float(bar["low"].iloc[0])
        bar_close = float(bar["close"].iloc[0])
        hold_days += 1

        # O(1) lookup from precomputed series
        ma50_val = ma50_series.get(bar_date)
        dynamic_ma50 = float(ma50_val) if ma50_val is not None and not pd.isna(ma50_val) else None

        if not is_short:
            # Hard stop first
            if bar_low <= stop_price:
                exit_price, exit_reason = stop_price * (1 - slip), "stop"
                break
            # Trailing MA50 exit — delayed activation (20d normal, 30d recovery)
            else:
                trail_delay = 30 if is_recovery else 20
                if hold_days >= trail_delay and dynamic_ma50 and bar_close < dynamic_ma50 * 0.99:
                    exit_price, exit_reason = bar_close * (1 - slip), "trail_ma50"
                    break
        else:
            # Hard stop first
            if bar_high >= stop_price:
                exit_price, exit_reason = stop_price * (1 + slip), "stop"
                break
            # Trailing MA50 exit — only active after 20 hold days
            elif hold_days >= 20 and dynamic_ma50 and bar_close > dynamic_ma50 * 1.01:
                exit_price, exit_reason = bar_close * (1 + slip), "trail_ma50"
                break

    if exit_price is None:
        last_idx  = min(start_idx + max_hold - 1, len(trading_dates) - 1)
        last_date = trading_dates[last_idx]
        last_bar  = df[df.index == last_date]
        exit_price  = float(last_bar["close"].iloc[0]) * (1 - slip) if not last_bar.empty else entry_price
        exit_reason = "timeout"

    # ── P&L — slippage already baked into exit_price above ───────────────────
    # entry_price comes in pre-slippage from the caller, so just use directly
    if not is_short:
        pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100

    pnl_pct = round(pnl_pct, 3)
    risk_pct = abs(entry_price - stop_price) / entry_price * 100
    pnl_r    = round(pnl_pct / risk_pct, 2) if risk_pct > 0 else 0

    return {
        "signal_date":  signal["signal_date"],
        "day_of_week":  signal.get("day_of_week"),
        "ticker":       ticker,
        "signal_type":  signal["signal_type"],
        "entry_type":   entry_type,
        "entry_price":  round(entry_price, 4),
        "exit_price":   round(exit_price, 4),
        "exit_reason":  exit_reason,
        "hold_days":    hold_days,
        "pnl_pct":      pnl_pct,
        "pnl_r":        pnl_r,
        "atr":          round(atr, 4),
        "stop_price":   round(stop_price, 4),
        "trail_exit":   1 if exit_reason == "trail_ma50" else 0,
        "vcs":          signal.get("vcs"),
        "rs":           signal.get("rs"),
        "base_score":   signal.get("base_score", 0),
        "sector":       signal.get("sector"),
        "market_score": signal.get("market_score"),
        "is_short":     1 if is_short else 0,
        "signal_id":    None,  # filled in after DB insert
        # MAE/MFE not tracked during reconstruction — set to None
        "mae_pct":      None,
        "mae_r":        None,
        "mfe_pct":      None,
        "mfe_r":        None,
        "slippage_pct": None,
    }


def _simulate_breakout_exit(
    signal: dict,
    bars_data: dict,
    signal_day_idx: int,
    trading_dates: pd.DatetimeIndex,
    params: dict,
) -> dict | None:
    """
    Simulate a breakout entry: wait up to 15 days for price to cross breakout_price,
    then enter and use base_low as stop. Tracks R-multiple with wider initial risk.
    Returns None if price never reaches breakout level within the window.
    """
    ticker         = signal["ticker"]
    breakout_price = signal.get("breakout_price")
    base_low       = signal.get("base_low")
    atr            = signal.get("atr")

    if not breakout_price or not base_low or not atr or atr <= 0:
        return None
    if ticker not in bars_data:
        return None
    # Skip shorts — breakout concept applies to longs only
    if signal.get("is_short"):
        return None

    df = bars_data[ticker]
    slip = params.get("slippage", 0.001)
    max_wait  = 15   # days to wait for breakout to trigger
    max_hold  = params.get("max_hold_days", 30)

    # Phase 1: wait for breakout trigger
    entry_price  = None
    entry_day_idx = None
    start_idx = signal_day_idx + 1
    wait_end  = min(start_idx + max_wait, len(trading_dates))

    for i in range(start_idx, wait_end):
        if i >= len(trading_dates):
            break
        bar_date = trading_dates[i]
        bar = df[df.index == bar_date]
        if bar.empty:
            continue
        bar_high = float(bar["high"].iloc[0])
        if bar_high >= breakout_price:
            entry_price   = breakout_price * (1 + slip)
            entry_day_idx = i
            break

    if entry_price is None:
        # Never broke out — record as a "no trigger" with 0 pnl
        return {
            "signal_date":  signal["signal_date"],
            "day_of_week":  signal.get("day_of_week"),
            "ticker":       ticker,
            "signal_type":  signal["signal_type"],
            "entry_type":   "breakout",
            "entry_price":  None,
            "exit_price":   None,
            "exit_reason":  "no_trigger",
            "hold_days":    0,
            "pnl_pct":      0.0,
            "pnl_r":        0.0,
            "atr":          round(atr, 4),
            "stop_price":   round(base_low, 4),
            "trail_exit":   0,
            "vcs":          signal.get("vcs"),
            "rs":           signal.get("rs"),
            "base_score":   signal.get("base_score", 0),
            "sector":       signal.get("sector"),
            "market_score": signal.get("market_score"),
            "is_short":     0,
            "signal_id":    None,
            "mae_pct": None, "mae_r": None, "mfe_pct": None,
            "mfe_r": None, "slippage_pct": None,
        }

    # Phase 2: simulate from entry with base_low stop
    # Risk = entry - base_low; targets scaled by same ATR multiples as MA entry
    risk_per_share = entry_price - base_low
    if risk_per_share <= 0:
        return None

    stop_price = base_low * (1 - slip)
    t1_mult = params.get("t1_atr_mult", 1.5)
    t2_mult = params.get("t2_atr_mult", 3.0)
    t3_mult = params.get("t3_atr_mult", 5.0)
    t1_price = entry_price + t1_mult * atr
    t2_price = entry_price + t2_mult * atr
    t3_price = entry_price + t3_mult * atr

    exit_price  = None
    exit_reason = None
    hold_days   = 0
    end_idx = min(entry_day_idx + 1 + max_hold, len(trading_dates))

    for i in range(entry_day_idx + 1, end_idx):
        if i >= len(trading_dates):
            break
        bar_date = trading_dates[i]
        bar = df[df.index == bar_date]
        if bar.empty:
            continue
        bar_high  = float(bar["high"].iloc[0])
        bar_low   = float(bar["low"].iloc[0])
        hold_days += 1

        if bar_low <= stop_price:
            exit_price, exit_reason = stop_price, "stop"
            break
        elif bar_high >= t3_price:
            exit_price, exit_reason = t3_price * (1 - slip), "t3"
            break
        elif bar_high >= t2_price:
            exit_price, exit_reason = t2_price * (1 - slip), "t2"
            break
        elif bar_high >= t1_price:
            exit_price, exit_reason = t1_price * (1 - slip), "t1"
            break

    if exit_price is None:
        last_idx  = min(entry_day_idx + max_hold, len(trading_dates) - 1)
        last_date = trading_dates[last_idx]
        last_bar  = df[df.index == last_date]
        exit_price  = float(last_bar["close"].iloc[0]) if not last_bar.empty else entry_price
        exit_reason = "timeout"

    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 3)
    risk_pct = risk_per_share / entry_price * 100
    pnl_r    = round(pnl_pct / risk_pct, 2) if risk_pct else 0

    return {
        "signal_date":  signal["signal_date"],
        "day_of_week":  signal.get("day_of_week"),
        "ticker":       ticker,
        "signal_type":  signal["signal_type"],
        "entry_type":   "breakout",
        "entry_price":  round(entry_price, 4),
        "exit_price":   round(exit_price, 4),
        "exit_reason":  exit_reason,
        "hold_days":    hold_days,
        "pnl_pct":      pnl_pct,
        "pnl_r":        pnl_r,
        "atr":          round(atr, 4),
        "stop_price":   round(stop_price, 4),
        "trail_exit":   0,
        "vcs":          signal.get("vcs"),
        "rs":           signal.get("rs"),
        "base_score":   signal.get("base_score", 0),
        "sector":       signal.get("sector"),
        "market_score": signal.get("market_score"),
        "is_short":     0,
        "signal_id":    None,
        "mae_pct": None, "mae_r": None, "mfe_pct": None,
        "mfe_r": None, "slippage_pct": None,
    }


# ── Main reconstruction runner ────────────────────────────────────────────────

def run_historical_reconstruction(
    bars_data: dict,
    lookback_days: int = 365,
    params: dict = None,
    progress_callback=None,
) -> dict:
    """
    Main entry point. Re-runs screener for every trading day
    in the lookback window and simulates exits.

    Returns summary dict with counts and status.
    """
    if params is None:
        params = DEFAULT_PARAMS.copy()

    print(f"\n[historical_bt] Starting reconstruction — {lookback_days} day lookback")
    t0 = time.time()

    init_backtest_tables()

    # Identify all ETF tickers to exclude from signal scanning
    from watchlist import ETFS
    from sector_rs import SECTOR_ETFS
    etf_tickers = set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM", "DIA"])

    # Get unified trading date index from SPY (most complete)
    if "SPY" not in bars_data:
        print("[historical_bt] SPY not in bars_data — cannot determine trading dates")
        return {"error": "SPY data required"}

    all_dates = bars_data["SPY"].index
    cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)).tz_localize(None)
    # Only process dates within lookback window, but need MIN_BARS_HISTORY before start
    scan_dates = all_dates[all_dates >= cutoff]
    start_offset = list(all_dates).index(scan_dates[0]) if len(scan_dates) > 0 else 0

    if start_offset < MIN_BARS_HISTORY:
        print(f"[historical_bt] Not enough history before scan window ({start_offset} bars, need {MIN_BARS_HISTORY})")
        return {"error": "Insufficient history"}

    total_days = len(scan_dates)
    print(f"[historical_bt] Scanning {total_days} trading days ({scan_dates[0].date()} to {scan_dates[-1].date()})")

    # ── Fast-path: if signals already exist but trades are missing, skip screener ──
    with get_conn() as conn:
        existing_signal_count = conn.execute("SELECT COUNT(*) FROM historical_signals").fetchone()[0]
        existing_trade_count  = conn.execute("SELECT COUNT(*) FROM historical_trades").fetchone()[0]

    if existing_signal_count > 50000 and existing_trade_count == 0:
        print(f"[historical_bt] Fast-path: {existing_signal_count} signals in DB, 0 trades — re-simulating exits only")
        date_to_idx = {d: i for i, d in enumerate(all_dates)}
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, signal_date, ticker, signal_type, atr, ma10, ma21, ma50, vcs, rs, "
                "base_score, sector, market_score, is_short, entry_close, entry_next_open "
                "FROM historical_signals ORDER BY signal_date"
            ).fetchall()
        all_trades = []
        for row in rows:
            sig = dict(zip(
                ["signal_id","signal_date","ticker","signal_type","atr","ma10","ma21","ma50","vcs","rs",
                 "base_score","sector","market_score","is_short","entry_close","entry_next_open"], row
            ))
            day_idx = date_to_idx.get(pd.Timestamp(sig["signal_date"]), -1)
            if day_idx < 0:
                continue
            for entry_type in params.get("entry_types", ["close"]):
                slip = params.get("slippage", 0.001)
                raw_entry = sig.get("entry_close") if entry_type == "close" else sig.get("entry_next_open")
                entry_price = raw_entry * (1 + slip) if raw_entry else None
                if not entry_price:
                    continue
                trade = _simulate_exit(sig, bars_data, day_idx, all_dates, params, entry_price, entry_type)
                if trade:
                    trade["signal_id"] = sig["signal_id"]
                    all_trades.append(trade)
        if all_trades:
            save_historical_trades(all_trades)
        elapsed = round(time.time() - t0, 1)
        print(f"[historical_bt] Complete in {elapsed}s — {existing_signal_count} signals, {len(all_trades)} trades")
        return {"signals_found": existing_signal_count, "trades_simulated": len(all_trades), "status": "complete"}

    all_signals = []
    all_trades = []

    # Pre-compute index map once — list().index() inside a loop is O(n²)
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    # ── Resume from checkpoint — skip days already saved in DB ───────────────
    with get_conn() as conn:
        last_saved = conn.execute(
            "SELECT MAX(signal_date) FROM historical_signals"
        ).fetchone()[0]

    if last_saved:
        last_saved_ts = pd.Timestamp(last_saved)
        skipped = sum(1 for d in scan_dates if d <= last_saved_ts)
        if skipped > 0:
            print(f"[historical_bt] Resuming from checkpoint — skipping {skipped} days already saved (last: {last_saved})")
            scan_dates = [d for d in scan_dates if d > last_saved_ts]
            total_days_original = total_days
            total_days = len(scan_dates)
            signals_found_offset = conn.execute("SELECT COUNT(*) FROM historical_signals").fetchone()[0] if skipped else 0
        else:
            signals_found_offset = 0
    else:
        signals_found_offset = 0

    with get_conn() as conn:
        signals_found_offset = conn.execute("SELECT COUNT(*) FROM historical_signals").fetchone()[0]
        days_already_done    = conn.execute("SELECT COUNT(DISTINCT signal_date) FROM historical_signals").fetchone()[0]

    days_processed = days_already_done
    signals_found  = signals_found_offset

    # ── Pre-compute ticker index positions ONCE — avoids O(n²) tolist() per day ──
    print("[historical_bt] Pre-computing ticker index positions...", flush=True)
    ticker_positions = {}
    for ticker, df in bars_data.items():
        ticker_positions[ticker] = df.index.tolist()
    print(f"[historical_bt] Index positions ready for {len(ticker_positions)} tickers", flush=True)

    for day_pos, scan_date in enumerate(scan_dates):
        day_idx = date_to_idx.get(scan_date, -1)
        if day_idx < 0:
            continue

        day_str = scan_date.date().isoformat()
        print(f"[historical_bt] Day {day_pos+1}/{total_days} — {day_str}", flush=True)

        # Scan this day — pass pre-computed positions for speed
        signals = _scan_day(all_dates, day_idx, bars_data, etf_tickers, params, ticker_positions)
        signals_found += len(signals)

        # Simulate exits for each signal
        regime_gate   = params.get("regime_gate", 48)
        min_rs        = params.get("min_rs", 0)
        min_base_score = params.get("min_base_score", 0)
        min_vol_ratio = params.get("min_vol_ratio", 0)
        for sig in signals:
            # Quality gate — skip low-quality signals entirely (not saved to DB)
            is_sig_short = sig.get("signal_type") == "SHORT"
            is_recovery  = sig.get("signal_type") == "RECOVERY"
            if is_sig_short:
                # Shorts need LOW rs (weak stocks only) — invert the gate
                if (sig.get("rs") or 100) > 45:
                    continue
            elif is_recovery:
                # Recovery signals — beaten-down stocks, skip RS/base gates
                # Volume surge already checked in detector
                pass
            else:
                # Longs need HIGH rs and volume confirmation
                if (sig.get("rs") or 0) < min_rs:
                    continue
                if (sig.get("vol_ratio") or 0) < min_vol_ratio:
                    continue
                if (sig.get("base_score") or 0) < min_base_score:
                    continue
            allowed_types = params.get("allowed_signal_types")
            if allowed_types and sig.get("signal_type") not in allowed_types:
                continue
            market_score = sig.get("market_score") or 0
            if is_sig_short or is_recovery:
                # Shorts/recovery — no market regime gate
                # Recovery happens DURING weak markets (that's the capitulation)
                regime_filtered = 0
            else:
                regime_filtered = 1 if (regime_gate > 0 and market_score < regime_gate) else 0
            sig["regime_filtered"] = regime_filtered

            # Only simulate trades when regime allows it
            if not regime_filtered:
                for entry_type in params.get("entry_types", ["close"]):
                    slip = params.get("slippage", 0.001)
                    if entry_type == "close":
                        raw_entry   = sig.get("entry_close")
                        entry_price = raw_entry * (1 + slip) if raw_entry else None
                    else:
                        raw_entry   = sig.get("entry_next_open")
                        entry_price = raw_entry * (1 + slip) if raw_entry else None

                    if not entry_price:
                        continue

                    trade = _simulate_exit(
                        sig, bars_data, day_idx, all_dates, params,
                        entry_price, entry_type
                    )
                    if trade:
                        trade["regime_filtered"] = 0
                        all_trades.append(trade)

                # Breakout entry simulation — longs only
                if not sig.get("is_short"):
                    bo_trade = _simulate_breakout_exit(sig, bars_data, day_idx, all_dates, params)
                    if bo_trade:
                        bo_trade["regime_filtered"] = 0
                        all_trades.append(bo_trade)

            # Strip internal _result before saving
            sig_clean = {k: v for k, v in sig.items() if not k.startswith("_")}
            all_signals.append(sig_clean)

        days_processed += 1

        if progress_callback:
            progress_callback(days_processed, total_days, signals_found)

        # Checkpoint every 5 days (was 10) — reduces data loss on crash
        if days_processed % 5 == 0:
            elapsed_so_far = round(time.time() - t0, 0)
            print(f"[historical_bt] {days_processed}/{days_already_done + total_days} days | {signals_found} signals | {len(all_trades)} trades | {elapsed_so_far}s elapsed", flush=True)
            if all_signals:
                save_historical_signals(all_signals)
                all_signals = []
            if all_trades:
                _match_and_save_trades(all_trades)
                all_trades = []

    # Save remaining
    if all_signals:
        save_historical_signals(all_signals)

    if all_trades:
        _match_and_save_trades(all_trades)

    elapsed = round(time.time() - t0, 1)
    print(f"[historical_bt] Complete in {elapsed}s — {signals_found} signals, {len(all_trades)} trades")

    return {
        "status": "complete",
        "days_scanned": days_processed,
        "signals_found": signals_found,
        "trades_simulated": len(all_trades),
        "elapsed_s": elapsed,
        "params": params,
    }


def _match_and_save_trades(trades: list[dict]):
    """Match trades to their signal IDs and batch save."""
    with get_conn() as conn:
        # Build a lookup of (signal_date, ticker, signal_type) -> id
        rows = conn.execute(
            "SELECT id, signal_date, ticker, signal_type FROM historical_signals"
        ).fetchall()
        lookup = {
            (r["signal_date"], r["ticker"], r["signal_type"]): r["id"]
            for r in rows
        }

    for t in trades:
        key = (t["signal_date"], t["ticker"], t["signal_type"])
        t["signal_id"] = lookup.get(key)

    save_historical_trades(trades)
