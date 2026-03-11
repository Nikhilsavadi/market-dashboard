"""
ep_realtime.py
--------------
Real-time EP monitoring features (Tier 1):

1. Entry Zone Alerts — poll actionable EP stocks every 5min, alert when price enters zone
2. VCP Detection — scan watchlist for volatility contraction patterns
3. Sector Clustering — score EPs by sector theme strength
4. Pyramiding Rules — calculate add levels for open positions
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ── 1. REAL-TIME ENTRY ZONE ALERTS ──────────────────────────────────────────

# Track which alerts were already sent today (ticker -> last alert time)
_zone_alerts_sent: dict[str, str] = {}
_ZONE_ALERT_COOLDOWN_MINS = 60  # Don't re-alert same ticker within 60 min


def check_entry_zones(cache: dict) -> list[dict]:
    """
    Check if any actionable EP stocks are currently in their entry zone.
    Called every 5 minutes during market hours.

    Returns list of alerts fired.
    """
    global _zone_alerts_sent
    from alerts import _send

    ep_data = cache.get("stockbee_ep", {})
    if not ep_data:
        return []

    # Get all actionable EPs (long + short) that have entry intelligence
    candidates = []
    for ep in ep_data.get("actionable_eps", []):
        if ep.get("entry_intel"):
            candidates.append(ep)
    for ep in ep_data.get("actionable_overflow", []):
        if ep.get("entry_intel"):
            candidates.append(ep)
    for ep in ep_data.get("all_short_eps", []):
        if ep.get("entry_intel"):
            candidates.append(ep)

    if not candidates:
        return []

    # Fetch current prices via yfinance (batch)
    tickers = [c["ticker"] for c in candidates]
    prices = _fetch_current_prices(tickers)
    if not prices:
        return []

    alerts_fired = []
    now = datetime.now(timezone.utc)

    for ep in candidates:
        ticker = ep["ticker"]
        current_price = prices.get(ticker)
        if current_price is None:
            continue

        intel = ep["entry_intel"]
        zone_lo = intel.get("entry_zone_low")
        zone_hi = intel.get("entry_zone_high")
        stop = intel.get("stop_price")
        r1 = (intel.get("r_levels") or {}).get("r1")

        if zone_lo is None or zone_hi is None:
            continue

        is_short = ep.get("ep_side") == "SHORT" or (ep.get("ep_type", "").startswith("SHORT"))

        # Check if price is in the entry zone
        in_zone = False
        if is_short:
            in_zone = zone_hi <= current_price <= zone_lo  # Short: zone is inverted
        else:
            in_zone = zone_lo <= current_price <= zone_hi

        if not in_zone:
            continue

        # Cooldown check
        last_alert = _zone_alerts_sent.get(ticker)
        if last_alert:
            last_time = datetime.fromisoformat(last_alert)
            if (now - last_time).total_seconds() < _ZONE_ALERT_COOLDOWN_MINS * 60:
                continue

        # Fire alert
        tier_label = ep.get("tier_label", "")
        ep_type = ep.get("ep_type", "")
        name = ep.get("name", "")
        name_str = f" {name}" if name else ""

        if is_short:
            msg = (
                f"🎯 <b>SHORT ENTRY ZONE</b>\n"
                f"🔻 <b>{ticker}</b>{name_str} NOW ${current_price:.2f}\n"
                f"Zone: ${zone_hi:.2f}-${zone_lo:.2f} | {ep_type}\n"
            )
            if stop:
                msg += f"Cover stop: ${stop:.2f}"
        else:
            tier_emoji = {"MAX BET": "🥇", "STRONG": "🥈", "NORMAL": "🥉"}.get(tier_label, "")
            msg = (
                f"🎯 <b>ENTRY ZONE HIT</b>\n"
                f"{tier_emoji} <b>{ticker}</b>{name_str} NOW ${current_price:.2f}\n"
                f"Zone: ${zone_lo:.2f}-${zone_hi:.2f} | {ep_type} | {tier_label}\n"
            )
            if stop:
                msg += f"Stop: ${stop:.2f}"
                if r1:
                    rr = abs(r1 - current_price) / abs(current_price - stop) if abs(current_price - stop) > 0.01 else 0
                    msg += f" | T1: ${r1:.2f} | R:R {rr:.1f}"

        # Add sector theme if available
        sector_theme = ep.get("sector_theme_score", 0)
        if sector_theme >= 2:
            msg += f"\n🔥 Sector theme: {ep.get('sector', '')} ({sector_theme} peer EPs)"

        _send(msg)
        _zone_alerts_sent[ticker] = now.isoformat()
        alerts_fired.append({"ticker": ticker, "price": current_price, "side": "SHORT" if is_short else "LONG"})

    # Clean up old alerts (older than today)
    today = now.date().isoformat()
    _zone_alerts_sent = {k: v for k, v in _zone_alerts_sent.items()
                         if v[:10] == today}

    return alerts_fired


def _fetch_current_prices(tickers: list) -> dict:
    """Fetch current prices for a list of tickers via yfinance."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        data = yf.download(tickers if len(tickers) > 1 else tickers[0],
                           period="1d", interval="1d",
                           progress=False, threads=True)
        prices = {}
        if len(tickers) == 1:
            if "Close" in data.columns and len(data) > 0:
                prices[tickers[0]] = float(data["Close"].iloc[-1])
        else:
            if "Close" in data.columns:
                for t in tickers:
                    try:
                        val = data["Close"][t].iloc[-1]
                        if pd.notna(val):
                            prices[t] = float(val)
                    except Exception:
                        pass
        return prices
    except Exception as e:
        print(f"[ep-realtime] Price fetch error: {e}")
        return {}


# ── 2. VCP DETECTION ────────────────────────────────────────────────────────

def detect_vcp(df: pd.DataFrame, min_contractions: int = 3) -> dict:
    """
    Detect Volatility Contraction Pattern (VCP) in price data.

    A VCP occurs when:
    - Price makes a series of contracting price swings (each range smaller than previous)
    - Volume declines during the contractions
    - The pattern resolves with a breakout on expanding volume

    Returns dict with VCP analysis.
    """
    result = {
        "vcp_detected": False,
        "contractions": 0,
        "contraction_ratios": [],  # Each range as % of previous
        "volume_declining": False,
        "tightness_score": 0,  # 0-10
        "pivot_price": None,
        "vcp_stop": None,
    }

    if df is None or len(df) < 20:
        return result

    try:
        # Look at last 30 bars for VCP formation
        recent = df.tail(30).copy()
        highs = recent["high"].values
        lows = recent["low"].values
        closes = recent["close"].values
        volumes = recent["volume"].values

        # Find swing highs and swing lows (5-bar pivots)
        swing_highs = []
        swing_lows = []

        for i in range(2, len(recent) - 2):
            if highs[i] >= max(highs[i-2:i]) and highs[i] >= max(highs[i+1:i+3]):
                swing_highs.append((i, highs[i]))
            if lows[i] <= min(lows[i-2:i]) and lows[i] <= min(lows[i+1:i+3]):
                swing_lows.append((i, lows[i]))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return result

        # Calculate ranges between consecutive swing high/low pairs
        ranges = []
        for j in range(min(len(swing_highs), len(swing_lows))):
            h = swing_highs[j][1]
            l = swing_lows[j][1]
            if l > 0:
                ranges.append((h - l) / l * 100)

        if len(ranges) < 2:
            return result

        # Check for contracting ranges
        contractions = 0
        ratios = []
        for k in range(1, len(ranges)):
            if ranges[k-1] > 0:
                ratio = ranges[k] / ranges[k-1]
                ratios.append(round(ratio, 2))
                if ratio < 0.75:  # Each range at least 25% smaller
                    contractions += 1

        # Volume should decline during contractions
        vol_first_half = float(np.mean(volumes[:len(volumes)//2]))
        vol_second_half = float(np.mean(volumes[len(volumes)//2:]))
        vol_declining = vol_second_half < vol_first_half * 0.8

        # Tightness: how tight is the most recent range?
        last_5_range = (max(highs[-5:]) - min(lows[-5:])) / min(lows[-5:]) * 100 if min(lows[-5:]) > 0 else 99
        tightness = max(0, min(10, int(10 - last_5_range)))  # Tighter = higher score

        vcp_detected = contractions >= min_contractions and vol_declining

        # Pivot price = recent swing high (breakout level)
        pivot = float(swing_highs[-1][1]) if swing_highs else None
        # VCP stop = last swing low
        vcp_stop = float(swing_lows[-1][1]) if swing_lows else None

        result.update({
            "vcp_detected": vcp_detected,
            "contractions": contractions,
            "contraction_ratios": ratios,
            "volume_declining": vol_declining,
            "tightness_score": tightness,
            "pivot_price": round(pivot, 2) if pivot else None,
            "vcp_stop": round(vcp_stop, 2) if vcp_stop else None,
        })

    except Exception as e:
        print(f"[vcp] Detection error: {e}")

    return result


def scan_watchlist_vcp(bars_data: dict, ep_watchlist: list) -> list[dict]:
    """
    Scan EP watchlist stocks for VCP formation.
    These are high-probability second-chance entries.
    """
    from alerts import _send

    vcp_alerts = []
    for entry in ep_watchlist:
        ticker = entry.get("ticker", "")
        if ticker not in bars_data:
            continue

        df = bars_data[ticker]
        vcp = detect_vcp(df)

        if not vcp["vcp_detected"]:
            continue

        vcp_alert = {
            "ticker": ticker,
            "name": entry.get("name", ""),
            "ep_type": entry.get("ep_type", ""),
            "days_watched": entry.get("days_watched", 0),
            **vcp,
        }
        vcp_alerts.append(vcp_alert)

        # Send Telegram alert for VCP detection
        msg = (
            f"📐 <b>VCP FORMING</b> — {ticker}"
            f"\n{vcp['contractions']} contractions · "
            f"Tightness {vcp['tightness_score']}/10 · "
            f"Vol declining: {'Yes' if vcp['volume_declining'] else 'No'}"
        )
        if vcp["pivot_price"]:
            msg += f"\nPivot: ${vcp['pivot_price']:.2f}"
        if vcp["vcp_stop"]:
            msg += f" | Stop: ${vcp['vcp_stop']:.2f}"
        msg += f"\nOriginal EP: {entry.get('ep_type', '')} {entry.get('days_watched', 0)}d ago"

        _send(msg)

    return vcp_alerts


# ── 3. SECTOR CLUSTERING / THEME SCORING ────────────────────────────────────

# GICS sector mapping
SECTOR_MAP = {
    "Technology": ["technology", "software", "semiconductor", "hardware", "IT", "cloud",
                   "saas", "cybersecurity", "data"],
    "Healthcare": ["healthcare", "biotech", "pharma", "medical", "drug", "therapeutics",
                   "diagnostic", "genomic"],
    "Consumer": ["consumer", "retail", "restaurant", "apparel", "luxury", "food",
                 "beverage", "e-commerce"],
    "Financial": ["financial", "bank", "insurance", "capital", "asset", "wealth",
                  "fintech", "payment"],
    "Energy": ["energy", "oil", "gas", "solar", "wind", "renewable", "nuclear",
               "uranium", "lithium", "battery"],
    "Industrial": ["industrial", "aerospace", "defense", "construction", "machinery",
                   "engineering", "transport"],
    "Materials": ["material", "chemical", "mining", "steel", "gold", "silver",
                  "copper", "rare earth"],
    "Real Estate": ["reit", "real estate", "property", "housing", "mortgage"],
    "Communication": ["communication", "media", "entertainment", "streaming",
                      "advertising", "social", "telecom"],
    "Utilities": ["utility", "electric", "water", "gas distribution"],
}


def classify_sector(fund: dict) -> str:
    """Classify a stock into a sector based on yfinance data."""
    # yfinance provides sector directly
    sector = fund.get("sector", "")
    if sector:
        return sector

    # Fallback: try to infer from industry
    industry = fund.get("industry", "").lower()
    if not industry:
        return "Unknown"

    for sector_name, keywords in SECTOR_MAP.items():
        for kw in keywords:
            if kw in industry:
                return sector_name
    return "Other"


def score_sector_theme(all_eps: list) -> list:
    """
    Score each EP by how many peer EPs are in the same sector.

    Multiple EPs in the same sector = theme play = higher conviction.
    3+ EPs in sector = hot theme (score 3+)

    Mutates and returns all_eps with added sector_theme fields.
    """
    # Count EPs per sector
    sector_counts = {}
    for ep in all_eps:
        sector = ep.get("sector", "Unknown")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    # Score each EP
    for ep in all_eps:
        sector = ep.get("sector", "Unknown")
        peer_count = sector_counts.get(sector, 0)
        ep["sector_theme_score"] = peer_count
        ep["sector_theme_hot"] = peer_count >= 3

    # Build theme summary
    hot_sectors = {s: c for s, c in sector_counts.items() if c >= 3 and s != "Unknown"}

    return all_eps, {
        "sector_counts": sector_counts,
        "hot_sectors": hot_sectors,
        "theme_play_count": sum(1 for ep in all_eps if ep.get("sector_theme_hot")),
    }


# ── 4. PYRAMIDING RULES ────────────────────────────────────────────────────

def calculate_pyramid_plan(ep: dict, equity: float = 100000, config: dict = None) -> dict:
    """
    Calculate a complete pyramiding plan for an EP trade.

    Rules:
    - Initial entry: half-Kelly at entry zone
    - Add 1: quarter-Kelly at R1 (1R profit) on volume confirmation
    - Add 2: quarter-Kelly at new high on volume
    - Max position: initial + 2 adds = full Kelly

    Returns pyramid plan with levels, sizes, and risk management.
    """
    cfg = config or {}
    intel = ep.get("entry_intel", {})
    r_levels = intel.get("r_levels", {})

    price = ep.get("price", 0)
    stop = intel.get("stop_price")
    zone_lo = intel.get("entry_zone_low")
    zone_hi = intel.get("entry_zone_high")
    r1 = r_levels.get("r1")
    r2 = r_levels.get("r2")
    r3 = r_levels.get("r3")

    if not price or not stop or not zone_lo:
        return {"has_plan": False}

    is_short = ep.get("ep_side") == "SHORT" or (ep.get("ep_type", "").startswith("SHORT"))

    # Risk per share
    entry_price = (zone_lo + zone_hi) / 2 if zone_hi else zone_lo
    risk_per_share = abs(entry_price - stop)
    if risk_per_share < 0.01:
        return {"has_plan": False}

    # Tier-based sizing
    tier = ep.get("conviction_tier", 3)
    tier_label = ep.get("tier_label", "NORMAL")

    # Half-Kelly allocations by tier
    half_kelly_pct = {1: 0.20, 2: 0.09, 3: 0.04}.get(tier, 0.04)
    risk_pct = cfg.get("default_risk_pct", 3) / 100

    # Initial position: half-Kelly
    initial_dollar = equity * half_kelly_pct
    initial_shares = int(initial_dollar / entry_price) if entry_price > 0 else 0
    initial_risk = initial_shares * risk_per_share

    # Add 1: quarter-Kelly at R1
    add1_dollar = equity * half_kelly_pct * 0.5
    add1_shares = int(add1_dollar / r1) if r1 and r1 > 0 else 0
    add1_price = r1

    # Add 2: quarter-Kelly at R2 or new high
    add2_dollar = equity * half_kelly_pct * 0.5
    new_high = r2 if r2 else (r1 * 1.05 if r1 else None)
    add2_shares = int(add2_dollar / new_high) if new_high and new_high > 0 else 0
    add2_price = new_high

    # Stop management for pyramiding
    # After Add 1: move stop to breakeven on initial
    # After Add 2: move stop to Add 1 entry
    total_shares = initial_shares + add1_shares + add2_shares
    total_cost = (initial_shares * entry_price +
                  add1_shares * (add1_price or 0) +
                  add2_shares * (add2_price or 0))
    avg_price = total_cost / total_shares if total_shares > 0 else 0

    plan = {
        "has_plan": True,
        "is_short": is_short,
        "tier": tier,
        "tier_label": tier_label,
        "half_kelly_pct": round(half_kelly_pct * 100, 1),

        # Initial entry
        "initial": {
            "price": round(entry_price, 2),
            "shares": initial_shares,
            "dollar": round(initial_shares * entry_price, 0),
            "stop": round(stop, 2),
            "risk_dollar": round(initial_risk, 0),
            "risk_pct_equity": round(initial_risk / equity * 100, 2),
        },

        # Add 1 at R1
        "add1": {
            "trigger": "R1 profit target on volume",
            "price": round(add1_price, 2) if add1_price else None,
            "shares": add1_shares,
            "dollar": round(add1_shares * add1_price, 0) if add1_price else 0,
            "new_stop": round(entry_price, 2),  # Move to breakeven
            "condition": "Volume > 1.5x average on breakout day",
        },

        # Add 2 at new high
        "add2": {
            "trigger": "New high / R2 on volume",
            "price": round(add2_price, 2) if add2_price else None,
            "shares": add2_shares,
            "dollar": round(add2_shares * add2_price, 0) if add2_price else 0,
            "new_stop": round(add1_price, 2) if add1_price else None,  # Move to Add1 entry
            "condition": "Volume > 1.5x average, price > R1",
        },

        # Full position summary
        "full_position": {
            "total_shares": total_shares,
            "total_dollar": round(total_cost, 0),
            "avg_price": round(avg_price, 2),
            "pct_equity": round(total_cost / equity * 100, 1),
            "max_risk_at_full": round(total_shares * risk_per_share, 0),
        },

        # Targets
        "targets": {
            "t1": round(r1, 2) if r1 else None,
            "t2": round(r2, 2) if r2 else None,
            "t3": round(r3, 2) if r3 else None,
        },

        # Rules
        "rules": [
            f"Entry: {initial_shares} shares @ ${entry_price:.2f} (stop ${stop:.2f})",
            f"Add 1: {add1_shares} shares @ ${add1_price:.2f} → move stop to ${entry_price:.2f}" if add1_price else "Add 1: N/A",
            f"Add 2: {add2_shares} shares @ ${add2_price:.2f} → move stop to ${add1_price:.2f}" if add2_price and add1_price else "Add 2: N/A",
            "Never add to a losing position",
            "Only add if volume confirms (>1.5x avg)",
        ],
    }

    return plan


# ── 5. NEXT EARNINGS COUNTDOWN ──────────────────────────────────────────────

def get_earnings_countdown(ticker: str) -> Optional[dict]:
    """Get days until next earnings for a ticker."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        if cal is not None and not cal.empty:
            # calendar can be a DataFrame with Earnings Date row
            if "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"]
                next_date = pd.Timestamp(dates.iloc[0])
            elif hasattr(cal, "columns") and len(cal.columns) > 0:
                next_date = pd.Timestamp(cal.iloc[0, 0])
            else:
                return None

            today = pd.Timestamp(date.today())
            days_until = (next_date - today).days
            return {
                "earnings_date": next_date.strftime("%Y-%m-%d"),
                "days_until_earnings": days_until,
                "earnings_imminent": 0 < days_until <= 7,
                "earnings_catalyst_window": 7 < days_until <= 42,
            }
    except Exception:
        pass
    return None


# ── INTEGRATION: Enrich EP signals with all Tier 1 features ────────────────

def enrich_ep_signals(all_eps: list, all_short_eps: list,
                      bars_data: dict, fund_data: dict,
                      ep_watchlist: list, config: dict) -> dict:
    """
    Post-process EP signals with Tier 1 enhancements:
    1. Sector classification + theme scoring
    2. VCP detection on watchlist
    3. Pyramid plans for actionable EPs
    4. Earnings countdown for top picks

    Called at the end of run_ep_scan() to enrich results.
    """
    # 1. Classify sectors and score themes
    for ep in all_eps + all_short_eps:
        ticker = ep["ticker"]
        fund = fund_data.get(ticker, {})
        ep["sector"] = classify_sector(fund)

    all_eps, theme_summary = score_sector_theme(all_eps)
    # Also score shorts
    if all_short_eps:
        all_short_eps, short_theme = score_sector_theme(all_short_eps)
        theme_summary["short_hot_sectors"] = short_theme.get("hot_sectors", {})

    # 2. VCP detection on watchlist stocks
    vcp_results = []
    for entry in ep_watchlist:
        ticker = entry.get("ticker", "")
        if ticker in bars_data:
            vcp = detect_vcp(bars_data[ticker])
            if vcp["vcp_detected"]:
                vcp_results.append({
                    "ticker": ticker,
                    "ep_type": entry.get("ep_type", ""),
                    "days_watched": entry.get("days_watched", 0),
                    **vcp,
                })

    # 3. Pyramid plans for actionable EPs (top picks only)
    for ep in all_eps:
        if ep.get("conviction_tier", 0) >= 1:
            ep["pyramid_plan"] = calculate_pyramid_plan(ep, config=config)

    # 4. Earnings countdown for actionable EPs (top 10 only to limit API calls)
    actionable = [e for e in all_eps if e.get("conviction_tier", 0) >= 1]
    for ep in actionable[:10]:
        earnings = get_earnings_countdown(ep["ticker"])
        if earnings:
            ep.update(earnings)

    return {
        "theme_summary": theme_summary,
        "vcp_formations": vcp_results,
    }
