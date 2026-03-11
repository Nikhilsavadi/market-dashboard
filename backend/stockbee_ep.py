"""
stockbee_ep.py
--------------
Pradeep Bonde (Stockbee) Episodic Pivot system — full implementation.

Covers:
  LONG:
  1. MAGNA 53+ CAP 10x10 scoring (0-7)
  2. Five EP variations: Classic, Delayed, 9M, Story, Momentum Burst
  3. Delayed EP watchlist tracker (persisted in DB)
  4. Volume spike scanner (9M EP detection)
  5. Kelly conviction tiers (MAX/STRONG/NORMAL/WATCHLIST)
  6. Entry price intelligence (zones, R-multiples, quality score)
  7. Tiny Titans quality filter (7 criteria, 0-7 score)

  SHORT:
  8. Short EP detection: SHORT_CLASSIC, SHORT_DELAYED, SHORT_STORY
  9. Short MAGNA score (0-6): institutional, short interest, revenue, trend, volume, catalyst
  10. Short catalyst classification: earnings miss, guidance cut, downgrade, accounting, regulatory
  11. Short entry intelligence (inverted levels, bounce resistance)
  12. Bear regime auto-promote (shorts to top when breadth < 40%)

  SHARED:
  13. S&P 500 breadth market regime indicator
  14. 2LYNCH checklist, TI65, Ants, DNB, bag holder, sales acceleration
  15. Short interest overlay, sector RS summary

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

    # ── Kelly Conviction Tiers (validated out-of-sample, 1663 trades, 5yr) ──
    # Only tiers that validated in both train AND test are included.
    # Target: 2-3 trades/month. Everything below Tier 3 is watchlist-only.
    #
    # TIER 1 "MAX" (½Kelly 15-26%, size 3x):
    #   Gap30+ micro-cap:     test 68% WR, +20.5% avg, PF 4.23
    #   Gap20+ TI65-strong:   test 46% WR, +7.1% avg, PF 2.68
    # TIER 2 "STRONG" (½Kelly 9-10%, size 2x):
    #   Gap50+ any:           test 44% WR, +7.0% avg, PF 1.72
    #   Micro+neglected+gap20: test 44% WR, +5.9% avg, PF 1.74
    #   TT>=5 any:            test 44% WR, +2.3% avg, PF 1.90
    # TIER 3 "NORMAL" (½Kelly 4%, size 1x):
    #   Vol5x+ gap20+:        test 38% WR, +1.9% avg, PF 1.29
    #   Vol10x+ any:          test 45% WR, +1.8% avg, PF 1.23

    "tier_max_dollar_vol": 5_000_000,   # Micro-cap threshold (avg daily $ vol)
    "tier1_gap_micro": 30,              # Gap % for micro-cap max tier
    "tier1_gap_ti65": 20,               # Gap % + TI65 STRONG for max tier
    "tier2_gap_any": 50,                # Gap % for strong tier (any stock)
    "tier2_gap_micro_neglected": 20,    # Gap % for micro + neglected
    "tier2_tt_score": 5,                # Tiny Titans score for strong tier
    "tier3_gap_vol5x": 20,              # Gap % with 5x+ volume
    "tier3_vol_any": 10,                # Volume ratio for normal tier (any gap)

    # Position sizing
    "default_risk_pct": 3,              # Risk 3% of equity per trade at stop
    "default_leverage": 50,             # CFD leverage
    "default_max_positions": 3,         # Max concurrent positions (focused)

    # 2LYNCH checklist (momentum burst scoring)
    "lynch_min_score": 4,               # Minimum 2LYNCH score to highlight

    # Bag holder protection
    "bag_holder_consec_up_days": 3,     # Flag after X consecutive up days

    # TI65 trend intensity
    "ti65_period": 65,                  # Price momentum lookback (days)
    "ti65_min_pct": 10,                 # Minimum 65-day return % for confirmed uptrend

    # Ants pattern
    "ants_tight_days": 3,              # Minimum days of tight consolidation
    "ants_tight_range_pct": 1.5,       # Max daily range % during consolidation
    "ants_narrow_day_pct": 0.3,        # Final narrow day range %

    # Opening range volume
    "or_vol_check_minutes": 20,        # First X minutes of trading
    "or_vol_adv_pct": 100,             # Flag if X% of ADV traded in opening range

    # Quarterly earnings weighting
    "earnings_weight_q1": 0.40,        # Most recent quarter weight
    "earnings_weight_q2": 0.20,
    "earnings_weight_q3": 0.20,
    "earnings_weight_q4": 0.20,

    # Do Not Buy filters
    "dnb_consec_up_days": 3,           # Consecutive up days threshold
    "dnb_extended_above_50ma_pct": 30, # % above 50MA = extended
    "dnb_vol_decline_days": 3,         # Check last X up days for declining volume

    # ── SHORT EP settings ────────────────────────────────────────────────
    "short_ep_gap_pct": -20,           # Gap DOWN 20%+ (negative)
    "short_ep_vol_mult": 3,            # Volume 3x+ average
    "short_ep_story_gap_pct": -15,     # Story short: gap down 15%+
    "short_delayed_lookback_days": 30, # Delayed short: lookback window
    "short_delayed_bounce_min": 3,     # Delayed short: min bounce days
    "short_delayed_bounce_max": 10,    # Delayed short: max bounce days
    "short_delayed_vol_mult": 1.5,     # Delayed short: breakdown volume mult
    "short_magna_inst_own_min": 60,    # Short MAGNA: institutional ownership %
    "short_magna_short_int_min": 10,   # Short MAGNA: short interest already building
    "short_magna_rev_decline_qtrs": 2, # Short MAGNA: declining rev for X+ quarters
    "bear_regime_threshold": 40,       # Auto-promote shorts when breadth below X%
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

            # Require meaningful price move — gap ≥3% OR intraday range ≥5%
            intraday_range = (day_high - day_low) / day_low * 100 if day_low > 0 else 0
            if abs(gap_pct) < 3 and intraday_range < 5:
                continue

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


# ── ENTRY PRICE INTELLIGENCE ─────────────────────────────────────────────────

def calculate_entry_intelligence(df: pd.DataFrame, ep_result: dict,
                                  config: dict = None) -> dict:
    """
    Compute actionable price levels for an EP setup from daily OHLCV data.

    Returns:
        entry_zone_low / entry_zone_high — optimal buy range
        gap_fill_level — prior close (gap start); breach = thesis broken
        prior_base_high / prior_base_low — pre-gap consolidation range
        ema10 / ema20 / ema50 — moving average pullback zones
        vwap_proxy — EP day typical price (H+L+C)/3
        atr — 14-day ATR for volatility context
        stop_price — calculated stop (EP day low -1% or ATR-based)
        risk_dollars — entry mid minus stop
        r_levels — dict with 1R, 2R, 3R target prices
        risk_reward — expected R:R based on historical EP moves
        entry_quality — EXCELLENT / GOOD / FAIR / POOR
        entry_notes — list of human-readable notes
    """
    cfg = {**EP_CONFIG, **(config or {})}
    result = {
        "entry_zone_low": None, "entry_zone_high": None,
        "gap_fill_level": None, "prior_base_high": None, "prior_base_low": None,
        "ema10": None, "ema20": None, "ema50": None,
        "vwap_proxy": None, "atr": None,
        "stop_price": None, "risk_dollars": None,
        "r_levels": {}, "risk_reward": None,
        "entry_quality": "POOR", "entry_notes": [],
    }

    if df is None or len(df) < 20:
        return result

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df["volume"]
    n = len(df)

    price = float(closes.iloc[-1])
    ep_type = ep_result.get("ep_type", "")
    gap_pct = ep_result.get("ep_gap_pct") or ep_result.get("gap_pct", 0)
    ep_day_high = ep_result.get("ep_day_high") or ep_result.get("day_high", price)
    ep_day_low = ep_result.get("ep_day_low") or ep_result.get("day_low", price)
    ep_day_close = ep_result.get("ep_day_close") or ep_result.get("day_close", price)
    days_ago = ep_result.get("ep_days_ago") or ep_result.get("days_ago", 0)
    notes = []

    # ── 1. Gap fill level (prior close = where the gap started) ───────────
    # If price returns here, the gap has been fully retraced → thesis broken
    ep_idx = max(0, n - 1 - days_ago)
    if ep_idx > 0:
        gap_fill = round(float(closes.iloc[ep_idx - 1]), 2)
    else:
        # Estimate from gap %
        gap_fill = round(price / (1 + gap_pct / 100), 2) if gap_pct > 0 else None
    result["gap_fill_level"] = gap_fill

    # ── 2. Pre-gap consolidation range (20 bars before EP day) ────────────
    base_end = max(0, ep_idx - 1)
    base_start = max(0, base_end - 20)
    if base_end > base_start:
        base_highs = highs.iloc[base_start:base_end]
        base_lows = lows.iloc[base_start:base_end]
        result["prior_base_high"] = round(float(base_highs.max()), 2)
        result["prior_base_low"] = round(float(base_lows.min()), 2)

    # ── 3. EMAs (current values) ─────────────────────────────────────────
    if n >= 10:
        result["ema10"] = round(float(closes.ewm(span=10, adjust=False).mean().iloc[-1]), 2)
    if n >= 20:
        result["ema20"] = round(float(closes.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    if n >= 50:
        result["ema50"] = round(float(closes.ewm(span=50, adjust=False).mean().iloc[-1]), 2)

    # ── 4. VWAP proxy from EP day (typical price) ────────────────────────
    if ep_day_high and ep_day_low and ep_day_close:
        result["vwap_proxy"] = round((ep_day_high + ep_day_low + ep_day_close) / 3, 2)

    # ── 5. ATR (14-day) ──────────────────────────────────────────────────
    if n >= 15:
        tr_vals = []
        for i in range(n - 14, n):
            h = float(highs.iloc[i])
            l = float(lows.iloc[i])
            pc = float(closes.iloc[i - 1])
            tr_vals.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = round(sum(tr_vals) / len(tr_vals), 2)
        result["atr"] = atr
    else:
        atr = round((float(highs.iloc[-1]) - float(lows.iloc[-1])), 2)
        result["atr"] = atr

    # ── 6. Stop price ────────────────────────────────────────────────────
    # Primary: EP day low -1%  |  Fallback: 2x ATR below entry
    ep_low_stop = round(ep_day_low * 0.99, 2) if ep_day_low else None

    # For delayed / MOM_BURST use recent swing low
    if ep_type in ("DELAYED", "MOM_BURST"):
        lookback = min(10, n - 1)
        swing_low = round(float(lows.iloc[-lookback:].min()) * 0.99, 2)
        stop_price = swing_low
        notes.append(f"Stop at recent swing low ${swing_low}")
    elif ep_low_stop:
        stop_price = ep_low_stop
    else:
        stop_price = round(price - 2 * atr, 2)

    # Floor: never set stop above gap fill (that's thesis-dead territory)
    if gap_fill and stop_price and stop_price > gap_fill:
        stop_price = round(gap_fill * 0.99, 2)
        notes.append("Stop widened to below gap fill level")

    result["stop_price"] = stop_price

    # ── 7. Entry zone ────────────────────────────────────────────────────
    # Zone depends on EP type and timing (same day vs days later)
    if ep_type == "CLASSIC":
        if days_ago == 0:
            # Same day: entry at market or on ORH breakout
            zone_low = round(price, 2)
            zone_high = round(price * 1.005, 2)
            notes.append("EP day — buy at market or above opening range high")
        else:
            # Days later: first pullback to EP day high or VWAP
            vwap = result["vwap_proxy"] or ep_day_close
            zone_low = round(min(vwap, ep_day_high) * 0.995, 2)
            zone_high = round(ep_day_high * 1.005, 2)
            notes.append(f"Pullback entry near EP day high ${ep_day_high}")
            if price > ep_day_high * 1.05:
                notes.append("CAUTION: price extended >5% above EP day high")

    elif ep_type == "DELAYED":
        # Buy on breakout above EP day high
        zone_low = round(ep_day_high, 2)
        zone_high = round(ep_day_high * 1.01, 2)
        notes.append(f"Breakout entry above EP day high ${ep_day_high}")

    elif ep_type == "9M":
        # Volume signal — entry on continuation above day high
        day_high = ep_result.get("day_high", price)
        zone_low = round(day_high, 2)
        zone_high = round(day_high * 1.005, 2)
        notes.append("Buy above signal day high on continued volume")

    elif ep_type == "STORY":
        # Momentum entry — buy at market, tight stop
        zone_low = round(price * 0.995, 2)
        zone_high = round(price * 1.005, 2)
        notes.append("Momentum entry — move to breakeven fast")

    elif ep_type == "MOM_BURST":
        # Pullback to EMA — enter near EMA10/20
        ema_entry = result["ema10"] or result["ema20"] or price
        zone_low = round(ema_entry * 0.995, 2)
        zone_high = round(ema_entry * 1.005, 2)
        notes.append(f"Pullback entry near EMA ${ema_entry}")

    else:
        zone_low = round(price * 0.995, 2)
        zone_high = round(price * 1.005, 2)

    result["entry_zone_low"] = zone_low
    result["entry_zone_high"] = zone_high

    # ── 8. Risk dollars and R-multiples ──────────────────────────────────
    entry_mid = round((zone_low + zone_high) / 2, 2)
    risk = round(entry_mid - stop_price, 2) if stop_price and entry_mid > stop_price else None

    if risk and risk > 0:
        result["risk_dollars"] = risk
        result["r_levels"] = {
            "r1": round(entry_mid + risk, 2),
            "r2": round(entry_mid + 2 * risk, 2),
            "r3": round(entry_mid + 3 * risk, 2),
        }

        # Risk/reward: use 2R as default target (realistic for EPs)
        result["risk_reward"] = round(2.0, 1)

        # Adjust R:R based on tier potential
        if gap_pct >= 30:
            result["risk_reward"] = round(3.0, 1)
            notes.append("Large gap — 3R+ potential")
        elif gap_pct >= 50:
            result["risk_reward"] = round(4.0, 1)

        # Warn if risk is too wide (>15% from entry)
        risk_pct = risk / entry_mid * 100
        if risk_pct > 15:
            notes.append(f"WARNING: wide stop ({risk_pct:.0f}% risk) — consider half size")
        elif risk_pct < 3:
            notes.append(f"Tight stop ({risk_pct:.1f}% risk) — good R:R")

    # ── 9. Entry quality score ───────────────────────────────────────────
    quality_pts = 0

    # Price near entry zone (not chasing)
    if zone_low and zone_high:
        if zone_low <= price <= zone_high * 1.02:
            quality_pts += 2
            notes.append("Price in entry zone")
        elif price <= zone_high * 1.05:
            quality_pts += 1
        else:
            notes.append("Price above entry zone — wait for pullback")

    # Volume confirmation today
    if n >= 20:
        adv20 = float(volumes.iloc[-20:].mean())
        today_vol = float(volumes.iloc[-1])
        if adv20 > 0 and today_vol > adv20 * 1.5:
            quality_pts += 1
            notes.append("Volume confirming (+50% vs avg)")

    # Not extended from EMAs
    if result["ema20"] and result["ema20"] > 0:
        pct_from_20 = (price - result["ema20"]) / result["ema20"] * 100
        if 0 <= pct_from_20 <= 5:
            quality_pts += 1
        elif pct_from_20 > 15:
            notes.append(f"Extended {pct_from_20:.0f}% above 20EMA")

    # Tight stop available (risk < 8%)
    if risk and entry_mid > 0:
        if risk / entry_mid * 100 <= 8:
            quality_pts += 1

    # Gap held (not faded)
    if gap_fill and price > gap_fill:
        quality_pts += 1

    if quality_pts >= 5:
        result["entry_quality"] = "EXCELLENT"
    elif quality_pts >= 3:
        result["entry_quality"] = "GOOD"
    elif quality_pts >= 2:
        result["entry_quality"] = "FAIR"
    else:
        result["entry_quality"] = "POOR"

    result["entry_quality_score"] = quality_pts
    result["entry_notes"] = notes

    return result


# ── TINY TITANS QUALITY SCORE ──────────────────────────────────────────────

def score_tiny_titans(fund: dict) -> dict:
    """
    Score stock on Tiny Titans quality criteria (0-7).
    Market cap <$3B, Net Debt/EBITDA <3, no dilution, margin >10%,
    ROIC >15%, revenue CAGR >9%, EPS growth >11%.
    """
    criteria = {}
    mc = fund.get("market_cap")
    criteria["small_cap"] = {
        "met": mc is not None and mc < 3e9,
        "value": f"${mc/1e9:.1f}B" if mc else "N/A",
        "threshold": "< $3B",
    }
    nd = fund.get("net_debt_ebitda")
    criteria["low_debt"] = {
        "met": nd is not None and nd < 3,
        "value": f"{nd:.1f}x" if nd is not None else "N/A",
        "threshold": "< 3x",
    }
    no_dil = fund.get("no_dilution")
    dil_pct = fund.get("dilution_pct")
    criteria["no_dilution"] = {
        "met": no_dil is True,
        "value": f"{dil_pct:+.1f}%" if dil_pct is not None else "N/A",
        "threshold": "< 5% increase",
    }
    npm = fund.get("net_profit_margin")
    criteria["profit_margin"] = {
        "met": npm is not None and npm > 10,
        "value": f"{npm:.1f}%" if npm is not None else "N/A",
        "threshold": "> 10%",
    }
    roic = fund.get("roic")
    criteria["high_roic"] = {
        "met": roic is not None and roic > 15,
        "value": f"{roic:.1f}%" if roic is not None else "N/A",
        "threshold": "> 15%",
    }
    rev_cagr = fund.get("revenue_cagr")
    criteria["revenue_growth"] = {
        "met": rev_cagr is not None and rev_cagr > 9,
        "value": f"{rev_cagr:.1f}%/yr" if rev_cagr is not None else "N/A",
        "threshold": "> 9%/yr",
    }
    eps_g = fund.get("eps_growth_yoy")
    earnings_g = fund.get("earnings_growth")
    eps_val = round(earnings_g * 100, 1) if earnings_g is not None else eps_g
    criteria["eps_growth"] = {
        "met": eps_val is not None and eps_val > 11,
        "value": f"{eps_val:.1f}%" if eps_val is not None else "N/A",
        "threshold": "> 11%",
    }
    score = sum(1 for c in criteria.values() if c["met"])
    data_available = sum(1 for c in criteria.values() if c["value"] != "N/A")
    return {
        "tt_score": score,
        "tt_max": 7,
        "tt_data_available": data_available,
        "tt_criteria": criteria,
        "tt_quality": "HIGH" if score >= 5 else "MEDIUM" if score >= 3 else "LOW",
    }


# ── CONVICTION TIER CLASSIFICATION (Kelly-validated) ──────────────────────

def classify_conviction_tier(signal: dict, bars_data: dict = None,
                              config: dict = None) -> dict:
    """
    Kelly-validated conviction tiers (5yr walk-forward, 1663 trades OOS).

    TIER 1 MAX  (3x size, half-Kelly 15-26%): Gap30+ micro OR Gap20+ TI65-strong
    TIER 2 STRONG (2x size, half-Kelly 9-10%): Gap50+ any OR micro+neglected+gap20 OR TT>=5
    TIER 3 NORMAL (1x size, half-Kelly 4%): Vol5x+ gap20+ OR Vol10x+ any
    WATCHLIST: everything else — shown separately, not actionable
    """
    cfg = {**EP_CONFIG, **(config or {})}

    gap_pct = signal.get("gap_pct") or signal.get("ep_gap_pct", 0)
    ticker = signal.get("ticker", "")
    price = signal.get("price", 0)
    ep_day_low = signal.get("ep_day_low") or signal.get("day_low", 0)
    vol_ratio = signal.get("ep_vol_ratio") or signal.get("vol_ratio", 1)
    ti65_label = signal.get("ti65_label", "N/A")
    tt_score = signal.get("tt_score", 0)
    lynch_score = signal.get("lynch_score", 0)
    analyst_count = signal.get("analyst_count") or 0

    # Dollar volume for micro-cap check
    dollar_vol = 0
    if bars_data and ticker in bars_data:
        df = bars_data[ticker]
        if df is not None and len(df) >= 50:
            dollar_vol = float(
                (df["close"].iloc[-50:] * df["volume"].iloc[-50:]).mean()
            )
    if dollar_vol == 0:
        dollar_vol = signal.get("avg_dollar_vol", signal.get("dollar_vol", 0))

    is_micro = dollar_vol < cfg["tier_max_dollar_vol"]
    is_neglected = analyst_count <= 2

    # Stop and exit strategy
    stop_price = round(ep_day_low * 0.99, 2) if ep_day_low else round(price * 0.85, 2)
    stop_dist_pct = round((price - stop_price) / price * 100, 1) if price > 0 else 0
    be_trigger = cfg["exit_be_trigger_pct"]
    trail_pct = cfg["exit_trail_pct"]

    exit_strategy = {
        "be_trigger_pct": be_trigger,
        "trail_pct": trail_pct,
        "stop_price": stop_price,
        "stop_dist_pct": stop_dist_pct,
        "description": (
            f"Initial stop: ${stop_price} ({stop_dist_pct}% below entry). "
            f"After +{be_trigger}% gain, move stop to breakeven. "
            f"Then trail {trail_pct}% from highest close."
        ),
    }

    base = {
        "exit_strategy": exit_strategy,
        "dollar_vol": round(dollar_vol),
        "is_micro": is_micro,
    }

    # ── TIER 1 MAX — half-Kelly 15-26%, 3x position ──────────────
    # Gap 30%+ micro-cap (PF 3.74, 56% WR) OR Gap 20%+ with TI65 STRONG
    if (gap_pct >= cfg["tier1_gap_micro"] and is_micro) or \
       (gap_pct >= cfg["tier1_gap_ti65"] and ti65_label == "STRONG"):
        reason = "micro gap30+" if (gap_pct >= cfg["tier1_gap_micro"] and is_micro) \
                 else "gap20+ TI65-STRONG"
        return {
            **base,
            "conviction_tier": 1,
            "tier_label": "MAX BET",
            "tier_color": "#d4af37",
            "tier_sizing": "3x",
            "half_kelly_pct": "15-26%",
            "tier_reason": reason,
            "tier_description": f"MAX: {reason} | half-Kelly 15-26% | 3x size",
            "position_sizing": {
                "risk_pct": cfg["default_risk_pct"] * 3,
                "stop_price": stop_price,
                "stop_dist_pct": stop_dist_pct,
                "description": f"3x base risk. Stop ${stop_price} ({stop_dist_pct}%).",
            },
        }

    # ── TIER 2 STRONG — half-Kelly 9-10%, 2x position ────────────
    # Gap 50%+ any stock, OR micro+neglected+gap20, OR Tiny Titans >= 5
    if (gap_pct >= cfg["tier2_gap_any"]) or \
       (is_micro and is_neglected and gap_pct >= cfg["tier2_gap_micro_neglected"]) or \
       (tt_score >= cfg["tier2_tt_score"]):
        if gap_pct >= cfg["tier2_gap_any"]:
            reason = f"gap{gap_pct:.0f}%"
        elif tt_score >= cfg["tier2_tt_score"]:
            reason = f"TinyTitans {tt_score}/7"
        else:
            reason = "micro+neglected+gap20"
        return {
            **base,
            "conviction_tier": 2,
            "tier_label": "STRONG",
            "tier_color": "#ff6d00",
            "tier_sizing": "2x",
            "half_kelly_pct": "9-10%",
            "tier_reason": reason,
            "tier_description": f"STRONG: {reason} | half-Kelly 9-10% | 2x size",
            "position_sizing": {
                "risk_pct": cfg["default_risk_pct"] * 2,
                "stop_price": stop_price,
                "stop_dist_pct": stop_dist_pct,
                "description": f"2x base risk. Stop ${stop_price} ({stop_dist_pct}%).",
            },
        }

    # ── TIER 3 NORMAL — half-Kelly 4%, 1x position ───────────────
    # Vol 5x+ with gap 20%+, OR Vol 10x+ any gap
    if (vol_ratio >= 5 and gap_pct >= cfg["tier3_gap_vol5x"]) or \
       (vol_ratio >= cfg["tier3_vol_any"]):
        reason = f"vol{vol_ratio:.0f}x gap{gap_pct:.0f}%" if gap_pct >= 20 \
                 else f"vol{vol_ratio:.0f}x"
        return {
            **base,
            "conviction_tier": 3,
            "tier_label": "NORMAL",
            "tier_color": "#2d7a3a",
            "tier_sizing": "1x",
            "half_kelly_pct": "4%",
            "tier_reason": reason,
            "tier_description": f"NORMAL: {reason} | half-Kelly 4% | 1x size",
            "position_sizing": {
                "risk_pct": cfg["default_risk_pct"],
                "stop_price": stop_price,
                "stop_dist_pct": stop_dist_pct,
                "description": f"1x base risk. Stop ${stop_price} ({stop_dist_pct}%).",
            },
        }

    # ── WATCHLIST — not actionable ────────────────────────────────
    return {
        **base,
        "conviction_tier": 0,
        "tier_label": "WATCHLIST",
        "tier_color": "#666",
        "tier_sizing": "0x",
        "half_kelly_pct": "0%",
        "tier_reason": "below threshold",
        "tier_description": "Does not meet Kelly filter criteria — watch only",
        "position_sizing": {
            "risk_pct": 0,
            "stop_price": stop_price,
            "stop_dist_pct": stop_dist_pct,
            "description": "No position — watchlist only.",
        },
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

            # ── Tiny Titans fields ──────────────────────────────────
            # Net profit margin
            net_income = info.get("netIncomeToCommon")
            revenue_total = info.get("totalRevenue")
            if net_income and revenue_total and revenue_total > 0:
                fund["net_profit_margin"] = round(net_income / revenue_total * 100, 1)

            # ROIC proxy (ROE from yfinance)
            roe = info.get("returnOnEquity")
            if roe is not None:
                fund["roic"] = round(roe * 100, 1)

            # Net Debt / EBITDA
            total_debt = info.get("totalDebt", 0) or 0
            cash = info.get("totalCash", 0) or 0
            ebitda = info.get("ebitda")
            net_debt = total_debt - cash
            if ebitda and ebitda > 0:
                fund["net_debt_ebitda"] = round(net_debt / ebitda, 2)

            # Revenue CAGR + EPS growth + dilution (from financials/balance sheet)
            try:
                tk = yf.Ticker(ticker)
                financials = tk.financials
                if financials is not None and not financials.empty:
                    rev_row = None
                    for idx in financials.index:
                        if "revenue" in str(idx).lower() or "total revenue" in str(idx).lower():
                            rev_row = financials.loc[idx]
                            break
                    if rev_row is not None:
                        revs = [float(v) for v in rev_row.values if pd.notna(v) and v > 0]
                        if len(revs) >= 2:
                            newest, oldest, years = revs[0], revs[-1], len(revs) - 1
                            if oldest > 0 and years > 0:
                                fund["revenue_cagr"] = round(((newest / oldest) ** (1 / years) - 1) * 100, 1)

                # EPS growth
                try:
                    earnings = tk.earnings_history
                    if earnings is not None and not earnings.empty and "epsActual" in earnings.columns:
                        eps_vals = earnings["epsActual"].dropna().tolist()
                        if len(eps_vals) >= 4:
                            recent, year_ago = eps_vals[-1], eps_vals[-4]
                            if year_ago > 0:
                                fund["eps_growth_yoy"] = round((recent - year_ago) / abs(year_ago) * 100, 1)
                except Exception:
                    pass

                # Shares dilution (current vs 3yr ago)
                try:
                    bs = tk.balance_sheet
                    if bs is not None and not bs.empty:
                        shares_row = None
                        for idx in bs.index:
                            if "share" in str(idx).lower() and "outstanding" in str(idx).lower():
                                shares_row = bs.loc[idx]
                                break
                            if "ordinary" in str(idx).lower() and "share" in str(idx).lower():
                                shares_row = bs.loc[idx]
                                break
                        if shares_row is not None:
                            s_vals = [float(v) for v in shares_row.values if pd.notna(v) and v > 0]
                            if len(s_vals) >= 2:
                                dil = (s_vals[0] - s_vals[-1]) / s_vals[-1] * 100
                                fund["dilution_pct"] = round(dil, 1)
                                fund["no_dilution"] = dil <= 5
                except Exception:
                    pass
            except Exception:
                pass

            # Revenue growth quarters (for sales acceleration)
            # Build from quarterly financials if available
            try:
                if 'tk' not in dir():
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

            # Company name, sector, and asset type for filtering
            fund["company_name"] = info.get("shortName") or info.get("longName") or ""
            fund["sector"] = info.get("sector") or ""
            fund["industry"] = info.get("industry") or ""
            fund["quoteType"] = info.get("quoteType", "EQUITY")

            # Recent news headlines for catalyst classification
            try:
                news_items = tk.news if 'tk' in dir() else yf.Ticker(ticker).news
                if news_items:
                    fund["news"] = [
                        {"title": n.get("title", ""), "publisher": n.get("publisher", ""),
                         "date": n.get("providerPublishTime", "")}
                        for n in news_items[:5]
                    ]
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


# ── 2LYNCH CHECKLIST SCORING ─────────────────────────────────────────────────

def calculate_lynch_score(df: pd.DataFrame, fundamentals: dict = None,
                          config: dict = None) -> dict:
    """
    Stockbee 2LYNCH checklist for momentum burst setups (0-6).

    Criteria:
      L — Leader in sector (above 50MA + relative strength)
      Y — Young uptrend (EMA10 > EMA20 > EMA50, trending < 6 months)
      N — Neglected / under-followed (< 10 analysts)
      C — Consolidation (tight range near EMA, volume drying up)
      H — High volume breakout (today's vol > 1.5x average)
      2 — 2x earnings or revenue acceleration (growth doubling QoQ)
    """
    cfg = {**EP_CONFIG, **(config or {})}
    fund = fundamentals or {}
    result = {"lynch_score": 0, "lynch_details": {}, "lynch_color": "red"}

    if df is None or len(df) < 50:
        return result

    closes = df["close"]
    volumes = df["volume"]
    highs = df["high"]
    lows = df["low"]
    price = float(closes.iloc[-1])
    n = len(df)

    details = {}

    # L — Leader: above 50MA and outperforming (price > 50MA and near 52w high)
    ma50 = float(closes.iloc[-50:].mean())
    w52_high = float(highs.iloc[-min(252, n):].max())
    pct_from_high = (w52_high - price) / w52_high * 100 if w52_high > 0 else 99
    l_met = price > ma50 and pct_from_high <= 15
    details["L"] = {
        "met": l_met,
        "label": "Leader",
        "reason": f"{'Above' if price > ma50 else 'Below'} 50MA, {pct_from_high:.1f}% from 52w high",
    }

    # Y — Young uptrend: EMA stack aligned, trending < 6 months
    ema10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
    ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
    ema_aligned = ema10 > ema20 > ema50
    # Check if trend is "young" — price was below 50MA within last 130 days (~6 months)
    ma50_series = closes.rolling(50).mean()
    recent_below = False
    if len(ma50_series) >= 130:
        for j in range(-130, -10):
            if float(closes.iloc[j]) < float(ma50_series.iloc[j]):
                recent_below = True
                break
    else:
        recent_below = True  # short history = young by default
    y_met = ema_aligned and recent_below
    details["Y"] = {
        "met": y_met,
        "label": "Young uptrend",
        "reason": f"EMA stack {'aligned' if ema_aligned else 'NOT aligned'}, "
                  f"{'young' if recent_below else 'mature'} trend",
    }

    # N — Neglected
    analyst_count = fund.get("analyst_count")
    n_met = analyst_count is not None and analyst_count < cfg["magna_analyst_count_max"]
    if analyst_count is None:
        market_cap = fund.get("market_cap")
        n_met = market_cap is not None and market_cap < 2e9
    details["N"] = {
        "met": n_met,
        "label": "Neglected",
        "reason": f"{analyst_count} analysts" if analyst_count is not None else "Unknown coverage",
    }

    # C — Consolidation: tight range + volume drying up
    consol_bars = 5
    recent_range = (float(highs.iloc[-consol_bars:].max()) - float(lows.iloc[-consol_bars:].min())) / price * 100
    avg_vol_20 = float(volumes.iloc[-20:].mean()) if n >= 20 else float(volumes.mean())
    recent_vol = float(volumes.iloc[-consol_bars:].mean())
    vol_drying = recent_vol < avg_vol_20 * 0.7 if avg_vol_20 > 0 else False
    c_met = recent_range <= 5.0 and vol_drying
    details["C"] = {
        "met": c_met,
        "label": "Consolidation",
        "reason": f"Range {recent_range:.1f}%, vol {'drying' if vol_drying else 'not drying'}",
    }

    # H — High volume breakout
    today_vol = float(volumes.iloc[-1])
    h_met = today_vol > avg_vol_20 * 1.5 if avg_vol_20 > 0 else False
    details["H"] = {
        "met": h_met,
        "label": "High volume",
        "reason": f"Today {today_vol / avg_vol_20:.1f}x avg" if avg_vol_20 > 0 else "N/A",
    }

    # 2 — 2x earnings/revenue acceleration
    rev_quarters = fund.get("revenue_growth_quarters", [])
    two_met = False
    if len(rev_quarters) >= 2 and rev_quarters[0] is not None and rev_quarters[1] is not None:
        if rev_quarters[1] > 0 and rev_quarters[0] >= rev_quarters[1] * 2:
            two_met = True
    earnings_surprise = fund.get("earnings_surprise_pct")
    if earnings_surprise is not None and earnings_surprise >= 100:
        two_met = True
    details["2"] = {
        "met": two_met,
        "label": "2x acceleration",
        "reason": f"Rev trend: {rev_quarters[:3]}" if rev_quarters else "No data",
    }

    score = sum(1 for d in details.values() if d["met"])
    color = "green" if score >= 5 else "yellow" if score >= 3 else "red"

    return {"lynch_score": score, "lynch_details": details, "lynch_color": color}


# ── BAG HOLDER PROTECTION ───────────────────────────────────────────────────

def detect_bag_holder_risk(df: pd.DataFrame, config: dict = None) -> dict:
    """
    Flag stocks up 3+ consecutive days — chasing risk.

    Returns:
        bag_holder_risk: bool
        consecutive_up_days: int
        warning: str or None
    """
    cfg = {**EP_CONFIG, **(config or {})}
    threshold = cfg["bag_holder_consec_up_days"]
    result = {"bag_holder_risk": False, "consecutive_up_days": 0, "bag_holder_warning": None}

    if df is None or len(df) < 2:
        return result

    closes = df["close"]
    consec = 0
    for i in range(len(closes) - 1, 0, -1):
        if float(closes.iloc[i]) > float(closes.iloc[i - 1]):
            consec += 1
        else:
            break

    result["consecutive_up_days"] = consec
    if consec >= threshold:
        result["bag_holder_risk"] = True
        result["bag_holder_warning"] = f"BAG HOLDER RISK — do not chase ({consec} consecutive up days)"

    return result


# ── TI65 TREND INTENSITY ────────────────────────────────────────────────────

def calculate_ti65(df: pd.DataFrame, config: dict = None) -> dict:
    """
    TI65: 65-day price momentum filter.

    Returns:
        ti65_value: float (% change over 65 days)
        ti65_confirmed: bool (above minimum threshold)
        ti65_label: str
    """
    cfg = {**EP_CONFIG, **(config or {})}
    period = cfg["ti65_period"]
    min_pct = cfg["ti65_min_pct"]
    result = {"ti65_value": None, "ti65_confirmed": False, "ti65_label": "N/A"}

    if df is None or len(df) < period + 1:
        return result

    closes = df["close"]
    price_now = float(closes.iloc[-1])
    price_then = float(closes.iloc[-period - 1])

    if price_then <= 0:
        return result

    ti65 = (price_now - price_then) / price_then * 100
    confirmed = ti65 >= min_pct

    if ti65 >= 30:
        label = "STRONG"
    elif ti65 >= min_pct:
        label = "CONFIRMED"
    elif ti65 >= 0:
        label = "WEAK"
    else:
        label = "DOWNTREND"

    return {
        "ti65_value": round(ti65, 1),
        "ti65_confirmed": confirmed,
        "ti65_label": label,
    }


# ── ANTS PATTERN DETECTION ──────────────────────────────────────────────────

def detect_ants_pattern(df: pd.DataFrame, config: dict = None) -> dict:
    """
    Ants: 3+ days of tight (<1.5%) daily range followed by a narrow (<0.3%) day.
    Pre-breakout compression pattern.

    Returns:
        ants_detected: bool
        ants_tight_days: int (count of qualifying tight days)
        ants_narrow_day_range: float (range % of final narrow day)
        ants_details: str
    """
    cfg = {**EP_CONFIG, **(config or {})}
    min_tight = cfg["ants_tight_days"]
    tight_pct = cfg["ants_tight_range_pct"]
    narrow_pct = cfg["ants_narrow_day_pct"]
    result = {"ants_detected": False, "ants_tight_days": 0,
              "ants_narrow_day_range": None, "ants_details": None}

    if df is None or len(df) < min_tight + 2:
        return result

    highs = df["high"]
    lows = df["low"]
    closes = df["close"]
    n = len(df)

    # Check the last bar for narrow day
    last_high = float(highs.iloc[-1])
    last_low = float(lows.iloc[-1])
    last_close = float(closes.iloc[-1])
    if last_close <= 0:
        return result

    last_range_pct = (last_high - last_low) / last_close * 100

    # Count consecutive tight days before the last bar
    tight_count = 0
    for i in range(n - 2, max(n - 15, 0) - 1, -1):  # scan up to 15 bars back
        h = float(highs.iloc[i])
        l = float(lows.iloc[i])
        c = float(closes.iloc[i])
        if c <= 0:
            break
        day_range = (h - l) / c * 100
        if day_range <= tight_pct:
            tight_count += 1
        else:
            break

    result["ants_tight_days"] = tight_count
    result["ants_narrow_day_range"] = round(last_range_pct, 2)

    if tight_count >= min_tight and last_range_pct <= narrow_pct:
        result["ants_detected"] = True
        result["ants_details"] = (
            f"{tight_count} tight days (<{tight_pct}% range) + "
            f"narrow day ({last_range_pct:.2f}%) — pre-breakout compression"
        )

    return result


# ── OPENING RANGE VOLUME CHECK ──────────────────────────────────────────────

def check_opening_range_volume(df: pd.DataFrame, intraday_df: pd.DataFrame = None,
                               config: dict = None) -> dict:
    """
    Check if a stock trades its full average daily volume in the first 15-20 min.
    Flag as 'MASSIVE VOLUME' if yes.

    Args:
        df: Daily OHLCV bars
        intraday_df: Optional intraday bars (1-min or 5-min) with volume.
                     If not available, estimates from daily bar shape.
        config: Override thresholds

    Returns:
        or_massive_volume: bool
        or_volume_pct_of_adv: float (% of ADV in opening range)
        or_label: str
    """
    cfg = {**EP_CONFIG, **(config or {})}
    result = {"or_massive_volume": False, "or_volume_pct_of_adv": None, "or_label": None}

    if df is None or len(df) < 20:
        return result

    volumes = df["volume"]
    adv_50 = float(volumes.iloc[-50:].mean()) if len(volumes) >= 50 else float(volumes.mean())
    if adv_50 <= 0:
        return result

    today_vol = float(volumes.iloc[-1])

    # If we have intraday data, use actual opening range volume
    if intraday_df is not None and len(intraday_df) > 0:
        try:
            minutes = cfg["or_vol_check_minutes"]
            # Assume intraday_df is sorted by time, take first N minutes
            or_bars = intraday_df.head(minutes)  # 1-min bars
            if len(or_bars) == 0:
                or_bars = intraday_df.head(minutes // 5)  # 5-min bars
            or_vol = float(or_bars["volume"].sum())
        except Exception:
            or_vol = None
    else:
        # Estimate: if today's total volume is already > ADV and it's early,
        # or if volume ratio suggests front-loaded day.
        # Heuristic: on gap days, ~40-60% of volume trades in first 30 min.
        # If total day vol > 2x ADV, opening range likely had full ADV.
        if today_vol >= adv_50 * 2:
            or_vol = adv_50  # conservative estimate: at least 1x ADV in OR
        else:
            or_vol = today_vol * 0.4  # typical OR is ~40% of daily vol

    if or_vol is None:
        return result

    pct_of_adv = or_vol / adv_50 * 100

    result["or_volume_pct_of_adv"] = round(pct_of_adv, 1)
    if pct_of_adv >= cfg["or_vol_adv_pct"]:
        result["or_massive_volume"] = True
        result["or_label"] = "MASSIVE VOLUME"

    return result


# ── QUARTERLY EARNINGS WEIGHTING ─────────────────────────────────────────────

def weighted_growth_score(fundamentals: dict, config: dict = None) -> dict:
    """
    Weight quarterly growth with most recent quarter at 40%, older at 20% each.

    Returns:
        weighted_growth: float (weighted average growth %)
        growth_trend: 'accelerating' | 'decelerating' | 'stable' | 'insufficient'
        growth_quarters: list of {quarter, growth, weight}
    """
    cfg = {**EP_CONFIG, **(config or {})}
    weights = [
        cfg["earnings_weight_q1"],
        cfg["earnings_weight_q2"],
        cfg["earnings_weight_q3"],
        cfg["earnings_weight_q4"],
    ]

    result = {"weighted_growth": None, "growth_trend": "insufficient", "growth_quarters": []}

    rev_quarters = fundamentals.get("revenue_growth_quarters", [])
    if not rev_quarters or len(rev_quarters) < 2:
        return result

    # Pad with None if fewer than 4 quarters
    padded = (rev_quarters + [None] * 4)[:4]

    total_weight = 0
    weighted_sum = 0
    quarter_details = []

    for i, (growth, weight) in enumerate(zip(padded, weights)):
        label = f"Q{i + 1}"
        if growth is not None:
            weighted_sum += growth * weight
            total_weight += weight
            quarter_details.append({"quarter": label, "growth": growth, "weight": weight})
        else:
            quarter_details.append({"quarter": label, "growth": None, "weight": weight})

    result["growth_quarters"] = quarter_details

    if total_weight > 0:
        result["weighted_growth"] = round(weighted_sum / total_weight, 1)

    # Determine trend from available data
    valid = [g for g in rev_quarters if g is not None]
    if len(valid) >= 2:
        if all(valid[i] >= valid[i + 1] for i in range(len(valid) - 1)):
            result["growth_trend"] = "accelerating"
        elif all(valid[i] <= valid[i + 1] for i in range(len(valid) - 1)):
            result["growth_trend"] = "decelerating"
        else:
            result["growth_trend"] = "stable"

    return result


# ── DO NOT BUY FILTER ────────────────────────────────────────────────────────

def check_do_not_buy(df: pd.DataFrame, config: dict = None) -> dict:
    """
    Automatic 'Do Not Buy' filter. Flags:
      1. Stocks up 3+ consecutive days
      2. Stocks extended >30% above 50-day MA
      3. Stocks with declining volume on up days

    Returns:
        do_not_buy: bool
        dnb_reasons: list of str
        dnb_flags: dict with individual flag booleans
    """
    cfg = {**EP_CONFIG, **(config or {})}
    result = {"do_not_buy": False, "dnb_reasons": [], "dnb_flags": {}}

    if df is None or len(df) < 10:
        return result

    closes = df["close"]
    volumes = df["volume"]
    n = len(df)
    price = float(closes.iloc[-1])
    reasons = []
    flags = {}

    # 1. Consecutive up days
    consec_up = 0
    for i in range(n - 1, 0, -1):
        if float(closes.iloc[i]) > float(closes.iloc[i - 1]):
            consec_up += 1
        else:
            break
    flags["consecutive_up"] = consec_up >= cfg["dnb_consec_up_days"]
    if flags["consecutive_up"]:
        reasons.append(f"Up {consec_up} consecutive days — chasing risk")

    # 2. Extended above 50MA
    if n >= 50:
        ma50 = float(closes.iloc[-50:].mean())
        if ma50 > 0:
            pct_above = (price - ma50) / ma50 * 100
            flags["extended_above_50ma"] = pct_above >= cfg["dnb_extended_above_50ma_pct"]
            if flags["extended_above_50ma"]:
                reasons.append(f"Extended {pct_above:.0f}% above 50MA — mean reversion risk")
        else:
            flags["extended_above_50ma"] = False
    else:
        flags["extended_above_50ma"] = False

    # 3. Declining volume on up days (last 5 bars)
    check_days = cfg["dnb_vol_decline_days"]
    up_day_vols = []
    for i in range(n - 1, max(n - 10, 0), -1):
        if float(closes.iloc[i]) > float(closes.iloc[i - 1]):
            up_day_vols.append(float(volumes.iloc[i]))
        if len(up_day_vols) >= check_days:
            break

    declining_vol = False
    if len(up_day_vols) >= check_days:
        # Check if each subsequent up day has lower volume
        declining_vol = all(up_day_vols[i] > up_day_vols[i + 1]
                          for i in range(len(up_day_vols) - 1))
    flags["declining_vol_on_up"] = declining_vol
    if declining_vol:
        reasons.append(f"Volume declining on last {len(up_day_vols)} up days — weak buying")

    result["do_not_buy"] = len(reasons) > 0
    result["dnb_reasons"] = reasons
    result["dnb_flags"] = flags

    return result


# ── SHORT EP DETECTION ────────────────────────────────────────────────────────

def classify_news_catalyst(fund: dict) -> dict:
    """
    Classify EP catalyst from recent yfinance news headlines.

    Parses headline keywords to identify:
    - EARNINGS: beat/miss, EPS, revenue, quarterly results
    - GUIDANCE: raised/lowered guidance, outlook, forecast
    - ANALYST: upgrade/downgrade, price target
    - CONTRACT: deal, partnership, acquisition, FDA
    - OFFERING: secondary, dilution, shelf registration
    - UNKNOWN: no clear catalyst identified

    Returns dict with catalyst_type, catalyst_headline, catalyst_tags.
    """
    result = {
        "news_catalyst": "UNKNOWN",
        "news_headline": "",
        "news_tags": [],
        "news_publisher": "",
    }

    news = fund.get("news", [])
    if not news:
        return result

    # Keyword groups (checked in priority order)
    CATALYST_KEYWORDS = {
        "EARNINGS": [
            "earnings", "EPS", "quarterly results", "revenue beat",
            "profit", "net income", "beats estimates", "misses estimates",
            "quarterly report", "fiscal Q", "beats consensus",
        ],
        "GUIDANCE": [
            "guidance", "outlook", "forecast", "raises full-year",
            "lowers guidance", "raises guidance", "revised outlook",
            "full-year", "annual forecast",
        ],
        "FDA": [
            "FDA", "approval", "breakthrough", "phase 3", "phase 2",
            "clinical trial", "drug approval", "PDUFA", "NDA",
        ],
        "ANALYST": [
            "upgrade", "downgrade", "price target", "initiates coverage",
            "overweight", "underweight", "buy rating", "outperform",
        ],
        "CONTRACT": [
            "contract", "deal", "partnership", "acquisition", "merger",
            "awarded", "selected", "billion-dollar", "agreement",
        ],
        "OFFERING": [
            "offering", "secondary", "dilution", "shelf registration",
            "stock sale", "public offering", "ATM",
        ],
    }

    for article in news[:5]:
        title = article.get("title", "")
        title_lower = title.lower()

        for catalyst_type, keywords in CATALYST_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    result["news_catalyst"] = catalyst_type
                    result["news_headline"] = title[:120]
                    result["news_publisher"] = article.get("publisher", "")
                    result["news_tags"].append(catalyst_type)

                    # Return on first strong match
                    if catalyst_type in ("EARNINGS", "FDA", "GUIDANCE"):
                        return result

    # If we found tags but no strong match, use the first one
    if result["news_tags"] and result["news_catalyst"] == "UNKNOWN":
        result["news_catalyst"] = result["news_tags"][0]

    # If still unknown but we have headlines, use top headline
    if result["news_catalyst"] == "UNKNOWN" and news:
        result["news_headline"] = news[0].get("title", "")[:120]
        result["news_publisher"] = news[0].get("publisher", "")

    return result


def _classify_short_catalyst(fund: dict) -> dict:
    """
    Classify the catalyst driving a gap-down EP.

    Returns:
        catalyst_type: str — EARNINGS_MISS | GUIDANCE_CUT | DOWNGRADE |
                              ACCOUNTING | REGULATORY | UNKNOWN
        catalyst_label: str — human-readable description
        catalyst_severity: int — 1 (mild) to 3 (severe)
    """
    result = {"catalyst_type": "UNKNOWN", "catalyst_label": "Unknown catalyst",
              "catalyst_severity": 1}

    # Earnings miss: negative earnings surprise
    earnings_surp = fund.get("earnings_surprise_pct")
    if earnings_surp is not None and earnings_surp < -5:
        result["catalyst_type"] = "EARNINGS_MISS"
        result["catalyst_label"] = f"Earnings miss {earnings_surp:+.0f}%"
        result["catalyst_severity"] = 3 if earnings_surp < -20 else 2
        return result

    # Guidance cut: forward PE much higher than trailing (lowered estimates)
    forward_pe = fund.get("forward_pe")
    trailing_pe = fund.get("trailing_pe")
    if forward_pe and trailing_pe and forward_pe > trailing_pe * 1.3:
        result["catalyst_type"] = "GUIDANCE_CUT"
        result["catalyst_label"] = "Forward estimates cut (PE expansion)"
        result["catalyst_severity"] = 2
        return result

    # Downgrade: recommendation is sell/underperform
    rec = fund.get("recommendation_key") or fund.get("recommendationKey")
    if rec and rec.lower() in ("sell", "strong_sell", "underperform"):
        result["catalyst_type"] = "DOWNGRADE"
        result["catalyst_label"] = f"Analyst rating: {rec}"
        result["catalyst_severity"] = 2
        return result

    # Declining revenue (proxy for accounting/structural issues)
    rev_q1 = fund.get("revenue_growth_q1")
    rev_growth = fund.get("revenue_growth")
    if rev_q1 is not None and rev_q1 < -10:
        result["catalyst_type"] = "ACCOUNTING"
        result["catalyst_label"] = f"Revenue decline {rev_q1:+.0f}%"
        result["catalyst_severity"] = 2
        return result
    if rev_growth is not None and rev_growth < -0.1:
        result["catalyst_type"] = "ACCOUNTING"
        result["catalyst_label"] = f"Revenue decline {rev_growth*100:+.0f}%"
        result["catalyst_severity"] = 2
        return result

    return result


def calculate_short_magna_score(ticker: str, df: pd.DataFrame,
                                 fund: dict, config: dict = None) -> dict:
    """
    MAGNA score for SHORT setups (0-6). Higher = better short candidate.

    Criteria:
      I — Institutional ownership >= 60% (institutions dumping)
      S — Short interest already building (>= 10%)
      R — Revenue declining 2+ consecutive quarters
      D — Price below 200-day MA (downtrend confirmed)
      V — Volume surge on gap-down day (3x+ avg = panic selling)
      C — Catalyst severity >= 2 (not just noise)
    """
    cfg = {**EP_CONFIG, **(config or {})}
    score = 0
    details = {}

    # I — Institutional ownership
    inst_own = fund.get("institutional_ownership") or fund.get("heldPercentInstitutions")
    if inst_own is not None:
        inst_pct = inst_own * 100 if inst_own < 1 else inst_own
    else:
        inst_pct = None
    met = inst_pct is not None and inst_pct >= cfg["short_magna_inst_own_min"]
    if met:
        score += 1
    details["I"] = {
        "met": met,
        "reason": f"Institutional {inst_pct:.0f}%" if inst_pct else "N/A",
        "label": "Institutional Ownership",
    }

    # S — Short interest building
    short_pct = fund.get("short_pct_float")
    met = short_pct is not None and short_pct >= cfg["short_magna_short_int_min"]
    if met:
        score += 1
    details["S"] = {
        "met": met,
        "reason": f"Short interest {short_pct:.1f}%" if short_pct else "N/A",
        "label": "Short Interest Building",
    }

    # R — Revenue declining 2+ quarters
    rev_quarters = fund.get("revenue_growth_quarters", [])
    declining_count = sum(1 for r in rev_quarters if r is not None and r < 0)
    met = declining_count >= cfg["short_magna_rev_decline_qtrs"]
    if met:
        score += 1
    details["R"] = {
        "met": met,
        "reason": f"{declining_count} declining quarters" if rev_quarters else "N/A",
        "label": "Revenue Decline",
    }

    # D — Price below 200-day MA
    below_200ma = False
    if df is not None and len(df) >= 200:
        price = float(df["close"].iloc[-1])
        ma200 = float(df["close"].iloc[-200:].mean())
        below_200ma = price < ma200
    elif df is not None and len(df) >= 50:
        price = float(df["close"].iloc[-1])
        ma50 = float(df["close"].iloc[-50:].mean())
        below_200ma = price < ma50  # fallback to 50MA
    if below_200ma:
        score += 1
    details["D"] = {
        "met": below_200ma,
        "reason": "Below 200MA" if below_200ma else "Above 200MA",
        "label": "Downtrend Confirmed",
    }

    # V — Volume surge (checked at signal level, pass as fund field)
    vol_ratio = fund.get("_short_vol_ratio", 1)
    met = vol_ratio >= 3
    if met:
        score += 1
    details["V"] = {
        "met": met,
        "reason": f"Volume {vol_ratio:.1f}x avg",
        "label": "Panic Volume",
    }

    # C — Catalyst severity
    severity = fund.get("_catalyst_severity", 1)
    met = severity >= 2
    if met:
        score += 1
    details["C"] = {
        "met": met,
        "reason": f"Severity {severity}/3",
        "label": "Catalyst Strength",
    }

    color = "#d32f2f" if score >= 4 else "#ff6d00" if score >= 2 else "#999"

    return {
        "short_magna_score": score,
        "short_magna_max": 6,
        "short_magna_details": details,
        "short_magna_color": color,
    }


def _detect_short_classic_ep(df: pd.DataFrame, cfg: dict, fund: dict) -> dict:
    """
    Short Classic EP: gap DOWN 20%+ on volume 3x+ average.
    Mirror of long classic EP but for shorts.
    """
    empty = {"detected": False}
    try:
        closes = df["close"]
        opens = df["open"]
        volumes = df["volume"]
        highs = df["high"]
        lows = df["low"]
        n = len(df)

        for i in range(max(1, n - 5), n):
            prior_close = float(closes.iloc[i - 1])
            if prior_close <= 0:
                continue

            day_open = float(opens.iloc[i])
            day_close = float(closes.iloc[i])
            day_high = float(highs.iloc[i])
            day_low = float(lows.iloc[i])
            day_vol = float(volumes.iloc[i])

            # Gap DOWN percentage (will be negative)
            gap_pct = (day_open - prior_close) / prior_close * 100

            # Must be a significant gap down
            if gap_pct > cfg["short_ep_gap_pct"]:  # e.g. gap_pct > -20 means skip
                continue

            # Close didn't recover (held at least 50% of the gap down)
            gap_size = prior_close - day_open  # positive number
            if gap_size > 0 and (prior_close - day_close) < gap_size * 0.5:
                continue  # bounced back too much

            # Volume check
            adv_start = max(0, i - 50)
            adv = float(volumes.iloc[adv_start:i].mean()) if i > adv_start else 0
            if adv <= 0:
                continue
            vol_ratio = day_vol / adv

            if vol_ratio < cfg["short_ep_vol_mult"]:
                continue

            # Classify catalyst
            catalyst_info = _classify_short_catalyst(fund)

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
                "prior_close": round(prior_close, 2),
                "days_ago": days_ago,
                "date": date_str,
                **catalyst_info,
                "stop": round(day_high * 1.01, 2),  # stop ABOVE gap day high
                "target": round(day_close * 0.85, 2),  # 15% downside target
            }

    except Exception:
        pass
    return empty


def _detect_short_delayed_ep(df: pd.DataFrame, past_short_eps: list,
                              cfg: dict) -> dict:
    """
    Delayed Short EP: stock gapped down 3-10 days ago, bounced (dead cat),
    now breaking BELOW gap day low on volume.
    """
    empty = {"detected": False}
    try:
        if not past_short_eps:
            return empty

        closes = df["close"]
        volumes = df["volume"]
        lows = df["low"]
        highs = df["high"]
        price = float(closes.iloc[-1])
        today_vol = float(volumes.iloc[-1])
        n = len(df)

        for ep in past_short_eps:
            days_since = ep.get("days_since", 0)
            if days_since < cfg["short_delayed_bounce_min"] or \
               days_since > cfg["short_delayed_bounce_max"]:
                continue

            ep_low = ep.get("ep_day_low", 0)
            ep_high = ep.get("ep_day_high", 0)

            if ep_low <= 0:
                continue

            # Must have bounced from the gap-down low (dead cat bounce)
            # Check if price went above ep_low at some point during bounce
            bounce_high = float(highs.iloc[-(days_since):].max()) if days_since > 0 else 0
            bounce_pct = (bounce_high - ep_low) / ep_low * 100 if ep_low > 0 else 0

            if bounce_pct < 2:  # barely bounced — not a delayed setup
                continue

            # Now breaking below gap day low
            if price >= ep_low:
                continue

            # Volume confirmation
            adv_50 = float(volumes.iloc[-50:].mean()) if n >= 50 else float(volumes.mean())
            breakdown_vol_ratio = today_vol / adv_50 if adv_50 > 0 else 0

            if breakdown_vol_ratio < cfg["short_delayed_vol_mult"]:
                continue

            return {
                "detected": True,
                "days_since_ep": days_since,
                "original_ep_date": ep.get("ep_date"),
                "ep_day_high": ep_high,
                "ep_day_low": ep_low,
                "bounce_high": round(bounce_high, 2),
                "bounce_pct": round(bounce_pct, 1),
                "breakdown_vol_ratio": round(breakdown_vol_ratio, 1),
                "stop": round(bounce_high * 1.01, 2),  # stop above dead cat high
                "target": round(ep_low * 0.85, 2),
            }

    except Exception:
        pass
    return empty


def classify_short_ep_type(df: pd.DataFrame, fund: dict,
                            past_short_eps: list = None,
                            config: dict = None) -> dict:
    """
    Classify short EP type: SHORT_CLASSIC, SHORT_DELAYED, or SHORT_STORY.
    """
    cfg = {**EP_CONFIG, **(config or {})}
    result = {
        "ep_type": None,
        "ep_side": "SHORT",
        "ep_badge": None,
        "ep_badge_color": "#d32f2f",
        "ep_type_details": None,
    }

    # 1. Short Classic EP (gap down 20%+ on 3x vol)
    classic = _detect_short_classic_ep(df, cfg, fund)
    if classic["detected"]:
        result.update({
            "ep_type": "SHORT_CLASSIC",
            "ep_badge": "SHORT EP",
            "ep_type_details": (
                f"Gap down {classic['gap_pct']:.0f}% on {classic['vol_ratio']:.0f}x volume | "
                f"{classic.get('catalyst_label', 'Unknown catalyst')}"
            ),
            **{f"ep_{k}": v for k, v in classic.items() if k != "detected"},
        })
        return result

    # 2. Short Delayed EP (dead cat bounce → breakdown)
    delayed = _detect_short_delayed_ep(df, past_short_eps or [], cfg)
    if delayed["detected"]:
        result.update({
            "ep_type": "SHORT_DELAYED",
            "ep_badge": "SHORT DELAYED",
            "ep_type_details": (
                f"Dead cat bounce {delayed['bounce_pct']:.0f}%, "
                f"now breaking below gap low on {delayed['breakdown_vol_ratio']:.0f}x volume"
            ),
            **{f"ep_{k}": v for k, v in delayed.items() if k != "detected"},
        })
        return result

    # 3. Short Story EP (gap down 15%+ without fundamental backing — hype collapse)
    if df is not None and len(df) >= 10:
        try:
            closes = df["close"]
            opens = df["open"]
            volumes = df["volume"]
            highs = df["high"]
            lows = df["low"]
            n = len(df)

            for i in range(max(1, n - 5), n):
                prior_close = float(closes.iloc[i - 1])
                if prior_close <= 0:
                    continue
                day_open = float(opens.iloc[i])
                gap_pct = (day_open - prior_close) / prior_close * 100

                if gap_pct > cfg["short_ep_story_gap_pct"]:
                    continue

                day_vol = float(volumes.iloc[i])
                adv_start = max(0, i - 50)
                adv = float(volumes.iloc[adv_start:i].mean()) if i > adv_start else 0
                if adv <= 0:
                    continue
                vol_ratio = day_vol / adv
                if vol_ratio < 1.5:
                    continue

                # No severe fundamental catalyst → it's a story/hype unwind
                catalyst_info = _classify_short_catalyst(fund)
                if catalyst_info["catalyst_severity"] >= 2:
                    continue  # Has real fundamentals → already caught by classic

                day_close = float(closes.iloc[i])
                day_high = float(highs.iloc[i])
                day_low = float(lows.iloc[i])
                days_ago = (n - 1) - i
                date_str = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])

                result.update({
                    "ep_type": "SHORT_STORY",
                    "ep_badge": "SHORT STORY",
                    "ep_type_details": (
                        f"Hype unwind — gap down {gap_pct:.0f}% on {vol_ratio:.0f}x volume, "
                        f"no fundamental catalyst"
                    ),
                    "ep_gap_pct": round(gap_pct, 1),
                    "ep_vol_ratio": round(vol_ratio, 1),
                    "ep_day_high": round(day_high, 2),
                    "ep_day_low": round(day_low, 2),
                    "ep_day_open": round(day_open, 2),
                    "ep_day_close": round(day_close, 2),
                    "ep_prior_close": round(prior_close, 2),
                    "ep_days_ago": days_ago,
                    "ep_date": date_str,
                    "ep_stop": round(day_high * 1.01, 2),
                    "ep_target": round(day_close * 0.90, 2),
                    **{f"ep_{k}": v for k, v in catalyst_info.items()},
                })
                return result
        except Exception:
            pass

    return result


def calculate_short_entry_intelligence(df: pd.DataFrame, ep_result: dict,
                                        config: dict = None) -> dict:
    """
    Entry price intelligence for SHORT EP setups — mirror of long but inverted.

    Returns:
        entry_zone_low / entry_zone_high — optimal short entry range
        gap_fill_level — prior close; if price recovers here, short thesis dead
        bounce_resistance — dead cat bounce high (key resistance)
        ema10 / ema20 / ema50 — overhead resistance levels
        atr — 14-day ATR
        stop_price — above gap day high or bounce high
        risk_dollars — stop minus entry mid
        r_levels — 1R, 2R, 3R downside targets
        entry_quality — EXCELLENT / GOOD / FAIR / POOR
        entry_notes — human-readable notes
    """
    cfg = {**EP_CONFIG, **(config or {})}
    result = {
        "entry_zone_low": None, "entry_zone_high": None,
        "gap_fill_level": None, "bounce_resistance": None,
        "ema10": None, "ema20": None, "ema50": None,
        "atr": None, "stop_price": None, "risk_dollars": None,
        "r_levels": {}, "risk_reward": None,
        "entry_quality": "POOR", "entry_notes": [],
    }

    if df is None or len(df) < 20:
        return result

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df["volume"]
    n = len(df)

    price = float(closes.iloc[-1])
    ep_type = ep_result.get("ep_type", "")
    gap_pct = abs(ep_result.get("ep_gap_pct") or ep_result.get("gap_pct", 0))
    ep_day_high = ep_result.get("ep_day_high") or ep_result.get("day_high", price)
    ep_day_low = ep_result.get("ep_day_low") or ep_result.get("day_low", price)
    ep_day_close = ep_result.get("ep_day_close") or ep_result.get("day_close", price)
    ep_prior_close = ep_result.get("ep_prior_close") or ep_result.get("prior_close")
    days_ago = ep_result.get("ep_days_ago") or ep_result.get("days_ago", 0)
    notes = []

    # ── 1. Gap fill level (prior close — if recovered, thesis broken) ─────
    ep_idx = max(0, n - 1 - days_ago)
    if ep_prior_close:
        gap_fill = round(ep_prior_close, 2)
    elif ep_idx > 0:
        gap_fill = round(float(closes.iloc[ep_idx - 1]), 2)
    else:
        gap_fill = round(price * (1 + gap_pct / 100), 2) if gap_pct > 0 else None
    result["gap_fill_level"] = gap_fill

    # ── 2. Bounce resistance (highest price since gap-down) ───────────────
    if days_ago > 0 and days_ago < n:
        bounce_high = round(float(highs.iloc[-(days_ago):].max()), 2)
        result["bounce_resistance"] = bounce_high
    else:
        bounce_high = ep_day_high

    # ── 3. EMAs (overhead resistance for shorts) ─────────────────────────
    if n >= 10:
        result["ema10"] = round(float(closes.ewm(span=10, adjust=False).mean().iloc[-1]), 2)
    if n >= 20:
        result["ema20"] = round(float(closes.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    if n >= 50:
        result["ema50"] = round(float(closes.ewm(span=50, adjust=False).mean().iloc[-1]), 2)

    # ── 4. ATR ────────────────────────────────────────────────────────────
    if n >= 15:
        tr_vals = []
        for i in range(n - 14, n):
            h = float(highs.iloc[i])
            l = float(lows.iloc[i])
            pc = float(closes.iloc[i - 1])
            tr_vals.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = round(sum(tr_vals) / len(tr_vals), 2)
    else:
        atr = round(float(highs.iloc[-1]) - float(lows.iloc[-1]), 2)
    result["atr"] = atr

    # ── 5. Stop price (above gap day high or bounce high) ─────────────────
    if ep_type == "SHORT_DELAYED":
        stop_price = round(bounce_high * 1.01, 2) if bounce_high else round(ep_day_high * 1.01, 2)
        notes.append(f"Stop above dead cat bounce high ${stop_price}")
    else:
        stop_price = round(ep_day_high * 1.01, 2)
        notes.append(f"Stop above gap day high ${stop_price}")

    # Ceiling: never set stop below gap fill (that's already thesis-dead zone)
    if gap_fill and stop_price and stop_price < gap_fill:
        stop_price = round(gap_fill * 1.01, 2)
        notes.append("Stop widened to above gap fill level")

    result["stop_price"] = stop_price

    # ── 6. Entry zone ────────────────────────────────────────────────────
    if ep_type == "SHORT_CLASSIC":
        if days_ago == 0:
            zone_low = round(price * 0.995, 2)
            zone_high = round(price, 2)
            notes.append("Short at market on gap-down day")
        else:
            # Enter on dead cat bounce toward VWAP or gap day close
            vwap = round((ep_day_high + ep_day_low + ep_day_close) / 3, 2)
            zone_low = round(ep_day_close, 2)
            zone_high = round(vwap, 2)
            if zone_low > zone_high:
                zone_low, zone_high = zone_high, zone_low
            notes.append(f"Short on bounce to gap day VWAP ${vwap}")

    elif ep_type == "SHORT_DELAYED":
        zone_low = round(ep_day_low * 0.995, 2)
        zone_high = round(ep_day_low, 2)
        notes.append(f"Short on breakdown below gap day low ${ep_day_low}")

    elif ep_type == "SHORT_STORY":
        zone_low = round(price * 0.995, 2)
        zone_high = round(price * 1.005, 2)
        notes.append("Momentum short — cover quickly on any bounce")

    else:
        zone_low = round(price * 0.995, 2)
        zone_high = round(price * 1.005, 2)

    result["entry_zone_low"] = zone_low
    result["entry_zone_high"] = zone_high

    # ── 7. Risk dollars and R-multiples (inverted for shorts) ─────────────
    entry_mid = round((zone_low + zone_high) / 2, 2)
    risk = round(stop_price - entry_mid, 2) if stop_price and stop_price > entry_mid else None

    if risk and risk > 0:
        result["risk_dollars"] = risk
        result["r_levels"] = {
            "r1": round(entry_mid - risk, 2),
            "r2": round(entry_mid - 2 * risk, 2),
            "r3": round(entry_mid - 3 * risk, 2),
        }
        result["risk_reward"] = 3.0 if gap_pct >= 30 else 2.0

        risk_pct = risk / entry_mid * 100 if entry_mid > 0 else 0
        if risk_pct > 15:
            notes.append(f"WARNING: wide stop ({risk_pct:.0f}% risk) — half size")
        elif risk_pct < 5:
            notes.append(f"Tight stop ({risk_pct:.1f}% risk) — good R:R")

    # ── 8. Entry quality score ───────────────────────────────────────────
    quality_pts = 0

    # Price near entry zone
    if zone_low and zone_high:
        if zone_low * 0.98 <= price <= zone_high:
            quality_pts += 2
            notes.append("Price in entry zone")
        elif price >= zone_low * 0.95:
            quality_pts += 1

    # Volume confirming
    if n >= 20:
        adv20 = float(volumes.iloc[-20:].mean())
        today_vol = float(volumes.iloc[-1])
        if adv20 > 0 and today_vol > adv20 * 1.5:
            quality_pts += 1
            notes.append("Volume confirming sell pressure")

    # Below key EMAs (bearish)
    if result["ema20"] and price < result["ema20"]:
        quality_pts += 1
    if result["ema50"] and price < result["ema50"]:
        quality_pts += 1

    # Gap held (didn't fill)
    if gap_fill and price < gap_fill:
        quality_pts += 1

    if quality_pts >= 5:
        result["entry_quality"] = "EXCELLENT"
    elif quality_pts >= 3:
        result["entry_quality"] = "GOOD"
    elif quality_pts >= 2:
        result["entry_quality"] = "FAIR"

    result["entry_quality_score"] = quality_pts
    result["entry_notes"] = notes

    return result


# ── SHORT EP WATCHLIST PERSISTENCE ────────────────────────────────────────────

def init_short_ep_watchlist_table():
    """Create short EP watchlist table for delayed short tracking."""
    from database import get_conn
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS short_ep_watchlist (
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
                added_date      TEXT DEFAULT (date('now')),
                status          TEXT DEFAULT 'watching',
                breakdown_date  TEXT,
                breakdown_price REAL,
                days_watched    INTEGER DEFAULT 0,
                bounce_high     REAL,
                current_price   REAL,
                last_updated    TEXT DEFAULT (datetime('now')),
                UNIQUE(ticker, ep_date)
            );
        """)


def add_to_short_ep_watchlist(signal: dict):
    """Add a short EP to the watchlist for delayed breakdown tracking."""
    from database import get_conn
    init_short_ep_watchlist_table()
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO short_ep_watchlist
                (ticker, ep_type, ep_date, ep_day_high, ep_day_low,
                 ep_day_open, ep_day_close, ep_gap_pct, ep_vol_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.get("ticker"),
                signal.get("ep_type", "SHORT_CLASSIC"),
                signal.get("ep_date") or date.today().isoformat(),
                signal.get("ep_day_high"),
                signal.get("ep_day_low"),
                signal.get("ep_day_open"),
                signal.get("ep_day_close"),
                signal.get("ep_gap_pct"),
                signal.get("ep_vol_ratio"),
            ))
    except Exception:
        pass


def get_past_short_eps(status: str = "watching") -> list:
    """Get past short EPs for delayed breakdown detection."""
    from database import get_conn
    init_short_ep_watchlist_table()
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT ticker, ep_date, ep_day_high, ep_day_low, ep_day_open,
                       julianday('now') - julianday(ep_date) as days_since
                FROM short_ep_watchlist
                WHERE status = ?
                  AND julianday('now') - julianday(ep_date) <= 30
            """, (status,)).fetchall()
        result = {}
        for r in rows:
            ticker = r[0]
            result.setdefault(ticker, []).append({
                "ep_date": r[1],
                "ep_day_high": r[2],
                "ep_day_low": r[3],
                "ep_day_open": r[4],
                "days_since": int(r[5]) if r[5] else 0,
            })
        return result
    except Exception:
        return {}


# ── FULL EP SCAN PIPELINE ────────────────────────────────────────────────────

def run_ep_scan(bars_data: dict, fundamentals: dict = None,
                config: dict = None) -> dict:
    """
    Run the full Stockbee EP scan pipeline (long + short).

    Returns dict with all EP results organized by type and side.
    """
    cfg = {**EP_CONFIG, **(config or {})}
    fund_data = fundamentals or {}

    # Get past EPs from watchlist for delayed EP detection (long)
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

    # Get past short EPs for delayed short detection
    past_short_eps_by_ticker = get_past_short_eps("watching")

    all_eps = []
    classic_eps = []
    delayed_eps = []
    nine_m_eps = []
    story_eps = []
    mom_bursts = []

    # Short EP lists
    all_short_eps = []
    short_classic_eps = []
    short_delayed_eps = []
    short_story_eps = []

    # Known ETF/fund suffixes and tickers to exclude
    _FUND_QUOTE_TYPES = {"ETF", "MUTUALFUND", "MONEYMARKET", "INDEX"}

    for ticker, df in bars_data.items():
        if df is None or len(df) < 30:
            continue

        # Skip penny stocks (< $2)
        last_close = float(df["close"].iloc[-1])
        if last_close < 2.0:
            continue

        # Skip ETFs, mutual funds, and index funds
        fund = fund_data.get(ticker, {})
        quote_type = fund.get("quoteType", "EQUITY")
        if quote_type in _FUND_QUOTE_TYPES:
            continue

        past_eps = past_eps_by_ticker.get(ticker, [])
        past_short_eps = past_short_eps_by_ticker.get(ticker, [])

        # ── LONG EP scan ──────────────────────────────────────────────
        # Classify EP type
        ep_result = classify_ep_type(df, fund, past_eps, cfg)

        if ep_result["ep_type"] is not None:
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

            # ── New Stockbee features ────────────────────────────────────
            price = float(df["close"].iloc[-1])

            # 2LYNCH score (especially useful for MOM_BURST setups)
            lynch = calculate_lynch_score(df, fund, cfg)

            # Bag holder protection
            bag_holder = detect_bag_holder_risk(df, cfg)

            # TI65 trend intensity
            ti65 = calculate_ti65(df, cfg)

            # Ants pattern
            ants = detect_ants_pattern(df, cfg)

            # Opening range volume (intraday data not available in daily scan)
            or_vol = check_opening_range_volume(df, None, cfg)

            # Weighted growth score
            growth = weighted_growth_score(fund, cfg)

            # Do Not Buy filter
            dnb = check_do_not_buy(df, cfg)

            # Tiny Titans quality score
            tt = score_tiny_titans(fund)

            # Conviction tier (Kelly-validated) — needs features computed above
            tier_info = classify_conviction_tier(
                {**ep_result, "ticker": ticker, "price": price,
                 "analyst_count": fund.get("analyst_count"),
                 **ti65, **lynch, **tt},
                bars_data, cfg
            )

            # Entry price intelligence
            entry_intel = calculate_entry_intelligence(df, ep_result, cfg)

            # News-based catalyst classification
            news_cat = classify_news_catalyst(fund)

            # Build full signal
            signal = {
                "ticker": ticker,
                "name": fund.get("company_name", ""),
                "price": round(price, 2),
                "ep_side": "LONG",
                **ep_result,
                **magna,
                **sales,
                **short_int,
                "entry_tactic": entry_tactic,
                "entry_intel": entry_intel,
                **news_cat,
                **lynch,
                **bag_holder,
                **ti65,
                **ants,
                **or_vol,
                **growth,
                **dnb,
                **tt,
                **tier_info,
            }

            all_eps.append(signal)

            # Route to correct list
            if ep_result["ep_type"] == "CLASSIC":
                classic_eps.append(signal)
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

        # ── SHORT EP scan ─────────────────────────────────────────────
        short_result = classify_short_ep_type(df, fund, past_short_eps, cfg)

        if short_result["ep_type"] is not None:
            price = float(df["close"].iloc[-1])

            # Short MAGNA score — pass vol_ratio and catalyst severity
            vol_ratio = short_result.get("ep_vol_ratio", 1)
            catalyst_sev = short_result.get("ep_catalyst_severity", 1)
            short_fund = {
                **fund,
                "_short_vol_ratio": vol_ratio,
                "_catalyst_severity": catalyst_sev,
            }
            short_magna = calculate_short_magna_score(ticker, df, short_fund, cfg)

            # Short entry intelligence
            short_entry_intel = calculate_short_entry_intelligence(df, short_result, cfg)

            # News catalyst (enhances fundamental-based short catalyst)
            short_news = classify_news_catalyst(fund)

            short_signal = {
                "ticker": ticker,
                "name": fund.get("company_name", ""),
                "price": round(price, 2),
                **short_result,
                **short_magna,
                **short_news,
                "entry_intel": short_entry_intel,
                "short_pct_float": fund.get("short_pct_float"),
            }

            all_short_eps.append(short_signal)

            if short_result["ep_type"] == "SHORT_CLASSIC":
                short_classic_eps.append(short_signal)
                add_to_short_ep_watchlist({
                    **short_signal,
                    "ep_date": short_result.get("ep_date"),
                })
            elif short_result["ep_type"] == "SHORT_DELAYED":
                short_delayed_eps.append(short_signal)
            elif short_result["ep_type"] == "SHORT_STORY":
                short_story_eps.append(short_signal)

    # Sort long EPs by conviction tier (best first), then MAGNA score
    sort_key = lambda x: (-x.get("conviction_tier", 0), -x.get("magna_score", 0))
    for lst in [all_eps, classic_eps, delayed_eps, nine_m_eps, story_eps, mom_bursts]:
        lst.sort(key=sort_key)

    # Sort short EPs by short MAGNA score descending
    short_sort = lambda x: -x.get("short_magna_score", 0)
    for lst in [all_short_eps, short_classic_eps, short_delayed_eps, short_story_eps]:
        lst.sort(key=short_sort)

    # ── Quality gate: split actionable (tiers 1-3) vs watchlist ──
    actionable_eps = [e for e in all_eps if e.get("conviction_tier", 0) >= 1]
    watchlist_eps = [e for e in all_eps if e.get("conviction_tier", 0) == 0]

    # Cap actionable to max_positions (focused portfolio)
    max_pos = cfg.get("default_max_positions", 3)

    # Volume spikes
    vol_spikes = scan_volume_spikes(bars_data, cfg)

    # S&P breadth
    sp_breadth = calculate_sp500_breadth(bars_data)

    # ── Bear regime auto-promote: shorts to top when breadth < 40% ──
    bear_regime = False
    breadth_pct = sp_breadth.get("pct_above_50ma")
    if breadth_pct is not None and breadth_pct < cfg["bear_regime_threshold"]:
        bear_regime = True

    # Build combined display list: in bear regime, shorts first
    if bear_regime:
        display_order = all_short_eps + actionable_eps[:max_pos]
        sp_breadth["trade_guidance"] = (
            "BEAR REGIME — short EPs promoted. "
            "Only A+ long setups, prefer short side."
        )
    else:
        display_order = actionable_eps[:max_pos] + all_short_eps

    # EP Watchlist (with display fields)
    ep_watchlist = get_ep_watchlist_display()

    # Sector RS summary (leading/lagging vs SPY)
    sector_rs_summary = _compute_sector_rs_summary(bars_data)

    # ── Tier 1 enrichment: sector themes, VCP, pyramiding, earnings ──
    try:
        from ep_realtime import enrich_ep_signals
        tier1_extras = enrich_ep_signals(
            all_eps, all_short_eps, bars_data, fund_data,
            ep_watchlist, cfg
        )
    except Exception as e:
        print(f"[ep-scan] Tier 1 enrichment error: {e}")
        import traceback; traceback.print_exc()
        tier1_extras = {"theme_summary": {}, "vcp_formations": []}

    return {
        # ── Combined display (respects bear regime ordering) ──
        "display_eps": display_order,
        "bear_regime": bear_regime,

        # ── Long EPs ──
        "actionable_eps": actionable_eps[:max_pos],
        "actionable_overflow": actionable_eps[max_pos:],
        "watchlist_eps": watchlist_eps,
        "all_eps": all_eps,
        "classic_eps": classic_eps,
        "delayed_eps": delayed_eps,
        "nine_m_eps": nine_m_eps,
        "story_eps": story_eps,
        "mom_bursts": mom_bursts,

        # ── Short EPs ──
        "all_short_eps": all_short_eps,
        "short_classic_eps": short_classic_eps,
        "short_delayed_eps": short_delayed_eps,
        "short_story_eps": short_story_eps,

        # ── Market context ──
        "volume_spikes": vol_spikes[:50],
        "sp500_breadth": sp_breadth,
        "ep_watchlist": ep_watchlist,
        "sector_rs_summary": sector_rs_summary,
        "ep_config": cfg,

        # ── Tier 1 features ──
        "theme_summary": tier1_extras.get("theme_summary", {}),
        "vcp_formations": tier1_extras.get("vcp_formations", []),

        "summary": {
            # Long
            "total_long_eps": len(all_eps),
            "actionable": len(actionable_eps),
            "watchlist_only": len(watchlist_eps),
            "tier1_max": sum(1 for e in all_eps if e.get("conviction_tier") == 1),
            "tier2_strong": sum(1 for e in all_eps if e.get("conviction_tier") == 2),
            "tier3_normal": sum(1 for e in all_eps if e.get("conviction_tier") == 3),
            "classic": len(classic_eps),
            "delayed": len(delayed_eps),
            "nine_m": len(nine_m_eps),
            "story": len(story_eps),
            "mom_burst": len(mom_bursts),

            # Short
            "total_short_eps": len(all_short_eps),
            "short_classic": len(short_classic_eps),
            "short_delayed": len(short_delayed_eps),
            "short_story": len(short_story_eps),
            "short_high_magna": sum(1 for e in all_short_eps
                                    if e.get("short_magna_score", 0) >= 4),

            # Market
            "bear_regime": bear_regime,
            "vol_spikes": len(vol_spikes),
            "watchlist_active": len(ep_watchlist),

            # Features
            "high_conviction": sum(1 for e in all_eps if e.get("magna_score", 0) >= 5),
            "bag_holder_count": sum(1 for e in all_eps if e.get("bag_holder_risk")),
            "do_not_buy_count": sum(1 for e in all_eps if e.get("do_not_buy")),
            "ants_count": sum(1 for e in all_eps if e.get("ants_detected")),
            "massive_vol_count": sum(1 for e in all_eps if e.get("or_massive_volume")),
            "ti65_confirmed_count": sum(1 for e in all_eps if e.get("ti65_confirmed")),
            "lynch_high_count": sum(1 for e in all_eps if e.get("lynch_score", 0) >= 4),
            "tt_high_count": sum(1 for e in all_eps if e.get("tt_score", 0) >= 5),

            # Tier 1
            "theme_plays": tier1_extras.get("theme_summary", {}).get("theme_play_count", 0),
            "hot_sectors": list(tier1_extras.get("theme_summary", {}).get("hot_sectors", {}).keys()),
            "vcp_count": len(tier1_extras.get("vcp_formations", [])),
        },
    }
