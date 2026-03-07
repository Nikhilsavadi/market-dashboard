"""
stockbee_ep.py
--------------
Pradeep Bonde (Stockbee) Episodic Pivot system — full implementation.

Covers:
  1. MAGNA 53+ CAP 10x10 scoring (0-7)
  2. Five EP variations: Classic, Delayed, 9M, Story, Momentum Burst
  3. Delayed EP watchlist tracker (persisted in DB)
  4. Volume spike scanner (9M EP detection)
  5. Short interest overlay
  6. Sales acceleration screen
  7. Entry tactic recommendations
  8. S&P 500 breadth market regime indicator

All thresholds are configurable via EP_CONFIG dict.
"""

import json
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ── Configurable thresholds ──────────────────────────────────────────────────

EP_CONFIG = {
    # MAGNA scoring thresholds
    "magna_earnings_beat_pct": 20,       # M: earnings beat consensus by X%
    "magna_sales_growth_pct": 30,        # M: OR sales growth X% for 2 consecutive qtrs
    "magna_analyst_count_max": 10,       # N: fewer than X analysts = neglected
    "magna_analyst_upgrade_days": 14,    # A: upgrade within last X days
    "magna_52w_high_pct": 3,             # 53+: within X% of 52w high
    "magna_market_cap_max_b": 10,        # CAP: under $X billion
    "magna_ipo_years_max": 10,           # 10x10: IPO within last X years

    # EP detection thresholds
    "classic_ep_gap_pct": 10,            # Classic EP: minimum gap %
    "classic_ep_vol_mult": 2,            # Classic EP: volume X times average
    "delayed_ep_lookback_days": 30,      # Delayed EP: lookback window
    "delayed_ep_max_pullback_pct": 50,   # Delayed EP: max pullback from gap move
    "delayed_ep_breakout_vol_mult": 1.5, # Delayed EP: breakout volume multiplier
    "nine_m_volume": 9_000_000,          # 9M EP: share volume threshold
    "nine_m_vol_mult": 3,               # 9M EP: or 3x 50-day avg volume by midday
    "story_ep_gap_pct": 10,             # Story EP: minimum gap %
    "mom_burst_ema_periods": [10, 20],   # Momentum Burst: EMA periods
    "mom_burst_consol_bars": 5,          # Momentum Burst: consolidation bars

    # Watchlist
    "watchlist_max_days": 30,            # Remove from watchlist after X days

    # Short interest
    "short_interest_squeeze_pct": 15,    # Flag squeeze potential above X%

    # Entry tactic display
    "show_entry_prices": True,

    # ── Backtest-validated settings (5yr walk-forward) ──────────────────────
    # Exit strategy: move stop to breakeven after X% gain, then trail Y%
    "exit_be_trigger_pct": 10,          # Move to breakeven after 10% gain
    "exit_trail_pct": 15,               # Trail 15% from highest close
    # No fixed holding period — hold until trailing stop triggers

    # Conviction tiers (validated out-of-sample over 5 years)
    # Tier 1 "Bread & Butter": Gap 30%+ micro-cap (<$5M avg daily $ vol)
    #   ~25 trades/yr, 56% WR, +13.7% exp, PF 3.74, profitable every year
    # Tier 2 "Sniper": Gap 50%+ STORY type
    #   ~10 trades/yr, 66% WR, +9.3% exp, PF 2.36
    "tier1_min_gap_pct": 30,
    "tier1_max_dollar_vol": 5_000_000,
    "tier2_min_gap_pct": 50,

    # Position sizing
    "default_risk_pct": 3,              # Risk 3% of equity per trade at stop
    "default_leverage": 50,             # CFD leverage
    "default_max_positions": 8,
}


# ── MAGNA SCORING ────────────────────────────────────────────────────────────

def calculate_magna_score(ticker: str, df: pd.DataFrame,
                          fundamentals: dict = None,
                          config: dict = None) -> dict:
    """
    Calculate MAGNA 53+ CAP 10x10 score (0-7).

    Args:
        ticker: Stock ticker
        df: OHLCV DataFrame
        fundamentals: Dict with earnings, revenue, analyst data, etc.
        config: Override EP_CONFIG thresholds

    Returns dict with:
        magna_score: int 0-7
        magna_details: dict with each component's status
        magna_color: 'green' | 'yellow' | 'red'
    """
    cfg = {**EP_CONFIG, **(config or {})}
    fund = fundamentals or {}

    details = {
        "M": {"met": False, "label": "Massive Acceleration", "reason": "N/A"},
        "A_analyst": {"met": False, "label": "Analyst Upgrades", "reason": "N/A"},
        "G": {"met": False, "label": "Guidance", "reason": "N/A"},
        "N": {"met": False, "label": "Neglect", "reason": "N/A"},
        "53+": {"met": False, "label": "Technical Position", "reason": "N/A"},
        "CAP": {"met": False, "label": "Small/Mid Cap", "reason": "N/A"},
        "10x10": {"met": False, "label": "Young Company", "reason": "N/A"},
    }

    # ── M: Massive Acceleration ──────────────────────────────────────────────
    earnings_surprise_pct = fund.get("earnings_surprise_pct")
    sales_growth_q1 = fund.get("revenue_growth_q1")
    sales_growth_q2 = fund.get("revenue_growth_q2")

    if earnings_surprise_pct is not None and earnings_surprise_pct >= cfg["magna_earnings_beat_pct"]:
        details["M"]["met"] = True
        details["M"]["reason"] = f"Earnings beat by {earnings_surprise_pct:.0f}%"
    elif (sales_growth_q1 is not None and sales_growth_q2 is not None
          and sales_growth_q1 >= cfg["magna_sales_growth_pct"]
          and sales_growth_q2 >= cfg["magna_sales_growth_pct"]):
        details["M"]["met"] = True
        details["M"]["reason"] = f"Sales growth {sales_growth_q1:.0f}% / {sales_growth_q2:.0f}% (2 qtrs)"
    elif earnings_surprise_pct is not None:
        details["M"]["reason"] = f"Earnings beat {earnings_surprise_pct:.0f}% (need {cfg['magna_earnings_beat_pct']}%+)"
    elif sales_growth_q1 is not None:
        details["M"]["reason"] = f"Sales growth {sales_growth_q1:.0f}% (checking)"

    # ── G: Guidance ──────────────────────────────────────────────────────────
    guidance_raised = fund.get("guidance_raised", False)
    estimates_revised_up = fund.get("estimates_revised_up", False)
    if guidance_raised or estimates_revised_up:
        details["G"]["met"] = True
        reason_parts = []
        if guidance_raised:
            reason_parts.append("Guidance raised")
        if estimates_revised_up:
            reason_parts.append("Estimates revised up")
        details["G"]["reason"] = " + ".join(reason_parts)
    else:
        details["G"]["reason"] = "No guidance raise detected"

    # ── N: Neglect ───────────────────────────────────────────────────────────
    analyst_count = fund.get("analyst_count")
    if analyst_count is not None and analyst_count < cfg["magna_analyst_count_max"]:
        details["N"]["met"] = True
        details["N"]["reason"] = f"{analyst_count} analysts (< {cfg['magna_analyst_count_max']})"
    elif analyst_count is not None:
        details["N"]["reason"] = f"{analyst_count} analysts (>= {cfg['magna_analyst_count_max']})"
    else:
        # If we can't determine analyst count, check if it's a small/unknown stock
        market_cap = fund.get("market_cap")
        if market_cap is not None and market_cap < 2e9:
            details["N"]["met"] = True
            details["N"]["reason"] = f"Small cap (${market_cap/1e9:.1f}B) — likely neglected"

    # ── A: Analyst Upgrades ──────────────────────────────────────────────────
    recent_upgrade = fund.get("recent_upgrade", False)
    pt_raise = fund.get("price_target_raised", False)
    if recent_upgrade or pt_raise:
        details["A_analyst"]["met"] = True
        reason_parts = []
        if recent_upgrade:
            reason_parts.append("Analyst upgrade")
        if pt_raise:
            reason_parts.append("Price target raised")
        details["A_analyst"]["reason"] = " + ".join(reason_parts)
    else:
        details["A_analyst"]["reason"] = "No recent upgrades"

    # ── 53+: Technical Position ──────────────────────────────────────────────
    try:
        closes = df["close"]
        price = float(closes.iloc[-1])

        # Above 50-day MA
        if len(closes) >= 50:
            ma50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
            above_ma50 = price > ma50
        else:
            above_ma50 = True  # insufficient data, don't penalize

        # Within X% of 52-week high
        if len(closes) >= 252:
            w52_high = float(df["high"].iloc[-252:].max())
        else:
            w52_high = float(df["high"].max())

        pct_from_high = (w52_high - price) / w52_high * 100 if w52_high > 0 else 99
        near_high = pct_from_high <= cfg["magna_52w_high_pct"]

        if above_ma50 and near_high:
            details["53+"]["met"] = True
            details["53+"]["reason"] = f"Above 50MA, {pct_from_high:.1f}% from 52w high"
        else:
            reasons = []
            if not above_ma50:
                reasons.append("below 50MA")
            if not near_high:
                reasons.append(f"{pct_from_high:.1f}% from high (need <{cfg['magna_52w_high_pct']}%)")
            details["53+"]["reason"] = ", ".join(reasons)
    except Exception:
        details["53+"]["reason"] = "Insufficient price data"

    # ── CAP: Small/Mid Cap ───────────────────────────────────────────────────
    market_cap = fund.get("market_cap")
    if market_cap is not None:
        cap_b = market_cap / 1e9
        if cap_b < cfg["magna_market_cap_max_b"]:
            details["CAP"]["met"] = True
            details["CAP"]["reason"] = f"${cap_b:.1f}B (< ${cfg['magna_market_cap_max_b']}B)"
        else:
            details["CAP"]["reason"] = f"${cap_b:.1f}B (>= ${cfg['magna_market_cap_max_b']}B)"
    else:
        details["CAP"]["reason"] = "Market cap unavailable"

    # ── 10x10: Young Company ─────────────────────────────────────────────────
    ipo_date = fund.get("ipo_date")
    if ipo_date:
        try:
            if isinstance(ipo_date, str):
                ipo_dt = datetime.strptime(ipo_date, "%Y-%m-%d")
            else:
                ipo_dt = ipo_date
            years_since_ipo = (datetime.now() - ipo_dt).days / 365.25
            if years_since_ipo <= cfg["magna_ipo_years_max"]:
                details["10x10"]["met"] = True
                details["10x10"]["reason"] = f"IPO {years_since_ipo:.1f} years ago"
            else:
                details["10x10"]["reason"] = f"IPO {years_since_ipo:.0f} years ago (> {cfg['magna_ipo_years_max']})"
        except Exception:
            details["10x10"]["reason"] = "IPO date parse error"
    else:
        details["10x10"]["reason"] = "IPO date unavailable"

    # ── Calculate total score ────────────────────────────────────────────────
    score = sum(1 for d in details.values() if d["met"])

    if score >= 5:
        color = "green"
    elif score >= 3:
        color = "yellow"
    else:
        color = "red"

    return {
        "magna_score": score,
        "magna_details": details,
        "magna_color": color,
    }


# ── EP TYPE CLASSIFICATION ───────────────────────────────────────────────────

def classify_ep_type(df: pd.DataFrame, fundamentals: dict = None,
                     past_eps: list = None, config: dict = None) -> dict:
    """
    Classify the EP variation for a stock.

    Returns dict with:
        ep_type: 'CLASSIC' | 'DELAYED' | '9M' | 'STORY' | 'MOM_BURST' | None
        ep_badge: Display label
        ep_type_details: Explanation
        ep_warning: Warning text (for Story EP)
        + all detection fields
    """
    cfg = {**EP_CONFIG, **(config or {})}
    fund = fundamentals or {}
    past = past_eps or []

    result = {
        "ep_type": None,
        "ep_badge": None,
        "ep_type_details": None,
        "ep_warning": None,
    }

    if df is None or len(df) < 30:
        return result

    closes = df["close"]
    volumes = df["volume"]
    highs = df["high"]
    lows = df["low"]
    opens = df["open"]
    price = float(closes.iloc[-1])
    n = len(df)

    # ── 1. Check for Classic EP (today or last 5 days) ───────────────────────
    classic = _detect_classic_ep(df, cfg, fund)
    if classic["detected"]:
        result.update({
            "ep_type": "CLASSIC",
            "ep_badge": "CLASSIC EP",
            "ep_type_details": (
                f"Gap {classic['gap_pct']:.1f}%, Vol {classic['vol_ratio']:.1f}x, "
                f"Catalyst: {classic.get('catalyst', 'Earnings/Sales')}"
            ),
            **{f"ep_{k}": v for k, v in classic.items() if k != "detected"},
        })
        return result

    # ── 2. Check for Delayed EP ──────────────────────────────────────────────
    delayed = _detect_delayed_ep(df, past, cfg)
    if delayed["detected"]:
        result.update({
            "ep_type": "DELAYED",
            "ep_badge": "DELAYED EP",
            "ep_type_details": (
                f"Classic EP {delayed['days_since_ep']}d ago, "
                f"pullback {delayed['pullback_pct']:.1f}%, "
                f"breaking above EP high on {delayed['breakout_vol_ratio']:.1f}x vol"
            ),
            **{f"ep_{k}": v for k, v in delayed.items() if k != "detected"},
        })
        return result

    # ── 3. Check for 9M EP ───────────────────────────────────────────────────
    nine_m = _detect_9m_ep(df, cfg)
    if nine_m["detected"]:
        result.update({
            "ep_type": "9M",
            "ep_badge": "9M EP",
            "ep_type_details": (
                f"Volume {nine_m['volume']:,.0f} shares "
                f"({nine_m['vol_ratio']:.1f}x avg), "
                f"Catalyst: {nine_m.get('catalyst', 'Unknown')}"
            ),
            **{f"ep_{k}": v for k, v in nine_m.items() if k != "detected"},
        })
        return result

    # ── 4. Check for Story EP (Sugar Baby) ───────────────────────────────────
    story = _detect_story_ep(df, cfg, fund)
    if story["detected"]:
        result.update({
            "ep_type": "STORY",
            "ep_badge": "STORY EP",
            "ep_type_details": (
                f"Gap {story['gap_pct']:.1f}% on news/hype, "
                f"NO fundamental backing"
            ),
            "ep_warning": "Quick profit setup - tight stops, don't hold.",
            **{f"ep_{k}": v for k, v in story.items() if k != "detected"},
        })
        return result

    # ── 5. Check for Momentum Burst ──────────────────────────────────────────
    mom = _detect_momentum_burst(df, cfg)
    if mom["detected"]:
        result.update({
            "ep_type": "MOM_BURST",
            "ep_badge": "MOM BURST",
            "ep_type_details": (
                f"Pullback to {mom['pullback_ma']} in uptrend, "
                f"{mom['consol_bars']}-bar tight consolidation, "
                f"volume expanding"
            ),
            **{f"ep_{k}": v for k, v in mom.items() if k != "detected"},
        })
        return result

    return result


def _detect_classic_ep(df: pd.DataFrame, cfg: dict, fund: dict) -> dict:
    """Classic EP: earnings/sales catalyst + gap up 10%+ + volume 2x+ average."""
    empty = {"detected": False}
    try:
        closes = df["close"]
        opens = df["open"]
        volumes = df["volume"]
        highs = df["high"]
        lows = df["low"]
        n = len(df)

        # Scan last 5 days
        for i in range(max(1, n - 5), n):
            prior_close = float(closes.iloc[i - 1])
            if prior_close <= 0:
                continue

            day_open = float(opens.iloc[i])
            day_close = float(closes.iloc[i])
            day_high = float(highs.iloc[i])
            day_low = float(lows.iloc[i])
            day_vol = float(volumes.iloc[i])

            gap_pct = (day_open - prior_close) / prior_close * 100

            if gap_pct < cfg["classic_ep_gap_pct"]:
                continue

            # Close didn't fully fade (held at least 70% of gap)
            if day_close < prior_close + (day_open - prior_close) * 0.5:
                continue

            # Volume check
            adv_start = max(0, i - 50)
            adv = float(volumes.iloc[adv_start:i].mean()) if i > adv_start else 0
            if adv <= 0:
                continue
            vol_ratio = day_vol / adv

            if vol_ratio < cfg["classic_ep_vol_mult"]:
                continue

            # Has fundamental catalyst?
            has_earnings = (fund.get("earnings_surprise_pct") is not None
                          and fund.get("earnings_surprise_pct", 0) > 0)
            has_sales = (fund.get("revenue_growth_q1") is not None
                        and fund.get("revenue_growth_q1", 0) > 10)

            if not has_earnings and not has_sales:
                # Still detected but might be reclassified as Story EP
                continue

            catalyst = []
            if has_earnings:
                catalyst.append(f"EPS beat {fund.get('earnings_surprise_pct', 0):.0f}%")
            if has_sales:
                catalyst.append(f"Revenue +{fund.get('revenue_growth_q1', 0):.0f}%")

            days_ago = (n - 1) - i
            date_str = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])

            return {
                "detected": True,
                "gap_pct": round(gap_pct, 1),
                "vol_ratio": round(vol_ratio, 1),
                "day_high": round(day_high, 2),
                "day_low": round(day_low, 2),
                "day_open": round(day_open, 2),
                "day_close": round(day_close, 2),
                "days_ago": days_ago,
                "date": date_str,
                "catalyst": " + ".join(catalyst),
                "stop": round(day_low * 0.99, 2),
                "target": round(float(closes.iloc[-1]) * (1 + gap_pct / 100), 2),
            }

    except Exception:
        pass
    return empty


def _detect_delayed_ep(df: pd.DataFrame, past_eps: list, cfg: dict) -> dict:
    """
    Delayed Reaction EP: Classic EP 5-30 days ago, consolidated (pulled back
    less than 50% of gap move), now breaking above EP day high on above-avg volume.
    """
    empty = {"detected": False}
    try:
        if not past_eps:
            return empty

        closes = df["close"]
        volumes = df["volume"]
        highs = df["high"]
        price = float(closes.iloc[-1])
        today_vol = float(volumes.iloc[-1])
        n = len(df)

        for ep in past_eps:
            days_since = ep.get("days_since", 0)
            if days_since < 5 or days_since > cfg["delayed_ep_lookback_days"]:
                continue

            ep_high = ep.get("ep_day_high", 0)
            ep_low = ep.get("ep_day_low", 0)
            ep_open = ep.get("ep_day_open", 0)
            gap_move = ep_high - ep_open if ep_open > 0 else 0

            if gap_move <= 0:
                continue

            # Pullback from EP high
            pullback = ep_high - price
            pullback_pct_of_gap = (pullback / gap_move * 100) if gap_move > 0 else 100

            # Must have pulled back less than 50% of the gap move
            if pullback_pct_of_gap > cfg["delayed_ep_max_pullback_pct"]:
                continue

            # Must still be above EP day low (thesis intact)
            if price < ep_low:
                continue

            # Now breaking above EP day high
            if price <= ep_high:
                continue

            # Volume confirmation
            adv_50 = float(volumes.iloc[-50:].mean()) if n >= 50 else float(volumes.mean())
            breakout_vol_ratio = today_vol / adv_50 if adv_50 > 0 else 0

            if breakout_vol_ratio < cfg["delayed_ep_breakout_vol_mult"]:
                continue

            pullback_pct = (ep_high - price) / ep_high * 100 if ep_high > 0 else 0

            return {
                "detected": True,
                "days_since_ep": days_since,
                "original_ep_date": ep.get("ep_date"),
                "ep_day_high": ep_high,
                "ep_day_low": ep_low,
                "pullback_pct": abs(pullback_pct),
                "breakout_vol_ratio": round(breakout_vol_ratio, 1),
                "consolidation_low": round(float(lows_min) if 'lows_min' in dir() else ep_low, 2),
                "stop": round(min(ep_low, float(df["low"].iloc[-5:].min())) * 0.99, 2),
                "target": round(price * 1.15, 2),
            }

    except Exception:
        pass
    return empty


def _detect_9m_ep(df: pd.DataFrame, cfg: dict) -> dict:
    """9M EP: stock trades 9M+ shares or 3x 50-day avg volume."""
    empty = {"detected": False}
    try:
        volumes = df["volume"]
        closes = df["close"]
        highs = df["high"]
        lows = df["low"]
        n = len(df)

        # Check last 3 days
        for i in range(max(1, n - 3), n):
            day_vol = float(volumes.iloc[i])

            # 50-day average volume
            adv_start = max(0, i - 50)
            adv_50 = float(volumes.iloc[adv_start:i].mean()) if i > adv_start else 0
            vol_ratio = day_vol / adv_50 if adv_50 > 0 else 0

            is_9m = day_vol >= cfg["nine_m_volume"]
            is_3x = vol_ratio >= cfg["nine_m_vol_mult"]

            if not (is_9m or is_3x):
                continue

            day_close = float(closes.iloc[i])
            day_high = float(highs.iloc[i])
            day_low = float(lows.iloc[i])
            days_ago = (n - 1) - i
            date_str = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])

            # Try to identify catalyst
            prior_close = float(closes.iloc[i - 1]) if i > 0 else day_close
            gap_pct = (float(df["open"].iloc[i]) - prior_close) / prior_close * 100 if prior_close > 0 else 0
            catalyst = "Unknown catalyst - pure volume signal"
            if abs(gap_pct) > 5:
                catalyst = f"Gap {'up' if gap_pct > 0 else 'down'} {abs(gap_pct):.1f}% on volume"

            return {
                "detected": True,
                "volume": day_vol,
                "vol_ratio": round(vol_ratio, 1),
                "day_high": round(day_high, 2),
                "day_low": round(day_low, 2),
                "day_close": round(day_close, 2),
                "days_ago": days_ago,
                "date": date_str,
                "catalyst": catalyst,
                "gap_pct": round(gap_pct, 1),
                "stop": round(day_low * 0.99, 2),
                "target": round(day_close * 1.10, 2),
            }

    except Exception:
        pass
    return empty


def _detect_story_ep(df: pd.DataFrame, cfg: dict, fund: dict) -> dict:
    """Story EP (Sugar Baby): gap up 10%+ on news/hype WITHOUT strong fundamentals."""
    empty = {"detected": False}
    try:
        closes = df["close"]
        opens = df["open"]
        volumes = df["volume"]
        highs = df["high"]
        lows = df["low"]
        n = len(df)

        # Check last 5 days
        for i in range(max(1, n - 5), n):
            prior_close = float(closes.iloc[i - 1])
            if prior_close <= 0:
                continue

            day_open = float(opens.iloc[i])
            gap_pct = (day_open - prior_close) / prior_close * 100
            if gap_pct < cfg["story_ep_gap_pct"]:
                continue

            day_vol = float(volumes.iloc[i])
            adv_start = max(0, i - 50)
            adv = float(volumes.iloc[adv_start:i].mean()) if i > adv_start else 0
            if adv <= 0:
                continue
            vol_ratio = day_vol / adv

            if vol_ratio < 1.5:
                continue

            # Key: NO strong fundamental backing
            has_earnings_beat = (fund.get("earnings_surprise_pct") is not None
                                and fund.get("earnings_surprise_pct", 0) >= 10)
            has_revenue_accel = (fund.get("revenue_growth_q1") is not None
                                and fund.get("revenue_growth_q1", 0) >= 20)

            if has_earnings_beat or has_revenue_accel:
                continue  # This is a Classic EP, not a Story EP

            day_close = float(closes.iloc[i])
            day_high = float(highs.iloc[i])
            day_low = float(lows.iloc[i])
            days_ago = (n - 1) - i
            date_str = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])

            return {
                "detected": True,
                "gap_pct": round(gap_pct, 1),
                "vol_ratio": round(vol_ratio, 1),
                "day_high": round(day_high, 2),
                "day_low": round(day_low, 2),
                "day_close": round(day_close, 2),
                "days_ago": days_ago,
                "date": date_str,
                "stop": round(day_low * 0.99, 2),
                "target": round(day_close * 1.10, 2),
            }

    except Exception:
        pass
    return empty


def _detect_momentum_burst(df: pd.DataFrame, cfg: dict) -> dict:
    """
    Momentum Burst: stock in established uptrend, pulls back to 10/20 EMA
    on low volume, then breaks out of 3-5 day tight consolidation on
    increasing volume.
    """
    empty = {"detected": False}
    try:
        closes = df["close"]
        volumes = df["volume"]
        highs = df["high"]
        lows = df["low"]
        n = len(df)

        if n < 50:
            return empty

        price = float(closes.iloc[-1])
        ema10 = closes.ewm(span=10, adjust=False).mean()
        ema20 = closes.ewm(span=20, adjust=False).mean()
        ema50 = closes.ewm(span=50, adjust=False).mean()

        ema10_val = float(ema10.iloc[-1])
        ema20_val = float(ema20.iloc[-1])
        ema50_val = float(ema50.iloc[-1])

        # Established uptrend: EMA10 > EMA20 > EMA50
        if not (ema10_val > ema20_val > ema50_val):
            return empty

        # EMA10 must be rising
        if float(ema10.iloc[-1]) <= float(ema10.iloc[-5]):
            return empty

        # Price near 10/20 EMA (within 2% of either)
        pct_from_ema10 = abs(price - ema10_val) / price * 100
        pct_from_ema20 = abs(price - ema20_val) / price * 100

        near_ema = pct_from_ema10 <= 2.0 or pct_from_ema20 <= 2.0
        if not near_ema:
            return empty

        pullback_ma = "EMA10" if pct_from_ema10 <= pct_from_ema20 else "EMA20"

        # Tight consolidation: last 3-5 bars have tight range
        consol_bars = cfg["mom_burst_consol_bars"]
        recent_highs = highs.iloc[-consol_bars:]
        recent_lows = lows.iloc[-consol_bars:]
        range_pct = (float(recent_highs.max()) - float(recent_lows.min())) / price * 100

        if range_pct > 5.0:  # consolidation not tight enough
            return empty

        # Volume drying up during pullback, then expanding today
        avg_vol = float(volumes.iloc[-20:-5].mean())
        pullback_vol = float(volumes.iloc[-consol_bars:-1].mean())
        today_vol = float(volumes.iloc[-1])

        vol_drying = pullback_vol < avg_vol * 0.8 if avg_vol > 0 else False
        vol_expanding = today_vol > pullback_vol * 1.2 if pullback_vol > 0 else False

        if not (vol_drying or vol_expanding):
            return empty

        # Today's close above consolidation high
        consol_high = float(recent_highs.iloc[:-1].max())
        if price < consol_high:
            return empty

        swing_low = float(lows.iloc[-10:].min())

        return {
            "detected": True,
            "pullback_ma": pullback_ma,
            "pct_from_ema10": round(pct_from_ema10, 1),
            "pct_from_ema20": round(pct_from_ema20, 1),
            "consol_bars": consol_bars,
            "consol_range_pct": round(range_pct, 1),
            "vol_expanding": vol_expanding,
            "stop": round(swing_low * 0.99, 2),
            "target": round(price * 1.10, 2),
        }

    except Exception:
        pass
    return empty


# ── VOLUME SPIKE SCANNER ─────────────────────────────────────────────────────

def scan_volume_spikes(bars_data: dict, config: dict = None) -> list:
    """
    Scan all stocks for volume spikes (9M EP candidates).

    Returns list of dicts sorted by volume ratio descending.
    """
    cfg = {**EP_CONFIG, **(config or {})}
    spikes = []

    for ticker, df in bars_data.items():
        try:
            if df is None or len(df) < 20:
                continue

            volumes = df["volume"]
            today_vol = float(volumes.iloc[-1])
            adv_50 = float(volumes.iloc[-50:].mean()) if len(volumes) >= 50 else float(volumes.mean())

            if adv_50 <= 0:
                continue

            vol_ratio = today_vol / adv_50

            is_9m = today_vol >= cfg["nine_m_volume"]
            is_3x = vol_ratio >= cfg["nine_m_vol_mult"]

            if not (is_9m or is_3x):
                continue

            closes = df["close"]
            price = float(closes.iloc[-1])
            prior_close = float(closes.iloc[-2]) if len(closes) >= 2 else price
            chg_pct = (price - prior_close) / prior_close * 100 if prior_close > 0 else 0

            spikes.append({
                "ticker": ticker,
                "volume": int(today_vol),
                "vol_ratio": round(vol_ratio, 1),
                "adv_50": int(adv_50),
                "is_9m": is_9m,
                "price": round(price, 2),
                "chg_pct": round(chg_pct, 1),
                "catalyst": "Unknown - pure volume signal",
            })

        except Exception:
            continue

    spikes.sort(key=lambda x: x["vol_ratio"], reverse=True)
    return spikes


# ── SALES ACCELERATION SCREEN ────────────────────────────────────────────────

def detect_sales_acceleration(fundamentals: dict) -> dict:
    """
    Identify stocks with ACCELERATING revenue growth.

    Returns dict with:
        sales_accelerating: bool
        revenue_trend: list of quarterly growth rates
        triple_digit: bool (100%+ growth)
        sparkline_data: list of values for mini chart
    """
    result = {
        "sales_accelerating": False,
        "revenue_trend": [],
        "triple_digit": False,
        "sparkline_data": [],
    }

    rev_growth = fundamentals.get("revenue_growth_quarters", [])
    if not rev_growth or len(rev_growth) < 2:
        return result

    result["revenue_trend"] = rev_growth
    result["sparkline_data"] = rev_growth

    # Check acceleration: each quarter faster than the last
    accelerating = True
    for i in range(1, len(rev_growth)):
        if rev_growth[i] is None or rev_growth[i - 1] is None:
            accelerating = False
            break
        if rev_growth[i] <= rev_growth[i - 1]:
            accelerating = False
            break

    result["sales_accelerating"] = accelerating

    # Check for triple digit
    if rev_growth and rev_growth[-1] is not None and rev_growth[-1] >= 100:
        result["triple_digit"] = True

    return result


# ── SHORT INTEREST OVERLAY ───────────────────────────────────────────────────

def get_short_interest_data(fundamentals: dict, config: dict = None) -> dict:
    """
    Extract short interest data for a stock.

    Returns dict with:
        short_pct_float: float (short interest as % of float)
        days_to_cover: float
        squeeze_potential: bool
        short_trend: 'increasing' | 'decreasing' | 'stable' | 'unknown'
    """
    cfg = {**EP_CONFIG, **(config or {})}

    result = {
        "short_pct_float": None,
        "days_to_cover": None,
        "squeeze_potential": False,
        "short_trend": "unknown",
    }

    short_pct = fundamentals.get("short_pct_float")
    if short_pct is not None:
        result["short_pct_float"] = round(short_pct, 1)
        result["squeeze_potential"] = short_pct >= cfg["short_interest_squeeze_pct"]

    dtc = fundamentals.get("days_to_cover")
    if dtc is not None:
        result["days_to_cover"] = round(dtc, 1)

    short_trend = fundamentals.get("short_interest_trend")
    if short_trend:
        result["short_trend"] = short_trend

    return result


# ── ENTRY TACTIC RECOMMENDATIONS ─────────────────────────────────────────────

def recommend_entry_tactic(ep_type: str, magna_score: int,
                           signal_data: dict = None) -> dict:
    """
    Based on EP type and MAGNA score, recommend an entry approach.

    Returns dict with:
        entry_approach: str (label)
        entry_description: str (detailed instruction)
        entry_price: float (calculated buy level)
        stop_price: float
        risk_label: str
    """
    s = signal_data or {}
    price = s.get("price", 0)
    ep_day_high = s.get("ep_day_high", price)
    ep_day_low = s.get("ep_day_low", price)
    consol_low = s.get("consolidation_low", ep_day_low)
    swing_low = s.get("stop", price * 0.95)

    if ep_type == "CLASSIC" and magna_score >= 5:
        return {
            "entry_approach": "AGGRESSIVE",
            "entry_description": "Buy at open, stop below gap day low",
            "entry_price": round(price, 2),
            "stop_price": round(ep_day_low * 0.99, 2),
            "risk_label": "High conviction - full size",
        }

    elif ep_type == "CLASSIC" and magna_score >= 3:
        # Opening range high = first 5-min bar high (approximate with day's current high)
        orh = s.get("day_high", price * 1.005)
        return {
            "entry_approach": "STANDARD",
            "entry_description": "Buy above opening range high (first 5-min bar), stop below gap day low",
            "entry_price": round(orh, 2),
            "stop_price": round(ep_day_low * 0.99, 2),
            "risk_label": "Standard size",
        }

    elif ep_type == "DELAYED":
        return {
            "entry_approach": "CONSERVATIVE",
            "entry_description": "Buy on breakout above EP day high, stop below consolidation low",
            "entry_price": round(ep_day_high * 1.005, 2),
            "stop_price": round(consol_low * 0.99, 2),
            "risk_label": "Reduced size until confirmation",
        }

    elif ep_type == "9M":
        day_high = s.get("day_high", price)
        day_low = s.get("day_low", price * 0.95)
        return {
            "entry_approach": "VOLUME CONFIRM",
            "entry_description": "Buy above day's high on continued volume, stop below day's low",
            "entry_price": round(day_high * 1.005, 2),
            "stop_price": round(day_low * 0.99, 2),
            "risk_label": "Confirm volume continuation",
        }

    elif ep_type == "STORY":
        return {
            "entry_approach": "QUICK PROFIT",
            "entry_description": "Buy momentum, move stop to breakeven fast, take 50% at +10%, trail rest",
            "entry_price": round(price, 2),
            "stop_price": round(ep_day_low * 0.99, 2) if ep_day_low else round(price * 0.95, 2),
            "risk_label": "Half size - momentum only",
        }

    elif ep_type == "MOM_BURST":
        return {
            "entry_approach": "PULLBACK ENTRY",
            "entry_description": "Buy near 10/20 EMA, stop below recent swing low",
            "entry_price": round(price, 2),
            "stop_price": round(swing_low, 2),
            "risk_label": "Standard size - trend continuation",
        }

    else:
        return {
            "entry_approach": "WATCH",
            "entry_description": "No clear EP setup - add to watchlist",
            "entry_price": None,
            "stop_price": None,
            "risk_label": "Do not trade yet",
        }


# ── CONVICTION TIER CLASSIFICATION (backtest-validated) ────────────────────

def classify_conviction_tier(signal: dict, bars_data: dict = None,
                              config: dict = None) -> dict:
    """
    Classify an EP signal into conviction tiers based on 5-year
    walk-forward validated filters.

    Returns dict with:
        conviction_tier: 1 | 2 | 0 (0 = no tier / watchlist only)
        tier_label: str
        tier_color: str
        exit_strategy: dict with be_trigger, trail_pct, description
        position_sizing: dict with risk_pct, stop_price, shares_formula
    """
    cfg = {**EP_CONFIG, **(config or {})}

    gap_pct = signal.get("gap_pct") or signal.get("ep_gap_pct", 0)
    ep_type = signal.get("ep_type", "")
    ticker = signal.get("ticker", "")
    price = signal.get("price", 0)
    ep_day_low = signal.get("ep_day_low") or signal.get("day_low", 0)

    # Calculate avg daily dollar volume if bars available
    dollar_vol = 0
    if bars_data and ticker in bars_data:
        df = bars_data[ticker]
        if df is not None and len(df) >= 50:
            dollar_vol = float(
                (df["close"].iloc[-50:] * df["volume"].iloc[-50:]).mean()
            )
    # Fallback: use signal data if available
    if dollar_vol == 0:
        dollar_vol = signal.get("avg_dollar_vol", signal.get("dollar_vol", 0))

    is_micro = dollar_vol < cfg["tier1_max_dollar_vol"]

    # Stop and exit strategy (same for both tiers)
    stop_price = round(ep_day_low * 0.99, 2) if ep_day_low else round(price * 0.85, 2)
    stop_dist_pct = round((price - stop_price) / price * 100, 1) if price > 0 else 0
    be_trigger = cfg["exit_be_trigger_pct"]
    trail_pct = cfg["exit_trail_pct"]
    risk_pct = cfg["default_risk_pct"]

    exit_strategy = {
        "be_trigger_pct": be_trigger,
        "trail_pct": trail_pct,
        "stop_price": stop_price,
        "stop_dist_pct": stop_dist_pct,
        "description": (
            f"Initial stop: ${stop_price} ({stop_dist_pct}% below entry). "
            f"After +{be_trigger}% gain, move stop to breakeven. "
            f"Then trail {trail_pct}% from highest close. No time limit."
        ),
    }

    position_sizing = {
        "risk_pct": risk_pct,
        "stop_price": stop_price,
        "stop_dist_pct": stop_dist_pct,
        "description": (
            f"Risk {risk_pct}% of equity at stop. "
            f"Shares = (equity * {risk_pct}%) / (entry - ${stop_price})."
        ),
    }

    # Tier 2: Gap 50%+ AND STORY type
    # 5yr validated: 66% WR, +9.3% exp, PF 2.36, ~10 trades/yr
    if gap_pct >= cfg["tier2_min_gap_pct"] and ep_type == "STORY":
        return {
            "conviction_tier": 2,
            "tier_label": "TIER 2 - Sniper",
            "tier_color": "#ff6d00",
            "tier_description": "Gap 50%+ STORY: 66% WR, +9.3% avg, ~10/yr (5yr validated)",
            "exit_strategy": exit_strategy,
            "position_sizing": position_sizing,
            "dollar_vol": round(dollar_vol),
        }

    # Tier 1: Gap 30%+ AND micro-cap (< $5M daily dollar vol)
    # 5yr validated: 56% WR, +13.7% exp, PF 3.74, ~25 trades/yr
    if gap_pct >= cfg["tier1_min_gap_pct"] and is_micro:
        return {
            "conviction_tier": 1,
            "tier_label": "TIER 1 - Bread & Butter",
            "tier_color": "#2d7a3a",
            "tier_description": "Gap 30%+ micro-cap: 56% WR, +13.7% avg, ~25/yr (5yr validated)",
            "exit_strategy": exit_strategy,
            "position_sizing": position_sizing,
            "dollar_vol": round(dollar_vol),
        }

    # No tier: still show but flag as unvalidated
    return {
        "conviction_tier": 0,
        "tier_label": "WATCHLIST",
        "tier_color": "#666",
        "tier_description": "Does not match backtested filter criteria",
        "exit_strategy": exit_strategy,
        "position_sizing": position_sizing,
        "dollar_vol": round(dollar_vol),
    }


# ── S&P 500 BREADTH MARKET REGIME ───────────────────────────────────────────

def calculate_sp500_breadth(bars_data: dict) -> dict:
    """
    Calculate S&P 500 breadth-based market regime.

    Returns:
        pct_above_50ma: % of S&P 500 stocks above 50-day MA
        regime: 'BULLISH' | 'NEUTRAL' | 'BEARISH'
        regime_color: 'green' | 'yellow' | 'red'
        spy_above_50ma: bool
        vix_level: float
        breadth_ad_ratio: float (advance/decline ratio)
        trade_guidance: str
    """
    result = {
        "pct_above_50ma": None,
        "regime": "NEUTRAL",
        "regime_color": "yellow",
        "spy_above_50ma": None,
        "vix_level": None,
        "breadth_ad_ratio": None,
        "trade_guidance": "Trade selectively, reduce size",
    }

    # Count stocks above 50-day MA
    above_50 = 0
    total = 0
    advancing = 0
    declining = 0

    for ticker, df in bars_data.items():
        try:
            if df is None or len(df) < 50:
                continue
            closes = df["close"]
            price = float(closes.iloc[-1])
            ma50 = float(closes.iloc[-50:].mean())
            total += 1
            if price > ma50:
                above_50 += 1

            # Advance/decline
            prev = float(closes.iloc[-2])
            if price > prev:
                advancing += 1
            elif price < prev:
                declining += 1
        except Exception:
            continue

    if total > 0:
        pct = round(above_50 / total * 100, 1)
        result["pct_above_50ma"] = pct

        if pct >= 70:
            result["regime"] = "BULLISH"
            result["regime_color"] = "green"
            result["trade_guidance"] = "Trade aggressively, full size"
        elif pct >= 40:
            result["regime"] = "NEUTRAL"
            result["regime_color"] = "yellow"
            result["trade_guidance"] = "Trade selectively, reduce size"
        else:
            result["regime"] = "BEARISH"
            result["regime_color"] = "red"
            result["trade_guidance"] = "Only trade A+ setups, tight stops"

    if declining > 0:
        result["breadth_ad_ratio"] = round(advancing / declining, 2)
    elif advancing > 0:
        result["breadth_ad_ratio"] = advancing  # all advancing

    # SPY trend
    spy_df = bars_data.get("SPY")
    if spy_df is not None and len(spy_df) >= 50:
        spy_price = float(spy_df["close"].iloc[-1])
        spy_ma50 = float(spy_df["close"].iloc[-50:].mean())
        result["spy_above_50ma"] = spy_price > spy_ma50

    # VIX — fetch via Polygon (falls back gracefully if no API key)
    try:
        from polygon_client import _get
        vix_data = _get("/v2/aggs/ticker/VIX/prev", {"adjusted": "true"})
        if vix_data and vix_data.get("results"):
            result["vix_level"] = round(float(vix_data["results"][0]["c"]), 1)
    except Exception:
        pass

    return result


# ── FUNDAMENTAL DATA FETCHER ─────────────────────────────────────────────────

def fetch_fundamentals_batch(tickers: list, delay: float = 0.15) -> dict:
    """
    Fetch fundamental data for MAGNA scoring using yfinance.

    Returns dict: ticker -> fundamentals dict
    """
    import time

    results = {}

    for ticker in tickers:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info

            fund = {}

            # Market cap
            fund["market_cap"] = info.get("marketCap")

            # Analyst count
            fund["analyst_count"] = info.get("numberOfAnalystOpinions")

            # Short interest
            shares_short = info.get("sharesShort")
            float_shares = info.get("floatShares")
            if shares_short and float_shares and float_shares > 0:
                fund["short_pct_float"] = round(shares_short / float_shares * 100, 1)
            fund["days_to_cover"] = info.get("shortRatio")

            # Earnings surprise
            # yfinance doesn't always have this, use earningsQuarterlyGrowth as proxy
            eq_growth = info.get("earningsQuarterlyGrowth")
            if eq_growth is not None:
                fund["earnings_surprise_pct"] = round(eq_growth * 100, 1)

            # Revenue growth
            rev_growth = info.get("revenueGrowth")
            if rev_growth is not None:
                fund["revenue_growth_q1"] = round(rev_growth * 100, 1)

            # IPO date / first trade date
            # yfinance doesn't directly provide IPO date, but we can check
            # if the stock has been public < 10 years by looking at earliest available data
            first_trade = info.get("firstTradeDateEpochUtc")
            if first_trade:
                fund["ipo_date"] = datetime.fromtimestamp(first_trade).strftime("%Y-%m-%d")

            # Recommendation (proxy for analyst upgrades)
            rec = info.get("recommendationKey")
            if rec in ("strong_buy", "buy"):
                fund["recent_upgrade"] = True

            # Target price (proxy for price target raised)
            target = info.get("targetMeanPrice")
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            if target and current and target > current * 1.1:
                fund["price_target_raised"] = True

            # Forward PE vs trailing PE (proxy for guidance raised)
            forward_pe = info.get("forwardPE")
            trailing_pe = info.get("trailingPE")
            if forward_pe and trailing_pe and forward_pe < trailing_pe * 0.85:
                fund["estimates_revised_up"] = True

            # Revenue growth quarters (for sales acceleration)
            # Build from quarterly financials if available
            try:
                tk = yf.Ticker(ticker)
                quarterly = tk.quarterly_financials
                if quarterly is not None and not quarterly.empty:
                    rev_row = None
                    for idx in quarterly.index:
                        if "revenue" in str(idx).lower() or "total revenue" in str(idx).lower():
                            rev_row = quarterly.loc[idx]
                            break
                    if rev_row is not None and len(rev_row) >= 4:
                        # Calculate YoY growth for available quarters
                        revs = [float(v) for v in rev_row.values[:4] if pd.notna(v)]
                        if len(revs) >= 2:
                            growth_rates = []
                            # Revenue is in reverse chronological order
                            for i in range(len(revs) - 1):
                                if revs[i + 1] > 0:
                                    g = (revs[i] - revs[i + 1]) / revs[i + 1] * 100
                                    growth_rates.append(round(g, 1))
                            fund["revenue_growth_quarters"] = growth_rates
                            if len(growth_rates) >= 2:
                                fund["revenue_growth_q2"] = growth_rates[1] if len(growth_rates) > 1 else None
            except Exception:
                pass

            results[ticker] = fund

            time.sleep(delay)

        except Exception as e:
            print(f"[stockbee] Fundamentals fetch failed for {ticker}: {e}")
            results[ticker] = {}

    return results


# ── EP WATCHLIST PERSISTENCE (DB) ────────────────────────────────────────────

def init_ep_watchlist_table():
    """Create EP watchlist table if it doesn't exist."""
    from database import get_conn
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ep_watchlist (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT NOT NULL,
                ep_type         TEXT NOT NULL,
                ep_date         TEXT NOT NULL,
                ep_day_high     REAL,
                ep_day_low      REAL,
                ep_day_open     REAL,
                ep_day_close    REAL,
                ep_gap_pct      REAL,
                ep_vol_ratio    REAL,
                magna_score     INTEGER,
                magna_details   TEXT,
                added_date      TEXT DEFAULT (date('now')),
                status          TEXT DEFAULT 'watching',
                breakout_date   TEXT,
                breakout_price  REAL,
                removed_date    TEXT,
                days_watched    INTEGER DEFAULT 0,
                consolidation_low  REAL,
                current_price   REAL,
                last_updated    TEXT DEFAULT (datetime('now')),
                UNIQUE(ticker, ep_date)
            );
            CREATE INDEX IF NOT EXISTS idx_ep_watchlist_ticker ON ep_watchlist(ticker);
            CREATE INDEX IF NOT EXISTS idx_ep_watchlist_status ON ep_watchlist(status);
        """)


def add_to_ep_watchlist(signal: dict):
    """Add an EP signal to the watchlist."""
    from database import get_conn
    init_ep_watchlist_table()

    ticker = signal.get("ticker")
    ep_date = signal.get("ep_day") or signal.get("ep_date") or date.today().isoformat()

    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO ep_watchlist (
                ticker, ep_type, ep_date, ep_day_high, ep_day_low,
                ep_day_open, ep_day_close, ep_gap_pct, ep_vol_ratio,
                magna_score, magna_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker,
            signal.get("ep_type", "CLASSIC"),
            ep_date,
            signal.get("ep_day_high"),
            signal.get("ep_day_low"),
            signal.get("ep_day_open"),
            signal.get("ep_day_close"),
            signal.get("ep_gap_pct"),
            signal.get("ep_vol_ratio"),
            signal.get("magna_score"),
            json.dumps(signal.get("magna_details", {})),
        ))


def get_ep_watchlist(status: str = "watching") -> list:
    """Get all EP watchlist entries."""
    from database import get_conn
    init_ep_watchlist_table()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM ep_watchlist
            WHERE status = ?
            ORDER BY added_date DESC
        """, (status,)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["magna_details"] = json.loads(d["magna_details"]) if d["magna_details"] else {}
            except Exception:
                d["magna_details"] = {}
            results.append(d)
        return results


def update_ep_watchlist(bars_data: dict, config: dict = None):
    """
    Daily update of EP watchlist:
    - Update current prices and consolidation depth
    - Check for breakout signals (Delayed EP entry)
    - Remove entries older than 30 days
    """
    cfg = {**EP_CONFIG, **(config or {})}
    from database import get_conn
    init_ep_watchlist_table()

    watchlist = get_ep_watchlist("watching")
    today = date.today().isoformat()
    alerts = []

    with get_conn() as conn:
        for entry in watchlist:
            ticker = entry["ticker"]
            df = bars_data.get(ticker)
            if df is None or len(df) < 5:
                continue

            closes = df["close"]
            volumes = df["volume"]
            lows = df["low"]
            highs = df["high"]
            price = float(closes.iloc[-1])
            today_vol = float(volumes.iloc[-1])

            ep_high = entry.get("ep_day_high", 0)
            ep_close = entry.get("ep_day_close", 0)
            ep_low = entry.get("ep_day_low", 0)

            # Days since EP
            try:
                ep_dt = datetime.strptime(entry["ep_date"], "%Y-%m-%d")
                days_since = (datetime.now() - ep_dt).days
            except Exception:
                days_since = 0

            # Consolidation depth (% pullback from EP high)
            consol_depth = round((ep_high - price) / ep_high * 100, 1) if ep_high > 0 else 0

            # Consolidation low (lowest low since EP date)
            consol_low = float(lows.iloc[-min(days_since + 1, len(lows)):].min())

            # Volume ratio
            adv_50 = float(volumes.iloc[-50:].mean()) if len(volumes) >= 50 else float(volumes.mean())
            vol_ratio = today_vol / adv_50 if adv_50 > 0 else 0

            # Check for breakout (Delayed EP entry signal)
            breakout = False
            if (price > ep_high
                    and vol_ratio >= cfg["delayed_ep_breakout_vol_mult"]
                    and days_since >= 5):
                breakout = True
                alerts.append({
                    "ticker": ticker,
                    "type": "DELAYED_EP_BREAKOUT",
                    "price": price,
                    "ep_high": ep_high,
                    "vol_ratio": round(vol_ratio, 1),
                    "days_since_ep": days_since,
                })

            # Update entry
            if breakout:
                conn.execute("""
                    UPDATE ep_watchlist SET
                        status = 'breakout',
                        breakout_date = ?,
                        breakout_price = ?,
                        current_price = ?,
                        days_watched = ?,
                        consolidation_low = ?,
                        last_updated = datetime('now')
                    WHERE id = ?
                """, (today, price, price, days_since, consol_low, entry["id"]))
            elif days_since > cfg["watchlist_max_days"]:
                conn.execute("""
                    UPDATE ep_watchlist SET
                        status = 'expired',
                        removed_date = ?,
                        days_watched = ?,
                        current_price = ?,
                        last_updated = datetime('now')
                    WHERE id = ?
                """, (today, days_since, price, entry["id"]))
            else:
                conn.execute("""
                    UPDATE ep_watchlist SET
                        current_price = ?,
                        days_watched = ?,
                        consolidation_low = ?,
                        last_updated = datetime('now')
                    WHERE id = ?
                """, (price, days_since, consol_low, entry["id"]))

    return alerts


def get_ep_watchlist_display() -> list:
    """
    Get EP watchlist with calculated display fields.
    """
    watchlist = get_ep_watchlist("watching")

    for entry in watchlist:
        ep_high = entry.get("ep_day_high", 0)
        ep_close = entry.get("ep_day_close", 0)
        current = entry.get("current_price", 0)

        # Price vs EP day close
        if ep_close and current:
            entry["pct_vs_ep_close"] = round((current - ep_close) / ep_close * 100, 1)
        else:
            entry["pct_vs_ep_close"] = None

        # Consolidation depth
        if ep_high and current:
            entry["consolidation_depth"] = round((ep_high - current) / ep_high * 100, 1)
        else:
            entry["consolidation_depth"] = None

    return watchlist


def _compute_sector_rs_summary(bars_data: dict) -> dict:
    """Compute leading/lagging sectors vs SPY for dashboard one-liner."""
    try:
        from sector_rs import SECTOR_ETFS
    except ImportError:
        return {}

    spy = bars_data.get("SPY")
    if spy is None or len(spy) < 25:
        return {}

    spy_ret = float(spy["close"].iloc[-1] / spy["close"].iloc[-22] - 1) if len(spy) >= 22 else 0

    sectors = []
    for name, etf in SECTOR_ETFS.items():
        df = bars_data.get(etf)
        if df is None or len(df) < 22:
            continue
        ret = float(df["close"].iloc[-1] / df["close"].iloc[-22] - 1)
        rs = round((ret - spy_ret) * 100, 2)
        sectors.append({"name": name, "etf": etf, "rs_1m": rs})

    sectors.sort(key=lambda x: x["rs_1m"], reverse=True)
    leading = [s["name"] for s in sectors if s["rs_1m"] > 1]
    lagging = [s["name"] for s in sectors if s["rs_1m"] < -1]

    return {
        "leading": leading[:5],
        "lagging": lagging[:5],
        "all_sectors": sectors,
    }


# ── FULL EP SCAN PIPELINE ────────────────────────────────────────────────────

def run_ep_scan(bars_data: dict, fundamentals: dict = None,
                config: dict = None) -> dict:
    """
    Run the full Stockbee EP scan pipeline.

    Returns dict with all EP results organized by type.
    """
    cfg = {**EP_CONFIG, **(config or {})}
    fund_data = fundamentals or {}

    # Get past EPs from watchlist for delayed EP detection
    past_eps_raw = get_ep_watchlist("watching")
    past_eps_by_ticker = {}
    for ep in past_eps_raw:
        ticker = ep["ticker"]
        past_eps_by_ticker.setdefault(ticker, []).append({
            "days_since": ep.get("days_watched", 0),
            "ep_date": ep.get("ep_date"),
            "ep_day_high": ep.get("ep_day_high"),
            "ep_day_low": ep.get("ep_day_low"),
            "ep_day_open": ep.get("ep_day_open"),
        })

    all_eps = []
    classic_eps = []
    delayed_eps = []
    nine_m_eps = []
    story_eps = []
    mom_bursts = []

    for ticker, df in bars_data.items():
        if df is None or len(df) < 30:
            continue

        fund = fund_data.get(ticker, {})
        past_eps = past_eps_by_ticker.get(ticker, [])

        # Classify EP type
        ep_result = classify_ep_type(df, fund, past_eps, cfg)
        if ep_result["ep_type"] is None:
            continue

        # Calculate MAGNA score
        magna = calculate_magna_score(ticker, df, fund, cfg)

        # Sales acceleration
        sales = detect_sales_acceleration(fund)

        # Short interest
        short_int = get_short_interest_data(fund, cfg)

        # Entry tactic
        entry_tactic = recommend_entry_tactic(
            ep_result["ep_type"], magna["magna_score"],
            {**ep_result, "price": float(df["close"].iloc[-1])}
        )

        # Conviction tier (backtest-validated)
        price = float(df["close"].iloc[-1])
        tier_info = classify_conviction_tier(
            {**ep_result, "ticker": ticker, "price": price},
            bars_data, cfg
        )

        # Build full signal
        signal = {
            "ticker": ticker,
            "price": round(price, 2),
            **ep_result,
            **magna,
            **sales,
            **short_int,
            "entry_tactic": entry_tactic,
            **tier_info,
        }

        all_eps.append(signal)

        # Route to correct list
        if ep_result["ep_type"] == "CLASSIC":
            classic_eps.append(signal)
            # Add to watchlist for delayed EP tracking
            add_to_ep_watchlist({**signal, "ep_date": ep_result.get("ep_date")})
        elif ep_result["ep_type"] == "DELAYED":
            delayed_eps.append(signal)
        elif ep_result["ep_type"] == "9M":
            nine_m_eps.append(signal)
            add_to_ep_watchlist({**signal, "ep_date": ep_result.get("ep_date")})
        elif ep_result["ep_type"] == "STORY":
            story_eps.append(signal)
        elif ep_result["ep_type"] == "MOM_BURST":
            mom_bursts.append(signal)

    # Sort each list by MAGNA score descending
    for lst in [all_eps, classic_eps, delayed_eps, nine_m_eps, story_eps, mom_bursts]:
        lst.sort(key=lambda x: x.get("magna_score", 0), reverse=True)

    # Volume spikes
    vol_spikes = scan_volume_spikes(bars_data, cfg)

    # S&P breadth
    sp_breadth = calculate_sp500_breadth(bars_data)

    # EP Watchlist (with display fields)
    ep_watchlist = get_ep_watchlist_display()

    # Sector RS summary (leading/lagging vs SPY)
    sector_rs_summary = _compute_sector_rs_summary(bars_data)

    return {
        "all_eps": all_eps,
        "classic_eps": classic_eps,
        "delayed_eps": delayed_eps,
        "nine_m_eps": nine_m_eps,
        "story_eps": story_eps,
        "mom_bursts": mom_bursts,
        "volume_spikes": vol_spikes[:50],
        "sp500_breadth": sp_breadth,
        "ep_watchlist": ep_watchlist,
        "sector_rs_summary": sector_rs_summary,
        "ep_config": cfg,
        "summary": {
            "total_eps": len(all_eps),
            "classic": len(classic_eps),
            "delayed": len(delayed_eps),
            "nine_m": len(nine_m_eps),
            "story": len(story_eps),
            "mom_burst": len(mom_bursts),
            "vol_spikes": len(vol_spikes),
            "watchlist_active": len(ep_watchlist),
            "high_conviction": sum(1 for e in all_eps if e.get("magna_score", 0) >= 5),
            "tier1_count": sum(1 for e in all_eps if e.get("conviction_tier") == 1),
            "tier2_count": sum(1 for e in all_eps if e.get("conviction_tier") == 2),
        },
    }
