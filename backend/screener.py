"""
screener.py
-----------
V3: EMA entry signals, weekly timeframe confirmation, proper VCS (oratnek methodology),
    Mansfield-weighted RS replacing simple 1Y percentile rank.
"""

import numpy as np
import pandas as pd
from typing import Optional
from base_detector import detect_ll_hl_pivot, detect_darvas_box, detect_flag_pennant


def calculate_mas(closes: pd.Series) -> dict:
    """
    Entry-signal MAs: EMA10, EMA21, EMA50 — faster response for swing entries.
    Trend anchor: SMA200 — kept as SMA intentionally (long-term structural level,
    should NOT be reactive to short-term noise).
    Slopes use the EMA series directly for accuracy.
    """
    result = {
        "ma10": None, "ma21": None, "ma50": None, "ma200": None,
        "ma21_slope": None, "ma50_slope": None,
    }

    if len(closes) >= 10:
        ema10_series   = closes.ewm(span=10, adjust=False).mean()
        result["ma10"] = round(float(ema10_series.iloc[-1]), 4)

    if len(closes) >= 21:
        ema21_series   = closes.ewm(span=21, adjust=False).mean()
        result["ma21"] = round(float(ema21_series.iloc[-1]), 4)

    if len(closes) >= 50:
        ema50_series   = closes.ewm(span=50, adjust=False).mean()
        result["ma50"] = round(float(ema50_series.iloc[-1]), 4)

    # SMA200 — structural anchor, deliberately NOT an EMA
    if len(closes) >= 200:
        result["ma200"] = round(float(closes.iloc[-200:].mean()), 4)

    # Slope: % change of EMA over last 5 bars (~1 trading week)
    SLOPE_BARS = 5
    if len(closes) >= 21 + SLOPE_BARS:
        ema21_s = closes.ewm(span=21, adjust=False).mean()
        prev    = float(ema21_s.iloc[-(1 + SLOPE_BARS)])
        if prev > 0 and result["ma21"]:
            result["ma21_slope"] = round((result["ma21"] - prev) / prev * 100, 3)

    if len(closes) >= 50 + SLOPE_BARS:
        ema50_s = closes.ewm(span=50, adjust=False).mean()
        prev    = float(ema50_s.iloc[-(1 + SLOPE_BARS)])
        if prev > 0 and result["ma50"]:
            result["ma50_slope"] = round((result["ma50"] - prev) / prev * 100, 3)

    return result


def calculate_weekly_mas(weekly_closes: pd.Series) -> dict:
    """
    Weekly timeframe MAs for higher-timeframe trend confirmation.
    wEMA10 ≈ daily EMA50, wEMA40 ≈ daily SMA200.
    Hard gate in is_long_signal: price must be above wEMA10 and wEMA10 > wEMA40.
    """
    result = {
        "w_ema10": None, "w_ema40": None,
        "w_stack_ok": False,
        "w_above_ema10": False,
        "w_above_ema40": False,
        "w_ema10_slope": None,
    }
    if weekly_closes is None or len(weekly_closes) < 12:
        return result

    price = float(weekly_closes.iloc[-1])

    if len(weekly_closes) >= 10:
        s10               = weekly_closes.ewm(span=10, adjust=False).mean()
        result["w_ema10"] = round(float(s10.iloc[-1]), 4)
        result["w_above_ema10"] = price > result["w_ema10"]
        if len(s10) >= 3:
            prev = float(s10.iloc[-3])
            if prev > 0:
                result["w_ema10_slope"] = round((result["w_ema10"] - prev) / prev * 100, 3)

    if len(weekly_closes) >= 40:
        s40               = weekly_closes.ewm(span=40, adjust=False).mean()
        result["w_ema40"] = round(float(s40.iloc[-1]), 4)
        result["w_above_ema40"] = price > result["w_ema40"]

    if result["w_ema10"] and result["w_ema40"]:
        result["w_stack_ok"] = bool(
            price > result["w_ema10"] and result["w_ema10"] > result["w_ema40"]
        )
    elif result["w_ema10"]:
        # <40 weekly bars — pass on wEMA10 alone
        result["w_stack_ok"] = bool(price > result["w_ema10"])

    return result


def calculate_core_stats(df: pd.DataFrame, weekly_closes: pd.Series = None,
                         w_ema10: float = None) -> dict:
    """
    Core Stats — Nik's entry validity filter.

    Returns:
      adr_pct          — Average Daily Range % over 21 days (target: 3.5–8%)
      atr21            — ATR(14) value (same as main atr field)
      ema21_low        — Lowest EMA21 value over last 10 bars (stop-loss anchor)
      ema21_low_pct    — Distance from price to ema21_low as % of price
                         (<5% = low risk, >8% = too risky)
      within_1atr_ema21  — Price within 1×ATR of EMA21 (entry ceiling check)
      within_1atr_wema10 — Price within 1×ATR of weekly EMA10 (weekly ceiling)
      within_3atr_sma50  — Price within 3×ATR of SMA50 (SMA50 ceiling)
      three_weeks_tight  — Last 3 weekly closes within 1.5% of each other
    """
    result = {
        "adr_pct": None, "ema21_low": None, "ema21_low_pct": None,
        "within_1atr_ema21": None, "within_1atr_wema10": None,
        "within_3atr_sma50": None, "three_weeks_tight": False,
        "entry_readiness": None,
    }
    try:
        closes = df["close"]
        highs  = df.get("high", closes)
        lows   = df.get("low",  closes)
        price  = float(closes.iloc[-1])

        # ── ADR % (21-day average of daily high-low range as % of low) ─────
        if len(highs) >= 21 and len(lows) >= 21:
            ranges = ((highs - lows) / lows * 100).iloc[-21:]
            result["adr_pct"] = round(float(ranges.mean()), 2)

        # ── EMA21 series ────────────────────────────────────────────────────
        if len(closes) >= 21:
            ema21_series = closes.ewm(span=21, adjust=False).mean()
            ema21_now    = float(ema21_series.iloc[-1])

            # EMA21 Low = lowest EMA21 value over last 10 bars
            ema21_low = float(ema21_series.iloc[-10:].min())
            result["ema21_low"] = round(ema21_low, 2)
            if price > 0:
                result["ema21_low_pct"] = round((price - ema21_low) / price * 100, 2)

            # ── ATR for ceiling checks ───────────────────────────────────────
            atr = calculate_atr_series(df, period=14)
            if atr and atr > 0:
                # ATR 21 EMA ceiling: price within 1×ATR above EMA21
                result["within_1atr_ema21"] = bool(price <= ema21_now + 1.0 * atr)

                # ATR 50 SMA ceiling: price within 3×ATR above SMA50
                if len(closes) >= 50:
                    sma50 = float(closes.iloc[-50:].mean())
                    result["within_3atr_sma50"] = bool(price <= sma50 + 3.0 * atr)

                # ATR 10 WMA (weekly) ceiling: price within 1×ATR above wEMA10
                if w_ema10 is not None:
                    result["within_1atr_wema10"] = bool(price <= w_ema10 + 1.0 * atr)

        # ── 3-Weeks Tight ────────────────────────────────────────────────────
        # Last 3 weekly closes (resample or use weekly_closes) within 1.5% of each other
        try:
            if weekly_closes is not None and len(weekly_closes) >= 3:
                wc = weekly_closes.iloc[-3:]
            elif len(closes) >= 15:
                wc = closes.resample("W-FRI").last().dropna().iloc[-3:]
            else:
                wc = None

            if wc is not None and len(wc) >= 3:
                wc_vals = wc.values.astype(float)
                spread = (max(wc_vals) - min(wc_vals)) / min(wc_vals) * 100
                result["three_weeks_tight"] = bool(spread <= 1.5)
        except Exception:
            pass

    except Exception:
        pass

    # ── Entry Readiness Score (1–5) ─────────────────────────────────────────
    # Combines Core Stats into a single at-a-glance rating.
    # 5 = all criteria met, high conviction entry zone
    # 1 = multiple issues, skip or wait
    try:
        pts = 0
        # ADR in target range (1 pt)
        if result["adr_pct"] is not None and 3.5 <= result["adr_pct"] <= 8:
            pts += 1
        # EMA21 Low % — most important criterion (2 pts graded)
        e21 = result["ema21_low_pct"]
        if e21 is not None:
            if e21 < 5:    pts += 2   # low risk
            elif e21 <= 8: pts += 1   # moderate — partial credit
            # >8 = 0 pts, likely no entry
        # 3-Weeks Tight (1 pt)
        if result["three_weeks_tight"]:
            pts += 1
        # All ceiling checks pass (1 pt)
        ceilings = [result["within_1atr_ema21"], result["within_1atr_wema10"], result["within_3atr_sma50"]]
        valid_ceilings = [c for c in ceilings if c is not None]
        if valid_ceilings and all(valid_ceilings):
            pts += 1
        result["entry_readiness"] = min(5, pts)
    except Exception:
        pass

    return result


def calculate_atr_series(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    try:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = float(tr.iloc[-period:].mean())
        return round(atr, 4) if atr > 0 else None
    except Exception:
        return None


def detect_ma_touch_atr(price, ma, atr, lower_atr_mult, upper_atr_mult) -> bool:
    """V2 core: ATR-based proximity window. Normalises for volatility."""
    if ma is None or atr is None or atr == 0:
        return False
    distance = price - ma
    return (-lower_atr_mult * atr) <= distance <= (upper_atr_mult * atr)


def ma_proximity_pct(price: float, ma: Optional[float]) -> Optional[float]:
    if ma is None or ma == 0:
        return None
    return round((price - ma) / price * 100, 3)


def calculate_vcs(closes: pd.Series, highs: pd.Series = None,
                  lows: pd.Series = None, volumes: pd.Series = None) -> Optional[float]:
    """
    Proper Volatility Contraction Score (0–10 scale, lower = tighter).
    Mirrors oratnek's VCS methodology:
      1. ATR compression   — short ATR vs long ATR
      2. StdDev compression — short StdDev vs long StdDev
      3. Volume dry-up     — recent volume vs baseline (supply exhaustion)
      4. Higher-low check  — structure intact (penalty if lows breaking down)
      5. Consistency bonus — longer compression = more coiled energy

    Score is inverted: 1 = maximally coiled, 10 = loose/expanding.
    Compatible with existing signal scoring which rewards vcs <= 3.
    """
    if len(closes) < 50:
        return None

    price = float(closes.iloc[-1])

    # ── 1. ATR compression (0–35 pts, lower ratio = more compressed)
    atr_score = 0.0
    if highs is not None and lows is not None and len(highs) >= 50:
        try:
            prev_close  = closes.shift(1)
            tr          = pd.concat([
                highs - lows,
                (highs - prev_close).abs(),
                (lows  - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr_short   = float(tr.iloc[-10:].mean())
            atr_long    = float(tr.iloc[-50:].mean())
            if atr_long > 0:
                atr_ratio = atr_short / atr_long
                # ratio < 0.5 = very tight, > 1.2 = expanding
                atr_score = max(0, 35 * (1 - min(atr_ratio, 1.5) / 1.5))
        except Exception:
            pass

    # ── 2. StdDev compression (0–25 pts)
    std_score = 0.0
    recent_std   = float(closes.iloc[-10:].std())
    baseline_std = float(closes.iloc[-50:].std())
    if baseline_std > 0:
        std_ratio = recent_std / baseline_std
        std_score = max(0, 25 * (1 - min(std_ratio, 1.5) / 1.5))

    # ── 3. Volume dry-up (0–20 pts) — supply exhaustion
    vol_score = 0.0
    if volumes is not None and len(volumes) >= 30:
        try:
            recent_vol   = float(volumes.iloc[-10:].mean())
            baseline_vol = float(volumes.iloc[-30:].mean())
            if baseline_vol > 0:
                vol_ratio = recent_vol / baseline_vol
                # vol_ratio < 0.6 = strong dry-up, > 1.0 = expanding (bad)
                vol_score = max(0, 20 * (1 - min(vol_ratio, 1.2) / 1.2))
        except Exception:
            pass

    # ── 4. Higher-low structure check (0 or –10 penalty)
    hl_penalty = 0.0
    if lows is not None and len(lows) >= 20:
        try:
            # Split last 20 bars into two halves; second half lows should be >= first
            mid = 10
            first_half_low  = float(lows.iloc[-20:-mid].min())
            second_half_low = float(lows.iloc[-mid:].min())
            if second_half_low < first_half_low * 0.97:  # lows breaking down
                hl_penalty = -10.0
        except Exception:
            pass

    # ── 5. Consistency bonus (0–10 pts) — longer compression = more coiled
    consistency = 0.0
    try:
        # Count consecutive bars where daily range < 80% of 50-bar avg range
        if highs is not None and lows is not None:
            daily_ranges = (highs - lows).iloc[-50:]
            avg_range    = float(daily_ranges.mean())
            if avg_range > 0:
                tight_bars = sum(1 for r in daily_ranges.iloc[-20:] if r < avg_range * 0.8)
                consistency = min(10, tight_bars * 0.5)
    except Exception:
        pass

    # ── Total raw score (0–90)
    raw = atr_score + std_score + vol_score + hl_penalty + consistency

    # Invert and rescale to 1–10 (1 = maximally coiled, 10 = loose)
    # raw 80+ → VCS ~1, raw 0 → VCS ~10
    vcs = 10.0 - (raw / 90.0) * 9.0
    return round(max(1.0, min(10.0, vcs)), 1)


def calculate_mansfield_rs(closes: pd.Series, spy_closes: pd.Series,
                            all_weighted_rs: list) -> int:
    """
    Mansfield-style weighted Relative Strength rank.

    Weighting (matches IBD methodology, recent periods count more):
      12-month return × 0.4
       9-month return × 0.2
       6-month return × 0.2
       3-month return × 0.2

    Returns percentile rank 1–99 vs the full universe.
    Falls back to 50 on insufficient data.
    """
    if closes is None or spy_closes is None or len(closes) < 63:
        return 50

    try:
        aligned = pd.DataFrame({"stock": closes, "spy": spy_closes}).dropna()
        if len(aligned) < 63:
            return 50

        def _pct(series, periods):
            if len(series) < periods:
                return None
            start = float(series.iloc[-periods])
            end   = float(series.iloc[-1])
            return (end - start) / start if start != 0 else None

        s = aligned["stock"]
        b = aligned["spy"]

        # Per-period RS ratios (stock return vs benchmark return)
        def _rs_period(periods):
            sr = _pct(s, periods)
            br = _pct(b, periods)
            if sr is None or br is None:
                return None
            # Normalised RS: how much stock outperformed benchmark
            return sr - br

        rs_12 = _rs_period(252) if _rs_period(252) is not None else _rs_period(min(252, len(s) - 1))
        rs_9  = _rs_period(189)
        rs_6  = _rs_period(126)
        rs_3  = _rs_period(63)

        if rs_12 is None:
            return 50

        # Weighted composite (recent periods count more)
        weights = [(rs_12, 0.4), (rs_9, 0.2), (rs_6, 0.2), (rs_3, 0.2)]
        total_w, score = 0.0, 0.0
        for val, w in weights:
            if val is not None:
                score   += val * w
                total_w += w

        if total_w == 0:
            return 50
        weighted_score = score / total_w  # normalise to valid weights

        if not all_weighted_rs:
            return 50

        # Percentile rank in universe — filter out any None values defensively
        valid_rs = [r for r in all_weighted_rs if r is not None]
        if not valid_rs:
            return 50
        rank = sum(1 for r in valid_rs if r < weighted_score) / len(valid_rs)
        return max(1, min(99, int(rank * 100)))

    except Exception:
        return 50


def _calculate_weighted_rs_score(closes: pd.Series, spy_closes: pd.Series) -> Optional[float]:
    """
    Returns the raw weighted RS score for a ticker (used to build the universe list
    passed into calculate_mansfield_rs). Not the rank — the raw value.
    """
    if closes is None or spy_closes is None or len(closes) < 63:
        return None
    try:
        aligned = pd.DataFrame({"stock": closes, "spy": spy_closes}).dropna()
        if len(aligned) < 63:
            return None
        s, b = aligned["stock"], aligned["spy"]

        def _rs(periods):
            if len(s) < periods or len(b) < periods:
                return None
            sr = (float(s.iloc[-1]) - float(s.iloc[-periods])) / float(s.iloc[-periods]) if float(s.iloc[-periods]) != 0 else None
            br = (float(b.iloc[-1]) - float(b.iloc[-periods])) / float(b.iloc[-periods]) if float(b.iloc[-periods]) != 0 else None
            return (sr - br) if sr is not None and br is not None else None

        rs_12 = _rs(252) if _rs(252) is not None else _rs(min(252, len(s) - 1))
        rs_9  = _rs(189)
        rs_6  = _rs(126)
        rs_3  = _rs(63)
        if rs_12 is None:
            return None

        weights = [(rs_12, 0.4), (rs_9, 0.2), (rs_6, 0.2), (rs_3, 0.2)]
        total_w, score = 0.0, 0.0
        for val, w in weights:
            if val is not None:
                score += val * w; total_w += w
        return score / total_w if total_w > 0 else None
    except Exception:
        return None


# Keep old name as alias so backtest/historical code still works
def calculate_1y_return(closes: pd.Series) -> Optional[float]:
    if len(closes) < 63:
        return None
    start = closes.iloc[-min(252, len(closes))]
    end   = closes.iloc[-1]
    if start == 0:
        return None
    return (end - start) / start


def calculate_rs_rank(ticker_return_1y: float, all_returns: list) -> int:
    """Legacy — kept for backtest compatibility. Use calculate_mansfield_rs for live signals."""
    if not all_returns:
        return 50
    rank = sum(1 for r in all_returns if r < ticker_return_1y) / len(all_returns)
    return max(1, min(99, int(rank * 100)))


def volume_ratio(volumes: pd.Series, window: int = 50) -> Optional[float]:
    if len(volumes) < window + 1:
        return None
    avg = volumes.iloc[-window - 1:-1].mean()
    if avg == 0:
        return None
    return round(float(volumes.iloc[-1]) / avg, 2)


def volume_trend(volumes: pd.Series, window: int = 10) -> str:
    if len(volumes) < window + 5:
        return "neutral"
    recent_avg = volumes.iloc[-window:].mean()
    prior_avg  = volumes.iloc[-window - 10:-window].mean()
    if prior_avg == 0:
        return "neutral"
    ratio = recent_avg / prior_avg
    if ratio < 0.75:  return "drying"
    if ratio > 1.25:  return "expanding"
    return "neutral"


def calculate_signal_score(
    rs, vcs, base_score, vol_ratio, sector_rs_rank,
    market_score, earnings_days, tier, bouncing_from, pct_from_52w_high,
    ma21_slope=None, ma50_slope=None, coiling=False,
    ll_hl_detected=False, approaching_pivot=False,
    darvas_detected=False, darvas_status=None,
    w_stack_ok=False,
    theme=None, sector_rs_data=None,
    **kwargs,
) -> float:
    """Signal quality score 1-10. Used for alert filtering and UI sorting."""
    score = 0.0
    # RS (0-2.5)
    if rs >= 90:   score += 2.5
    elif rs >= 80: score += 2.0
    elif rs >= 70: score += 1.5
    elif rs >= 60: score += 0.8
    else:          score += 0.2
    # VCS (0-2.0)
    if vcs is not None:
        if vcs <= 2:   score += 2.0
        elif vcs <= 3: score += 1.8
        elif vcs <= 4: score += 1.4
        elif vcs <= 5: score += 1.0
        elif vcs <= 6: score += 0.5
        else:          score += 0.1
    # Base score (0-2.0)
    if base_score:
        score += min(2.0, base_score / 50)
    # Market regime (0-1.5)
    if market_score >= 65:   score += 1.5
    elif market_score >= 55: score += 1.0
    elif market_score >= 45: score += 0.5
    # Volume (0-1.0)
    if vol_ratio:
        if vol_ratio >= 2.0:   score += 1.0
        elif vol_ratio >= 1.5: score += 0.7
        elif vol_ratio >= 1.1: score += 0.4
    # Sector RS (0-1.0)
    if sector_rs_rank:
        if sector_rs_rank <= 3:   score += 1.0
        elif sector_rs_rank <= 6: score += 0.7
        elif sector_rs_rank <= 9: score += 0.4
    # MA slope (0-1.0) — soft bonus, not a gate
    if ma21_slope is not None:
        if ma21_slope > 1.0:    score += 0.8
        elif ma21_slope > 0.5:  score += 0.6
        elif ma21_slope > 0.0:  score += 0.3
        elif ma21_slope < -0.5: score -= 0.5
        else:                   score -= 0.2
    if ma50_slope is not None:
        if ma50_slope > 0.3:    score += 0.2
        elif ma50_slope < 0.0:  score -= 0.2
    # Coiling bonus
    if coiling:
        score += 0.3
    # Weekly timeframe confirmation bonus
    if w_stack_ok:
        score += 0.5   # daily + weekly aligned = higher conviction
    # LL-HL Pivot bonus
    if ll_hl_detected:
        score += 0.5
    if approaching_pivot:
        score += 0.4
    # Darvas Box bonus
    if darvas_detected and darvas_status == "approaching":
        score += 0.5
    elif darvas_detected and darvas_status == "in_box":
        score += 0.2
    # Flag / Pennant bonus — high-conviction continuation pattern
    flag_detected  = kwargs.get("flag_detected", False)
    flag_st        = kwargs.get("flag_status")
    if flag_detected and flag_st == "breaking":   score += 1.2  # imminent breakout → biggest bonus
    elif flag_detected and flag_st == "broken_out": score += 0.8
    elif flag_detected and flag_st == "watch":      score += 0.5
    # Proximity bonuses
    if bouncing_from == "MA10":  score += 0.3
    if pct_from_52w_high and pct_from_52w_high >= -5: score += 0.3
    # Earnings penalty
    if earnings_days is not None:
        if earnings_days <= 2:   score -= 2.0
        elif earnings_days <= 5: score -= 1.0
        elif earnings_days <= 7: score -= 0.5
    if tier == 3: score -= 0.5
    # Theme bonus — boosted for priority themes (Defence, DefenceTech, Space, Gold)
    if theme:
        try:
            from sector_rs import get_theme_score_bonus
            score += get_theme_score_bonus(theme, sector_rs_data)
        except Exception:
            pass
    return round(max(1.0, min(10.0, score)), 1)


# ── Short setup detectors ────────────────────────────────────────────────────

def detect_ma_rejection(closes, highs, lows, volumes, ma_val, ma_slope,
                        atr, lookback=8):
    """
    Detect a failed rally into a declining MA from below.

    Returns dict with:
        rejected        : bool  — core signal
        rejection_high  : float — highest high during the rally
        pct_above_ma    : float — how far above MA the high got
        rally_vol_dry   : bool  — volume dried up on the rally
        coiling         : bool  — tight range under MA now
        bars_tested     : int   — how many bars tested the MA
    """
    result = {"rejected": False, "rejection_high": None,
              "pct_above_ma": None, "rally_vol_dry": False,
              "coiling": False, "bars_tested": 0}

    import math
    if ma_val is None or ma_slope is None or atr is None or atr <= 0:
        return result
    if isinstance(ma_slope, float) and math.isnan(ma_slope):
        return result
    if isinstance(ma_val, float) and math.isnan(ma_val):
        return result

    # MA must be declining to act as resistance
    if ma_slope > 0.1:
        return result

    n = len(closes)
    if n < lookback + 5:
        return result

    price = float(closes.iloc[-1])
    # Current price must be below MA (otherwise not a failed rally — it broke above)
    if price >= ma_val * 1.02:
        return result

    avg_vol = float(volumes.iloc[-20:].mean()) if len(volumes) >= 20 else None

    # Scan last `lookback` bars for a rally that touched or pierced the MA
    rally_highs = []
    rally_vols  = []
    bars_tested = 0

    for i in range(n - lookback, n):
        h = float(highs.iloc[i])
        c = float(closes.iloc[i])
        v = float(volumes.iloc[i])
        # Bar touched within 2% of MA from below
        pct_to_ma = (ma_val - h) / ma_val * 100
        if -2.0 <= pct_to_ma <= 4.0:   # high got within 4% below or 2% above
            rally_highs.append(h)
            rally_vols.append(v)
            bars_tested += 1

    if not rally_highs:
        return result

    rejection_high  = max(rally_highs)
    pct_above_ma    = round((rejection_high - ma_val) / ma_val * 100, 2)

    # Volume check: rally volume < 85% of 20d avg = weak buyers
    rally_vol_dry = False
    if avg_vol and rally_vols:
        avg_rally_vol = sum(rally_vols) / len(rally_vols)
        rally_vol_dry = avg_rally_vol < avg_vol * 0.85

    # Coiling: last 2 bars have tight range (< 0.65× ATR) and close < MA
    coiling = False
    if n >= 2:
        recent_ranges = [
            float(highs.iloc[i]) - float(lows.iloc[i])
            for i in range(n - 2, n)
        ]
        avg_recent_range = sum(recent_ranges) / len(recent_ranges)
        coiling = avg_recent_range < atr * 0.65 and float(closes.iloc[-1]) < ma_val

    result.update({
        "rejected":       True,
        "rejection_high": round(rejection_high, 4),
        "pct_above_ma":   pct_above_ma,
        "rally_vol_dry":  rally_vol_dry,
        "coiling":        coiling,
        "bars_tested":    bars_tested,
    })
    return result


def detect_weekly_short(weekly_df):
    """
    Detect weekly-timeframe failed rally into wEMA10 or wEMA40.

    Returns dict with:
        w_rejected      : bool
        w_rejection_ma  : str  — "wEMA10" | "wEMA40" | None
        w_vol_dry       : bool
        w_ma_slope      : float
    """
    result = {"w_rejected": False, "w_rejection_ma": None,
              "w_vol_dry": False, "w_ma_slope": None}

    if weekly_df is None or len(weekly_df) < 15:
        return result

    wc = weekly_df["close"]
    wh = weekly_df.get("high", wc)
    wv = weekly_df["volume"] if "volume" in weekly_df.columns else None

    try:
        wema10 = float(wc.ewm(span=10, adjust=False).mean().iloc[-1])
        wema40 = float(wc.ewm(span=40, adjust=False).mean().iloc[-1])
        wema10_prev = float(wc.ewm(span=10, adjust=False).mean().iloc[-2])
        wema40_prev = float(wc.ewm(span=40, adjust=False).mean().iloc[-2])
    except Exception:
        return result

    import math
    if any(math.isnan(v) for v in [wema10, wema40, wema10_prev, wema40_prev]):
        return result

    w_price = float(wc.iloc[-1])
    w_high  = float(wh.iloc[-1])
    w_high2 = float(wh.iloc[-2]) if len(wh) >= 2 else w_high

    for ma_val, ma_prev, ma_name in [
        (wema10, wema10_prev, "wEMA10"),
        (wema40, wema40_prev, "wEMA40"),
    ]:
        ma_slope = ma_val - ma_prev
        if ma_slope > 0:             # must be declining
            continue
        if w_price >= ma_val * 1.01: # current price still above = not rejected
            continue
        # High of last 1-2 weekly bars touched within 3% of MA
        touched = (
            abs(w_high  - ma_val) / ma_val < 0.03 or
            abs(w_high2 - ma_val) / ma_val < 0.03
        )
        if not touched:
            continue

        # Volume dry on the rally week
        w_vol_dry = False
        if wv is not None and len(wv) >= 10:
            avg_wvol   = float(wv.iloc[-10:].mean())
            rally_wvol = float(wv.iloc[-1])
            w_vol_dry  = rally_wvol < avg_wvol * 0.80

        result.update({
            "w_rejected":     True,
            "w_rejection_ma": ma_name,
            "w_vol_dry":      w_vol_dry,
            "w_ma_slope":     round(ma_slope, 4),
        })
        return result   # return on first (strongest) match

    return result


def calculate_short_score(
    rs, price, ma21, ma50, ma200,
    ma21_slope, ma50_slope, ma200_slope,
    atr, closes, highs, lows, volumes,
    weekly_df=None,
) -> tuple:
    """
    New short scoring: rewards MA rejection quality, not extended moves.

    Returns (score: int, setup_type: str|None, rejection_ma: str|None, detail: dict)
    """
    score       = 0
    setup_type  = None
    rejection_ma = None
    detail      = {}

    if price is None or atr is None or atr <= 0:
        return 0, None, None, {}

    # ── Check each MA for rejection (priority: MA200 > MA50 > MA21) ──────────
    ma_checks = [
        ("MA200", ma200, ma200_slope, 20),
        ("MA50",  ma50,  ma50_slope,  15),
        ("MA21",  ma21,  ma21_slope,  10),
    ]

    best_rejection = None
    best_ma_bonus  = 0

    for ma_name, ma_val, ma_slope, ma_bonus in ma_checks:
        if ma_val is None or ma_slope is None:
            continue
        rej = detect_ma_rejection(closes, highs, lows, volumes, ma_val, ma_slope, atr)
        if rej["rejected"]:
            # Take the highest-bonus MA rejection
            if ma_bonus > best_ma_bonus:
                best_rejection  = (ma_name, rej, ma_bonus)
                best_ma_bonus   = ma_bonus

    if best_rejection:
        ma_name, rej, ma_bonus = best_rejection
        rejection_ma = ma_name
        setup_type   = f"DAILY_{ma_name}_REJECT"
        score += 20   # base: price was rejected off MA
        score += ma_bonus

        if rej["rally_vol_dry"]:
            score += 10
            detail["rally_vol_dry"] = True
        if rej["coiling"]:
            score += 10
            detail["coiling"] = True
        detail["bars_tested"]    = rej["bars_tested"]
        detail["pct_above_ma"]   = rej["pct_above_ma"]
        detail["rejection_high"] = rej["rejection_high"]

    # ── Weekly confirmation ───────────────────────────────────────────────────
    w_short = detect_weekly_short(weekly_df)
    if w_short["w_rejected"]:
        w_bonus = 15 if best_rejection else 10
        score  += w_bonus
        if setup_type is None:
            setup_type   = f"WEEKLY_{w_short['w_rejection_ma']}_REJECT"
            rejection_ma = w_short["w_rejection_ma"]
        if w_short["w_vol_dry"]:
            score += 5
        detail["w_rejection_ma"] = w_short["w_rejection_ma"]
        detail["w_vol_dry"]      = w_short["w_vol_dry"]

    # No setup found — return early with 0
    if setup_type is None:
        return 0, None, None, detail

    # ── Trend / RS bonus ─────────────────────────────────────────────────────
    if rs is not None:
        if rs < 10:   score += 15
        elif rs < 20: score += 10
        elif rs < 30: score += 5
        elif rs > 50: score -= 15   # don't short strong stocks

    # MA slope (negative = actively declining = better resistance)
    best_slope = None
    for ma_val, ma_slope in [(ma21, ma21_slope), (ma50, ma50_slope), (ma200, ma200_slope)]:
        if ma_slope is not None and ma_val is not None and rejection_ma and ma_val == {
            "MA21": ma21, "MA50": ma50, "MA200": ma200,
            "wEMA10": None, "wEMA40": None
        }.get(rejection_ma):
            best_slope = ma_slope
    if best_slope is not None and best_slope < -0.3:
        score += 10
    elif best_slope is not None and best_slope < 0:
        score += 5

    # Below MA50 = intermediate downtrend confirmed
    if ma50 and price < ma50:
        score += 5

    # Penalty: price above MA200 = longer-term uptrend, riskier short
    if ma200 and price > ma200:
        score -= 10

    return min(100, max(0, score)), setup_type, rejection_ma, detail


def calculate_rs_line(closes: pd.Series, spy_closes: pd.Series, periods: int = 60) -> list:
    """Last N days of stock/SPY ratio, normalised to 100."""
    try:
        aligned = pd.DataFrame({"stock": closes, "spy": spy_closes}).dropna()
        if len(aligned) < 20:
            return []
        recent = aligned.iloc[-periods:]
        ratio  = recent["stock"] / recent["spy"]
        base   = ratio.iloc[0]
        if base == 0:
            return []
        normalised = (ratio / base * 100).round(2)
        return [{"date": str(idx.date()), "rs_line": float(v)} for idx, v in normalised.items()]
    except Exception:
        return []


def analyse_stock(
    ticker: str,
    df: pd.DataFrame,
    all_weighted_rs: list,         # replaces all_1y_returns — now Mansfield scores
    spy_closes: pd.Series = None,
    market_score: int = 50,
    tier: int = 2,
    weekly_df: pd.DataFrame = None,  # weekly OHLCV bars for higher-TF confirmation
) -> Optional[dict]:
    try:
        if df is None or len(df) < 21:
            return None

        closes  = df["close"]
        volumes = df["volume"]
        highs   = df.get("high", closes)
        lows    = df.get("low",  closes)
        price   = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) > 1 else price
        chg_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

        atr = calculate_atr_series(df)
        mas = calculate_mas(closes)
        ma10, ma21, ma50, ma200 = mas["ma10"], mas["ma21"], mas["ma50"], mas["ma200"]
        ma21_slope = mas.get("ma21_slope")
        ma50_slope = mas.get("ma50_slope")

        pct_from_ma10 = ma_proximity_pct(price, ma10)
        pct_from_ma21 = ma_proximity_pct(price, ma21)
        pct_from_ma50 = ma_proximity_pct(price, ma50)

        # Daily MA stack (EMA10/21/50 above SMA200)
        ma_stack_ok = bool(
            ma10 and ma21 and ma50 and
            ma10 > ma50 and
            ma21 > ma50 and
            (ma200 is None or ma50 > ma200)
        )

        ma21_rising = ma21_slope is not None and ma21_slope > 0
        ma21_strong = ma21_slope is not None and ma21_slope > 0.5
        ma50_rising = ma50_slope is not None and ma50_slope > 0
        coiling     = bool(ma10 and ma21 and ma50 and ma10 < ma21 and
                           ma10 > ma50 and ma21 > ma50)
        above_ma200 = bool(ma200 and price > ma200)

        # ATR-based MA touches
        ma10_touch = detect_ma_touch_atr(price, ma10, atr, 0.1, 0.5) if ma10 else False
        ma21_touch = detect_ma_touch_atr(price, ma21, atr, 0.5, 1.0) if ma21 else False
        ma50_touch = detect_ma_touch_atr(price, ma50, atr, 0.3, 1.5) if ma50 else False
        ma21_below = pct_from_ma21 is not None and pct_from_ma21 < 0

        bouncing_from = (
            "MA10" if ma10_touch else
            "MA21" if ma21_touch else
            "MA50" if ma50_touch else None
        )

        # ── Weekly timeframe confirmation ─────────────────────────────────────
        weekly_closes = None
        if weekly_df is not None and len(weekly_df) >= 12:
            weekly_closes = weekly_df["close"]
        elif len(closes) >= 60:
            # Fallback: resample daily bars to weekly (Friday closes)
            weekly_closes = closes.resample("W-FRI").last().dropna()

        w_mas = calculate_weekly_mas(weekly_closes)
        w_stack_ok     = w_mas["w_stack_ok"]
        w_ema10        = w_mas["w_ema10"]
        w_ema40        = w_mas["w_ema40"]
        w_above_ema10  = w_mas["w_above_ema10"]
        w_above_ema40  = w_mas["w_above_ema40"]
        w_ema10_slope  = w_mas["w_ema10_slope"]

        # ── Core Stats (Nik's entry validity filter) ─────────────────────
        core = calculate_core_stats(df, weekly_closes=weekly_closes, w_ema10=w_ema10)

        # ── Proper VCS (oratnek methodology) ─────────────────────────────────
        vcs = calculate_vcs(closes, highs=highs, lows=lows, volumes=volumes)

        vol_ratio_val = volume_ratio(volumes)
        vol_trend_val = volume_trend(volumes)
        today_vol     = int(volumes.iloc[-1])

        # ── Mansfield-weighted RS ─────────────────────────────────────────────
        rs = calculate_mansfield_rs(closes, spy_closes, all_weighted_rs)

        w52_high          = round(float(closes.tail(252).max()), 4) if len(closes) >= 20 else price
        w52_low           = round(float(closes.tail(252).min()), 4) if len(closes) >= 20 else price
        pct_from_52w_high = round((price - w52_high) / w52_high * 100, 1)

        days_below_ma21 = 0
        if ma21:
            for c in reversed(closes.values[:-1]):
                if c < ma21: days_below_ma21 += 1
                else: break

        # ── New short setup detection ─────────────────────────────────────────
        # Pass weekly_df so we can check weekly MA rejections too.
        # ma200_slope: compute the same way as ma21_slope / ma50_slope
        _ma200_series = closes.ewm(span=200, adjust=False).mean()
        ma200_slope = None
        if len(_ma200_series) >= 6:
            ma200_slope = round(
                float(_ma200_series.iloc[-1] - _ma200_series.iloc[-6]) / 5, 4
            )

        # weekly_df for short detection — use passed-in or resample
        _weekly_for_short = weekly_df
        if _weekly_for_short is None and len(df) >= 60:
            _weekly_for_short = df.resample("W-FRI").agg({
                "open":  "first", "high": "max",
                "low":   "min",   "close": "last",
                "volume": "sum",
            }).dropna()

        short_score, short_setup_type, rejection_ma, short_detail = calculate_short_score(
            rs       = rs,
            price    = price,
            ma21     = ma21,   ma50  = ma50,   ma200  = ma200,
            ma21_slope  = ma21_slope,
            ma50_slope  = ma50_slope,
            ma200_slope = ma200_slope,
            atr      = atr,
            closes   = closes,
            highs    = highs,
            lows     = lows,
            volumes  = volumes,
            weekly_df = _weekly_for_short,
        )

        # Legacy fields kept for DB / frontend compat
        failed_rally      = short_setup_type is not None
        rally_vol_dry     = short_detail.get("rally_vol_dry", False)
        short_coiling     = short_detail.get("coiling", False)
        w_short_rejection = short_detail.get("w_rejection_ma")

        # ── Stop & target calculation ─────────────────────────────────────────
        # Long stops: below entry at swing low / ATR
        # Short stops: above entry at the rejected MA + 0.5×ATR buffer
        stop_price  = None
        stop_basis  = None
        is_short_candidate = short_setup_type is not None

        if atr:
            if is_short_candidate:
                # Short stop: just above the rejected MA (or swing high if tighter)
                ma_map_stop = {
                    "MA21": ma21, "MA50": ma50, "MA200": ma200,
                }
                rej_ma_val = ma_map_stop.get(rejection_ma) if rejection_ma else None
                if rej_ma_val:
                    ma_stop     = rej_ma_val + 0.5 * atr
                else:
                    ma_stop     = price + 1.5 * atr
                if "high" in df.columns and len(df) >= 5:
                    swing_high  = float(df["high"].iloc[-5:].max())
                    struct_stop = swing_high + 0.25 * atr
                    # Use the lower (tighter) stop for shorts
                    raw_stop    = min(ma_stop, struct_stop)
                    stop_basis  = "swing_high" if raw_stop == round(struct_stop, 4) else "ma_level"
                else:
                    raw_stop    = ma_stop
                    stop_basis  = "ma_level"
                # Hard cap: never risk more than 8% on a short
                ceiling_stop = price * 1.08
                stop_price   = round(min(raw_stop, ceiling_stop), 4)
                if stop_price <= price:   # safety: stop must be above price
                    stop_price = round(price + 1.5 * atr, 4)
                    stop_basis = "atr"
            else:
                # Long stop: swing low / ATR below entry
                atr_stop    = price - 1.5 * atr
                if "low" in df.columns and len(df) >= 5:
                    swing_low   = float(df["low"].iloc[-5:].min())
                    struct_stop = swing_low - 0.25 * atr
                    raw_stop    = max(atr_stop, struct_stop)
                    stop_basis  = "swing_low" if raw_stop == round(struct_stop, 4) else "atr"
                else:
                    raw_stop    = atr_stop
                    stop_basis  = "atr"
                floor_stop  = price * 0.92
                stop_price  = round(max(raw_stop, floor_stop), 4)
                if stop_price >= price:
                    stop_price = round(price - 1.5 * atr, 4)
                    stop_basis = "atr"

        # R-multiple targets
        # Longs: targets above entry. Shorts: targets BELOW entry (price falling).
        if stop_price and atr:
            if is_short_candidate:
                risk     = stop_price - price          # risk = stop above - entry
                target_1 = round(price - 1.0 * risk, 4)   # 1R down
                target_2 = round(price - 2.0 * risk, 4)   # 2R down
                target_3 = round(price - 3.5 * risk, 4)   # 3.5R down
            else:
                risk     = price - stop_price
                target_1 = round(price + 1.0 * risk, 4)
                target_2 = round(price + 2.0 * risk, 4)
                target_3 = round(price + 3.5 * risk, 4)
        else:
            target_1 = target_2 = target_3 = None

        # EMA21 as initial trailing anchor (shown in frontend; updated nightly by journal_tracker)
        ema21_trail = round(float(ma21), 4) if ma21 else None

        # Partial exit plan — shown in signal card and journal
        partial_plan = None
        if stop_price and target_1 and target_2 and target_3:
            if is_short_candidate:
                risk_pct = round((stop_price - price) / price * 100, 2)
                partial_plan = {
                    "risk_pct":   risk_pct,
                    "t1_action":  "Cover 1/3 · Move stop to breakeven",
                    "t2_action":  "Cover 1/3 · Trail stop to EMA21",
                    "t3_action":  "Cover final 1/3 · Trail stop to EMA10",
                    "stop_basis": stop_basis,
                }
            else:
                risk_pct = round((price - stop_price) / price * 100, 2)
                partial_plan = {
                    "risk_pct":   risk_pct,
                    "t1_action":  "Sell 1/3 · Raise stop to breakeven",
                    "t2_action":  "Sell 1/3 · Trail stop to EMA21",
                    "t3_action":  "Sell final 1/3 · Trail stop to EMA10",
                    "stop_basis": stop_basis,
                }

        rs_line = calculate_rs_line(closes, spy_closes, 60) if spy_closes is not None else []

        # ── Inline chart data (last 60 bars) ─────────────────────────────────
        # Serialised as compact array — travels with signal, no extra API call.
        # Includes OHLCV + EMA10/21/50 so frontend can draw full setup chart.
        CHART_BARS = 60
        chart_data = []
        try:
            chart_slice = df.iloc[-CHART_BARS:].copy()
            ema10_s = closes.ewm(span=10, adjust=False).mean().iloc[-CHART_BARS:]
            ema21_s = closes.ewm(span=21, adjust=False).mean().iloc[-CHART_BARS:]
            ema50_s = closes.ewm(span=50, adjust=False).mean().iloc[-CHART_BARS:]

            for i, (idx_dt, row) in enumerate(chart_slice.iterrows()):
                chart_data.append({
                    "d":  str(idx_dt.date()),
                    "o":  round(float(row.get("open",  row["close"])), 2),
                    "h":  round(float(row.get("high",  row["close"])), 2),
                    "l":  round(float(row.get("low",   row["close"])), 2),
                    "c":  round(float(row["close"]), 2),
                    "v":  int(row.get("volume", 0)),
                    "e1": round(float(ema10_s.iloc[i]), 2),
                    "e2": round(float(ema21_s.iloc[i]), 2),
                    "e5": round(float(ema50_s.iloc[i]), 2),
                })
        except Exception:
            chart_data = []

        # ── oratnek pattern detectors ─────────────────────────────────────────
        ll_hl  = detect_ll_hl_pivot(df)
        darvas = detect_darvas_box(df)
        ep     = detect_ep_setup(df)
        hve    = detect_hve_retest(df)
        flag   = detect_flag_pennant(df)

        flag_status = flag.get("flag_status")
        if flag.get("flag_detected") and flag_status == "breaking":
            setup_tag = "FLAG BREAK"   # ← highest priority: actionable right now
        elif flag.get("flag_detected") and flag_status == "broken_out":
            setup_tag = "FLAG BO"      # recent breakout — follow-through
        elif ll_hl.get("approaching_pivot") and darvas.get("darvas_status") == "approaching":
            setup_tag = "LL-HL + DARVAS"
        elif flag.get("flag_detected") and flag_status == "watch":
            setup_tag = "FLAG WATCH"   # valid flag forming, not at trigger yet
        elif ll_hl.get("approaching_pivot"):
            setup_tag = "LL-HL PIVOT"
        elif darvas.get("darvas_status") == "approaching":
            setup_tag = "DARVAS"
        elif hve.get("hve_entry_ok"):
            setup_tag = "HVE RETEST"
        elif hve.get("hve_detected"):
            setup_tag = "HVE WATCH"
        elif ep.get("ep_entry_ok"):
            setup_tag = "EP DELAYED"
        elif ep.get("ep_detected"):
            setup_tag = "EP WATCH"
        elif ll_hl.get("ll_hl_detected"):
            setup_tag = "LL-HL"
        elif darvas.get("darvas_status") == "in_box":
            setup_tag = "IN BOX"
        elif darvas.get("darvas_status") == "breakout":
            setup_tag = "DARVAS BO"
        else:
            setup_tag = None

        return {
            "ticker": ticker, "tier": tier,
            "price": round(price, 2), "chg": chg_pct,
            "ma10": ma10, "ma21": ma21, "ma50": ma50, "ma200": ma200,
            "ma21_slope": ma21_slope, "ma50_slope": ma50_slope,
            "ma21_rising": ma21_rising, "ma21_strong": ma21_strong,
            "ma50_rising": ma50_rising, "coiling": coiling,
            "pct_from_ma10": pct_from_ma10, "pct_from_ma21": pct_from_ma21, "pct_from_ma50": pct_from_ma50,
            "ma10_touch": ma10_touch, "ma21_touch": ma21_touch, "ma50_touch": ma50_touch,
            "ma21_below": ma21_below, "bouncing_from": bouncing_from,
            "ma_stack_ok": ma_stack_ok, "above_ma200": above_ma200,
            # Weekly timeframe fields
            "w_ema10": w_ema10, "w_ema40": w_ema40,
            "w_stack_ok": w_stack_ok,
            "w_above_ema10": w_above_ema10, "w_above_ema40": w_above_ema40,
            "w_ema10_slope": w_ema10_slope,
            "vcs": vcs, "vol": today_vol, "vol_ratio": vol_ratio_val, "vol_trend": vol_trend_val,
            "rs": rs, "days_below_ma21": days_below_ma21, "failed_rally": failed_rally,
            "short_score": short_score,
            "short_setup_type": short_setup_type,
            "rejection_ma": rejection_ma,
            "rally_vol_dry": rally_vol_dry,
            "short_coiling": short_coiling,
            "w_short_rejection": w_short_rejection,
            "w52_high": w52_high, "w52_low": w52_low,
            "pct_from_52w_high": pct_from_52w_high,
            "atr": atr, "stop_price": stop_price, "stop_basis": stop_basis,
            "ema21_trail": ema21_trail, "partial_plan": partial_plan,
            "target_1": target_1, "target_2": target_2, "target_3": target_3,
            "rs_line": rs_line,
            "chart_data": chart_data,
            # oratnek pattern fields
            "setup_tag":         setup_tag,
            "ll_hl_detected":    ll_hl.get("ll_hl_detected", False),
            "ll_price":          ll_hl.get("ll_price"),
            "hl_price":          ll_hl.get("hl_price"),
            "pivot_line":        ll_hl.get("pivot_line"),
            "pct_from_pivot":    ll_hl.get("pct_from_pivot"),
            "approaching_pivot": ll_hl.get("approaching_pivot", False),
            "pivot_broken":      ll_hl.get("pivot_broken", False),
            "pivot_length":      ll_hl.get("pivot_length"),
            "darvas_detected":   darvas.get("darvas_detected", False),
            "box_top":           darvas.get("box_top"),
            "box_bottom":        darvas.get("box_bottom"),
            "box_height_pct":    darvas.get("box_height_pct"),
            "box_bars":          darvas.get("box_bars"),
            "darvas_status":     darvas.get("darvas_status"),
            "pct_from_box_top":  darvas.get("pct_from_box_top"),
            # ── Flag / Pennant pattern ───────────────────────────────────────
            "flag_detected":    flag.get("flag_detected", False),
            "flag_type":        flag.get("flag_type"),
            "pole_pct":         flag.get("pole_pct"),
            "pole_bars":        flag.get("pole_bars"),
            "pole_high_price":  flag.get("pole_high_price"),
            "flag_bars":        flag.get("flag_bars"),
            "flag_low":         flag.get("flag_low"),
            "flag_retrace_pct": flag.get("flag_retrace_pct"),
            "tl_touches":       flag.get("tl_touches"),
            "tl_slope":         flag.get("tl_slope"),
            "flag_breakout_level": flag.get("breakout_level"),
            "flag_status":      flag.get("flag_status"),
            "flag_stop_price":  flag.get("stop_price"),
            "flag_target_price":flag.get("target_price"),
            "vol_dry_flag":     flag.get("vol_dry_flag", False),
            "pole_vol_ratio":   flag.get("pole_vol_ratio"),
            "signal_score": None,  # filled in scanner after sector/market data
            # ── Core Stats (Nik's entry validity filter) ──────────────────
            "adr_pct":            core.get("adr_pct"),
            "ema21_low":          core.get("ema21_low"),
            "ema21_low_pct":      core.get("ema21_low_pct"),
            "within_1atr_ema21":  core.get("within_1atr_ema21"),
            "within_1atr_wema10": core.get("within_1atr_wema10"),
            "within_3atr_sma50":  core.get("within_3atr_sma50"),
            "three_weeks_tight":  core.get("three_weeks_tight", False),
            "entry_readiness":    core.get("entry_readiness"),
            # EP (Delayed Reaction Episodic Pivot) fields
            "ep_detected":     ep.get("ep_detected", False),
            "ep_entry_ok":     ep.get("ep_entry_ok", False),
            "ep_day":          ep.get("ep_day"),
            "ep_days_ago":     ep.get("ep_days_ago"),
            "ep_gap_pct":      ep.get("ep_gap_pct"),
            "ep_vol_ratio":    ep.get("ep_vol_ratio"),
            "ep_day_high":     ep.get("ep_day_high"),
            "ep_day_low":      ep.get("ep_day_low"),
            "ep_pullback_pct": ep.get("ep_pullback_pct"),
            "ep_stop":         ep.get("ep_stop"),
            "ep_target":       ep.get("ep_target"),
            "ep_neglect":      ep.get("ep_neglect"),
            # HVE (High Volume Earnings retest) fields
            "hve_detected":       hve.get("hve_detected", False),
            "hve_entry_ok":       hve.get("hve_entry_ok", False),
            "hve_gap_date":       hve.get("hve_gap_date"),
            "hve_gap_pct":        hve.get("hve_gap_pct"),
            "hve_vol_ratio":      hve.get("hve_vol_ratio"),
            "hve_gap_open":       hve.get("hve_gap_open"),
            "hve_support_level":  hve.get("hve_support_level"),
            "hve_test_count":     hve.get("hve_test_count"),
            "hve_pct_from_level": hve.get("hve_pct_from_level"),
            "hve_stop":           hve.get("hve_stop"),
            "hve_days_since_gap": hve.get("hve_days_since_gap"),
        }

    except Exception as e:
        import traceback as _tb
        print(f"[screener] Error analysing {ticker}: {e}\n{''.join(_tb.format_tb(__import__('sys').exc_info()[2])[-3:])}")
        return None


def is_long_signal(s: dict, settings: dict = None) -> bool:
    if not s: return False
    settings  = settings or {}
    has_touch = s.get("ma10_touch") or s.get("ma21_touch") or s.get("ma50_touch")
    vcs_ok    = s.get("vcs") is not None and s["vcs"] <= settings.get("vcs_filter", 6.0)
    vol_ok    = s.get("vol_ratio") is not None and s["vol_ratio"] >= 1.1
    rs_ok     = s.get("rs", 0) >= settings.get("rs_filter", 70)
    ma_stack_ok = s.get("ma_stack_ok", False)

    # Hard gate: below SMA200 is not a leading stock
    ma200 = s.get("ma200")
    above_ma200 = s.get("above_ma200", True)
    if ma200 is not None and not above_ma200:
        return False

    # Weekly confirmation gate: price must be in weekly uptrend
    # Soft: if weekly data available and stack fails, block signal
    # If weekly data not available (w_ema10 is None), allow through
    w_ema10    = s.get("w_ema10")
    w_stack_ok = s.get("w_stack_ok", True)  # default True = don't block if no data
    if w_ema10 is not None and not w_stack_ok:
        return False  # daily uptrend but weekly trend is down — skip

    return bool(has_touch and vcs_ok and vol_ok and rs_ok and ma_stack_ok)


def is_short_signal(s: dict) -> bool:
    """
    New filter: require an actual MA rejection setup, not just "price below MA21".

    Minimum criteria:
      - short_setup_type is set (daily or weekly MA rejection detected)
      - rejection_ma is identified
      - short_score >= 45
      - RS <= 45 (avoid shorting relatively strong stocks)
      - price below the rejected MA (confirmed failure)
    """
    if not s:
        return False
    setup   = s.get("short_setup_type")
    rej_ma  = s.get("rejection_ma")
    score   = s.get("short_score", 0)
    rs      = s.get("rs", 100)
    price   = s.get("price")

    if not setup or not rej_ma:
        return False
    if score < 45:
        return False
    if rs > 45:
        return False

    # Confirm price is actually below the rejected MA
    ma_map = {
        "MA21":   s.get("ma21"),
        "MA50":   s.get("ma50"),
        "MA200":  s.get("ma200"),
        "wEMA10": s.get("w_ema10"),
        "wEMA40": s.get("w_ema40"),
    }
    ma_val = ma_map.get(rej_ma)
    if ma_val and price and price >= ma_val * 1.025:
        return False   # price crept back above MA — setup no longer valid

    return True


def passes_earnings_gate(s: dict, min_days: int = 7) -> bool:
    days = s.get("days_to_earnings")
    if days is None: return True
    return days > min_days or days < 0


def is_duplicate(ticker: str, open_tickers: set) -> bool:
    return ticker in open_tickers


# ── Episodic Pivot (Delayed Reaction) Detector ────────────────────────────────
#
# Detects stocks that had a major earnings-style gap 1-5 days ago (the "EP day")
# and have since pulled back / consolidated into a lower-risk delayed entry zone.
#
# EP Day criteria:
#   - Gap from prior close ≥ 10% (open vs prior close)
#   - Volume on EP day ≥ 3× the 20-day ADV before that day
#   - Closed positively on EP day (didn't immediately fade the gap)
#
# Current state (delayed reaction entry) criteria:
#   - Price still above EP day open (thesis intact)
#   - Pulled back ≤ 20% from EP day high (consolidating, not collapsing)
#   - Volume has dried up since EP day (VCS tightening)
#
# Prior neglect filter:
#   - Stock was flat or down in the 3 months before EP day
#   (distinguishes genuine repricing from momentum stock that beat estimates)
#
# Exit rules for EP setups differ from VCP:
#   - Stop: below EP day LOW (not ATR stop) — below this level thesis is dead
#   - Target: 2× the initial gap magnitude (if gap was 15%, target is +30% from entry)
#   - No trailing stop until price clears EP day high by >5%

def detect_ep_setup(df: pd.DataFrame, lookback_days: int = 5) -> dict:
    """
    Scan recent bars for an Episodic Pivot day and check if current price
    is in a delayed reaction entry zone.

    Returns dict with ep_detected (bool) and all relevant EP fields.
    """
    _empty = {
        "ep_detected":    False,
        "ep_day":         None,
        "ep_days_ago":    None,
        "ep_gap_pct":     None,
        "ep_vol_ratio":   None,
        "ep_day_high":    None,
        "ep_day_low":     None,
        "ep_day_open":    None,
        "ep_pullback_pct": None,   # % pulled back from EP day high
        "ep_stop":        None,    # stop below EP day low
        "ep_target":      None,    # 2× gap magnitude from current price
        "ep_neglect":     None,    # True if stock was neglected before EP
        "ep_entry_ok":    False,   # True if delayed reaction entry conditions met
    }

    try:
        if df is None or len(df) < 30:
            return _empty

        closes  = df["close"]
        volumes = df["volume"] if "volume" in df.columns else None
        highs   = df["high"]   if "high"   in df.columns else closes
        lows    = df["low"]    if "low"    in df.columns else closes
        opens   = df["open"]   if "open"   in df.columns else closes

        if volumes is None:
            return _empty

        n = len(df)

        # ── Scan last `lookback_days` bars for an EP day ──────────────────────
        ep_idx    = None
        ep_info   = {}
        scan_end  = n - 1           # today
        scan_start = max(1, n - 1 - lookback_days)   # don't look at today itself

        for i in range(scan_start, scan_end):
            # Gap from prior close to open
            prior_close = float(closes.iloc[i - 1])
            day_open    = float(opens.iloc[i])
            day_close   = float(closes.iloc[i])
            day_high    = float(highs.iloc[i])
            day_low     = float(lows.iloc[i])
            day_vol     = float(volumes.iloc[i])

            if prior_close <= 0:
                continue

            gap_pct = (day_open - prior_close) / prior_close * 100

            # Must gap up ≥ 10%
            if gap_pct < 10.0:
                continue

            # Must close positively (not fade the gap — fade = failed EP)
            if day_close < day_open * 0.97:
                continue

            # Volume must be ≥ 3× the 20-day ADV *before* this day
            adv_start = max(0, i - 20)
            adv_vols  = volumes.iloc[adv_start:i]
            if len(adv_vols) < 5:
                continue
            adv = float(adv_vols.mean())
            if adv <= 0:
                continue
            vol_ratio = day_vol / adv

            if vol_ratio < 3.0:
                continue

            # Valid EP day found — take the most recent one
            ep_idx  = i
            ep_info = {
                "gap_pct":   round(gap_pct, 1),
                "vol_ratio": round(vol_ratio, 1),
                "day_open":  round(day_open, 2),
                "day_high":  round(day_high, 2),
                "day_low":   round(day_low, 2),
                "day_close": round(day_close, 2),
                "date":      str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i]),
            }
            # Keep scanning — want the MOST RECENT qualifying EP day

        if ep_idx is None:
            return _empty

        # ── Prior neglect check ───────────────────────────────────────────────
        # Was the stock flat or down in the 63 bars (≈3 months) before EP day?
        neglect_start = max(0, ep_idx - 63)
        neglect_end   = ep_idx
        if neglect_end - neglect_start >= 10:
            neglect_start_px = float(closes.iloc[neglect_start])
            neglect_end_px   = float(closes.iloc[neglect_end - 1])
            neglect_return   = (neglect_end_px - neglect_start_px) / neglect_start_px * 100
            ep_neglect       = neglect_return <= 10.0   # flat or down = True
        else:
            ep_neglect = None   # not enough data

        # ── Current state vs EP day ───────────────────────────────────────────
        current_price  = float(closes.iloc[-1])
        ep_days_ago    = (n - 1) - ep_idx
        ep_day_high    = ep_info["day_high"]
        ep_day_low     = ep_info["day_low"]
        ep_day_open    = ep_info["day_open"]
        gap_pct        = ep_info["gap_pct"]

        # Pullback from EP day high
        pullback_pct = round((ep_day_high - current_price) / ep_day_high * 100, 1)

        # Stop = just below EP day low
        ep_stop = round(ep_day_low * 0.99, 2)

        # Target = entry + 2× gap magnitude
        # (if gap was 15%, we expect at least another 15-30% from entry)
        ep_target = round(current_price * (1 + gap_pct / 100), 2)

        # ── Delayed reaction entry conditions ─────────────────────────────────
        # 1. Price still above EP day open (gap held)
        above_ep_open   = current_price > ep_day_open
        # 2. Not too extended above EP day high (if it's rocketing, too late for delayed entry)
        not_extended    = current_price <= ep_day_high * 1.05
        # 3. Pulled back meaningfully but not collapsed (5-20% pullback from EP high)
        healthy_pb      = 3.0 <= pullback_pct <= 20.0
        # 4. Price above EP stop (thesis intact)
        above_stop      = current_price > ep_stop

        ep_entry_ok = bool(above_ep_open and not_extended and healthy_pb and above_stop)

        return {
            "ep_detected":     True,
            "ep_day":          ep_info["date"],
            "ep_days_ago":     ep_days_ago,
            "ep_gap_pct":      gap_pct,
            "ep_vol_ratio":    ep_info["vol_ratio"],
            "ep_day_high":     ep_day_high,
            "ep_day_low":      ep_day_low,
            "ep_day_open":     ep_day_open,
            "ep_pullback_pct": pullback_pct,
            "ep_stop":         ep_stop,
            "ep_target":       ep_target,
            "ep_neglect":      ep_neglect,
            "ep_entry_ok":     ep_entry_ok,
            # theme set by scanner; placeholder here
            "theme":           None,
        }

    except Exception as e:
        print(f"[ep_detector] Error: {e}")
        return _empty


def detect_hve_retest(df: pd.DataFrame, lookback_days: int = 120) -> dict:
    """
    Detect High Volume Earnings (HVE) gap retest setups.

    Pattern (Tom Hougaard methodology):
    1. Stock had a major earnings gap (25%+) on extreme volume (5×+ ADV) in last 60-120 days
    2. Price has since pulled back to test the HVE level (gap open or gap midpoint)
    3. Currently sitting at or near the HVE with price holding (not collapsing through)
    4. This test is the entry — SL below HVE candle low

    Returns dict with hve_detected, hve_entry_ok, and all relevant HVE fields.
    """
    _empty = {
        "hve_detected":       False,
        "hve_entry_ok":       False,
        "hve_gap_date":       None,
        "hve_gap_pct":        None,
        "hve_vol_ratio":      None,
        "hve_gap_open":       None,
        "hve_gap_high":       None,
        "hve_gap_low":        None,
        "hve_support_level":  None,   # the level price is retesting
        "hve_test_count":     None,   # how many times tested so far
        "hve_pct_from_level": None,   # % above/below the HVE support
        "hve_stop":           None,
        "hve_days_since_gap": None,
    }

    try:
        if df is None or len(df) < 30:
            return _empty

        closes  = df["close"]
        volumes = df["volume"] if "volume" in df.columns else None
        highs   = df["high"]   if "high"   in df.columns else closes
        lows    = df["low"]    if "low"    in df.columns else closes
        opens   = df["open"]   if "open"   in df.columns else closes

        if volumes is None:
            return _empty

        n = len(df)
        scan_start = max(1, n - 1 - lookback_days)

        # ── Step 1: Find the most recent HVE gap day ─────────────────────────
        hve_idx  = None
        hve_info = {}

        for i in range(scan_start, n - 5):   # must be at least 5 days ago
            prior_close = float(closes.iloc[i - 1])
            day_open    = float(opens.iloc[i])
            day_close   = float(closes.iloc[i])
            day_high    = float(highs.iloc[i])
            day_low     = float(lows.iloc[i])
            day_vol     = float(volumes.iloc[i])

            if prior_close <= 0:
                continue

            gap_pct = (day_open - prior_close) / prior_close * 100

            # HVE requires a bigger gap than EP — minimum 25%
            if gap_pct < 25.0:
                continue

            # Must close strong (not fade — fading gap = distribution, not HVE)
            if day_close < day_open * 0.95:
                continue

            # Volume must be extreme — 5× ADV minimum
            adv_start = max(0, i - 20)
            adv_vols  = volumes.iloc[adv_start:i]
            if len(adv_vols) < 5:
                continue
            adv = float(adv_vols.mean())
            if adv <= 0:
                continue

            vol_ratio = day_vol / adv
            if vol_ratio < 5.0:
                continue

            # Valid HVE day — keep the most recent one
            hve_idx  = i
            hve_info = {
                "gap_pct":   round(gap_pct, 1),
                "vol_ratio": round(vol_ratio, 1),
                "gap_open":  round(day_open, 2),
                "gap_high":  round(day_high, 2),
                "gap_low":   round(day_low, 2),
                "date":      str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i]),
            }

        if hve_idx is None:
            return _empty

        # ── Step 2: Define the HVE support level ─────────────────────────────
        # Support = gap open (the level price gapped to on earnings day)
        # This is where institutional buyers stepped in — it's magnetic
        hve_support = hve_info["gap_open"]
        hve_gap_low = hve_info["gap_low"]

        # ── Step 3: Count how many times price has tested the support ─────────
        post_gap = closes.iloc[hve_idx + 1:]
        post_lows = lows.iloc[hve_idx + 1:] if "low" in df.columns else post_gap

        test_count = 0
        in_test    = False
        tolerance  = 0.05   # within 5% of support level counts as a test

        for low_val in post_lows:
            near_support = abs(float(low_val) - hve_support) / hve_support <= tolerance
            if near_support and not in_test:
                test_count += 1
                in_test     = True
            elif not near_support:
                in_test = False

        # ── Step 4: Current price vs HVE support ──────────────────────────────
        current_price   = float(closes.iloc[-1])
        current_low     = float(lows.iloc[-1]) if "low" in df.columns else current_price
        days_since_gap  = (n - 1) - hve_idx
        pct_from_level  = round((current_price - hve_support) / hve_support * 100, 1)

        # ── Step 5: Entry conditions ──────────────────────────────────────────
        # 1. Price is near the HVE support (within 8% above, or just testing it)
        near_support_now = -2.0 <= pct_from_level <= 8.0

        # 2. Price has not completely broken below HVE gap low (thesis intact)
        above_gap_low = current_price > hve_gap_low * 0.97

        # 3. At least one prior test (confirms support, not first approach)
        # First approach can also work but is slightly riskier
        has_prior_test = test_count >= 1

        # 4. Not too old — HVE loses relevance after 4 months
        not_too_old = days_since_gap <= 90

        hve_entry_ok = bool(near_support_now and above_gap_low and not_too_old)

        return {
            "hve_detected":       True,
            "hve_entry_ok":       hve_entry_ok,
            "hve_gap_date":       hve_info["date"],
            "hve_gap_pct":        hve_info["gap_pct"],
            "hve_vol_ratio":      hve_info["vol_ratio"],
            "hve_gap_open":       hve_info["gap_open"],
            "hve_gap_high":       hve_info["gap_high"],
            "hve_gap_low":        hve_info["gap_low"],
            "hve_support_level":  round(hve_support, 2),
            "hve_test_count":     test_count,
            "hve_pct_from_level": pct_from_level,
            "hve_stop":           round(hve_gap_low * 0.98, 2),
            "hve_days_since_gap": days_since_gap,
        }

    except Exception as e:
        print(f"[hve_detector] Error: {e}")
        return _empty
