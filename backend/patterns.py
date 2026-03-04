"""
patterns.py
-----------
Chart pattern detection engine.

Patterns:
  1. Bull Flag     — pole + tight consolidation + breakout
  2. VCP           — volatility contraction pattern (Minervini)
  3. Cup & Handle  — rounded base + tight handle + breakout
  4. Asc Triangle  — flat resistance + higher lows coiling to apex

Each detector returns a dict with:
  - pattern_type, stage, score, description
  - key levels: entry, stop, targets
  - supporting metrics
"""

import numpy as np
import pandas as pd
from typing import Optional


# ── Shared helpers ────────────────────────────────────────────────────────────

def _avg_vol(volumes: pd.Series, lookback: int = 20) -> Optional[float]:
    if len(volumes) < lookback + 1:
        return None
    return float(volumes.iloc[-(lookback + 1):-1].mean())


def _atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    try:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.iloc[-period:].mean())
    except Exception:
        return None


def _linreg_slope(series: pd.Series) -> float:
    """Normalised slope of a linear regression — positive = rising."""
    try:
        y = series.values
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]
        return float(slope / series.mean())  # normalise by mean
    except Exception:
        return 0.0


def _fit_trendline(highs: pd.Series):
    """Fit a line through the highs. Returns (slope, intercept)."""
    x = np.arange(len(highs))
    return np.polyfit(x, highs.values, 1)


def _score_clamp(s: float) -> float:
    return round(min(10.0, max(1.0, s)), 1)


# ── 1. Bull Flag ──────────────────────────────────────────────────────────────

def detect_flag(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> Optional[dict]:
    """
    Bull Flag detector.

    Pole:  3-10 day move of 8%+ on above-average volume
    Flag:  5-20 day consolidation, drifting back 3-15%
           Volume drying up (flag avg vol < pole avg vol)
           Higher lows preferred
    Entry: Break above flag high on volume
    """
    try:
        if df is None or len(df) < 30:
            return None
        if rs_rank < 70:
            return None

        closes  = df["close"]
        volumes = df["volume"]
        highs   = df["high"]
        lows    = df["low"]

        price     = float(closes.iloc[-1])
        avg_vol20 = _avg_vol(volumes, 20)
        if not avg_vol20:
            return None

        # ── Find the pole ──────────────────────────────────────────────────
        # Scan back up to 40 days for a strong 3-10 day surge
        best_pole = None
        for pole_end in range(5, min(41, len(closes) - 5)):
            for pole_len in range(3, 11):
                pole_start = pole_end + pole_len
                if pole_start >= len(closes):
                    continue

                pole_closes  = closes.iloc[-(pole_start):-( pole_end)]
                pole_volumes = volumes.iloc[-(pole_start):-( pole_end)]

                if len(pole_closes) < 2:
                    continue

                pole_low   = float(pole_closes.iloc[0])
                pole_high  = float(pole_closes.iloc[-1])
                pole_move  = (pole_high - pole_low) / pole_low * 100

                if pole_move < 8:
                    continue

                pole_avg_vol = float(pole_volumes.mean())
                if pole_avg_vol < avg_vol20 * 1.3:  # pole must have above-avg vol
                    continue

                if best_pole is None or pole_move > best_pole["move"]:
                    best_pole = {
                        "move":      round(pole_move, 1),
                        "pole_high": pole_high,
                        "pole_low":  pole_low,
                        "pole_len":  pole_len,
                        "pole_end":  pole_end,
                        "avg_vol":   pole_avg_vol,
                    }

        if not best_pole:
            return None

        # ── Flag consolidation ────────────────────────────────────────────
        flag_len  = best_pole["pole_end"]  # days since pole ended
        if flag_len < 3 or flag_len > 25:
            return None

        flag_closes  = closes.iloc[-flag_len:]
        flag_volumes = volumes.iloc[-flag_len:]
        flag_highs   = highs.iloc[-flag_len:]
        flag_lows    = lows.iloc[-flag_len:]

        flag_high = float(flag_highs.max())
        flag_low  = float(flag_lows.min())

        # Flag depth — how much did it pull back from pole high?
        pole_high   = best_pole["pole_high"]
        flag_depth  = (pole_high - float(flag_closes.min())) / pole_high * 100

        if flag_depth < 2 or flag_depth > 18:  # too shallow or too deep
            return None

        # Volume dry-up in flag (good flags have declining vol)
        flag_avg_vol  = float(flag_volumes.mean())
        vol_dry_ratio = flag_avg_vol / best_pole["avg_vol"]  # < 0.7 = good dry-up

        # Slope of flag — slight downward drift is ideal
        flag_slope = _linreg_slope(flag_closes)

        # Higher lows in flag?
        if len(flag_lows) >= 4:
            first_half_low  = float(flag_lows.iloc[:len(flag_lows)//2].min())
            second_half_low = float(flag_lows.iloc[len(flag_lows)//2:].min())
            higher_lows = second_half_low >= first_half_low * 0.99
        else:
            higher_lows = False

        # ── Stage detection ───────────────────────────────────────────────
        # Is price breaking out now or still forming?
        today_vol     = float(volumes.iloc[-1])
        vol_ratio_now = today_vol / avg_vol20

        at_flag_high   = price >= flag_high * 0.995
        breaking_out   = at_flag_high and vol_ratio_now >= 1.5
        still_forming  = not breaking_out and flag_depth >= 2

        stage = "breaking_out" if breaking_out else "forming"

        # ── Entry / stops / targets ───────────────────────────────────────
        atr_val = _atr(df) or price * 0.02
        entry   = round(flag_high * 1.002, 2)  # just above flag high
        stop    = round(flag_low * 0.99, 2)
        t1      = round(entry + best_pole["move"] / 100 * entry * 0.5, 2)  # 50% of pole
        t2      = round(entry + best_pole["move"] / 100 * entry * 0.8, 2)  # 80% of pole
        t3      = round(entry + best_pole["move"] / 100 * entry, 2)        # full pole

        # ── Score ─────────────────────────────────────────────────────────
        score = 5.0
        if best_pole["move"] >= 20:   score += 1.5
        elif best_pole["move"] >= 12: score += 1.0
        if vol_dry_ratio <= 0.5:      score += 1.5
        elif vol_dry_ratio <= 0.7:    score += 1.0
        if higher_lows:               score += 0.5
        if flag_depth <= 8:           score += 0.5
        if vcs and vcs <= 4:          score += 0.5
        if rs_rank >= 90:             score += 0.5
        if breaking_out:              score += 1.0

        chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)

        return {
            "ticker":        ticker,
            "pattern_type":  "FLAG",
            "stage":         stage,
            "price":         round(price, 2),
            "chg":           chg,
            "rs":            rs_rank,
            "vcs":           vcs,
            "signal_score":  _score_clamp(score),
            # Pole
            "pole_move_pct": best_pole["move"],
            "pole_len_days": best_pole["pole_len"],
            "pole_high":     round(pole_high, 2),
            # Flag
            "flag_depth_pct":  round(flag_depth, 1),
            "flag_len_days":   flag_len,
            "flag_high":       round(flag_high, 2),
            "flag_low":        round(flag_low, 2),
            "vol_dry_ratio":   round(vol_dry_ratio, 2),
            "higher_lows":     higher_lows,
            "vol_ratio":       round(vol_ratio_now, 2),
            # Levels
            "entry":    entry,
            "stop_price": stop,
            "target_1": t1,
            "target_2": t2,
            "target_3": t3,
            "atr":      round(atr_val, 4),
            # Description
            "description": (
                f"{best_pole['move']:.0f}% pole over {best_pole['pole_len']}d · "
                f"{flag_depth:.0f}% flag depth · "
                f"vol dry-up {vol_dry_ratio:.2f}x"
            ),
        }

    except Exception as e:
        print(f"[patterns] FLAG {ticker}: {e}")
        return None


# ── 2. VCP (Volatility Contraction Pattern) ───────────────────────────────────

def detect_vcp(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> Optional[dict]:
    """
    Minervini VCP detector.

    Looks for 3-4 successive contractions:
      - Each correction shallower than the last
      - Each contraction period shorter than the last
      - Volume declining through contractions
      - Price tightening near pivot high
    """
    try:
        if df is None or len(df) < 45:
            return None
        if rs_rank < 70:
            return None

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"]

        price     = float(closes.iloc[-1])
        avg_vol20 = _avg_vol(volumes, 20)
        if not avg_vol20:
            return None

        # ── Find contractions over the last 60 days ───────────────────────
        # Divide into 4 windows and measure depth of each correction
        window = min(60, len(closes) - 1)
        seg_len = window // 4

        contractions = []
        for i in range(4):
            start = -(window - i * seg_len)
            end   = -(window - (i + 1) * seg_len) if i < 3 else None
            seg_c = closes.iloc[start:end]
            seg_h = highs.iloc[start:end]
            seg_l = lows.iloc[start:end]
            seg_v = volumes.iloc[start:end]

            if len(seg_c) < 3:
                continue

            seg_high = float(seg_h.max())
            seg_low  = float(seg_l.min())
            depth    = (seg_high - seg_low) / seg_high * 100
            avg_v    = float(seg_v.mean())

            contractions.append({
                "depth":   depth,
                "avg_vol": avg_v,
                "len":     len(seg_c),
            })

        if len(contractions) < 3:
            return None

        # ── Check that each contraction is shallower ──────────────────────
        depths = [c["depth"] for c in contractions]
        vols   = [c["avg_vol"] for c in contractions]

        # Count how many successive pairs are contracting
        contracting_pairs = sum(
            1 for i in range(1, len(depths))
            if depths[i] < depths[i - 1] * 1.1  # allow 10% tolerance
        )

        vol_declining_pairs = sum(
            1 for i in range(1, len(vols))
            if vols[i] <= vols[i - 1]
        )

        if contracting_pairs < 2:
            return None

        # ── Pivot high — recent 20-day high ──────────────────────────────
        pivot_high = float(highs.iloc[-20:].max())
        pct_from_pivot = (price - pivot_high) / pivot_high * 100

        # Price should be within 10% of pivot (forming or breaking)
        if pct_from_pivot < -10:
            return None

        # ── VCS confirmation ──────────────────────────────────────────────
        # VCS should be tightening — last contraction should be tightest
        last_depth  = depths[-1]
        first_depth = depths[0]
        contraction_ratio = last_depth / first_depth if first_depth > 0 else 1

        # ── Stage ─────────────────────────────────────────────────────────
        today_vol  = float(volumes.iloc[-1])
        vol_ratio  = today_vol / avg_vol20
        at_pivot   = price >= pivot_high * 0.98
        breaking   = at_pivot and vol_ratio >= 1.5

        stage = "breaking_out" if breaking else "stage_2" if at_pivot else "forming"

        # ── Levels ───────────────────────────────────────────────────────
        atr_val = _atr(df) or price * 0.02
        entry   = round(pivot_high * 1.002, 2)
        stop    = round(float(lows.iloc[-10:].min()) * 0.99, 2)
        t1      = round(entry + 2 * atr_val, 2)
        t2      = round(entry + 4 * atr_val, 2)
        t3      = round(entry + 7 * atr_val, 2)

        # ── Score ─────────────────────────────────────────────────────────
        score = 5.0
        if contracting_pairs >= 3:      score += 1.5
        elif contracting_pairs >= 2:    score += 1.0
        if vol_declining_pairs >= 2:    score += 1.0
        if contraction_ratio <= 0.4:    score += 1.0  # very tight final contraction
        elif contraction_ratio <= 0.6:  score += 0.5
        if vcs and vcs <= 3:            score += 1.0
        elif vcs and vcs <= 5:          score += 0.5
        if rs_rank >= 90:               score += 0.5
        if at_pivot:                    score += 0.5
        if breaking:                    score += 1.0

        chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)

        return {
            "ticker":       ticker,
            "pattern_type": "VCP",
            "stage":        stage,
            "price":        round(price, 2),
            "chg":          chg,
            "rs":           rs_rank,
            "vcs":          vcs,
            "signal_score": _score_clamp(score),
            # VCP metrics
            "contractions":       contracting_pairs,
            "contraction_ratio":  round(contraction_ratio, 2),
            "depths":             [round(d, 1) for d in depths],
            "vol_declining":      vol_declining_pairs,
            "pivot_high":         round(pivot_high, 2),
            "pct_from_pivot":     round(pct_from_pivot, 1),
            "vol_ratio":          round(vol_ratio, 2),
            # Levels
            "entry":      entry,
            "stop_price": stop,
            "target_1":   t1,
            "target_2":   t2,
            "target_3":   t3,
            "atr":        round(atr_val, 4),
            "description": (
                f"{contracting_pairs} contractions · "
                f"ratio {contraction_ratio:.2f} · "
                f"{pct_from_pivot:.1f}% from pivot"
            ),
        }

    except Exception as e:
        print(f"[patterns] VCP {ticker}: {e}")
        return None


# ── 3. Cup & Handle ───────────────────────────────────────────────────────────

def detect_cup_handle(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> Optional[dict]:
    """
    O'Neil Cup & Handle detector.

    Cup:    6-30 weeks, U-shaped (rounded bottom preferred over V)
            Depth 15-35% from cup left high to cup low
            Right side recovers to within 5% of left side high
    Handle: 1-4 weeks, drifts back 5-15% in upper half of cup
            Volume dries up in handle
    Entry:  Break above handle high / cup right side on volume
    """
    try:
        if df is None or len(df) < 60:
            return None
        if rs_rank < 70:
            return None

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"]

        price     = float(closes.iloc[-1])
        avg_vol20 = _avg_vol(volumes, 20)
        if not avg_vol20:
            return None

        # ── Try different cup lengths ─────────────────────────────────────
        best_cup = None

        for cup_weeks in range(6, min(31, len(closes) // 5)):
            cup_days = cup_weeks * 5

            if cup_days + 5 > len(closes):
                continue

            # Cup window (before any handle)
            cup_closes = closes.iloc[-(cup_days + 5):-5]
            cup_highs  = highs.iloc[-(cup_days + 5):-5]
            cup_lows   = lows.iloc[-(cup_days + 5):-5]
            cup_vols   = volumes.iloc[-(cup_days + 5):-5]

            if len(cup_closes) < 20:
                continue

            cup_left_high  = float(cup_closes.iloc[:cup_days//4].max())
            cup_right_high = float(cup_closes.iloc[-(cup_days//4):].max())
            cup_bottom     = float(cup_lows.min())

            # Cup depth
            cup_depth = (cup_left_high - cup_bottom) / cup_left_high * 100
            if cup_depth < 12 or cup_depth > 40:
                continue

            # Right side must recover to within 5% of left side
            recovery = (cup_right_high - cup_bottom) / (cup_left_high - cup_bottom)
            if recovery < 0.85:
                continue

            # U-shape check: bottom third should be flatter than edges
            third = cup_days // 3
            bottom_range = float(cup_closes.iloc[third:-third].max()) - float(cup_closes.iloc[third:-third].min())
            edge_range   = max(
                float(cup_closes.iloc[:third].max()) - float(cup_closes.iloc[:third].min()),
                float(cup_closes.iloc[-third:].max()) - float(cup_closes.iloc[-third:].min()),
            )
            is_rounded = bottom_range <= edge_range * 1.5

            score_base = 5.0
            if is_rounded:       score_base += 0.5
            if cup_depth <= 25:  score_base += 0.5
            if recovery >= 0.95: score_base += 0.5

            if best_cup is None or score_base > best_cup["score_base"]:
                best_cup = {
                    "left_high":   cup_left_high,
                    "right_high":  cup_right_high,
                    "bottom":      cup_bottom,
                    "depth":       cup_depth,
                    "recovery":    recovery,
                    "weeks":       cup_weeks,
                    "is_rounded":  is_rounded,
                    "score_base":  score_base,
                    "avg_vol":     float(cup_vols.mean()),
                }

        if not best_cup:
            return None

        # ── Handle ────────────────────────────────────────────────────────
        handle_closes = closes.iloc[-5:]
        handle_highs  = highs.iloc[-5:]
        handle_lows   = lows.iloc[-5:]
        handle_vols   = volumes.iloc[-5:]

        handle_high  = float(handle_highs.max())
        handle_low   = float(handle_lows.min())
        handle_depth = (handle_high - handle_low) / handle_high * 100

        # Handle must be in upper half of cup
        cup_midpoint = best_cup["bottom"] + (best_cup["left_high"] - best_cup["bottom"]) * 0.5
        handle_valid = handle_low >= cup_midpoint * 0.97

        # Volume dry-up in handle
        handle_avg_vol = float(handle_vols.mean())
        vol_dry = handle_avg_vol / best_cup["avg_vol"]

        # ── Pivot = cup right high ────────────────────────────────────────
        pivot = best_cup["right_high"]
        pct_from_pivot = (price - pivot) / pivot * 100

        today_vol = float(volumes.iloc[-1])
        vol_ratio = today_vol / avg_vol20
        breaking  = price >= pivot * 0.99 and vol_ratio >= 1.5

        stage = "breaking_out" if breaking else "handle_forming" if handle_valid else "right_side"

        # ── Levels ───────────────────────────────────────────────────────
        atr_val = _atr(df) or price * 0.02
        cup_range = best_cup["left_high"] - best_cup["bottom"]
        entry   = round(pivot * 1.002, 2)
        stop    = round(handle_low * 0.99, 2)
        t1      = round(entry + cup_range * 0.5, 2)
        t2      = round(entry + cup_range * 0.8, 2)
        t3      = round(entry + cup_range, 2)

        # ── Score ─────────────────────────────────────────────────────────
        score = best_cup["score_base"]
        if handle_valid:          score += 0.5
        if handle_depth <= 10:    score += 0.5
        if vol_dry <= 0.6:        score += 1.0
        elif vol_dry <= 0.8:      score += 0.5
        if rs_rank >= 90:         score += 0.5
        if vcs and vcs <= 4:      score += 0.5
        if breaking:              score += 1.0

        chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)

        return {
            "ticker":       ticker,
            "pattern_type": "CUP_HANDLE",
            "stage":        stage,
            "price":        round(price, 2),
            "chg":          chg,
            "rs":           rs_rank,
            "vcs":          vcs,
            "signal_score": _score_clamp(score),
            # Cup metrics
            "cup_weeks":       best_cup["weeks"],
            "cup_depth_pct":   round(best_cup["depth"], 1),
            "cup_left_high":   round(best_cup["left_high"], 2),
            "cup_bottom":      round(best_cup["bottom"], 2),
            "cup_recovery":    round(best_cup["recovery"] * 100, 1),
            "cup_rounded":     best_cup["is_rounded"],
            # Handle metrics
            "handle_depth_pct": round(handle_depth, 1),
            "handle_valid":     handle_valid,
            "vol_dry_ratio":    round(vol_dry, 2),
            "pivot":            round(pivot, 2),
            "pct_from_pivot":   round(pct_from_pivot, 1),
            "vol_ratio":        round(vol_ratio, 2),
            # Levels
            "entry":      entry,
            "stop_price": stop,
            "target_1":   t1,
            "target_2":   t2,
            "target_3":   t3,
            "atr":        round(atr_val, 4),
            "description": (
                f"{best_cup['weeks']}wk cup · {best_cup['depth']:.0f}% depth · "
                f"{'rounded' if best_cup['is_rounded'] else 'V-shape'} · "
                f"{handle_depth:.0f}% handle"
            ),
        }

    except Exception as e:
        print(f"[patterns] CUP {ticker}: {e}")
        return None


# ── 4. Ascending Triangle ─────────────────────────────────────────────────────

def detect_ascending_triangle(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> Optional[dict]:
    """
    Ascending Triangle detector.

    Flat resistance: recent highs cluster within 2% of each other
    Rising lows:    successive lows forming an upward slope
    Volume:         declining as price coils toward apex
    Entry:          break above flat resistance on volume
    """
    try:
        if df is None or len(df) < 30:
            return None
        if rs_rank < 65:
            return None

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"]

        price     = float(closes.iloc[-1])
        avg_vol20 = _avg_vol(volumes, 20)
        if not avg_vol20:
            return None

        # ── Look at last 15-40 days ───────────────────────────────────────
        for lookback in [20, 30, 40]:
            if lookback > len(closes) - 2:
                continue

            w_highs  = highs.iloc[-lookback:]
            w_lows   = lows.iloc[-lookback:]
            w_vols   = volumes.iloc[-lookback:]
            w_closes = closes.iloc[-lookback:]

            # ── Flat resistance ───────────────────────────────────────────
            # Find the max high and check that recent highs cluster near it
            resistance = float(w_highs.max())
            # How many bars touched within 2% of resistance?
            touches = sum(1 for h in w_highs if h >= resistance * 0.98)
            if touches < 2:
                continue

            # ── Rising lows ───────────────────────────────────────────────
            low_slope = _linreg_slope(w_lows)
            if low_slope <= 0:
                continue  # lows must be rising

            # Fit line through lows — check it's genuinely ascending
            low_coeffs = _fit_trendline(w_lows)
            low_at_start = np.polyval(low_coeffs, 0)
            low_at_end   = np.polyval(low_coeffs, lookback - 1)
            low_rise_pct = (low_at_end - low_at_start) / low_at_start * 100

            if low_rise_pct < 2:  # lows must rise at least 2% over the period
                continue

            # ── Volume declining ──────────────────────────────────────────
            vol_slope = _linreg_slope(w_vols)
            vol_declining = vol_slope < 0

            # ── Coil tightness — price near apex ─────────────────────────
            current_support = float(np.polyval(low_coeffs, lookback - 1))
            range_pct = (resistance - current_support) / resistance * 100

            # Good triangle has range tightening to < 8%
            if range_pct > 15:
                continue

            # ── Stage ─────────────────────────────────────────────────────
            today_vol = float(volumes.iloc[-1])
            vol_ratio = today_vol / avg_vol20
            breaking  = price >= resistance * 0.998 and vol_ratio >= 1.4

            stage = "breaking_out" if breaking else "coiling" if range_pct < 5 else "forming"

            # ── Levels ───────────────────────────────────────────────────
            atr_val    = _atr(df) or price * 0.02
            entry      = round(resistance * 1.002, 2)
            stop       = round(current_support * 0.99, 2)
            tri_height = resistance - float(w_lows.iloc[0])  # measure of triangle height
            t1 = round(entry + tri_height * 0.5, 2)
            t2 = round(entry + tri_height * 0.8, 2)
            t3 = round(entry + tri_height, 2)

            # ── Score ─────────────────────────────────────────────────────
            score = 5.0
            if touches >= 3:          score += 1.0
            elif touches >= 2:        score += 0.5
            if low_rise_pct >= 5:     score += 1.0
            elif low_rise_pct >= 3:   score += 0.5
            if vol_declining:         score += 1.0
            if range_pct <= 5:        score += 1.0  # very tight coil
            elif range_pct <= 8:      score += 0.5
            if vcs and vcs <= 4:      score += 0.5
            if rs_rank >= 85:         score += 0.5
            if breaking:              score += 1.0

            chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)

            return {
                "ticker":       ticker,
                "pattern_type": "ASC_TRIANGLE",
                "stage":        stage,
                "price":        round(price, 2),
                "chg":          chg,
                "rs":           rs_rank,
                "vcs":          vcs,
                "signal_score": _score_clamp(score),
                # Triangle metrics
                "resistance":       round(resistance, 2),
                "support_now":      round(current_support, 2),
                "range_pct":        round(range_pct, 1),
                "touches":          touches,
                "low_rise_pct":     round(low_rise_pct, 1),
                "vol_declining":    vol_declining,
                "lookback_days":    lookback,
                "vol_ratio":        round(vol_ratio, 2),
                # Levels
                "entry":      entry,
                "stop_price": stop,
                "target_1":   t1,
                "target_2":   t2,
                "target_3":   t3,
                "atr":        round(atr_val, 4),
                "description": (
                    f"{touches} resistance touches · "
                    f"lows +{low_rise_pct:.1f}% · "
                    f"{range_pct:.1f}% range · "
                    f"{'vol declining' if vol_declining else 'vol mixed'}"
                ),
            }

        return None

    except Exception as e:
        print(f"[patterns] TRI {ticker}: {e}")
        return None


# ── Master scanner ────────────────────────────────────────────────────────────

def scan_all_patterns(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> list[dict]:
    """
    Run all four detectors and return any that trigger.
    A stock can match multiple patterns (e.g. VCP + Flag).
    """
    results = []
    for fn in [detect_flag, detect_vcp, detect_cup_handle, detect_ascending_triangle]:
        try:
            r = fn(ticker, df, rs_rank, vcs)
            if r:
                results.append(r)
        except Exception as e:
            print(f"[patterns] {fn.__name__} {ticker}: {e}")
    return results
