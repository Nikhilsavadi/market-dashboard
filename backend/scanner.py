"""
scanner.py - V2
---------------
Full scan pipeline with all V2 improvements:
- ATR-based proximity (via screener)
- Signal scoring 1-10
- Watchlist tiers
- Pre-earnings gate (default on)
- Duplicate detection (already in journal)
- RS line per signal
- Enhanced market regime (VIX + breadth + 200MA distance)
- Position sizing on every signal
- Journal feedback loop
"""

import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import pandas as pd
import yfinance as yf
from fetch_utils import fetch_bars_batch

from screener import (
    analyse_stock, calculate_1y_return, is_long_signal, is_short_signal,
    passes_earnings_gate, is_duplicate, calculate_signal_score,
    _calculate_weighted_rs_score,
)
from historical_bt import _is_weekly_signal
from base_detector import detect_base
from sector_rs import calculate_sector_rs, SECTOR_ETFS, get_sector, get_theme, get_theme_score_bonus, get_sector_rotation_bias, apply_sector_bias_to_signals
from priority_rank import get_top_picks, rank_signals, get_top_short_picks
from earnings import batch_earnings
from breakout import detect_cup_and_handle, detect_extended_breakout, detect_weekly_breakout_retest
from patterns import scan_all_patterns
from options_flow import batch_options_flow, options_flag
from news import batch_news
from alerts import send_scan_alert
from market_regime import enhanced_market_conditions, REGIME_ETFS
from database import init_db, save_signal_history, journal_list
from watchlist import ALL_TICKERS, ETFS, BENCHMARK, TICKER_TIER, TIER_ALERT_THRESHOLD
from universe_expander import get_scan_universe
from settings import get_settings, calculate_position_size, calculate_portfolio_heat

CACHE_FILE  = Path(__file__).parent / "cache.json"
BATCH_SIZE  = 50
LOOKBACK_DAYS = 380
WEEKLY_LOOKBACK_DAYS = 380 * 2  # ~2 years of weekly bars for wEMA40 (needs 40 weeks minimum)

ALL_ETFS = list(set(ETFS + list(SECTOR_ETFS.values()) + [BENCHMARK] + REGIME_ETFS))


def fetch_weekly_bars(client, tickers: list) -> dict:
    """
    Fetch weekly OHLCV bars for HTF confirmation.
    Provider priority: Polygon → yfinance fallback.
    """
    import os
    if os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_weekly_bars as pg_weekly
            return pg_weekly(tickers, weeks=104, min_rows=10)
        except Exception as e:
            print(f"[scanner] Polygon weekly failed ({e}) — falling back to yfinance")
    return fetch_bars_batch(
        tickers,
        period    = "2y",
        interval  = "1wk",
        min_rows  = 10,
        batch_size= 50,
        label     = "scanner/weekly",
    )


# Global scan lock — prevents concurrent scans doubling Yahoo request rate
_SCAN_LOCK = threading.Lock()


def get_alpaca_client():
    """
    Returns a dummy sentinel — kept for API compatibility.
    All data fetching now uses yfinance. Alpaca keys no longer required.
    """
    return None


def fetch_bars(client, tickers: list) -> dict:
    """
    Fetch daily OHLCV bars for the full universe.
    Provider priority: Polygon → yfinance fallback.
    """
    import os
    if os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_bars as pg_bars
            return pg_bars(tickers, days=LOOKBACK_DAYS, interval="day", min_rows=20, label="scanner")
        except Exception as e:
            print(f"[scanner] Polygon daily failed ({e}) — falling back to yfinance")
    return fetch_bars_batch(
        tickers,
        period    = f"{LOOKBACK_DAYS}d",
        interval  = "1d",
        min_rows  = 20,
        batch_size= 50,
        label     = "scanner",
    )


def run_scan() -> dict:
    # Prevent concurrent scans — two simultaneous runs double Yahoo request rate
    if not _SCAN_LOCK.acquire(blocking=False):
        print("[scanner] Scan already running — ignoring concurrent trigger")
        try:
            from database import get_last_scan
            cached = get_last_scan()
            if cached:
                return cached
        except Exception:
            pass
        return {}

    try:
        return _run_scan_inner()
    finally:
        _SCAN_LOCK.release()


def _run_scan_inner() -> dict:
    print(f"\n[scanner] === V2 Scan started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    t0 = time.time()
    init_db()

    # Load settings
    settings = get_settings()
    hide_earnings_lt = settings.get("hide_earnings_lt_days", 14)
    min_signal_score = settings.get("min_signal_score", 6)
    market_gate_longs  = settings.get("market_gate_longs", 45)

    client = get_alpaca_client()

    # 1. Fetch daily bars
    stock_tickers = [t for t in get_scan_universe() if t not in ALL_ETFS]
    bars_data     = fetch_bars(client, stock_tickers + ALL_ETFS)
    if not bars_data:
        print("[scanner] No data — aborting")
        return {}

    # ── Ensure critical regime ETFs are always present ───────────────────────
    missing_etfs = [e for e in ALL_ETFS if e not in bars_data]
    if missing_etfs:
        print(f"[scanner] Re-fetching {len(missing_etfs)} missing ETFs: {missing_etfs[:8]}...")
        import os as _os
        if _os.environ.get("POLYGON_API_KEY"):
            try:
                from polygon_client import fetch_bars as _pg
                etf_data = _pg(missing_etfs, days=LOOKBACK_DAYS, interval="day",
                               min_rows=20, label="etf-retry")
            except Exception as _e:
                print(f"[scanner] Polygon ETF retry failed ({_e}) — using yfinance")
                etf_data = fetch_bars_batch(
                    missing_etfs, period=f"{LOOKBACK_DAYS}d", interval="1d",
                    min_rows=20, batch_size=len(missing_etfs), label="etf-retry",
                )
        else:
            import time as _time; _time.sleep(5)
            etf_data = fetch_bars_batch(
                missing_etfs, period=f"{LOOKBACK_DAYS}d", interval="1d",
                min_rows=20, batch_size=len(missing_etfs), label="etf-retry",
            )
        bars_data.update(etf_data)
        still_missing = [e for e in ALL_ETFS if e not in bars_data]
        if still_missing:
            print(f"[scanner] Still missing after retry: {still_missing}")
        else:
            print(f"[scanner] All ETFs now present")

    # SPY closes for RS line + Mansfield RS calculation
    spy_closes = bars_data.get("SPY", {}).get("close") if "SPY" in bars_data else None

    # 1b. Fetch weekly bars — Tier 1 only, run in parallel with market conditions
    # Tier 2/3 names rarely signal on weekly confirmation; screener falls back to
    # resampling daily bars when weekly_df is None — no data loss, big time saving.
    # Skip entirely on weekends (weekly bars are identical to Friday's).
    today_weekday = datetime.now().weekday()  # 0=Mon … 6=Sun
    is_weekend = today_weekday >= 5
    tier1_for_weekly = [t for t in stock_tickers if TICKER_TIER.get(t, 2) == 1]

    weekly_bars: dict = {}
    _weekly_future = None

    if is_weekend:
        print("[scanner] Weekend — skipping weekly bars fetch (no new data since Friday)")
    else:
        print(f"[scanner] Fetching weekly bars for {len(tier1_for_weekly)} Tier 1 tickers "
              f"(was {len(stock_tickers)}) in background thread...")
        _weekly_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="weekly")
        _weekly_future = _weekly_executor.submit(fetch_weekly_bars, client, tier1_for_weekly)

    # 2. Enhanced market conditions
    print("[scanner] Calculating market conditions...")
    market = enhanced_market_conditions(bars_data, set(ALL_ETFS))
    market_score = market.get("score", 50)
    market_label = market.get("label", "Neutral")

    # 2b. Regime gate + change detection
    from market_regime import check_regime_change, score_to_gate, GATE_MODE, GATE_SIZE
    regime_change = check_regime_change(market_score)
    regime_gate   = regime_change["new_gate"]    # GO / CAUTION / WARN / DANGER
    regime_mode   = regime_change["mode"]        # LONGS / SELECTIVE / EXITS_ONLY / SHORTS
    size_mult     = regime_change["size"]
    market["gate"]      = regime_gate
    market["mode"]      = regime_mode
    market["size_mult"] = size_mult
    print(f"[scanner] Regime: {regime_gate} ({regime_mode}) size×{size_mult}"
          + (f" — CHANGED from {regime_change['old_gate']}" if regime_change["changed"] else ""))

    # 1c. Collect weekly bars result (background thread started before market conditions)
    if _weekly_future is not None:
        try:
            weekly_bars = _weekly_future.result(timeout=300)  # wait up to 5 min
            _weekly_executor.shutdown(wait=False)
            print(f"[scanner] Weekly bars ready: {len(weekly_bars)} tickers")
        except Exception as e:
            print(f"[scanner] Weekly bars fetch failed: {e} — continuing without HTF")
            weekly_bars = {}

    # 3. Mansfield-weighted RS universe
    # Build the raw weighted RS score for every stock — used to rank each ticker
    # relative to the full universe (replaces simple 1Y return percentile)
    print("[scanner] Calculating Mansfield RS universe...")
    all_weighted_rs = []
    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue
        score = _calculate_weighted_rs_score(df["close"], spy_closes)
        if score is not None:
            all_weighted_rs.append(score)

    # 4. Get open journal tickers for duplicate detection
    open_entries = journal_list(status="watching") + journal_list(status="open")
    open_tickers = {e["ticker"] for e in open_entries}
    print(f"[scanner] {len(open_tickers)} tickers already in journal (will suppress duplicates in alerts)")

    # 5. Screener — pass weekly bars, SPY closes, and market score
    print("[scanner] Running screener...")
    MIN_PRICE   = settings.get("min_price", 5.0)
    MIN_AVG_VOL = settings.get("min_avg_vol", 200_000)

    raw_results   = []
    skipped_price = 0
    skipped_vol   = 0
    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue

        # Price filter — skip penny stocks
        try:
            last_price = float(df["close"].iloc[-1])
            if last_price < MIN_PRICE:
                skipped_price += 1
                continue
        except Exception:
            pass

        # Volume filter — skip thinly traded (20-day avg vol)
        try:
            avg_vol = float(df["volume"].tail(20).mean())
            if avg_vol < MIN_AVG_VOL:
                skipped_vol += 1
                continue
        except Exception:
            pass

        tier       = TICKER_TIER.get(ticker, 2)
        weekly_df  = weekly_bars.get(ticker)   # None if fetch failed — screener falls back to resampling
        result = analyse_stock(ticker, df, all_weighted_rs, spy_closes, market_score, tier, weekly_df)
        if result:
            raw_results.append(result)

    print(f"[scanner] Analysed {len(raw_results)} stocks "
          f"(skipped {skipped_price} <${MIN_PRICE}, {skipped_vol} <{MIN_AVG_VOL//1000}k avg vol)")

    # 6. Base detection + sector / theme tagging
    print("[scanner] Detecting bases + sectors + themes...")
    for result in raw_results:
        ticker = result["ticker"]
        if ticker in bars_data:
            base_info = detect_base(bars_data[ticker])
            result.update(base_info)
        result["sector"] = get_sector(ticker)
        result["theme"]  = get_theme(ticker)

    # 7. Sector RS
    print("[scanner] Calculating sector RS...")
    sector_rs = calculate_sector_rs(bars_data)
    for result in raw_results:
        sector = result.get("sector", "Technology")
        s_data = sector_rs.get(sector, {})
        result["sector_rs_rank"] = s_data.get("rank")
        result["sector_trend"]   = s_data.get("trend")
        result["sector_rs_1m"]   = s_data.get("rs_vs_spy_1m")
        result["sector_aligned"]  = (s_data.get("rs_vs_spy_1m") or 0) > 0

    # 7b. Sector rotation bias signal
    rotation_bias = get_sector_rotation_bias(sector_rs)
    if rotation_bias.get("rotation_alert"):
        print(f"[scanner] {rotation_bias['rotation_alert']}")
    # Apply sector bias adjustments to raw results (small score nudge ±0.5)
    raw_results = apply_sector_bias_to_signals(raw_results, sector_rs)

    # 8. Compute signal score now that we have all dimensions
    for result in raw_results:
        result["signal_score"] = calculate_signal_score(
            rs               = result.get("rs", 50),
            vcs              = result.get("vcs"),
            base_score       = result.get("base_score", 0),
            vol_ratio        = result.get("vol_ratio"),
            sector_rs_rank   = result.get("sector_rs_rank"),
            market_score     = market_score,
            earnings_days    = result.get("days_to_earnings"),
            tier             = result.get("tier", 2),
            bouncing_from    = result.get("bouncing_from"),
            pct_from_52w_high= result.get("pct_from_52w_high"),
            ma21_slope       = result.get("ma21_slope"),
            ma50_slope       = result.get("ma50_slope"),
            coiling          = result.get("coiling", False),
            ll_hl_detected   = result.get("ll_hl_detected", False),
            approaching_pivot= result.get("approaching_pivot", False),
            darvas_detected  = result.get("darvas_detected", False),
            theme            = result.get("theme"),
            sector_rs_data   = sector_rs,
            flag_detected    = result.get("flag_detected", False),
            flag_status      = result.get("flag_status"),
            darvas_status    = result.get("darvas_status"),
            w_stack_ok       = result.get("w_stack_ok", False),
            is_weekly_signal = _is_weekly_signal(result),
        )

    # 9. Filter signals — regime-aware routing
    # GO:       full long playbook, normal RS filter
    # CAUTION:  longs with tighter RS (>85) and tier-1 only
    # WARN:     no new longs (empty list), shorts only
    # DANGER:   no longs, shorts prioritised

    if regime_mode == "LONGS":
        long_candidates  = [s for s in raw_results if is_long_signal(s, settings)]
    elif regime_mode == "SELECTIVE":
        selective_settings = {**settings, "rs_filter": max(settings.get("rs_filter", 70), 85)}
        long_candidates  = [
            s for s in raw_results
            if is_long_signal(s, selective_settings) and s.get("tier", 99) <= 1
        ]
    else:
        # EXITS_ONLY or SHORTS — no new long signals
        long_candidates  = []

    short_candidates = [s for s in raw_results if is_short_signal(s)]
    # In DANGER mode, surface more shorts (relax score threshold slightly)
    if regime_mode == "SHORTS":
        short_candidates = [
            s for s in raw_results
            if s.get("pct_from_ma21") is not None and s["pct_from_ma21"] < 0
            and s.get("rs", 100) <= 40
            and s.get("short_score", 0) >= 40
        ]

    # 9b. Cup & Handle + Extended Breakout watchlist
    print("[scanner] Detecting cup & handle patterns and extended breakouts...")
    cup_handle_signals        = []
    extended_bo_signals       = []
    weekly_bo_retest_signals  = []

    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue
        rs_match = next((s for s in raw_results if s["ticker"] == ticker), None)
        if not rs_match:
            continue
        rs_rank = rs_match.get("rs", 0) or 0
        vcs_val = rs_match.get("vcs")
        ma10    = rs_match.get("ma10")
        ma21    = rs_match.get("ma21")

        # Cup & Handle — actionable setups
        ch = detect_cup_and_handle(ticker, df, rs_rank, vcs_val)
        if ch:
            ch["sector"] = get_sector(ticker)
            ch["tier"]   = TICKER_TIER.get(ticker, 2)
            ch["ma10"]   = ma10
            ch["ma21"]   = ma21
            ch["ma50"]   = rs_match.get("ma50")
            cup_handle_signals.append(ch)

        # Extended breakout watchlist
        ext = detect_extended_breakout(ticker, df, rs_rank, vcs_val, ma10, ma21)
        if ext:
            ext["sector"] = get_sector(ticker)
            ext["tier"]   = TICKER_TIER.get(ticker, 2)
            extended_bo_signals.append(ext)

        # Weekly breakout retest (uses weekly bars)
        if weekly_df is not None:
            wbr = detect_weekly_breakout_retest(ticker, weekly_df, rs_rank, vcs_val)
            if wbr is not None:
                # Enrich with readiness fields from daily
                wbr["entry_readiness"] = signals.get("entry_readiness")
                wbr["adr_pct"]         = signals.get("adr_pct")
                wbr["ema21_low_pct"]   = signals.get("ema21_low_pct")
                wbr["three_weeks_tight"] = signals.get("three_weeks_tight")
                wbr["sector"]          = signals.get("sector", "")
                weekly_bo_retest_signals.append(wbr)

    cup_handle_signals.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
    # Sort extended by watch_status urgency then pct_from_ma10
    status_order = {"approaching_ma10": 0, "approaching_ma21": 1, "extended_ma10": 2, "extended": 3}
    extended_bo_signals.sort(key=lambda x: (status_order.get(x.get("watch_status","extended"), 3), x.get("pct_from_ma10") or 99))
    weekly_bo_retest_signals.sort(key=lambda x: x.get("signal_score", 0), reverse=True)

    # Keep combined for backward compat
    breakout_signals = cup_handle_signals  # primary breakout list is now C&H

    print(f"[scanner] {len(cup_handle_signals)} cup & handle, {len(extended_bo_signals)} extended breakouts, {len(weekly_bo_retest_signals)} weekly retests")

    # 9c. Chart pattern detection — Flag, VCP, Cup & Handle, Ascending Triangle
    print("[scanner] Detecting chart patterns...")
    pattern_signals = []
    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue
        rs_match = next((s for s in raw_results if s["ticker"] == ticker), None)
        if not rs_match:
            continue
        rs_rank = rs_match.get("rs", 0)
        vcs_val = rs_match.get("vcs")
        if rs_rank < 65:  # skip weak RS names
            continue
        patterns = scan_all_patterns(ticker, df, rs_rank, vcs_val)
        for p in patterns:
            p["sector"] = get_sector(ticker)
            p["tier"]   = TICKER_TIER.get(ticker, 2)
            p["ma10"]   = rs_match.get("ma10")
            p["ma21"]   = rs_match.get("ma21")
            p["ma50"]   = rs_match.get("ma50")
            pattern_signals.append(p)

    pattern_signals.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
    print(f"[scanner] {len(pattern_signals)} pattern signals "
          f"({sum(1 for p in pattern_signals if p['pattern_type']=='FLAG')} flags, "
          f"{sum(1 for p in pattern_signals if p['pattern_type']=='VCP')} vcps, "
          f"{sum(1 for p in pattern_signals if p['pattern_type']=='CUP_HANDLE')} cups, "
          f"{sum(1 for p in pattern_signals if p['pattern_type']=='ASC_TRIANGLE')} triangles)")

    # 10. Earnings — fetch for candidates + top RS pipeline stocks
    pipeline_tickers = [
        s["ticker"] for s in raw_results
        if (s.get("rs") or 0) >= 80 and not s.get("ma10_touch") and not s.get("ma21_touch") and not s.get("ma50_touch")
    ][:40]  # top 40 pipeline names
    all_candidate_tickers = list(set(
        [s["ticker"] for s in long_candidates[:25]] +
        [s["ticker"] for s in short_candidates[:15]] +
        pipeline_tickers
    ))
    print(f"[scanner] Fetching earnings for {len(all_candidate_tickers)} tickers...")
    earnings_data = batch_earnings(all_candidate_tickers, delay=0.1)
    for s in raw_results:
        if s["ticker"] in earnings_data:
            s.update(earnings_data[s["ticker"]])
            # Recompute signal score with earnings data now available
            s["signal_score"] = calculate_signal_score(
                rs               = s.get("rs", 50),
                vcs              = s.get("vcs"),
                base_score       = s.get("base_score", 0),
                vol_ratio        = s.get("vol_ratio"),
                sector_rs_rank   = s.get("sector_rs_rank"),
                market_score     = market_score,
                earnings_days    = s.get("days_to_earnings"),
                tier             = s.get("tier", 2),
                bouncing_from    = s.get("bouncing_from"),
                pct_from_52w_high= s.get("pct_from_52w_high"),
                ma21_slope       = s.get("ma21_slope"),
                ma50_slope       = s.get("ma50_slope"),
                coiling          = s.get("coiling", False),
                ll_hl_detected   = s.get("ll_hl_detected", False),
                approaching_pivot= s.get("approaching_pivot", False),
                darvas_detected  = s.get("darvas_detected", False),
                darvas_status    = s.get("darvas_status"),
                w_stack_ok       = s.get("w_stack_ok", False),
                is_weekly_signal = _is_weekly_signal(s),
            )

    # 10b. Options flow for top long candidates + breakouts
    options_tickers = list(set(
        [s["ticker"] for s in long_candidates[:15]] +
        [s["ticker"] for s in breakout_signals[:10]] +
        [s["ticker"] for s in pattern_signals[:15]]
    ))
    print(f"[scanner] Fetching options flow for {len(options_tickers)} tickers...")
    options_data = batch_options_flow(options_tickers, delay=0.25)
    # Attach options flag to signals
    for s in long_candidates + breakout_signals + pattern_signals:
        flow = options_data.get(s["ticker"])
        s["options_flag"]    = options_flag(flow)
        s["options_cp_ratio"] = flow.get("cp_ratio") if flow else None
        s["options_sweeps"]   = flow.get("has_sweeps", False) if flow else False

    # 11. Apply earnings gate and min score filter
    long_signals = [
        s for s in long_candidates
        if passes_earnings_gate(s, hide_earnings_lt)
        and (s.get("signal_score") or 0) >= min_signal_score
    ]
    short_signals = [
        s for s in short_candidates
        if passes_earnings_gate(s, hide_earnings_lt)
    ]

    # 12. Add position sizing to every long signal
    for s in long_signals:
        if s.get("stop_price") and s.get("price"):
            pos = calculate_position_size(s["price"], s["stop_price"])
            s["position"] = pos

    # 13. Sort — by signal score desc, then VCS asc for tiebreak
    long_signals  = sorted(long_signals,  key=lambda s: (-(s.get("signal_score") or 0), s.get("vcs") or 10))
    short_signals = sorted(short_signals, key=lambda s: -(s.get("short_score") or 0))

    # MA bounce sub-lists
    ma10_bounces = [s for s in long_signals if s.get("ma10_touch")]
    ma21_bounces = [s for s in long_signals if s.get("ma21_touch") and not s.get("ma10_touch")]
    ma50_bounces = [s for s in long_signals if s.get("ma50_touch") and not s.get("ma10_touch") and not s.get("ma21_touch")]

    # EP Delayed Reaction setups — from all raw results (not just long_signals)
    # EP setups don't require VCP-style MA touch — they have their own entry logic
    ep_signals = sorted(
        [s for s in raw_results if s.get("ep_detected")],
        key=lambda s: (
            -int(s.get("ep_entry_ok", False)),  # entry-ready first
            s.get("ep_days_ago") or 99,          # most recent EP day first
            -(s.get("ep_gap_pct") or 0),         # largest gap first
        )
    )
    print(f"[scanner] EP setups: {len(ep_signals)} detected "
          f"({sum(1 for s in ep_signals if s.get('ep_entry_ok'))} entry-ready)")

    # HVE Retest setups
    hve_signals = sorted(
        [s for s in raw_results if s.get("hve_detected")],
        key=lambda s: (
            -int(s.get("hve_entry_ok", False)),       # entry-ready first
            s.get("hve_days_since_gap") or 999,       # most recent gap first
            -(s.get("hve_gap_pct") or 0),             # largest gap first
        )
    )
    print(f"[scanner] HVE retest setups: {len(hve_signals)} detected "
          f"({sum(1 for s in hve_signals if s.get('hve_entry_ok'))} entry-ready)")

    # "Setup of the Day" — highest scoring non-duplicate
    non_dup_longs = [s for s in long_signals if not s.get("is_duplicate")]
    sotd_long  = non_dup_longs[0] if non_dup_longs else None
    sotd_short = short_signals[0] if short_signals else None

    # 14. News for top signals
    news_tickers = list(set(
        [s["ticker"] for s in long_signals[:10]] +
        [s["ticker"] for s in short_signals[:8]]
    ))
    print(f"[scanner] Fetching news for {len(news_tickers)} tickers...")
    news_data = batch_news(news_tickers)
    for s in long_signals + short_signals:
        s["news"] = news_data.get(s["ticker"], [])

    # 15. Portfolio heat
    portfolio_heat = calculate_portfolio_heat(open_entries)

    # 16. Save signal history
    scan_date   = date.today().isoformat()
    all_signals = long_signals + short_signals
    if all_signals:
        save_signal_history(scan_date, all_signals)

    elapsed = round(time.time() - t0, 1)
    print(f"[scanner] === Complete in {elapsed}s — {len(long_signals)} longs, {len(short_signals)} shorts ===\n")

    payload = {
        "scanned_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "scan_duration_s":   elapsed,
        "total_scanned":     len(raw_results),
        "market":            market,
        "sector_rs":         sector_rs,
        "sector_rotation":   rotation_bias,
        "long_signals":      long_signals,
        "short_signals":     short_signals[:30],
        "ma10_bounces":      ma10_bounces,
        "ma21_bounces":      ma21_bounces,
        "ma50_bounces":      ma50_bounces,
        "sotd_long":         sotd_long,
        "sotd_short":        sotd_short,
        "portfolio_heat":    portfolio_heat,
        "open_tickers":      list(open_tickers),
        "cup_handle_signals":         cup_handle_signals[:25],
        "extended_bo_signals":        extended_bo_signals[:30],
        "weekly_bo_retest_signals":   weekly_bo_retest_signals[:30],
        "pattern_signals":   pattern_signals[:40],
        "ep_signals":        ep_signals[:40],
        "hve_signals":       hve_signals[:40],
        "all_stocks":        sorted(raw_results, key=lambda s: -(s.get("rs") or 0)),
        "settings":          settings,
    }

    # 16b. Stockbee EP scan — runs in same scan cycle using existing bars
    try:
        from stockbee_ep import (
            run_ep_scan, fetch_fundamentals_batch,
            init_ep_watchlist_table, update_ep_watchlist
        )
        init_ep_watchlist_table()

        # Fetch fundamentals for EP candidates (stocks with gaps or high volume)
        ep_candidate_tickers = list(set(
            [s["ticker"] for s in ep_signals[:20]] +
            [s["ticker"] for s in raw_results
             if s.get("vol_ratio") and s["vol_ratio"] >= 2.0][:30]
        ))
        print(f"[scanner] Fetching fundamentals for {len(ep_candidate_tickers)} EP candidates...")
        ep_fund = fetch_fundamentals_batch(ep_candidate_tickers, delay=0.15)

        # Run full EP scan
        ep_result = run_ep_scan(bars_data, ep_fund)
        payload["stockbee_ep"] = ep_result

        # Update EP watchlist with current prices
        ep_alerts = update_ep_watchlist(bars_data)
        if ep_alerts:
            print(f"[scanner] EP Watchlist alerts: {len(ep_alerts)} breakout signals!")
            payload["stockbee_ep"]["watchlist_alerts"] = ep_alerts

        print(f"[scanner] Stockbee EP scan: {ep_result.get('summary', {})}")
    except Exception as e:
        print(f"[scanner] Stockbee EP scan error: {e}")
        import traceback; traceback.print_exc()

    # 17. Write cache
    CACHE_FILE.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[scanner] Cache written -> {CACHE_FILE}")

    # 17b. Update watchlist tracker with today's long signals
    try:
        from database import upsert_watchlist_tickers
        upsert_watchlist_tickers(long_signals)
    except Exception as e:
        print(f"[scanner] Watchlist tracker update error: {e}")

    # 18. Journal check + position digest
    try:
        from journal_tracker import run_journal_check
        run_journal_check(bars_data, market_label=market_label, regime_gate=regime_gate)
    except Exception as e:
        print(f"[scanner] Journal check error: {e}")

    # 19. Alerts (filtered by tier + score)
    try:
        send_scan_alert(payload, open_tickers=open_tickers)
    except Exception as e:
        print(f"[scanner] Alert error: {e}")

    return payload



def run_replay(as_of_date: str) -> dict:
    """
    Historical replay: re-run the full scan pipeline as if today were `as_of_date`.
    Fetches historical bar data clipped to as_of_date, runs the full screener.
    Returns same payload structure as run_scan() — no cache write.
    """
    from datetime import datetime as dt
    print(f"\n[replay] === Replay started for {as_of_date} ===")
    t0 = time.time()

    try:
        cutoff = pd.Timestamp(as_of_date)
    except Exception as e:
        return {"error": f"Invalid date: {e}"}

    # Fetch bars from 560 days before cutoff up to cutoff
    lookback_start = (cutoff - pd.Timedelta(days=560)).strftime("%Y-%m-%d")
    cutoff_str     = cutoff.strftime("%Y-%m-%d")
    weekly_start   = (cutoff - pd.Timedelta(days=760)).strftime("%Y-%m-%d")

    client = get_alpaca_client()
    stock_tickers = [t for t in ALL_TICKERS if t not in ALL_ETFS]

    print(f"[replay] Fetching daily bars {lookback_start} -> {cutoff_str}...")
    import os as _os
    if _os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_bars_batch_polygon
            bars_data = fetch_bars_batch_polygon(
                stock_tickers + ALL_ETFS,
                start=lookback_start, end=cutoff_str,
                interval="1d", min_rows=20, label="replay",
            )
        except Exception as _e:
            print(f"[replay] Polygon daily failed ({_e}) — falling back to yfinance")
            bars_data = fetch_bars_batch(
                stock_tickers + ALL_ETFS, start=lookback_start, end=cutoff_str,
                interval="1d", min_rows=20, batch_size=50, label="replay",
            )
    else:
        bars_data = fetch_bars_batch(
            stock_tickers + ALL_ETFS, start=lookback_start, end=cutoff_str,
            interval="1d", min_rows=20, batch_size=50, label="replay",
        )

    print(f"[replay] Fetching weekly bars {weekly_start} -> {cutoff_str}...")
    if _os.environ.get("POLYGON_API_KEY"):
        try:
            from polygon_client import fetch_bars_batch_polygon
            weekly_bars = fetch_bars_batch_polygon(
                stock_tickers,
                start=weekly_start, end=cutoff_str,
                interval="1wk", min_rows=10, label="replay/weekly",
            )
        except Exception as _e:
            print(f"[replay] Polygon weekly failed ({_e}) — falling back to yfinance")
            weekly_bars = fetch_bars_batch(
                stock_tickers, start=weekly_start, end=cutoff_str,
                interval="1wk", min_rows=10, batch_size=50, label="replay/weekly",
            )
    else:
        weekly_bars = fetch_bars_batch(
            stock_tickers, start=weekly_start, end=cutoff_str,
            interval="1wk", min_rows=10, batch_size=50, label="replay/weekly",
        )

    if not bars_data:
        return {"error": "No data fetched — check date or network"}

    # ── From here: identical to run_scan() ──────────────────────────────────
    settings         = get_settings()
    hide_earnings_lt = settings.get("hide_earnings_lt_days", 14)
    min_signal_score = settings.get("min_signal_score", 6)

    spy_closes = bars_data.get("SPY", {}).get("close") if "SPY" in bars_data else None

    from market_regime import enhanced_market_conditions, check_regime_change
    market       = enhanced_market_conditions(bars_data, set(ALL_ETFS))
    market_score = market.get("score", 50)
    market_label = market.get("label", "Neutral")

    regime_change = check_regime_change(market_score)
    regime_gate   = regime_change["new_gate"]
    regime_mode   = regime_change["mode"]
    size_mult     = regime_change["size"]
    market["gate"]      = regime_gate
    market["mode"]      = regime_mode
    market["size_mult"] = size_mult

    all_weighted_rs = []
    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue
        score = _calculate_weighted_rs_score(df["close"], spy_closes)
        if score is not None:
            all_weighted_rs.append(score)

    MIN_PRICE   = settings.get("min_price", 5.0)
    MIN_AVG_VOL = settings.get("min_avg_vol", 200_000)

    raw_results = []
    for ticker, df in bars_data.items():
        if ticker in ALL_ETFS:
            continue
        try:
            if float(df["close"].iloc[-1]) < MIN_PRICE:
                continue
            if float(df["volume"].tail(20).mean()) < MIN_AVG_VOL:
                continue
        except Exception:
            pass
        tier      = TICKER_TIER.get(ticker, 2)
        weekly_df = weekly_bars.get(ticker)
        result    = analyse_stock(ticker, df, all_weighted_rs, spy_closes, market_score, tier, weekly_df)
        if result:
            raw_results.append(result)

    for result in raw_results:
        ticker = result["ticker"]
        if ticker in bars_data:
            base_info = detect_base(bars_data[ticker])
            result.update(base_info)
        result["sector"]          = get_sector(ticker)

    sector_rs = calculate_sector_rs(bars_data)
    for result in raw_results:
        sector = result.get("sector", "Technology")
        s_data = sector_rs.get(sector, {})
        result["sector_rs_rank"] = s_data.get("rank")
        result["sector_trend"]   = s_data.get("trend")
        result["sector_rs_1m"]   = s_data.get("rs_vs_spy_1m")
        result["sector_aligned"] = (s_data.get("rs_vs_spy_1m") or 0) > 0

    for result in raw_results:
        result["signal_score"] = calculate_signal_score(
            rs               = result.get("rs", 50),
            vcs              = result.get("vcs"),
            base_score       = result.get("base_score", 0),
            vol_ratio        = result.get("vol_ratio"),
            sector_rs_rank   = result.get("sector_rs_rank"),
            market_score     = market_score,
            earnings_days    = None,
            tier             = result.get("tier", 2),
            bouncing_from    = result.get("bouncing_from"),
            pct_from_52w_high= result.get("pct_from_52w_high"),
            theme            = result.get("theme"),
            sector_rs_data   = sector_rs,
            flag_detected    = result.get("flag_detected", False),
            flag_status      = result.get("flag_status"),
            ma21_slope       = result.get("ma21_slope"),
            ma50_slope       = result.get("ma50_slope"),
            coiling          = result.get("coiling", False),
            ll_hl_detected   = result.get("ll_hl_detected", False),
            approaching_pivot= result.get("approaching_pivot", False),
            darvas_detected  = result.get("darvas_detected", False),
            darvas_status    = result.get("darvas_status"),
            w_stack_ok       = result.get("w_stack_ok", False),
            is_weekly_signal = _is_weekly_signal(result),
        )

    if regime_mode == "LONGS":
        long_candidates = [s for s in raw_results if is_long_signal(s, settings)]
    elif regime_mode == "SELECTIVE":
        sel = {**settings, "rs_filter": max(settings.get("rs_filter", 70), 85)}
        long_candidates = [s for s in raw_results if is_long_signal(s, sel) and s.get("tier", 99) <= 1]
    else:
        long_candidates = []

    short_candidates = [s for s in raw_results if is_short_signal(s)]

    long_signals  = [s for s in long_candidates if (s.get("signal_score") or 0) >= min_signal_score]
    short_signals = [s for s in short_candidates]

    for s in long_signals:
        if s.get("stop_price") and s.get("price"):
            pos = calculate_position_size(s["price"], s["stop_price"])
            s["position"] = pos

    long_signals  = sorted(long_signals,  key=lambda s: (-(s.get("signal_score") or 0), s.get("vcs") or 10))
    short_signals = sorted(short_signals, key=lambda s: -(s.get("short_score") or 0))

    ma10_bounces = [s for s in long_signals if s.get("ma10_touch")]
    ma21_bounces = [s for s in long_signals if s.get("ma21_touch") and not s.get("ma10_touch")]
    ma50_bounces = [s for s in long_signals if s.get("ma50_touch") and not s.get("ma10_touch") and not s.get("ma21_touch")]

    ep_signals = sorted(
        [s for s in raw_results if s.get("ep_detected")],
        key=lambda s: (-(s.get("ep_gap_pct") or 0)),
    )

    elapsed = round(time.time() - t0, 1)
    print(f"[replay] === Complete in {elapsed}s — {len(long_signals)} longs, {len(short_signals)} shorts ===")

    return {
        "replay_date":      as_of_date,
        "scanned_at":       f"REPLAY: {as_of_date} (run {datetime.now().strftime('%H:%M')})",
        "scan_duration_s":  elapsed,
        "total_scanned":    len(raw_results),
        "market":           market,
        "sector_rs":        sector_rs,
        "sector_rotation":  rotation_bias,
        "long_signals":     long_signals,
        "short_signals":    short_signals[:30],
        "ma10_bounces":     ma10_bounces,
        "ma21_bounces":     ma21_bounces,
        "ma50_bounces":     ma50_bounces,
        "sotd_long":        long_signals[0] if long_signals else None,
        "sotd_short":       short_signals[0] if short_signals else None,
        "ep_signals":       ep_signals[:40],
        "all_stocks":       sorted(raw_results, key=lambda s: -(s.get("rs") or 0)),
        "pattern_signals":  [],
        "cup_handle_signals": [],
        "extended_bo_signals": [],
        "weekly_bo_retest_signals": [],
        "portfolio_heat":   {},
        "open_tickers":     [],
        "settings":         settings,
        "is_replay":        True,
    }


if __name__ == "__main__":
    run_scan()

# ── ETF pre-fetch patch ──────────────────────────────────────────────────────
# Injected: fetch critical regime ETFs first in a dedicated small batch,
# then merge into bars_data so they're never lost to rate-limit batches.
