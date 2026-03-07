"""
EP Portfolio Simulation with realistic constraints:
  - $10K starting capital, 5x CFD leverage available
  - be10_trail15 strategy on gap 30%+ EPs
  - Position sizing based on stop distance
  - Max concurrent positions
  - Day-by-day equity curve
  - Track drawdowns, margin usage, win streaks
"""
import os, sys, json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

import numpy as np
import pandas as pd
from ep_backtest import _detect_ep_day
from stockbee_ep import EP_CONFIG

LOOKBACK = 365
STARTING_CAPITAL = 10_000
LEVERAGE = 5  # 5x CFD leverage
MAX_POSITIONS = 8  # max concurrent open positions
RISK_PER_TRADE_PCT = 3  # risk 3% of equity per trade on the stop
MAX_POSITION_PCT = 30  # max 30% of equity per position (notional / leverage)
BE_TRIGGER = 10  # move to breakeven after 10% gain
TRAIL_PCT = 15   # then trail 15% from highest close
MIN_GAP = 30     # gap 30%+ filter

print(f"=== EP Portfolio Simulation ===")
print(f"Starting capital : ${STARTING_CAPITAL:,}")
print(f"Leverage         : {LEVERAGE}x (CFDs)")
print(f"Max positions    : {MAX_POSITIONS}")
print(f"Risk per trade   : {RISK_PER_TRADE_PCT}% of equity at stop")
print(f"Strategy         : BE {BE_TRIGGER}% then trail {TRAIL_PCT}%")
print(f"Filter           : Gap {MIN_GAP}%+")
print()

# ── Fetch bars ────────────────────────────────────────────────────────────────
from scanner import get_alpaca_client
from universe_expander import get_scan_universe
from watchlist import ETFS
from sector_rs import SECTOR_ETFS

all_tickers = get_scan_universe()
all_etfs = list(set(ETFS + list(SECTOR_ETFS.values()) + ["SPY", "QQQ", "IWM"]))
stock_tickers = [t for t in all_tickers if t not in all_etfs]

print(f"Fetching bars for {len(stock_tickers)} stocks...")
if os.environ.get("POLYGON_API_KEY"):
    from polygon_client import fetch_bars as pg_bars
    bars_data = pg_bars(stock_tickers, days=max(500, LOOKBACK + 150),
                        interval="day", min_rows=50, label="ep-portsim")
else:
    client = get_alpaca_client()
    from scanner import fetch_bars
    bars_data = fetch_bars(client, stock_tickers)

print(f"Got bars for {len(bars_data)} stocks\n")
cfg = dict(EP_CONFIG)

# ── Build a master calendar of all trading days ──────────────────────────────
all_dates = set()
for ticker, df in bars_data.items():
    if df is not None and len(df) > 0:
        for dt in df.index:
            all_dates.add(pd.Timestamp(dt).normalize())
all_dates = sorted(all_dates)

# We only simulate the last LOOKBACK days
cutoff_date = all_dates[-1] - timedelta(days=LOOKBACK)
sim_dates = [d for d in all_dates if d >= cutoff_date]
print(f"Simulation period: {sim_dates[0].date()} to {sim_dates[-1].date()} ({len(sim_dates)} trading days)\n")

# ── Pre-scan: find all EP events with their dates ────────────────────────────
print("Pre-scanning all EP events...")
ep_by_date = defaultdict(list)  # date -> list of EP event dicts

for ticker, df in bars_data.items():
    if df is None or len(df) < 60:
        continue
    n = len(df)
    start_idx = max(50, n - LOOKBACK)
    for idx in range(start_idx, n - 1):
        ep = _detect_ep_day(df, idx, cfg)
        if ep is None:
            continue
        if ep["gap_pct"] < MIN_GAP:
            continue

        ep_date = pd.Timestamp(df.index[idx]).normalize()
        entry_idx = idx + 1
        entry_date = pd.Timestamp(df.index[entry_idx]).normalize()
        entry_price = float(df["open"].iloc[entry_idx])
        if entry_price <= 0:
            continue

        initial_stop = ep["day_low"] * 0.99
        stop_distance_pct = (entry_price - initial_stop) / entry_price * 100

        if ep["is_9m"] and ep["gap_pct"] < 5:
            ep_type = "9M"
        elif ep["gap_pct"] >= 10 and not ep.get("neglected", True):
            ep_type = "STORY"
        else:
            ep_type = "CLASSIC"

        ep_by_date[entry_date].append({
            "ticker": ticker, "df": df, "entry_idx": entry_idx,
            "entry_price": entry_price, "initial_stop": initial_stop,
            "stop_distance_pct": stop_distance_pct,
            "ep_date": ep["date"], "entry_date": str(entry_date.date()),
            "ep_type": ep_type, "gap_pct": ep["gap_pct"],
            "vol_ratio": ep["vol_ratio"],
        })

total_eps = sum(len(v) for v in ep_by_date.values())
print(f"Found {total_eps} EP events across {len(ep_by_date)} entry dates\n")


# ── Day-by-day portfolio simulation ──────────────────────────────────────────
class Position:
    def __init__(self, ticker, entry_price, shares, initial_stop, entry_date,
                 ep_type, gap_pct, cost_basis):
        self.ticker = ticker
        self.entry_price = entry_price
        self.shares = shares
        self.initial_stop = initial_stop
        self.stop = initial_stop
        self.entry_date = entry_date
        self.ep_type = ep_type
        self.gap_pct = gap_pct
        self.cost_basis = cost_basis  # actual $ deployed (before leverage)
        self.highest = entry_price
        self.breakeven_hit = False
        self.current_price = entry_price
        self.hold_days = 0
        self.closed = False
        self.exit_price = None
        self.exit_date = None
        self.exit_reason = None
        self.pnl = 0

    def update(self, day_high, day_low, day_close, current_date):
        if self.closed:
            return
        self.hold_days += 1
        self.current_price = day_close

        # Check stop hit
        if day_low <= self.stop:
            self.exit_price = self.stop
            self.exit_date = str(current_date.date())
            self.exit_reason = "be_stop" if self.breakeven_hit else "initial_stop"
            self.pnl = (self.exit_price - self.entry_price) * self.shares
            self.closed = True
            return

        # Update highest
        if day_close > self.highest:
            self.highest = day_close

        # Phase 1: move to breakeven
        if not self.breakeven_hit and self.highest >= self.entry_price * (1 + BE_TRIGGER / 100):
            self.stop = max(self.stop, self.entry_price * 1.005)
            self.breakeven_hit = True

        # Phase 2: trail
        if self.breakeven_hit:
            new_stop = self.highest * (1 - TRAIL_PCT / 100)
            self.stop = max(self.stop, new_stop)

    @property
    def unrealized_pnl(self):
        if self.closed:
            return self.pnl
        return (self.current_price - self.entry_price) * self.shares

    @property
    def market_value(self):
        if self.closed:
            return 0
        return self.current_price * self.shares


equity = STARTING_CAPITAL
cash = STARTING_CAPITAL
open_positions = []
closed_trades = []
equity_curve = []
daily_log = []
max_equity = STARTING_CAPITAL
max_drawdown = 0
max_concurrent = 0
margin_calls = 0
skipped_no_capital = 0
skipped_max_pos = 0

for day_idx, current_date in enumerate(sim_dates):
    # ── Update open positions ─────────────────────────────────────────────
    newly_closed = []
    for pos in open_positions:
        if pos.closed:
            continue
        df = bars_data.get(pos.ticker)
        if df is None:
            continue
        # Find today's bar
        try:
            mask = pd.Timestamp(df.index).normalize() == current_date if len(df) == 1 else \
                   [pd.Timestamp(d).normalize() == current_date for d in df.index]
            day_bar = df[mask]
        except Exception:
            day_bar = pd.DataFrame()

        if len(day_bar) == 0:
            continue

        day_high = float(day_bar["high"].iloc[0])
        day_low = float(day_bar["low"].iloc[0])
        day_close = float(day_bar["close"].iloc[0])

        pos.update(day_high, day_low, day_close, current_date)

        if pos.closed:
            newly_closed.append(pos)
            cash += pos.cost_basis + pos.pnl  # return capital + PnL
            closed_trades.append(pos)

    open_positions = [p for p in open_positions if not p.closed]

    # ── Open new positions (entry signals for today) ──────────────────────
    new_eps = ep_by_date.get(current_date, [])
    # Sort by gap size descending (take biggest gaps first)
    new_eps.sort(key=lambda x: x["gap_pct"], reverse=True)

    for ep in new_eps:
        # Check if already in this ticker
        if any(p.ticker == ep["ticker"] for p in open_positions):
            continue

        if len(open_positions) >= MAX_POSITIONS:
            skipped_max_pos += 1
            continue

        entry_price = ep["entry_price"]
        stop_price = ep["initial_stop"]
        stop_dist = entry_price - stop_price

        if stop_dist <= 0:
            continue

        # Position sizing: risk X% of equity at the stop
        risk_amount = equity * (RISK_PER_TRADE_PCT / 100)
        shares_by_risk = risk_amount / stop_dist

        # Cap notional at MAX_POSITION_PCT of equity
        max_notional = equity * (MAX_POSITION_PCT / 100)
        shares_by_cap = max_notional / entry_price
        shares = min(shares_by_risk, shares_by_cap)

        # Cost basis (margin required = notional / leverage)
        notional = shares * entry_price
        margin_required = notional / LEVERAGE

        if margin_required > cash * 0.90:  # leave 10% buffer
            # Try half size
            shares = shares / 2
            notional = shares * entry_price
            margin_required = notional / LEVERAGE
            if margin_required > cash * 0.90:
                skipped_no_capital += 1
                continue

        cash -= margin_required

        pos = Position(
            ticker=ep["ticker"],
            entry_price=entry_price,
            shares=shares,
            initial_stop=stop_price,
            entry_date=ep["entry_date"],
            ep_type=ep["ep_type"],
            gap_pct=ep["gap_pct"],
            cost_basis=margin_required,
        )
        open_positions.append(pos)

    # ── End of day accounting ─────────────────────────────────────────────
    unrealized = sum(p.unrealized_pnl for p in open_positions)
    total_margin = sum(p.cost_basis for p in open_positions)
    equity = cash + total_margin + unrealized
    max_equity = max(max_equity, equity)
    dd = (max_equity - equity) / max_equity * 100 if max_equity > 0 else 0
    max_drawdown = max(max_drawdown, dd)
    max_concurrent = max(max_concurrent, len(open_positions))

    # Margin call check: if equity < 50% of margin
    if total_margin > 0 and equity < total_margin * 0.5:
        margin_calls += 1

    equity_curve.append({
        "date": str(current_date.date()),
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "positions": len(open_positions),
        "unrealized": round(unrealized, 2),
        "drawdown": round(dd, 2),
    })

# ── Close remaining open positions at last price ─────────────────────────────
for pos in open_positions:
    pos.pnl = (pos.current_price - pos.entry_price) * pos.shares
    pos.exit_price = pos.current_price
    pos.exit_date = str(sim_dates[-1].date())
    pos.exit_reason = "open_eod"
    pos.closed = True
    cash += pos.cost_basis + pos.pnl
    closed_trades.append(pos)

final_equity = cash

# ── Results ───────────────────────────────────────────────────────────────────
print("=" * 80)
print("PORTFOLIO SIMULATION RESULTS")
print("=" * 80)

print(f"\n  Starting Capital  : ${STARTING_CAPITAL:>10,}")
print(f"  Final Equity      : ${final_equity:>10,.2f}")
print(f"  Total Return      : {(final_equity / STARTING_CAPITAL - 1) * 100:>+9.1f}%")
print(f"  Max Equity        : ${max_equity:>10,.2f}")
print(f"  Max Drawdown      : {max_drawdown:>9.1f}%")
print(f"  Margin Calls      : {margin_calls}")

# Annualize
days_in_sim = (sim_dates[-1] - sim_dates[0]).days
total_ret = final_equity / STARTING_CAPITAL
annualized = (total_ret ** (365 / days_in_sim) - 1) * 100 if days_in_sim > 0 else 0
print(f"\n  Simulation Days   : {days_in_sim}")
print(f"  Annualized Return : {annualized:>+9.1f}%")

# Trade stats
wins = [t for t in closed_trades if t.pnl > 0]
losses = [t for t in closed_trades if t.pnl <= 0]
still_open = [t for t in closed_trades if t.exit_reason == "open_eod"]

print(f"\n  Total Trades      : {len(closed_trades)}")
print(f"  Winners           : {len(wins)} ({len(wins)/len(closed_trades)*100:.1f}%)")
print(f"  Losers            : {len(losses)} ({len(losses)/len(closed_trades)*100:.1f}%)")
print(f"  Still Open (EOD)  : {len(still_open)}")
print(f"  Skipped (max pos) : {skipped_max_pos}")
print(f"  Skipped (no cash) : {skipped_no_capital}")
print(f"  Max Concurrent    : {max_concurrent}")

if wins:
    avg_win_pct = np.mean([(w.exit_price - w.entry_price) / w.entry_price * 100 for w in wins])
    print(f"\n  Avg Win           : +{avg_win_pct:.1f}%")
if losses:
    avg_loss_pct = np.mean([(l.exit_price - l.entry_price) / l.entry_price * 100 for l in losses])
    print(f"  Avg Loss          : {avg_loss_pct:.1f}%")

avg_hold = np.mean([t.hold_days for t in closed_trades])
print(f"  Avg Hold Days     : {avg_hold:.1f}")

# Biggest wins and losses by $ PnL
print(f"\n  --- TOP 10 WINS (by $ PnL) ---")
sorted_wins = sorted(wins, key=lambda t: t.pnl, reverse=True)
for t in sorted_wins[:10]:
    ret_pct = (t.exit_price - t.entry_price) / t.entry_price * 100
    print(f"    {t.ticker:<7} {t.entry_date} -> {t.exit_date}  "
          f"${t.pnl:>+8,.0f}  ({ret_pct:>+6.1f}%)  gap {t.gap_pct:.0f}%  "
          f"held {t.hold_days}d  [{t.exit_reason}]")

print(f"\n  --- TOP 10 LOSSES (by $ PnL) ---")
sorted_losses = sorted(losses, key=lambda t: t.pnl)
for t in sorted_losses[:10]:
    ret_pct = (t.exit_price - t.entry_price) / t.entry_price * 100
    print(f"    {t.ticker:<7} {t.entry_date} -> {t.exit_date}  "
          f"${t.pnl:>+8,.0f}  ({ret_pct:>+6.1f}%)  gap {t.gap_pct:.0f}%  "
          f"held {t.hold_days}d  [{t.exit_reason}]")

# Monthly breakdown
print(f"\n  --- MONTHLY BREAKDOWN ---")
monthly = defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0})
for t in closed_trades:
    if t.exit_date:
        month = t.exit_date[:7]
        monthly[month]["trades"] += 1
        monthly[month]["pnl"] += t.pnl
        if t.pnl > 0:
            monthly[month]["wins"] += 1

print(f"  {'Month':<10} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'PnL $':>10} {'Cum PnL $':>12}")
print(f"  {'-'*55}")
cum_pnl = 0
for month in sorted(monthly.keys()):
    m = monthly[month]
    cum_pnl += m["pnl"]
    wr = m["wins"] / m["trades"] * 100 if m["trades"] > 0 else 0
    print(f"  {month:<10} {m['trades']:>7} {m['wins']:>5} {wr:>5.0f}% ${m['pnl']:>+9,.0f} ${cum_pnl:>+11,.0f}")

# Equity curve milestones
print(f"\n  --- EQUITY MILESTONES ---")
milestones = [15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000]
eq_df = pd.DataFrame(equity_curve)
for m in milestones:
    reached = eq_df[eq_df["equity"] >= m]
    if len(reached) > 0:
        first = reached.iloc[0]
        print(f"  ${m:>7,} reached on {first['date']} (day {eq_df.index[eq_df['date'] == first['date']].tolist()[0]})")

# Drawdown periods
print(f"\n  --- WORST DRAWDOWN PERIODS ---")
peak_eq = 0
dd_start = None
dd_periods = []
for row in equity_curve:
    eq = row["equity"]
    if eq > peak_eq:
        if dd_start and peak_eq > 0:
            dd_pct = (peak_eq - min_eq) / peak_eq * 100
            if dd_pct > 5:
                dd_periods.append({"start": dd_start, "end": row["date"],
                                   "peak": peak_eq, "trough": min_eq, "dd_pct": dd_pct})
        peak_eq = eq
        dd_start = row["date"]
        min_eq = eq
    else:
        min_eq = min(min_eq, eq)

dd_periods.sort(key=lambda x: x["dd_pct"], reverse=True)
for dd in dd_periods[:5]:
    print(f"  {dd['start']} to {dd['end']}: "
          f"${dd['peak']:,.0f} -> ${dd['trough']:,.0f} (-{dd['dd_pct']:.1f}%)")

# ── Save equity curve ────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "ep_equity_curve.json"
out_path.write_text(json.dumps({
    "config": {
        "starting_capital": STARTING_CAPITAL, "leverage": LEVERAGE,
        "max_positions": MAX_POSITIONS, "risk_per_trade_pct": RISK_PER_TRADE_PCT,
        "strategy": f"be{BE_TRIGGER}_trail{TRAIL_PCT}", "min_gap": MIN_GAP,
    },
    "summary": {
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / STARTING_CAPITAL - 1) * 100, 1),
        "annualized_return_pct": round(annualized, 1),
        "max_drawdown_pct": round(max_drawdown, 1),
        "total_trades": len(closed_trades),
        "win_rate": round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else 0,
    },
    "equity_curve": equity_curve,
    "trades": [
        {"ticker": t.ticker, "entry_date": t.entry_date, "exit_date": t.exit_date,
         "entry_price": round(t.entry_price, 2), "exit_price": round(t.exit_price, 2) if t.exit_price else None,
         "pnl": round(t.pnl, 2), "hold_days": t.hold_days,
         "exit_reason": t.exit_reason, "ep_type": t.ep_type, "gap_pct": t.gap_pct}
        for t in closed_trades
    ],
}, indent=2, default=str))
print(f"\nEquity curve saved to {out_path.name}")
