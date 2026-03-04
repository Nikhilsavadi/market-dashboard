"""
breakout.py
-----------
Two distinct signals:

1. CUP & HANDLE (actionable)
   - Stock made a high, pulled back to form a cup (15-50% depth)
   - Now in a handle: tight consolidation 2-8% below the cup high
   - Handle duration: 5-20 bars, volume contracting
   - Entry: just above handle high
   - Stop: just below handle low
   - RS >= 80, VCS <= 6

2. EXTENDED BREAKOUT WATCHLIST (watch only)
   - Already broke to 52w high on volume — currently extended
   - Watch for retrace to MA10/21 for second entry
   - Flagged as approaching_ma10/ma21 when price gets close
"""

import pandas as pd
import numpy as np
from typing import Optional


def _calc_atr(df: pd.DataFrame, periods: int = 14) -> float:
    try:
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"]  - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        return float(tr.iloc[-periods:].mean())
    except Exception:
        return float(df["close"].iloc[-1]) * 0.02


def _vol_contracting(volumes: pd.Series, handle_days: int) -> bool:
    """True if avg vol in last 5 days < avg vol in prior 5 days."""
    if len(volumes) < 10:
        return False
    recent_5 = float(volumes.iloc[-5:].mean())
    prior_5  = float(volumes.iloc[-10:-5].mean())
    return prior_5 > 0 and recent_5 < prior_5 * 0.9


def _find_cup(closes: pd.Series):
    """
    Find the most recent cup pattern in the last 6 months.
    Left lip: recent swing high (not in last 10 bars)
    Cup bottom: 15-50% pullback from left lip
    Right lip: current price recovering to within 2-12% of left lip
    Returns dict or None.
    """
    if len(closes) < 40:
        return None

    lookback = closes.iloc[-126:] if len(closes) >= 126 else closes
    n        = len(lookback)
    vals     = lookback.values

    # Left lip: highest point, excluding last 10 bars
    search_vals    = vals[:-10]
    if len(search_vals) < 15:
        return None
    left_lip_pos   = int(np.argmax(search_vals))
    left_lip_val   = float(search_vals[left_lip_pos])

    if left_lip_pos < 5:
        return None

    # Cup bottom: lowest point after left lip
    after_left_vals = vals[left_lip_pos:]
    if len(after_left_vals) < 10:
        return None
    bottom_offset   = int(np.argmin(after_left_vals))
    cup_bottom_val  = float(after_left_vals[bottom_offset])
    cup_bottom_pos  = left_lip_pos + bottom_offset

    # Cup depth: 15-50%
    cup_depth_pct = (left_lip_val - cup_bottom_val) / left_lip_val * 100
    if cup_depth_pct < 15 or cup_depth_pct > 50:
        return None

    # Right lip: current price within 2-12% of left lip
    right_lip_val  = float(vals[-1])
    dist_from_left = (left_lip_val - right_lip_val) / left_lip_val * 100
    if dist_from_left < 2 or dist_from_left > 12:
        return None

    # Handle bars: approximate from when price crossed 75% of recovery
    recovery_level = cup_bottom_val + (left_lip_val - cup_bottom_val) * 0.75
    after_bottom   = vals[cup_bottom_pos:]
    handle_start   = 0
    for i, v in enumerate(after_bottom):
        if v >= recovery_level:
            handle_start = i
            break
    handle_bars = len(after_bottom) - handle_start
    if handle_bars < 3 or handle_bars > 25:
        return None

    recovery_range = left_lip_val - cup_bottom_val
    recovery_pct   = round((right_lip_val - cup_bottom_val) / recovery_range * 100, 1) if recovery_range else 0

    return {
        "left_lip":       round(left_lip_val, 2),
        "cup_bottom":     round(cup_bottom_val, 2),
        "cup_depth_pct":  round(cup_depth_pct, 1),
        "dist_from_left": round(dist_from_left, 2),
        "handle_bars":    handle_bars,
        "recovery_pct":   recovery_pct,
    }


def detect_cup_and_handle(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
) -> Optional[dict]:
    """Detect cup and handle setup. Returns signal dict or None."""
    try:
        if df is None or len(df) < 60:
            return None

        closes  = df["close"]
        volumes = df["volume"]
        price   = float(closes.iloc[-1])

        if rs_rank < 80:
            return None
        if vcs and vcs > 6:
            return None

        avg_vol_20 = float(volumes.iloc[-21:-1].mean()) if len(volumes) >= 21 else None
        if not avg_vol_20 or avg_vol_20 == 0:
            return None

        vol_today = float(volumes.iloc[-1])
        vol_ratio = round(vol_today / avg_vol_20, 2)

        cup = _find_cup(closes)
        if not cup:
            return None

        left_lip      = cup["left_lip"]
        cup_bottom    = cup["cup_bottom"]
        dist_from_lip = cup["dist_from_left"]
        handle_bars   = cup["handle_bars"]
        cup_depth     = cup["cup_depth_pct"]

        # Handle tightness
        handle_window = closes.iloc[-handle_bars:] if handle_bars <= len(closes) else closes
        handle_high   = float(handle_window.max())
        handle_low    = float(handle_window.min())
        handle_range  = (handle_high - handle_low) / handle_low * 100 if handle_low > 0 else 99

        if handle_range > 8:
            return None

        vol_contracting = _vol_contracting(volumes, handle_bars)

        # Entry, stop, targets
        atr         = _calc_atr(df)
        entry_pivot = round(handle_high * 1.005, 2)
        stop        = round(handle_low  * 0.99,  2)
        risk        = max(entry_pivot - stop, atr * 0.5)
        t1          = round(entry_pivot + 1.5 * risk, 2)
        t2          = round(entry_pivot + 3.0 * risk, 2)
        t3          = round(entry_pivot + 5.0 * risk, 2)

        chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)

        # Score 1-10
        score = 5.0
        if rs_rank >= 95:          score += 2.0
        elif rs_rank >= 90:        score += 1.5
        elif rs_rank >= 85:        score += 1.0
        if vcs and vcs <= 3:       score += 1.5
        elif vcs and vcs <= 5:     score += 1.0
        if vol_contracting:        score += 1.0
        if handle_range < 4:       score += 0.5
        if 5 <= handle_bars <= 15: score += 0.5
        if cup_depth >= 20:        score += 0.5
        if dist_from_lip <= 5:     score += 0.5
        score = round(min(10.0, score), 1)

        if handle_range < 4 and vol_contracting and vcs and vcs <= 4:
            quality = "ideal"
        elif handle_range < 6 and vol_contracting:
            quality = "good"
        else:
            quality = "developing"

        return {
            "ticker":           ticker,
            "signal_type":      "CUP_HANDLE",
            "price":            round(price, 2),
            "chg":              chg,
            "entry_pivot":      entry_pivot,
            "stop_price":       stop,
            "target_1":         t1,
            "target_2":         t2,
            "target_3":         t3,
            "left_lip":         left_lip,
            "cup_bottom":       cup_bottom,
            "cup_depth_pct":    cup_depth,
            "dist_from_pivot":  round(dist_from_lip, 2),
            "handle_bars":      handle_bars,
            "handle_range_pct": round(handle_range, 1),
            "vol_contracting":  vol_contracting,
            "vol_ratio":        vol_ratio,
            "avg_vol_20":       int(avg_vol_20),
            "rs":               rs_rank,
            "vcs":              vcs,
            "atr":              round(atr, 4),
            "signal_score":     score,
            "cup_quality":      quality,
            "recovery_pct":     cup.get("recovery_pct"),
        }

    except Exception as e:
        print(f"[breakout] Cup/Handle error {ticker}: {e}")
        return None


def detect_extended_breakout(
    ticker: str,
    df: pd.DataFrame,
    rs_rank: int,
    vcs: Optional[float],
    ma10: Optional[float],
    ma21: Optional[float],
) -> Optional[dict]:
    """
    Detect stocks that already broke out to 52w highs and are extended.
    Watchlist only — second entry when they retrace to MA10/21.
    """
    try:
        if df is None or len(df) < 60:
            return None

        closes  = df["close"]
        volumes = df["volume"]
        price   = float(closes.iloc[-1])

        if rs_rank < 75:
            return None

        avg_vol_20 = float(volumes.iloc[-21:-1].mean()) if len(volumes) >= 21 else None
        if not avg_vol_20 or avg_vol_20 == 0:
            return None

        # Must be near or at 52w high
        prior_252 = closes.iloc[-253:-1] if len(closes) >= 253 else closes.iloc[:-1]
        high_52w  = float(prior_252.max())
        dist_high = (price - high_52w) / high_52w * 100

        if dist_high < -1 or dist_high > 25:
            return None

        # Recent vol surge (last 5 days) confirms the breakout happened
        recent_vols = volumes.iloc[-6:-1]
        vol_surge   = round(float(recent_vols.max()) / avg_vol_20, 2)
        if vol_surge < 1.3:
            return None

        # Distance from MAs
        pct_from_ma10 = round((price - ma10) / ma10 * 100, 1) if ma10 else None
        pct_from_ma21 = round((price - ma21) / ma21 * 100, 1) if ma21 else None

        # Watch status — drives urgency in UI
        if pct_from_ma10 is not None and 0 < pct_from_ma10 <= 5:
            watch_status = "approaching_ma10"
        elif pct_from_ma21 is not None and 0 < pct_from_ma21 <= 8:
            watch_status = "approaching_ma21"
        elif pct_from_ma10 is not None and 5 < pct_from_ma10 <= 15:
            watch_status = "extended_ma10"
        else:
            watch_status = "extended"

        chg = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2)
        atr = _calc_atr(df)

        return {
            "ticker":         ticker,
            "signal_type":    "EXTENDED_BO",
            "price":          round(price, 2),
            "chg":            chg,
            "high_52w":       round(high_52w, 2),
            "dist_from_high": round(dist_high, 2),
            "pct_from_ma10":  pct_from_ma10,
            "pct_from_ma21":  pct_from_ma21,
            "ma10":           round(ma10, 2) if ma10 else None,
            "ma21":           round(ma21, 2) if ma21 else None,
            "ma10_entry":     round(ma10 * 1.005, 2) if ma10 else None,
            "ma21_entry":     round(ma21 * 1.005, 2) if ma21 else None,
            "vol_surge":      vol_surge,
            "rs":             rs_rank,
            "vcs":            vcs,
            "atr":            round(atr, 4),
            "watch_status":   watch_status,
        }

    except Exception as e:
        print(f"[breakout] Extended BO error {ticker}: {e}")
        return None


# ── Weekly Breakout Retest ─────────────────────────────────────────────────────
def detect_weekly_breakout_retest(
    ticker: str,
    weekly_df: pd.DataFrame,
    rs_rank: float = 50,
    vcs: float = None,
) -> Optional[dict]:
    """
    Detect the AMAT-style weekly breakout→retest setup:

    1. RESISTANCE LEVEL: Price broke above a level that held for >= 8 weeks
       (resistance = highest weekly close in a 8-52w lookback, excluding last 6 weeks)
    2. BREAKOUT: A clean break above resistance — close > resistance by >= 1%,
       on volume >= 1.2x the 10w average
    3. RETEST: Price pulled back to within ±5% of the resistance level (now support)
       in the 3-12 weeks after the breakout
    4. RETEST QUALITY:
       - Tight weekly candles during retest (avg weekly range < 6% of price)
       - Volume contracted during retest (< 0.85x breakout volume)
       - Weekly MAs still stacked (EMA10 > SMA21 > SMA50 or 2 of 3)
       - Price held above the resistance-turned-support
    5. CURRENT: Now reclaiming / bouncing — last weekly close back above resistance
       or within 2% above it (ready to launch)
    """
    try:
        if weekly_df is None or len(weekly_df) < 40:
            return None

        df = weekly_df.copy()
        df.columns = [c.lower() for c in df.columns]
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            return None

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"]
        n       = len(df)
        price   = float(closes.iloc[-1])

        # ── Step 1: Find resistance level ─────────────────────────────────────
        # Look back 8-52 weeks, exclude last 6 weeks (the breakout / retest zone)
        lookback_start = max(0, n - 52)
        lookback_end   = max(0, n - 6)

        if lookback_end - lookback_start < 8:
            return None

        resistance_window = closes.iloc[lookback_start:lookback_end]
        resistance = float(resistance_window.max())

        # Resistance must be meaningful — price was "stuck" below it
        # Check it was tested at least twice (price came within 2% at least 2 times)
        touches = int(((resistance_window >= resistance * 0.98) & (resistance_window <= resistance * 1.02)).sum())
        if touches < 2:
            return None

        # ── Step 2: Find the breakout week ───────────────────────────────────
        # Scan the last 3-16 weeks for a close that broke above resistance on volume
        search_start = max(0, n - 16)
        search_end   = n - 1  # not the very last bar (that's the retest or launch)

        breakout_week = None
        breakout_close = None
        breakout_vol   = None
        avg_vol_pre_bo = float(volumes.iloc[search_start - 10 : search_start].mean()) if search_start >= 10 else float(volumes.iloc[:search_start].mean())

        for i in range(search_start, search_end):
            c = float(closes.iloc[i])
            v = float(volumes.iloc[i])
            prev_close = float(closes.iloc[i - 1]) if i > 0 else resistance
            # Break: closed above resistance by >=1%, coming from below
            if c > resistance * 1.01 and prev_close < resistance * 1.03:
                # Volume surge on the breakout week >= 1.2x recent avg
                vol_ratio = v / avg_vol_pre_bo if avg_vol_pre_bo > 0 else 1
                if vol_ratio >= 1.1:
                    breakout_week  = i
                    breakout_close = c
                    breakout_vol   = v
                    break  # take first (earliest) breakout

        if breakout_week is None:
            return None

        # ── Step 3: Retest zone (weeks after breakout) ────────────────────────
        retest_bars = df.iloc[breakout_week + 1:]
        if len(retest_bars) < 2:
            return None

        # Price must have touched back within ±5% of resistance after the breakout
        rt_lows   = retest_bars["low"]
        rt_closes = retest_bars["close"]

        # Did any retest candle come within 5% of resistance from above?
        retest_low    = float(rt_lows.min())
        retest_min_close = float(rt_closes.min())
        pct_to_resist = (retest_min_close - resistance) / resistance * 100

        retest_touched = (retest_low <= resistance * 1.05) and (retest_min_close >= resistance * 0.97)
        if not retest_touched:
            return None

        # ── Step 4: Retest quality ────────────────────────────────────────────
        rt_highs   = retest_bars["high"].values
        rt_lo      = retest_bars["low"].values
        rt_cl      = retest_bars["close"].values
        rt_vol     = retest_bars["volume"].values
        n_rt       = len(retest_bars)

        # Weekly candle tightness during retest
        weekly_ranges = [(rt_highs[i] - rt_lo[i]) / rt_cl[i] * 100 for i in range(n_rt)]
        avg_range_pct = float(np.mean(weekly_ranges)) if weekly_ranges else 10

        # Volume contraction vs breakout week
        avg_rt_vol = float(np.mean(rt_vol)) if len(rt_vol) > 0 else breakout_vol
        vol_contraction = avg_rt_vol / breakout_vol if breakout_vol > 0 else 1.0

        # MAs at current point
        ma_vals = {}
        for period, label in [(10, "ema10"), (21, "sma21"), (50, "sma50")]:
            if len(closes) >= period:
                if "ema" in label:
                    ma_vals[label] = float(closes.ewm(span=period, adjust=False).mean().iloc[-1])
                else:
                    ma_vals[label] = float(closes.rolling(period).mean().iloc[-1])

        ema10 = ma_vals.get("ema10", 0)
        sma21 = ma_vals.get("sma21", 0)
        sma50 = ma_vals.get("sma50", 0)

        # MA stack score (0-3)
        ma_stack = int(ema10 > sma21) + int(sma21 > sma50) + int(price > ema10)

        # ── Step 5: Current position — launching or retesting ─────────────────
        last_close  = price
        prev_close  = float(closes.iloc[-2]) if n >= 2 else price
        chg_pct     = round((last_close - prev_close) / prev_close * 100, 2)

        pct_from_resistance = round((last_close - resistance) / resistance * 100, 2)

        # Stage classification
        if last_close > resistance * 1.03:
            stage = "launched"          # already moving up after retest
        elif last_close >= resistance * 0.99:
            stage = "retesting"         # sitting right on the level — prime entry
        elif last_close >= resistance * 0.96:
            stage = "near_support"      # slightly below, still viable
        else:
            stage = "broke_support"     # gave back too much

        if stage == "broke_support":
            return None

        # ── Score (0-10) ──────────────────────────────────────────────────────
        score = 5.0
        if vol_contraction < 0.7:   score += 1.0   # tight vol retest
        elif vol_contraction < 0.85: score += 0.5
        if avg_range_pct < 4:       score += 1.0   # very tight candles
        elif avg_range_pct < 6:     score += 0.5
        if ma_stack >= 3:           score += 1.0
        elif ma_stack == 2:         score += 0.5
        if rs_rank >= 90:           score += 1.0
        elif rs_rank >= 80:         score += 0.5
        if vcs is not None and vcs <= 3:  score += 0.5
        if stage == "retesting":    score += 0.5   # sitting right on level
        score = round(min(10, score), 1)

        # Targets
        # T1: 2x the resistance level height above breakout
        # T2/T3: extensions
        range_to_resistance = resistance - float(closes.iloc[lookback_start:lookback_end].min())
        t1 = round(resistance + range_to_resistance * 1.0, 2)
        t2 = round(resistance + range_to_resistance * 1.618, 2)
        t3 = round(resistance + range_to_resistance * 2.618, 2)

        # Stop: just below resistance (structure stop)
        stop = round(resistance * 0.97, 2)

        atr = _calc_atr(df) if len(df) >= 14 else price * 0.02

        return {
            "ticker":             ticker,
            "signal_type":        "WEEKLY_BO_RETEST",
            "price":              round(price, 2),
            "chg":                chg_pct,
            "resistance":         round(resistance, 2),
            "pct_from_resistance": pct_from_resistance,
            "breakout_close":     round(breakout_close, 2),
            "weeks_since_bo":     n - breakout_week,
            "retest_low":         round(retest_low, 2),
            "retest_candles":     n_rt,
            "avg_range_pct":      round(avg_range_pct, 2),
            "vol_contraction":    round(vol_contraction, 2),
            "ma_stack":           ma_stack,
            "ema10_w":            round(ema10, 2) if ema10 else None,
            "sma21_w":            round(sma21, 2) if sma21 else None,
            "sma50_w":            round(sma50, 2) if sma50 else None,
            "stage":              stage,
            "rs":                 rs_rank,
            "vcs":                vcs,
            "signal_score":       score,
            "entry":              round(resistance * 1.005, 2),   # just above resistance
            "stop_price":         stop,
            "target_1":           t1,
            "target_2":           t2,
            "target_3":           t3,
            "resistance_touches": touches,
            "atr":                round(atr, 3),
        }

    except Exception as e:
        print(f"[breakout] Weekly retest error {ticker}: {e}")
        return None
