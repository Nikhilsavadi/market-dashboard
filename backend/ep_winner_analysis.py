"""
ep_winner_analysis.py
---------------------
Reverse-engineer the optimal EP exit strategy by studying the biggest winners.

Approach: Start from known big EP movers, pull their full price path post-EP,
analyze MFE trajectory, drawdown tolerance, time-to-peak, and design an exit
that maximizes capture of 100%+ runners.
"""

import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ── Known big EP winners to study ────────────────────────────────────────────
# Format: (ticker, approximate_ep_date, catalyst_description)
# These are stocks that had massive moves after episodic pivots

WINNERS_TO_STUDY = [
    # Mega winners (100%+)
    ("CDTX", "2024-06-01", "2025-03-01", "Biotech catalyst"),
    ("COGT", "2024-06-01", "2025-03-01", "Biotech catalyst"),
    ("CIEN", "2024-06-01", "2025-03-01", "Tech/networking"),
    ("SATS", "2024-06-01", "2025-03-01", "Satellite tech"),
    ("TCMD", "2024-06-01", "2025-03-01", "Medical devices"),
    ("IREN", "2024-01-01", "2025-03-01", "Bitcoin mining/AI"),
    ("HOOD", "2024-01-01", "2025-03-01", "Fintech/crypto"),
    ("NVDA", "2024-01-01", "2025-03-01", "AI/semiconductors"),
    ("PLTR", "2024-01-01", "2025-03-01", "AI/defense"),
    # Add more known EP movers
    ("SMCI", "2024-01-01", "2025-03-01", "AI servers"),
    ("APP", "2024-01-01", "2025-03-01", "Ad tech"),
    ("AFRM", "2024-01-01", "2025-03-01", "Fintech BNPL"),
    ("CELH", "2024-01-01", "2025-03-01", "Energy drinks"),
    ("DUOL", "2024-01-01", "2025-03-01", "Ed tech"),
    ("AXON", "2024-01-01", "2025-03-01", "Law enforcement tech"),
    ("TGTX", "2024-01-01", "2025-03-01", "Biotech"),
    ("RDDT", "2024-03-01", "2025-03-01", "Social media IPO"),
    ("MSTR", "2024-01-01", "2025-03-01", "Bitcoin treasury"),
]


def fetch_daily_bars(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV bars from yfinance."""
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(start=start, end=end, interval="1d")
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return pd.DataFrame()


def detect_ep_events(df: pd.DataFrame, ticker: str, min_gap: float = 8.0) -> list:
    """
    Find all EP-like events in the price history.
    More lenient than live scanner to catch the actual catalyst day.
    """
    events = []
    if len(df) < 60:
        return events

    for i in range(50, len(df)):
        prior_close = float(df["close"].iloc[i - 1])
        if prior_close <= 0:
            continue

        day_open = float(df["open"].iloc[i])
        day_close = float(df["close"].iloc[i])
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        day_vol = float(df["volume"].iloc[i])

        gap_pct = (day_open - prior_close) / prior_close * 100

        # Check both gap-up EPs and intraday surge EPs
        intraday_move = (day_close - prior_close) / prior_close * 100

        # Lenient: gap >= min_gap OR intraday move >= 15% with volume
        avg_vol = float(df["volume"].iloc[max(0, i-50):i].mean())
        vol_ratio = day_vol / avg_vol if avg_vol > 0 else 0

        is_ep = False
        if gap_pct >= min_gap and vol_ratio >= 2:
            is_ep = True
        elif intraday_move >= 15 and vol_ratio >= 3:
            is_ep = True

        if not is_ep:
            continue

        # Close held above 30% of the move
        if day_close < prior_close + (day_open - prior_close) * 0.3 and gap_pct >= min_gap:
            if intraday_move < 10:
                continue

        date_str = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])

        events.append({
            "idx": i,
            "date": date_str,
            "prior_close": round(prior_close, 2),
            "open": round(day_open, 2),
            "close": round(day_close, 2),
            "high": round(day_high, 2),
            "low": round(day_low, 2),
            "volume": int(day_vol),
            "gap_pct": round(gap_pct, 1),
            "intraday_move_pct": round(intraday_move, 1),
            "vol_ratio": round(vol_ratio, 1),
        })

    return events


def trace_price_path(df: pd.DataFrame, entry_idx: int, max_days: int = 252) -> dict:
    """
    Trace the full price path from entry forward.
    Returns detailed day-by-day data for analysis.
    """
    n = len(df)
    entry_price = float(df["open"].iloc[entry_idx])
    if entry_price <= 0:
        return {}

    path = []
    highest_close = entry_price
    lowest_close = entry_price
    highest_high = entry_price
    peak_day = 0
    trough_day = 0

    # Track drawdown from peak
    max_drawdown_from_peak = 0
    drawdown_at_each_day = []

    # Track weekly closes for MA analysis
    weekly_closes = []

    for i in range(entry_idx, min(entry_idx + max_days + 1, n)):
        day_close = float(df["close"].iloc[i])
        day_high = float(df["high"].iloc[i])
        day_low = float(df["low"].iloc[i])
        hold_days = i - entry_idx

        gain_pct = (day_close - entry_price) / entry_price * 100
        mfe_pct = (highest_high - entry_price) / entry_price * 100
        dd_from_peak = (highest_close - day_close) / highest_close * 100 if highest_close > 0 else 0

        if day_high > highest_high:
            highest_high = day_high
            peak_day = hold_days

        if day_close > highest_close:
            highest_close = day_close

        if day_close < lowest_close:
            lowest_close = day_close
            trough_day = hold_days

        max_drawdown_from_peak = max(max_drawdown_from_peak, dd_from_peak)

        # 10-week (50-day) MA
        ma50 = None
        if i >= 50:
            ma50 = float(df["close"].iloc[i-49:i+1].mean())

        # 21-day EMA proxy (simple for now)
        ma21 = None
        if i >= 21:
            ma21 = float(df["close"].iloc[i-20:i+1].mean())

        path.append({
            "day": hold_days,
            "date": str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i]),
            "close": round(day_close, 2),
            "high": round(day_high, 2),
            "low": round(day_low, 2),
            "gain_pct": round(gain_pct, 1),
            "mfe_pct": round(mfe_pct, 1),
            "dd_from_peak_pct": round(dd_from_peak, 1),
            "ma50": round(ma50, 2) if ma50 else None,
            "ma21": round(ma21, 2) if ma21 else None,
        })

    if not path:
        return {}

    # Key milestones
    milestones = {}
    for target in [10, 20, 50, 100, 150, 200, 300, 500]:
        for p in path:
            if p["gain_pct"] >= target:
                milestones[f"days_to_{target}pct"] = p["day"]
                break

    # Drawdown analysis: what was the max pullback while still being a winner?
    # Find all drawdown episodes > 10%
    drawdown_episodes = []
    in_drawdown = False
    dd_start = 0
    for p in path:
        if p["dd_from_peak_pct"] >= 10 and not in_drawdown:
            in_drawdown = True
            dd_start = p["day"]
        elif p["dd_from_peak_pct"] < 5 and in_drawdown:
            in_drawdown = False
            drawdown_episodes.append({
                "start_day": dd_start,
                "end_day": p["day"],
                "duration": p["day"] - dd_start,
                "max_dd": max(x["dd_from_peak_pct"] for x in path if dd_start <= x["day"] <= p["day"]),
            })

    return {
        "entry_price": round(entry_price, 2),
        "peak_price": round(highest_high, 2),
        "peak_day": peak_day,
        "final_gain_pct": path[-1]["gain_pct"] if path else 0,
        "mfe_pct": round((highest_high - entry_price) / entry_price * 100, 1),
        "max_drawdown_from_peak": round(max_drawdown_from_peak, 1),
        "milestones": milestones,
        "drawdown_episodes": drawdown_episodes,
        "path": path,
    }


def simulate_exit_strategies(path: list, entry_price: float) -> dict:
    """
    Run multiple exit strategies on the same price path and compare results.
    """
    strategies = {}

    # Strategy 1: Tight trail (current live: 15% trail from peak)
    strategies["tight_15pct_trail"] = _sim_trail(path, entry_price, trail_pct=15, be_trigger=10, max_days=60)

    # Strategy 2: 10-week MA trail (current position strategy)
    strategies["10w_ma_trail"] = _sim_ma_trail(path, entry_price, ma_key="ma50", be_trigger=10, activate_pct=15, max_days=252)

    # Strategy 3: 21-day MA trail (tighter MA, faster exits)
    strategies["21d_ma_trail"] = _sim_ma_trail(path, entry_price, ma_key="ma21", be_trigger=10, activate_pct=10, max_days=252)

    # Strategy 4: Ratcheting trail (tighten as gain increases)
    strategies["ratchet_trail"] = _sim_ratchet(path, entry_price)

    # Strategy 5: Time-based scale out (sell 1/3 at +20%, 1/3 at +50%, let rest ride)
    strategies["scale_out"] = _sim_scale_out(path, entry_price)

    # Strategy 6: Chandelier exit (3 ATR from highest high)
    strategies["chandelier_3atr"] = _sim_chandelier(path, entry_price, atr_mult=3.0)

    # Strategy 7: "Never sell a winner" — hold max period, only stop at -25% from peak
    strategies["hold_max_25pct_stop"] = _sim_trail(path, entry_price, trail_pct=25, be_trigger=10, max_days=252)

    # Strategy 8: Hybrid — tight trail until +50%, then switch to 10w MA
    strategies["hybrid_tight_then_ma"] = _sim_hybrid(path, entry_price)

    return strategies


def _sim_trail(path: list, entry_price: float, trail_pct: float, be_trigger: float, max_days: int) -> dict:
    """Simple trailing stop from highest close."""
    highest = entry_price
    be_hit = False
    stop = 0  # no initial stop for this comparison

    for p in path:
        if p["day"] == 0:
            continue
        if p["day"] > max_days:
            return {"exit_day": max_days, "exit_gain": path[min(max_days, len(path)-1)]["gain_pct"], "exit_reason": "timeout"}

        close = entry_price * (1 + p["gain_pct"] / 100)
        highest = max(highest, close)
        gain = p["gain_pct"]

        if not be_hit and gain >= be_trigger:
            be_hit = True
            stop = entry_price

        if be_hit:
            trail_stop = highest * (1 - trail_pct / 100)
            stop = max(stop, trail_stop)

        low = entry_price * (1 + p["gain_pct"] / 100)  # approximate with close
        if be_hit and close <= stop:
            exit_gain = (stop - entry_price) / entry_price * 100
            return {"exit_day": p["day"], "exit_gain": round(exit_gain, 1), "exit_reason": "trail_stop"}

    last = path[-1] if path else {"day": 0, "gain_pct": 0}
    return {"exit_day": last["day"], "exit_gain": last["gain_pct"], "exit_reason": "timeout"}


def _sim_ma_trail(path: list, entry_price: float, ma_key: str, be_trigger: float,
                  activate_pct: float, max_days: int) -> dict:
    """Exit when close drops below MA after activation threshold."""
    be_hit = False
    ma_active = False

    for p in path:
        if p["day"] == 0:
            continue
        if p["day"] > max_days:
            break

        gain = p["gain_pct"]
        close = p["close"]
        ma_val = p.get(ma_key)

        if not be_hit and gain >= be_trigger:
            be_hit = True
        if not ma_active and gain >= activate_pct:
            ma_active = True

        # MA trail: exit on close below MA (check weekly = every 5 days)
        if ma_active and ma_val and p["day"] % 5 == 0:
            if close < ma_val:
                return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": "ma_trail"}

        # Hard stop: 25% from peak
        if be_hit and p["dd_from_peak_pct"] >= 25:
            # Approximate exit at 25% drawdown level
            exit_gain = gain  # close approximation
            return {"exit_day": p["day"], "exit_gain": round(exit_gain, 1), "exit_reason": "hard_stop"}

    last = path[-1] if path else {"day": 0, "gain_pct": 0}
    return {"exit_day": last["day"], "exit_gain": last["gain_pct"], "exit_reason": "timeout"}


def _sim_ratchet(path: list, entry_price: float) -> dict:
    """
    Ratcheting trail: tighten the stop as gains increase.
    0-20%: 20% trail
    20-50%: 15% trail
    50-100%: 12% trail
    100%+: 10% trail (protect the double)
    """
    highest = entry_price
    be_hit = False

    for p in path:
        if p["day"] == 0:
            continue
        if p["day"] > 252:
            break

        close = p["close"]
        gain = p["gain_pct"]
        highest_gain = p["mfe_pct"]

        if not be_hit and gain >= 10:
            be_hit = True

        if be_hit:
            # Determine trail % based on highest gain achieved
            if highest_gain >= 100:
                trail = 10
            elif highest_gain >= 50:
                trail = 12
            elif highest_gain >= 20:
                trail = 15
            else:
                trail = 20

            # Check if drawdown exceeds trail
            if p["dd_from_peak_pct"] >= trail:
                approx_exit_gain = highest_gain * (1 - trail / 100)  # rough estimate
                return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": f"ratchet_{trail}pct"}

    last = path[-1] if path else {"day": 0, "gain_pct": 0}
    return {"exit_day": last["day"], "exit_gain": last["gain_pct"], "exit_reason": "timeout"}


def _sim_scale_out(path: list, entry_price: float) -> dict:
    """
    Scale out: sell 1/3 at +30%, 1/3 at +100%, let final 1/3 ride with 20% trail.
    Weighted average exit.
    """
    portions = [
        {"target": 30, "size": 0.333, "filled": False, "exit_gain": 0},
        {"target": 100, "size": 0.333, "filled": False, "exit_gain": 0},
    ]
    remaining = 0.334  # final third
    highest = entry_price
    be_hit = False

    for p in path:
        if p["day"] == 0:
            continue
        if p["day"] > 252:
            break

        gain = p["gain_pct"]
        close = p["close"]
        highest = max(highest, close)

        for portion in portions:
            if not portion["filled"] and gain >= portion["target"]:
                portion["filled"] = True
                portion["exit_gain"] = gain
                portion["exit_day"] = p["day"]

        if not be_hit and gain >= 10:
            be_hit = True

        # Trail the remainder with 20% from peak
        if be_hit and remaining > 0 and p["dd_from_peak_pct"] >= 20:
            avg_gain = sum(po["exit_gain"] * po["size"] for po in portions if po["filled"]) + gain * remaining
            return {"exit_day": p["day"], "exit_gain": round(avg_gain, 1), "exit_reason": "scale_out_trail"}

    # End of period
    last_gain = path[-1]["gain_pct"] if path else 0
    avg_gain = sum(po["exit_gain"] * po["size"] for po in portions if po["filled"])
    unfilled = sum(po["size"] for po in portions if not po["filled"]) + remaining
    avg_gain += last_gain * unfilled
    last_day = path[-1]["day"] if path else 0
    return {"exit_day": last_day, "exit_gain": round(avg_gain, 1), "exit_reason": "timeout"}


def _sim_chandelier(path: list, entry_price: float, atr_mult: float) -> dict:
    """Chandelier exit: trail N * ATR from highest high."""
    be_hit = False

    for p in path:
        if p["day"] == 0 or p["day"] < 20:
            continue
        if p["day"] > 252:
            break

        gain = p["gain_pct"]
        if not be_hit and gain >= 10:
            be_hit = True

        # Approximate ATR as day range (we don't have true ATR here, use dd_from_peak as proxy)
        # A 3 ATR stop roughly equals ~15-20% from peak for volatile stocks
        if be_hit and p["dd_from_peak_pct"] >= atr_mult * 5:  # rough: 3 ATR ~ 15%
            return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": "chandelier"}

    last = path[-1] if path else {"day": 0, "gain_pct": 0}
    return {"exit_day": last["day"], "exit_gain": last["gain_pct"], "exit_reason": "timeout"}


def _sim_hybrid(path: list, entry_price: float) -> dict:
    """
    Hybrid: tight 15% trail until +50%, then switch to 10w MA trail.
    Best of both worlds: protect early gains, ride big winners.
    """
    highest = entry_price
    be_hit = False
    switched_to_ma = False

    for p in path:
        if p["day"] == 0:
            continue
        if p["day"] > 252:
            break

        gain = p["gain_pct"]
        close = p["close"]
        highest = max(highest, close)
        ma50 = p.get("ma50")

        if not be_hit and gain >= 10:
            be_hit = True

        # Phase 1: tight trail until +50%
        if be_hit and not switched_to_ma:
            if p["mfe_pct"] >= 50:
                switched_to_ma = True
            elif p["dd_from_peak_pct"] >= 15:
                return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": "tight_trail"}

        # Phase 2: 10w MA trail after +50%
        if switched_to_ma and ma50 and p["day"] % 5 == 0:
            if close < ma50:
                return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": "ma_trail"}
            # Hard stop 25% from peak
            if p["dd_from_peak_pct"] >= 25:
                return {"exit_day": p["day"], "exit_gain": round(gain, 1), "exit_reason": "hard_stop"}

    last = path[-1] if path else {"day": 0, "gain_pct": 0}
    return {"exit_day": last["day"], "exit_gain": last["gain_pct"], "exit_reason": "timeout"}


def analyze_winner(ticker: str, start: str, end: str, desc: str) -> dict:
    """Full analysis of one EP winner."""
    print(f"\n{'='*60}")
    print(f"  Analyzing {ticker} ({desc})")
    print(f"{'='*60}")

    df = fetch_daily_bars(ticker, start, end)
    if df.empty:
        print(f"  No data for {ticker}")
        return {}

    print(f"  Got {len(df)} bars from {df.index[0].date()} to {df.index[-1].date()}")

    # Find EP events
    events = detect_ep_events(df, ticker, min_gap=8.0)
    print(f"  Found {len(events)} EP events")

    if not events:
        # Try with lower threshold
        events = detect_ep_events(df, ticker, min_gap=5.0)
        print(f"  Retry with 5% gap: found {len(events)} events")

    if not events:
        return {"ticker": ticker, "error": "no_ep_events", "bars": len(df)}

    # For each EP event, trace path and test strategies
    best_event = None
    best_mfe = 0

    results = []
    for ev in events:
        entry_idx = ev["idx"] + 1  # enter next day
        if entry_idx >= len(df):
            continue

        trace = trace_price_path(df, entry_idx, max_days=252)
        if not trace or not trace.get("path"):
            continue

        mfe = trace["mfe_pct"]
        if mfe > best_mfe:
            best_mfe = mfe
            best_event = ev

        # Only analyze events with significant moves
        if mfe < 20:
            continue

        strategies = simulate_exit_strategies(trace["path"], trace["entry_price"])

        result = {
            "ep_date": ev["date"],
            "gap_pct": ev["gap_pct"],
            "vol_ratio": ev["vol_ratio"],
            "intraday_move": ev["intraday_move_pct"],
            "entry_price": trace["entry_price"],
            "mfe_pct": trace["mfe_pct"],
            "peak_day": trace["peak_day"],
            "max_dd_from_peak": trace["max_drawdown_from_peak"],
            "milestones": trace["milestones"],
            "drawdown_episodes": trace["drawdown_episodes"],
            "strategies": strategies,
        }
        results.append(result)

        print(f"\n  EP on {ev['date']}: gap {ev['gap_pct']}%, vol {ev['vol_ratio']}x")
        print(f"    MFE: +{trace['mfe_pct']:.0f}% (peak day {trace['peak_day']})")
        print(f"    Max DD from peak: -{trace['max_drawdown_from_peak']:.0f}%")
        if trace.get("milestones"):
            for m, d in sorted(trace["milestones"].items()):
                print(f"    {m}: {d} days")
        print(f"    Strategy comparison:")
        for name, strat in sorted(strategies.items()):
            print(f"      {name:25s}: +{strat['exit_gain']:6.1f}% in {strat['exit_day']:3d}d ({strat['exit_reason']})")

    return {
        "ticker": ticker,
        "description": desc,
        "total_bars": len(df),
        "ep_events": len(events),
        "analyzed_events": len(results),
        "best_mfe": round(best_mfe, 1),
        "results": results,
    }


def run_full_analysis():
    """Run analysis on all known winners and produce summary."""
    print("=" * 70)
    print("  EP WINNER REVERSE-ENGINEERING ANALYSIS")
    print("  Studying price paths of biggest EP movers to find optimal exit")
    print("=" * 70)

    all_results = []
    for ticker, start, end, desc in WINNERS_TO_STUDY:
        result = analyze_winner(ticker, start, end, desc)
        if result and result.get("results"):
            all_results.append(result)

    print("\n\n")
    print("=" * 70)
    print("  SUMMARY: STRATEGY COMPARISON ACROSS ALL BIG WINNERS")
    print("=" * 70)

    # Aggregate strategy performance across all events
    strategy_totals = {}
    total_events = 0

    for result in all_results:
        for event in result["results"]:
            total_events += 1
            mfe = event["mfe_pct"]
            for strat_name, strat_result in event["strategies"].items():
                if strat_name not in strategy_totals:
                    strategy_totals[strat_name] = {
                        "gains": [],
                        "days": [],
                        "capture_rates": [],
                        "mfes": [],
                    }
                st = strategy_totals[strat_name]
                st["gains"].append(strat_result["exit_gain"])
                st["days"].append(strat_result["exit_day"])
                st["mfes"].append(mfe)
                if mfe > 0:
                    st["capture_rates"].append(strat_result["exit_gain"] / mfe * 100)

    print(f"\nTotal EP events analyzed: {total_events}")
    print(f"Tickers studied: {len(all_results)}")
    print()

    # Print comparison table
    print(f"{'Strategy':<28s} {'Avg Gain':>9s} {'Med Gain':>9s} {'Avg Days':>9s} {'Capture%':>9s} {'100%+ Hits':>10s}")
    print("-" * 85)

    strategy_rankings = []
    for name, st in sorted(strategy_totals.items()):
        gains = np.array(st["gains"])
        days = np.array(st["days"])
        captures = np.array(st["capture_rates"])
        big_wins = sum(1 for g in gains if g >= 100)

        avg_gain = np.mean(gains)
        med_gain = np.median(gains)
        avg_days = np.mean(days)
        avg_capture = np.mean(captures) if len(captures) > 0 else 0

        print(f"{name:<28s} {avg_gain:>+8.1f}% {med_gain:>+8.1f}% {avg_days:>8.0f}d {avg_capture:>8.0f}% {big_wins:>10d}")

        strategy_rankings.append({
            "name": name,
            "avg_gain": round(avg_gain, 1),
            "median_gain": round(med_gain, 1),
            "avg_days": round(avg_days, 0),
            "avg_capture": round(avg_capture, 1),
            "big_wins_100pct": big_wins,
            "total_events": len(gains),
        })

    # Sort by avg gain and show ranking
    strategy_rankings.sort(key=lambda x: x["avg_gain"], reverse=True)
    print(f"\n{'─'*70}")
    print("RANKING by average gain:")
    for i, s in enumerate(strategy_rankings, 1):
        print(f"  #{i}: {s['name']} → +{s['avg_gain']:.1f}% avg, {s['avg_capture']:.0f}% capture, {s['big_wins_100pct']} 100%+ winners")

    # Common characteristics of biggest winners
    print(f"\n\n{'='*70}")
    print("  COMMON TRAITS OF 100%+ EP WINNERS")
    print(f"{'='*70}")

    big_winner_traits = []
    for result in all_results:
        for event in result["results"]:
            if event["mfe_pct"] >= 100:
                big_winner_traits.append({
                    "ticker": result["ticker"],
                    "sector": result["description"],
                    "gap_pct": event["gap_pct"],
                    "vol_ratio": event["vol_ratio"],
                    "mfe_pct": event["mfe_pct"],
                    "peak_day": event["peak_day"],
                    "max_dd": event["max_dd_from_peak"],
                    "drawdown_episodes": len(event["drawdown_episodes"]),
                    "milestones": event["milestones"],
                })

    if big_winner_traits:
        gaps = [t["gap_pct"] for t in big_winner_traits]
        vols = [t["vol_ratio"] for t in big_winner_traits]
        peaks = [t["peak_day"] for t in big_winner_traits]
        dds = [t["max_dd"] for t in big_winner_traits]
        dd_eps = [t["drawdown_episodes"] for t in big_winner_traits]

        print(f"\n  Found {len(big_winner_traits)} EP events with 100%+ MFE:")
        print(f"  Gap %:        avg {np.mean(gaps):.0f}%, median {np.median(gaps):.0f}%, range {np.min(gaps):.0f}-{np.max(gaps):.0f}%")
        print(f"  Vol ratio:    avg {np.mean(vols):.0f}x, median {np.median(vols):.0f}x, range {np.min(vols):.0f}-{np.max(vols):.0f}x")
        print(f"  Peak day:     avg {np.mean(peaks):.0f}d, median {np.median(peaks):.0f}d, range {np.min(peaks):.0f}-{np.max(peaks):.0f}d")
        print(f"  Max DD:       avg {np.mean(dds):.0f}%, median {np.median(dds):.0f}%, range {np.min(dds):.0f}-{np.max(dds):.0f}%")
        print(f"  DD episodes:  avg {np.mean(dd_eps):.1f}, range {np.min(dd_eps)}-{np.max(dd_eps)}")

        print(f"\n  Key insight: Big winners tolerate drawdowns of up to {np.percentile(dds, 75):.0f}% (75th pct)")
        print(f"  and take {np.median(peaks):.0f} days (median) to reach peak")

        # Time to milestones
        all_milestones = {}
        for t in big_winner_traits:
            for m, d in t["milestones"].items():
                if m not in all_milestones:
                    all_milestones[m] = []
                all_milestones[m].append(d)

        if all_milestones:
            print(f"\n  Time to milestones (100%+ winners):")
            for m in sorted(all_milestones.keys()):
                vals = all_milestones[m]
                print(f"    {m}: avg {np.mean(vals):.0f}d, median {np.median(vals):.0f}d ({len(vals)} stocks reached)")

    # Save full results
    output = {
        "analysis_date": datetime.now().isoformat(),
        "total_tickers": len(all_results),
        "total_events": total_events,
        "strategy_rankings": strategy_rankings,
        "big_winner_traits": big_winner_traits,
        "detailed_results": [],
    }
    for r in all_results:
        # Exclude full path data to keep file manageable
        detail = {k: v for k, v in r.items()}
        for event in detail.get("results", []):
            if "strategies" in event:
                # Keep strategies but remove path data
                pass
        output["detailed_results"].append(detail)

    output_path = Path(__file__).parent / "ep_winner_analysis_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Full results saved to {output_path}")

    return output


if __name__ == "__main__":
    run_full_analysis()
