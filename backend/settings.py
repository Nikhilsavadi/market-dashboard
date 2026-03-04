"""
settings.py
-----------
User-configurable trading settings stored in SQLite.
Controls account size, risk per trade, pre-earnings filter,
signal score threshold, and other preferences.
"""

import json
from database import get_conn


DEFAULTS = {
    "account_size":          10000.0,   # £ or $ — total trading account
    "risk_pct":              1.0,       # % of account risked per trade
    "max_positions":         5,         # max concurrent open trades
    "hide_earnings_lt_days": 14,        # filter out signals with earnings < N days
    "min_price":            5.0,        # skip stocks below this price
    "min_avg_vol":          200000,     # skip stocks below this 20-day avg volume
    "min_signal_score":      6,         # minimum score (1-10) to show in UI
    "alert_min_score":       7,         # minimum score to send Telegram alert
    "market_gate_longs":     45,        # suppress longs if market score < this
    "market_gate_shorts":    65,        # suppress shorts if market score > this
    "vcs_filter":            6.0,       # max VCS for long signals
    "rs_filter":             70,        # min RS rank for long signals
    "max_position_pct":      25.0,      # max % of account in any single position
}


def init_settings_table():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Insert defaults for any missing keys
        for k, v in DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, json.dumps(v))
            )


def get_settings() -> dict:
    init_settings_table()
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)  # start with defaults
    for row in rows:
        try:
            result[row["key"]] = json.loads(row["value"])
        except Exception:
            result[row["key"]] = row["value"]
    return result


def update_setting(key: str, value) -> dict:
    init_settings_table()
    if key not in DEFAULTS:
        raise ValueError(f"Unknown setting: {key}")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
    return get_settings()


def update_settings(updates: dict) -> dict:
    for k, v in updates.items():
        update_setting(k, v)
    return get_settings()


# ── Position Sizing ───────────────────────────────────────────────────────────

def calculate_position_size(
    entry_price: float,
    stop_price: float,
    account_size: float = None,
    risk_pct: float = None,
) -> dict:
    """
    Calculate position size based on ATR stop distance.

    shares = (account * risk_pct/100) / (entry - stop)
    position_value = shares * entry
    """
    s = get_settings()
    account = account_size or s["account_size"]
    risk = risk_pct or s["risk_pct"]

    if not entry_price or not stop_price or entry_price <= stop_price:
        return {
            "shares": None,
            "position_value": None,
            "risk_amount": None,
            "risk_pct_of_account": None,
        }

    risk_amount    = account * (risk / 100)
    stop_distance  = entry_price - stop_price
    shares         = risk_amount / stop_distance
    position_value = shares * entry_price
    pct_of_account = (position_value / account) * 100

    # Cap position size — never put more than max_position_pct% in one trade
    max_pos_pct   = s.get("max_position_pct", 25.0)
    max_pos_value = account * (max_pos_pct / 100)
    capped        = False
    if position_value > max_pos_value:
        position_value = max_pos_value
        shares         = position_value / entry_price
        pct_of_account = max_pos_pct
        capped         = True
        # Recalculate actual risk with capped shares
        risk_amount = shares * stop_distance

    return {
        "shares":              round(shares, 1),
        "position_value":      round(position_value, 2),
        "risk_amount":         round(risk_amount, 2),
        "risk_pct_of_account": round(pct_of_account, 1),
        "stop_distance":       round(stop_distance, 4),
        "account_size":        account,
        "risk_pct":            risk,
        "capped":              capped,
        "max_position_pct":    max_pos_pct,
    }


def calculate_portfolio_heat(open_journal_entries: list, account_size: float = None) -> dict:
    """
    Portfolio heat = total capital at risk across all open positions.
    Each open position risks (entry - stop) * shares.
    """
    s = get_settings()
    account = account_size or s["account_size"]
    risk_pct = s["risk_pct"]

    total_at_risk = 0.0
    for entry in open_journal_entries:
        ep = entry.get("entry_price")
        sp = entry.get("stop_price")
        if ep and sp and ep > sp:
            # Assume standard position sizing
            risk_amount = account * (risk_pct / 100)
            total_at_risk += risk_amount

    heat_pct = (total_at_risk / account) * 100 if account else 0
    max_heat = s["max_positions"] * risk_pct

    return {
        "total_at_risk":    round(total_at_risk, 2),
        "heat_pct":         round(heat_pct, 1),
        "max_heat_pct":     round(max_heat, 1),
        "open_positions":   len(open_journal_entries),
        "max_positions":    s["max_positions"],
        "slots_available":  max(0, s["max_positions"] - len(open_journal_entries)),
        "account_size":     account,
    }
