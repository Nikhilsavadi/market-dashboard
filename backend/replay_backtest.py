from fetch_utils import fetch_bars_batch
"""
replay_backtest.py
------------------
Given a list of signals (from run_replay) and the full bars_data dict,
simulate each trade using trailing stop logic:

  - Entry:        closing price on signal date (or next available bar)
  - Initial stop: signal["stop_price"]
  - Trail:        activates once close >= entry * 1.03
                  trail level = lowest low of last 3 bars (updates daily)
  - Exit:         close below trail stop, OR 20-bar timeout
  - R multiple:   (exit_price - entry) / (entry - initial_stop)
  - Outcome:      WIN (R > 0), LOSS (R <= 0), TIMEOUT (20 bars, no stop hit)
"""

import pandas as pd
import numpy as np
from typing import Optional


def simulate_trade(
    ticker: str,
    entry_date: str,
    entry_price: float,
    initial_stop: float,
    bars: pd.DataFrame,
    max_bars: int = 20,
) -> dict:
    """
    Simulate one trade on `bars` (full history, daily OHLCV).
    bars must have columns: open, high, low, close, volume
    bars.index is DatetimeIndex sorted ascending.

    Returns a result dict with outcome metrics.
    """
    base = {
        "ticker":        ticker,
        "entry_date":    entry_date,
        "entry_price":   entry_price,
        "initial_stop":  initial_stop,
        "outcome":       "NO_DATA",
        "exit_price":    None,
        "exit_date":     None,
        "exit_reason":   None,
        "r_multiple":    None,
        "pct_gain":      None,
        "days_held":     None,
        "max_gain_pct":  None,
        "trail_activated": False,
        "bars_detail":   [],
    }

    if bars is None or bars.empty:
        return base

    if initial_stop is None or initial_stop <= 0:
        base["outcome"] = "NO_STOP"
        return base

    # Find bars AFTER entry date
    try:
        entry_ts  = pd.Timestamp(entry_date)
        future    = bars[bars.index > entry_ts].copy()
    except Exception:
        base["outcome"] = "DATE_ERROR"
        return base

    if future.empty:
        base["outcome"] = "NO_FUTURE_BARS"
        return base

    risk_per_share = entry_price - initial_stop
    if risk_per_share <= 0:
        base["outcome"] = "INVALID_STOP"
        return base

    trail_active   = False
    trail_stop     = initial_stop
    current_stop   = initial_stop
    max_close      = entry_price
    bars_held      = 0
    detail         = []

    # Need a rolling window that includes bars up to current point
    # We'll keep a small deque of recent lows
    recent_lows    = []

    for i, (dt, row) in enumerate(future.iterrows()):
        if bars_held >= max_bars:
            # Timeout exit at open of next bar — use close of last bar
            exit_price  = float(row["close"])
            exit_reason = "TIMEOUT"
            r_mult      = (exit_price - entry_price) / risk_per_share
            base.update({
                "outcome":      "TIMEOUT",
                "exit_price":   round(exit_price, 4),
                "exit_date":    str(dt.date()),
                "exit_reason":  "20-bar timeout",
                "r_multiple":   round(r_mult, 2),
                "pct_gain":     round((exit_price - entry_price) / entry_price * 100, 2),
                "days_held":    bars_held,
                "max_gain_pct": round((max_close - entry_price) / entry_price * 100, 2),
                "trail_activated": trail_active,
                "bars_detail":  detail,
            })
            return base

        close = float(row["close"])
        low   = float(row["low"])
        high  = float(row["high"])

        # Track max close for max_gain
        max_close = max(max_close, close)

        # Update rolling 3-bar low window
        recent_lows.append(low)
        if len(recent_lows) > 3:
            recent_lows.pop(0)

        # Check if trail should activate (close >= entry * 1.03)
        if not trail_active and close >= entry_price * 1.03:
            trail_active = True
            # Trail starts at lowest low of bars seen so far (max 3)
            trail_stop   = min(recent_lows)
            current_stop = trail_stop

        # Update trail stop if active (ratchet up only)
        if trail_active:
            new_trail = min(recent_lows)
            current_stop = max(current_stop, new_trail)  # trail only moves up

        # Check stop: exit if close below current stop
        if close < current_stop:
            exit_price  = close
            exit_reason = "TRAIL_STOP" if trail_active else "INITIAL_STOP"
            r_mult      = (exit_price - entry_price) / risk_per_share
            outcome     = "WIN" if r_mult > 0.1 else "LOSS"
            base.update({
                "outcome":      outcome,
                "exit_price":   round(exit_price, 4),
                "exit_date":    str(dt.date()),
                "exit_reason":  exit_reason,
                "r_multiple":   round(r_mult, 2),
                "pct_gain":     round((exit_price - entry_price) / entry_price * 100, 2),
                "days_held":    bars_held + 1,
                "max_gain_pct": round((max_close - entry_price) / entry_price * 100, 2),
                "trail_activated": trail_active,
                "bars_detail":  detail,
            })
            return base

        detail.append({
            "date":          str(dt.date()),
            "close":         round(close, 2),
            "stop":          round(current_stop, 2),
            "trail_active":  trail_active,
        })
        bars_held += 1

    # Ran out of bars before stop or timeout — still open
    last_close = float(future["close"].iloc[-1])
    r_mult     = (last_close - entry_price) / risk_per_share
    base.update({
        "outcome":      "OPEN",
        "exit_price":   round(last_close, 4),
        "exit_date":    str(future.index[-1].date()),
        "exit_reason":  "Still open / insufficient future bars",
        "r_multiple":   round(r_mult, 2),
        "pct_gain":     round((last_close - entry_price) / entry_price * 100, 2),
        "days_held":    bars_held,
        "max_gain_pct": round((max_close - entry_price) / entry_price * 100, 2),
        "trail_activated": trail_active,
        "bars_detail":  detail,
    })
    return base


def run_backtest_on_signals(
    signals: list,
    replay_date: str,
    max_bars: int = 20,
) -> dict:
    """
    Given a list of replay signals, fetch forward bars and simulate each trade.

    signals: list of dicts with ticker, price, stop_price fields
    replay_date: ISO date string e.g. "2023-10-26"
    Returns: { results: [...], summary: {...} }
    """

    if not signals:
        return {"results": [], "summary": {}}

    # Date range: from replay_date to replay_date + 60 calendar days
    # (covers 20 trading days + buffer)
    replay_ts   = pd.Timestamp(replay_date)
    end_date    = (replay_ts + pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    start_date  = (replay_ts - pd.Timedelta(days=5)).strftime("%Y-%m-%d")  # small lookback for 3-bar window seed

    tickers = list({s["ticker"] for s in signals if s.get("ticker") and s.get("stop_price")})
    if not tickers:
        return {"results": [], "summary": {}}

    print(f"[backtest] Fetching forward bars for {len(tickers)} tickers {start_date} -> {end_date}")

    bars_map = fetch_bars_batch(
        tickers,
        start      = start_date,
        end        = end_date,
        interval   = "1d",
        min_rows   = 2,
        batch_size = 50,
        label      = "backtest",
    )

    print(f"[backtest] Got bars for {len(bars_map)}/{len(tickers)} tickers")

    # Simulate each signal
    results = []
    for s in signals:
        ticker      = s.get("ticker")
        entry_price = s.get("price")
        stop_price  = s.get("stop_price")

        if not ticker or not entry_price or not stop_price:
            continue

        bars   = bars_map.get(ticker)
        result = simulate_trade(
            ticker       = ticker,
            entry_date   = replay_date,
            entry_price  = float(entry_price),
            initial_stop = float(stop_price),
            bars         = bars,
            max_bars     = max_bars,
        )

        # Attach signal metadata for display
        result["rs"]             = s.get("rs")
        result["vcs"]            = s.get("vcs")
        result["sector"]         = s.get("sector")
        result["signal_score"]   = s.get("signal_score")
        result["entry_readiness"]= s.get("entry_readiness")
        result["adr_pct"]        = s.get("adr_pct")
        result["ema21_low_pct"]  = s.get("ema21_low_pct")
        result["bouncing_from"]  = s.get("bouncing_from")
        result["three_weeks_tight"] = s.get("three_weeks_tight", False)
        results.append(result)

    # Summary stats
    completed  = [r for r in results if r["outcome"] in ("WIN", "LOSS", "TIMEOUT")]
    wins       = [r for r in completed if r["outcome"] == "WIN"]
    losses     = [r for r in completed if r["outcome"] in ("LOSS",)]
    timeouts   = [r for r in completed if r["outcome"] == "TIMEOUT"]

    r_multiples = [r["r_multiple"] for r in completed if r["r_multiple"] is not None]
    win_r       = [r["r_multiple"] for r in wins if r["r_multiple"] is not None]
    loss_r      = [r["r_multiple"] for r in losses if r["r_multiple"] is not None]

    summary = {
        "total":         len(results),
        "completed":     len(completed),
        "wins":          len(wins),
        "losses":        len(losses),
        "timeouts":      len(timeouts),
        "open":          len([r for r in results if r["outcome"] == "OPEN"]),
        "win_rate":      round(len(wins) / len(completed) * 100, 1) if completed else 0,
        "avg_r":         round(float(np.mean(r_multiples)), 2) if r_multiples else 0,
        "total_r":       round(float(np.sum(r_multiples)), 2) if r_multiples else 0,
        "avg_win_r":     round(float(np.mean(win_r)), 2) if win_r else 0,
        "avg_loss_r":    round(float(np.mean(loss_r)), 2) if loss_r else 0,
        "expectancy":    round(
            (len(wins)/len(completed) * float(np.mean(win_r)) if win_r else 0) +
            (len(losses)/len(completed) * float(np.mean(loss_r)) if loss_r else 0), 2
        ) if completed else 0,
        "trail_activated_pct": round(
            sum(1 for r in results if r["trail_activated"]) / len(results) * 100, 1
        ) if results else 0,
        "avg_days_held": round(float(np.mean([r["days_held"] for r in completed if r["days_held"]])), 1) if completed else 0,
    }

    # Sort by r_multiple desc (wins first)
    results.sort(key=lambda r: (r["r_multiple"] or -99), reverse=True)

    return {"results": results, "summary": summary}


# ─────────────────────────────────────────────────────────────────────────────
# CORRELATION ANALYSIS — batch replay across multiple dates
# ─────────────────────────────────────────────────────────────────────────────

def run_correlation_analysis(week_start: str, max_bars: int = 20) -> dict:
    """
    Given a single week-start date (Monday ISO string e.g. "2023-10-23"):
    1. Runs replay for that date (Monday scan)
    2. Backtests all long signals with trailing stop logic
    3. Returns per-trade results enriched with regime + readiness
       plus aggregated cross-tab: regime × readiness → win_rate, avg_r, profit_factor

    The caller (API endpoint) can aggregate across multiple weeks.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from scanner import run_replay

    print(f"\n[corr] Running replay for {week_start}...")
    try:
        replay = run_replay(week_start)
    except Exception as e:
        return {"error": str(e), "week": week_start}

    if "error" in replay:
        return {"error": replay["error"], "week": week_start}

    signals = replay.get("long_signals", [])
    market  = replay.get("market", {})
    regime_gate  = market.get("gate", "UNKNOWN")
    regime_score = market.get("score", 50)
    regime_mode  = market.get("mode", "UNKNOWN")
    vix          = market.get("vix")

    if not signals:
        return {
            "week":          week_start,
            "regime_gate":   regime_gate,
            "regime_score":  regime_score,
            "regime_mode":   regime_mode,
            "vix":           vix,
            "total_signals": 0,
            "trades":        [],
            "summary":       {},
        }

    # Run backtest
    print(f"[corr] Backtesting {len(signals)} signals for {week_start}...")
    bt = run_backtest_on_signals(signals, week_start, max_bars=max_bars)
    trades = bt.get("results", [])

    # Enrich each trade with regime context
    for t in trades:
        t["week"]          = week_start
        t["regime_gate"]   = regime_gate
        t["regime_score"]  = regime_score
        t["regime_mode"]   = regime_mode
        t["vix"]           = vix
        # Normalise readiness to int bucket
        er = t.get("entry_readiness")
        t["readiness_bucket"] = int(round(er)) if er is not None else 0

    return {
        "week":          week_start,
        "regime_gate":   regime_gate,
        "regime_score":  regime_score,
        "regime_mode":   regime_mode,
        "vix":           vix,
        "total_signals": len(signals),
        "trades":        trades,
        "summary":       bt.get("summary", {}),
    }


def aggregate_correlation(weeks_data: list) -> dict:
    """
    Given list of run_correlation_analysis() results (one per week),
    aggregate into:
      - all_trades: flat list of every simulated trade
      - cross_tab: dict keyed (regime_gate, readiness_bucket) → metrics
      - equity_curve: list of {trade_n, equity, week, ticker, r}
      - profit_factor: total wins R / abs(total losses R)
      - overall summary
    """
    all_trades = []
    for week_data in weeks_data:
        all_trades.extend(week_data.get("trades", []))

    if not all_trades:
        return {"all_trades": [], "cross_tab": [], "equity_curve": [], "summary": {}}

    completed = [t for t in all_trades if t.get("outcome") in ("WIN", "LOSS", "TIMEOUT")]

    # ── Cross-tab: regime × readiness ────────────────────────────────────────
    from collections import defaultdict
    buckets = defaultdict(list)
    for t in completed:
        key = (t.get("regime_gate", "UNKNOWN"), t.get("readiness_bucket", 0))
        buckets[key].append(t)

    cross_tab = []
    for (gate, readiness), trades in sorted(buckets.items()):
        r_vals   = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
        wins     = [r for r in r_vals if r > 0.1]
        losses   = [r for r in r_vals if r <= 0.1]
        win_r    = sum(wins)
        loss_r   = abs(sum(losses)) if losses else 0
        pf       = round(win_r / loss_r, 2) if loss_r > 0 else (99.0 if win_r > 0 else 0.0)
        avg_r    = round(float(np.mean(r_vals)), 2) if r_vals else 0
        exp      = round(
            (len(wins)/len(r_vals) * float(np.mean(wins)) if wins else 0) +
            (len(losses)/len(r_vals) * float(np.mean(losses)) if losses else 0), 2
        ) if r_vals else 0

        cross_tab.append({
            "regime_gate":     gate,
            "readiness":       readiness,
            "trades":          len(trades),
            "wins":            len(wins),
            "losses":          len(losses),
            "win_rate":        round(len(wins) / len(r_vals) * 100, 1) if r_vals else 0,
            "avg_r":           avg_r,
            "total_r":         round(sum(r_vals), 2),
            "profit_factor":   pf,
            "expectancy":      exp,
            "avg_days_held":   round(float(np.mean([t["days_held"] for t in trades if t.get("days_held")])), 1),
            "trail_pct":       round(sum(1 for t in trades if t.get("trail_activated")) / len(trades) * 100, 1),
        })

    # Sort: GO first, then readiness desc within regime
    gate_order = {"GO": 0, "CAUTION": 1, "WARN": 2, "DANGER": 3, "UNKNOWN": 4}
    cross_tab.sort(key=lambda x: (gate_order.get(x["regime_gate"], 9), -x["readiness"]))

    # ── Equity curve: $10k starting, fixed 1% risk per trade ─────────────────
    equity       = 10000.0
    risk_pct     = 0.01          # 1% of equity risked per trade
    equity_curve = [{"n": 0, "equity": round(equity, 2), "week": "", "ticker": "START", "r": 0}]

    # Sort trades chronologically by entry_date
    time_ordered = sorted(completed, key=lambda t: t.get("entry_date", ""))
    for i, t in enumerate(time_ordered):
        r = t.get("r_multiple") or 0
        risk_amt = equity * risk_pct
        equity  += risk_amt * r
        equity   = max(equity, 0)  # can't go below 0
        equity_curve.append({
            "n":       i + 1,
            "equity":  round(equity, 2),
            "week":    t.get("week", ""),
            "ticker":  t.get("ticker", ""),
            "r":       round(r, 2),
            "outcome": t.get("outcome", ""),
            "regime":  t.get("regime_gate", ""),
            "readiness": t.get("readiness_bucket", 0),
        })

    # ── Overall summary ───────────────────────────────────────────────────────
    r_vals  = [t["r_multiple"] for t in completed if t.get("r_multiple") is not None]
    wins_r  = [r for r in r_vals if r > 0.1]
    loss_r  = [r for r in r_vals if r <= 0.1]
    pf_all  = round(sum(wins_r) / abs(sum(loss_r)), 2) if loss_r else (99.0 if wins_r else 0)

    summary = {
        "total_trades":    len(completed),
        "total_weeks":     len(weeks_data),
        "wins":            len(wins_r),
        "losses":          len([r for r in r_vals if r <= 0.1]),
        "win_rate":        round(len(wins_r) / len(r_vals) * 100, 1) if r_vals else 0,
        "avg_r":           round(float(np.mean(r_vals)), 2) if r_vals else 0,
        "total_r":         round(sum(r_vals), 2),
        "profit_factor":   pf_all,
        "expectancy":      round(
            (len(wins_r)/len(r_vals) * float(np.mean(wins_r)) if wins_r else 0) +
            (len([r for r in r_vals if r <= 0.1])/len(r_vals) * float(np.mean([r for r in r_vals if r <= 0.1])) if [r for r in r_vals if r <= 0.1] else 0), 2
        ) if r_vals else 0,
        "final_equity":    round(equity_curve[-1]["equity"], 2) if equity_curve else 10000,
        "equity_growth_pct": round((equity_curve[-1]["equity"] - 10000) / 10000 * 100, 1) if equity_curve else 0,
        "max_drawdown_pct": _max_drawdown(equity_curve),
    }

    return {
        "all_trades":   all_trades,
        "cross_tab":    cross_tab,
        "equity_curve": equity_curve,
        "summary":      summary,
        "weeks_data":   [{"week": w["week"], "regime_gate": w.get("regime_gate"),
                          "regime_score": w.get("regime_score"), "total_signals": w.get("total_signals", 0),
                          "summary": w.get("summary", {})} for w in weeks_data],
    }


def _max_drawdown(equity_curve: list) -> float:
    """Calculate max drawdown % from equity curve."""
    if len(equity_curve) < 2:
        return 0.0
    equities  = [e["equity"] for e in equity_curve]
    peak      = equities[0]
    max_dd    = 0.0
    for e in equities:
        peak   = max(peak, e)
        dd     = (peak - e) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return round(max_dd, 1)