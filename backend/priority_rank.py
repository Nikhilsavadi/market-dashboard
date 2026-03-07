"""
priority_rank.py
----------------
Ranks signals by their likelihood of moving quickly and cleanly.
Designed for capital-constrained traders who can only take 1-3 trades.

This is NOT the same as signal_score (which measures setup quality).
priority_score answers a different question:
  "Given I can only take 2 trades, which ones should I act on FIRST?"

Formula weights:
  VCS tightness     30%  — coiled bases break faster and cleaner
  Vol ratio         20%  — institutional interest present today
  Pivot proximity   25%  — how close to the actual trigger
  Sector momentum   15%  — is the sector moving RIGHT NOW
  RS rank           10%  — relative strength confirmation

Result: top 3 labelled TAKE, WATCH, MONITOR
"""

from typing import Optional


# ── Tier labels ───────────────────────────────────────────────────────────────

TIER_TAKE    = "TAKE"     # act on this — highest priority
TIER_WATCH   = "WATCH"    # second pick if capital allows
TIER_MONITOR = "MONITOR"  # review but don't act yet


def calculate_priority_score(signal: dict, sector_rs_data: dict = None) -> dict:
    """
    Compute priority_score for a single signal.
    Returns dict with priority_score, tier, and reasoning breakdown.
    """
    vcs       = signal.get("vcs") or 6.0
    vol_ratio = signal.get("vol_ratio") or 1.0
    rs        = signal.get("rs") or 70
    price     = signal.get("price") or 0
    sector    = signal.get("sector", "")

    # ── 1. VCS tightness (0–30 pts) ──────────────────────────────────────────
    # VCS 1-2: max score. VCS 7+: zero.
    vcs_score = max(0, (8 - vcs) / 7 * 30)
    vcs_note  = (
        "🔥 extremely coiled" if vcs <= 2 else
        "🔥 tight base"       if vcs <= 3 else
        "✓ reasonable coil"   if vcs <= 5 else
        "loose — lower priority"
    )

    # ── 2. Volume ratio (0–20 pts) ───────────────────────────────────────────
    # 2.0×+ = full score. Below 1.0 = no score.
    vol_score = min(20, max(0, (vol_ratio - 1.0) / 1.0 * 20))
    vol_note  = (
        f"vol {vol_ratio:.1f}× — strong institutional activity" if vol_ratio >= 1.8 else
        f"vol {vol_ratio:.1f}× — above average"                 if vol_ratio >= 1.3 else
        f"vol {vol_ratio:.1f}× — light, may take time"          if vol_ratio >= 1.0 else
        f"vol {vol_ratio:.1f}× — drying up (can be bullish)"
    )

    # ── 3. Pivot proximity (0–25 pts) ────────────────────────────────────────
    # How close is price to the actual breakout trigger?
    # pct_from_pivot: 0% = right at pivot, 5% = 5% below
    pct_from_pivot = signal.get("pct_from_pivot")

    # Fall back to distance from nearest MA if no pivot data
    if pct_from_pivot is None:
        ma21 = signal.get("ma21")
        if ma21 and price:
            pct_from_pivot = abs(price - ma21) / price * 100
        else:
            pct_from_pivot = 5.0  # assume moderate distance

    if pct_from_pivot <= 0.5:
        prox_score = 25
        prox_note  = "right at pivot — can trigger any moment"
    elif pct_from_pivot <= 1.5:
        prox_score = 20
        prox_note  = f"{pct_from_pivot:.1f}% from pivot — very close"
    elif pct_from_pivot <= 3.0:
        prox_score = 13
        prox_note  = f"{pct_from_pivot:.1f}% from pivot — close"
    elif pct_from_pivot <= 5.0:
        prox_score = 6
        prox_note  = f"{pct_from_pivot:.1f}% from pivot — needs time"
    else:
        prox_score = 0
        prox_note  = f"{pct_from_pivot:.1f}% from pivot — early stage"

    # ── 4. Sector momentum right now (0–15 pts) ──────────────────────────────
    # Use 1-month sector RS vs SPY — positive = leading sector
    sector_rs_1m = signal.get("sector_rs_1m") or 0
    if sector_rs_data and sector:
        sector_rs_1m = sector_rs_data.get(sector, {}).get("rs_vs_spy_1m") or sector_rs_1m

    if sector_rs_1m >= 3:
        sect_score = 15
        sect_note  = f"{sector} leading market strongly"
    elif sector_rs_1m >= 1:
        sect_score = 10
        sect_note  = f"{sector} outperforming"
    elif sector_rs_1m >= -1:
        sect_score = 5
        sect_note  = f"{sector} in line with market"
    else:
        sect_score = 0
        sect_note  = f"{sector} lagging — sector headwind"

    # ── 5. RS rank (0–10 pts) ────────────────────────────────────────────────
    rs_score = min(10, max(0, (rs - 70) / 25 * 10))
    rs_note  = f"RS {rs}"

    # ── Total ─────────────────────────────────────────────────────────────────
    total = round(vcs_score + vol_score + prox_score + sect_score + rs_score, 1)

    # ── Tier assignment ───────────────────────────────────────────────────────
    # Also respect the base signal_score — don't prioritise a weak setup
    signal_score = signal.get("signal_score") or 5
    if total >= 55 and signal_score >= 7:
        tier = TIER_TAKE
    elif total >= 35 or (total >= 25 and signal_score >= 8):
        tier = TIER_WATCH
    else:
        tier = TIER_MONITOR

    # ── Reason string — concise, for Telegram ─────────────────────────────────
    reasons = []
    if vcs <= 3:       reasons.append(vcs_note)
    if vol_ratio >= 1.5: reasons.append(vol_note)
    if pct_from_pivot <= 1.5: reasons.append(prox_note)
    if sector_rs_1m >= 2:    reasons.append(sect_note)
    if not reasons:
        reasons = [vcs_note, prox_note]

    return {
        "priority_score":   total,
        "priority_tier":    tier,
        "priority_reason":  " · ".join(reasons),
        "priority_breakdown": {
            "vcs_score":   round(vcs_score, 1),
            "vol_score":   round(vol_score, 1),
            "prox_score":  round(prox_score, 1),
            "sect_score":  round(sect_score, 1),
            "rs_score":    round(rs_score, 1),
            "total":       total,
        },
        "priority_notes": {
            "vcs":     vcs_note,
            "vol":     vol_note,
            "prox":    prox_note,
            "sector":  sect_note,
            "rs":      rs_note,
        },
    }


def rank_signals(signals: list, sector_rs_data: dict = None, max_take: int = 2) -> list:
    """
    Score and rank all signals. Assigns TAKE to top max_take,
    WATCH to next 2, MONITOR to the rest.

    Returns signals sorted by priority_score descending,
    with priority_score, priority_tier, priority_reason added.
    """
    if not signals:
        return []

    scored = []
    for s in signals:
        rank_data = calculate_priority_score(s, sector_rs_data)
        scored.append({**s, **rank_data})

    scored.sort(key=lambda x: (
        x.get("priority_score", 0),
        x.get("signal_score", 0),
    ), reverse=True)

    # Re-assign tiers based on actual rank position
    for i, s in enumerate(scored):
        if i < max_take:
            s["priority_tier"] = TIER_TAKE
        elif i < max_take + 2:
            s["priority_tier"] = TIER_WATCH
        else:
            s["priority_tier"] = TIER_MONITOR

    return scored


def get_top_picks(signals: list, sector_rs_data: dict = None, max_take: int = 2) -> dict:
    """
    Returns the ranked signal list plus a summary dict for easy consumption.
    Used by the API endpoint and morning brief.
    """
    ranked = rank_signals(signals, sector_rs_data, max_take)

    take    = [s for s in ranked if s.get("priority_tier") == TIER_TAKE]
    watch   = [s for s in ranked if s.get("priority_tier") == TIER_WATCH]
    monitor = [s for s in ranked if s.get("priority_tier") == TIER_MONITOR]

    return {
        "ranked":  ranked,
        "take":    take,
        "watch":   watch,
        "monitor": monitor,
        "summary": {
            "total":    len(ranked),
            "take":     len(take),
            "watch":    len(watch),
            "monitor":  len(monitor),
            "top_tickers": [s["ticker"] for s in take],
        },
    }


def calculate_short_priority_score(signal: dict, sector_rs_data: dict = None) -> dict:
    """
    Priority score for short signals.
    Same framework as longs but with flipped sector and RS logic:
      - Sector WEAKNESS is rewarded (lagging sectors = tailwind for shorts)
      - RS WEAKNESS is rewarded (low RS = already showing relative weakness)
      - VCS still matters — tight coil before breakdown is cleanest short
      - Vol on down days — confirms distribution
      - Proximity to resistance (broken MA = ideal short entry zone)
    """
    vcs       = signal.get("vcs") or 6.0
    vol_ratio = signal.get("vol_ratio") or 1.0
    rs        = signal.get("rs") or 50
    price     = signal.get("price") or 0
    sector    = signal.get("sector", "")

    # ── 1. VCS / volatility contraction (0–25 pts) ───────────────────────────
    # Tight coil before breakdown = clean short entry
    vcs_score = max(0, (8 - vcs) / 7 * 25)
    vcs_note  = (
        "🔥 tight before breakdown" if vcs <= 3 else
        "✓ reasonable contraction"  if vcs <= 5 else
        "loose — choppier entry"
    )

    # ── 2. Volume on down days (0–20 pts) ────────────────────────────────────
    # High vol confirms distribution / institutional selling
    vol_score = min(20, max(0, (vol_ratio - 1.0) / 1.0 * 20))
    vol_note  = (
        f"vol {vol_ratio:.1f}× — heavy distribution"  if vol_ratio >= 1.8 else
        f"vol {vol_ratio:.1f}× — elevated selling"    if vol_ratio >= 1.3 else
        f"vol {vol_ratio:.1f}× — moderate"
    )

    # ── 3. Proximity to resistance / broken MA (0–25 pts) ────────────────────
    # Best short entry = just below broken MA (failed rally back)
    pct_from_pivot = signal.get("pct_from_pivot")
    if pct_from_pivot is None:
        ma21 = signal.get("ma21")
        if ma21 and price:
            pct_from_pivot = abs(price - ma21) / price * 100
        else:
            pct_from_pivot = 5.0

    if pct_from_pivot <= 0.5:
        prox_score = 25
        prox_note  = "at broken MA — ideal short entry"
    elif pct_from_pivot <= 1.5:
        prox_score = 20
        prox_note  = f"{pct_from_pivot:.1f}% from resistance — close"
    elif pct_from_pivot <= 3.0:
        prox_score = 12
        prox_note  = f"{pct_from_pivot:.1f}% from resistance"
    elif pct_from_pivot <= 5.0:
        prox_score = 5
        prox_note  = f"{pct_from_pivot:.1f}% from resistance — needs pullback"
    else:
        prox_score = 0
        prox_note  = f"{pct_from_pivot:.1f}% — too extended, wait for bounce"

    # ── 4. Sector weakness (0–20 pts) ────────────────────────────────────────
    # Flipped vs longs: LAGGING sector = tailwind for shorts
    sector_rs_1m = signal.get("sector_rs_1m") or 0
    if sector_rs_data and sector:
        sector_rs_1m = sector_rs_data.get(sector, {}).get("rs_vs_spy_1m") or sector_rs_1m

    if sector_rs_1m <= -3:
        sect_score = 20
        sect_note  = f"{sector} collapsing vs market"
    elif sector_rs_1m <= -1:
        sect_score = 14
        sect_note  = f"{sector} underperforming"
    elif sector_rs_1m <= 1:
        sect_score = 7
        sect_note  = f"{sector} in line with market"
    else:
        sect_score = 0
        sect_note  = f"{sector} leading — sector headwind for short"

    # ── 5. RS weakness (0–10 pts) ────────────────────────────────────────────
    # Low RS = stock already showing relative weakness = better short candidate
    rs_score = min(10, max(0, (50 - rs) / 40 * 10)) if rs < 50 else 0
    rs_note  = f"RS {rs} — {'weak' if rs < 30 else 'moderate weakness'}"

    total = round(vcs_score + vol_score + prox_score + sect_score + rs_score, 1)

    short_score = signal.get("short_score") or signal.get("signal_score") or 5
    if total >= 55 and short_score >= 60:
        tier = TIER_TAKE
    elif total >= 35 or (total >= 25 and short_score >= 70):
        tier = TIER_WATCH
    else:
        tier = TIER_MONITOR

    reasons = []
    if vcs <= 3:          reasons.append(vcs_note)
    if vol_ratio >= 1.5:  reasons.append(vol_note)
    if pct_from_pivot <= 1.5: reasons.append(prox_note)
    if sector_rs_1m <= -2:   reasons.append(sect_note)
    if not reasons:
        reasons = [vcs_note, prox_note]

    return {
        "priority_score":   total,
        "priority_tier":    tier,
        "priority_reason":  " · ".join(reasons),
        "priority_breakdown": {
            "vcs_score":   round(vcs_score, 1),
            "vol_score":   round(vol_score, 1),
            "prox_score":  round(prox_score, 1),
            "sect_score":  round(sect_score, 1),
            "rs_score":    round(rs_score, 1),
            "total":       total,
        },
        "priority_notes": {
            "vcs":    vcs_note,
            "vol":    vol_note,
            "prox":   prox_note,
            "sector": sect_note,
            "rs":     rs_note,
        },
    }


def rank_short_signals(signals: list, sector_rs_data: dict = None, max_take: int = 2) -> list:
    """Score and rank short signals by short-specific priority."""
    if not signals:
        return []

    scored = []
    for s in signals:
        rank_data = calculate_short_priority_score(s, sector_rs_data)
        scored.append({**s, **rank_data})

    scored.sort(key=lambda x: (
        x.get("priority_score", 0),
        x.get("short_score", 0),
    ), reverse=True)

    for i, s in enumerate(scored):
        if i < max_take:
            s["priority_tier"] = TIER_TAKE
        elif i < max_take + 2:
            s["priority_tier"] = TIER_WATCH
        else:
            s["priority_tier"] = TIER_MONITOR

    return scored


def get_top_short_picks(signals: list, sector_rs_data: dict = None, max_take: int = 2) -> dict:
    """Returns ranked short signals with TAKE/WATCH/MONITOR split."""
    ranked  = rank_short_signals(signals, sector_rs_data, max_take)
    take    = [s for s in ranked if s.get("priority_tier") == TIER_TAKE]
    watch   = [s for s in ranked if s.get("priority_tier") == TIER_WATCH]
    monitor = [s for s in ranked if s.get("priority_tier") == TIER_MONITOR]

    return {
        "ranked":  ranked,
        "take":    take,
        "watch":   watch,
        "monitor": monitor,
        "summary": {
            "total":    len(ranked),
            "take":     len(take),
            "watch":    len(watch),
            "monitor":  len(monitor),
            "top_tickers": [s["ticker"] for s in take],
        },
    }



def get_focus_list(scan_data: dict, sector_rs_data: dict = None, max_picks: int = 8) -> dict:
    """
    Master focus list — combines ALL signal types and ranks into top N picks.
    
    This answers: "I can only trade 5-8 names today. Which ones?"
    
    Sources (in priority bonus order):
    1. HVE retest entry-ready   (+20 bonus pts — highest conviction)
    2. EP delayed reaction ready (+15 bonus pts)
    3. MA bounce long signals    (base priority score)
    4. Pattern signals           (base priority score)
    
    Deduplicates by ticker — same stock in multiple lists gets best score only.
    """
    candidates = {}   # ticker → best scored signal

    def _add(signal, bonus: float = 0.0, source: str = ""):
        if not signal or not signal.get("ticker"):
            return
        ticker = signal["ticker"]
        rank_data  = calculate_priority_score(signal, sector_rs_data)
        base_score = rank_data["priority_score"]
        total      = round(base_score + bonus, 1)

        existing = candidates.get(ticker)
        if existing is None or total > existing["focus_score"]:
            candidates[ticker] = {
                **signal,
                **rank_data,
                "focus_score":  total,
                "focus_source": source,
                "focus_bonus":  bonus,
            }

    # 1. HVE entry-ready (highest bonus)
    for s in scan_data.get("hve_signals", []):
        if s.get("hve_entry_ok"):
            _add(s, bonus=20.0, source="HVE_RETEST")
        else:
            _add(s, bonus=8.0, source="HVE_WATCH")

    # 2. EP entry-ready
    for s in scan_data.get("ep_signals", []):
        if s.get("ep_entry_ok"):
            _add(s, bonus=15.0, source="EP_READY")
        else:
            _add(s, bonus=5.0, source="EP_WATCH")

    # 3. Long signals (MA bounce)
    for s in scan_data.get("long_signals", []):
        source = "MA10" if s.get("ma10_touch") else "MA21" if s.get("ma21_touch") else "MA50"
        _add(s, bonus=0.0, source=source)

    # 4. Pattern signals
    for s in scan_data.get("pattern_signals", []):
        _add(s, bonus=2.0, source="PATTERN")

    # Sort by focus_score
    ranked = sorted(candidates.values(), key=lambda x: (
        x.get("focus_score", 0),
        x.get("signal_score", 0),
        x.get("rs", 0),
    ), reverse=True)

    # Assign tiers
    for i, s in enumerate(ranked):
        if i < 3:
            s["priority_tier"] = TIER_TAKE
        elif i < max_picks:
            s["priority_tier"] = TIER_WATCH
        else:
            s["priority_tier"] = TIER_MONITOR

    top = ranked[:max_picks]

    return {
        "focus_list":    top,
        "all_ranked":    ranked[:30],
        "take":          [s for s in top if s.get("priority_tier") == TIER_TAKE],
        "watch":         [s for s in top if s.get("priority_tier") == TIER_WATCH],
        "total_scanned": len(candidates),
        "summary": {
            "top_tickers":   [s["ticker"] for s in top],
            "hve_in_list":   sum(1 for s in top if "HVE" in s.get("focus_source", "")),
            "ep_in_list":    sum(1 for s in top if "EP" in s.get("focus_source", "")),
            "ma_in_list":    sum(1 for s in top if s.get("focus_source") in ("MA10", "MA21", "MA50")),
        },
    }
