"""
trade_suggester.py
------------------
Options structure suggestion engine — three structures, capital-aware.

Structure selection (VCS + vol_ratio driven, not score):
  VCS <= 3 AND vol_ratio >= 2.0  -> OTM naked call  (close at T1, lowest outlay)
  VCS <= 3 AND vol_ratio 1.5-2.0 -> Ratio spread 1:2 (coiled, moderate vol)
  VCS 4-6  OR  vol_ratio < 1.5   -> Bull call spread  (standard, defined risk)
  VCS > 6                         -> Bull call spread + warning (loose base)
  Score 9+                        -> override: naked ATM call if EV wins

OTM call strike: price + 1 ATR (one standard move away)
OTM close target: T1 (sell when thesis plays out, don't hold to expiry)
Ratio spread: 1:2 (buy 1, sell 2 at T1 strike)
Premium cap: $500 per contract -- if OTM/ratio exceeds this, fall back to spread

Kelly: fractional (25%), hard cap 2.5% portfolio
"""

import math
import time
from datetime import datetime, timedelta
from typing import Optional

from options_chain import (
    fetch_chain, build_call_spread, kelly_position_size,
    bs_price, implied_vol, kelly_fraction
)

RISK_FREE_RATE   = 0.053
MAX_POSITION_PCT = 0.025   # 2.5% hard cap
KELLY_FRACTION   = 0.25    # fractional Kelly
MAX_PREMIUM      = 500     # $500 per contract cap
OTM_ATR_MULT     = 1.0     # OTM strike = price + 1 ATR


# -- Helpers ------------------------------------------------------------------

def _find_strike(calls: list, target: float) -> Optional[dict]:
    if not calls:
        return None
    return min(calls, key=lambda c: abs(c.get("strike", 9999) - target))


def _kelly_size(prob: float, win_mult: float, premium: float,
                portfolio_value: float) -> dict:
    kf        = kelly_fraction(prob, win_mult, 1.0)
    kf_frac   = kf * KELLY_FRACTION
    size_pct  = min(MAX_POSITION_PCT, kf_frac)
    contracts = max(1, int((portfolio_value * size_pct) / (premium * 100)))
    return {
        "kelly_full": round(kf, 4),
        "kelly_frac": round(kf_frac, 4),
        "size_pct":   round(size_pct * 100, 2),
        "contracts":  contracts,
        "cost":       round(contracts * premium * 100, 0),
    }


# -- Structure evaluators -----------------------------------------------------

def _evaluate_otm_call(chain, signal, prob, portfolio_value):
    """
    OTM call: strike = price + 1 ATR. Close at T1 (do NOT hold to expiry).
    Estimates value at T1 using BS with half the remaining DTE.
    Falls back (returns None) if premium > MAX_PREMIUM.
    """
    price = signal.get("price") or 0
    atr   = signal.get("atr") or price * 0.02
    t1    = signal.get("target_1") or price * 1.08
    calls = chain.get("calls", [])
    T     = chain.get("T", 0.08)

    if not calls or not price:
        return None

    call = _find_strike(calls, price + OTM_ATR_MULT * atr)
    if not call:
        return None

    strike = call.get("strike", price + atr)
    ask    = call.get("ask") or call.get("lastPrice") or 0
    iv     = call.get("iv") or 0.4

    if ask <= 0 or ask * 100 > MAX_PREMIUM:
        return None

    # Value when we close at T1 (halfway through DTE)
    val_at_t1 = bs_price(t1, strike, T * 0.5, RISK_FREE_RATE, iv, "call")
    avg_win   = max(0, val_at_t1 - ask)
    ev        = prob * avg_win - (1 - prob) * ask
    win_mult  = avg_win / ask if ask > 0 else 0
    sz        = _kelly_size(prob, win_mult, ask, portfolio_value)

    return {
        "structure":        "OTM_CALL",
        "long_strike":      round(strike, 2),
        "short_strike":     None,
        "premium":          round(ask, 2),
        "max_loss":         round(ask, 2),
        "max_gain":         "open (close at T1)",
        "max_gain_num":     round(avg_win, 2),
        "val_at_t1":        round(val_at_t1, 2),
        "close_target":     t1,
        "ev":               round(ev, 3),
        "iv":               round(iv, 3),
        "kelly_full":       sz["kelly_full"],
        "kelly_frac":       sz["kelly_frac"],
        "size_pct":         sz["size_pct"],
        "contracts":        sz["contracts"],
        "cost":             sz["cost"],
        "otm_distance":     round(strike - price, 2),
        "otm_distance_pct": round((strike - price) / price * 100, 1),
    }


def _evaluate_ratio_spread(chain, signal, prob, portfolio_value):
    """
    Ratio spread 1:2: buy 1 ATM call, sell 2 calls at T1 strike.
    Very low net debit (sometimes zero). Max profit at T1.
    Unlimited risk above T1 -- only appropriate when VCS <= 3.
    Falls back if net debit > MAX_PREMIUM.
    """
    price = signal.get("price") or 0
    atr   = signal.get("atr") or price * 0.02
    t1    = signal.get("target_1") or price * 1.08
    calls = chain.get("calls", [])

    if not calls or not price:
        return None

    long_call  = _find_strike(calls, price)
    short_call = _find_strike(calls, t1)

    if not long_call or not short_call:
        return None
    if long_call.get("strike") == short_call.get("strike"):
        return None

    long_strike  = long_call.get("strike", price)
    short_strike = short_call.get("strike", t1)
    long_ask     = long_call.get("ask") or long_call.get("lastPrice") or 0
    short_bid    = short_call.get("bid") or short_call.get("lastPrice") or 0
    iv           = long_call.get("iv") or 0.4

    if long_ask <= 0:
        return None

    net_debit    = max(0, long_ask - 2 * short_bid)
    if net_debit * 100 > MAX_PREMIUM:
        return None

    spread_width  = short_strike - long_strike
    max_profit    = max(0, spread_width - net_debit)
    blowout_price = t1 + 2 * atr  # approx pain point
    loss_blowout  = max(0, (blowout_price - long_strike) - 2 * (blowout_price - short_strike) - net_debit)
    ev            = prob * max_profit - (1 - prob) * max(net_debit, 0.5)

    prem_for_sz   = max(net_debit, 0.01)
    win_mult      = max_profit / prem_for_sz if prem_for_sz > 0 else 0
    sz            = _kelly_size(prob, win_mult, prem_for_sz, portfolio_value)

    return {
        "structure":       "RATIO_SPREAD",
        "long_strike":     round(long_strike, 2),
        "short_strike":    round(short_strike, 2),
        "ratio":           "1:2",
        "premium":         round(net_debit, 2),
        "max_loss":        round(net_debit, 2),
        "max_gain":        round(max_profit, 2),
        "max_gain_num":    round(max_profit, 2),
        "loss_at_blowout": round(loss_blowout, 2),
        "blowout_price":   round(blowout_price, 2),
        "ev":              round(ev, 3),
        "iv":              round(iv, 3),
        "kelly_full":      sz["kelly_full"],
        "kelly_frac":      sz["kelly_frac"],
        "size_pct":        sz["size_pct"],
        "contracts":       sz["contracts"],
        "cost":            round(max(net_debit, 0) * sz["contracts"] * 100, 0),
    }


def _evaluate_spread(chain, signal, prob, portfolio_value):
    """Standard 1:1 bull call spread. Always available as fallback."""
    price = signal.get("price") or 0
    t1    = signal.get("target_1") or price * 1.08

    if not price:
        return None

    result = build_call_spread(
        chain=chain,
        current_price=price,
        target_price=t1,
        probability_estimate=prob,
        portfolio_value=portfolio_value,
        max_loss_pct=MAX_POSITION_PCT * 100,
    )
    if not result or not result.get("spreads"):
        return None

    best = result["spreads"][0]
    best["structure"] = "CALL_SPREAD"
    return best


# -- Structure selection (VCS + vol_ratio primary) ----------------------------

def select_structure(signal, score, otm, ratio, spread, naked):
    """
    VCS + vol_ratio drives structure. Score 9+ can override to naked ATM call.

    VCS <= 3 AND vol >= 2.0  -> OTM call  (fast mover, lowest outlay)
    VCS <= 3 AND vol >= 1.5  -> Ratio 1:2 (coiled, moderate vol)
    everything else          -> Bull call spread
    Score 9+ override        -> naked ATM call if EV wins
    """
    vcs   = signal.get("vcs") or 6
    vol_r = signal.get("vol_ratio") or 1.0

    if vcs <= 3 and vol_r >= 2.0 and otm:
        chosen = otm
        reason = (
            f"OTM call: VCS {vcs} (tight base) + {vol_r:.1f}x volume "
            f"= fast move expected. Lowest outlay -- close at T1 (${signal.get('target_1','?')}), do not hold to expiry."
        )
    elif vcs <= 3 and vol_r >= 1.5 and ratio:
        chosen = ratio
        reason = (
            f"Ratio spread 1:2: VCS {vcs} (coiling) + {vol_r:.1f}x volume "
            f"= controlled cost with max profit at T1. "
            f"Tight base limits runaway risk above T1."
        )
    elif spread:
        chosen = spread
        reason = (
            f"Bull call spread: VCS {vcs}, {vol_r:.1f}x vol. "
            + ("Loose base -- defined risk essential, consider waiting for tighter VCS." if vcs > 6
               else "Standard defined-risk setup.")
        )
    else:
        return None

    # Score 9+ override: ATM naked call if EV beats chosen structure
    chosen_ev = chosen.get("ev") or 0
    naked_ev  = (naked or {}).get("ev") or 0
    if score >= 9 and naked and naked_ev > chosen_ev:
        alt = chosen
        return {
            **naked,
            "structure_reason": (
                f"Naked call: score 9+ override -- naked EV ${naked_ev:.2f} > "
                f"{chosen['structure']} EV ${chosen_ev:.2f}."
            ),
            "alternative": alt,
        }

    # Best available alternative for UI display
    alts = [x for x in [ratio, otm, spread] if x and x is not chosen]
    return {**chosen, "structure_reason": reason, "alternative": alts[0] if alts else None}


# -- Probability estimation ---------------------------------------------------

def estimate_probability(signal):
    score    = signal.get("combined_score") or signal.get("signal_score") or 5
    rs       = signal.get("rs") or 50
    vcs      = signal.get("vcs") or 6
    vol_r    = signal.get("vol_ratio") or 1
    social   = signal.get("social_label")
    aligned  = signal.get("sector_aligned", True)
    above200 = signal.get("above_ma200", True)

    if score >= 9:    base = 0.68
    elif score >= 8:  base = 0.60
    elif score >= 7:  base = 0.50
    elif score >= 6:  base = 0.40
    else:             base = 0.32

    adj, reasons = 0.0, []

    if rs >= 90:      adj += 0.05; reasons.append("RS 90+ (+5%)")
    elif rs >= 85:    adj += 0.03; reasons.append("RS 85+ (+3%)")
    if aligned:       adj += 0.04; reasons.append("Sector tailwind (+4%)")
    else:             adj -= 0.04; reasons.append("Sector headwind (-4%)")
    if social == "HOT":    adj += 0.05; reasons.append("Social HOT (+5%)")
    elif social == "ACTIVE": adj += 0.03; reasons.append("Social ACTIVE (+3%)")
    if vcs is not None and vcs <= 3: adj += 0.04; reasons.append("Tight base VCS<=3 (+4%)")
    if vol_r >= 2.0:  adj += 0.03; reasons.append("Volume conviction (+3%)")
    if not above200:  adj -= 0.08; reasons.append("Below MA200 (-8%)")

    final_prob = round(max(0.15, min(0.80, base + adj)), 3)
    return {
        "probability": final_prob,
        "base_rate":   base,
        "adjustments": adj,
        "reasons":     reasons,
        "confidence":  "high" if abs(adj) >= 0.08 else "medium" if abs(adj) >= 0.04 else "low",
    }


# -- Expiry selection ---------------------------------------------------------

def select_expiry(signal):
    price = signal.get("price") or 0
    t1    = signal.get("target_1") or 0
    atr   = signal.get("atr") or (price * 0.02)
    vcs   = signal.get("vcs") or 5

    days_to_t1 = max(5, round(abs(t1 - price) / atr)) if price and t1 and atr else 15
    vcs_buffer  = max(0, (vcs - 3) * 2)
    target_dte  = min(60, max(21, days_to_t1 * 2 + vcs_buffer))

    if target_dte <= 25:   expiry_index, dte_label = 0, "~3 weeks"
    elif target_dte <= 45: expiry_index, dte_label = 1, "~1 month"
    else:                  expiry_index, dte_label = 2, "~2 months"

    return {
        "target_dte":   target_dte,
        "expiry_index": expiry_index,
        "dte_label":    dte_label,
        "days_to_t1":   days_to_t1,
        "rationale":    f"T1 ~{days_to_t1}d at 1 ATR/day + VCS buffer -> {target_dte} DTE target",
    }


# -- Fixed-tier reference -----------------------------------------------------

def fixed_tier_size(score):
    if score >= 9:    pct = 2.5
    elif score >= 8:  pct = 2.0
    elif score >= 7:  pct = 1.0
    else:             pct = 0.5
    return {"pct": pct, "label": f"{pct}% (fixed tier)"}


# -- Main entry point ---------------------------------------------------------

def suggest_trade(signal: dict, portfolio_value: float = 50000) -> dict:
    ticker = signal.get("ticker", "?")
    score  = signal.get("combined_score") or signal.get("signal_score") or 5
    price  = signal.get("price") or 0
    vcs    = signal.get("vcs") or 6
    vol_r  = signal.get("vol_ratio") or 1.0

    prob_data    = estimate_probability(signal)
    prob         = prob_data["probability"]
    expiry_data  = select_expiry(signal)
    expiry_index = expiry_data["expiry_index"]

    chain = None
    try:
        chain = fetch_chain(ticker, expiry_index=expiry_index)
        if not chain:
            chain = fetch_chain(ticker, expiry_index=min(expiry_index + 1, 2))
    except Exception as e:
        return {"ticker": ticker, "error": f"Chain fetch failed: {e}", "status": "error"}

    if not chain:
        return {"ticker": ticker, "error": "No options chain available", "status": "no_chain"}

    otm    = _evaluate_otm_call(chain, signal, prob, portfolio_value)
    ratio  = _evaluate_ratio_spread(chain, signal, prob, portfolio_value)
    spread = _evaluate_spread(chain, signal, prob, portfolio_value)

    # Naked ATM call: only evaluated for score 9+ override
    naked = None
    if score >= 9:
        try:
            calls = chain.get("calls", [])
            atm   = _find_strike(calls, price) if calls else None
            if atm:
                ask    = atm.get("ask") or atm.get("lastPrice") or 0
                strike = atm.get("strike", price)
                t1     = signal.get("target_1") or price * 1.08
                iv     = atm.get("iv") or 0.4
                avg_win = max(0, t1 - strike)
                ev_n    = prob * avg_win - (1 - prob) * ask
                kf      = kelly_fraction(prob, avg_win / ask if ask > 0 else 0, 1.0)
                kf_f    = kf * KELLY_FRACTION
                sz      = min(MAX_POSITION_PCT, kf_f)
                ctrs    = max(1, int((portfolio_value * sz) / (ask * 100)))
                naked = {
                    "structure": "NAKED_CALL", "long_strike": strike, "short_strike": None,
                    "premium": round(ask, 2), "max_loss": round(ask, 2),
                    "max_gain": "unlimited", "max_gain_num": round(avg_win, 2),
                    "ev": round(ev_n, 3), "iv": round(iv, 3),
                    "kelly_full": round(kf, 4), "kelly_frac": round(kf_f, 4),
                    "size_pct": round(sz * 100, 2), "contracts": ctrs,
                    "cost": round(ctrs * ask * 100, 0),
                }
        except Exception:
            pass

    suggestion = select_structure(signal, score, otm, ratio, spread, naked)
    if not suggestion:
        return {"ticker": ticker, "error": "Could not build viable structure", "status": "no_spread"}

    kelly_full = suggestion.get("kelly_full") or suggestion.get("kelly_fraction") or 0
    kelly_frac = round(kelly_full * KELLY_FRACTION, 4)
    size_pct   = min(MAX_POSITION_PCT * 100, kelly_frac * 100)

    kelly_workings = {
        "full_kelly":       round(kelly_full * 100, 1),
        "fractional_kelly": round(kelly_frac * 100, 2),
        "applied_size":     round(size_pct, 2),
        "hard_cap":         MAX_POSITION_PCT * 100,
        "fixed_tier_ref":   fixed_tier_size(score),
        "note": (
            f"Full Kelly = {kelly_full*100:.1f}% -> "
            f"x{KELLY_FRACTION} fractional = {kelly_frac*100:.2f}% -> "
            f"capped at {size_pct:.2f}%"
        ),
    }

    struct   = suggestion.get("structure", "CALL_SPREAD")
    long_s   = suggestion.get("long_strike") or suggestion.get("buy_strike") or "?"
    short_s  = suggestion.get("short_strike") or suggestion.get("sell_strike")
    prem     = suggestion.get("premium") or suggestion.get("net_debit") or 0
    ev_val   = suggestion.get("ev") or suggestion.get("expected_value") or 0
    iv       = suggestion.get("iv") or chain.get("avg_iv") or 0

    struct_labels = {
        "OTM_CALL":     f"Buy ${long_s} OTM call @ ${prem:.2f} -- close at T1",
        "RATIO_SPREAD": f"Buy 1x ${long_s} / Sell 2x ${short_s} call @ ${prem:.2f} net debit",
        "CALL_SPREAD":  f"Buy ${long_s} / Sell ${short_s} call spread @ ${prem:.2f} debit",
        "NAKED_CALL":   f"Buy ${long_s} ATM call @ ${prem:.2f}",
    }
    trade_desc = struct_labels.get(struct, f"Buy ${long_s} call @ ${prem:.2f}")

    warnings = []
    if iv > 0.6:       warnings.append(f"High IV ({iv:.0%}) -- premium inflated.")
    if prob < 0.35:    warnings.append("Low probability -- reduce size or skip.")
    if score < 6.5:    warnings.append("Below conviction threshold.")
    if struct == "RATIO_SPREAD": warnings.append(f"Loss accelerates above ${suggestion.get('blowout_price','?')} -- only valid VCS<=3.")
    if struct == "OTM_CALL":     warnings.append("Close at T1. Do not hold to expiry -- theta accelerates last 2 weeks.")
    if vcs > 6:        warnings.append(f"VCS {vcs} is loose -- consider waiting for tighter base.")

    rationale = (
        f"{trade_desc}, expiring {chain.get('expiry', expiry_data['dte_label'])}. "
        f"P(reach T1) = {prob:.0%} -> EV = ${ev_val:.2f}/contract. "
        f"Size: {size_pct:.1f}% portfolio ({suggestion.get('contracts',1)} contract(s), "
        f"${suggestion.get('cost',0):.0f} total). "
        f"{suggestion.get('structure_reason','')}"
    )

    return {
        "ticker":             ticker,
        "status":             "ok",
        "score":              score,
        "structure_selected": struct,
        "signal_summary": {
            "price": price, "rs": signal.get("rs"), "vcs": vcs,
            "vol_ratio": vol_r, "signal_score": signal.get("signal_score"),
            "social_score": signal.get("social_score"), "sector": signal.get("sector"),
            "sector_aligned": signal.get("sector_aligned"),
            "ma_bounce": signal.get("bouncing_from"), "atr": signal.get("atr"),
            "target_1": signal.get("target_1"), "coiling": signal.get("coiling", False),
            "adr_pct":            signal.get("adr_pct"),
            "ema21_low":          signal.get("ema21_low"),
            "ema21_low_pct":      signal.get("ema21_low_pct"),
            "within_1atr_ema21":  signal.get("within_1atr_ema21"),
            "within_1atr_wema10": signal.get("within_1atr_wema10"),
            "within_3atr_sma50":  signal.get("within_3atr_sma50"),
            "three_weeks_tight":  signal.get("three_weeks_tight", False),
            "stop_price":         signal.get("stop_price"),
            "pct_from_52w_high":  signal.get("pct_from_52w_high"),
            "w52_high":           signal.get("w52_high"),
        },
        "probability":    prob_data,
        "expiry":         expiry_data,
        "suggestion":     suggestion,
        "all_evaluated": {
            "otm_call":     {"available": otm is not None,
                             "premium": otm.get("premium") if otm else None,
                             "ev": otm.get("ev") if otm else None},
            "ratio_spread": {"available": ratio is not None,
                             "premium": ratio.get("premium") if ratio else None,
                             "ev": ratio.get("ev") if ratio else None},
            "call_spread":  {"available": spread is not None,
                             "premium": (spread or {}).get("premium") or (spread or {}).get("net_debit"),
                             "ev": (spread or {}).get("ev") or (spread or {}).get("expected_value")},
        },
        "kelly_workings": kelly_workings,
        "rationale":      rationale,
        "warning":        " | ".join(warnings) if warnings else None,
        "chain_expiry":   chain.get("expiry"),
        "chain_iv":       round(iv, 3),
    }


def suggest_batch(signals: list, portfolio_value: float = 50000,
                  min_score: float = 7.0, max_suggestions: int = 10) -> list:
    candidates = sorted(
        [s for s in signals
         if (s.get("combined_score") or s.get("signal_score") or 0) >= min_score
         and s.get("price", 0) > 2],
        key=lambda x: x.get("combined_score") or x.get("signal_score") or 0,
        reverse=True
    )
    results = []
    for s in candidates[:max_suggestions]:
        try:
            results.append(suggest_trade(s, portfolio_value))
            time.sleep(0.5)
        except Exception as e:
            results.append({"ticker": s.get("ticker"), "status": "error", "error": str(e)})
    return results
