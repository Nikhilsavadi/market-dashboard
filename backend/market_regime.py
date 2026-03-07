"""
market_regime.py
----------------
Market health scoring modelled after oratnek's methodology:

  Score = % of positive signals across 43 ETFs, evaluated across:
    - Breadth & Trend Metrics  : SMA10, SMA20, SMA50, SMA200, 20>50, 50>200
    - Performance Overview     : % 1W, % 1M, % 3M, % 1Y, % YTD
    - 52-Week High proximity   : within 5% of 52w high
    - VIX                      : single global signal

Each metric per ETF generates ONE binary signal: Positive (1) or not (0).
Final score = positive_signals / total_signals * 100.

Thresholds:
  >= 60  -> Positive
  >= 40  -> Neutral
  <  40  -> Negative

Time-based signals (% 1W, % 1M, etc.) are Positive if return > 0.
"""

import os
from typing import Optional


# ---------------------------------------------------------------------------
# 43-ETF Universe
# ---------------------------------------------------------------------------
# Broad market (8)
_REGIME_ETFS_RAW = [
    # Core indices (equity only)
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "IWM",   # Russell 2000 small-cap
    "MDY",   # S&P 400 mid-cap
    "RSP",   # S&P 500 equal-weight (breadth check)
    "QQQE",  # Nasdaq 100 equal-weight
    # All 11 GICS sectors
    "XLK",   # Technology
    "XLF",   # Financials
    "XLE",   # Energy
    "XLV",   # Health Care
    "XLC",   # Communication Services
    "XLI",   # Industrials
    "XLB",   # Materials
    "XLP",   # Consumer Staples
    "XLRE",  # Real Estate
    "XLU",   # Utilities
    "XLY",   # Consumer Discretionary
    # Factor / style (equity only)
    "IWF",   # Russell 1000 Growth
    "IWD",   # Russell 1000 Value
    "MTUM",  # Momentum factor
]
# NOTE: Bonds, commodities, international, thematic ETFs excluded.
# They rise in risk-off and would inflate score when equities are weak.
# Deduplicate, preserve order -> exactly 43 unique
_seen: set = set()
REGIME_ETFS: list = []
for _e in _REGIME_ETFS_RAW:
    if _e not in _seen:
        _seen.add(_e)
        REGIME_ETFS.append(_e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_vix() -> Optional[float]:
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="2d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception as e:
        print(f"[market_regime] VIX fetch failed: {e}")
    return None


def _ytd_bars_back(closes) -> Optional[int]:
    """Estimate trading bars elapsed since Jan 1 of current year."""
    try:
        import pandas as pd
        if hasattr(closes, "index") and isinstance(closes.index, pd.DatetimeIndex):
            idx = closes.index
            year_start = pd.Timestamp(year=idx[-1].year, month=1, day=1, tz=idx[-1].tz)
            ytd_bars = int((idx >= year_start).sum())
            return ytd_bars if ytd_bars > 0 else None
    except Exception:
        pass
    # Fallback: ~50 trading days in if we have enough data
    return min(50, len(closes) - 1) if len(closes) > 20 else None


def _pct_return(closes, days_back: int) -> Optional[float]:
    if len(closes) <= days_back:
        return None
    try:
        end   = float(closes.iloc[-1])
        start = float(closes.iloc[-1 - days_back])
        if start == 0:
            return None
        return (end - start) / start * 100
    except Exception:
        return None


def score_etf(closes) -> tuple:
    """
    Score one ETF across all metrics using WEIGHTED signals.
    Short-term signals (1W, 1M, SMA10, SMA20) are weighted 3x
    Medium-term signals (3M, SMA50, 20>50) are weighted 2x
    Long-term signals (1Y, SMA200, 50>200, 52w high, YTD) are weighted 1x

    This ensures current market conditions dominate the score rather than
    being diluted by lagging long-term metrics from prior bull runs.
    """
    pos = 0.0
    tot = 0.0
    n   = len(closes)

    if n < 10:
        return 0, 0

    price = float(closes.iloc[-1])

    # -- SMA signals — weighted by recency ----------------------------------
    sma_values = {}
    sma_weights = {10: 5, 20: 4, 50: 2, 200: 1}  # sharply front-weighted
    for period, weight in sma_weights.items():
        if n >= period:
            sma = float(closes.iloc[-period:].mean())
            sma_values[period] = sma
            tot += weight
            if price > sma:
                pos += weight

    # MA cross signals
    if 20 in sma_values and 50 in sma_values:
        tot += 3  # medium-high weight
        if sma_values[20] > sma_values[50]:
            pos += 3

    if 50 in sma_values and 200 in sma_values:
        tot += 1  # low weight — very lagging
        if sma_values[50] > sma_values[200]:
            pos += 1

    # -- Performance signals — weighted by recency --------------------------
    perf_weights = {
        5:   5,   # 1W — highest weight, most current
        21:  4,   # 1M — high weight
        63:  2,   # 3M — medium weight
        252: 1,   # 1Y — lowest weight, very lagging
    }
    for days, weight in perf_weights.items():
        r = _pct_return(closes, days)
        if r is not None:
            tot += weight
            if r > 0:
                pos += weight

    # YTD — low weight (reset Jan 1, can be very stale mid-year)
    ytd_days = _ytd_bars_back(closes)
    if ytd_days and ytd_days > 0:
        r_ytd = _pct_return(closes, ytd_days)
        if r_ytd is not None:
            tot += 1
            if r_ytd > 0:
                pos += 1

    # -- 52-week high proximity — low weight (lags significantly) -----------
    lookback = min(252, n)
    if lookback >= 20:
        high_52w = float(closes.tail(lookback).max())
        tot += 1
        if high_52w > 0 and (price / high_52w) >= 0.95:
            pos += 1

    return pos, tot


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def oratnek_market_conditions(bars_data: dict) -> dict:
    """
    Compute market regime score using oratnek's binary-signal methodology.
    """
    total_pos    = 0
    total_sig    = 0
    etf_details  = {}
    etfs_scored  = 0
    etfs_skipped = []

    for etf in REGIME_ETFS:
        if etf not in bars_data:
            etfs_skipped.append(etf)
            continue

        df = bars_data[etf]
        closes = (df["close"] if hasattr(df, "columns") and "close" in df.columns else df).dropna()

        pos, tot = score_etf(closes)
        if tot == 0:
            etfs_skipped.append(etf)
            continue

        etfs_scored += 1
        total_pos   += pos
        total_sig   += tot

        etf_pct = round(pos / tot * 100)
        etf_details[etf] = {
            "positive": pos,
            "total":    tot,
            "pct":      etf_pct,
            "label":    "Positive" if etf_pct >= 60 else "Neutral" if etf_pct >= 40 else "Negative",
        }

    # -- VIX: single global signal -------------------------------------------
    vix       = get_vix()
    vix_label = None
    if vix is not None:
        total_sig += 3   # VIX weighted 3x — it's the most real-time fear signal
        if vix < 18:          # below 18 = healthy / risk-on (tighter than before)
            total_pos += 3
        if   vix < 15:  vix_label = "Complacent"
        elif vix < 18:  vix_label = "Low"
        elif vix < 22:  vix_label = "Normal"
        elif vix < 27:  vix_label = "Elevated"
        elif vix < 32:  vix_label = "High Fear"
        else:           vix_label = "Panic"

    # -- Final score ----------------------------------------------------------
    score = round(total_pos / total_sig * 100) if total_sig > 0 else 50
    # Tighter thresholds — weighted scoring means neutral band should be narrower
    label = "Positive" if score >= 55 else "Neutral" if score >= 45 else "Negative"

    # -- Regime gates ---------------------------------------------------------
    should_trade_longs  = score >= 45
    should_trade_shorts = score <= 55
    regime_warning = None
    if score < 35:
        regime_warning = "Market in distribution — long signals high risk"
    elif score < 48:
        regime_warning = "Market weakening — be selective with longs"

    # -- Breadth compat (used by scanner / frontend breadth display) ----------
    above_pos  = sum(1 for d in etf_details.values() if d["pct"] >= 60)
    above_high = sum(1 for d in etf_details.values() if d["pct"] >= 80)
    n_etfs     = len(etf_details)
    breadth_compat = {
        "breadth_50ma_pct": round(above_pos  / n_etfs * 100, 1) if n_etfs else None,
        "breadth_21ma_pct": round(above_pos  / n_etfs * 100, 1) if n_etfs else None,
        "new_highs_pct":    round(above_high / n_etfs * 100, 1) if n_etfs else None,
        "stocks_checked":   n_etfs,
    }

    # -- Index compat (used by frontend for SPY/QQQ/IWM price cards) ----------
    index_compat = {}
    for etf in ["SPY", "QQQ", "IWM", "RSP", "QQQE"]:
        if etf not in bars_data:
            continue
        df = bars_data[etf]
        closes = (df["close"] if hasattr(df, "columns") and "close" in df.columns else df).dropna()
        n = len(closes)
        if n < 2:
            continue
        price = float(closes.iloc[-1])
        def _ma(p):
            return float(closes.iloc[-p:].mean()) if n >= p else None
        ma21, ma50, ma200 = _ma(21), _ma(50), _ma(200)
        chg_1d = (price - float(closes.iloc[-2]))  / float(closes.iloc[-2])  * 100 if n > 1  else 0
        chg_1m = (price - float(closes.iloc[-21])) / float(closes.iloc[-21]) * 100 if n > 21 else 0
        chg_3m = (price - float(closes.iloc[-63])) / float(closes.iloc[-63]) * 100 if n > 63 else 0
        index_compat[etf] = {
            "price":           round(price, 2),
            "chg_1d":          round(chg_1d, 2),
            "chg_1m":          round(chg_1m, 2),
            "chg_3m":          round(chg_3m, 2),
            "above_ma21":      bool(ma21  and price > ma21),
            "above_ma50":      bool(ma50  and price > ma50),
            "above_ma200":     bool(ma200 and price > ma200),
            "dist_from_200ma": round((price - ma200) / ma200 * 100, 1) if ma200 else None,
            "ma21":            round(ma21,  2) if ma21  else None,
            "ma50":            round(ma50,  2) if ma50  else None,
            "ma200":           round(ma200, 2) if ma200 else None,
        }

    if etfs_skipped:
        print(f"[market_regime] ETFs skipped (no data): {etfs_skipped}")
    print(f"[market_regime] Scored {etfs_scored}/{len(REGIME_ETFS)} ETFs | "
          f"{total_pos}/{total_sig} positive signals | Score: {score} ({label})")

    return {
        # Core
        "score":            score,
        "label":            label,
        # Signal breakdown
        "etf_count":        etfs_scored,
        "positive_signals": total_pos,
        "total_signals":    total_sig,
        "etf_details":      etf_details,
        # VIX
        "vix":              vix,
        "vix_label":        vix_label,
        # Regime gates
        "should_trade_longs":  should_trade_longs,
        "should_trade_shorts": should_trade_shorts,
        "regime_warning":      regime_warning,
        # Compat keys used by scanner.py and frontend
        "breadth":          breadth_compat,
        "indices":          index_compat,
    }


# ---------------------------------------------------------------------------
# Regime gate + change detection
# ---------------------------------------------------------------------------

import json, os

_REGIME_STATE_FILE = "/tmp/regime_state.json"

# Tiered gate thresholds
def score_to_gate(score: int) -> str:
    if score >= 60: return "GO"
    if score >= 48: return "CAUTION"
    if score >= 35: return "WARN"
    return "DANGER"

# What the mode means for signal routing
GATE_MODE = {
    "GO":      "LONGS",        # full long playbook, normal size
    "CAUTION": "SELECTIVE",    # longs with tighter filter (RS>85, tier1 only)
    "WARN":    "EXITS_ONLY",   # no new longs; manage open positions only
    "DANGER":  "SHORTS",       # close longs; show short candidates only
}

GATE_SIZE = {
    "GO": 1.0, "CAUTION": 0.75, "WARN": 0.5, "DANGER": 0.25,
}

# Playbook messages for each transition
_TRANSITION_PLAYBOOK = {
    ("GO",      "CAUTION"): "⚠️ Market shifted CAUTION. Tighten filters: RS>85, tier-1 only, reduce size to 75%.",
    ("GO",      "WARN"):    "🟠 Market dropped to WARN. No new longs. Manage existing exits. Size 50%.",
    ("GO",      "DANGER"):  "🔴 Market in DANGER. Close longs, switch to short candidates. Extreme caution.",
    ("CAUTION", "GO"):      "🟢 Market recovered to GO. Full playbook active. Normal size.",
    ("CAUTION", "WARN"):    "🟠 Market weakening to WARN. No new longs. Trail stops, manage exits.",
    ("CAUTION", "DANGER"):  "🔴 Market in DANGER. Defensive mode. Consider closing longs.",
    ("WARN",    "GO"):      "🟢 Market recovered to GO. Cautiously re-engage longs.",
    ("WARN",    "CAUTION"): "🟡 Market recovering to CAUTION. Selective longs OK. 75% size.",
    ("WARN",    "DANGER"):  "🔴 Market deteriorating to DANGER. Exit longs. Short candidates only.",
    ("DANGER",  "WARN"):    "🟠 Market stabilising to WARN. Still no new longs but monitor closely.",
    ("DANGER",  "CAUTION"): "🟡 Recovery to CAUTION. Begin watching setups. 75% size.",
    ("DANGER",  "GO"):      "🟢 Strong recovery — GO. Re-engage full playbook carefully.",
}


def get_previous_regime() -> dict:
    """Read last stored regime state from disk."""
    try:
        with open(_REGIME_STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_regime_state(gate: str, score: int):
    """Persist current regime gate to disk."""
    try:
        with open(_REGIME_STATE_FILE, "w") as f:
            json.dump({"gate": gate, "score": score,
                       "date": str(__import__("datetime").date.today())}, f)
    except Exception:
        pass


def check_regime_change(new_score: int) -> dict:
    """
    Compare new score to previous state.
    Returns dict with change info and playbook action.
    Fires Telegram alert if regime gate has changed.
    """
    new_gate = score_to_gate(new_score)
    prev     = get_previous_regime()
    old_gate = prev.get("gate")

    result = {
        "new_gate":   new_gate,
        "old_gate":   old_gate,
        "changed":    old_gate is not None and old_gate != new_gate,
        "playbook":   None,
        "mode":       GATE_MODE[new_gate],
        "size":       GATE_SIZE[new_gate],
    }

    if result["changed"]:
        key      = (old_gate, new_gate)
        playbook = _TRANSITION_PLAYBOOK.get(key,
            f"Regime changed: {old_gate} → {new_gate}. Score: {new_score}.")
        result["playbook"] = playbook

        # Fire Telegram alert
        try:
            from alerts import _send
            msg = (
                f"<b>🚨 REGIME CHANGE: {old_gate} → {new_gate}</b>\n"
                f"Score: {new_score}/100\n\n"
                f"{playbook}"
            )
            _send(msg)
            print(f"[market_regime] Regime change alert sent: {old_gate} -> {new_gate}")
        except Exception as e:
            print(f"[market_regime] Alert failed: {e}")

    # Always update state
    save_regime_state(new_gate, new_score)
    return result


# Keep old name as alias so scanner.py import doesn't break
def enhanced_market_conditions(bars_data: dict, etf_tickers: set = None) -> dict:
    """
    Alias for oratnek_market_conditions.
    etf_tickers param accepted but ignored.
    """
    return oratnek_market_conditions(bars_data)
