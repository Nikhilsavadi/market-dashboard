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
    Simulate a trade from entry_idx forward.
    Returns trade result dict.
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

    all_trades = []
    ep_events = []

    for ticker, df in bars_data.items():
        if df is None or len(df) < 60:
            continue

        n = len(df)
        start_idx = max(50, n - lookback_days)

        for idx in range(start_idx, n - 1):  # -1 because we need next day for entry
            ep = _detect_ep_day(df, idx, cfg)
            if ep is None:
                continue

            ep["ticker"] = ticker

            # Determine EP type
            ep_type = "CLASSIC"
            if ep["is_9m"] and ep["gap_pct"] < 5:
                ep_type = "9M"
            elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
                ep_type = "STORY"  # Gap without neglect = likely story

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

            # Target: 2x gap magnitude from entry
            target_pct = ep["gap_pct"]  # e.g., if gap was 15%, target is +15% from entry

            trade = _simulate_trade(df, entry_idx, entry_price, stop_price,
                                    target_pct=max(10, target_pct), max_hold=20)
            trade["ticker"] = ticker
            trade["ep_date"] = ep["date"]
            trade["ep_type"] = ep_type
            trade["gap_pct"] = ep["gap_pct"]
            trade["vol_ratio"] = ep["vol_ratio"]
            trade["neglected"] = ep.get("neglected")
            trade["above_50ma"] = ep.get("above_50ma")
            trade["near_52w_high"] = ep.get("near_52w_high")
            trade["is_9m"] = ep.get("is_9m")

            all_trades.append(trade)

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
                "target": int((tdf["exit_reason"] == "target").sum()),
                "timeout": int((tdf["exit_reason"] == "timeout").sum()),
            },
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

    return {
        "total_events": len(ep_events),
        "total_trades": len(all_trades),
        "lookback_days": lookback_days,
        "overall": overall,
        "by_type": by_type,
        "by_gap_size": by_gap,
        "by_volume_ratio": by_vol,
        "by_neglect": by_neglect,
        "by_technical_position": by_tech,
        "sample_trades": sample_trades,
        "insights": insights,
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

    print(f"[ep-bt] Running backtest over {lookback_days} days...")
    result = backtest_eps(bars, lookback_days=lookback_days)
    print(f"[ep-bt] Complete: {result['total_trades']} trades from {result['total_events']} EP events")

    return result
