"""
microcap_scanner.py
-------------------
Separate EOD scan for micro/small caps (<$2B market cap)
in the top 3 RS sectors only.

Runs at 22:00 UK — 1 hour after main scan — to avoid memory/rate limit
conflicts with the main 865-ticker scan.

Sector gate: only scans stocks whose sector ETF is in the top 3 by
1-month RS vs SPY. This filters ~85% of Russell 2000 noise upfront
before fetching any bars.

Filters vs main scanner:
  - RS >= 75 (vs 70) — micro caps have noisier RS, need a higher bar
  - VCS <= 8 (vs 6) — small caps are inherently more volatile
  - Vol ratio >= 1.2 (vs 1.1) — want to see conviction volume
  - MA stack: MA10 > MA21 > MA50 required (MA200 optional — many micros <200 bars)
  - Market cap: yfinance fast_info.market_cap < $2B
  - Price > $2 (exclude penny stocks and OTC garbage)
  - Average daily volume > 50K shares (minimum liquidity)
"""

import os
import json
import time
import traceback
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
# alpaca imports removed — using yfinance

from microcap_watchlist import MICROCAP_TICKERS
from screener import (
    analyse_stock, calculate_1y_return, is_long_signal,
    calculate_mas, calculate_atr_series, detect_ma_touch_atr,
    calculate_vcs, volume_ratio, calculate_rs_rank,
)
from sector_rs import calculate_sector_rs, SECTOR_ETFS, get_sector
from market_regime import get_market_regime

CACHE_FILE = Path("/tmp/microcap_cache.json")
BATCH_SIZE = 50        # tickers per Alpaca request
MAX_TICKERS = 2000     # safety cap
MIN_PRICE   = 2.0      # exclude sub-$2
MIN_ADV     = 50_000   # min avg daily volume (shares)
MAX_MKTCAP  = 2e9      # $2B cap
TOP_N_SECTORS = 3      # gate: only scan stocks in top N sectors by RS


def _alpaca_client():
    """Returns None — kept for compatibility. All fetching uses yfinance."""
    return None


def _get_top_sectors(bars_data: dict) -> list[str]:
    """
    Return top N sector names by 1-month RS vs SPY.
    Uses sector ETF price data already fetched.
    """
    sector_rs = calculate_sector_rs(bars_data)
    ranked = sorted(
        [(name, data.get("rs_vs_spy_1m", -999)) for name, data in sector_rs.items()],
        key=lambda x: x[1], reverse=True
    )
    top = [name for name, _ in ranked[:TOP_N_SECTORS]]
    print(f"[microcap] Top {TOP_N_SECTORS} sectors: {top}")
    return top


def _get_sector_for_ticker(ticker: str) -> Optional[str]:
    """
    Quick yfinance sector lookup. Cached in a simple dict during the scan.
    Falls back to get_sector() (STOCK_SECTOR_MAP) first.
    """
    known = get_sector(ticker)
    if known != "Technology":  # non-default means it's in the map
        return known
    try:
        info = yf.Ticker(ticker).fast_info
        # yfinance doesn't expose sector cleanly in fast_info — use info dict
        full = yf.Ticker(ticker).info
        raw  = full.get("sector", "")
        # Map yfinance sector strings to our sector names
        yf_map = {
            "Technology":              "Technology",
            "Financial Services":      "Financials",
            "Healthcare":              "Healthcare",
            "Energy":                  "Energy",
            "Consumer Cyclical":       "Consumer Disc",
            "Consumer Defensive":      "Consumer Staples",
            "Industrials":             "Industrials",
            "Basic Materials":         "Materials",
            "Real Estate":             "Real Estate",
            "Utilities":               "Utilities",
            "Communication Services":  "Communication",
        }
        return yf_map.get(raw, None)
    except Exception:
        return None


def _fetch_bars_batch(client, tickers: list, days: int = 260) -> dict:
    """Fetch EOD bars via yfinance. `client` unused — kept for compatibility."""
    results    = {}
    batch_size = 200
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            raw = yf.download(batch, period=f"{days}d", interval="1d",
                              auto_adjust=True, progress=False, threads=True)
            if raw.empty:
                continue
            import pandas as pd
            if isinstance(raw.columns, pd.MultiIndex):
                for ticker in batch:
                    try:
                        df = raw.xs(ticker, axis=1, level=1).copy()
                        df.columns = [c.lower() for c in df.columns]
                        df.index = pd.to_datetime(df.index).tz_localize(None)
                        df = df.dropna(how="all").sort_index()
                        if len(df) >= 21:
                            results[ticker] = df[["open","high","low","close","volume"]]
                    except Exception:
                        pass
            else:
                t = batch[0]
                raw.columns = [c.lower() for c in raw.columns]
                raw.index = pd.to_datetime(raw.index).tz_localize(None)
                raw = raw.dropna(how="all").sort_index()
                if len(raw) >= 21:
                    results[t] = raw[["open","high","low","close","volume"]]
        except Exception as e:
            print(f"[microcap] Batch fetch error: {e}")
        time.sleep(1.0)
    return results


def _quick_filter(ticker: str, df: pd.DataFrame) -> tuple[bool, str]:
    """
    Fast pre-filter before full analyse_stock.
    Returns (passes, reason_if_fail).
    """
    closes  = df["close"]
    volumes = df["volume"]
    price   = float(closes.iloc[-1])

    # Price floor
    if price < MIN_PRICE:
        return False, f"price ${price:.2f} < ${MIN_PRICE}"

    # Average daily volume
    adv = float(volumes.tail(20).mean())
    if adv < MIN_ADV:
        return False, f"ADV {adv:.0f} < {MIN_ADV}"

    # MA stack check (fast version)
    mas = calculate_mas(closes)
    ma10, ma21, ma50 = mas["ma10"], mas["ma21"], mas["ma50"]
    if not (ma10 and ma21 and ma50):
        return False, "insufficient MA history"
    if not (ma10 > ma21 > ma50):
        return False, f"MA stack broken: {ma10:.2f}/{ma21:.2f}/{ma50:.2f}"

    # Price must be above all MAs
    if price < ma50:
        return False, "price below MA50"

    return True, ""


def _get_market_cap(ticker: str) -> Optional[float]:
    """Fetch market cap via yfinance fast_info."""
    try:
        fi = yf.Ticker(ticker).fast_info
        mc = getattr(fi, "market_cap", None)
        return float(mc) if mc else None
    except Exception:
        return None


def run_microcap_scan() -> dict:
    """
    Full micro cap scan pipeline:
    1. Fetch sector ETF bars → identify top 3 sectors
    2. For each micro cap ticker, quick sector lookup → gate out non-top sectors
    3. Batch fetch bars for gated tickers
    4. Quick filter (price, volume, MA stack)
    5. Full analyse_stock
    6. Market cap check (yfinance — only for candidates passing step 4)
    7. Score and sort
    """
    start_time = time.time()
    print(f"\n[microcap] === SCAN START {datetime.now().strftime('%H:%M:%S')} ===")
    print(f"[microcap] Universe: {len(MICROCAP_TICKERS)} tickers")

    client = _alpaca_client()

    # ── Step 1: Fetch sector ETF bars ────────────────────────────────────
    print("[microcap] Fetching sector ETF bars...")
    sector_etf_tickers = list(SECTOR_ETFS.values()) + ["SPY", "IWM"]
    etf_bars = _fetch_bars_batch(client, sector_etf_tickers, days=130)

    top_sectors = _get_top_sectors(etf_bars)

    # ── Step 2: Sector gate ───────────────────────────────────────────────
    # Use known sector map first (fast), then yfinance for unknowns
    print(f"[microcap] Applying sector gate (top sectors: {top_sectors})...")
    gated_tickers  = []
    sector_cache   = {}
    unknown_tickers = []

    for t in MICROCAP_TICKERS[:MAX_TICKERS]:
        sec = get_sector(t)
        if sec and sec != "Technology":  # known mapping
            sector_cache[t] = sec
            if sec in top_sectors:
                gated_tickers.append(t)
        else:
            unknown_tickers.append(t)  # need yfinance lookup

    # For unknowns, do batch yfinance lookup (slow — limit)
    print(f"[microcap] {len(gated_tickers)} known-sector tickers gated. {len(unknown_tickers)} need yfinance lookup...")
    for t in unknown_tickers[:300]:  # cap yfinance calls
        try:
            sec = _get_sector_for_ticker(t)
            if sec:
                sector_cache[t] = sec
                if sec in top_sectors:
                    gated_tickers.append(t)
        except Exception:
            pass

    print(f"[microcap] Sector gate: {len(gated_tickers)} tickers in top sectors")

    # ── Step 3: Batch fetch bars ──────────────────────────────────────────
    print(f"[microcap] Fetching EOD bars for {len(gated_tickers)} tickers...")
    bars_data = dict(etf_bars)  # carry over ETF bars

    for i in range(0, len(gated_tickers), BATCH_SIZE):
        batch = gated_tickers[i:i + BATCH_SIZE]
        batch_bars = _fetch_bars_batch(client, batch, days=260)
        bars_data.update(batch_bars)
        fetched = len([t for t in batch if t in batch_bars])
        print(f"[microcap]   Batch {i//BATCH_SIZE + 1}: {fetched}/{len(batch)} fetched")
        time.sleep(0.3)  # rate limit courtesy

    print(f"[microcap] Total bars fetched: {len(bars_data)} tickers")

    # ── Step 4-6: Screen each ticker ─────────────────────────────────────
    spy_closes = bars_data.get("SPY", pd.DataFrame()).get("close", pd.Series())
    all_1y_returns = []
    for t, df in bars_data.items():
        if t in gated_tickers:
            ret = calculate_1y_return(df["close"])
            if ret is not None:
                all_1y_returns.append(ret)

    candidates  = []
    skipped     = {"no_bars": 0, "quick_filter": 0, "mktcap": 0, "not_long": 0}
    mktcap_hits = 0

    for ticker in gated_tickers:
        if ticker not in bars_data:
            skipped["no_bars"] += 1
            continue

        df = bars_data[ticker]

        # Quick filter
        passes, reason = _quick_filter(ticker, df)
        if not passes:
            skipped["quick_filter"] += 1
            continue

        # Full analysis
        result = analyse_stock(
            ticker=ticker,
            df=df,
            all_1y_returns=all_1y_returns,
            spy_closes=spy_closes if not spy_closes.empty else None,
            market_score=50,
            tier=4,  # Tier 4 = micro cap
        )
        if not result:
            continue

        # Must pass long signal filter
        if not is_long_signal(result, {"rs_filter": 75, "vcs_filter": 8.0}):
            skipped["not_long"] += 1
            continue

        # Market cap check (only for passing candidates — expensive)
        mktcap = _get_market_cap(ticker)
        if mktcap is not None and mktcap > MAX_MKTCAP:
            skipped["mktcap"] += 1
            continue

        # Enrich
        result["sector"]      = sector_cache.get(ticker, get_sector(ticker))
        result["market_cap"]  = mktcap
        result["mktcap_str"]  = f"${mktcap/1e6:.0f}M" if mktcap else "unknown"
        result["ticker"]      = ticker
        result["adv"]         = int(df["volume"].tail(20).mean())
        result["tier"]        = 4

        candidates.append(result)
        mktcap_hits += 1

    # ── Step 7: Score and sort ────────────────────────────────────────────
    # Signal score already in result from analyse_stock
    # Re-score with micro cap context (sector RS contributes)
    sector_rs = calculate_sector_rs(bars_data)
    for r in candidates:
        sec    = r.get("sector", "Technology")
        s_data = sector_rs.get(sec, {})
        r["sector_rs_rank"]  = s_data.get("rank")
        r["sector_rs_1m"]    = s_data.get("rs_vs_spy_1m")
        r["sector_aligned"]  = (s_data.get("rs_vs_spy_1m") or 0) > 0

        # Micro cap specific signal score (RS weighted higher, mktcap bonus for smaller)
        rs    = r.get("rs", 50)
        vcs   = r.get("vcs") or 6
        vol_r = r.get("vol_ratio") or 1
        score = 5.0
        if rs >= 90: score += 2.0
        elif rs >= 85: score += 1.5
        elif rs >= 80: score += 1.0
        elif rs >= 75: score += 0.5
        if vcs <= 3: score += 1.5
        elif vcs <= 5: score += 1.0
        elif vcs <= 7: score += 0.5
        if vol_r >= 2.0: score += 1.0
        elif vol_r >= 1.5: score += 0.5
        if s_data.get("rank") == 1: score += 1.0
        elif s_data.get("rank") == 2: score += 0.5
        mc = r.get("market_cap")
        if mc and mc < 300e6: score += 0.5  # bonus for true micro
        r["signal_score"] = round(min(10.0, score), 1)

    # Sort by score
    candidates.sort(key=lambda x: x.get("signal_score", 0), reverse=True)

    # ── Step 8: Social enrichment (top 30 candidates only) ───────────────
    print("[microcap] Fetching social intelligence for top candidates...")
    try:
        from social_sentiment import enrich_signals_with_social
        candidates = enrich_signals_with_social(candidates, max_tickers=30)
        print(f"[microcap] Social enrichment complete")
    except Exception as e:
        print(f"[microcap] Social enrichment failed (non-fatal): {e}")

    # ── Step 8: Social intelligence enrichment ───────────────────────────
    # Fetch for top 30 candidates by signal_score (rate limit friendly)
    print("[microcap] Fetching social intelligence for top candidates...")
    try:
        from social_sentiment import enrich_signals_with_social
        candidates = enrich_signals_with_social(candidates, max_tickers=30)
        hot_social = [s for s in candidates if (s.get("social_score") or 0) >= 5]
        print(f"[microcap] Social enrichment done. HOT/ACTIVE: {len(hot_social)}")
    except Exception as e:
        print(f"[microcap] Social enrichment failed (non-fatal): {e}")
        hot_social = []

    # ── Send Telegram alerts for convergence signals ──────────────────────
    # A micro cap with BOTH technical setup AND social momentum is the sweet spot
    try:
        _send_convergence_alerts(candidates)
    except Exception as e:
        print(f"[microcap] Convergence alerts failed: {e}")

    # Group by MA touch type
    ma10_bounces = [s for s in candidates if s.get("ma10_touch")]
    ma21_bounces = [s for s in candidates if s.get("ma21_touch") and not s.get("ma10_touch")]
    ma50_bounces = [s for s in candidates if s.get("ma50_touch") and not s.get("ma10_touch") and not s.get("ma21_touch")]

    elapsed = round(time.time() - start_time, 1)
    print(f"\n[microcap] === SCAN COMPLETE {elapsed}s ===")
    print(f"[microcap] Candidates: {len(candidates)} | MA10: {len(ma10_bounces)} | MA21: {len(ma21_bounces)} | MA50: {len(ma50_bounces)}")
    print(f"[microcap] Social HOT: {len(hot_social)}")
    print(f"[microcap] Skipped — no bars: {skipped['no_bars']}, quick filter: {skipped['quick_filter']}, mktcap: {skipped['mktcap']}, not long: {skipped['not_long']}")

    payload = {
        "scanned_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scan_seconds":  elapsed,
        "top_sectors":   top_sectors,
        "total_gated":   len(gated_tickers),
        "total_signals": len(candidates),
        "hot_social":    len(hot_social),
        "ma10_bounces":  ma10_bounces[:20],
        "ma21_bounces":  ma21_bounces[:20],
        "ma50_bounces":  ma50_bounces[:20],
        "all_signals":   candidates[:60],
    }

    # Cache to disk
    try:
        CACHE_FILE.write_text(json.dumps(payload, default=str))
        print(f"[microcap] Cache written → {CACHE_FILE}")
    except Exception as e:
        print(f"[microcap] Cache write error: {e}")

    return payload


def _send_convergence_alerts(candidates: list) -> None:
    """
    Fire Telegram alerts for micro caps where technical + social converge.
    Convergence = signal_score >= 7 AND social_score >= 5.
    """
    from alerts import _send

    convergence = [
        s for s in candidates
        if (s.get("signal_score") or 0) >= 7
        and (s.get("social_score") or 0) >= 5
    ]
    if not convergence:
        return

    lines = [f"<b>🔥 MICRO CAP CONVERGENCE — {datetime.now().strftime('%Y-%m-%d')}</b>",
             f"Technical + Social momentum aligned\n"]

    for s in convergence[:5]:
        ticker     = s["ticker"]
        price      = s.get("price", 0)
        tech_score = s.get("signal_score", 0)
        soc_score  = s.get("social_score", 0)
        combined   = s.get("combined_score", 0)
        ma         = s.get("bouncing_from", "MA")
        mktcap     = s.get("mktcap_str", "")
        sector     = s.get("sector", "")
        soc_label  = s.get("social_label", "")
        alerts     = s.get("social_alerts", [])
        stop       = s.get("stop_price")
        t1         = s.get("target_1")
        rs         = s.get("rs", 0)

        alert_str = " · ".join(alerts[:2]) if alerts else ""

        lines.append(
            f"<b>{ticker}</b> ${price:.2f} | {mktcap} | {sector}\n"
            f"  ↗ {ma} bounce · RS {rs} · Tech {tech_score} · Social {soc_score} ({soc_label})\n"
            f"  Combined: <b>{combined}/10</b>\n"
            f"  {alert_str}\n"
            + (f"  Stop ${stop:.2f} → T1 ${t1:.2f}" if stop and t1 else "")
        )

    _send("\n".join(lines))
    print(f"[microcap] Sent convergence alert for {len(convergence)} tickers")
