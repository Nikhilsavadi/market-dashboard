"""
options_chain.py
----------------
Fetches live options chain from Yahoo Finance and runs:
  - Black-Scholes implied volatility extraction
  - Expected value calculation vs user's probability estimate
  - Bull call spread builder (finds best strike combo)
  - Kelly optimal bet size
  - Bearish put spread support too
"""

import math
import requests
import time
from datetime import date, datetime
from typing import Optional


# ── Black-Scholes helpers ─────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via approximation."""
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if x >= 0 else 1.0 - cdf


def bs_price(S, K, T, r, sigma, option_type="call") -> float:
    """Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        return max(0, S - K) if option_type == "call" else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_delta(S, K, T, r, sigma, option_type="call") -> float:
    """Black-Scholes delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if (option_type == "call" and S > K) else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    if option_type == "call":
        return _norm_cdf(d1)
    else:
        return _norm_cdf(d1) - 1.0


def implied_vol(market_price, S, K, T, r, option_type="call") -> Optional[float]:
    """Newton-Raphson IV solver."""
    if T <= 0 or market_price <= 0:
        return None
    intrinsic = max(0, S - K) if option_type == "call" else max(0, K - S)
    if market_price < intrinsic:
        return None
    sigma = 0.3  # initial guess
    for _ in range(50):
        price = bs_price(S, K, T, r, sigma, option_type)
        diff  = price - market_price
        if abs(diff) < 0.0001:
            return round(sigma, 4)
        # Vega
        d1    = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        vega  = S * math.sqrt(T) * math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
        if vega < 1e-8:
            break
        sigma -= diff / vega
        sigma  = max(0.001, min(sigma, 20.0))
    return round(sigma, 4)


# ── Kelly calculator ──────────────────────────────────────────────────────────

def kelly_fraction(win_prob: float, win_payoff: float, loss_amount: float = 1.0) -> float:
    """
    Kelly criterion for binary bet.
    win_prob: probability of winning (0-1)
    win_payoff: how much you win (in same units as loss_amount)
    loss_amount: how much you lose (default 1.0)
    Returns optimal fraction of bankroll to bet.
    """
    if win_prob <= 0 or win_prob >= 1 or win_payoff <= 0:
        return 0.0
    b = win_payoff / loss_amount  # odds
    f = (b * win_prob - (1 - win_prob)) / b
    return round(max(0.0, f), 4)


def kelly_position_size(
    portfolio_value: float,
    kelly_f: float,
    max_loss_pct: float = 2.5,
    fractional: float = 0.25,
) -> dict:
    """
    Returns recommended $ position size.
    Applies fractional Kelly (default 1/4 Kelly) and caps at max_loss_pct.
    """
    full_kelly_dollar  = portfolio_value * kelly_f
    frac_kelly_dollar  = full_kelly_dollar * fractional
    max_loss_dollar    = portfolio_value * (max_loss_pct / 100)
    recommended        = min(frac_kelly_dollar, max_loss_dollar)
    return {
        "full_kelly_pct":  round(kelly_f * 100, 2),
        "frac_kelly_pct":  round(kelly_f * fractional * 100, 2),
        "recommended_usd": round(recommended, 2),
        "max_loss_usd":    round(max_loss_dollar, 2),
        "contracts":       max(1, int(recommended / 100)),  # rough: $100 per contract
    }


# ── Yahoo Finance options chain ───────────────────────────────────────────────

def fetch_chain(ticker: str, expiry_index: int = 0) -> Optional[dict]:
    """
    Fetch options chain from Alpaca Options API.
    Falls back to a BS-synthetic chain if Alpaca is unavailable or has no data.
    expiry_index: 0 = nearest expiry, 1 = next, etc.
    """
    import os
    from datetime import date, timedelta
    from alpaca.data.historical import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest

    api_key    = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        return _synthetic_chain(ticker, expiry_index)

    try:
        # Step 1: Get stock price from Alpaca snapshot
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestQuoteRequest
        stock_client = StockHistoricalDataClient(api_key, secret_key)
        try:
            quote_req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quote     = stock_client.get_stock_latest_quote(quote_req)
            q         = quote.get(ticker)
            S         = float((q.ask_price + q.bid_price) / 2) if q else None
        except Exception:
            S = None

        # Step 2: Get option contracts to find expiry dates
        trading_client = TradingClient(api_key, secret_key, paper=True)
        today     = date.today()
        max_expiry = today + timedelta(days=90)

        contracts_req = GetOptionContractsRequest(
            underlying_symbols=[ticker],
            expiration_date_gte=str(today + timedelta(days=7)),
            expiration_date_lte=str(max_expiry),
            type="call",
            limit=1000,
        )
        contracts_resp = trading_client.get_option_contracts(contracts_req)
        contracts = list(contracts_resp.option_contracts) if hasattr(contracts_resp, "option_contracts") else []

        if not contracts:
            print(f"[options_chain] No Alpaca contracts for {ticker}, using synthetic")
            return _synthetic_chain(ticker, expiry_index)

        # Group by expiry date
        from collections import defaultdict
        by_expiry = defaultdict(list)
        for c in contracts:
            by_expiry[str(c.expiration_date)].append(c)

        sorted_expiries = sorted(by_expiry.keys())
        if expiry_index >= len(sorted_expiries):
            expiry_index = len(sorted_expiries) - 1

        chosen_expiry = sorted_expiries[expiry_index]
        expiry_date   = date.fromisoformat(chosen_expiry)
        dte           = (expiry_date - today).days
        T             = max(dte / 365.0, 0.001)
        r             = 0.045

        # Step 3: Get snapshots for this expiry
        expiry_contracts = by_expiry[chosen_expiry]
        symbols = [c.symbol for c in expiry_contracts]

        # Fetch snapshots in batches of 100
        option_client = OptionHistoricalDataClient(api_key, secret_key)
        from alpaca.data.requests import OptionSnapshotRequest
        snapshots = {}
        for i in range(0, len(symbols), 100):
            batch = symbols[i:i+100]
            try:
                snap_req  = OptionSnapshotRequest(symbol_or_symbols=batch)
                snap_resp = option_client.get_option_snapshot(snap_req)
                snapshots.update(snap_resp)
            except Exception as e:
                print(f"[options_chain] Snapshot batch error: {e}")

        if not snapshots and S is None:
            return _synthetic_chain(ticker, expiry_index)

        # Step 4: Build calls list from snapshots
        calls = []
        puts  = []
        for c in expiry_contracts:
            sym  = c.symbol
            snap = snapshots.get(sym)
            K    = float(c.strike_price)

            if snap and snap.latest_quote:
                bid  = float(snap.latest_quote.bid_price or 0)
                ask  = float(snap.latest_quote.ask_price or 0)
                last = float(snap.latest_trade.price if snap.latest_trade else 0)
                oi   = int(snap.greeks.delta * 1000) if snap.greeks else 0  # proxy
                vol  = float(snap.implied_volatility or 0.3) if snap.implied_volatility else 0.3
                mid  = round((bid + ask) / 2, 2) if bid and ask else last
                # Use Alpaca greeks if available, else compute via BS
                if snap.greeks:
                    delta = float(snap.greeks.delta or 0)
                    iv    = float(snap.implied_volatility or vol)
                else:
                    spot  = S or K  # fallback
                    iv    = vol
                    delta = bs_delta(spot, K, T, r, iv, "call" if c.type == "call" else "put")
            else:
                # No snapshot — estimate via BS with assumed IV
                spot  = S or K
                iv    = 0.35
                bid   = ask = last = 0
                mid   = round(bs_price(spot, K, T, r, iv, str(c.type)), 2)
                delta = bs_delta(spot, K, T, r, iv, str(c.type))
                oi    = 0

            entry = {
                "strike": K, "bid": bid, "ask": ask,
                "lastPrice": last, "mid": mid,
                "iv": round(iv, 4), "delta": round(delta, 4),
                "openInterest": oi, "dte": dte,
                "alpaca_symbol": sym,
            }
            if str(c.type) == "call":
                calls.append(entry)
            else:
                puts.append(entry)

        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])

        # Derive spot price from ATM strike if we don't have it
        if S is None and calls:
            S = sorted(calls, key=lambda x: abs(x["delta"] - 0.5))[0]["strike"]

        return {
            "ticker":  ticker,
            "expiry":  chosen_expiry,
            "dte":     dte,
            "spot":    S,
            "calls":   calls,
            "puts":    puts,
            "source":  "alpaca",
        }

    except Exception as e:
        print(f"[options_chain] Alpaca fetch failed for {ticker}: {e}")
        return _synthetic_chain(ticker, expiry_index)


def _synthetic_chain(ticker: str, expiry_index: int = 0) -> Optional[dict]:
    """
    Generate a synthetic options chain using Black-Scholes when Alpaca is unavailable.
    Uses yfinance for spot price only (fast_info, not the blocked options endpoint).
    Assumes IV of 35% — reasonable baseline for mid-cap growth stocks.
    """
    import os, yfinance as yf
    from datetime import date, timedelta

    S = None
    # Alpaca latest quote (always works if keys set, no proxy issues)
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestQuoteRequest
        api_key    = os.environ.get("ALPACA_API_KEY")
        secret_key = os.environ.get("ALPACA_SECRET_KEY")
        if api_key and secret_key:
            stock_client = StockHistoricalDataClient(api_key, secret_key)
            quote_req    = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quote        = stock_client.get_stock_latest_quote(quote_req)
            q            = quote.get(ticker)
            if q:
                S = float((q.ask_price + q.bid_price) / 2)
    except Exception:
        pass
    # yfinance fast_info as fallback (not the blocked options endpoint)
    if not S:
        try:
            info = yf.Ticker(ticker).fast_info
            S    = float(getattr(info, "last_price", None) or getattr(info, "regular_market_price", 0))
        except Exception:
            pass

    if not S or S <= 0:
        return None

    # Synthetic expiry schedule: 3rd Friday of next 3 months
    today = date.today()
    expiries = []
    for months_ahead in range(1, 4):
        # Approximate 3rd Friday
        yr  = today.year + ((today.month + months_ahead - 1) // 12)
        mo  = ((today.month + months_ahead - 1) % 12) + 1
        first_day = date(yr, mo, 1)
        first_fri = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_fri = first_fri + timedelta(weeks=2)
        if third_fri > today:
            expiries.append(third_fri)

    if not expiries:
        return None

    expiry_index = min(expiry_index, len(expiries) - 1)
    expiry_date  = expiries[expiry_index]
    dte          = (expiry_date - today).days
    T            = max(dte / 365.0, 0.001)
    r, iv        = 0.045, 0.35

    # Build strikes around ATM: ±20% in 2.5% steps
    strikes = sorted(set(
        round(S * (1 + step / 100), 2)
        for step in range(-20, 25, 3)
    ))

    def make_option(K, opt_type):
        price = round(bs_price(S, K, T, r, iv, opt_type), 2)
        delta = bs_delta(S, K, T, r, iv, opt_type)
        spread = max(round(price * 0.05, 2), 0.05)
        return {
            "strike": K, "bid": round(price - spread, 2),
            "ask": round(price + spread, 2),
            "lastPrice": price, "mid": price,
            "iv": iv, "delta": round(delta, 4),
            "openInterest": 0, "dte": dte, "synthetic": True,
        }

    calls = [make_option(K, "call") for K in strikes]
    puts  = [make_option(K, "put")  for K in strikes]

    return {
        "ticker": ticker, "expiry": expiry_date.isoformat(),
        "dte": dte, "spot": S,
        "calls": calls, "puts": puts,
        "source": "synthetic",
    }


def build_call_spread(
    chain: dict,
    user_prob: float,       # user's P(above long strike) estimate 0-1
    price_target: float,    # user's expected price if ITM
    portfolio_value: float,
    max_loss_pct: float = 2.5,
) -> dict:
    """
    Finds the best bull call spread given user's probability and target.
    Scores all combos by EV and Kelly, returns top 5.
    """
    S    = chain["spot"]
    T    = chain["T"]
    r    = chain["r"]
    calls = chain["calls"]

    if not calls or S <= 0 or T <= 0:
        return {"spreads": [], "error": "No calls available"}

    results = []

    for i, long_leg in enumerate(calls):
        K1  = long_leg["strike"]
        iv1 = long_leg["iv"] or 0.3

        # Only consider long strikes near/above spot (ATM to +15%)
        if K1 < S * 0.95 or K1 > S * 1.20:
            continue

        cost_long = long_leg["mid"]
        if cost_long <= 0:
            continue

        for short_leg in calls[i+1:]:
            K2 = short_leg["strike"]

            # Short strike should be between target and max realistic
            if K2 > S * 1.35:
                break
            if K2 < price_target * 0.95:
                continue

            cost_short = short_leg["mid"]
            if cost_short <= 0:
                continue

            net_debit  = round(cost_long - cost_short, 2)
            max_profit = round(K2 - K1 - net_debit, 2)

            if net_debit <= 0 or max_profit <= 0:
                continue

            # User's probability that price exceeds K1 (long strike)
            # Assume if user says prob of K1, prob of K2 scales down proportionally
            # Simple: use BS to get ratio, then apply user's override
            delta_k1 = long_leg["delta"] or 0.5
            delta_k2 = short_leg["delta"] or 0.2
            # Scale user prob by market ratio between strikes
            ratio = delta_k2 / delta_k1 if delta_k1 > 0 else 0.4
            prob_k2 = user_prob * ratio  # prob price ends above short strike

            # Expected value at expiry
            # If price ends between K1 and K2: partial value = (avg_price - K1)
            # Approximate: 50% chance of hitting K2 if above K1
            avg_settle_if_itm = min(price_target, (K1 + K2) / 2 + (price_target - K1) * 0.3)
            avg_settle_if_itm = max(K1, min(K2, avg_settle_if_itm))

            # EV components
            # P(below K1): lose net_debit
            # P(between K1 and K2): win partial = avg_settle - K1 - net_debit
            # P(above K2): win max = max_profit
            p_itm   = user_prob
            p_above = prob_k2
            p_below = 1 - p_itm

            partial_val = max(0, avg_settle_if_itm - K1 - net_debit)
            ev = (p_above * max_profit) + ((p_itm - p_above) * partial_val) - (p_below * net_debit)
            ev = round(ev, 3)

            if ev <= 0:
                continue

            # Kelly
            # Simplify: treat as binary — either win max_profit or lose net_debit
            # Use p_itm as win probability (conservative: partial counts as win)
            kf    = kelly_fraction(p_itm, max_profit, net_debit)
            sizing = kelly_position_size(portfolio_value, kf, max_loss_pct)

            # Market EV (using delta as market's implied prob)
            market_prob_k1 = long_leg["delta"] or 0.5
            market_prob_k2 = short_leg["delta"] or 0.2
            market_ev = (market_prob_k2 * max_profit) + ((market_prob_k1 - market_prob_k2) * partial_val) - ((1 - market_prob_k1) * net_debit)

            ev_edge = round(ev - market_ev, 3)

            results.append({
                "long_strike":   K1,
                "short_strike":  K2,
                "net_debit":     net_debit,
                "max_profit":    max_profit,
                "max_loss":      net_debit,
                "spread_width":  round(K2 - K1, 2),
                "reward_risk":   round(max_profit / net_debit, 2),
                "breakeven":     round(K1 + net_debit, 2),
                "user_ev":       ev,
                "market_ev":     round(market_ev, 3),
                "ev_edge":       ev_edge,
                "user_prob_itm": round(p_itm * 100, 1),
                "user_prob_max": round(p_above * 100, 1),
                "market_prob":   round(market_prob_k1 * 100, 1),
                "kelly_full":    round(kf * 100, 2),
                "kelly_frac":    round(kf * 25, 2),  # 1/4 Kelly
                "rec_contracts": sizing["contracts"],
                "rec_usd":       sizing["recommended_usd"],
                "long_iv":       long_leg["iv"],
                "short_iv":      short_leg["iv"],
                "long_delta":    long_leg["delta"],
                "short_delta":   short_leg["delta"],
                "long_bid":      long_leg["bid"],
                "long_ask":      long_leg["ask"],
                "short_bid":     short_leg["bid"],
                "short_ask":     short_leg["ask"],
            })

    # Sort by EV edge descending
    results.sort(key=lambda x: x["ev_edge"], reverse=True)

    return {
        "spreads":   results[:6],
        "total_found": len(results),
        "spot":      S,
        "expiry":    chain["expiry"],
        "dte":       chain["dte"],
    }


def build_put_spread(
    chain: dict,
    user_prob: float,       # P(below long put strike)
    price_target: float,    # expected price if ITM (below spot)
    portfolio_value: float,
    max_loss_pct: float = 2.5,
) -> dict:
    """Bearish put spread builder."""
    S    = chain["spot"]
    T    = chain["T"]
    puts = chain["puts"]

    if not puts or S <= 0:
        return {"spreads": [], "error": "No puts available"}

    results = []

    for i, long_leg in enumerate(puts):
        K1 = long_leg["strike"]  # long put (higher strike = more expensive)
        if K1 > S * 1.02 or K1 < S * 0.80:
            continue

        cost_long = long_leg["mid"]
        if cost_long <= 0:
            continue

        for short_leg in puts[:i]:  # lower strikes
            K2 = short_leg["strike"]  # short put (lower strike)
            if K2 < price_target * 1.05 or K2 > K1:
                continue

            cost_short = short_leg["mid"]
            if cost_short <= 0:
                continue

            net_debit  = round(cost_long - cost_short, 2)
            max_profit = round(K1 - K2 - net_debit, 2)

            if net_debit <= 0 or max_profit <= 0:
                continue

            p_itm  = user_prob
            kf     = kelly_fraction(p_itm, max_profit, net_debit)
            sizing = kelly_position_size(portfolio_value, kf, max_loss_pct)
            ev     = round(p_itm * max_profit - (1 - p_itm) * net_debit, 3)

            if ev <= 0:
                continue

            market_prob = long_leg["delta"] or 0.3

            results.append({
                "long_strike":   K1,
                "short_strike":  K2,
                "net_debit":     net_debit,
                "max_profit":    max_profit,
                "max_loss":      net_debit,
                "spread_width":  round(K1 - K2, 2),
                "reward_risk":   round(max_profit / net_debit, 2),
                "breakeven":     round(K1 - net_debit, 2),
                "user_ev":       ev,
                "user_prob_itm": round(p_itm * 100, 1),
                "market_prob":   round(market_prob * 100, 1),
                "kelly_full":    round(kf * 100, 2),
                "kelly_frac":    round(kf * 25, 2),
                "rec_contracts": sizing["contracts"],
                "rec_usd":       sizing["recommended_usd"],
                "long_iv":       long_leg["iv"],
                "long_delta":    long_leg["delta"],
            })

    results.sort(key=lambda x: x["user_ev"], reverse=True)
    return {
        "spreads":     results[:6],
        "total_found": len(results),
        "spot":        S,
        "expiry":      chain["expiry"],
        "dte":         chain["dte"],
    }
