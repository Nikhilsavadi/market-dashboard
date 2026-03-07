"""
universe_expander.py
--------------------
Weekly job (Sun 08:30 UK) that auto-discovers breakout candidates OUTSIDE
the static 1193-ticker universe and adds qualifying ones to the DB.

Discovery sources (in order):
  1. Polygon top-gainers snapshot  — stocks moving strongly TODAY
  2. Polygon top-losers snapshot   — beaten down names starting to recover
  3. Static candidate pool         — hand-picked sectors we want to watch
     (kept as a safety net for weeks Polygon has no new names)

Quality gates (ALL must pass):
  - Price >= $5
  - 20-day avg volume >= 200k
  - Price above 50-day MA
  - RS vs SPY (60-day) in top 40th percentile of THIS candidate set
  - Volume trend: recent 20d >= prior 20d (not falling off)

Lifecycle:
  - Added tickers survive in DB across deploys
  - Re-checked weekly — last_confirmed timestamp updated if still passing
  - Auto-expired after 90 days with no re-confirmation
  - Telegram alert on Sun morning: N added, N expired

Scanner integration:
  - scanner.py calls get_scan_universe() → static + dynamic combined
  - reload_dynamic_tickers() called at app startup to merge into memory
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Optional


# ── Config ─────────────────────────────────────────────────────────────────────
MIN_PRICE         = 5.0
MIN_AVG_VOL       = 200_000     # 20-day avg
MIN_BARS          = 55          # need ~60 days history for RS
ABOVE_MA50        = True
RS_PERCENTILE_MIN = 40          # top 40% of THIS candidate pool
VOL_TREND_MIN     = -10         # allow slight vol decline (-10%)
MAX_ADD_PER_RUN   = 40          # cap new additions per week
EXPIRY_DAYS       = 90          # days before stale ticker auto-removed

# Skip leveraged/inverse ETFs and warrants
SKIP_SUFFIXES = {"W", "R", "P"}   # warrants, rights, preferred
SKIP_EXACT = {
    "SOXL","SOXS","TQQQ","SQQQ","UVXY","SVXY","SPXL","SPXS","UPRO","SPXU",
    "LABU","LABD","NUGT","DUST","JNUG","JDST","FNGU","FNGD","NAIL","HIBL",
    "TNA","TZA","UDOW","SDOW","URTY","SRTY","EDC","EDZ",
}

# Static candidate pool — sectors we always want to monitor but aren't in
# our main watchlist. These are checked every week as a baseline.
STATIC_CANDIDATES = [
    # Optical networking / photonics
    "AAOI", "MTSI", "INFN", "IIVI", "NPKI",
    # Aviation / leasing
    "FTAI", "AL", "AER",
    # Power infrastructure
    "SOLS", "ARRY", "SHLS", "NOVA", "GEV",
    # Drone / defence tech
    "UMAC", "KTOS", "AVAV",
    # Fintech / crypto adjacent
    "CRCL", "NU", "GRAB",
    # Semi equipment not in main list
    "ONTO", "IPGP", "MTSI", "POWI",
    # Recent IPOs / high-growth
    "RDDT", "BIRK", "HIMS",
    # S&P 400 mid-caps we often miss
    "PNFP", "HOMB", "RXO", "MGNI", "IIPR",
    # Misc high-RS names spotted in market
    "NOK", "FTAI", "VICR", "FSLY", "UAMY",
]
STATIC_CANDIDATES = list(dict.fromkeys(STATIC_CANDIDATES))  # dedupe


# ── Polygon live discovery ─────────────────────────────────────────────────────

def _polygon_get(endpoint: str, params: dict = None) -> Optional[dict]:
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        return None
    try:
        r = requests.get(
            f"https://api.polygon.io{endpoint}",
            params={"apiKey": api_key, **(params or {})},
            timeout=15,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _fetch_live_candidates() -> list[dict]:
    """
    Pull Polygon gainers + losers snapshots.
    Returns list of {ticker, source, price, volume, change_pct}.
    """
    candidates = []

    for endpoint, source in [
        ("/v2/snapshot/locale/us/markets/stocks/gainers", "gainer"),
        ("/v2/snapshot/locale/us/markets/stocks/losers",  "loser_bounce"),
    ]:
        data = _polygon_get(endpoint, {"include_otc": False})
        if not data or "tickers" not in data:
            print(f"[expander] Polygon {source} fetch failed/empty")
            continue
        for t in data["tickers"]:
            sym = t.get("ticker", "").upper().strip()
            day = t.get("day", {})
            candidates.append({
                "ticker":     sym,
                "source":     source,
                "price":      day.get("c", 0),
                "volume":     day.get("v", 0),
                "change_pct": t.get("todaysChangePerc", 0),
            })
        print(f"[expander] Polygon {source}: {len(data['tickers'])} tickers")

    return candidates


def _is_valid_symbol(sym: str) -> bool:
    """Filter out ETFs, warrants, long symbols etc."""
    if not sym or len(sym) > 5:
        return False
    if sym in SKIP_EXACT:
        return False
    if not sym.replace("-", "").isalpha():
        return False
    if sym[-1] in SKIP_SUFFIXES and len(sym) >= 4:
        return False
    return True


# ── Scoring ────────────────────────────────────────────────────────────────────

def _score_candidate(ticker: str, df: pd.DataFrame,
                     spy_closes: pd.Series) -> Optional[dict]:
    """
    Apply hard gates. Returns scored dict or None if fails any gate.
    Does NOT apply RS percentile gate here (needs full pool first).
    """
    try:
        if df is None or len(df) < MIN_BARS:
            return None

        closes  = df["close"]
        volumes = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)
        price   = float(closes.iloc[-1])

        if price < MIN_PRICE:
            return None

        avg_vol_20 = float(volumes.tail(20).mean()) if len(volumes) >= 20 else 0
        if avg_vol_20 < MIN_AVG_VOL:
            return None

        # Above 50-day MA
        if ABOVE_MA50 and len(closes) >= 50:
            if price < float(closes.tail(50).mean()):
                return None

        # Volume trend
        if len(volumes) >= 40:
            vol_trend = (
                (float(volumes.tail(20).mean()) - float(volumes.iloc[-40:-20].mean()))
                / float(volumes.iloc[-40:-20].mean()) * 100
            )
        else:
            vol_trend = 0.0

        if vol_trend < VOL_TREND_MIN:
            return None

        # RS score (weighted vs SPY — matches live scanner exactly)
        from screener import _calculate_weighted_rs_score
        rs_raw = _calculate_weighted_rs_score(closes, spy_closes)
        if rs_raw is None:
            return None

        # 1-month momentum
        mom_1m = round((price / float(closes.iloc[-21]) - 1) * 100, 1) \
                 if len(closes) >= 21 and float(closes.iloc[-21]) > 0 else 0.0

        return {
            "ticker":    ticker,
            "price":     round(price, 2),
            "avg_vol":   int(avg_vol_20),
            "rs_raw":    round(rs_raw, 4),
            "vol_trend": round(vol_trend, 1),
            "mom_1m":    mom_1m,
        }
    except Exception as e:
        print(f"[expander] Score error {ticker}: {e}")
        return None


# ── Main expansion runner ──────────────────────────────────────────────────────

def run_universe_expansion() -> dict:
    """
    Main entry point — called by weekly scheduler (Sun 08:30 UK).
    1. Gather live candidates from Polygon + static pool
    2. Fetch bars, score, percentile-rank
    3. Save qualifiers to DB
    4. Re-confirm existing dynamic tickers
    5. Expire stale ones
    6. Send Telegram summary
    """
    t0 = time.time()
    print(f"\n[expander] === Universe expansion {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    from fetch_utils import fetch_bars_batch
    from watchlist import ALL_TICKERS
    from database import get_dynamic_additions, save_dynamic_addition, remove_dynamic_addition

    static_set    = set(ALL_TICKERS)
    existing_dyn  = {r["ticker"] for r in get_dynamic_additions(active_only=True)}
    already_known = static_set | existing_dyn

    # ── 1. Build candidate list ───────────────────────────────────────────────
    live = _fetch_live_candidates()

    # Combine live + static, filter known + invalid
    all_candidates = []
    seen = set()
    for c in live:
        sym = c["ticker"]
        if sym in seen or sym in already_known or not _is_valid_symbol(sym):
            continue
        seen.add(sym)
        all_candidates.append(c)

    # Add static candidates not yet in universe
    for sym in STATIC_CANDIDATES:
        if sym not in seen and sym not in already_known and _is_valid_symbol(sym):
            all_candidates.append({"ticker": sym, "source": "static_pool",
                                    "price": 0, "volume": 0, "change_pct": 0})
            seen.add(sym)

    print(f"[expander] {len(all_candidates)} candidates to evaluate "
          f"({len(live)} live, {len(STATIC_CANDIDATES)} static pool)")

    if not all_candidates:
        print("[expander] No new candidates this week")
        _reconfirm_existing(existing_dyn, already_known)
        return {"added": 0, "removed": 0, "checked": 0}

    # ── 2. Fetch bars ─────────────────────────────────────────────────────────
    tickers_to_fetch = [c["ticker"] for c in all_candidates] + ["SPY"]
    bars = fetch_bars_batch(
        tickers_to_fetch,
        period    = "380d",
        interval  = "1d",
        min_rows  = MIN_BARS,
        label     = "expander",
    )

    if "SPY" not in bars:
        print("[expander] SPY fetch failed — cannot compute RS, aborting")
        return {"added": 0, "removed": 0, "checked": 0, "error": "SPY missing"}

    spy_closes = bars.pop("SPY")["close"]
    print(f"[expander] Fetched {len(bars)}/{len(all_candidates)} candidates")

    # ── 3. Score all candidates ───────────────────────────────────────────────
    scored = []
    for c in all_candidates:
        ticker = c["ticker"]
        df = bars.get(ticker)
        result = _score_candidate(ticker, df, spy_closes)
        if result:
            result["source"]     = c["source"]
            result["change_pct"] = c.get("change_pct", 0)
            scored.append(result)

    print(f"[expander] {len(scored)}/{len(bars)} passed price/vol/MA/trend gates")

    if not scored:
        print("[expander] No candidates passed gates")
        _reconfirm_existing(existing_dyn, already_known)
        return {"added": 0, "removed": 0, "checked": len(bars)}

    # ── 4. Percentile rank by RS within this pool ─────────────────────────────
    scored.sort(key=lambda x: x["rs_raw"], reverse=True)
    n = len(scored)
    added = []

    for i, s in enumerate(scored):
        rs_pct = int((n - i) / n * 100)   # rank 1 = 100th percentile
        if rs_pct < RS_PERCENTILE_MIN:
            continue

        reason = (f"AutoAdd | src={s['source']} RS={rs_pct} "
                  f"vol_trend={s['vol_trend']:+.0f}% mom={s['mom_1m']:+.1f}%")

        save_dynamic_addition(
            ticker    = s["ticker"],
            price     = s["price"],
            avg_vol   = s["avg_vol"],
            rs_score  = rs_pct,
            vol_trend = s["vol_trend"],
            mom_1m    = s["mom_1m"],
            reason    = reason,
        )
        added.append(s["ticker"])
        print(f"[expander]   + {s['ticker']:<8} ${s['price']:.2f} "
              f"RS={rs_pct} vol_trend={s['vol_trend']:+.0f}% "
              f"src={s['source']}")

        if len(added) >= MAX_ADD_PER_RUN:
            break

    # ── 5. Re-confirm existing dynamic tickers ────────────────────────────────
    removed = _reconfirm_existing(existing_dyn, already_known)

    # ── 6. Reload memory + Telegram alert ────────────────────────────────────
    if added:
        reload_dynamic_tickers()

    elapsed = round(time.time() - t0, 1)
    total   = len(get_dynamic_additions(active_only=True))
    print(f"[expander] === Complete in {elapsed}s — "
          f"added={len(added)} removed={len(removed)} total_dynamic={total} ===")

    _send_alert(added, removed, total)

    return {
        "added":   len(added),
        "removed": len(removed),
        "checked": len(all_candidates),
        "new_tickers": added,
        "expired": removed,
        "total_dynamic": total,
    }


def _reconfirm_existing(existing_dyn: set, already_known: set) -> list:
    """
    Re-fetch and re-score current dynamic tickers.
    Updates last_confirmed if still passing, soft-deletes if stale.
    Returns list of expired tickers.
    """
    if not existing_dyn:
        return []

    from fetch_utils import fetch_bars_batch
    from database import get_dynamic_additions, save_dynamic_addition, remove_dynamic_addition

    print(f"[expander] Re-confirming {len(existing_dyn)} existing dynamic tickers...")
    bars = fetch_bars_batch(list(existing_dyn) + ["SPY"], period="80d",
                            interval="1d", label="expander_recheck")

    spy_closes = bars.pop("SPY", {})
    if spy_closes is not None and "close" in spy_closes:
        spy_closes = spy_closes["close"]
    else:
        spy_closes = pd.Series(dtype=float)

    removed = []
    for ticker in existing_dyn:
        df = bars.get(ticker)
        result = _score_candidate(ticker, df, spy_closes)
        if result:
            # Still passing — update last_confirmed via upsert
            save_dynamic_addition(
                ticker    = ticker,
                price     = result["price"],
                avg_vol   = result["avg_vol"],
                rs_score  = result["rs_raw"],
                vol_trend = result["vol_trend"],
                mom_1m    = result["mom_1m"],
                reason    = "weekly_recheck",
            )
        else:
            # Failed re-check — mark inactive (will expire in 90 days)
            # For now we just log; hard removal only via expire_stale_dynamic()
            print(f"[expander]   RECHECK FAIL {ticker} — no longer passing gates")

    # Expire truly stale entries (not confirmed in 90 days)
    removed = _expire_stale()
    return removed


def _expire_stale() -> list:
    """Remove dynamic tickers not re-confirmed in EXPIRY_DAYS."""
    from database import get_conn
    try:
        with get_conn() as conn:
            rows = conn.execute(
                f"""SELECT ticker FROM universe_additions
                    WHERE active = 1
                    AND added_date < date('now', '-{EXPIRY_DAYS} days')
                    AND ticker NOT IN (
                        SELECT ticker FROM universe_additions
                        WHERE reason = 'weekly_recheck'
                        AND added_date >= date('now', '-{EXPIRY_DAYS} days')
                    )"""
            ).fetchall()
            expired = [r[0] for r in rows]
            if expired:
                conn.execute(
                    f"UPDATE universe_additions SET active=0, removed_date=date('now') "
                    f"WHERE ticker IN ({','.join('?'*len(expired))})",
                    expired
                )
        return expired
    except Exception as e:
        print(f"[expander] expire_stale error: {e}")
        return []


def _send_alert(added: list, removed: list, total: int):
    try:
        if not added and not removed:
            return
        from alerts import send_telegram
        lines = ["🔍 *Universe Expansion*"]
        if added:
            lines.append(f"✅ Added ({len(added)}): {', '.join(added[:20])}")
        if removed:
            lines.append(f"⏏️ Expired ({len(removed)}): {', '.join(removed[:10])}")
        lines.append(f"📊 Dynamic total: {total} tickers")
        send_telegram("\n".join(lines))
    except Exception as e:
        print(f"[expander] Alert failed: {e}")


# ── Scanner integration ────────────────────────────────────────────────────────

def _is_valid_ticker(t: str) -> bool:
    """
    Filter out non-stock symbols that Polygon/yfinance sometimes returns.
    - SHORT_VOLUME suffixes (FINRA short sale data)
    - Warrants, rights, units (common suffixes)
    - Tickers longer than 5 chars with underscores (usually data indices)
    - Permanently excluded tickers (consistently fail or return bad data)
    """
    if not t or not isinstance(t, str):
        return False
    t = t.strip().upper()

    # Permanently excluded — consistently fail API calls or return corrupt data
    _PERMANENT_EXCLUDE = {
        "SNDK", "DPSI", "EIDX", "EPZM", "FMTX", "FWBI", "LBPH", "MORF",
        "ORPH", "PNTM",
    }
    if t in _PERMANENT_EXCLUDE:
        return False

    # FINRA short sale volume symbols
    if "_SHORT_VOLUME" in t or t.endswith("_SV"):
        return False
    # Other underscore-suffixed data symbols
    if "_" in t and len(t) > 5:
        return False
    # Too long to be a real stock ticker
    if len(t) > 6:
        return False
    return True


def get_scan_universe() -> list[str]:
    """
    Returns full scan universe: static ALL_TICKERS + active dynamic additions.
    Called by scanner.py so every scan automatically includes new tickers.
    """
    from watchlist import ALL_TICKERS
    try:
        from database import get_dynamic_additions
        dynamic = [r["ticker"] for r in get_dynamic_additions(active_only=True)]
        if not dynamic:
            return [t for t in ALL_TICKERS if _is_valid_ticker(t)]
        static_set = set(ALL_TICKERS)
        new_ones   = [t for t in dynamic if t not in static_set and _is_valid_ticker(t)]
        combined   = [t for t in ALL_TICKERS if _is_valid_ticker(t)] + new_ones
        if new_ones:
            print(f"[expander] Universe: {len(ALL_TICKERS)} static + "
                  f"{len(new_ones)} dynamic = {len(combined)}")
        return combined
    except Exception as e:
        print(f"[expander] get_scan_universe fallback: {e}")
        from watchlist import ALL_TICKERS
        return [t for t in ALL_TICKERS if _is_valid_ticker(t)]


def reload_dynamic_tickers() -> int:
    """
    Merge active DB additions into watchlist.ALL_TICKERS in memory.
    Called at app startup and after each expansion run.
    """
    try:
        from database import get_dynamic_additions
        import watchlist as wl
        additions = [r["ticker"] for r in get_dynamic_additions(active_only=True)]
        added = 0
        for t in additions:
            if t not in wl.ALL_TICKERS:
                wl.ALL_TICKERS.append(t)
                wl.TICKER_TIER[t] = 2
                added += 1
        if added:
            print(f"[expander] Merged {added} dynamic tickers -> "
                  f"universe now {len(wl.ALL_TICKERS)}")
        return added
    except Exception as e:
        print(f"[expander] reload_dynamic_tickers failed: {e}")
        return 0


# ── Manual add ─────────────────────────────────────────────────────────────────

def manually_add_ticker(ticker: str, notes: str = "manual") -> dict:
    """
    Manually add a single ticker via the API endpoint.
    Fetches bars, applies gates (relaxed — no RS percentile gate),
    saves if passes price/vol/MA.
    """
    from fetch_utils import fetch_bars_batch
    from database import save_dynamic_addition

    ticker = ticker.upper().strip()
    bars = fetch_bars_batch([ticker, "SPY"], period="80d", interval="1d",
                             label="manual_add")
    df = bars.get(ticker)
    spy_c = bars.get("SPY")
    spy_closes = spy_c["close"] if spy_c is not None and "close" in spy_c \
                 else pd.Series(dtype=float)

    result = _score_candidate(ticker, df, spy_closes)
    if not result:
        return {"success": False, "reason": "failed_gates"}

    save_dynamic_addition(
        ticker    = ticker,
        price     = result["price"],
        avg_vol   = result["avg_vol"],
        rs_score  = result["rs_raw"],
        vol_trend = result["vol_trend"],
        mom_1m    = result["mom_1m"],
        reason    = f"manual | {notes}",
    )
    reload_dynamic_tickers()
    return {"success": True, "ticker": ticker, "price": result["price"],
            "rs_raw": result["rs_raw"], "avg_vol": result["avg_vol"]}


if __name__ == "__main__":
    result = run_universe_expansion()
    print(result)
