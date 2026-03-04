"""
base_detector.py
----------------
Detects chart bases, pivot points, VCP stages, and base quality scores.
Works on a pandas Series of closing prices + highs/lows.
"""

import numpy as np
import pandas as pd
from typing import Optional


# ── ATR ───────────────────────────────────────────────────────────────────────

def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Average True Range over N periods."""
    if len(df) < period + 1:
        return None
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    return round(float(tr.iloc[-period:].mean()), 4)


# ── Pivot Highs / Lows ────────────────────────────────────────────────────────

def find_pivot_highs(highs: pd.Series, left: int = 5, right: int = 5) -> list[int]:
    """Return indices of pivot highs (local maxima with N bars on each side)."""
    pivots = []
    for i in range(left, len(highs) - right):
        window = highs.iloc[i - left:i + right + 1]
        if highs.iloc[i] == window.max():
            pivots.append(i)
    return pivots


def find_pivot_lows(lows: pd.Series, left: int = 5, right: int = 5) -> list[int]:
    """Return indices of pivot lows (local minima)."""
    pivots = []
    for i in range(left, len(lows) - right):
        window = lows.iloc[i - left:i + right + 1]
        if lows.iloc[i] == window.min():
            pivots.append(i)
    return pivots


# ── Base Detection ────────────────────────────────────────────────────────────

def detect_base(df: pd.DataFrame, min_bars: int = 15) -> dict:
    """
    Detects whether a stock is forming a base and scores its quality.

    Returns:
        in_base: bool
        base_type: 'flat' | 'cup' | 'vcp' | 'none'
        base_depth_pct: how far price fell from high to low in base
        base_length_bars: how many days the base has been forming
        pivot_price: the buy point (high of the handle / right side of base)
        pct_from_pivot: how close price is to the buy point
        base_score: 1-100 quality score
        vcp_stages: number of VCP contractions detected
    """
    if len(df) < min_bars:
        return _empty_base()

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    # Look at last 200 bars for base formation
    lookback = min(200, len(df))
    recent_closes = closes.iloc[-lookback:]
    recent_highs = highs.iloc[-lookback:]
    recent_lows = lows.iloc[-lookback:]

    # Find the high of the potential base (52w high area)
    base_high_idx = recent_highs.values.argmax()
    base_high = float(recent_highs.iloc[base_high_idx])

    # Only look at bars after the peak for base formation
    post_peak = recent_closes.iloc[base_high_idx:]
    post_peak_highs = recent_highs.iloc[base_high_idx:]
    post_peak_lows = recent_lows.iloc[base_high_idx:]

    if len(post_peak) < min_bars:
        return _empty_base()

    base_low = float(post_peak_lows.min())
    base_depth_pct = round((base_high - base_low) / base_high * 100, 1)
    base_length = len(post_peak)
    current_price = float(closes.iloc[-1])

    # Base type classification
    base_type = "none"
    in_base = False

    if base_depth_pct <= 15 and base_length >= 15:
        base_type = "flat"
        in_base = True
    elif base_depth_pct <= 35 and base_length >= 25:
        base_type = "cup"
        in_base = True
    elif base_depth_pct <= 25:
        base_type = "vcp"
        in_base = True

    # VCP stage count (count contractions — each tighter than the last)
    vcp_stages = _count_vcp_stages(post_peak_highs, post_peak_lows)

    # Pivot / buy point = high of the right side (last 10% of base)
    right_side_bars = max(5, base_length // 5)
    pivot_price = round(float(post_peak_highs.iloc[-right_side_bars:].max()), 4)
    pct_from_pivot = round((current_price - pivot_price) / pivot_price * 100, 2)

    # Base quality score
    base_score = _score_base(
        base_type=base_type,
        base_depth_pct=base_depth_pct,
        base_length=base_length,
        vcp_stages=vcp_stages,
        pct_from_pivot=pct_from_pivot,
        df=df,
    )

    return {
        "in_base": in_base,
        "base_type": base_type,
        "base_depth_pct": base_depth_pct,
        "base_length_bars": base_length,
        "pivot_price": pivot_price if in_base else None,
        "pct_from_pivot": pct_from_pivot if in_base else None,
        "base_score": base_score,
        "vcp_stages": vcp_stages,
        "base_high": round(base_high, 4),
        "base_low": round(base_low, 4),
    }


def _count_vcp_stages(highs: pd.Series, lows: pd.Series) -> int:
    """
    Count VCP contractions: each successive swing should be tighter than the last.
    A contraction = range (high-low) shrinks by at least 25%.
    """
    if len(highs) < 20:
        return 0

    # Split into thirds and measure range in each segment
    n = len(highs)
    segments = [
        highs.iloc[:n//3].max() - lows.iloc[:n//3].min(),
        highs.iloc[n//3:2*n//3].max() - lows.iloc[n//3:2*n//3].min(),
        highs.iloc[2*n//3:].max() - lows.iloc[2*n//3:].min(),
    ]

    stages = 0
    for i in range(1, len(segments)):
        if segments[i] < segments[i-1] * 0.75:  # 25%+ contraction
            stages += 1

    return stages


def _score_base(
    base_type: str,
    base_depth_pct: float,
    base_length: int,
    vcp_stages: int,
    pct_from_pivot: float,
    df: pd.DataFrame,
) -> int:
    if base_type == "none":
        return 0

    score = 0

    # Base type (flat bases score highest — tightest action)
    score += {"flat": 25, "vcp": 22, "cup": 18}.get(base_type, 0)

    # Depth (shallower = tighter = better)
    if base_depth_pct <= 10:
        score += 20
    elif base_depth_pct <= 15:
        score += 15
    elif base_depth_pct <= 25:
        score += 10
    else:
        score += 5

    # Length (long enough to shake out weak holders)
    if 20 <= base_length <= 60:
        score += 15
    elif base_length > 60:
        score += 10
    else:
        score += 5

    # VCP stages (more contractions = more coiled)
    score += min(20, vcp_stages * 8)

    # Proximity to pivot (within 5% = near buy point)
    if pct_from_pivot is not None:
        if -2 <= pct_from_pivot <= 2:
            score += 15  # right at pivot
        elif -5 <= pct_from_pivot <= 5:
            score += 10
        elif pct_from_pivot < -15:
            score += 2   # too far below pivot
        else:
            score += 5

    # Volume dry-up in base (declining volume = smart money not selling)
    if len(df) >= 20:
        vol = df["volume"]
        recent_vol = float(vol.iloc[-10:].mean())
        base_vol = float(vol.iloc[-40:-10].mean()) if len(vol) >= 40 else float(vol.mean())
        if base_vol > 0 and recent_vol / base_vol < 0.7:
            score += 5  # volume drying up — positive

    return min(100, score)


def _empty_base() -> dict:
    return {
        "in_base": False,
        "base_type": "none",
        "base_depth_pct": None,
        "base_length_bars": None,
        "pivot_price": None,
        "pct_from_pivot": None,
        "base_score": 0,
        "vcp_stages": 0,
        "base_high": None,
        "base_low": None,
    }


# ── LL-HL Pivot Detection ─────────────────────────────────────────────────────
# Replication of oratnek's LL-HL Pivot indicator logic.
# Scans pivot lengths 3–10 simultaneously, selects the tightest valid structure
# (lowest pivot line = best risk/reward), returns the breakout resistance level.

def detect_ll_hl_pivot(df: pd.DataFrame, min_length: int = 3, max_length: int = 10) -> dict:
    """
    Scan for a bullish LL → HL structure across multiple pivot lengths.

    Logic (mirrors oratnek's indicator):
      1. For each length L in [min_length, max_length]:
         - Find the most recent pivot low (LL candidate)
         - Find a subsequent pivot low that is HIGHER than LL (= HL)
         - The resistance / pivot line = highest HIGH between LL and HL
         - Structure is valid as long as price > HL (not violated)
      2. Priority: "Tightest" — pick the structure with the LOWEST pivot line
         (closest resistance to current price = best R:R, mirrors oratnek default)
      3. Invalidation: if price has closed below the HL the structure is discarded

    Returns dict with keys:
      ll_hl_detected  : bool
      ll_price        : float   — price of the LL pivot low
      hl_price        : float   — price of the HL pivot low (support)
      pivot_line      : float   — resistance / breakout trigger
      pct_from_pivot  : float   — % price is from pivot line (negative = below)
      approaching_pivot: bool   — price within 3% below the pivot line
      pivot_broken    : bool    — price has already closed above pivot line
      pivot_length    : int     — which pivot length produced this structure
    """
    if len(df) < (max_length * 2 + 5):
        return _empty_ll_hl()

    closes = df["close"]
    highs  = df["high"]
    lows   = df["low"]
    price  = float(closes.iloc[-1])

    best: dict = {}
    best_pivot_line = float("inf")

    for length in range(min_length, max_length + 1):
        # Need at least 3×length bars for two pivot lows to form
        if len(lows) < length * 3 + length:
            continue

        # Scan for pivot lows from oldest → newest within last 120 bars
        lookback = min(120, len(lows) - length)
        pivot_lows = []  # list of (index, price)
        for i in range(length, lookback - length):
            idx = -(lookback - i)  # negative index from end
            window = lows.iloc[idx - length: idx + length + 1]
            candidate = float(lows.iloc[idx])
            if candidate == float(window.min()):
                pivot_lows.append((idx, candidate))

        if len(pivot_lows) < 2:
            continue

        # Walk pairs from most recent backwards looking for LL → HL
        for j in range(len(pivot_lows) - 1, 0, -1):
            hl_idx, hl_price = pivot_lows[j]
            ll_idx, ll_price = pivot_lows[j - 1]

            # HL must be strictly higher than LL
            if hl_price <= ll_price:
                continue

            # Structure still valid — price must not have closed below HL
            if price < hl_price:
                continue

            # Pivot line = highest HIGH between LL and HL
            # Convert negative indices to slice correctly
            if ll_idx < 0 and hl_idx < 0:
                hi_slice = highs.iloc[ll_idx: hl_idx if hl_idx != 0 else None]
            else:
                continue  # skip edge cases

            if hi_slice.empty:
                continue

            pivot_line = float(hi_slice.max())

            # Tightest priority: lowest pivot line (closest resistance)
            if pivot_line < best_pivot_line and pivot_line > price * 0.90:
                best_pivot_line = pivot_line
                pct_from = round((price - pivot_line) / pivot_line * 100, 2)
                best = {
                    "ll_hl_detected":   True,
                    "ll_price":         round(ll_price, 4),
                    "hl_price":         round(hl_price, 4),
                    "pivot_line":       round(pivot_line, 4),
                    "pct_from_pivot":   pct_from,
                    "approaching_pivot": -3.0 <= pct_from < 0,
                    "pivot_broken":     pct_from >= 0,
                    "pivot_length":     length,
                }
                break  # found best for this length, move to next

    return best if best else _empty_ll_hl()


def _empty_ll_hl() -> dict:
    return {
        "ll_hl_detected":    False,
        "ll_price":          None,
        "hl_price":          None,
        "pivot_line":        None,
        "pct_from_pivot":    None,
        "approaching_pivot": False,
        "pivot_broken":      False,
        "pivot_length":      None,
    }


# ── Darvas Box Detection ──────────────────────────────────────────────────────
# Replication of oratnek's Darvas Lines/Box indicator logic.
# Tracks the N-bar consolidation range, detects price approaching box top
# or breaking out above it (the actionable event).

def detect_darvas_box(df: pd.DataFrame, bars: int = 20, max_box_height_pct: float = 15.0) -> dict:
    """
    Detect a Darvas box consolidation and breakout setup.

    Logic (mirrors oratnek's indicator):
      1. Box top    = highest HIGH over the last `bars` bars
      2. Box bottom = lowest  LOW  over the same window
      3. Box height must be ≤ max_box_height_pct (filters wide/loose ranges)
      4. Status:
         - "breakout"    : today's close > box_top (energy release upward)
         - "approaching" : price within 2% below box_top (imminent breakout watch)
         - "in_box"      : price inside the range (still coiling)
         - "below_box"   : price below box_bottom (structure failed)
      5. Box bars tracks how many days the box has been forming (maturity)

    Returns dict with keys:
      darvas_detected  : bool
      box_top          : float
      box_bottom       : float
      box_height_pct   : float
      box_bars         : int   — how long the box has been forming
      darvas_status    : str   — 'breakout' | 'approaching' | 'in_box' | 'below_box'
      pct_from_box_top : float — % price is from box top (negative = below)
    """
    if len(df) < bars + 5:
        return _empty_darvas()

    closes = df["close"]
    highs  = df["high"]
    lows   = df["low"]
    price  = float(closes.iloc[-1])

    window_highs = highs.iloc[-bars:]
    window_lows  = lows.iloc[-bars:]

    box_top    = float(window_highs.max())
    box_bottom = float(window_lows.min())

    if box_top <= 0 or box_bottom <= 0:
        return _empty_darvas()

    box_height_pct = round((box_top - box_bottom) / box_top * 100, 2)

    # Reject loose / wide boxes — not a tight consolidation
    if box_height_pct > max_box_height_pct:
        return _empty_darvas()

    pct_from_top = round((price - box_top) / box_top * 100, 2)

    if pct_from_top >= 0:
        status = "breakout"
    elif pct_from_top >= -2.0:
        status = "approaching"
    elif price >= box_bottom:
        status = "in_box"
    else:
        status = "below_box"

    # Count how many consecutive bars price has stayed within the box
    box_bars = 0
    for i in range(1, len(closes) + 1):
        c = float(closes.iloc[-i])
        if box_bottom * 0.98 <= c <= box_top * 1.02:
            box_bars += 1
        else:
            break

    return {
        "darvas_detected":  status in ("approaching", "in_box", "breakout"),
        "box_top":          round(box_top, 4),
        "box_bottom":       round(box_bottom, 4),
        "box_height_pct":   box_height_pct,
        "box_bars":         box_bars,
        "darvas_status":    status,
        "pct_from_box_top": pct_from_top,
    }


def _empty_darvas() -> dict:
    return {
        "darvas_detected":  False,
        "box_top":          None,
        "box_bottom":       None,
        "box_height_pct":   None,
        "box_bars":         None,
        "darvas_status":    None,
        "pct_from_box_top": None,
    }


# ── Flag & Pennant Detector ───────────────────────────────────────────────────
#
# Classic momentum-continuation pattern:
#   1. POLE  — sharp strong move (≥8% in ≤10 bars) on elevated volume
#   2. FLAG  — tight descending consolidation with 3+ trendline touches,
#              thin candles, volume drying up (market resting, not distributing)
#   3. ENTRY — break of the most recent swing high in the flag / pennant
#   4. STOP  — Low of the breakout day (LOD)
#
# Bull flags:   price slopes slightly DOWN after the pole (descending channel)
# Pennants:     price forms a symmetrical triangle (lower highs + higher lows)
# Both are valid — we detect both and label them separately.

def detect_flag_pennant(
    df: pd.DataFrame,
    min_pole_pct:    float = 8.0,   # minimum % move to qualify as a pole
    max_pole_bars:   int   = 10,    # pole must form within this many bars
    min_flag_bars:   int   = 4,     # flag needs at least this many bars to form
    max_flag_bars:   int   = 25,    # flag that's >25 bars is a base, not a flag
    max_flag_retrace: float = 0.62, # flag must not retrace more than 62% of pole (Fib)
    min_tl_touches:  int   = 3,     # minimum trendline touches required
    touch_tolerance: float = 0.015, # 1.5% tolerance for a "touch"
) -> dict:
    """
    Detect a Bull Flag or Pennant continuation pattern.

    Returns dict with:
      flag_detected    : bool
      flag_type        : 'bull_flag' | 'pennant' | None
      pole_start_price : float  — price at the base of the pole
      pole_high_price  : float  — price at the top of the pole
      pole_pct         : float  — % gain of the pole
      pole_bars        : int    — how many bars the pole took
      flag_bars        : int    — how many bars the flag/pennant has been forming
      flag_low         : float  — lowest low in the flag
      flag_retrace_pct : float  — how much of the pole was given back (%)
      tl_touches       : int    — number of confirmed trendline touches
      tl_slope         : float  — slope of upper trendline (negative = descending)
      breakout_level   : float  — the level price needs to clear for entry trigger
      flag_status      : 'watch' | 'breaking' | 'broken_out' | None
        watch       = valid flag, not yet at breakout level
        breaking    = price within 1.5% of breakout level (actionable)
        broken_out  = price has cleared the breakout level today/recently
      stop_price       : float  — stop = low of breakout bar, or flag low
      target_price     : float  — measured move = breakout level + pole height
      vol_dry_flag     : bool   — True if volume has contracted in the flag
      pole_vol_ratio   : float  — vol on pole vs prior ADV (confirms pole strength)
    """
    _empty = {
        "flag_detected":    False,
        "flag_type":        None,
        "pole_start_price": None,
        "pole_high_price":  None,
        "pole_pct":         None,
        "pole_bars":        None,
        "flag_bars":        None,
        "flag_low":         None,
        "flag_retrace_pct": None,
        "tl_touches":       None,
        "tl_slope":         None,
        "breakout_level":   None,
        "flag_status":      None,
        "stop_price":       None,
        "target_price":     None,
        "vol_dry_flag":     False,
        "pole_vol_ratio":   None,
    }

    try:
        if df is None or len(df) < max_pole_bars + min_flag_bars + 10:
            return _empty

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"] if "volume" in df.columns else None

        n = len(df)
        price = float(closes.iloc[-1])

        # ── Step 1: Find the pole ─────────────────────────────────────────────
        # Scan the last ~60 bars for a strong upward pole.
        # The pole top must be followed by a consolidation (the flag).
        # We scan from oldest to newest so we get the most RECENT valid pole.

        best_pole = None

        scan_range = range(max(0, n - 60), n - min_flag_bars - 1)

        for start_i in scan_range:
            for end_i in range(start_i + 2, min(start_i + max_pole_bars + 1, n - min_flag_bars)):
                pole_start_px = float(closes.iloc[start_i])
                pole_high_px  = float(highs.iloc[end_i])

                if pole_start_px <= 0:
                    continue

                pole_pct = (pole_high_px - pole_start_px) / pole_start_px * 100

                if pole_pct < min_pole_pct:
                    continue

                # Pole must be mostly consecutive up bars (not a random scatter)
                pole_slice = closes.iloc[start_i:end_i + 1]
                up_bars = sum(1 for i in range(1, len(pole_slice))
                              if float(pole_slice.iloc[i]) > float(pole_slice.iloc[i-1]))
                up_ratio = up_bars / max(1, len(pole_slice) - 1)

                if up_ratio < 0.55:   # at least 55% of bars were up
                    continue

                # Pole volume check — average volume during pole vs prior 20-bar ADV
                pole_vol_ratio = None
                if volumes is not None:
                    adv_start = max(0, start_i - 20)
                    adv_vols  = volumes.iloc[adv_start:start_i]
                    pole_vols = volumes.iloc[start_i:end_i + 1]
                    if len(adv_vols) >= 3:
                        adv = float(adv_vols.mean())
                        if adv > 0:
                            pole_vol_ratio = round(float(pole_vols.mean()) / adv, 2)

                # Keep highest pole_pct; use recency (end_i) as tiebreaker
                if best_pole is None or pole_pct > best_pole["pole_pct"] or                         (pole_pct >= best_pole["pole_pct"] * 0.99 and end_i > best_pole["end_i"]):
                    best_pole = {
                        "start_i":      start_i,
                        "end_i":        end_i,
                        "start_px":     round(pole_start_px, 4),
                        "high_px":      round(pole_high_px, 4),
                        "pole_pct":     round(pole_pct, 2),
                        "pole_bars":    end_i - start_i,
                        "vol_ratio":    pole_vol_ratio,
                    }

        if best_pole is None:
            return _empty

        pole_end_i    = best_pole["end_i"]
        pole_high_px  = best_pole["high_px"]
        pole_start_px = best_pole["start_px"]
        pole_height   = pole_high_px - pole_start_px   # absolute height for measured move

        # ── Step 2: Identify the flag window (bars after pole top) ────────────
        flag_start_i = pole_end_i + 1
        flag_end_i   = n - 1   # up to today

        flag_bars = flag_end_i - flag_start_i + 1

        if flag_bars < min_flag_bars or flag_bars > max_flag_bars:
            return _empty

        flag_highs  = highs.iloc[flag_start_i:flag_end_i + 1]
        flag_lows   = lows.iloc[flag_start_i:flag_end_i + 1]
        flag_closes = closes.iloc[flag_start_i:flag_end_i + 1]

        flag_high = float(flag_highs.max())
        flag_low  = float(flag_lows.min())

        # Flag must not retrace more than 50% of the pole — otherwise it's a base
        retrace_pct = (pole_high_px - flag_low) / pole_height * 100
        if retrace_pct > max_flag_retrace * 100:
            return _empty

        # Flag highs should be declining (or at worst flat) — not making new highs
        # (a flag that keeps pushing to new highs is a breakout, not a flag)
        if flag_high > pole_high_px * 1.02:
            return _empty

        # ── Step 3: Fit descending trendline through flag highs ───────────────
        # Use linear regression on the flag highs (by bar index).
        flag_h_arr = flag_highs.values.astype(float)
        flag_l_arr = flag_lows.values.astype(float)
        x = np.arange(len(flag_h_arr), dtype=float)

        # Upper trendline: fit through highs
        if len(x) >= 2:
            slope_h, intercept_h = np.polyfit(x, flag_h_arr, 1)
        else:
            return _empty

        # Lower trendline: fit through lows
        slope_l, intercept_l = np.polyfit(x, flag_l_arr, 1)

        # ── Step 4: Count trendline touches ──────────────────────────────────
        # A touch = a bar's high is within tolerance of the fitted upper trendline.
        tl_touches = 0
        for i, h in enumerate(flag_h_arr):
            tl_val = slope_h * i + intercept_h
            if abs(h - tl_val) / tl_val <= touch_tolerance:
                tl_touches += 1

        if tl_touches < min_tl_touches:
            return _empty

        # ── Step 5: Classify — bull flag vs pennant ───────────────────────────
        # Bull flag:  upper TL slopes down, lower TL also slopes down (parallel channel)
        # Pennant:    upper TL slopes down, lower TL slopes UP (converging = triangle)
        if slope_l > 0.0 and slope_h < 0.0:
            flag_type = "pennant"
        elif slope_h < -0.001:   # clearly descending upper TL
            flag_type = "bull_flag"
        else:
            # Flat or ascending = not a flag
            return _empty

        # ── Step 6: Breakout level ────────────────────────────────────────────
        # = most recent swing high within the flag
        # (the level the 3rd-step description calls "Break of Recent High")
        # Use the highest high in the LAST THIRD of the flag — the most actionable level
        last_third_start = flag_start_i + max(0, flag_bars * 2 // 3)
        recent_flag_high = float(highs.iloc[last_third_start:flag_end_i + 1].max())
        breakout_level   = round(recent_flag_high * 1.001, 4)  # tiny buffer above

        # ── Step 7: Status ────────────────────────────────────────────────────
        pct_from_bo = (price - breakout_level) / breakout_level * 100
        if pct_from_bo >= 0:
            flag_status = "broken_out"
        elif pct_from_bo >= -1.5:
            flag_status = "breaking"
        else:
            flag_status = "watch"

        # ── Step 8: Stop & Target ─────────────────────────────────────────────
        # Stop = flag low (if watching) or LOD of breakout bar (if breaking/broken)
        stop_price   = round(flag_low * 0.995, 4)   # just below flag low
        target_price = round(breakout_level + pole_height, 4)   # measured move

        # ── Step 9: Volume dry-up in flag ─────────────────────────────────────
        vol_dry_flag = False
        if volumes is not None and len(flag_closes) >= 4:
            pole_avg_vol = float(volumes.iloc[max(0, pole_end_i - best_pole["pole_bars"]):pole_end_i + 1].mean())
            flag_avg_vol = float(volumes.iloc[flag_start_i:flag_end_i + 1].mean())
            if pole_avg_vol > 0:
                vol_dry_flag = flag_avg_vol < pole_avg_vol * 0.7   # 30%+ volume contraction

        return {
            "flag_detected":    True,
            "flag_type":        flag_type,
            "pole_start_price": best_pole["start_px"],
            "pole_high_price":  best_pole["high_px"],
            "pole_pct":         best_pole["pole_pct"],
            "pole_bars":        best_pole["pole_bars"],
            "flag_bars":        flag_bars,
            "flag_low":         round(flag_low, 4),
            "flag_retrace_pct": round(retrace_pct, 1),
            "tl_touches":       tl_touches,
            "tl_slope":         round(slope_h, 4),
            "breakout_level":   breakout_level,
            "flag_status":      flag_status,
            "stop_price":       stop_price,
            "target_price":     target_price,
            "vol_dry_flag":     vol_dry_flag,
            "pole_vol_ratio":   best_pole["vol_ratio"],
        }

    except Exception as e:
        print(f"[flag_detector] Error: {e}")
        return _empty


def _empty_flag() -> dict:
    return {
        "flag_detected":    False,
        "flag_type":        None,
        "pole_start_price": None,
        "pole_high_price":  None,
        "pole_pct":         None,
        "pole_bars":        None,
        "flag_bars":        None,
        "flag_low":         None,
        "flag_retrace_pct": None,
        "tl_touches":       None,
        "tl_slope":         None,
        "breakout_level":   None,
        "flag_status":      None,
        "stop_price":       None,
        "target_price":     None,
        "vol_dry_flag":     False,
        "pole_vol_ratio":   None,
    }
