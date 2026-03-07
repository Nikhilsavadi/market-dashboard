"""
database.py
-----------
SQLite database layer. Single file, no external dependencies.
Stores: journal entries, signal history, backtest results.
Railway persists the file as long as the volume is mounted.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

import os

# Use Railway persistent volume if available, otherwise fall back to app dir
_volume_path = Path("/app/data")
if _volume_path.exists() and os.access(_volume_path, os.W_OK):
    DB_PATH = _volume_path / "dashboard.db"
else:
    DB_PATH = Path(__file__).parent / "dashboard.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads
    return conn


def init_db():
    """Create all tables if they don't exist. Safe to call multiple times."""
    # ── Volume migration: copy existing DB to persistent volume if needed ──
    _old_path = Path(__file__).parent / "dashboard.db"
    if DB_PATH != _old_path and not DB_PATH.exists() and _old_path.exists():
        import shutil
        print(f"[db] Migrating DB from {_old_path} -> {DB_PATH}")
        shutil.copy2(_old_path, DB_PATH)
        print(f"[db] Migration complete — {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    # ─────────────────────────────────────────────────────────────────────
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS journal (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT NOT NULL,
                added_date   TEXT NOT NULL,
                signal_type  TEXT,
                entry_price  REAL,
                ma10         REAL,
                ma21         REAL,
                ma50         REAL,
                vcs          REAL,
                rs           INTEGER,
                vol_ratio    REAL,
                atr          REAL,
                stop_price   REAL,
                target_1     REAL,
                target_2     REAL,
                target_3     REAL,
                notes        TEXT,
                status       TEXT DEFAULT 'watching',
                exit_price   REAL,
                exit_date    TEXT,
                exit_reason  TEXT,
                pnl_pct      REAL,
                pnl_gbp      REAL,       -- actual £ profit/loss
                position_size_gbp REAL,  -- £ position size at entry
                signal_score REAL,
                tier         INTEGER DEFAULT 2,
                sector       TEXT,
                theme        TEXT,
                flag_detected    INTEGER,
                flag_type        TEXT,
                flag_status      TEXT,
                pole_pct         REAL,
                flag_bars        INTEGER,
                breakout_level   REAL,
                flag_stop        REAL,
                flag_target      REAL,
                position_json TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                -- Pre-trade prompt fields
                thesis        TEXT,
                invalidation  TEXT,
                exit_plan     TEXT,
                confidence    INTEGER DEFAULT 3,
                regime_score  REAL,
                iv_note       TEXT,
                -- Skip tracking fields
                skip_reason   TEXT,
                skip_note     TEXT,
                suggestion_score REAL,
                suggestion_ev    REAL,
                suggestion_structure TEXT,
                outcome_if_taken REAL
            );

            CREATE TABLE IF NOT EXISTS signal_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date    TEXT NOT NULL,
                ticker       TEXT NOT NULL,
                signal_type  TEXT,
                price        REAL,
                ma10         REAL,
                ma21         REAL,
                ma50         REAL,
                vcs          REAL,
                rs           INTEGER,
                vol_ratio    REAL,
                short_score      INTEGER,
                short_setup_type TEXT,
                rejection_ma     TEXT,
                short_coiling    INTEGER,
                atr          REAL,
                sector       TEXT,
                theme        TEXT,
                flag_detected    INTEGER,
                flag_type        TEXT,
                flag_status      TEXT,
                pole_pct         REAL,
                flag_bars        INTEGER,
                breakout_level   REAL,
                flag_stop        REAL,
                flag_target      REAL,
                signal_score     REAL,
                base_score       INTEGER,
                market_score     INTEGER,
                w_stack_ok       INTEGER DEFAULT 0,
                is_weekly_signal INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS backtest_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date        TEXT NOT NULL,
                signal_type     TEXT NOT NULL,
                total_signals   INTEGER,
                win_rate        REAL,
                avg_return_pct  REAL,
                avg_hold_days   INTEGER,
                best_trade_pct  REAL,
                worst_trade_pct REAL,
                sharpe          REAL,
                params          TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            -- V2: settings key-value store
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- V2: weekly scan summary cache
            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week_ending TEXT NOT NULL,
                total_signals INTEGER,
                long_signals  INTEGER,
                short_signals INTEGER,
                avg_score     REAL,
                market_label  TEXT,
                market_score  INTEGER,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_journal_ticker     ON journal(ticker);
            CREATE INDEX IF NOT EXISTS idx_journal_status     ON journal(status);
            CREATE INDEX IF NOT EXISTS idx_signal_history_date ON signal_history(scan_date);
            CREATE INDEX IF NOT EXISTS idx_signal_history_ticker ON signal_history(ticker);

            -- Dynamic universe additions (auto-expanded weekly)
            CREATE TABLE IF NOT EXISTS universe_additions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT NOT NULL UNIQUE,
                added_date  TEXT DEFAULT (date('now')),
                price       REAL,
                avg_vol     INTEGER,
                rs_score    REAL,
                vol_trend   REAL,
                mom_1m      REAL,
                reason      TEXT,
                active      INTEGER DEFAULT 1,
                removed_date TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_universe_additions_ticker ON universe_additions(ticker);

            -- Watchlist tracker — persists daily signal appearances
            CREATE TABLE IF NOT EXISTS watchlist_tracker (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT NOT NULL,
                signal_type  TEXT,
                score        REAL,
                sector       TEXT,
                first_seen   TEXT DEFAULT (date('now')),
                last_seen    TEXT DEFAULT (date('now')),
                appearances  INTEGER DEFAULT 1,
                UNIQUE(ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist_tracker(ticker);

            -- Watchlist exports — one row per daily export
            CREATE TABLE IF NOT EXISTS watchlist_exports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                export_date TEXT NOT NULL,
                tickers_json TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            -- Bot trades (DAX ASRS + FTSE 1BN/1BP pushed from VPS)
            CREATE TABLE IF NOT EXISTS bot_trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                bot          TEXT NOT NULL,          -- 'DAX' or 'FTSE'
                date         TEXT NOT NULL,
                trade_num    INTEGER DEFAULT 1,
                direction    TEXT,                   -- 'LONG' or 'SHORT'
                entry        REAL,
                exit         REAL,
                pnl_pts      REAL,
                mfe          REAL,
                bar_type     TEXT,                   -- FTSE: '1BN','1BP'; DAX: null
                bar_width    REAL,
                stake        REAL,
                stop_phase   TEXT,
                exit_reason  TEXT,
                extra_json   TEXT,                   -- any additional fields
                created_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bot_trades_bot  ON bot_trades(bot);
            CREATE INDEX IF NOT EXISTS idx_bot_trades_date ON bot_trades(date);
        """)

        # Safe column additions for existing DBs (ALTER TABLE IF NOT EXISTS not supported in old SQLite)
        existing_journal_cols = {row[1] for row in conn.execute("PRAGMA table_info(journal)").fetchall()}
        for col, typedef in [
            ("signal_score", "REAL"),
            ("tier",         "INTEGER DEFAULT 2"),
            ("sector",       "TEXT"),
            ("position_json","TEXT"),
        ]:
            if col not in existing_journal_cols:
                try:
                    conn.execute(f"ALTER TABLE journal ADD COLUMN {col} {typedef}")
                except Exception:
                    pass

        # ── Migrate journal table: add £ PnL columns if missing ─────────────
        existing_j_cols = {row[1] for row in conn.execute("PRAGMA table_info(journal)").fetchall()}
        for col, typedef in [("pnl_gbp", "REAL"), ("position_size_gbp", "REAL")]:
            if col not in existing_j_cols:
                try:
                    conn.execute(f"ALTER TABLE journal ADD COLUMN {col} {typedef}")
                except Exception:
                    pass

        existing_sh_cols = {row[1] for row in conn.execute("PRAGMA table_info(signal_history)").fetchall()}
        # ── Migrate journal table for £ P&L tracking ─────────────────────────
        existing_j_cols = {row[1] for row in conn.execute("PRAGMA table_info(journal)").fetchall()}
        for col, typedef in [
            ("pnl_gbp",           "REAL"),
            ("pnl_r",             "REAL"),
            ("position_size_gbp", "REAL"),
        ]:
            if col not in existing_j_cols:
                try:
                    conn.execute(f"ALTER TABLE journal ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
        for col, typedef in [
            ("signal_score",     "REAL"),
            ("base_score",       "INTEGER"),
            ("market_score",     "INTEGER"),
            ("theme",            "TEXT"),
            ("flag_detected",    "INTEGER"),
            ("flag_type",        "TEXT"),
            ("flag_status",      "TEXT"),
            ("pole_pct",         "REAL"),
            ("flag_bars",        "INTEGER"),
            ("breakout_level",   "REAL"),
            ("flag_stop",        "REAL"),
            ("flag_target",      "REAL"),
        ]:
            if col not in existing_sh_cols:
                try:
                    conn.execute(f"ALTER TABLE signal_history ADD COLUMN {col} {typedef}")
                except Exception:
                    pass

    print(f"[db] Initialised at {DB_PATH}")

    # ── Safe column migrations (idempotent — runs on every startup) ──────────
    _new_journal_cols = [
        ("thesis",               "TEXT"),
        ("invalidation",         "TEXT"),
        ("exit_plan",            "TEXT"),
        ("confidence",           "INTEGER DEFAULT 3"),
        ("regime_score",         "REAL"),
        ("iv_note",              "TEXT"),
        ("skip_reason",          "TEXT"),
        ("skip_note",            "TEXT"),
        ("suggestion_score",     "REAL"),
        ("suggestion_ev",        "REAL"),
        ("suggestion_structure", "TEXT"),
        ("outcome_if_taken",     "REAL"),
    ]
    with get_conn() as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(journal)").fetchall()}
        for col, typedef in _new_journal_cols:
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE journal ADD COLUMN {col} {typedef}")
                    print(f"[db] Migrated journal: added {col}")
                except Exception as e:
                    print(f"[db] Migration warning ({col}): {e}")


# ── Journal CRUD ──────────────────────────────────────────────────────────────

def journal_add(entry: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO journal (
                ticker, added_date, signal_type, entry_price,
                ma10, ma21, ma50, vcs, rs, vol_ratio, atr,
                stop_price, target_1, target_2, target_3, notes, status,
                signal_score, tier, sector, position_json,
                thesis, invalidation, exit_plan, confidence,
                regime_score, iv_note,
                skip_reason, skip_note,
                suggestion_score, suggestion_ev, suggestion_structure
            ) VALUES (
                :ticker, :added_date, :signal_type, :entry_price,
                :ma10, :ma21, :ma50, :vcs, :rs, :vol_ratio, :atr,
                :stop_price, :target_1, :target_2, :target_3, :notes, :status,
                :signal_score, :tier, :sector, :position_json,
                :thesis, :invalidation, :exit_plan, :confidence,
                :regime_score, :iv_note,
                :skip_reason, :skip_note,
                :suggestion_score, :suggestion_ev, :suggestion_structure
            )
        """, {
            **{k: None for k in [
                "ma10","ma21","ma50","vol_ratio","atr","signal_score","tier",
                "sector","position_json","thesis","invalidation","exit_plan",
                "confidence","regime_score","iv_note","skip_reason","skip_note",
                "suggestion_score","suggestion_ev","suggestion_structure",
            ]},
            **entry,
            "tier":          entry.get("tier", 2),
            "position_json": json.dumps(entry.get("position")) if entry.get("position") else None,
        })
        return cur.lastrowid


def journal_list(status: str = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM journal WHERE status = ? ORDER BY added_date DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM journal ORDER BY added_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def journal_update(id: int, updates: dict) -> bool:
    allowed = {
        "status", "exit_price", "exit_date", "exit_reason",
        "pnl_pct", "pnl_gbp", "position_size_gbp",
        "notes", "entry_price", "stop_price",
        "target_1", "target_2", "target_3",
        "signal_score", "tier", "sector", "position_json",
    }
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = id
    with get_conn() as conn:
        conn.execute(f"UPDATE journal SET {set_clause} WHERE id = :id", fields)
    return True


def journal_delete(id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM journal WHERE id = ?", (id,))


def journal_get(id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM journal WHERE id = ?", (id,)).fetchone()
        return dict(row) if row else None


# ── Signal History ────────────────────────────────────────────────────────────

def save_signal_history(scan_date: str, signals: list[dict]):
    """Persist each signal from a scan so we can backtest later."""
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO signal_history (
                scan_date, ticker, signal_type, price, ma10, ma21, ma50,
                vcs, rs, vol_ratio, short_score, short_setup_type, rejection_ma, short_coiling, atr, sector, theme, flag_detected, flag_type, flag_status, pole_pct, flag_bars, breakout_level, flag_stop, flag_target,
                signal_score, base_score, market_score, w_stack_ok, is_weekly_signal
            ) VALUES (
                :scan_date, :ticker, :signal_type, :price, :ma10, :ma21, :ma50,
                :vcs, :rs, :vol_ratio, :short_score, :short_setup_type, :rejection_ma, :short_coiling, :atr, :sector, :theme, :flag_detected, :flag_type, :flag_status, :pole_pct, :flag_bars, :breakout_level, :flag_stop, :flag_target,
                :signal_score, :base_score, :market_score, :w_stack_ok, :is_weekly_signal
            )
        """, [
            {
                "scan_date":    scan_date,
                "ticker":       s.get("ticker"),
                "signal_type":  s.get("bouncing_from") or ("SHORT" if s.get("short_score", 0) > 50 else None),
                "price":        s.get("price"),
                "ma10":         s.get("ma10"),
                "ma21":         s.get("ma21"),
                "ma50":         s.get("ma50"),
                "vcs":          s.get("vcs"),
                "rs":           s.get("rs"),
                "vol_ratio":    s.get("vol_ratio"),
                "short_score":       s.get("short_score", 0),
                "short_setup_type":  s.get("short_setup_type"),
                "rejection_ma":      s.get("rejection_ma"),
                "short_coiling":     int(bool(s.get("short_coiling", False))),
                "atr":          s.get("atr"),
                "sector":       s.get("sector"),
                "theme":        s.get("theme"),
                "flag_detected":  int(bool(s.get("flag_detected", False))),
                "flag_type":      s.get("flag_type"),
                "flag_status":    s.get("flag_status"),
                "pole_pct":       s.get("pole_pct"),
                "flag_bars":      s.get("flag_bars"),
                "breakout_level": s.get("flag_breakout_level"),
                "flag_stop":      s.get("flag_stop_price"),
                "flag_target":    s.get("flag_target_price"),
                "signal_score": s.get("signal_score"),
                "base_score":      s.get("base_score", 0),
                "market_score":    s.get("market_score"),
                "w_stack_ok":      int(bool(s.get("w_stack_ok", False))),
                "is_weekly_signal": int(bool(s.get("is_weekly_signal", False))),
            }
            for s in signals
        ])


def get_signal_history(ticker: str = None, days: int = 365) -> list[dict]:
    with get_conn() as conn:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM signal_history WHERE ticker = ? ORDER BY scan_date DESC LIMIT 200",
                (ticker,)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM signal_history
                   WHERE scan_date >= date('now', ?)
                   ORDER BY scan_date DESC""",
                (f"-{days} days",)
            ).fetchall()
        return [dict(r) for r in rows]


# ── Backtest Results ──────────────────────────────────────────────────────────

def save_backtest(result: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO backtest_results (
                run_date, signal_type, total_signals, win_rate,
                avg_return_pct, avg_hold_days, best_trade_pct,
                worst_trade_pct, sharpe, params
            ) VALUES (
                :run_date, :signal_type, :total_signals, :win_rate,
                :avg_return_pct, :avg_hold_days, :best_trade_pct,
                :worst_trade_pct, :sharpe, :params
            )
        """, {**result, "params": json.dumps(result.get("params", {}))})


def get_backtest_results() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backtest_results ORDER BY run_date DESC, signal_type"
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"]) if d["params"] else {}
            results.append(d)
        return results


# ── Historical Backtest Tables ────────────────────────────────────────────────

def init_backtest_tables():
    """Create extended backtest tables."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS historical_signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_date     TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                signal_type     TEXT NOT NULL,
                price           REAL,
                entry_close     REAL,       -- close on signal date
                entry_next_open REAL,       -- next day open (realistic entry)
                breakout_price  REAL,       -- 20-day high + 0.5% (breakout entry level)
                base_low        REAL,       -- lowest low of last 15 days (breakout stop)
                ma10            REAL,
                ma21            REAL,
                ma50            REAL,
                vcs             REAL,
                rs              INTEGER,
                vol_ratio       REAL,
                atr             REAL,
                base_score      INTEGER,
                base_type       TEXT,
                vcp_stages      INTEGER,
                sector          TEXT,
                sector_rs_1m    REAL,
                market_score    INTEGER,
                pct_from_ma21   REAL,
                w_stack_ok      INTEGER DEFAULT 0,
                w_ema10         REAL,
                w_ema40         REAL,
                w_ema10_slope   REAL,
                w_above_ema10   INTEGER DEFAULT 0,
                w_above_ema40   INTEGER DEFAULT 0,
                within_1atr_wema10 INTEGER DEFAULT 0,
                is_weekly_signal   INTEGER DEFAULT 0,
                regime_filtered    INTEGER DEFAULT 0,  -- 1 = signal fired in WARN/DANGER, not traded
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS historical_trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id       INTEGER REFERENCES historical_signals(id),
                signal_date     TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                signal_type     TEXT,
                entry_type      TEXT,       -- 'close' or 'next_open'
                entry_price     REAL,
                exit_price      REAL,
                exit_reason     TEXT,       -- stop/t1/t2/t3/ma21/timeout
                hold_days       INTEGER,
                pnl_pct         REAL,
                pnl_r           REAL,       -- pnl in R multiples (1R = 1.5x ATR)
                atr             REAL,
                stop_price      REAL,
                trail_exit      INTEGER DEFAULT 0,
                vcs             REAL,
                rs              INTEGER,
                base_score      INTEGER,
                sector          TEXT,
                market_score    INTEGER,
                is_short        INTEGER DEFAULT 0,
                day_of_week     TEXT,       -- MON/TUE/WED/THU/FRI
                mae_pct         REAL,       -- max adverse excursion %
                mae_r           REAL,       -- max adverse excursion in R
                mfe_pct         REAL,       -- max favourable excursion %
                mfe_r           REAL,       -- max favourable excursion in R
                slippage_pct    REAL,       -- round-trip slippage applied
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bt_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date        TEXT NOT NULL,
                signal_type     TEXT,
                total_trades    INTEGER,
                win_rate        REAL,
                avg_pnl_pct     REAL,
                avg_pnl_r       REAL,
                avg_hold_days   REAL,
                best_trade_pct  REAL,
                worst_trade_pct REAL,
                sharpe          REAL,
                profit_factor   REAL,
                max_drawdown_pct REAL,
                params          TEXT,       -- JSON
                exit_breakdown  TEXT,       -- JSON
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS equity_curve (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER REFERENCES bt_runs(id),
                curve_date      TEXT NOT NULL,
                portfolio_value REAL,
                daily_pnl       REAL,
                open_positions  INTEGER,
                drawdown_pct    REAL,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_hist_signals_date   ON historical_signals(signal_date);
            CREATE INDEX IF NOT EXISTS idx_hist_signals_ticker ON historical_signals(ticker);
            CREATE INDEX IF NOT EXISTS idx_hist_trades_type    ON historical_trades(signal_type);
            CREATE INDEX IF NOT EXISTS idx_hist_trades_date    ON historical_trades(signal_date);
        """)
        # ── Migrate existing DBs: add MAE/MFE columns if missing ─────────────
        existing_ht_cols = {row[1] for row in conn.execute("PRAGMA table_info(historical_trades)").fetchall()}
        for col, typedef in [
            ("mae_pct",      "REAL"),
            ("mae_r",        "REAL"),
            ("mfe_pct",      "REAL"),
            ("mfe_r",        "REAL"),
            ("slippage_pct", "REAL"),
        ]:
            if col not in existing_ht_cols:
                try:
                    conn.execute(f"ALTER TABLE historical_trades ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
        # Migrate: add weekly signal columns to historical_signals if missing
        existing_hs_cols = {row[1] for row in conn.execute("PRAGMA table_info(historical_signals)").fetchall()}
        for col, typedef in [
            ("day_of_week",        "TEXT"),
            ("w_stack_ok",         "INTEGER DEFAULT 0"),
            ("w_ema10",            "REAL"),
            ("w_ema40",            "REAL"),
            ("w_ema10_slope",      "REAL"),
            ("w_above_ema10",      "INTEGER DEFAULT 0"),
            ("w_above_ema40",      "INTEGER DEFAULT 0"),
            ("within_1atr_wema10", "INTEGER DEFAULT 0"),
            ("is_weekly_signal",   "INTEGER DEFAULT 0"),
            ("regime_filtered",    "INTEGER DEFAULT 0"),
            ("breakout_price",     "REAL"),
            ("base_low",           "REAL"),
        ]:
            if col not in existing_hs_cols:
                try:
                    conn.execute(f"ALTER TABLE historical_signals ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
        conn.executescript("")
    print("[db] Historical backtest tables ready")


def save_historical_signals(signals: list[dict]):
    if not signals:
        return
    with get_conn() as conn:
        conn.executemany("""
            INSERT OR IGNORE INTO historical_signals (
                signal_date, ticker, signal_type, price, entry_close, entry_next_open,
                breakout_price, base_low,
                ma10, ma21, ma50, vcs, rs, vol_ratio, atr, base_score, base_type,
                vcp_stages, sector, sector_rs_1m, market_score, pct_from_ma21,
                day_of_week,
                w_stack_ok, w_ema10, w_ema40, w_ema10_slope, w_above_ema10,
                w_above_ema40, within_1atr_wema10, is_weekly_signal, regime_filtered
            ) VALUES (
                :signal_date, :ticker, :signal_type, :price, :entry_close, :entry_next_open,
                :breakout_price, :base_low,
                :ma10, :ma21, :ma50, :vcs, :rs, :vol_ratio, :atr, :base_score, :base_type,
                :vcp_stages, :sector, :sector_rs_1m, :market_score, :pct_from_ma21,
                :day_of_week,
                :w_stack_ok, :w_ema10, :w_ema40, :w_ema10_slope, :w_above_ema10,
                :w_above_ema40, :within_1atr_wema10, :is_weekly_signal,
                COALESCE(:regime_filtered, 0)
            )
        """, signals)


def save_historical_trades(trades: list[dict]):
    if not trades:
        return
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO historical_trades (
                signal_id, signal_date, ticker, signal_type, entry_type, entry_price,
                exit_price, exit_reason, hold_days, pnl_pct, pnl_r, atr, stop_price,
                trail_exit, vcs, rs, base_score, sector,
                market_score, is_short, day_of_week,
                mae_pct, mae_r, mfe_pct, mfe_r, slippage_pct
            ) VALUES (
                :signal_id, :signal_date, :ticker, :signal_type, :entry_type, :entry_price,
                :exit_price, :exit_reason, :hold_days, :pnl_pct, :pnl_r, :atr, :stop_price,
                :trail_exit, :vcs, :rs, :base_score, :sector,
                :market_score, :is_short, :day_of_week,
                :mae_pct, :mae_r, :mfe_pct, :mfe_r, :slippage_pct
            )
        """, trades)


def save_bt_run(result: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO bt_runs (
                run_date, signal_type, total_trades, win_rate, avg_pnl_pct, avg_pnl_r,
                avg_hold_days, best_trade_pct, worst_trade_pct, sharpe, profit_factor,
                max_drawdown_pct, params, exit_breakdown
            ) VALUES (
                :run_date, :signal_type, :total_trades, :win_rate, :avg_pnl_pct, :avg_pnl_r,
                :avg_hold_days, :best_trade_pct, :worst_trade_pct, :sharpe, :profit_factor,
                :max_drawdown_pct, :params, :exit_breakdown
            )
        """, {
            **result,
            "params": json.dumps(result.get("params", {})),
            "exit_breakdown": json.dumps(result.get("exit_breakdown", {})),
        })
        return cur.lastrowid


def save_equity_curve(run_id: int, curve: list[dict]):
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO equity_curve (run_id, curve_date, portfolio_value, daily_pnl, open_positions, drawdown_pct)
            VALUES (:run_id, :curve_date, :portfolio_value, :daily_pnl, :open_positions, :drawdown_pct)
        """, [{**c, "run_id": run_id} for c in curve])


def get_historical_trades(
    signal_type: str = None,
    min_vcs: float = None,
    max_vcs: float = None,
    min_rs: int = None,
    min_base_score: int = None,
    sector: str = None,
    min_market_score: int = None,
    max_market_score: int = None,
    entry_type: str = None,
    date_from: str = None,   # "YYYY-MM-DD" inclusive
    date_to: str = None,     # "YYYY-MM-DD" inclusive
    sector_rs_positive: bool = None,   # True = sector outperforming SPY on 1m
    sector_rs_confirmed: bool = None,  # True = outperforming on BOTH 1m and 3m
    limit: int = None,
) -> list[dict]:
    """Flexible drill-down query with filters."""
    conditions = ["1=1"]
    params = {}

    if signal_type:
        conditions.append("t.signal_type = :signal_type")
        params["signal_type"] = signal_type
    if min_vcs is not None:
        conditions.append("t.vcs >= :min_vcs")
        params["min_vcs"] = min_vcs
    if max_vcs is not None:
        conditions.append("t.vcs <= :max_vcs")
        params["max_vcs"] = max_vcs
    if min_rs is not None:
        conditions.append("t.rs >= :min_rs")
        params["min_rs"] = min_rs
    if min_base_score is not None:
        conditions.append("t.base_score >= :min_base_score")
        params["min_base_score"] = min_base_score
    if sector:
        conditions.append("t.sector = :sector")
        params["sector"] = sector
    if min_market_score is not None:
        conditions.append("t.market_score >= :min_market_score")
        params["min_market_score"] = min_market_score
    if max_market_score is not None:
        conditions.append("t.market_score <= :max_market_score")
        params["max_market_score"] = max_market_score
    if entry_type:
        conditions.append("t.entry_type = :entry_type")
        params["entry_type"] = entry_type
    if date_from:
        conditions.append("t.signal_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("t.signal_date <= :date_to")
        params["date_to"] = date_to

    # sector_rs filters require joining to historical_signals
    # We handle this via a subquery on signal_id
    if sector_rs_positive:
        conditions.append(
            "signal_id IN (SELECT id FROM historical_signals WHERE sector_rs_1m > 0)"
        )
    if sector_rs_confirmed:
        conditions.append(
            "signal_id IN (SELECT id FROM historical_signals WHERE sector_rs_1m > 0 AND sector_rs_1m IS NOT NULL)"
        )

    where = " AND ".join(conditions)

    with get_conn() as conn:
        # Join to historical_signals to pull sector_rs_1m alongside trade data
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        rows = conn.execute(
            f"""SELECT t.*, s.sector_rs_1m
                FROM historical_trades t
                LEFT JOIN historical_signals s ON t.signal_id = s.id
                WHERE {where}
                ORDER BY t.signal_date DESC
                {limit_clause}""",
            params
        ).fetchall()
        return [dict(r) for r in rows]


def get_bt_runs() -> list[dict]:
    with get_conn() as conn:
        # Ensure table exists with all expected columns (add any missing ones)
        try:
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(bt_runs)").fetchall()}
            expected_cols = {
                "avg_pnl_r": "REAL", "sharpe": "REAL", "profit_factor": "REAL",
                "max_drawdown_pct": "REAL", "exit_breakdown": "TEXT",
            }
            for col, typ in expected_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE bt_runs ADD COLUMN {col} {typ}")
            conn.commit()
        except Exception:
            pass

        try:
            rows = conn.execute(
                "SELECT * FROM bt_runs ORDER BY run_date DESC, signal_type"
            ).fetchall()
        except Exception:
            return []

        results = []
        for r in rows:
            try:
                d = dict(r)
                d["params"]         = json.loads(d.get("params") or "{}")
                d["exit_breakdown"] = json.loads(d.get("exit_breakdown") or "{}")
                results.append(d)
            except Exception:
                pass
        return results


def get_equity_curve(run_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM equity_curve WHERE run_id = ? ORDER BY curve_date",
            (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def clear_historical_trades():
    """Wipe and re-run from scratch."""
    with get_conn() as conn:
        conn.execute("DELETE FROM historical_trades")
        conn.execute("DELETE FROM historical_signals")
        conn.execute("DELETE FROM bt_runs")
        conn.execute("DELETE FROM equity_curve")


# ── Dynamic universe additions ────────────────────────────────────────────────

def save_dynamic_addition(ticker: str, price: float, avg_vol: int,
                           rs_score: float, vol_trend: float,
                           mom_1m: float, reason: str):
    """Insert or update a dynamic ticker addition."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO universe_additions
                (ticker, price, avg_vol, rs_score, vol_trend, mom_1m, reason, active, added_date)
            VALUES (:ticker, :price, :avg_vol, :rs_score, :vol_trend, :mom_1m, :reason, 1, date('now'))
            ON CONFLICT(ticker) DO UPDATE SET
                price       = excluded.price,
                avg_vol     = excluded.avg_vol,
                rs_score    = excluded.rs_score,
                vol_trend   = excluded.vol_trend,
                mom_1m      = excluded.mom_1m,
                reason      = excluded.reason,
                active      = 1,
                removed_date = NULL
        """, dict(ticker=ticker, price=price, avg_vol=avg_vol,
                  rs_score=rs_score, vol_trend=vol_trend,
                  mom_1m=mom_1m, reason=reason))


def get_dynamic_additions(active_only: bool = True) -> list[dict]:
    """Return all dynamic universe additions."""
    with get_conn() as conn:
        where = "WHERE active = 1" if active_only else ""
        rows = conn.execute(
            f"SELECT * FROM universe_additions {where} ORDER BY rs_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def remove_dynamic_addition(ticker: str):
    """Soft-delete a dynamic addition (keeps history)."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE universe_additions
            SET active = 0, removed_date = date('now')
            WHERE ticker = ?
        """, (ticker,))


def upsert_watchlist_tickers(signals: list[dict]):
    """Update watchlist tracker with today's signals — upsert on ticker."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        for s in signals:
            ticker = s.get("ticker")
            if not ticker:
                continue
            existing = conn.execute(
                "SELECT id, appearances FROM watchlist_tracker WHERE ticker = ?", (ticker,)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE watchlist_tracker
                    SET last_seen = ?, appearances = appearances + 1,
                        score = ?, signal_type = ?, sector = ?
                    WHERE ticker = ?
                """, (today, s.get("signal_score"), s.get("signal_type"), s.get("sector"), ticker))
            else:
                conn.execute("""
                    INSERT INTO watchlist_tracker (ticker, signal_type, score, sector, first_seen, last_seen, appearances)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (ticker, s.get("signal_type"), s.get("signal_score"), s.get("sector"), today, today))


def get_watchlist_with_age() -> list[dict]:
    """Return all watchlist tickers with days_on_watchlist calculated."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ticker, signal_type, score, sector, first_seen, last_seen, appearances,
                   CAST(julianday('now') - julianday(first_seen) AS INTEGER) as days_on_watchlist
            FROM watchlist_tracker
            ORDER BY days_on_watchlist DESC, score DESC
        """).fetchall()
        return [dict(r) for r in rows]


def save_watchlist_export(tickers: list[dict], export_date: str):
    """Save a snapshot of today's export."""
    import json
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO watchlist_exports (export_date, tickers_json)
            VALUES (?, ?)
        """, (export_date, json.dumps(tickers)))


def get_watchlist_exports(limit: int = 14) -> list[dict]:
    """Return recent watchlist exports."""
    import json
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, export_date, tickers_json, created_at
            FROM watchlist_exports
            ORDER BY export_date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tickers"] = json.loads(d["tickers_json"])
            del d["tickers_json"]
            result.append(d)
        return result


# ── Bot trades (DAX / FTSE) ──────────────────────────────────────────────────

def bot_trades_sync(bot: str, trades: list[dict]):
    """Replace all trades for a bot with the new list (full sync)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM bot_trades WHERE bot = ?", (bot,))
        for t in trades:
            extra = {k: v for k, v in t.items()
                     if k not in ("bot", "date", "trade_num", "direction", "entry",
                                  "exit", "pnl_pts", "mfe", "bar_type", "bar_width",
                                  "stake", "stop_phase", "exit_reason")}
            conn.execute("""
                INSERT INTO bot_trades (bot, date, trade_num, direction, entry, exit,
                    pnl_pts, mfe, bar_type, bar_width, stake, stop_phase, exit_reason, extra_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bot,
                t.get("date", ""),
                t.get("trade_num", 1),
                t.get("direction", ""),
                t.get("entry"),
                t.get("exit"),
                t.get("pnl_pts"),
                t.get("mfe"),
                t.get("bar_type"),
                t.get("bar_width"),
                t.get("stake"),
                t.get("stop_phase"),
                t.get("exit_reason"),
                json.dumps(extra) if extra else None,
            ))


def bot_trades_list(bot: str = None) -> list[dict]:
    """Get all bot trades, optionally filtered by bot name."""
    with get_conn() as conn:
        if bot:
            rows = conn.execute(
                "SELECT * FROM bot_trades WHERE bot = ? ORDER BY date, trade_num", (bot,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bot_trades ORDER BY bot, date, trade_num"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("extra_json"):
                d["extra"] = json.loads(d["extra_json"])
            d.pop("extra_json", None)
            result.append(d)
        return result


def bot_trades_stats(bot: str) -> dict:
    """Compute summary stats for a bot."""
    trades = bot_trades_list(bot)
    if not trades:
        return {"bot": bot, "total_trades": 0}

    pnls = [t["pnl_pts"] or 0 for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = round(sum(pnls), 1)

    # Equity curve
    equity = []
    running = 0
    peak = 0
    max_dd = 0
    for t in trades:
        running += (t["pnl_pts"] or 0)
        running = round(running, 1)
        peak = max(peak, running)
        dd = round(peak - running, 1)
        max_dd = max(max_dd, dd)
        equity.append({"date": t["date"], "equity": running, "drawdown": dd})

    # Daily P&L
    daily = {}
    for t in trades:
        d = t["date"]
        daily[d] = round(daily.get(d, 0) + (t["pnl_pts"] or 0), 1)

    # Monthly P&L
    monthly = {}
    for t in trades:
        m = t["date"][:7]
        monthly[m] = round(monthly.get(m, 0) + (t["pnl_pts"] or 0), 1)

    # Streaks
    daily_results = list(daily.values())
    win_streak = lose_streak = cur_w = cur_l = 0
    for d in daily_results:
        if d > 0:
            cur_w += 1; cur_l = 0
            win_streak = max(win_streak, cur_w)
        elif d < 0:
            cur_l += 1; cur_w = 0
            lose_streak = max(lose_streak, cur_l)
        else:
            cur_w = cur_l = 0

    return {
        "bot": bot,
        "total_trades": len(trades),
        "total_pnl": total_pnl,
        "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
        "avg_win": round(sum(wins) / len(wins), 1) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 1) if losses else 0,
        "best_trade": round(max(pnls), 1) if pnls else 0,
        "worst_trade": round(min(pnls), 1) if pnls else 0,
        "max_drawdown": round(max_dd, 1),
        "win_streak": win_streak,
        "lose_streak": lose_streak,
        "trading_days": len(daily),
        "avg_mfe": round(sum(t["mfe"] or 0 for t in trades) / len(trades), 1) if trades else 0,
        "equity_curve": equity,
        "daily_pnl": daily,
        "monthly_pnl": monthly,
        "trades": trades,
    }
