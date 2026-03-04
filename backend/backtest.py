"""
backtest.py
-----------
Backtests historical signals using realistic ATR-based exits.

Realism improvements vs naive version:
  1. Entry at NEXT DAY'S OPEN — not signal close price
  2. Slippage: 0.1% per leg (entry + exit) = 0.2% round-trip
  3. Max hold extended to 25 bars (VCP/flag setups often take 15-25 days)
  4. MAE/MFE tracking: max adverse excursion and max favourable excursion
     per trade — essential for stop placement calibration
  5. R-multiple PnL: every trade expressed as multiples of 1R (1.5×ATR)

Exit logic:
  - Stop:     entry - 1.5×ATR (stop loss)
  - Target 1: entry + 1.5×ATR  (1R)
  - Target 2: entry + 3.0×ATR  (2R)
  - Target 3: entry + 5.0×ATR  (3.33R)
  - MA21 cross: close below MA21 × 0.99 (trend breakdown)
  - Timeout:  25 bars max hold
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional

from database import get_signal_history, save_backtest, get_conn
from base_detector import calculate_atr

# ── Config ─────────────────────────────────────────────────────────────────────

STOP_MULT   = 1.5
T1_MULT     = 1.5
T2_MULT     = 3.0
T3_MULT     = 5.0
MAX_HOLD    = 25          # bars — extended from 10 to capture full moves
SLIPPAGE    = 0.001       # 0.1% per leg (entry + exit = 0.2% round-trip)


# ── Public entry point ────────────────────────────────────────────────────────

def run_backtest(bars_data: dict, signal_type: str = None) -> list[dict]:
    """
    Run backtest for all signals in history.
    bars_data: the full OHLCV data dict from scanner.
    signal_type: filter by MA10/MA21/MA50/SHORT or None for all.
    """
    signals = get_signal_history(days=365)
    if signal_type:
        signals = [s for s in signals if s.get("signal_type") == signal_type]

    if not signals:
        print(f"[backtest] No signals found for type={signal_type}")
        return []

    results = []
    for sig in signals:
        result = _simulate_trade(sig, bars_data)
        if result:
            results.append(result)

    if not results:
        return []

    # Aggregate stats per signal type
    by_type: dict = {}
    for r in results:
        st = r["signal_type"] or "UNKNOWN"
        by_type.setdefault(st, []).append(r)

    summaries = []
    for st, trades in by_type.items():
        summary = _summarise(st, trades)
        save_backtest(summary)
        summaries.append(summary)

    return summaries


# ── Core simulation ───────────────────────────────────────────────────────────

def _simulate_trade(signal: dict, bars_data: dict) -> Optional[dict]:
    """
    Simulate a single trade from a historical signal.

    Key changes vs v1:
    - Enters at NEXT DAY'S OPEN (+ slippage), not signal-day close
    - Slippage applied on entry and exit
    - Tracks MAE (max adverse) and MFE (max favourable) excursion
    - Max hold extended to 25 bars
    """
    ticker      = signal.get("ticker")
    signal_date = signal.get("scan_date")
    atr         = signal.get("atr")

    if not ticker or not signal_date:
        return None
    if ticker not in bars_data:
        return None

    df     = bars_data[ticker]
    opens  = df.get("open",  df["close"])
    closes = df["close"]
    highs  = df.get("high", df["close"])
    lows   = df.get("low",  df["close"])

    # Find signal date index
    try:
        sig_ts    = pd.Timestamp(signal_date)
        sig_idx   = closes.index.searchsorted(sig_ts)
        entry_idx = sig_idx + 1             # ← next bar = realistic entry
        if entry_idx >= len(closes) - 1:
            return None                     # not enough future data
    except Exception:
        return None

    # ATR at signal date
    if not atr or atr <= 0:
        atr = _calc_atr_at_idx(df, sig_idx)
    if not atr:
        return None

    # Entry price = next-day open + slippage
    is_short    = signal.get("signal_type") == "SHORT"
    raw_entry   = float(opens.iloc[entry_idx])
    entry_price = raw_entry * (1 + SLIPPAGE) if not is_short else raw_entry * (1 - SLIPPAGE)

    stop   = entry_price - STOP_MULT * atr if not is_short else entry_price + STOP_MULT * atr
    t1     = entry_price + T1_MULT * atr   if not is_short else entry_price - T1_MULT * atr
    t2     = entry_price + T2_MULT * atr   if not is_short else entry_price - T2_MULT * atr
    t3     = entry_price + T3_MULT * atr   if not is_short else entry_price - T3_MULT * atr
    ma21   = signal.get("ma21")
    risk_r = abs(entry_price - stop)       # 1R in price terms

    exit_price  = None
    exit_reason = None
    hold_days   = 0

    # MAE / MFE tracking
    mae = 0.0   # worst intrabar move against us (in price, positive = bad)
    mfe = 0.0   # best intrabar move in our favour (in price, positive = good)

    # Walk forward bar by bar from entry+1
    for i in range(1, min(MAX_HOLD + 1, len(closes) - entry_idx)):
        idx       = entry_idx + i
        bar_high  = float(highs.iloc[idx])
        bar_low   = float(lows.iloc[idx])
        bar_close = float(closes.iloc[idx])
        hold_days = i

        if not is_short:
            # Update MAE/MFE
            mae = max(mae, entry_price - bar_low)    # how far it went against us
            mfe = max(mfe, bar_high - entry_price)   # how far it went in our favour

            if bar_low <= stop:
                exit_price  = stop * (1 - SLIPPAGE)
                exit_reason = "stop"
                break
            elif bar_high >= t3:
                exit_price  = t3 * (1 - SLIPPAGE)
                exit_reason = "target3"
                break
            elif bar_high >= t2:
                exit_price  = t2 * (1 - SLIPPAGE)
                exit_reason = "target2"
                break
            elif bar_high >= t1:
                exit_price  = t1 * (1 - SLIPPAGE)
                exit_reason = "target1"
                break
            elif ma21 and bar_close < ma21 * 0.99:
                exit_price  = bar_close * (1 - SLIPPAGE)
                exit_reason = "ma21_cross"
                break
        else:
            # Short: MAE is upward moves, MFE is downward moves
            mae = max(mae, bar_high - entry_price)
            mfe = max(mfe, entry_price - bar_low)

            if bar_high >= stop:
                exit_price  = stop * (1 + SLIPPAGE)
                exit_reason = "stop"
                break
            elif bar_low <= t3:
                exit_price  = t3 * (1 + SLIPPAGE)
                exit_reason = "target3"
                break
            elif bar_low <= t2:
                exit_price  = t2 * (1 + SLIPPAGE)
                exit_reason = "target2"
                break
            elif bar_low <= t1:
                exit_price  = t1 * (1 + SLIPPAGE)
                exit_reason = "target1"
                break
            elif ma21 and bar_close > ma21 * 1.01:
                exit_price  = bar_close * (1 + SLIPPAGE)
                exit_reason = "ma21_cross"
                break

    # Timeout exit
    if exit_price is None:
        raw_exit    = float(closes.iloc[min(entry_idx + MAX_HOLD, len(closes) - 1)])
        exit_price  = raw_exit * (1 - SLIPPAGE) if not is_short else raw_exit * (1 + SLIPPAGE)
        exit_reason = "timeout"

    # PnL
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    if is_short:
        pnl_pct = -pnl_pct
    pnl_r = round(pnl_pct / (risk_r / entry_price * 100), 2) if risk_r > 0 else 0

    # MAE/MFE as R multiples and percentages
    mae_r   = round(mae / risk_r, 2) if risk_r > 0 else 0
    mfe_r   = round(mfe / risk_r, 2) if risk_r > 0 else 0
    mae_pct = round(mae / entry_price * 100, 2)
    mfe_pct = round(mfe / entry_price * 100, 2)

    return {
        "ticker":       ticker,
        "signal_type":  signal.get("signal_type"),
        "signal_date":  signal_date,
        "entry_price":  round(entry_price, 4),
        "exit_price":   round(exit_price, 4),
        "exit_reason":  exit_reason,
        "hold_days":    hold_days,
        "pnl_pct":      round(pnl_pct, 2),
        "pnl_r":        pnl_r,
        "atr":          round(atr, 4),
        "stop":         round(stop, 4),
        "t1":           round(t1, 4),
        "t2":           round(t2, 4),
        "t3":           round(t3, 4),
        "mae_pct":      mae_pct,       # max adverse excursion %
        "mae_r":        mae_r,         # max adverse excursion in R
        "mfe_pct":      mfe_pct,       # max favourable excursion %
        "mfe_r":        mfe_r,         # max favourable excursion in R
        "vcs":          signal.get("vcs"),
        "rs":           signal.get("rs"),
        "slippage_pct": round(SLIPPAGE * 200, 3),  # 2-leg round trip
    }


# ── Summary stats ─────────────────────────────────────────────────────────────

def _summarise(signal_type: str, trades: list[dict]) -> dict:
    """Aggregate a list of trade results into summary stats including MAE/MFE."""
    pnls      = [t["pnl_pct"]   for t in trades]
    pnl_rs    = [t["pnl_r"]     for t in trades if t.get("pnl_r") is not None]
    hold_days = [t["hold_days"] for t in trades]
    mae_rs    = [t["mae_r"]     for t in trades if t.get("mae_r") is not None]
    mfe_rs    = [t["mfe_r"]     for t in trades if t.get("mfe_r") is not None]

    wins    = [p for p in pnls if p > 0]
    losses  = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100 if pnls else 0
    avg_hold = np.mean(hold_days) if hold_days else 5

    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses)) if losses else 1
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0

    sharpe = 0
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = round(np.mean(pnls) / np.std(pnls) * np.sqrt(252 / max(avg_hold, 1)), 2)

    # MAE analysis: what % of stopped trades were hit by noise
    # (went < 1R against us before stopping — suggests stop too tight or normal noise)
    stopped = [t for t in trades if t.get("exit_reason") == "stop"]
    noise_stops = [t for t in stopped if t.get("mae_r", 99) <= 1.0]
    noise_stop_pct = round(len(noise_stops) / len(stopped) * 100, 1) if stopped else 0

    exit_counts: dict = {}
    for t in trades:
        r = t.get("exit_reason", "unknown")
        exit_counts[r] = exit_counts.get(r, 0) + 1

    return {
        "run_date":        date.today().isoformat(),
        "signal_type":     signal_type,
        "total_signals":   len(trades),
        "win_rate":        round(win_rate, 1),
        "avg_return_pct":  round(np.mean(pnls), 2) if pnls else 0,
        "avg_return_r":    round(np.mean(pnl_rs), 2) if pnl_rs else 0,
        "avg_hold_days":   round(avg_hold, 1),
        "best_trade_pct":  round(max(pnls), 2) if pnls else 0,
        "worst_trade_pct": round(min(pnls), 2) if pnls else 0,
        "profit_factor":   profit_factor,
        "sharpe":          sharpe,
        "exit_breakdown":  exit_counts,
        # MAE/MFE summary
        "mae_analysis": {
            "avg_mae_r":       round(np.mean(mae_rs), 2) if mae_rs else 0,
            "median_mae_r":    round(float(np.median(mae_rs)), 2) if mae_rs else 0,
            "avg_mfe_r":       round(np.mean(mfe_rs), 2) if mfe_rs else 0,
            "median_mfe_r":    round(float(np.median(mfe_rs)), 2) if mfe_rs else 0,
            "stopped_trades":  len(stopped),
            "noise_stops":     len(noise_stops),
            "noise_stop_pct":  noise_stop_pct,
            "note": (
                f"{noise_stop_pct}% of stopped trades never went more than 1R against you "
                f"before triggering — {'stop placement looks good' if noise_stop_pct < 40 else 'consider widening stops, high noise-stop rate'}"
            ),
        },
        "params": {
            "stop_atr_mult":   STOP_MULT,
            "t1_atr_mult":     T1_MULT,
            "t2_atr_mult":     T2_MULT,
            "t3_atr_mult":     T3_MULT,
            "max_hold_days":   MAX_HOLD,
            "slippage_pct":    SLIPPAGE * 100,
            "entry":           "next_open",
            "ma21_cross_exit": True,
        },
        "trades": trades,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc_atr_at_idx(df: pd.DataFrame, idx: int, period: int = 14) -> Optional[float]:
    """Calculate ATR using the N bars before idx."""
    if idx < period:
        return None
    sub = df.iloc[max(0, idx - period - 1):idx]
    return calculate_atr(sub)
