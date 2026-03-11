"""
ep_backtest.py
--------------
Historical backtest for Stockbee Episodic Pivot setups.

Scans through historical bars day-by-day, detects EP events, simulates
entries and exits, and produces statistics to determine optimal trading
conditions for each EP type.

Key outputs:
  - Win rate, avg return, max drawdown by EP type
  - MAGNA score vs performance correlation
  - Best/worst conditions for EP trading
  - Delayed EP performance (breakout after consolidation)
  - Holding period analysis (1d, 3d, 5d, 10d, 20d returns)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from stockbee_ep import EP_CONFIG


def _detect_ep_day(df: pd.DataFrame, idx: int, cfg: dict) -> Optional[dict]:
    """
    Check if bar at `idx` qualifies as an EP day.
    Returns EP info dict or None.
    """
    if idx < 20:
        return None

    closes = df["close"]
    opens = df["open"]
    volumes = df["volume"]
    highs = df["high"]
    lows = df["low"]

    prior_close = float(closes.iloc[idx - 1])
    if prior_close <= 0:
        return None

    day_open = float(opens.iloc[idx])
    day_close = float(closes.iloc[idx])
    day_high = float(highs.iloc[idx])
    day_low = float(lows.iloc[idx])
    day_vol = float(volumes.iloc[idx])

    gap_pct = (day_open - prior_close) / prior_close * 100

    # Classic EP: gap >= 10%
    if gap_pct < cfg.get("classic_ep_gap_pct", 10):
        return None

    # Close didn't fully fade
    if day_close < prior_close + (day_open - prior_close) * 0.3:
        return None

    # Volume check
    adv_start = max(0, idx - 50)
    adv = float(volumes.iloc[adv_start:idx].mean())
    if adv <= 0:
        return None
    vol_ratio = day_vol / adv

    if vol_ratio < cfg.get("classic_ep_vol_mult", 2):
        return None

    # Check for 9M
    is_9m = day_vol >= cfg.get("nine_m_volume", 9_000_000)

    # Prior neglect check
    neglect_start = max(0, idx - 63)
    if idx - neglect_start >= 10:
        start_px = float(closes.iloc[neglect_start])
        end_px = float(closes.iloc[idx - 1])
        neglect_return = (end_px - start_px) / start_px * 100 if start_px > 0 else 0
        neglected = neglect_return <= 10
    else:
        neglected = None

    # Technical position (53+)
    above_50ma = True
    near_52w_high = False
    if idx >= 50:
        ma50 = float(closes.iloc[idx - 50:idx].mean())
        above_50ma = prior_close > ma50
    if idx >= 252:
        w52_high = float(highs.iloc[idx - 252:idx].max())
        pct_from_high = (w52_high - prior_close) / w52_high * 100
        near_52w_high = pct_from_high <= 3

    date_str = str(df.index[idx].date()) if hasattr(df.index[idx], "date") else str(df.index[idx])

    return {
        "idx": idx,
        "date": date_str,
        "gap_pct": round(gap_pct, 1),
        "vol_ratio": round(vol_ratio, 1),
        "day_open": round(day_open, 2),
        "day_close": round(day_close, 2),
        "day_high": round(day_high, 2),
        "day_low": round(day_low, 2),
        "volume": day_vol,
        "is_9m": is_9m,
        "neglected": neglected,
        "above_50ma": above_50ma,
        "near_52w_high": near_52w_high,
    }


def _simulate_trade(df: pd.DataFrame, entry_idx: int, entry_price: float,
                     stop_price: float, target_pct: float = 20.0,
                     max_hold: int = 20) -> dict:
    """
    Simulate a trade from entry_idx forward using FIXED stop/target.
    Legacy method — kept for comparison.
    """
    n = len(df)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    best_price = entry_price
    worst_price = entry_price
    exit_price = entry_price
    exit_reason = "timeout"
    hold_days = 0

    target_price = entry_price * (1 + target_pct / 100)

    # Multi-period returns
    returns = {}
    for d in [1, 3, 5, 10, 20]:
        future_idx = entry_idx + d
        if future_idx < n:
            future_price = float(closes.iloc[future_idx])
            returns[f"return_{d}d"] = round((future_price - entry_price) / entry_price * 100, 2)
        else:
            returns[f"return_{d}d"] = None

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_low = float(lows.iloc[i])
        day_high = float(highs.iloc[i])
        day_close = float(closes.iloc[i])
        hold_days = i - entry_idx

        best_price = max(best_price, day_high)
        worst_price = min(worst_price, day_low)

        # Stop hit
        if day_low <= stop_price:
            exit_price = stop_price
            exit_reason = "stop"
            break

        # Target hit
        if day_high >= target_price:
            exit_price = target_price
            exit_reason = "target"
            break

        exit_price = day_close

    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)
    mfe_pct = round((best_price - entry_price) / entry_price * 100, 2)
    mae_pct = round((worst_price - entry_price) / entry_price * 100, 2)

    return {
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "stop_price": round(stop_price, 2),
        "target_price": round(target_price, 2),
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "exit_reason": exit_reason,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "win": pnl_pct > 0,
        **returns,
    }


def _simulate_trade_trailing(df: pd.DataFrame, entry_idx: int, entry_price: float,
                              stop_price: float, be_trigger_pct: float = 10.0,
                              trail_pct: float = 15.0, max_hold: int = 60) -> dict:
    """
    Simulate a trade using the CURRENT live exit strategy:
    1. Initial stop below EP day low
    2. Move to breakeven after +be_trigger_pct% gain
    3. Trail trail_pct% from highest close
    4. No fixed target — hold until trailing stop triggers or max_hold days

    This matches EP_CONFIG exit_be_trigger_pct and exit_trail_pct.
    """
    n = len(df)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    best_price = entry_price
    worst_price = entry_price
    exit_price = entry_price
    exit_reason = "timeout"
    hold_days = 0
    breakeven_hit = False
    trailing_active = False
    current_stop = stop_price
    highest_close = entry_price

    # Multi-period returns (buy-and-hold reference)
    returns = {}
    for d in [1, 3, 5, 10, 20]:
        future_idx = entry_idx + d
        if future_idx < n:
            future_price = float(closes.iloc[future_idx])
            returns[f"return_{d}d"] = round((future_price - entry_price) / entry_price * 100, 2)
        else:
            returns[f"return_{d}d"] = None

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_low = float(lows.iloc[i])
        day_high = float(highs.iloc[i])
        day_close = float(closes.iloc[i])
        hold_days = i - entry_idx

        best_price = max(best_price, day_high)
        worst_price = min(worst_price, day_low)

        # Stop hit (initial or trailing)
        if day_low <= current_stop:
            exit_price = current_stop
            exit_reason = "trailing_stop" if trailing_active else ("breakeven" if breakeven_hit else "stop")
            break

        # Update highest close
        if day_close > highest_close:
            highest_close = day_close

        # Breakeven trigger
        gain_pct = (day_close - entry_price) / entry_price * 100
        if not breakeven_hit and gain_pct >= be_trigger_pct:
            breakeven_hit = True
            current_stop = max(current_stop, entry_price)

        # Trailing stop: activate after breakeven, trail from highest close
        if breakeven_hit:
            trailing_active = True
            trail_stop = highest_close * (1 - trail_pct / 100)
            current_stop = max(current_stop, trail_stop)

        exit_price = day_close

    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)
    mfe_pct = round((best_price - entry_price) / entry_price * 100, 2)
    mae_pct = round((worst_price - entry_price) / entry_price * 100, 2)

    return {
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "stop_price": round(stop_price, 2),
        "final_stop": round(current_stop, 2),
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "exit_reason": exit_reason,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "win": pnl_pct > 0,
        "breakeven_hit": breakeven_hit,
        "highest_close": round(highest_close, 2),
        **returns,
    }


def _simulate_trade_weekly_ma(df: pd.DataFrame, entry_idx: int, entry_price: float,
                               stop_price: float, ma_period: int = 10,
                               max_hold: int = 252) -> dict:
    """
    Simulate a trade using WEEKLY MA trailing stop (position trade style).

    Rules:
    1. Initial stop below EP day low
    2. After +15% gain, switch to 10-week (50-day) MA trail
    3. Exit when weekly close below the MA
    4. Max hold 252 days (1 year)

    This is how Minervini/O'Neil hold big winners for months.
    """
    n = len(df)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    best_price = entry_price
    worst_price = entry_price
    exit_price = entry_price
    exit_reason = "timeout"
    hold_days = 0
    breakeven_hit = False
    ma_trail_active = False
    current_stop = stop_price
    highest_close = entry_price

    # Multi-period returns
    returns = {}
    for d in [1, 3, 5, 10, 20, 60, 120]:
        future_idx = entry_idx + d
        if future_idx < n:
            future_price = float(closes.iloc[future_idx])
            returns[f"return_{d}d"] = round((future_price - entry_price) / entry_price * 100, 2)
        else:
            returns[f"return_{d}d"] = None

    ma_len = ma_period * 5  # 10 weeks = 50 trading days

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_low = float(lows.iloc[i])
        day_high = float(highs.iloc[i])
        day_close = float(closes.iloc[i])
        hold_days = i - entry_idx

        best_price = max(best_price, day_high)
        worst_price = min(worst_price, day_low)

        # Initial stop hit
        if day_low <= current_stop and not ma_trail_active:
            exit_price = current_stop
            exit_reason = "stop"
            break

        if day_close > highest_close:
            highest_close = day_close

        gain_pct = (day_close - entry_price) / entry_price * 100

        # Move to breakeven at +10%
        if not breakeven_hit and gain_pct >= 10:
            breakeven_hit = True
            current_stop = max(current_stop, entry_price)

        # Activate MA trail at +15%
        if not ma_trail_active and gain_pct >= 15:
            ma_trail_active = True

        # MA trail: check weekly close (every 5 bars) against MA
        if ma_trail_active and hold_days >= ma_len and hold_days % 5 == 0:
            ma_start = max(0, i - ma_len)
            ma_val = float(closes.iloc[ma_start:i].mean())
            if day_close < ma_val:
                exit_price = day_close
                exit_reason = "ma_trail"
                break
            # Also update hard stop to be 25% below highest
            current_stop = max(current_stop, highest_close * 0.75)

        # Hard stop (25% from peak) as catastrophe protection
        if ma_trail_active and day_low <= highest_close * 0.75:
            exit_price = highest_close * 0.75
            exit_reason = "hard_trail"
            break

        exit_price = day_close

    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)
    mfe_pct = round((best_price - entry_price) / entry_price * 100, 2)
    mae_pct = round((worst_price - entry_price) / entry_price * 100, 2)

    return {
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "stop_price": round(stop_price, 2),
        "final_stop": round(current_stop, 2),
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "exit_reason": exit_reason,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "win": pnl_pct > 0,
        "breakeven_hit": breakeven_hit,
        "highest_close": round(highest_close, 2),
        **returns,
    }


def _simulate_trade_ratchet(df: pd.DataFrame, entry_idx: int, entry_price: float,
                             stop_price: float, max_hold: int = 252) -> dict:
    """
    HYBRID exit strategy: ratchet phases 0-3, then 10w MA trail at phase 4.

    Reverse-engineered from 21 EP events across 12 big movers (HOOD +276%,
    NVDA +210%, APP +540%, PLTR +250%, AXON +180%, TGTX +140%):
    - 100%+ winners tolerate 32% avg drawdown, take 130d median to peak
    - Ratchet alone cuts at +134% (12% trail); position MA lets CDTX run to +407%
    - Solution: ratchet for early protection, MA trail to ride multi-baggers

    Phases:
    Phase 0 (0-10% gain):    Initial stop (EP day low)
    Phase 1 (10-20% gain):   Breakeven + 25% trail from peak
    Phase 2 (20-50% gain):   20% trail from peak
    Phase 3 (50-100% gain):  15% trail from peak + 10w MA secondary
    Phase 4 (100%+ gain):    10w MA trail ONLY (let it ride), 25% hard stop catastrophe

    The key insight: once you have a double, stop using % trails entirely and
    let the 10-week MA trail do the work — that's how you capture 200-400% moves.
    """
    n = len(df)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    best_price = entry_price
    worst_price = entry_price
    exit_price = entry_price
    exit_reason = "timeout"
    hold_days = 0
    breakeven_hit = False
    current_stop = stop_price
    highest_close = entry_price
    phase = 0

    # Multi-period returns
    returns = {}
    for d in [1, 3, 5, 10, 20, 60, 120]:
        future_idx = entry_idx + d
        if future_idx < n:
            future_price = float(closes.iloc[future_idx])
            returns[f"return_{d}d"] = round((future_price - entry_price) / entry_price * 100, 2)
        else:
            returns[f"return_{d}d"] = None

    ma_len = 50  # 10-week MA in trading days

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        day_low = float(lows.iloc[i])
        day_high = float(highs.iloc[i])
        day_close = float(closes.iloc[i])
        hold_days = i - entry_idx

        best_price = max(best_price, day_high)
        worst_price = min(worst_price, day_low)

        if day_close > highest_close:
            highest_close = day_close

        gain_pct = (day_close - entry_price) / entry_price * 100
        peak_gain = (highest_close - entry_price) / entry_price * 100

        # ── Phase 4: 100%+ gain → MA trail only (let runners ride) ──
        if peak_gain >= 100:
            phase = 4

            # Hard stop: 25% from peak (catastrophe protection only)
            hard_stop = highest_close * 0.75
            current_stop = max(current_stop, hard_stop)

            if day_low <= current_stop:
                exit_price = current_stop
                exit_reason = "hard_trail_p4"
                break

            # 10w MA trail: check weekly
            if hold_days >= ma_len and hold_days % 5 == 0:
                ma_start = max(0, i - ma_len)
                ma_val = float(closes.iloc[ma_start:i].mean())
                if day_close < ma_val:
                    exit_price = day_close
                    exit_reason = "ma_trail_p4"
                    break

            exit_price = day_close
            continue

        # ── Phases 0-3: ratcheting % trail ──

        # Stop hit (ratchet or initial)
        if day_low <= current_stop:
            exit_price = current_stop
            if phase == 0:
                exit_reason = "stop"
            elif breakeven_hit and phase <= 1:
                exit_reason = "breakeven"
            else:
                exit_reason = f"ratchet_p{phase}"
            break

        # Determine phase and trail %
        if peak_gain >= 50:
            phase = 3
            trail_pct = 15
        elif peak_gain >= 20:
            phase = 2
            trail_pct = 20
        elif peak_gain >= 10:
            phase = 1
            trail_pct = 25
            if not breakeven_hit:
                breakeven_hit = True
                current_stop = max(current_stop, entry_price)
        else:
            trail_pct = None

        # Update trailing stop based on ratchet
        if trail_pct is not None:
            ratchet_stop = highest_close * (1 - trail_pct / 100)
            current_stop = max(current_stop, ratchet_stop)

        # Phase 3: also check 10w MA as secondary exit (catches trend breaks)
        if phase >= 3 and hold_days >= ma_len and hold_days % 5 == 0:
            ma_start = max(0, i - ma_len)
            ma_val = float(closes.iloc[ma_start:i].mean())
            if day_close < ma_val:
                exit_price = day_close
                exit_reason = "ma_trail_p3"
                break

        exit_price = day_close

    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)
    mfe_pct = round((best_price - entry_price) / entry_price * 100, 2)
    mae_pct = round((worst_price - entry_price) / entry_price * 100, 2)

    return {
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "stop_price": round(stop_price, 2),
        "final_stop": round(current_stop, 2),
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "exit_reason": exit_reason,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "win": pnl_pct > 0,
        "breakeven_hit": breakeven_hit,
        "highest_close": round(highest_close, 2),
        "final_phase": phase,
        **returns,
    }


def backtest_eps(bars_data: dict, lookback_days: int = 365,
                 config: dict = None) -> dict:
    """
    Run historical EP backtest across all stocks.

    Scans each stock day-by-day, detects EP events, simulates trades.

    Args:
        bars_data: dict of ticker -> DataFrame
        lookback_days: how far back to scan
        config: override EP_CONFIG thresholds

    Returns comprehensive backtest results.
    """
    cfg = {**EP_CONFIG, **(config or {})}

    all_trades = []        # Swing (15% trail)
    all_trades_wide = []   # Position (weekly MA trail)
    all_trades_ratchet = []  # Winner-derived ratchet strategy
    ep_events = []

    # Exit strategy params from config
    be_trigger = cfg.get("exit_be_trigger_pct", 10)
    trail_pct = cfg.get("exit_trail_pct", 15)

    # ETF filter
    _FUND_QUOTE_TYPES = {"ETF", "MUTUALFUND", "MONEYMARKET", "INDEX"}

    for ticker, df in bars_data.items():
        if df is None or len(df) < 60:
            continue

        # Apply current live filters
        last_close = float(df["close"].iloc[-1])
        if last_close < 2.0:
            continue

        n = len(df)
        start_idx = max(50, n - lookback_days)

        for idx in range(start_idx, n - 1):  # -1 because we need next day for entry
            ep = _detect_ep_day(df, idx, cfg)
            if ep is None:
                continue

            # 9M EP filter: require gap >= 3% or intraday range >= 5%
            intraday_range = (ep["day_high"] - ep["day_low"]) / ep["day_low"] * 100 if ep["day_low"] > 0 else 0
            if ep.get("is_9m") and abs(ep["gap_pct"]) < 3 and intraday_range < 5:
                continue

            ep["ticker"] = ticker

            # Determine EP type
            ep_type = "CLASSIC"
            if ep["is_9m"] and ep["gap_pct"] < 5:
                ep_type = "9M"
            elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
                ep_type = "STORY"

            ep["ep_type"] = ep_type
            ep_events.append(ep)

            # Entry: next day open
            entry_idx = idx + 1
            if entry_idx >= n:
                continue

            entry_price = float(df["open"].iloc[entry_idx])
            if entry_price <= 0:
                continue

            # Stop: below EP day low
            stop_price = ep["day_low"] * 0.99

            # Classify Kelly tier (simplified — uses gap/vol/price)
            gap = ep["gap_pct"]
            vol_r = ep["vol_ratio"]
            avg_dollar_vol = float(df["close"].iloc[max(0,idx-50):idx].mean()) * float(df["volume"].iloc[max(0,idx-50):idx].mean()) if idx > 50 else 1e9
            is_micro = avg_dollar_vol < cfg.get("tier_max_dollar_vol", 5_000_000)

            if (is_micro and gap >= cfg.get("tier1_gap_micro", 30)) or gap >= cfg.get("tier1_gap_ti65", 20):
                tier = 1
                tier_label = "MAX"
            elif gap >= cfg.get("tier2_gap_any", 50) or (is_micro and ep.get("neglected") and gap >= cfg.get("tier2_gap_micro_neglected", 20)):
                tier = 2
                tier_label = "STRONG"
            elif (vol_r >= 5 and gap >= cfg.get("tier3_gap_vol5x", 20)) or vol_r >= cfg.get("tier3_vol_any", 10):
                tier = 3
                tier_label = "NORMAL"
            else:
                tier = 0
                tier_label = "WATCHLIST"

            # Simulate with trailing stop (current live strategy)
            trade = _simulate_trade_trailing(
                df, entry_idx, entry_price, stop_price,
                be_trigger_pct=be_trigger, trail_pct=trail_pct, max_hold=60,
            )
            trade["ticker"] = ticker
            trade["ep_date"] = ep["date"]
            trade["ep_type"] = ep_type
            trade["gap_pct"] = ep["gap_pct"]
            trade["vol_ratio"] = ep["vol_ratio"]
            trade["neglected"] = ep.get("neglected")
            trade["above_50ma"] = ep.get("above_50ma")
            trade["near_52w_high"] = ep.get("near_52w_high")
            trade["is_9m"] = ep.get("is_9m")
            trade["tier"] = tier
            trade["tier_label"] = tier_label
            trade["is_micro"] = is_micro

            all_trades.append(trade)

            # Also simulate with WIDE position-trade strategy (weekly MA trail)
            trade_wide = _simulate_trade_weekly_ma(
                df, entry_idx, entry_price, stop_price,
                ma_period=10, max_hold=252,
            )
            trade_wide["ticker"] = ticker
            trade_wide["ep_date"] = ep["date"]
            trade_wide["ep_type"] = ep_type
            trade_wide["gap_pct"] = ep["gap_pct"]
            trade_wide["vol_ratio"] = ep["vol_ratio"]
            trade_wide["tier"] = tier
            trade_wide["tier_label"] = tier_label
            all_trades_wide.append(trade_wide)

            # Also simulate with RATCHET strategy (winner-derived)
            trade_ratchet = _simulate_trade_ratchet(
                df, entry_idx, entry_price, stop_price, max_hold=252,
            )
            trade_ratchet["ticker"] = ticker
            trade_ratchet["ep_date"] = ep["date"]
            trade_ratchet["ep_type"] = ep_type
            trade_ratchet["gap_pct"] = ep["gap_pct"]
            trade_ratchet["vol_ratio"] = ep["vol_ratio"]
            trade_ratchet["tier"] = tier
            trade_ratchet["tier_label"] = tier_label
            all_trades_ratchet.append(trade_ratchet)

    # ── Aggregate statistics ─────────────────────────────────────────────────
    if not all_trades:
        return {
            "total_events": len(ep_events),
            "total_trades": 0,
            "message": "No EP events found in lookback period",
            "by_type": {},
            "overall": {},
        }

    trades_df = pd.DataFrame(all_trades)

    def _calc_stats(tdf: pd.DataFrame) -> dict:
        if len(tdf) == 0:
            return {}
        wins = tdf[tdf["pnl_pct"] > 0]
        losses = tdf[tdf["pnl_pct"] <= 0]
        avg_win = float(wins["pnl_pct"].mean()) if len(wins) > 0 else 0
        avg_loss = float(losses["pnl_pct"].mean()) if len(losses) > 0 else 0

        return {
            "total_trades": len(tdf),
            "win_rate": round(len(wins) / len(tdf) * 100, 1),
            "avg_return": round(float(tdf["pnl_pct"].mean()), 2),
            "median_return": round(float(tdf["pnl_pct"].median()), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "best_trade": round(float(tdf["pnl_pct"].max()), 2),
            "worst_trade": round(float(tdf["pnl_pct"].min()), 2),
            "avg_hold_days": round(float(tdf["hold_days"].mean()), 1),
            "avg_mfe": round(float(tdf["mfe_pct"].mean()), 2),
            "avg_mae": round(float(tdf["mae_pct"].mean()), 2),
            "profit_factor": round(abs(avg_win * len(wins)) / abs(avg_loss * len(losses)), 2) if len(losses) > 0 and avg_loss != 0 else 999,
            "expectancy": round(
                (len(wins) / len(tdf) * avg_win) + (len(losses) / len(tdf) * avg_loss), 2
            ),
            "exit_breakdown": {
                "stop": int((tdf["exit_reason"] == "stop").sum()),
                "breakeven": int((tdf["exit_reason"] == "breakeven").sum()),
                "trailing_stop": int((tdf["exit_reason"] == "trailing_stop").sum()),
                "target": int((tdf["exit_reason"] == "target").sum()),
                "timeout": int((tdf["exit_reason"] == "timeout").sum()),
            },
            "breakeven_rate": round(tdf["breakeven_hit"].sum() / len(tdf) * 100, 1) if "breakeven_hit" in tdf else None,
            # Multi-period returns
            "avg_return_1d": round(float(tdf["return_1d"].dropna().mean()), 2) if "return_1d" in tdf else None,
            "avg_return_3d": round(float(tdf["return_3d"].dropna().mean()), 2) if "return_3d" in tdf else None,
            "avg_return_5d": round(float(tdf["return_5d"].dropna().mean()), 2) if "return_5d" in tdf else None,
            "avg_return_10d": round(float(tdf["return_10d"].dropna().mean()), 2) if "return_10d" in tdf else None,
            "avg_return_20d": round(float(tdf["return_20d"].dropna().mean()), 2) if "return_20d" in tdf else None,
        }

    overall = _calc_stats(trades_df)

    # By EP type
    by_type = {}
    for ep_type in trades_df["ep_type"].unique():
        subset = trades_df[trades_df["ep_type"] == ep_type]
        by_type[ep_type] = _calc_stats(subset)

    # By Kelly tier (THE KEY OUTPUT — validates the current live tiers)
    by_tier = {}
    tier_names = {1: "MAX", 2: "STRONG", 3: "NORMAL", 0: "WATCHLIST"}
    for tier_num, tier_name in tier_names.items():
        subset = trades_df[trades_df["tier"] == tier_num]
        if len(subset) > 0:
            by_tier[tier_name] = _calc_stats(subset)

    # Actionable only (tiers 1-3, what we'd actually trade)
    actionable_df = trades_df[trades_df["tier"] >= 1]
    actionable_stats = _calc_stats(actionable_df) if len(actionable_df) > 0 else {}

    # Equity curve for actionable trades (simple: cumulative returns)
    equity_curve = []
    if len(actionable_df) > 0:
        sorted_trades = actionable_df.sort_values("ep_date")
        cum_return = 0
        for _, t in sorted_trades.iterrows():
            cum_return += t["pnl_pct"]
            equity_curve.append({
                "date": t["ep_date"],
                "ticker": t["ticker"],
                "pnl_pct": t["pnl_pct"],
                "cum_return": round(cum_return, 2),
                "tier": t["tier_label"],
            })

    # By gap size bucket
    trades_df["gap_bucket"] = pd.cut(trades_df["gap_pct"],
                                     bins=[0, 10, 15, 20, 30, 50, 100],
                                     labels=["10-15%", "15-20%", "20-30%", "30-50%", "50-100%", "100%+"],
                                     right=False)
    by_gap = {}
    for bucket in trades_df["gap_bucket"].unique():
        if pd.isna(bucket):
            continue
        subset = trades_df[trades_df["gap_bucket"] == bucket]
        by_gap[str(bucket)] = _calc_stats(subset)

    # By volume ratio bucket
    trades_df["vol_bucket"] = pd.cut(trades_df["vol_ratio"],
                                      bins=[0, 2, 3, 5, 10, 100],
                                      labels=["2-3x", "3-5x", "5-10x", "10x+", "100x+"],
                                      right=False)
    by_vol = {}
    for bucket in trades_df["vol_bucket"].unique():
        if pd.isna(bucket):
            continue
        subset = trades_df[trades_df["vol_bucket"] == bucket]
        by_vol[str(bucket)] = _calc_stats(subset)

    # By neglect status
    by_neglect = {}
    for val in [True, False]:
        subset = trades_df[trades_df["neglected"] == val]
        if len(subset) > 0:
            by_neglect["neglected" if val else "not_neglected"] = _calc_stats(subset)

    # By technical position
    by_tech = {}
    for val in [True, False]:
        subset = trades_df[trades_df["above_50ma"] == val]
        if len(subset) > 0:
            by_tech["above_50ma" if val else "below_50ma"] = _calc_stats(subset)

    # Near 52w high
    for val in [True, False]:
        subset = trades_df[trades_df["near_52w_high"] == val]
        if len(subset) > 0:
            by_tech["near_52w_high" if val else "not_near_high"] = _calc_stats(subset)

    # Sample trades (best and worst)
    sample_trades = []
    if len(trades_df) > 0:
        best = trades_df.nlargest(10, "pnl_pct")
        worst = trades_df.nsmallest(10, "pnl_pct")
        for _, row in pd.concat([best, worst]).iterrows():
            sample_trades.append({
                "ticker": row["ticker"],
                "ep_date": row["ep_date"],
                "ep_type": row["ep_type"],
                "gap_pct": row["gap_pct"],
                "vol_ratio": row["vol_ratio"],
                "entry_price": row["entry_price"],
                "exit_price": row["exit_price"],
                "pnl_pct": row["pnl_pct"],
                "hold_days": int(row["hold_days"]),
                "exit_reason": row["exit_reason"],
                "neglected": row.get("neglected"),
                "above_50ma": row.get("above_50ma"),
            })

    # Key insights
    insights = []
    if overall.get("win_rate", 0) > 55:
        insights.append(f"EP setups have a positive edge: {overall['win_rate']}% win rate")
    if overall.get("avg_return_1d", 0) > 1:
        insights.append(f"Strong 1-day follow-through: +{overall['avg_return_1d']}% avg next-day return")

    if "neglected" in by_neglect and "not_neglected" in by_neglect:
        negl_wr = by_neglect["neglected"].get("win_rate", 0)
        non_wr = by_neglect["not_neglected"].get("win_rate", 0)
        if negl_wr > non_wr + 5:
            insights.append(f"Neglected stocks outperform: {negl_wr}% vs {non_wr}% win rate")

    if "above_50ma" in by_tech and "below_50ma" in by_tech:
        above_wr = by_tech["above_50ma"].get("win_rate", 0)
        below_wr = by_tech["below_50ma"].get("win_rate", 0)
        if above_wr > below_wr + 5:
            insights.append(f"EPs above 50MA outperform: {above_wr}% vs {below_wr}% win rate")

    # Kelly tier insights
    for tier_name in ["MAX", "STRONG", "NORMAL", "WATCHLIST"]:
        if tier_name in by_tier:
            t = by_tier[tier_name]
            insights.append(
                f"{tier_name}: {t['total_trades']} trades, "
                f"{t['win_rate']}% WR, "
                f"{t['avg_return']:+.1f}% avg, "
                f"PF {t['profit_factor']}"
            )

    # Actionable vs watchlist comparison
    if actionable_stats and "WATCHLIST" in by_tier:
        act_exp = actionable_stats.get("expectancy", 0)
        watch_exp = by_tier["WATCHLIST"].get("expectancy", 0)
        if act_exp > watch_exp:
            insights.append(
                f"Tier filter works: actionable expectancy {act_exp:+.2f}% vs watchlist {watch_exp:+.2f}%"
            )

    # ── WIDE STRATEGY comparison (weekly MA trail, position trade) ──────────
    wide_stats = {}
    wide_by_tier = {}
    wide_actionable = {}
    wide_sample = []
    if all_trades_wide:
        wide_df = pd.DataFrame(all_trades_wide)
        wide_stats = _calc_stats(wide_df)

        for tier_num, tier_name in tier_names.items():
            subset = wide_df[wide_df["tier"] == tier_num]
            if len(subset) > 0:
                wide_by_tier[tier_name] = _calc_stats(subset)

        wide_act = wide_df[wide_df["tier"] >= 1]
        wide_actionable = _calc_stats(wide_act) if len(wide_act) > 0 else {}

        # Big winners (>100% gains)
        big_winners = wide_df[wide_df["pnl_pct"] >= 100]
        if len(big_winners) > 0:
            insights.append(
                f"WIDE STRATEGY: {len(big_winners)} trades with 100%+ returns "
                f"(avg {big_winners['pnl_pct'].mean():.0f}%, best {big_winners['pnl_pct'].max():.0f}%)"
            )

        # Wide vs narrow comparison
        if wide_actionable and actionable_stats:
            insights.append(
                f"SWING (15% trail): {actionable_stats.get('avg_return', 0):+.1f}% avg, "
                f"{actionable_stats.get('win_rate', 0):.0f}% WR"
            )
            insights.append(
                f"POSITION (10w MA): {wide_actionable.get('avg_return', 0):+.1f}% avg, "
                f"{wide_actionable.get('win_rate', 0):.0f}% WR, "
                f"hold {wide_actionable.get('avg_hold_days', 0):.0f}d"
            )

        # Top wide winners
        if len(wide_df) > 0:
            top_wide = wide_df.nlargest(10, "pnl_pct")
            for _, row in top_wide.iterrows():
                wide_sample.append({
                    "ticker": row["ticker"], "ep_date": row["ep_date"],
                    "pnl_pct": row["pnl_pct"], "hold_days": int(row["hold_days"]),
                    "exit_reason": row["exit_reason"], "tier": row["tier_label"],
                    "gap_pct": row["gap_pct"], "mfe_pct": row["mfe_pct"],
                })

    # ── RATCHET STRATEGY comparison (winner-derived) ─────────────────────
    ratchet_stats = {}
    ratchet_by_tier = {}
    ratchet_actionable = {}
    ratchet_sample = []
    if all_trades_ratchet:
        ratchet_df = pd.DataFrame(all_trades_ratchet)
        ratchet_stats = _calc_stats(ratchet_df)

        for tier_num, tier_name in tier_names.items():
            subset = ratchet_df[ratchet_df["tier"] == tier_num]
            if len(subset) > 0:
                ratchet_by_tier[tier_name] = _calc_stats(subset)

        ratchet_act = ratchet_df[ratchet_df["tier"] >= 1]
        ratchet_actionable = _calc_stats(ratchet_act) if len(ratchet_act) > 0 else {}

        # Big winners
        big_ratchet = ratchet_df[ratchet_df["pnl_pct"] >= 100]
        if len(big_ratchet) > 0:
            insights.append(
                f"RATCHET STRATEGY: {len(big_ratchet)} trades with 100%+ returns "
                f"(avg {big_ratchet['pnl_pct'].mean():.0f}%, best {big_ratchet['pnl_pct'].max():.0f}%)"
            )

        if ratchet_actionable:
            insights.append(
                f"RATCHET (winner-derived): {ratchet_actionable.get('avg_return', 0):+.1f}% avg, "
                f"{ratchet_actionable.get('win_rate', 0):.0f}% WR, "
                f"hold {ratchet_actionable.get('avg_hold_days', 0):.0f}d, "
                f"PF {ratchet_actionable.get('profit_factor', 0)}"
            )

        # Top ratchet winners
        if len(ratchet_df) > 0:
            top_ratchet = ratchet_df.nlargest(10, "pnl_pct")
            for _, row in top_ratchet.iterrows():
                ratchet_sample.append({
                    "ticker": row["ticker"], "ep_date": row["ep_date"],
                    "pnl_pct": row["pnl_pct"], "hold_days": int(row["hold_days"]),
                    "exit_reason": row["exit_reason"], "tier": row["tier_label"],
                    "gap_pct": row["gap_pct"], "mfe_pct": row["mfe_pct"],
                    "final_phase": row.get("final_phase", 0),
                })

    return {
        "total_events": len(ep_events),
        "total_trades": len(all_trades),
        "actionable_trades": len(actionable_df) if len(actionable_df) > 0 else 0,
        "lookback_days": lookback_days,
        "exit_strategy": f"BE at +{be_trigger}%, trail {trail_pct}%, max 60 days",
        "filters": "Price >= $2, no ETFs/funds, 9M needs 3% gap or 5% range",
        "overall": overall,
        "actionable_only": actionable_stats,
        "by_tier": by_tier,
        "by_type": by_type,
        "by_gap_size": by_gap,
        "by_volume_ratio": by_vol,
        "by_neglect": by_neglect,
        "by_technical_position": by_tech,
        "equity_curve": equity_curve,
        "sample_trades": sample_trades,
        "insights": insights,

        # ── WIDE STRATEGY (position trade) ──
        "wide_strategy": {
            "description": "10-week MA trail, BE at +10%, 25% hard stop, max 252 days",
            "overall": wide_stats,
            "actionable_only": wide_actionable,
            "by_tier": wide_by_tier,
            "top_winners": wide_sample,
        },

        # ── RATCHET STRATEGY (winner-derived) ──
        "ratchet_strategy": {
            "description": "Ratcheting trail: 25%→20%→15%→12% as gains grow, +10w MA secondary, max 252d",
            "overall": ratchet_stats,
            "actionable_only": ratchet_actionable,
            "by_tier": ratchet_by_tier,
            "top_winners": ratchet_sample,
        },

        "all_trades": [
            {k: v for k, v in t.items()
             if k not in ("gap_bucket", "vol_bucket")}
            for t in all_trades
        ],
    }


def run_ep_backtest_from_scan(lookback_days: int = 365) -> dict:
    """
    Convenience function: fetch bars and run EP backtest.
    Called from the API endpoint.
    """
    import os
    from scanner import fetch_bars, get_alpaca_client
    from universe_expander import get_scan_universe
    from watchlist import ETFS
    from sector_rs import SECTOR_ETFS

    all_tickers = get_scan_universe()
    all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
    stock_tickers = [t for t in all_tickers if t not in all_etfs]

    print(f"[ep-bt] Fetching bars for {len(stock_tickers)} stocks...")
    client = get_alpaca_client()

    if os.environ.get("POLYGON_API_KEY"):
        from polygon_client import fetch_bars as pg_bars
        bars = pg_bars(stock_tickers, days=max(500, lookback_days + 100),
                      interval="day", min_rows=50, label="ep-backtest")
    else:
        bars = fetch_bars(client, stock_tickers)

    print(f"[ep-bt] Got bars for {len(bars)} stocks, running backtest over {lookback_days} days...")
    result = backtest_eps(bars, lookback_days=lookback_days)
    print(f"[ep-bt] Complete: {result['total_trades']} trades from {result['total_events']} EP events")

    # Convert numpy types to native Python for JSON serialization
    def _sanitize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    return _sanitize(result)
