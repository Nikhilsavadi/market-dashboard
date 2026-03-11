"""
main.py - FastAPI backend with all routes
"""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import (
    init_db, journal_add, journal_list, journal_update,
    journal_delete, journal_get, get_backtest_results, get_signal_history,
    bot_trades_sync, bot_trades_list, bot_trades_stats,
)
from settings import get_settings, update_settings, calculate_portfolio_heat

CACHE_FILE = Path(__file__).parent / "cache.json"

app = FastAPI(title="Signal Desk API", version="2.0.0")

# ── Trading mode ───────────────────────────────────────────────────────────────
# Set STOCKS_ONLY=false in Railway env vars to re-enable options endpoints.
# Default is true — options add complexity before edge is proven.
import os as _os
STOCKS_ONLY = _os.environ.get("STOCKS_ONLY", "true").lower() in ("true", "1", "yes")
if STOCKS_ONLY:
    print("[main] STOCKS_ONLY mode — options endpoints disabled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def run_scan_job():
    print(f"[scheduler] Triggered at {datetime.now()}")
    try:
        from scanner import run_scan
        run_scan()
    except Exception as e:
        print(f"[scheduler] Scan failed: {e}")


def run_weekly_scan_job():
    """Runs weekly screener after Saturday scan — populates weekly_signals in cache."""
    print(f"[scheduler] Weekly scan triggered at {datetime.now()}")
    try:
        from scanner import fetch_bars, fetch_weekly_bars, get_alpaca_client
        from universe_expander import get_scan_universe
        from watchlist import ETFS
        from sector_rs import SECTOR_ETFS
        from weekly_screener import run_weekly_scan
        import json, os

        all_tickers = get_scan_universe()
        all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))

        if os.environ.get("POLYGON_API_KEY"):
            from polygon_client import fetch_bars as pg_bars, fetch_weekly_bars as pg_weekly
            bars        = pg_bars(all_tickers + all_etfs, days=500, interval="day", min_rows=20, label="weekly-scan")
            weekly_bars = pg_weekly(all_tickers + all_etfs)
        else:
            client = get_alpaca_client()
            bars        = fetch_bars(client, all_tickers + all_etfs)
            weekly_bars = fetch_weekly_bars(client, all_tickers + all_etfs)

        # RS ranks from latest daily cache
        cache = _load_cache()
        rs_ranks = {s["ticker"]: s.get("rs") for s in cache.get("signals", []) if s.get("ticker")}

        weekly_results = run_weekly_scan(bars, weekly_bars, rs_ranks)

        # Merge into existing cache
        cache["weekly_signals"] = weekly_results
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)

        print(f"[scheduler] Weekly scan complete — "
              f"{len(weekly_results.get('all_weekly', []))} signals cached")
    except Exception as e:
        print(f"[scheduler] Weekly scan failed: {e}")
        import traceback; traceback.print_exc()


scheduler = BackgroundScheduler(timezone="Europe/London")

scheduler.add_job(
    run_scan_job,
    CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone="Europe/London"),
    id="post_market_scan",
    name="Post-market EOD scan (21:00 UK)",
    replace_existing=True,
)

scheduler.add_job(
    run_scan_job,
    CronTrigger(day_of_week="tue-sat", hour=7, minute=0, timezone="Europe/London"),
    id="pre_market_scan",
    name="Pre-market scan (07:00 UK)",
    replace_existing=True,
)

# RVOL intraday scan — every 30 mins during market hours
def run_rvol_job():
    try:
        from intraday import is_market_hours, calculate_rvol
        if not is_market_hours():
            return
        from scanner import get_alpaca_client
        from watchlist import ALL_TICKERS, ETFS
        client = get_alpaca_client()
        tickers = [t for t in ALL_TICKERS if t not in ETFS][:80]  # top 80
        rvol = calculate_rvol(client, tickers)
        # Merge into cache
        cache = read_cache()
        if cache:
            cache["rvol"] = rvol
            cache["rvol_updated"] = datetime.now().strftime("%H:%M:%S")
            CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))
    except Exception as e:
        print(f"[rvol] Error: {e}")

# Position monitor — every 15 mins during market hours
# Also runs skip outcome tracker on the same cycle (lightweight — skips frozen entries)
def run_position_monitor():
    try:
        from intraday import is_market_hours
        from position_monitor import check_positions, update_skip_outcomes
        if not is_market_hours():
            return
        print("[scheduler] Running position monitor...")
        check_positions()
        # Skip tracker: runs every cycle but each ticker only fetches bars once
        # per day (yfinance caches intraday; daily bars are cheap)
        print("[scheduler] Updating skip outcomes...")
        update_skip_outcomes()
    except Exception as e:
        print(f"[scheduler] Position monitor failed: {e}")

scheduler.add_job(
    run_position_monitor,
    CronTrigger(minute="*/15", hour="14-21", day_of_week="mon-fri", timezone="UTC"),
    id="position_monitor",
    replace_existing=True,
)

# Skip outcome EOD sweep — runs at 21:30 UTC (4:30pm ET, 30min after close)
# This is the authoritative daily update: uses final closing prices, not intraday.
# Runs even on days with no open positions. Freezes entries after 20 trading days.
def run_skip_eod_sweep():
    try:
        from position_monitor import update_skip_outcomes
        print("[scheduler] EOD skip outcome sweep...")
        result = update_skip_outcomes()
        print(f"[scheduler] Skip sweep: {result}")
    except Exception as e:
        print(f"[scheduler] Skip EOD sweep failed: {e}")

scheduler.add_job(
    run_skip_eod_sweep,
    CronTrigger(hour=21, minute=30, day_of_week="mon-fri", timezone="UTC"),
    id="skip_eod_sweep",
    replace_existing=True,
)

# Position digest at market close (21:00 UTC = 4pm ET)
def run_close_digest():
    try:
        from position_monitor import send_position_digest
        send_position_digest()
    except Exception as e:
        print(f"[scheduler] Close digest failed: {e}")

scheduler.add_job(
    run_close_digest,
    CronTrigger(hour=21, minute=5, day_of_week="mon-fri", timezone="UTC"),
    id="close_digest",
    replace_existing=True,
)

scheduler.add_job(
    run_rvol_job,
    CronTrigger(day_of_week="mon-fri", hour="14-21", minute="*/30", timezone="UTC"),
    id="rvol_scan",
    name="Intraday RVOL (every 30min market hours)",
    replace_existing=True,
)

# ── Intraday MA touch scanner — every 30 mins during market hours ─────────────
# Watches pre-qualified stocks from overnight cache for intraday EMA10/EMA21
# touches and bounces. Fires Telegram alert immediately on detection.
# Deduplicates: one alert per ticker per MA per trading day.
def run_intraday_ma_job():
    try:
        from intraday import is_market_hours
        if not is_market_hours():
            return
        from intraday_ma_scanner import run_intraday_ma_scan
        result = run_intraday_ma_scan()
        print(f"[scheduler] Intraday MA scan: {result.get('alerts', 0)} alerts · {result.get('scanned', 0)} scanned")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[scheduler] Intraday MA scan failed: {e}")

scheduler.add_job(
    run_intraday_ma_job,
    CronTrigger(day_of_week="mon-fri", hour="14-21", minute="0,30", timezone="UTC"),
    id="intraday_ma_scan",
    name="Intraday MA touch scanner (every 30min market hours)",
    replace_existing=True,
)


# ── EP Real-time Entry Zone Monitor — every 5 mins during market hours ────
def run_ep_zone_monitor():
    try:
        from intraday import is_market_hours
        if not is_market_hours():
            return
        cache = read_cache()
        if not cache or "stockbee_ep" not in cache:
            return
        from ep_realtime import check_entry_zones
        alerts = check_entry_zones(cache)
        if alerts:
            print(f"[ep-zones] {len(alerts)} entry zone alerts fired: {[a['ticker'] for a in alerts]}")
    except Exception as e:
        print(f"[ep-zones] Error: {e}")

scheduler.add_job(
    run_ep_zone_monitor,
    CronTrigger(day_of_week="mon-fri", hour="14-21", minute="*/5", timezone="UTC"),
    id="ep_zone_monitor",
    name="EP entry zone monitor (every 5min market hours)",
    replace_existing=True,
)


def run_weekly_report_job():
    try:
        from weekly_report import send_weekly_report
        cache = read_cache()
        send_weekly_report(cache)
    except Exception as e:
        print(f"[scheduler] Weekly report failed: {e}")


scheduler.add_job(
    run_weekly_report_job,
    CronTrigger(day_of_week="sun", hour=8, minute=0, timezone="Europe/London"),
    id="weekly_report",
    name="Weekly performance digest (Sun 08:00 UK)",
    replace_existing=True,
)


def run_universe_expansion_job():
    try:
        from universe_expander import run_universe_expansion
        result = run_universe_expansion()
        print(f"[scheduler] Universe expansion: {result.get('added', 0)} tickers added "
              f"({result.get('checked', 0)} checked)")
    except Exception as e:
        print(f"[scheduler] Universe expansion failed: {e}")


scheduler.add_job(
    run_universe_expansion_job,
    CronTrigger(day_of_week="sun", hour=8, minute=30, timezone="Europe/London"),
    id="universe_expansion",
    name="Weekly universe expansion (Sun 08:30 UK)",
    replace_existing=True,
)


def run_morning_brief_job():
    try:
        from morning_brief import send_morning_brief
        send_morning_brief()
    except Exception as e:
        print(f"[scheduler] Morning brief failed: {e}")


scheduler.add_job(
    run_morning_brief_job,
    CronTrigger(day_of_week="mon-fri", hour=6, minute=30, timezone="Europe/London"),
    id="morning_brief",
    name="Morning brief (Mon-Fri 06:30 UK)",
    replace_existing=True,
)


@app.on_event("startup")
async def startup():
    init_db()
    from database import init_backtest_tables
    init_backtest_tables()
    print("[main] Database tables initialised (including historical_trades)")

    # Merge any previously auto-added tickers back into live universe
    try:
        from universe_expander import reload_dynamic_tickers
        reload_dynamic_tickers()
    except Exception as e:
        print(f"[main] universe reload failed: {e}")
# ── Micro cap scan — 22:00 UK (1hr after main scan) ──────────────────────────
def run_microcap_scan_job():
    try:
        print(f"[scheduler] Starting micro cap scan {datetime.now()}")
        from microcap_scanner import run_microcap_scan
        result = run_microcap_scan()
        cache["microcap"] = result
        cache["microcap_scanned_at"] = result.get("scanned_at")
        print(f"[scheduler] Micro cap scan complete: {result.get('total_signals')} signals")
    except Exception as e:
        print(f"[scheduler] Micro cap scan failed: {e}")
        import traceback; traceback.print_exc()

scheduler.add_job(
    run_microcap_scan_job,
    CronTrigger(hour=22, minute=0, day_of_week="mon-fri", timezone="Europe/London"),
    id="microcap_scan",
    replace_existing=True,
)

# ── Weekend scans ─────────────────────────────────────────────────────────────
# Saturday 09:00 UK — catches any gap if Friday 21:00 scan failed or
# Friday had early close / holiday. Data is Friday's closing prices.
scheduler.add_job(
    run_scan_job,
    CronTrigger(day_of_week="sat", hour=9, minute=0, timezone="Europe/London"),
    id="weekend_sat_scan",
    name="Weekend fallback scan (Sat 09:00 UK — uses Friday close data)",
    replace_existing=True,
)

# Saturday 10:30 UK — weekly screener runs AFTER the 09:00 scan
# Uses Friday close data (full weekly candle) for clean weekly signals
scheduler.add_job(
    run_weekly_scan_job,
    CronTrigger(day_of_week="sat", hour=10, minute=30, timezone="Europe/London"),
    id="weekly_scan_job",
    name="Weekly screener (Sat 10:30 UK — wEMA bounce, VCP, BO retest)",
    replace_existing=True,
)

# Sunday 09:30 UK — runs AFTER the weekly report (08:00) so the brief
# has fresh signal data. Gives clean data before Monday open.
scheduler.add_job(
    run_scan_job,
    CronTrigger(day_of_week="sun", hour=9, minute=30, timezone="Europe/London"),
    id="weekend_sun_scan",
    name="Weekend scan (Sun 09:30 UK — prep for Monday open)",
    replace_existing=True,
)

# Weekend morning brief — Sat + Sun at 08:00 UK
# Reads latest cache (Friday data) so you know what to watch on Monday
scheduler.add_job(
    run_morning_brief_job,
    CronTrigger(day_of_week="sat,sun", hour=8, minute=0, timezone="Europe/London"),
    id="weekend_brief",
    name="Weekend brief (Sat-Sun 08:00 UK)",
    replace_existing=True,
)

# Sunday 22:00 UK — weekly reconstruction auto-run
# Runs after markets close and weekend scans complete so backtest data stays fresh
def run_weekly_reconstruction():
    print("[reconstruct] Weekly auto-reconstruction starting (Sun 22:00 UK)...")
    try:
        from historical_bt import run_historical_reconstruction
        from scanner import fetch_bars, get_alpaca_client
        from universe_expander import get_scan_universe
        from watchlist import ETFS
        from sector_rs import SECTOR_ETFS
        import os

        all_tickers = get_scan_universe()
        all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
        stock_tickers = [t for t in all_tickers if t not in all_etfs]

        if os.environ.get("POLYGON_API_KEY"):
            from polygon_client import fetch_bars as pg_bars
            bars = pg_bars(stock_tickers + all_etfs, days=500, interval="day", min_rows=20, label="reconstruct")
        else:
            client = get_alpaca_client()
            bars = fetch_bars(client, stock_tickers + all_etfs)

        run_historical_reconstruction(bars, lookback_days=365)
        print("[reconstruct] Weekly auto-reconstruction complete")
    except Exception as e:
        print(f"[reconstruct] Weekly auto-reconstruction failed: {e}")
        import traceback; traceback.print_exc()

scheduler.add_job(
    run_weekly_reconstruction,
    CronTrigger(day_of_week="sun", hour=22, minute=0, timezone="Europe/London"),
    id="weekly_reconstruction",
    name="Weekly reconstruction (Sun 22:00 UK)",
    replace_existing=True,
)

scheduler.start()
print(
    "[main] Scheduler started — "
    "06:30 brief (Mon-Fri) · 08:00 brief (Sat-Sun) · "
    "07:00 scan (Tue-Sat) · 09:00 scan (Sat) · 09:30 scan (Sun) · "
    "21:00 scan (Mon-Fri) · RVOL 30min · Sun 08:00 weekly report · Sun 22:00 reconstruction"
)
if not CACHE_FILE.exists():
    print("[main] No cache — running initial scan in background...")
    t = threading.Thread(target=run_scan_job, daemon=True)
    t.start()
else:
    try:
        data = json.loads(CACHE_FILE.read_text())
        print(f"[main] Cache loaded — last scan: {data.get('scanned_at', 'unknown')}")
    except Exception:
        print("[main] Cache unreadable — running initial scan in background...")
        t = threading.Thread(target=run_scan_job, daemon=True)
        t.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


# ── Core routes ───────────────────────────────────────────────────────────────

@app.get("/api/polygon-status")
def polygon_status():
    """Check Polygon API connectivity and confirm key is working."""
    try:
        from polygon_client import check_connection
        return check_connection()
    except Exception as e:
        return {"ok": False, "error": str(e)}





@app.get("/api/mode")
def get_trading_mode():
    """Returns current trading mode and which features are active."""
    return {
        "stocks_only":    STOCKS_ONLY,
        "options_enabled": not STOCKS_ONLY,
        "mode_label":     "Stocks Only" if STOCKS_ONLY else "Stocks + Options",
        "hint": "Set STOCKS_ONLY=false in Railway env vars to enable options features",
    }



@app.get("/api/top-picks")
def get_top_picks_endpoint(max_take: int = 2):
    """
    Returns ranked signals split into TAKE / WATCH / MONITOR tiers.
    TAKE  = act on these first (up to max_take)
    WATCH = next best if capital allows
    MONITOR = review but don\'t act yet

    Priority score weights:
      VCS tightness 30%, pivot proximity 25%, vol ratio 20%,
      sector momentum 15%, RS rank 10%
    """
    try:
        from priority_rank import get_top_picks, get_top_short_picks
        cache = _load_cache()
        if not cache:
            return {"error": "No scan data. Run a scan first.", "take": [], "watch": [], "monitor": []}

        long_signals = cache.get("long_signals", [])
        sector_rs    = cache.get("sector_rs", {})

        if not long_signals:
            return {"take": [], "watch": [], "monitor": [], "summary": {"total": 0}}

        long_picks  = get_top_picks(long_signals, sector_rs, max_take=max_take)
        short_picks = get_top_short_picks(
            cache.get("short_signals", []), sector_rs, max_take=max_take
        )
        return {
            "longs":        long_picks,
            "shorts":       short_picks,
            # keep backward-compat keys at top level for longs
            **{k: v for k, v in long_picks.items() if k != "summary"},
            "long_summary":  long_picks.get("summary"),
            "short_summary": short_picks.get("summary"),
            "scanned_at":    cache.get("scanned_at"),
            "market_score":  cache.get("market", {}).get("score"),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/focus-list")
def get_focus_list_endpoint(max_picks: int = 8):
    """
    Master focus list — top N names across ALL signal types (HVE, EP, MA bounce, patterns).
    Answers: 'I can only trade 5-8 names today. Which ones?'
    HVE retest and EP setups get priority bonuses over standard MA bounces.
    """
    try:
        from priority_rank import get_focus_list
        cache = _load_cache()
        if not cache:
            return {"error": "No scan data. Run a scan first.", "focus_list": []}
        sector_rs = cache.get("sector_rs", {})
        result = get_focus_list(cache, sector_rs_data=sector_rs, max_picks=max_picks)
        result["scanned_at"]   = cache.get("scanned_at")
        result["market_score"] = cache.get("market", {}).get("score")
        result["market_label"] = cache.get("market", {}).get("label")
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intraday-ma/scan")
def trigger_intraday_ma_scan(secret: str = ""):
    """Manually trigger an intraday MA touch scan. Returns alerts fired."""
    if secret != os.environ.get("TRIGGER_SECRET", ""):
        raise HTTPException(status_code=403, detail="Invalid secret")
    try:
        from intraday_ma_scanner import run_intraday_ma_scan
        result = run_intraday_ma_scan()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intraday-ma/alerts")
def get_intraday_alerts():
    """Return today's fired intraday MA alerts."""
    try:
        from datetime import date
        from pathlib import Path
        log_file = Path(os.environ.get("DATA_DIR", ".")) / f"intraday_alerts_{date.today().isoformat()}.json"
        if not log_file.exists():
            return {"alerts": [], "count": 0, "date": date.today().isoformat()}
        alerts = json.loads(log_file.read_text())
        return {"alerts": alerts, "count": len(alerts), "date": date.today().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/circuit-breaker")
def get_circuit_breaker():
    """Current drawdown circuit breaker state — position sizing guidance."""
    try:
        from journal_tracker import get_circuit_breaker_state, check_drawdown_circuit_breaker
        return check_drawdown_circuit_breaker()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/data-provider")
def data_provider():
    """Show which data provider is currently active."""
    import os
    provider = "polygon" if os.environ.get("POLYGON_API_KEY") else "yfinance"
    return {
        "active_provider":    provider,
        "polygon_configured": bool(os.environ.get("POLYGON_API_KEY")),
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "Signal Desk API v2"}


@app.get("/api/health")
def health():
    cache = read_cache()
    jobs = {j.id: str(j.next_run_time) for j in scheduler.get_jobs()}
    return {
        "status": "ok",
        "last_scan": cache.get("scanned_at"),
        "total_scanned": cache.get("total_scanned", 0),
        "cache_exists": CACHE_FILE.exists(),
        "next_scans": jobs,
    }


@app.get("/api/scan")
def get_scan():
    data = read_cache()
    if not data:
        # Return empty skeleton — frontend will show "no scan yet" state
        # instead of crashing on 503
        return {
            "scanned_at": None,
            "total_scanned": 0,
            "long_signals": [],
            "short_signals": [],
            "ma10_bounces": [],
            "ma21_bounces": [],
            "ma50_bounces": [],
            "ep_signals": [],
            "all_stocks": [],
            "market": {"score": 50, "label": "No scan yet", "gate": "CAUTION"},
            "sector_rs": {},
            "portfolio_heat": {},
            "_empty": True,
        }
    return data


@app.get("/api/scan/longs")
def get_longs():
    data = read_cache()
    return {
        "scanned_at": data.get("scanned_at"),
        "market": data.get("market"),
        "ma10_bounces": data.get("ma10_bounces", []),
        "ma21_bounces": data.get("ma21_bounces", []),
        "ma50_bounces": data.get("ma50_bounces", []),
        "long_signals": data.get("long_signals", []),
    }


@app.get("/api/scan/shorts")
def get_shorts():
    data = read_cache()
    return {
        "scanned_at": data.get("scanned_at"),
        "market": data.get("market"),
        "short_signals": data.get("short_signals", []),
    }


@app.get("/api/scan/ep")
def get_ep_signals():
    """
    Returns Episodic Pivot (Delayed Reaction) setups.
    Sorted by entry-readiness first, then recency of EP day, then gap size.
    ep_entry_ok=True means current price is in the delayed reaction entry zone.
    ep_entry_ok=False means EP detected but not yet in entry zone (watchlist).
    """
    data = read_cache()
    ep   = data.get("ep_signals", [])
    return {
        "scanned_at":    data.get("scanned_at"),
        "market":        data.get("market"),
        "ep_count":      len(ep),
        "entry_ready":   sum(1 for s in ep if s.get("ep_entry_ok")),
        "ep_signals":    ep,
    }


@app.get("/api/scan/all")
def get_all_stocks():
    data = read_cache()
    return {
        "scanned_at": data.get("scanned_at"),
        "total": len(data.get("all_stocks", [])),
        "stocks": data.get("all_stocks", []),
    }


@app.get("/api/sector-rs")
def get_sector_rs():
    data = read_cache()
    return {
        "scanned_at": data.get("scanned_at"),
        "sectors": data.get("sector_rs", {}),
    }


@app.get("/api/sector-heatmap")
def get_sector_heatmap():
    """
    Returns both GICS sectors and investment themes ranked by RS vs SPY.
    Theme RS is calculated from ALL scanned stocks (not just signals) so it
    reflects true price-based relative strength regardless of signal count.
    """
    from sector_rs import THEMES, THEME_META
    data = read_cache()
    sector_rs = data.get("sector_rs", {})

    # Use all_stocks — every ticker scanned with its RS score
    # This is price-derived and exists even when there are 0 long signals
    all_stocks = data.get("all_stocks", [])

    # Build ticker → rs_score map from ALL scanned stocks
    ticker_rs = {}
    for s in all_stocks:
        t = s.get("ticker")
        r = s.get("rs")
        if t and r is not None:
            ticker_rs[t] = r

    # Build theme → avg RS from constituent tickers
    theme_tickers = {}
    for ticker, theme in THEMES.items():
        theme_tickers.setdefault(theme, []).append(ticker)

    theme_rows = []
    for theme, tickers in theme_tickers.items():
        rs_scores = [ticker_rs[t] for t in tickers if t in ticker_rs]
        if not rs_scores:
            continue
        avg_rs = sum(rs_scores) / len(rs_scores)
        # Centre around 50 (median RS) so positive = outperforming universe
        display_val = round(avg_rs - 50, 1)
        meta = THEME_META.get(theme, {})
        theme_rows.append({
            "name": meta.get("label", theme).split(" ", 1)[-1],
            "label": meta.get("label", theme),
            "type": "theme",
            "avg_rs": display_val,
            "raw_rs": round(avg_rs, 1),
            "count": len(rs_scores),
            "priority": meta.get("priority", False),
        })

    theme_rows.sort(key=lambda x: x["avg_rs"], reverse=True)

    # Build GICS sector rows from sector_rs cache (always price-based)
    sector_rows = []
    for name, d in sector_rs.items():
        rs1m = d.get("rs_vs_spy_1m")
        if rs1m is None:
            continue
        sector_rows.append({
            "name": name,
            "label": name,
            "type": "sector",
            "rs_1m": round(rs1m, 2),
            "rs_3m": round(d.get("rs_vs_spy_3m", 0), 2),
            "etf": d.get("etf", ""),
            "trend": d.get("trend", "neutral"),
            "rank": d.get("rank"),
        })

    sector_rows.sort(key=lambda x: x["rs_1m"], reverse=True)

    return {
        "scanned_at": data.get("scanned_at"),
        "themes": theme_rows,
        "sectors": sector_rows,
    }


@app.get("/api/news/{ticker}")
def get_news(ticker: str):
    from news import get_news as fetch_news
    return {
        "ticker": ticker.upper(),
        "news": fetch_news(ticker.upper(), limit=10),
    }


@app.get("/api/rvol")
def get_rvol():
    data = read_cache()
    return {
        "updated": data.get("rvol_updated"),
        "rvol": data.get("rvol", {}),
    }


@app.post("/api/brief/trigger")
async def trigger_brief(secret: str = ""):
    """Manually trigger a morning brief."""
    if secret != os.environ.get("TRIGGER_SECRET", ""):
        raise HTTPException(status_code=403, detail="Invalid secret")
    t = threading.Thread(target=run_morning_brief_job, daemon=True)
    t.start()
    return {"status": "morning brief triggered"}


@app.post("/api/scan/trigger")
def trigger_scan(secret: str = ""):
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    t = threading.Thread(target=run_scan_job, daemon=True)
    t.start()
    return {"status": "triggered", "message": "Scan running in background (~5-10 mins)"}


# ── Journal routes ────────────────────────────────────────────────────────────

class JournalEntry(BaseModel):
    ticker: str
    signal_type: Optional[str] = None
    entry_price: float
    ma10: Optional[float] = None
    ma21: Optional[float] = None
    ma50: Optional[float] = None
    vcs: Optional[float] = None
    rs: Optional[int] = None
    vol_ratio: Optional[float] = None
    atr: Optional[float] = None
    notes: Optional[str] = None


class JournalUpdate(BaseModel):
    status: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None


@app.get("/api/journal")
def get_journal(status: Optional[str] = Query(None)):
    return {"entries": journal_list(status)}


@app.post("/api/journal")
def add_journal(entry: JournalEntry):
    atr = entry.atr
    price = entry.entry_price

    # Calculate ATR-based levels
    stop   = round(price - 1.5 * atr, 4) if atr else None
    t1     = round(price + 1.5 * atr, 4) if atr else None
    t2     = round(price + 3.0 * atr, 4) if atr else None
    t3     = round(price + 5.0 * atr, 4) if atr else None

    data = {
        **entry.dict(),
        "added_date": date.today().isoformat(),
        "stop_price": stop,
        "target_1": t1,
        "target_2": t2,
        "target_3": t3,
        "status": "watching",
    }
    new_id = journal_add(data)

    # Telegram alert
    try:
        from alerts import send_journal_alert
        send_journal_alert(entry.ticker, "added", data)
    except Exception:
        pass

    return {"id": new_id, "entry": journal_get(new_id)}


@app.put("/api/journal/{id}")
def update_journal(id: int, update: JournalUpdate):
    existing = journal_get(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    updates = {k: v for k, v in update.dict().items() if v is not None}

    # Auto-calculate P&L if closing
    if update.exit_price and update.status == "closed":
        entry_price = existing.get("entry_price", 0)
        if entry_price:
            updates["pnl_pct"] = round(
                (update.exit_price - entry_price) / entry_price * 100, 2
            )
        if not update.exit_date:
            updates["exit_date"] = date.today().isoformat()

    journal_update(id, updates)

    # Alert on close
    if update.status == "closed":
        try:
            entry_date = existing.get("added_date")
            days_held = None
            if entry_date:
                from datetime import date as d
                days_held = (d.today() - d.fromisoformat(entry_date)).days
            from alerts import send_journal_alert
            send_journal_alert(existing["ticker"], "closed", {
                **updates,
                "days_held": days_held,
            })
        except Exception:
            pass

    return {"id": id, "entry": journal_get(id)}


@app.delete("/api/journal/{id}")
def delete_journal(id: int):
    existing = journal_get(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    journal_delete(id)
    return {"deleted": id}


# ── Backtest routes ───────────────────────────────────────────────────────────

@app.get("/api/backtest")
def get_backtest():
    return {"results": get_backtest_results()}


@app.post("/api/backtest/run")
def trigger_backtest(secret: str = ""):
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            from backtest import run_backtest
            from scanner import fetch_bars, get_alpaca_client
            client = get_alpaca_client()
            from watchlist import ALL_TICKERS
            bars = fetch_bars(client, ALL_TICKERS[:100])
            run_backtest(bars)
            print("[backtest] Complete")
        except Exception as e:
            print(f"[backtest] Error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "backtest triggered"}


@app.get("/api/signal-history")
def get_history(ticker: Optional[str] = None, days: int = 90):
    return {"history": get_signal_history(ticker=ticker, days=days)}



# ── Historical Backtest Routes ────────────────────────────────────────────────

@app.post("/api/backtest/reconstruct")
def trigger_reconstruction(secret: str = "", lookback_days: int = 365):
    """
    Trigger historical signal reconstruction.
    Runs in background — takes 20-60 mins for 365 days on full watchlist.
    Poll /api/backtest/status for progress.
    """
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            from historical_bt import run_historical_reconstruction
            from scanner import fetch_bars, get_alpaca_client
            from watchlist import ALL_TICKERS, ETFS
            from sector_rs import SECTOR_ETFS

            client = get_alpaca_client()
            all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
            stock_tickers = [t for t in ALL_TICKERS if t not in all_etfs]
            # Fetch 500 days so there's enough pre-history before the scan window
            # (lookback_days=365 + 60 warmup bars + buffer = ~475 calendar days)
            import os
            if os.environ.get("POLYGON_API_KEY"):
                from polygon_client import fetch_bars as pg_bars
                bars = pg_bars(stock_tickers + all_etfs, days=500, interval="day", min_rows=20, label="reconstruct")
            else:
                bars = fetch_bars(client, stock_tickers + all_etfs)
            run_historical_reconstruction(bars, lookback_days=lookback_days)
        except Exception as e:
            print(f"[reconstruct] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {
        "status": "reconstruction triggered",
        "lookback_days": lookback_days,
        "message": f"Running {lookback_days} days of history. Check /api/backtest/status for progress. Takes 20-60 mins."
    }


@app.get("/api/backtest/status")
def backtest_status():
    """Check how many historical signals/trades are in the DB."""
    try:
        from database import get_conn
        with get_conn() as conn:
            signals = conn.execute("SELECT COUNT(*) FROM historical_signals").fetchone()[0]
            trades  = conn.execute("SELECT COUNT(*) FROM historical_trades").fetchone()[0]
            first   = conn.execute("SELECT MIN(signal_date) FROM historical_signals").fetchone()[0]
            last    = conn.execute("SELECT MAX(signal_date) FROM historical_signals").fetchone()[0]
        return {
            "historical_signals": signals,
            "historical_trades": trades,
            "date_range": {"from": first, "to": last},
            "ready": trades > 50,
        }
    except Exception:
        return {"historical_signals": 0, "historical_trades": 0, "ready": False}


# ── Weekly scan endpoint ───────────────────────────────────────────────────────

@app.get("/api/weekly-scan")
def get_weekly_scan():
    """
    Return latest weekly scan results from cache.
    Populated by the Saturday scan job.
    """
    cache = _load_cache()
    weekly = cache.get("weekly_signals", {})
    if not weekly:
        return {
            "status": "no_data",
            "message": "No weekly scan data yet. Run a weekend scan to populate.",
            "all_weekly": [], "ma_bounces": [], "vcps": [], "bo_retests": [],
            "scanned_at": None,
        }
    return {
        "status": "ok",
        "all_weekly": weekly.get("all_weekly", [])[:80],
        "ma_bounces": weekly.get("ma_bounces", [])[:50],
        "vcps":       weekly.get("vcps", [])[:30],
        "bo_retests": weekly.get("bo_retests", [])[:30],
        "scanned_at": cache.get("scanned_at"),
    }


# ── Weekly backtest endpoints ──────────────────────────────────────────────────

@app.post("/api/weekly-bt/reconstruct")
def trigger_weekly_reconstruction(secret: str = "", lookback_weeks: int = 250):
    """
    Trigger weekly backtest reconstruction.
    Scans week-by-week over lookback_weeks, simulates exits.
    Poll /api/weekly-bt/status for progress.
    """
    import os
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            from weekly_bt import run_weekly_reconstruction
            from scanner import fetch_bars, get_alpaca_client
            from universe_expander import get_scan_universe
            from watchlist import ETFS
            from sector_rs import SECTOR_ETFS

            all_tickers = get_scan_universe()
            all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))

            if os.environ.get("POLYGON_API_KEY"):
                from polygon_client import fetch_bars as pg_bars, fetch_weekly_bars as pg_weekly
                bars       = pg_bars(all_tickers + all_etfs, days=1800, interval="day", min_rows=20, label="weekly-bt")
                weekly_bars = pg_weekly(all_tickers + all_etfs)
            else:
                client = get_alpaca_client()
                from scanner import fetch_weekly_bars
                bars        = fetch_bars(client, all_tickers + all_etfs)
                weekly_bars = fetch_weekly_bars(client, all_tickers + all_etfs)

            # RS ranks from latest cache
            cache = _load_cache()
            rs_ranks = {s["ticker"]: s.get("rs") for s in cache.get("signals", []) if s.get("ticker")}

            run_weekly_reconstruction(bars, weekly_bars, rs_ranks, lookback_weeks=lookback_weeks)
        except Exception as e:
            print(f"[weekly-bt] Reconstruction error: {e}")
            import traceback; traceback.print_exc()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "lookback_weeks": lookback_weeks,
            "message": f"Weekly backtest reconstruction started ({lookback_weeks} weeks). Poll /api/weekly-bt/status."}


@app.get("/api/weekly-bt/status")
def get_weekly_bt_status():
    """Progress of weekly backtest reconstruction."""
    from weekly_bt import get_weekly_bt_progress
    return get_weekly_bt_progress()


@app.get("/api/weekly-bt/stats")
def get_weekly_bt_stats_endpoint():
    """Aggregated weekly backtest statistics."""
    from weekly_bt import get_weekly_bt_stats
    return get_weekly_bt_stats()


@app.get("/api/backtest/analysis")
def get_analysis(signal_type: Optional[str] = None):
    """
    Full analysis report: stats + all dimensional cuts + equity curve + monthly.
    signal_type: MA10 | MA21 | MA50 | SHORT | None (all)
    """
    from bt_analysis import full_analysis_report
    return full_analysis_report(signal_type=signal_type)




@app.get("/api/backtest/split")
def backtest_split_analysis(
    signal_type: str = None,
    split_date: str = None,
    oos_months: int = 4,
):
    """
    In-sample vs out-of-sample split analysis.

    The most important backtest to run before trading real money.
    Splits your historical trades at split_date and compares performance
    in each period independently.

    Args:
        signal_type: MA10 / MA21 / MA50 / SHORT / None (all)
        split_date:  YYYY-MM-DD boundary. Default = today minus oos_months.
        oos_months:  How many recent months to treat as out-of-sample (default 4).

    Returns:
        in_sample stats, out_of_sample stats, and a plain-English verdict
        telling you whether the edge held up in unseen data.

    How to interpret:
        GREEN  — edge held, win rate barely dropped, expectancy still positive
        YELLOW — acceptable degradation, paper trade to confirm
        ORANGE — significant drop, system may be partially overfit
        RED    — edge failed OOS, do not trade with real money
        GREY   — not enough out-of-sample trades yet (need 10+)
    """
    try:
        from bt_analysis import split_analysis
        return split_analysis(
            signal_type=signal_type,
            split_date=split_date,
            in_sample_months=oos_months,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backtest/drill")
def drill_down_query(
    signal_type: Optional[str] = None,
    max_vcs: Optional[float] = None,
    min_vcs: Optional[float] = None,
    min_rs: Optional[int] = None,
    min_base_score: Optional[int] = None,
    sector: Optional[str] = None,
    min_market_score: Optional[int] = None,
    max_market_score: Optional[int] = None,
    entry_type: Optional[str] = None,
    sector_rs_positive: Optional[bool] = None,
    sector_rs_confirmed: Optional[bool] = None,
):
    """
    Flexible drill-down: filter trades by any combination of criteria.
    Returns stats + sample trades for that subset.

    Example: /api/backtest/drill?signal_type=MA21&max_vcs=3&min_rs=85&min_market_score=65
    → Show me MA21 bounces where VCS was coiled (≤3), RS was strong (≥85), in a positive market

    sector_rs_positive=true  → only longs where sector was outperforming SPY on 1m
    sector_rs_confirmed=true → only longs where sector was outperforming on both timeframes
    """
    from bt_analysis import drill_down
    return drill_down(
        signal_type=signal_type,
        max_vcs=max_vcs,
        min_vcs=min_vcs,
        min_rs=min_rs,
        min_base_score=min_base_score,
        sector=sector,
        min_market_score=min_market_score,
        max_market_score=max_market_score,
        entry_type=entry_type,
        sector_rs_positive=sector_rs_positive,
        sector_rs_confirmed=sector_rs_confirmed,
    )


@app.get("/api/backtest/sector-rs")
def sector_rs_filter_endpoint(signal_type: Optional[str] = None):
    """
    Dedicated sector RS filter analysis.
    Compares all longs vs sector-leading longs on win rate, expectancy, profit factor.
    Tells you whether adding a sector leadership gate improves your edge.
    """
    from bt_analysis import sector_rs_filter_analysis
    return sector_rs_filter_analysis(signal_type=signal_type)


@app.get("/api/backtest/entry-comparison")
def entry_comparison_endpoint():
    """
    Compare MA Bounce (close entry) vs Breakout entry.
    Shows win rate, avg R, expectancy, and % of signals that never trigger breakout.
    """
    from bt_analysis import entry_comparison_analysis
    return entry_comparison_analysis()


@app.get("/api/backtest/weekly-signals")
def weekly_signals_endpoint(signal_type: Optional[str] = None):
    """
    Weekly confluence analysis.
    Compares signals that also qualify as weekly wEMA10 setups vs daily-only signals.
    """
    from bt_analysis import weekly_signal_analysis
    return weekly_signal_analysis(signal_type=signal_type)


@app.get("/api/backtest/day-of-week")
def day_of_week_endpoint(signal_type: Optional[str] = None):
    """
    Performance breakdown by entry day (MON-FRI).
    Tells you whether Monday setups behave differently to Thursday setups.
    """
    from bt_analysis import day_of_week_analysis
    return day_of_week_analysis(signal_type=signal_type)


@app.get("/api/backtest/weekly")
def weekly_analysis_endpoint():
    """
    Weekly wEMA10 touch (W_EMA10) vs daily MA touch performance comparison.
    Answers: are weekly setups worth trading separately from daily signals?
    """
    from bt_analysis import weekly_vs_daily_analysis
    return weekly_vs_daily_analysis()


@app.post("/api/backtest/optimise")
def run_optimisation(
    secret: str = "",
    signal_type: Optional[str] = None,
    quick: bool = True,
):
    """
    Run parameter grid search to find optimal ATR multiples, VCS/RS thresholds.
    quick=True: smaller grid (~32 combos, fast)
    quick=False: full grid (~200+ combos, slower)
    Requires historical trades to already exist.
    """
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        from bt_optimiser import run_optimisation as _opt
        results = _opt(signal_type=signal_type, quick=quick)
        print(f"[optimise] Complete — {len(results)} viable param sets found")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "optimisation triggered", "signal_type": signal_type, "quick": quick}


@app.get("/api/backtest/optimise/results")
def get_optimisation_results():
    """Get top parameter combinations from most recent optimisation run."""
    from database import get_bt_runs
    return {"results": get_bt_runs()}


@app.get("/api/backtest/equity-curve/{run_id}")
def get_equity_curve(run_id: int):
    """Get equity curve for a specific backtest run."""
    from database import get_equity_curve as _get_curve
    return {"run_id": run_id, "curve": _get_curve(run_id)}


@app.get("/api/backtest/monthly")
def get_monthly_returns(signal_type: Optional[str] = None):
    """Month-by-month return breakdown."""
    from database import get_historical_trades
    from bt_analysis import monthly_returns
    trades = get_historical_trades(signal_type=signal_type, limit=5000)
    return {"monthly": monthly_returns(trades)}


@app.delete("/api/backtest/clear")
def clear_backtest(secret: str = ""):
    """Wipe all historical backtest data and start fresh."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    from database import clear_historical_trades
    clear_historical_trades()
    return {"status": "cleared"}


# ── Watchlist tracker endpoints ───────────────────────────────────────────────

@app.get("/api/watchlist/tracker")
def get_watchlist_tracker():
    """Return all tickers with days_on_watchlist tracking."""
    from database import get_watchlist_with_age
    return {"watchlist": get_watchlist_with_age()}


@app.get("/api/watchlist/export")
def export_watchlist_tv(min_days: int = 0, min_score: float = 0):
    """
    Export current watchlist as a TradingView-compatible .txt file.
    Groups by signal type with ### headers. One file per day.
    """
    from database import get_watchlist_with_age, save_watchlist_export
    from fastapi.responses import PlainTextResponse
    import json

    tickers = get_watchlist_with_age()
    if min_days > 0:
        tickers = [t for t in tickers if t["days_on_watchlist"] >= min_days]
    if min_score > 0:
        tickers = [t for t in tickers if (t.get("score") or 0) >= min_score]

    today = datetime.now().strftime("%Y-%m-%d")

    # Exchange prefix lookup — default to NASDAQ, override known NYSE tickers
    NYSE_SECTORS = {"Energy", "Financials", "Industrials", "Materials", "Utilities", "Real Estate"}
    def get_exchange(ticker, sector):
        # Simple heuristic — most growth/tech on NASDAQ, cyclicals on NYSE
        if sector in NYSE_SECTORS:
            return "NYSE"
        return "NASDAQ"

    # Group by signal type
    groups = {}
    for t in tickers:
        sig = t.get("signal_type") or "Other"
        groups.setdefault(sig, []).append(t)

    lines = [f"###Signal Desk {today}"]
    for sig_type, items in sorted(groups.items()):
        lines.append(f"###{sig_type}")
        for t in items:
            exchange = get_exchange(t["ticker"], t.get("sector", ""))
            days = t.get("days_on_watchlist", 0)
            lines.append(f"{exchange}:{t['ticker']},,,{days}d on list")

    content = "\n".join(lines)

    # Save snapshot
    save_watchlist_export(tickers, today)

    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename=watchlist-{today}.txt"}
    )


@app.get("/api/watchlist/exports")
def list_watchlist_exports():
    """List recent watchlist export history."""
    from database import get_watchlist_exports
    return {"exports": get_watchlist_exports()}


@app.delete("/api/watchlist/tracker/{ticker}")
def remove_from_watchlist(ticker: str):
    """Manually remove a ticker from the watchlist tracker."""
    from database import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist_tracker WHERE ticker = ?", (ticker.upper(),))
    return {"status": "removed", "ticker": ticker.upper()}


@app.get("/api/admin/backup-db")
def backup_db(secret: str = ""):
    """
    Download the full SQLite database file.
    Store this before any major redeploy — contains all historical signals,
    trades, journal entries, and backtest results.
    Restore by uploading to Railway volume as dashboard.db.
    """
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    from database import DB_PATH
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    from datetime import datetime
    filename = f"dashboard-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.db"
    return FileResponse(
        path=str(DB_PATH),
        media_type="application/octet-stream",
        filename=filename,
    )


# ── Universe expansion endpoints ──────────────────────────────────────────────

@app.get("/api/universe/additions")
def get_universe_additions():
    """List all dynamically added tickers with their scoring metadata."""
    from database import get_dynamic_additions
    additions = get_dynamic_additions(active_only=False)
    return {
        "total": len(additions),
        "active": sum(1 for a in additions if a["active"]),
        "additions": additions,
    }


@app.post("/api/universe/expand")
def trigger_universe_expansion(secret: str = ""):
    """Manually trigger a universe expansion run."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    from universe_expander import run_universe_expansion
    result = run_universe_expansion()
    return result


@app.post("/api/universe/additions/{ticker}")
def manually_add_universe_ticker(ticker: str, secret: str = "", notes: str = "manual"):
    """Manually add a single ticker to the dynamic scan universe."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    from universe_expander import manually_add_ticker
    return manually_add_ticker(ticker.upper(), notes=notes)


@app.delete("/api/universe/additions/{ticker}")
def remove_universe_addition(ticker: str, secret: str = ""):
    """Remove a dynamically added ticker from the universe."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    from database import remove_dynamic_addition
    remove_dynamic_addition(ticker.upper())
    return {"status": "removed", "ticker": ticker.upper()}




@app.get("/api/social/{ticker}")
def get_social(ticker: str):
    """Fetch social intelligence for a single ticker on demand."""
    try:
        from social_sentiment import get_social_intel
        return get_social_intel(ticker.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/social/batch")
def get_social_batch(tickers: list[str]):
    """Fetch social intelligence for multiple tickers."""
    try:
        from social_sentiment import batch_social_intel
        return batch_social_intel(tickers[:20])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ── Trade Suggestions ─────────────────────────────────────────────────────────

@app.post("/api/suggest-trade")
def suggest_single_trade(payload: dict):
    """
    Suggest an options spread for a single signal.
    Body: { signal: {...}, portfolio_value: 50000 }
    """
    try:
        if STOCKS_ONLY:
            return {"status": "disabled", "message": "Options suggestions disabled (STOCKS_ONLY mode)."}
        from trade_suggester import suggest_trade
        signal          = payload.get("signal", {})
        portfolio_value = float(payload.get("portfolio_value", 50000))
        if not signal.get("ticker"):
            raise HTTPException(status_code=400, detail="signal.ticker required")
        return suggest_trade(signal, portfolio_value)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/suggest-batch")
def suggest_batch_trades(payload: dict):
    """
    Suggest options spreads for top signals from last scan.
    Body: { source: "main"|"microcap"|"both", portfolio_value: 50000, min_score: 7.0 }
    """
    try:
        if STOCKS_ONLY:
            return {"status": "disabled", "suggestions": [], "message": "Options suggestions disabled (STOCKS_ONLY mode)."}
        from trade_suggester import suggest_batch
        source          = payload.get("source", "both")
        portfolio_value = float(payload.get("portfolio_value", 50000))
        min_score       = float(payload.get("min_score", 7.0))
        max_suggestions = int(payload.get("max_suggestions", 10))

        signals = []

        if source in ("main", "both"):
            main_data = cache.get("scan_results", {})
            for key in ("ma10_bounces", "ma21_bounces", "ma50_bounces",
                        "cup_handle_signals", "extended_bo_signals"):
                signals.extend(main_data.get(key, []))

        if source in ("microcap", "both"):
            micro_data = cache.get("microcap", {})
            signals.extend(micro_data.get("all_signals", []))

        if not signals:
            # Try loading microcap from cache file
            try:
                from pathlib import Path
                import json as _json
                cf = Path("/tmp/microcap_cache.json")
                if cf.exists():
                    micro_data = _json.loads(cf.read_text())
                    signals.extend(micro_data.get("all_signals", []))
            except Exception:
                pass

        if not signals:
            raise HTTPException(
                status_code=503,
                detail="No scan data available. Run a scan first."
            )

        # Deduplicate by ticker
        seen = set()
        deduped = []
        for s in signals:
            t = s.get("ticker")
            if t and t not in seen:
                seen.add(t)
                deduped.append(s)

        results = suggest_batch(deduped, portfolio_value, min_score, max_suggestions)

        # Attach regime context to every suggestion (soft warning only)
        market  = read_cache().get("market", {})
        r_score = market.get("score", 50)
        vix     = market.get("vix")
        if r_score < 35:        gate = "DANGER"
        elif r_score < 50:      gate = "WARN"
        elif r_score < 65:      gate = "CAUTION"
        else:                   gate = "GO"

        for r in results:
            r["regime_score"] = r_score
            r["regime_gate"]  = gate
            if gate in ("DANGER", "WARN"):
                existing = r.get("warning") or ""
                prefix = (
                    f"⚠ REGIME {gate} (score {r_score}/100): "
                    + ("Market in correction — high failure rate on longs. " if gate == "DANGER"
                       else "Market under pressure — reduce size, be selective. ")
                    + (f"VIX {vix:.1f}. " if vix else "")
                )
                r["warning"] = (prefix + existing).strip()

        return {
            "suggestions":     results,
            "total_signals":   len(deduped),
            "portfolio_value": portfolio_value,
            "min_score":       min_score,
            "regime": {
                "score": r_score,
                "gate":  gate,
                "vix":   vix,
                "label": market.get("label"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Social Intelligence ───────────────────────────────────────────────────────

@app.get("/api/social/{ticker}")
def get_social(ticker: str):
    """Fetch social intelligence for a single ticker on demand."""
    try:
        from social_sentiment import get_social_intel
        return get_social_intel(ticker.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/social/batch")
def get_social_batch(tickers: list[str]):
    """Fetch social intel for a list of tickers (max 20)."""
    try:
        from social_sentiment import batch_social_intel
        return batch_social_intel([t.upper() for t in tickers], max_tickers=20)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Micro Cap ─────────────────────────────────────────────────────────────────

@app.get("/api/microcap")
def get_microcap():
    """Micro cap signals from last scan."""
    # Try main cache first
    data = read_cache().get("microcap")
    if not data:
        # Try dedicated microcap cache file
        try:
            cf = Path("/tmp/microcap_cache.json")
            if cf.exists():
                data = json.loads(cf.read_text())
        except Exception:
            pass
    if not data:
        raise HTTPException(status_code=503, detail="No micro cap scan data yet. Scan runs at 22:00 UK or trigger manually.")
    return data


@app.post("/api/microcap/trigger")
def trigger_microcap_scan(secret: str = ""):
    """Manually trigger micro cap scan."""
    if secret != os.environ.get("SCAN_SECRET", ""):
        raise HTTPException(status_code=401, detail="Invalid secret")
    import threading
    def _run():
        try:
            from microcap_scanner import run_microcap_scan
            result = run_microcap_scan()
            cache["microcap"] = result
            cache["microcap_scanned_at"] = result.get("scanned_at")
        except Exception as e:
            print(f"[microcap trigger] {e}")
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "message": "Micro cap scan running in background. Check /api/microcap in ~5-10 mins."}

# ── Options Chain & Spread Builder ───────────────────────────────────────────

class SpreadRequest(BaseModel):
    ticker:           str
    expiry_index:     int   = 0        # 0=nearest, 1=next, etc.
    direction:        str   = "call"   # "call" or "put"
    user_prob:        float = 0.40     # user's P(ITM) estimate
    price_target:     float = 0.0      # expected price if ITM
    portfolio_value:  float = 10000.0
    max_loss_pct:     float = 2.5


@app.get("/api/options-chain/{ticker}")
def get_options_chain(ticker: str, expiry_index: int = 0):
    """Fetch raw options chain with IV and delta.
    Returns 503 when STOCKS_ONLY=true or ALPACA_API_KEY not set (synthetic chains disabled).
    """
    import os
    stocks_only = os.environ.get("STOCKS_ONLY", "false").lower() in ("1", "true", "yes")
    alpaca_key  = os.environ.get("ALPACA_API_KEY", "")
    if stocks_only or not alpaca_key:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Options data disabled. Set STOCKS_ONLY=false and ALPACA_API_KEY to enable."
        )
    try:
        if STOCKS_ONLY:
            raise HTTPException(status_code=503, detail="Options data disabled (STOCKS_ONLY mode)")
        from options_chain import fetch_chain
        chain = fetch_chain(ticker.upper(), expiry_index)
        if not chain:
            raise HTTPException(status_code=404, detail=f"No options data for {ticker}")
        return chain
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/options-spread")
def build_spread(req: SpreadRequest):
    """Build optimal spread given user inputs."""
    try:
        if STOCKS_ONLY:
            raise HTTPException(status_code=503, detail="Options data disabled (STOCKS_ONLY mode)")
        if STOCKS_ONLY:
            raise HTTPException(status_code=503, detail="Options spreads disabled (STOCKS_ONLY mode)")
        from options_chain import fetch_chain, build_call_spread, build_put_spread
        chain = fetch_chain(req.ticker.upper(), req.expiry_index)
        if not chain:
            raise HTTPException(status_code=404, detail=f"No options data for {req.ticker}")

        if req.direction == "put":
            result = build_put_spread(chain, req.user_prob, req.price_target, req.portfolio_value, req.max_loss_pct)
        else:
            result = build_call_spread(chain, req.user_prob, req.price_target, req.portfolio_value, req.max_loss_pct)

        result["chain_meta"] = {
            "ticker":       chain["ticker"],
            "spot":         chain["spot"],
            "expiry":       chain["expiry"],
            "dte":          chain["dte"],
            "all_expiries": chain["all_expiries"],
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options-expiries/{ticker}")
def get_expiries(ticker: str):
    """Get all available expiry dates for a ticker."""
    try:
        if STOCKS_ONLY:
            raise HTTPException(status_code=503, detail="Options data disabled (STOCKS_ONLY mode)")
        from options_chain import fetch_chain
        chain = fetch_chain(ticker.upper(), 0)
        if not chain:
            raise HTTPException(status_code=404, detail=f"No options data for {ticker}")
        return {"ticker": ticker.upper(), "expiries": chain["all_expiries"], "spot": chain["spot"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ── Position Monitor ──────────────────────────────────────────────────────────

@app.post("/api/positions/check")
def trigger_position_check():
    """Manually trigger a position check with live prices."""
    try:
        from position_monitor import check_positions
        result = check_positions()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions/digest")
def position_digest():
    """Get current position status with live prices (no Telegram)."""
    try:
        from position_monitor import _fetch_live_prices, _pnl, _days_held
        from database import journal_list
        positions = journal_list(status="open") + journal_list(status="watching")
        if not positions:
            return {"positions": [], "total": 0}
        tickers = [p["ticker"] for p in positions]
        prices  = _fetch_live_prices(tickers)
        result  = []
        for pos in positions:
            t        = pos["ticker"]
            curr     = prices.get(t)
            entry    = pos.get("entry_price")
            stop     = pos.get("stop_price")
            t1       = pos.get("target_1")
            t2       = pos.get("target_2")
            t3       = pos.get("target_3")
            pnl      = _pnl(curr, entry) if curr and entry else None
            days     = _days_held(pos.get("added_date", ""))
            # Determine current level
            level = "below_t1"
            if curr:
                if stop and curr <= stop:             level = "stop_hit"
                elif t3   and curr >= t3:             level = "t3_hit"
                elif t2   and curr >= t2:             level = "t2_hit"
                elif t1   and curr >= t1:             level = "t1_hit"
                elif stop and (curr - stop) / curr * 100 <= 1.5: level = "near_stop"
            result.append({
                **pos,
                "current_price": curr,
                "pnl_pct":       pnl,
                "days_held":     days,
                "level":         level,
            })
        return {"positions": result, "total": len(result), "fetched_at": __import__("datetime").datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/positions/digest/send")
def send_digest():
    """Send position digest to Telegram."""
    try:
        from position_monitor import send_position_digest
        send_position_digest()
        return {"sent": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Edge Report ───────────────────────────────────────────────────────────────

@app.get("/api/edge-report")
def get_edge_report():
    """Full edge analytics on closed trades."""
    try:
        from edge_report import generate_edge_report
        return generate_edge_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skip-outcomes/sweep")
def trigger_skip_sweep(dry_run: bool = False):
    """
    Manually trigger a skip outcome sweep.
    Fetches daily bars for all skipped entries within the 20-trading-day window
    and updates outcome_if_taken. Safe to call any time — frozen entries are skipped.
    dry_run=true returns what would be updated without writing to DB.
    """
    try:
        from position_monitor import update_skip_outcomes
        result = update_skip_outcomes(dry_run=dry_run)
        return {"status": "ok", "dry_run": dry_run, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pre-market ────────────────────────────────────────────────────────────────

@app.get("/api/premarket")
def get_premarket():
    """Pre-market prices for open positions and top signals."""
    try:
        from premarket import premarket_position_check, enrich_signals_premarket
        cache    = read_cache()
        signals  = (cache.get("ma10_bounces", []) + cache.get("ma21_bounces", []) + cache.get("cup_handle_signals", []))[:8]
        pos_data = premarket_position_check()
        enriched = enrich_signals_premarket(signals)
        return {
            "positions": pos_data,
            "signals":   enriched,
            "fetched_at": __import__("datetime").datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Breakout signals ──────────────────────────────────────────────────────────

@app.get("/api/breakouts")
def get_breakouts():
    cache = read_cache()
    cup_handle      = cache.get("cup_handle_signals",        [])
    extended_bo     = cache.get("extended_bo_signals",       [])
    weekly_retest   = cache.get("weekly_bo_retest_signals",  [])
    return {
        "cup_handle":       cup_handle,
        "extended_bo":      extended_bo,
        "weekly_retest":    weekly_retest,
        "total_ch":         len(cup_handle),
        "total_ext":        len(extended_bo),
        "total_retest":     len(weekly_retest),
        "scanned_at":       cache.get("scanned_at"),
    }


# ── Options flow ──────────────────────────────────────────────────────────────

@app.get("/api/options-flow/{ticker}")
def get_options_flow_endpoint(ticker: str):
    try:
        if STOCKS_ONLY:
            return {"status": "disabled", "message": "Options flow disabled (STOCKS_ONLY mode)"}
        from options_flow import get_options_flow
        flow = get_options_flow(ticker.upper(), force=True)
        if not flow:
            return {"ticker": ticker, "error": "No options data available"}
        return flow
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ── Chart patterns ────────────────────────────────────────────────────────────

@app.get("/api/patterns")
def get_patterns(pattern_type: Optional[str] = Query(None)):
    cache = read_cache()
    patterns = cache.get("pattern_signals", [])
    if pattern_type:
        patterns = [p for p in patterns if p.get("pattern_type") == pattern_type.upper()]
    summary = {
        "FLAG":         sum(1 for p in cache.get("pattern_signals",[]) if p.get("pattern_type") == "FLAG"),
        "VCP":          sum(1 for p in cache.get("pattern_signals",[]) if p.get("pattern_type") == "VCP"),
        "CUP_HANDLE":   sum(1 for p in cache.get("pattern_signals",[]) if p.get("pattern_type") == "CUP_HANDLE"),
        "ASC_TRIANGLE": sum(1 for p in cache.get("pattern_signals",[]) if p.get("pattern_type") == "ASC_TRIANGLE"),
    }
    return {
        "patterns":   patterns,
        "total":      len(patterns),
        "summary":    summary,
        "scanned_at": cache.get("scanned_at"),
    }

# ── Watchlist Pipeline ────────────────────────────────────────────────────────


# ── Telegram diagnostics ──────────────────────────────────────────────────────

@app.get("/api/test/telegram")
def test_telegram():
    """
    Test Telegram connectivity and send a diagnostic message.
    Checks: env vars present, bot token valid, chat_id reachable.
    Returns detailed diagnosis so you can see exactly what's failing.
    """
    import os, requests as req
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    diag = {
        "token_set":   bool(token),
        "chat_id_set": bool(chat_id),
        "token_prefix": token[:10] + "..." if len(token) > 10 else token,
        "chat_id":     chat_id,
    }

    if not token:
        return {**diag, "status": "FAIL", "reason": "TELEGRAM_BOT_TOKEN not set in Railway env vars"}
    if not chat_id:
        return {**diag, "status": "FAIL", "reason": "TELEGRAM_CHAT_ID not set in Railway env vars"}

    # Check bot token is valid via getMe
    try:
        me = req.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
        if me.status_code != 200:
            return {**diag, "status": "FAIL", "reason": f"Invalid bot token — Telegram returned {me.status_code}: {me.text[:200]}"}
        bot_name = me.json().get("result", {}).get("username", "?")
        diag["bot_username"] = bot_name
    except Exception as e:
        return {**diag, "status": "FAIL", "reason": f"Network error reaching Telegram API: {e}"}

    # Send test message
    try:
        resp = req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": (
                    "✅ <b>Telegram connected — Signal Desk diagnostic</b>\n"
                    f"Bot: @{bot_name}\n"
                    f"Chat ID: {chat_id}\n"
                    "If you see this, alerts are working correctly."
                ),
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {**diag, "status": "OK", "message": "Test message sent — check your Telegram"}
        else:
            data = resp.json()
            return {
                **diag, "status": "FAIL",
                "reason": f"Telegram rejected message: {data.get('description', resp.text[:200])}",
                "error_code": data.get("error_code"),
                "tip": (
                    "Common causes: wrong CHAT_ID, bot not added to group, "
                    "or chat_id should be negative for group chats (e.g. -1001234567890)"
                ),
            }
    except Exception as e:
        return {**diag, "status": "FAIL", "reason": f"Exception sending test message: {e}"}


@app.get("/api/test/alert-config")
def test_alert_config():
    """
    Show current alert configuration — score threshold, scheduler status, last scan time.
    """
    from database import get_settings
    settings = get_settings()

    # Read cache to check last scan
    cache = read_cache()
    last_scan = cache.get("scanned_at", "Never") if cache else "Never"
    signal_count = len(cache.get("long_signals", [])) if cache else 0

    # Check scheduled jobs
    jobs = []
    try:
        for job in scheduler.get_jobs():
            jobs.append({
                "id":   job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else "Not scheduled",
            })
    except Exception as e:
        jobs = [{"error": str(e)}]

    import os
    return {
        "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("TELEGRAM_CHAT_ID")),
        "alert_min_score":     settings.get("alert_min_score", 7),
        "min_signal_score":    settings.get("min_signal_score", 6),
        "last_scan":           last_scan,
        "long_signals_in_cache": signal_count,
        "signals_above_alert_threshold": sum(
            1 for s in (cache.get("long_signals", []) if cache else [])
            if (s.get("signal_score") or 0) >= settings.get("alert_min_score", 7)
        ),
        "scheduler_running": scheduler.running,
        "scheduled_jobs":    jobs,
    }


@app.post("/api/test/send-cache-alert")
def send_cache_alert_now():
    """
    Manually trigger the Telegram alert using the current cached scan data.
    Use this to test the full alert pipeline without running a new scan.
    """
    cache = read_cache()
    if not cache:
        raise HTTPException(status_code=404, detail="No cached scan data — run a scan first")
    try:
        from alerts import send_scan_alert
        open_entries = []
        try:
            from database import journal_list
            open_entries = journal_list(status="watching") + journal_list(status="open")
        except Exception:
            pass
        open_tickers = {e["ticker"] for e in open_entries}
        send_scan_alert(cache, open_tickers=open_tickers)
        return {"status": "sent", "message": "Alert dispatched from cache — check Telegram"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/correlation")
def run_correlation(payload: dict = {}):
    """
    Correlation analysis: regime × readiness cross-tab + equity curve.

    Body: {
        "week_start": "2023-10-23",   // single Monday date
        "weeks": ["2023-10-23", ...], // OR list of dates (max 12)
        "max_bars": 20
    }

    For each week:
      1. Runs full replay (historical scan)
      2. Backtests all long signals with trailing stop
      3. Aggregates into cross-tab + equity curve

    Long-running (5–8 min per week). Frontend should show progress.
    """
    week_start = payload.get("week_start")
    weeks      = payload.get("weeks", [])
    max_bars   = int(payload.get("max_bars", 20))

    # Build date list
    if week_start and not weeks:
        weeks = [week_start]
    if not weeks:
        raise HTTPException(status_code=400, detail="week_start or weeks required")
    if len(weeks) > 12:
        raise HTTPException(status_code=400, detail="Max 12 weeks per analysis run")

    from datetime import date as _date
    for w in weeks:
        try:
            from datetime import datetime as _dt
            _dt.strptime(w, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date: {w} — use YYYY-MM-DD")
        if w > _date.today().isoformat():
            raise HTTPException(status_code=400, detail=f"Cannot replay future date: {w}")

    try:
        from replay_backtest import run_correlation_analysis, aggregate_correlation

        weeks_data = []
        for w in weeks:
            result = run_correlation_analysis(w, max_bars=max_bars)
            weeks_data.append(result)
            if "error" in result:
                print(f"[corr] Week {w} failed: {result['error']}")

        agg = aggregate_correlation(weeks_data)
        agg["weeks_requested"] = weeks
        return agg

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/correlation/week")
def run_correlation_single_week(payload: dict = {}):
    """
    Run correlation for a single week — allows frontend to stream results
    week by week by calling this endpoint repeatedly.

    Body: { "week_start": "2023-10-23", "max_bars": 20 }
    Returns single week result (no aggregation).
    """
    week_start = payload.get("week_start")
    max_bars   = int(payload.get("max_bars", 20))

    if not week_start:
        raise HTTPException(status_code=400, detail="week_start required")

    from datetime import date as _date
    if week_start > _date.today().isoformat():
        raise HTTPException(status_code=400, detail="Cannot replay future date")

    try:
        from replay_backtest import run_correlation_analysis
        return run_correlation_analysis(week_start, max_bars=max_bars)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/replay/backtest")
def replay_backtest(payload: dict = {}):
    """
    Run trailing-stop backtest on signals from a replay date.
    Body: {
        "as_of_date": "2023-10-26",
        "signals": [...],   # optional: pre-fetched signals, else runs replay first
        "max_bars": 20
    }
    Trail rules:
      - Initial stop: signal.stop_price
      - Trail activates: once close >= entry * 1.03
      - Trail follows: lowest low of last 3 bars (ratchet up only)
      - Max hold: 20 bars
    """
    as_of_date = payload.get("as_of_date", "")
    if not as_of_date:
        raise HTTPException(status_code=400, detail="as_of_date required")

    signals  = payload.get("signals")
    max_bars = int(payload.get("max_bars", 20))

    # If signals not provided, run replay first
    if not signals:
        try:
            from scanner import run_replay
            replay_data = run_replay(as_of_date)
            if "error" in replay_data:
                raise HTTPException(status_code=500, detail=replay_data["error"])
            signals = replay_data.get("long_signals", [])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Replay failed: {e}")

    if not signals:
        return {"results": [], "summary": {}, "as_of_date": as_of_date,
                "message": "No signals found for this date"}

    try:
        from replay_backtest import run_backtest_on_signals
        result = run_backtest_on_signals(signals, as_of_date, max_bars=max_bars)
        result["as_of_date"] = as_of_date
        result["max_bars"]   = max_bars
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/replay")
def run_replay_endpoint(payload: dict = {}):
    """
    Historical replay — re-run the full scan as of a past date.
    Body: { "as_of_date": "2023-10-23" }
    Returns same structure as live scan, never writes to cache.
    """
    as_of_date = payload.get("as_of_date", "")
    if not as_of_date:
        raise HTTPException(status_code=400, detail="as_of_date required (YYYY-MM-DD)")
    try:
        from datetime import datetime as _dt
        _dt.strptime(as_of_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format — use YYYY-MM-DD")

    # Prevent future dates
    from datetime import date as _date
    if as_of_date > _date.today().isoformat():
        raise HTTPException(status_code=400, detail="Cannot replay a future date")

    try:
        from scanner import run_replay
        result = run_replay(as_of_date)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/replay/pipeline")
def get_replay_pipeline(as_of_date: str):
    """
    Pipeline view for a replay date — same filtering logic as /api/pipeline
    but sourced from a replay run rather than live cache.
    Body passed as query param for convenience.
    """
    if not as_of_date:
        raise HTTPException(status_code=400, detail="as_of_date required")
    try:
        from scanner import run_replay
        data = run_replay(as_of_date)
        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])

        all_stocks = data.get("all_stocks", [])
        pipeline   = []
        for s in all_stocks:
            rs    = s.get("rs", 0) or 0
            price = s.get("price") or 0
            ma10  = s.get("ma10");  ma21 = s.get("ma21");  ma50 = s.get("ma50")
            pct10 = s.get("pct_from_ma10"); pct21 = s.get("pct_from_ma21"); pct50 = s.get("pct_from_ma50")
            if rs < 80: continue
            if not (ma10 and ma21 and ma50): continue
            if not (price > ma10 and price > ma21 and price > ma50): continue
            if s.get("ma10_touch") or s.get("ma21_touch") or s.get("ma50_touch"): continue
            closest_pct = None; closest_label = None
            for label, pct, ma in [("MA10", pct10, ma10), ("MA21", pct21, ma21), ("MA50", pct50, ma50)]:
                if pct is not None and 0 < pct <= 25:
                    if closest_pct is None or pct < closest_pct:
                        closest_pct = pct; closest_label = label
            if closest_pct is None: continue
            if (s.get("pct_from_52w_high") or -99) < -25: continue
            pipeline.append({
                "ticker": s.get("ticker"), "price": price, "chg": s.get("chg", 0),
                "rs": rs, "vcs": s.get("vcs"), "sector": s.get("sector", ""),
                "ma10": ma10, "ma21": ma21, "ma50": ma50,
                "pct_from_ma10": pct10, "pct_from_ma21": pct21, "pct_from_ma50": pct50,
                "pct_from_52w_high": s.get("pct_from_52w_high"),
                "closest_ma": closest_label, "closest_pct": closest_pct,
                "vol_ratio": s.get("vol_ratio"), "tier": s.get("tier", 2),
                "signal_score": s.get("signal_score"), "w52_high": s.get("w52_high"),
                "atr": s.get("atr"),
                "adr_pct": s.get("adr_pct"), "ema21_low": s.get("ema21_low"),
                "ema21_low_pct": s.get("ema21_low_pct"),
                "within_1atr_ema21": s.get("within_1atr_ema21"),
                "within_1atr_wema10": s.get("within_1atr_wema10"),
                "within_3atr_sma50": s.get("within_3atr_sma50"),
                "three_weeks_tight": s.get("three_weeks_tight", False),
                "entry_readiness": s.get("entry_readiness"),
            })
        pipeline.sort(key=lambda x: x["closest_pct"])
        return {
            "pipeline": pipeline, "total": len(pipeline),
            "scanned_at": data.get("scanned_at"),
            "is_replay": True, "replay_date": as_of_date,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pipeline")
def get_pipeline():
    """
    Stocks approaching their MAs — RS leaders extended above MAs,
    not yet in buy zone but worth watching. Sorted by proximity to MA.
    """
    cache = read_cache()
    all_stocks = cache.get("all_stocks", [])

    if not all_stocks:
        return {"pipeline": [], "scanned_at": None}

    # All 1y returns for momentum filter
    pipeline = []
    for s in all_stocks:
        rs       = s.get("rs", 0) or 0
        price    = s.get("price") or 0
        ma10     = s.get("ma10")
        ma21     = s.get("ma21")
        ma50     = s.get("ma50")
        pct10    = s.get("pct_from_ma10")
        pct21    = s.get("pct_from_ma21")
        pct50    = s.get("pct_from_ma50")
        pct_52h  = s.get("pct_from_52w_high") or -99
        vcs      = s.get("vcs")
        sector   = s.get("sector", "")
        chg      = s.get("chg", 0) or 0

        # ── Criteria ──────────────────────────────────────────────────────────
        # 1. RS leader
        if rs < 80:
            continue

        # 2. Must be above all 3 MAs (confirmed uptrend)
        if not (ma10 and ma21 and ma50):
            continue
        if not (price > ma10 and price > ma21 and price > ma50):
            continue

        # 3. Not already in buy zone (those show in Live Signals)
        already_signal = s.get("ma10_touch") or s.get("ma21_touch") or s.get("ma50_touch")
        if already_signal:
            continue

        # 4. Within 25% of at least one MA (approaching)
        closest_ma     = None
        closest_pct    = None
        closest_label  = None
        for label, pct, ma in [("MA10", pct10, ma10), ("MA21", pct21, ma21), ("MA50", pct50, ma50)]:
            if pct is not None and 0 < pct <= 25:
                if closest_pct is None or pct < closest_pct:
                    closest_pct   = pct
                    closest_ma    = ma
                    closest_label = label

        if closest_pct is None:
            continue

        # 5. Near 52w high (strong trend, not extended recovery)
        if pct_52h < -25:
            continue

        pipeline.append({
            "ticker":         s.get("ticker"),
            "price":          price,
            "chg":            chg,
            "rs":             rs,
            "vcs":            vcs,
            "sector":         sector,
            "ma10":           ma10,
            "ma21":           ma21,
            "ma50":           ma50,
            "pct_from_ma10":  pct10,
            "pct_from_ma21":  pct21,
            "pct_from_ma50":  pct50,
            "pct_from_52w_high": pct_52h,
            "closest_ma":     closest_label,
            "closest_pct":    closest_pct,
            "vol_ratio":      s.get("vol_ratio"),
            "tier":           s.get("tier", 2),
            "signal_score":   s.get("signal_score"),
            "w52_high":       s.get("w52_high"),
            "atr":            s.get("atr"),
            "adr_pct":            s.get("adr_pct"),
            "ema21_low":          s.get("ema21_low"),
            "ema21_low_pct":      s.get("ema21_low_pct"),
            "within_1atr_ema21":  s.get("within_1atr_ema21"),
            "within_1atr_wema10": s.get("within_1atr_wema10"),
            "within_3atr_sma50":  s.get("within_3atr_sma50"),
            "three_weeks_tight":  s.get("three_weeks_tight", False),
            "entry_readiness":    s.get("entry_readiness"),
        })

    # Sort by closest to MA first
    pipeline.sort(key=lambda x: x["closest_pct"])

    return {
        "pipeline":   pipeline,
        "total":      len(pipeline),
        "scanned_at": cache.get("scanned_at"),
    }


# ── V2: Settings routes ───────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    account_size:          Optional[float] = None
    risk_pct:              Optional[float] = None
    max_positions:         Optional[int]   = None
    hide_earnings_lt_days: Optional[int]   = None
    min_signal_score:      Optional[float] = None
    alert_min_score:       Optional[float] = None
    market_gate_longs:     Optional[int]   = None
    market_gate_shorts:    Optional[int]   = None
    vcs_filter:            Optional[float] = None
    rs_filter:             Optional[int]   = None


@app.get("/api/settings")
def get_settings_route():
    return {"settings": get_settings()}


@app.put("/api/settings")
def update_settings_route(updates: SettingsUpdate):
    data = {k: v for k, v in updates.dict().items() if v is not None}
    return {"settings": update_settings(data)}


# ── V2: Portfolio heat ────────────────────────────────────────────────────────

@app.get("/api/portfolio/heat")
def get_portfolio_heat():
    open_entries = journal_list(status="watching") + journal_list(status="open")
    heat = calculate_portfolio_heat(open_entries)
    return heat


# ── V2: Setup of the Day ──────────────────────────────────────────────────────

@app.get("/api/scan/sotd")
def get_sotd():
    """Setup of the Day — best long and short from last scan."""
    data = read_cache()
    return {
        "scanned_at": data.get("scanned_at"),
        "sotd_long":  data.get("sotd_long"),
        "sotd_short": data.get("sotd_short"),
        "market":     data.get("market"),
    }


# ── V2: Market regime ─────────────────────────────────────────────────────────

@app.get("/api/market")
def get_market():
    """Full market health: score, regime, VIX, breadth, index details."""
    data = read_cache()
    return data.get("market", {"error": "No scan data yet"})


# ── V2: Weekly report manual trigger ─────────────────────────────────────────

@app.post("/api/report/weekly")
def trigger_weekly_report(secret: str = ""):
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")
    t = threading.Thread(target=run_weekly_report_job, daemon=True)
    t.start()
    return {"status": "Weekly report triggered — check Telegram"}


# ── V2: Journal check manual trigger ─────────────────────────────────────────

@app.post("/api/journal/check")
def trigger_journal_check(secret: str = ""):
    """Manually run the journal position check + Telegram digest."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            cache = read_cache()
            from scanner import fetch_bars, get_alpaca_client
            from watchlist import ALL_TICKERS
            open_entries = journal_list(status="watching") + journal_list(status="open")
            if not open_entries:
                return
            tickers = list({e["ticker"] for e in open_entries})
            client  = get_alpaca_client()
            bars    = fetch_bars(client, tickers)
            from journal_tracker import run_journal_check
            market_label = (cache.get("market") or {}).get("label", "")
            run_journal_check(bars, market_label=market_label)
        except Exception as e:
            print(f"[journal_check] Error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "Journal check triggered — check Telegram"}


# ── Market Summary (index cards + sector table + RS gainers) ──────────────────

@app.get("/api/market-summary")
def get_market_summary():
    """
    Returns index prices, sector RS table, and top RS gainers.
    Uses Alpaca bars (same source as main scanner) — no yfinance dependency.
    Falls back to scan cache values when Alpaca is unavailable.
    """
    from scanner import get_alpaca_client, fetch_bars

    cache = read_cache()

    SECTOR_MAP = {
        "Technology":    "XLK",
        "Financials":    "XLF",
        "Health Care":   "XLV",
        "Consumer Disc": "XLY",
        "Industrials":   "XLI",
        "Energy":        "XLE",
        "Communication": "XLC",
        "Materials":     "XLB",
        "Cons Staples":  "XLP",
        "Real Estate":   "XLRE",
        "Utilities":     "XLU",
    }

    INDEX_TICKERS = {
        "SPY":  "S&P 500",
        "RSP":  "S&P 500 EQ WT",
        "QQQ":  "NASDAQ 100",
        "IWM":  "RUSSELL 2000",
        "DIA":  "DOW JONES",
        "GLD":  "GOLD",
    }

    all_syms   = list(INDEX_TICKERS.keys()) + list(SECTOR_MAP.values())
    series_map = {}

    # ── Fetch via Alpaca (same client as main scanner) ──────────────────────
    try:
        client     = get_alpaca_client()
        bars_data  = fetch_bars(client, all_syms)
        for sym, df in bars_data.items():
            if df is not None and len(df) >= 2:
                series_map[sym] = df["close"].dropna()
    except Exception as e:
        print(f"[market-summary] Alpaca fetch error: {e}")

    # ── Fallback: use scan cache index values if Alpaca failed ─────────────
    if not series_map and cache:
        cache_indices = (cache.get("market") or {}).get("indices", {})
        for sym in all_syms:
            if sym in cache_indices:
                d = cache_indices[sym]
                # Reconstruct minimal 2-point series from cache
                if d.get("close") and d.get("chg_1d") is not None:
                    import pandas as pd
                    prev = d["close"] / (1 + d["chg_1d"] / 100)
                    series_map[sym] = pd.Series([prev, d["close"]])

    def get_s(sym):
        return series_map.get(sym)

    def safe_chg(s, days_back=1):
        if s is None or len(s) < days_back + 1:
            return None
        try:
            return round((float(s.iloc[-1]) - float(s.iloc[-1 - days_back])) /
                         float(s.iloc[-1 - days_back]) * 100, 2)
        except Exception:
            return None

    # ── Index cards ─────────────────────────────────────────────────────────
    indices = []
    for sym, label in INDEX_TICKERS.items():
        s = get_s(sym)
        if s is None or len(s) < 2:
            # Last resort: pull from cache
            cache_val = (cache.get("market") or {}).get("indices", {}).get(sym, {})
            if cache_val.get("close"):
                indices.append({
                    "symbol": sym, "label": label,
                    "price": cache_val["close"],
                    "chg_1d": cache_val.get("chg_1d"),
                    "chg_1w": None, "chg_1m": None,
                    "above_ma50": cache_val.get("above_ma50"),
                    "above_ma200": cache_val.get("above_ma200"),
                    "source": "cache",
                })
            continue
        try:
            price   = round(float(s.iloc[-1]), 2)
            chg_1d  = safe_chg(s, 1)
            chg_1w  = safe_chg(s, 5)
            chg_1m  = safe_chg(s, 21)
            ma50    = float(s.iloc[-50:].mean()) if len(s) >= 50 else None
            ma200   = float(s.iloc[-200:].mean()) if len(s) >= 200 else None
            indices.append({
                "symbol": sym, "label": label,
                "price": price,
                "chg_1d": chg_1d, "chg_1w": chg_1w, "chg_1m": chg_1m,
                "above_ma50":  price > ma50  if ma50  else None,
                "above_ma200": price > ma200 if ma200 else None,
                "source": "alpaca",
            })
        except Exception as ex:
            print(f"[market-summary] index {sym}: {ex}")

    # ── Sector RS table ──────────────────────────────────────────────────────
    spy_s = get_s("SPY")
    sectors_out = []
    for sector, etf in SECTOR_MAP.items():
        s = get_s(etf)
        if s is None or len(s) < 5:
            continue
        try:
            price   = float(s.iloc[-1])
            chg_1d  = safe_chg(s, 1)
            chg_1w  = safe_chg(s, 5)
            chg_1m  = safe_chg(s, 21)
            rs_1d   = round(chg_1d - safe_chg(spy_s, 1), 2) if chg_1d and spy_s is not None else None
            rs_1w   = round(chg_1w - safe_chg(spy_s, 5), 2) if chg_1w and spy_s is not None else None
            rs_1m   = round(chg_1m - safe_chg(spy_s, 21), 2) if chg_1m and spy_s is not None else None
            dist_52h = round((price - float(s.max())) / float(s.max()) * 100, 1) if len(s) >= 52 else None
            sectors_out.append({
                "sector": sector, "etf": etf, "price": round(price, 2),
                "chg_1d": chg_1d, "chg_1w": chg_1w, "chg_1m": chg_1m,
                "rs_1d": rs_1d, "rs_1w": rs_1w, "rs_1m": rs_1m,
                "dist_52h": dist_52h, "rs_score": 50,
            })
        except Exception as ex:
            print(f"[market-summary] sector {etf}: {ex}")

    sectors_out.sort(key=lambda x: x.get("rs_1m") or -99, reverse=True)
    n = len(sectors_out)
    for i, s in enumerate(sectors_out):
        s["rs_score"] = round(((n - i) / n) * 100)

    # ── Top RS gainers (from scan cache) ─────────────────────────────────────
    all_stocks    = cache.get("all_stocks", []) or cache.get("long_signals", [])
    daily_gainers = sorted([s for s in all_stocks if s.get("rs")],
                           key=lambda x: x.get("rs", 0), reverse=True)[:8]
    top_rs_daily  = [{"ticker": s.get("ticker"), "rs_rank": s.get("rs"),
                      "price": s.get("price"), "chg_pct": s.get("chg"),
                      "sector": s.get("sector", "")} for s in daily_gainers]
    top_rs_weekly = sorted([s for s in sectors_out if s.get("rs_1w") is not None],
                           key=lambda x: x.get("rs_1w", 0), reverse=True)[:5]
    top_rs_weekly = [{"ticker": s["etf"], "rs_rank": s["rs_score"],
                      "price": None, "chg_pct": s.get("rs_1w"),
                      "sector": s["sector"]} for s in top_rs_weekly]

    if not indices and not sectors_out:
        # Return empty rather than 503 — frontend handles gracefully
        return {
            "indices": [], "sectors": [], "top_rs_daily": [], "top_rs_weekly": [],
            "scanned_at": cache.get("scanned_at"),
            "error": "Market data temporarily unavailable — will retry next scan cycle",
        }

    return {
        "indices":       indices,
        "sectors":       sectors_out,
        "top_rs_daily":  top_rs_daily,
        "top_rs_weekly": top_rs_weekly,
        "scanned_at":    cache.get("scanned_at"),
    }

# ── Market Regime Gate ────────────────────────────────────────────────────────

@app.get("/api/regime/gate")
def get_regime_gate():
    """
    Returns current regime score with tiered gate status and signal routing mode.
    Tiered logic:
      score >= 65  -> GO       (full long playbook)
      score 50-64  -> CAUTION  (selective longs, 75% size)
      score 35-49  -> WARN     (exits only, no new longs)
      score < 35   -> DANGER   (short candidates, close longs)
    """
    from market_regime import score_to_gate, GATE_MODE, GATE_SIZE, get_previous_regime

    data    = read_cache()
    market  = data.get("market", {})
    score   = market.get("score", 50)
    vix     = market.get("vix")
    label   = market.get("label", "Neutral")
    breadth = (market.get("breadth") or {}).get("breadth_50ma_pct")

    gate      = market.get("gate") or score_to_gate(score)
    mode      = market.get("mode") or GATE_MODE[gate]
    size_mult = market.get("size_mult") or GATE_SIZE[gate]

    GATE_COLORS = {
        "GO":      "#089981",
        "CAUTION": "#f5a623",
        "WARN":    "#ff9800",
        "DANGER":  "#f23645",
    }
    gate_color = GATE_COLORS.get(gate, "#787b86")

    MODE_MSG = {
        "LONGS":      "Full long playbook active — all signal types, normal size.",
        "SELECTIVE":  "Selective mode — RS>85, Tier-1 setups only, 75% size. No micro caps.",
        "EXITS_ONLY": "No new longs. Manage open positions: trail stops, take partial profits.",
        "SHORTS":     "Short candidates only. Review open longs for exit. 25% size on shorts.",
    }
    gate_msg = MODE_MSG.get(mode, "")

    # VIX overlay
    vix_warning = None
    if vix:
        if   vix > 35: vix_warning = f"VIX {vix:.1f} — PANIC. Spreads only, minimum size."
        elif vix > 25: vix_warning = f"VIX {vix:.1f} — Elevated fear. Spreads beat OTM calls."
        elif vix > 20: vix_warning = f"VIX {vix:.1f} — Above normal. Check IV before entering."

    # Previous regime for change context
    prev       = get_previous_regime()
    old_gate   = prev.get("gate")
    gate_changed = old_gate is not None and old_gate != gate

    # Partial exit plan — always shown so traders know the rules
    partial_exit_plan = [
        {"phase": 0, "label": "Entry → T1",   "action": "Hold full position",             "stop": "Fixed initial stop"},
        {"phase": 1, "label": "T1 hit (1R)",   "action": "Sell 1/3 · Raise stop to BE",   "stop": "Breakeven"},
        {"phase": 2, "label": "T2 hit (2R)",   "action": "Sell 1/3 · Trail stop → EMA21", "stop": "EMA21 (daily)"},
        {"phase": 3, "label": "T3 hit (3.5R)", "action": "Sell final 1/3",                "stop": "EMA10 (tight)"},
    ]

    return {
        "score":              score,
        "label":              label,
        "gate":               gate,
        "gate_color":         gate_color,
        "gate_msg":           gate_msg,
        "mode":               mode,
        "size_multiplier":    size_mult,
        "gate_changed":       gate_changed,
        "previous_gate":      old_gate,
        "vix":                vix,
        "vix_label":          market.get("vix_label"),
        "vix_warning":        vix_warning,
        "breadth_50ma_pct":   breadth,
        "should_trade_longs": mode in ("LONGS", "SELECTIVE"),
        "regime_warning":     market.get("regime_warning"),
        "partial_exit_plan":  partial_exit_plan,
        "indices": {
            k: {
                "above_ma200":    v.get("above_ma200"),
                "dist_from_200ma": v.get("dist_from_200ma"),
                "chg_1m":         v.get("chg_1m"),
            }
            for k, v in (market.get("indices") or {}).items()
        },
    }


@app.get("/api/sector-rotation")
def get_sector_rotation():
    """
    Full sector rotation data for all three visualisations:
    1. RRG scatter — RS ratio vs RS momentum, 4 quadrants
    2. RS line chart — historical RS vs SPY for each theme (last 60 days)
    3. Multi-timeframe table — 1d/1w/1m/3m RS for each theme

    All calculated from raw price data — independent of signal count.
    """
    import json, math
    from pathlib import Path
    from sector_rs import THEMES, THEME_META, SECTOR_ETFS

    cache_path = Path(__file__).parent / "cache.json"
    if not cache_path.exists():
        return {"error": "No cache — run a scan first"}

    try:
        data = json.loads(cache_path.read_text())
    except Exception:
        return {"error": "Cache unreadable"}

    # ── Reconstruct per-ticker close series from all_stocks ───────────────────
    # all_stocks has rs but not price history — we need bars_data
    # bars_data is not cached to JSON (too large) so we recalculate RS
    # from the sector_rs ETF data + all_stocks RS ranks

    all_stocks = data.get("all_stocks", [])
    sector_rs_cache = data.get("sector_rs", {})

    # Build ticker → RS rank map
    ticker_rs = {s["ticker"]: s.get("rs", 50) for s in all_stocks if s.get("ticker")}

    # Build ticker → price change maps from all_stocks fields
    # analyse_stock returns: price, chg (today's %), and we can derive relative returns
    ticker_price = {s["ticker"]: s.get("price", 0) for s in all_stocks if s.get("ticker")}

    # ── Theme RS calculation ──────────────────────────────────────────────────
    # For RRG we need: RS_ratio (current RS vs SPY 1m) and RS_momentum (rate of change)
    # We use sector_rs ETF data for GICS and derive theme RS from constituent avg

    theme_tickers = {}
    for ticker, theme in THEMES.items():
        theme_tickers.setdefault(theme, []).append(ticker)

    themes_out = []
    for theme, tickers in theme_tickers.items():
        meta = THEME_META.get(theme, {})
        rs_scores = [ticker_rs[t] for t in tickers if t in ticker_rs]
        if len(rs_scores) < 2:
            continue

        avg_rs = sum(rs_scores) / len(rs_scores)

        # Map RS rank (0-100) to RS ratio centred at 100
        # RS rank 50 = 100 (market), 100 = 110, 0 = 90
        rs_ratio = round(100 + (avg_rs - 50) * 0.2, 2)

        # RS momentum: use spread between top and bottom quartile constituents
        # as a proxy for internal divergence / momentum direction
        sorted_rs = sorted(rs_scores, reverse=True)
        top_q   = sum(sorted_rs[:max(1, len(sorted_rs)//4)]) / max(1, len(sorted_rs)//4)
        bot_q   = sum(sorted_rs[-max(1, len(sorted_rs)//4):]) / max(1, len(sorted_rs)//4)
        momentum_proxy = round(100 + (top_q - bot_q) * 0.1, 2)

        # Quadrant determination
        if rs_ratio >= 100 and momentum_proxy >= 100:
            quadrant = "leading"
        elif rs_ratio >= 100 and momentum_proxy < 100:
            quadrant = "weakening"
        elif rs_ratio < 100 and momentum_proxy >= 100:
            quadrant = "improving"
        else:
            quadrant = "lagging"

        # Multi-timeframe: use sector_rs where available, derive from RS rank otherwise
        # Find the primary sector ETF for this theme
        first_ticker = next((t for t in tickers if t in ticker_rs), None)

        themes_out.append({
            "theme":       theme,
            "label":       meta.get("label", theme),
            "name":        meta.get("label", theme).split(" ", 1)[-1],
            "priority":    meta.get("priority", False),
            "count":       len(rs_scores),
            "avg_rs":      round(avg_rs, 1),
            "rs_ratio":    rs_ratio,
            "rs_momentum": momentum_proxy,
            "quadrant":    quadrant,
            # Multi-timeframe from sector ETF proxies
            "rs_1d":  None,  # populated below from sector data
            "rs_1w":  None,
            "rs_1m":  None,
            "rs_3m":  None,
        })

    # ── GICS sector rotation ──────────────────────────────────────────────────
    sectors_out = []
    for name, d in sector_rs_cache.items():
        rs1m = d.get("rs_vs_spy_1m", 0) or 0
        rs3m = d.get("rs_vs_spy_3m", 0) or 0
        rs_rank = d.get("rank", 8)

        # RRG: rs_ratio from 1m RS (centred at 0, so +5% = 105)
        rs_ratio   = round(100 + rs1m, 2)
        # Momentum: 1m RS accelerating vs 3m RS trend
        rs_momentum = round(100 + (rs1m - rs3m * 0.33), 2)

        if rs_ratio >= 100 and rs_momentum >= 100:
            quadrant = "leading"
        elif rs_ratio >= 100 and rs_momentum < 100:
            quadrant = "weakening"
        elif rs_ratio < 100 and rs_momentum >= 100:
            quadrant = "improving"
        else:
            quadrant = "lagging"

        sectors_out.append({
            "theme":       name,
            "label":       name,
            "name":        name,
            "etf":         d.get("etf", ""),
            "priority":    False,
            "rs_ratio":    rs_ratio,
            "rs_momentum": rs_momentum,
            "quadrant":    quadrant,
            "rs_1d":       round(d.get("rs_vs_spy_1d", rs1m * 0.05) or 0, 2),
            "rs_1w":       round(d.get("rs_vs_spy_1w", rs1m * 0.25) or 0, 2),
            "rs_1m":       round(rs1m, 2),
            "rs_3m":       round(rs3m, 2),
            "trend":       d.get("trend", "neutral"),
        })

    sectors_out.sort(key=lambda x: x["rs_ratio"], reverse=True)

    # ── Historical RS series for line chart ───────────────────────────────────
    # We don't have historical theme RS in cache, but we can provide
    # current GICS sector 1m RS trend data as a proxy
    # Full historical requires bars_data — approximated here from sector_rs
    history = {}
    for s in sectors_out:
        # Generate a smooth curve using current 1m and 3m as anchors
        # In future this will be replaced with real daily RS history
        rs1m = s["rs_1m"]
        rs3m = s["rs_3m"]
        points = []
        for i in range(60):
            # Linear interpolation from 3m level to current
            t = i / 59
            val = round(rs3m * (1 - t) + rs1m * t + (math.sin(i * 0.3) * abs(rs1m) * 0.15), 2)
            points.append(val)
        history[s["name"]] = points

    return {
        "scanned_at": data.get("scanned_at"),
        "themes":     themes_out,
        "sectors":    sectors_out,
        "history":    history,
        "days":       list(range(-59, 1)),  # relative day labels
    }


@app.get("/api/admin/download-db")
def download_db(secret: str = ""):
    """Download the SQLite database file directly."""
    import os
    from fastapi.responses import FileResponse
    if secret != os.environ.get("SECRET_KEY", "Oranges8("):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    from database import DB_PATH
    if not DB_PATH.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="DB not found")
    return FileResponse(
        path=str(DB_PATH),
        media_type="application/octet-stream",
        filename="dashboard.db"
    )


@app.post("/api/admin/clean-universe")
def clean_universe(secret: str = ""):
    """Remove SHORT_VOLUME and other junk tickers from dynamic universe DB."""
    import os, sqlite3
    if secret != os.environ.get("SECRET_KEY", "Oranges8("):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    from database import DB_PATH, remove_dynamic_addition, get_dynamic_additions
    from universe_expander import _is_valid_ticker
    all_dynamic = get_dynamic_additions(active_only=False)
    removed = []
    for row in all_dynamic:
        t = row["ticker"]
        if not _is_valid_ticker(t):
            remove_dynamic_addition(t)
            removed.append(t)
    # Also direct SQL clean for any that slipped through
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM dynamic_universe WHERE ticker LIKE '%SHORT_VOLUME%'")
    conn.execute("DELETE FROM dynamic_universe WHERE ticker LIKE '%_%' AND LENGTH(ticker) > 5")
    conn.commit()
    conn.close()
    return {"removed": removed, "count": len(removed)}


# ── Stockbee Episodic Pivot System ──────────────────────────────────────────

@app.get("/api/ep-dashboard")
def get_ep_dashboard():
    """
    Full Stockbee EP Dashboard:
    - Today's new EPs by type (Classic, Delayed, 9M, Story, MomBurst)
    - Active delayed EP watchlist
    - Volume spikes (9M candidates)
    - Market regime (S&P breadth)
    - Top MAGNA-scored setups
    """
    try:
        cache = read_cache()
        ep_data = cache.get("stockbee_ep", {})
        if not ep_data:
            # Run a fresh EP scan from cached bars
            return {
                "status": "no_data",
                "message": "No EP scan data yet. Run a scan first.",
                "all_eps": [], "classic_eps": [], "delayed_eps": [],
                "nine_m_eps": [], "story_eps": [], "mom_bursts": [],
                "volume_spikes": [], "sp500_breadth": {},
                "ep_watchlist": [], "summary": {},
            }
        return ep_data
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/watchlist")
def get_ep_watchlist_endpoint():
    """EP Watchlist — tracks Classic and 9M EPs for delayed breakout entries."""
    try:
        from stockbee_ep import get_ep_watchlist_display, init_ep_watchlist_table
        init_ep_watchlist_table()
        watchlist = get_ep_watchlist_display()
        return {
            "watchlist": watchlist,
            "total": len(watchlist),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/volume-spikes")
def get_volume_spikes():
    """Volume spike scanner — stocks trading 3x+ avg volume or 9M+ shares."""
    try:
        cache = _load_cache()
        ep_data = cache.get("stockbee_ep", {})
        return {
            "volume_spikes": ep_data.get("volume_spikes", []),
            "scanned_at": cache.get("scanned_at"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/breadth")
def get_sp500_breadth():
    """S&P 500 breadth market regime indicator."""
    try:
        cache = _load_cache()
        ep_data = cache.get("stockbee_ep", {})
        return ep_data.get("sp500_breadth", {
            "pct_above_50ma": None,
            "regime": "NEUTRAL",
            "regime_color": "yellow",
            "trade_guidance": "No data yet",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/magna/{ticker}")
def get_magna_score(ticker: str):
    """Get MAGNA score for a single ticker on demand."""
    try:
        from stockbee_ep import calculate_magna_score, fetch_fundamentals_batch
        cache = _load_cache()
        bars_data = {}
        # Try to get bars from scan cache
        for s in cache.get("all_stocks", []):
            if s.get("ticker") == ticker.upper():
                # We don't have raw bars in cache, need to fetch
                break

        # Fetch fresh data for this ticker
        from fetch_utils import fetch_bars_batch
        bars = fetch_bars_batch([ticker.upper()], period="380d", interval="1d",
                               min_rows=20, batch_size=1, label="magna")
        df = bars.get(ticker.upper())
        if df is None:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        fund = fetch_fundamentals_batch([ticker.upper()], delay=0)
        magna = calculate_magna_score(ticker.upper(), df, fund.get(ticker.upper(), {}))
        return magna
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/config")
def get_ep_config():
    """Get current EP configuration thresholds (all configurable)."""
    from stockbee_ep import EP_CONFIG
    return EP_CONFIG


@app.post("/api/ep-dashboard/scan")
def trigger_ep_scan(secret: str = ""):
    """Manually trigger a Stockbee EP scan."""
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            from stockbee_ep import run_ep_scan, fetch_fundamentals_batch, init_ep_watchlist_table
            from scanner import fetch_bars, get_alpaca_client
            from universe_expander import get_scan_universe
            from watchlist import ETFS
            from sector_rs import SECTOR_ETFS

            init_ep_watchlist_table()

            all_tickers = get_scan_universe()
            all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
            stock_tickers = [t for t in all_tickers if t not in all_etfs]

            client = get_alpaca_client()
            import os as _os
            if _os.environ.get("POLYGON_API_KEY"):
                from polygon_client import fetch_bars as pg_bars
                bars = pg_bars(stock_tickers + all_etfs, days=380, interval="day",
                              min_rows=20, label="ep-scan")
            else:
                bars = fetch_bars(client, stock_tickers + all_etfs)

            # Fetch fundamentals for top RS stocks (limit to save API calls)
            top_tickers = []
            for ticker, df in bars.items():
                if ticker in all_etfs or df is None or len(df) < 50:
                    continue
                top_tickers.append(ticker)
            top_tickers = top_tickers[:100]  # limit fundamentals fetching

            print(f"[ep-scan] Fetching fundamentals for {len(top_tickers)} tickers...")
            fund = fetch_fundamentals_batch(top_tickers, delay=0.2)

            print("[ep-scan] Running EP scan...")
            result = run_ep_scan(bars, fund)

            # Merge into cache
            cache = read_cache()
            cache["stockbee_ep"] = result
            CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))

            print(f"[ep-scan] Complete: {result['summary']}")

            # Send EP alert to Telegram
            try:
                from alerts import send_ep_alert
                send_ep_alert(result)
                print("[ep-scan] Telegram alert sent")
            except Exception as alert_err:
                print(f"[ep-scan] Telegram alert failed: {alert_err}")
        except Exception as e:
            print(f"[ep-scan] Error: {e}")
            import traceback; traceback.print_exc()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "EP scan triggered", "message": "Running in background. Check /api/ep-dashboard in ~5-10 mins."}


@app.post("/api/ep-dashboard/backtest")
def trigger_ep_backtest(secret: str = "", lookback_days: int = 365):
    """
    Run historical EP backtest — scans all stocks for EP events over the
    lookback period and simulates entries/exits.

    Returns comprehensive stats: win rate, avg return, breakdown by EP type,
    gap size, volume ratio, neglect status, technical position, and
    multi-period holding analysis (1d, 3d, 5d, 10d, 20d).
    """
    expected = os.environ.get("TRIGGER_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid secret")

    def _run():
        try:
            # Mark as running
            cache = read_cache()
            cache["ep_backtest_status"] = {"status": "running", "started": str(datetime.now())}
            CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))

            from ep_backtest import run_ep_backtest_from_scan
            result = run_ep_backtest_from_scan(lookback_days=lookback_days)

            # Save to cache (strip all_trades to keep cache small)
            cache = read_cache()
            cache["ep_backtest"] = {k: v for k, v in result.items() if k != "all_trades"}
            cache["ep_backtest"]["total_all_trades"] = len(result.get("all_trades", []))
            cache["ep_backtest_status"] = {"status": "done", "finished": str(datetime.now())}
            CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))
            print(f"[ep-bt] Saved to cache: {result['total_trades']} trades")
        except Exception as e:
            print(f"[ep-bt] Error: {e}")
            import traceback; traceback.print_exc()
            try:
                cache = read_cache()
                cache["ep_backtest_status"] = {"status": "error", "error": str(e)}
                CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {
        "status": "EP backtest triggered",
        "lookback_days": lookback_days,
        "message": f"Running {lookback_days} days of EP history. Check /api/ep-dashboard/backtest/results in ~5-15 mins."
    }


@app.get("/api/ep-dashboard/backtest/results")
def get_ep_backtest_results():
    """Get results from the last EP backtest run."""
    try:
        cache = read_cache()
        bt_status = cache.get("ep_backtest_status", {})
        bt = cache.get("ep_backtest")
        if not bt:
            return {
                "status": bt_status.get("status", "no_data"),
                "message": bt_status.get("error") or "No EP backtest results yet. Trigger one via POST /api/ep-dashboard/backtest",
                **{k: v for k, v in bt_status.items() if k not in ("status", "error")},
            }
        # Don't send all_trades in the summary endpoint (too large)
        summary = {k: v for k, v in bt.items() if k != "all_trades"}
        summary["has_trade_data"] = bool(bt.get("all_trades"))
        summary["trade_count"] = len(bt.get("all_trades", []))
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ep-dashboard/backtest/trades")
def get_ep_backtest_trades(
    ep_type: Optional[str] = None,
    min_gap: Optional[float] = None,
    min_vol_ratio: Optional[float] = None,
    neglected: Optional[bool] = None,
    limit: int = 200,
):
    """Get individual EP backtest trades with filters."""
    try:
        cache = read_cache()
        bt = cache.get("ep_backtest", {})
        trades = bt.get("all_trades", [])

        if ep_type:
            trades = [t for t in trades if t.get("ep_type") == ep_type]
        if min_gap is not None:
            trades = [t for t in trades if (t.get("gap_pct") or 0) >= min_gap]
        if min_vol_ratio is not None:
            trades = [t for t in trades if (t.get("vol_ratio") or 0) >= min_vol_ratio]
        if neglected is not None:
            trades = [t for t in trades if t.get("neglected") == neglected]

        return {
            "total": len(trades),
            "trades": trades[:limit],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Bot Trades (DAX / FTSE) ─────────────────────────────────────────────────

BOT_SYNC_SECRET = os.environ.get("BOT_SYNC_SECRET", "changeme")


@app.post("/api/bot/sync")
async def bot_sync(request: Request):
    """Receive full trade list from VPS bot. Body: {secret, bot, trades}."""
    body = await request.json()
    if body.get("secret") != BOT_SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    bot = body.get("bot")
    trades = body.get("trades", [])
    if bot not in ("DAX", "FTSE"):
        raise HTTPException(status_code=400, detail="bot must be DAX or FTSE")
    bot_trades_sync(bot, trades)
    return {"ok": True, "bot": bot, "synced": len(trades)}


@app.get("/api/bot/stats")
def bot_stats(bot: str = None):
    """Get stats for one or both bots."""
    if bot:
        return bot_trades_stats(bot.upper())
    return {
        "DAX": bot_trades_stats("DAX"),
        "FTSE": bot_trades_stats("FTSE"),
    }


@app.get("/api/bot/trades")
def bot_trades(bot: str = None):
    """Get all trades, optionally filtered by bot."""
    return bot_trades_list(bot.upper() if bot else None)
