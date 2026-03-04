import React, { useState, useCallback, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "";

// ── Palette ───────────────────────────────────────────────────────────────────
const C = {
  bg:      "var(--bg)",
  bg2:     "var(--bg2)",
  bg3:     "var(--bg3)",
  border:  "var(--border)",
  border2: "var(--border2)",
  green:   "var(--green)",
  red:     "var(--red)",
  amber:   "var(--yellow)",
  blue:    "var(--cyan)",
  purple:  "var(--purple)",
  text:    "var(--text)",
  text2:   "var(--text2)",
  text3:   "var(--text3)",
};

const pr  = (v, dp=2) => v == null ? "—" : `$${Number(v).toFixed(dp)}`;
const pct = (v, dp=1) => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(dp)}%`;

// ── Base styles ───────────────────────────────────────────────────────────────
const S = {
  page: {
    background: C.bg, minHeight: "100vh", color: C.text,
    fontFamily: "'Inter', -apple-system, sans-serif", fontSize: 12,
    padding: "0 0 60px",
  },
  header: {
    background: C.bg2, borderBottom: `1px solid ${C.border}`,
    padding: "16px 24px", display: "flex", alignItems: "center",
    justifyContent: "space-between", position: "sticky", top: 0, zIndex: 100,
  },
  logo: {
    fontFamily: "'Inter', -apple-system, sans-serif", fontSize: 11,
    letterSpacing: 4, color: C.green, fontWeight: 700,
    textTransform: "uppercase",
  },
  body: { display: "flex", gap: 0, height: "calc(100vh - 53px)" },
  panel: {
    background: C.bg2, borderRight: `1px solid ${C.border}`,
    padding: "20px 18px", overflowY: "auto", width: 300, flexShrink: 0,
  },
  main: { flex: 1, overflowY: "auto", padding: "20px 24px" },
  label: { fontSize: 9, color: C.text3, letterSpacing: 2, textTransform: "uppercase", marginBottom: 4 },
  input: {
    width: "100%", background: C.bg3, border: `1px solid ${C.border2}`,
    color: C.text, padding: "7px 10px", borderRadius: 3,
    fontFamily: "inherit", fontSize: 12, boxSizing: "border-box",
    outline: "none",
  },
  inputFocus: { borderColor: C.green },
  btn: (col=C.green, fill=false) => ({
    padding: "8px 16px", fontSize: 10, cursor: "pointer", borderRadius: 3,
    border: `1px solid ${col}`,
    background: fill ? col : "transparent",
    color: fill ? "#000" : col,
    fontFamily: "inherit", letterSpacing: 1, fontWeight: 700,
    textTransform: "uppercase", transition: "all 0.15s",
  }),
  fieldGroup: { marginBottom: 14 },
  divider: { borderTop: `1px solid ${C.border}`, margin: "16px 0" },
  card: {
    background: C.bg3, border: `1px solid ${C.border}`,
    borderRadius: 4, padding: "14px 16px", marginBottom: 10,
  },
  tag: (col) => ({
    fontSize: 8, fontWeight: 700, padding: "2px 7px", borderRadius: 2,
    background: `${col}22`, color: col, border: `1px solid ${col}44`,
    letterSpacing: 1, textTransform: "uppercase",
  }),
};

// ── Input field ───────────────────────────────────────────────────────────────
function Field({ label, value, onChange, type="text", placeholder="", step, min, max, suffix }) {
  const [focus, setFocus] = useState(false);
  return (
    <div style={S.fieldGroup}>
      <div style={S.label}>{label}</div>
      <div style={{ position: "relative" }}>
        <input
          type={type} value={value} step={step} min={min} max={max}
          placeholder={placeholder}
          onChange={e => onChange(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          style={{ ...S.input, ...(focus ? { borderColor: C.green } : {}), paddingRight: suffix ? 30 : 10 }}
        />
        {suffix && (
          <span style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: C.text3, fontSize: 11 }}>
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Probability slider ────────────────────────────────────────────────────────
function ProbSlider({ value, onChange, marketProb }) {
  return (
    <div style={S.fieldGroup}>
      <div style={{ ...S.label, display: "flex", justifyContent: "space-between" }}>
        <span>Your P(ITM) estimate</span>
        <span style={{ color: C.green, fontSize: 10 }}>{Math.round(value * 100)}%</span>
      </div>
      <input
        type="range" min="0.05" max="0.95" step="0.01"
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: C.green, cursor: "pointer" }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        <span style={{ fontSize: 9, color: C.text3 }}>5%</span>
        {marketProb && (
          <span style={{ fontSize: 9, color: C.amber }}>
            Market delta: {Math.round(marketProb * 100)}%
          </span>
        )}
        <span style={{ fontSize: 9, color: C.text3 }}>95%</span>
      </div>
      {marketProb && (
        <div style={{ marginTop: 6, fontSize: 10, color: value > marketProb ? C.green : C.red }}>
          {value > marketProb
            ? `↑ You're ${Math.round((value - marketProb) * 100)}% more bullish than market`
            : `↓ You're ${Math.round((marketProb - value) * 100)}% less bullish than market`}
        </div>
      )}
    </div>
  );
}

// ── Kelly gauge ───────────────────────────────────────────────────────────────
function KellyGauge({ fullKelly, fracKelly, recUsd, contracts, maxLossPct }) {
  const pct_used = Math.min(100, fracKelly);
  const col = fracKelly > 5 ? C.green : fracKelly > 2 ? C.amber : C.red;

  return (
    <div style={{ ...S.card, borderColor: `${col}44` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ fontSize: 9, color: C.text3, letterSpacing: 2 }}>KELLY SIZING</div>
        <div style={S.tag(col)}>¼ Kelly</div>
      </div>

      {/* Gauge bar */}
      <div style={{ height: 6, background: C.bg, borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
        <div style={{ width: `${pct_used * 10}%`, height: "100%", background: col, borderRadius: 3, transition: "width 0.4s" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {[
          ["Full Kelly",     `${fullKelly?.toFixed(1)}%`],
          ["¼ Kelly bet",    `${fracKelly?.toFixed(1)}%`],
          ["Rec. position",  pr(recUsd)],
          ["Est. contracts", contracts],
        ].map(([label, val]) => (
          <div key={label}>
            <div style={S.label}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: col }}>{val}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 10, fontSize: 10, color: C.text3 }}>
        Max loss cap: {maxLossPct}% of portfolio
      </div>
    </div>
  );
}

// ── Spread card ───────────────────────────────────────────────────────────────
function SpreadCard({ spread, spot, direction, selected, onSelect }) {
  const isGood  = spread.ev_edge > 0;
  const rr      = spread.reward_risk;
  const edgeCol = spread.ev_edge > 0.1 ? C.green : spread.ev_edge > 0 ? C.amber : C.red;

  return (
    <div
      onClick={() => onSelect(spread)}
      style={{
        ...S.card,
        cursor: "pointer",
        borderColor: selected ? C.green : isGood ? `${C.green}44` : C.border,
        borderWidth: selected ? 2 : 1,
        transition: "all 0.15s",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Left accent bar */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        background: isGood ? C.green : C.red,
      }} />

      <div style={{ paddingLeft: 8 }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
            {direction === "call" ? "📈" : "📉"} ${spread.long_strike} / ${spread.short_strike}
            <span style={{ fontSize: 10, color: C.text3, marginLeft: 8 }}>
              {direction === "call" ? "Call Spread" : "Put Spread"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <span style={S.tag(edgeCol)}>EV edge {spread.ev_edge >= 0 ? "+" : ""}{spread.ev_edge?.toFixed(2)}</span>
            {rr >= 2 && <span style={S.tag(C.purple)}>R/R {rr?.toFixed(1)}x</span>}
          </div>
        </div>

        {/* Key metrics grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 12 }}>
          {[
            ["Net debit",   pr(spread.net_debit),    C.text],
            ["Max profit",  pr(spread.max_profit),   C.green],
            ["Max loss",    pr(spread.max_loss),     C.red],
            ["Breakeven",   pr(spread.breakeven),    C.amber],
          ].map(([label, val, col]) => (
            <div key={label}>
              <div style={S.label}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: col }}>{val}</div>
            </div>
          ))}
        </div>

        {/* Probability comparison */}
        <div style={{ background: C.bg, borderRadius: 3, padding: "8px 10px", marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 9, color: C.text3, letterSpacing: 1 }}>PROBABILITY ANALYSIS</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            {[
              ["Your P(ITM)",    `${spread.user_prob_itm}%`,  C.green],
              ["Market delta",   `${spread.market_prob}%`,    C.text2],
              ["P(max profit)",  `${spread.user_prob_max}%`,  C.purple],
            ].map(([label, val, col]) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={S.label}>{label}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: col }}>{val}</div>
              </div>
            ))}
          </div>
        </div>

        {/* EV comparison */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div style={{ background: `${C.green}11`, border: `1px solid ${C.green}33`, borderRadius: 3, padding: "8px 10px" }}>
            <div style={S.label}>Your EV (per contract)</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.green }}>
              {spread.user_ev >= 0 ? "+" : ""}{pr(spread.user_ev * 100)}
            </div>
          </div>
          <div style={{ background: `${C.text3}11`, border: `1px solid ${C.border}`, borderRadius: 3, padding: "8px 10px" }}>
            <div style={S.label}>Market EV (per contract)</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.text2 }}>
              {spread.market_ev >= 0 ? "+" : ""}{pr(spread.market_ev * 100)}
            </div>
          </div>
        </div>

        {/* IV info */}
        <div style={{ marginTop: 10, display: "flex", gap: 16, fontSize: 10, color: C.text3 }}>
          <span>Long IV: {spread.long_iv ? `${(spread.long_iv * 100).toFixed(0)}%` : "—"}</span>
          <span>Short IV: {spread.short_iv ? `${(spread.short_iv * 100).toFixed(0)}%` : "—"}</span>
          <span>Width: ${spread.spread_width}</span>
        </div>
      </div>
    </div>
  );
}

// ── Options chain table ───────────────────────────────────────────────────────
function ChainTable({ calls, puts, spot, direction }) {
  const opts  = direction === "call" ? calls : puts;
  const neark = spot;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border2}` }}>
            {["Strike", "Bid", "Ask", "Mid", "IV", "Delta", "Vol", "OI", "Vol/OI"].map(h => (
              <th key={h} style={{ padding: "6px 10px", textAlign: "right", color: C.text3, fontSize: 9, letterSpacing: 1, fontWeight: 400 }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {opts.map(o => {
            const isAtm  = Math.abs(o.strike - neark) < neark * 0.015;
            const isItm  = direction === "call" ? o.strike < neark : o.strike > neark;
            const rowBg  = isAtm ? `${C.amber}15` : isItm ? `${C.green}08` : "transparent";
            const isHighVol = o.vol_oi && o.vol_oi > 2;
            return (
              <tr key={o.strike} style={{ background: rowBg, borderBottom: `1px solid ${C.border}22` }}>
                <td style={{ padding: "5px 10px", fontWeight: 700, color: isAtm ? C.amber : C.text }}>
                  {pr(o.strike, 1)}
                  {isAtm && <span style={{ fontSize: 8, color: C.amber, marginLeft: 4 }}>ATM</span>}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: C.text2 }}>{pr(o.bid)}</td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: C.text2 }}>{pr(o.ask)}</td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: C.text, fontWeight: 600 }}>{pr(o.mid)}</td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: o.iv > 0.5 ? C.red : C.text2 }}>
                  {o.iv ? `${(o.iv * 100).toFixed(0)}%` : "—"}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: C.blue }}>{o.delta ?? "—"}</td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: isHighVol ? C.amber : C.text2 }}>
                  {o.volume?.toLocaleString() || "—"}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: C.text3 }}>
                  {o.oi?.toLocaleString() || "—"}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: isHighVol ? C.red : C.text3, fontWeight: isHighVol ? 700 : 400 }}>
                  {o.vol_oi ?? "—"}
                  {isHighVol && " 🔥"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Signal prefill banner ─────────────────────────────────────────────────────
function PrefillBanner({ signal, onDismiss }) {
  if (!signal) return null;
  return (
    <div style={{
      background: `${C.green}15`, border: `1px solid ${C.green}44`,
      borderRadius: 4, padding: "10px 14px", marginBottom: 16,
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <div>
        <div style={{ fontSize: 9, color: C.green, letterSpacing: 2, marginBottom: 2 }}>SIGNAL PRE-FILLED</div>
        <div style={{ fontSize: 12, color: C.text }}>
          <strong>{signal.ticker}</strong> — {signal.signal_type} · RS {signal.rs} · Score {signal.signal_score}
        </div>
      </div>
      <button style={S.btn(C.text3)} onClick={onDismiss}>✕</button>
    </div>
  );
}

// ── Main Options Desk ─────────────────────────────────────────────────────────
export default function OptionsDesk({ prefillSignal, onPrefillConsumed }) {
  // Form state
  const [ticker,     setTicker]     = useState("");
  const [direction,  setDirection]  = useState("call");
  const [expiryIdx,  setExpiryIdx]  = useState(1);  // default: next expiry
  const [userProb,   setUserProb]   = useState(0.35);
  const [priceTarget,setPriceTarget] = useState("");
  const [portfolio,  setPortfolio]  = useState("10000");
  const [maxLoss,    setMaxLoss]    = useState("2.5");
  const [viewMode,   setViewMode]   = useState("spreads"); // spreads | chain

  // Data state
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [chain,      setChain]      = useState(null);
  const [spreads,    setSpreads]    = useState(null);
  const [selected,   setSelected]   = useState(null);
  const [expiries,   setExpiries]   = useState([]);
  const [signal,     setSignal]     = useState(null);

  // Prefill from signal card
  useEffect(() => {
    if (prefillSignal) {
      setTicker(prefillSignal.ticker || "");
      setDirection(prefillSignal.direction || "call");
      if (prefillSignal.target_1) setPriceTarget(String(prefillSignal.target_1));
      setSignal(prefillSignal);
      onPrefillConsumed?.();
    }
  }, [prefillSignal, onPrefillConsumed]);

  // Load expiries when ticker changes
  const loadExpiries = useCallback(async (t) => {
    if (!t || t.length < 1) return;
    try {
      const res  = await fetch(`${API}/api/options-expiries/${t.toUpperCase()}`);
      const data = await res.json();
      if (data.expiries) {
        setExpiries(data.expiries);
        if (data.spot && !priceTarget) {
          setPriceTarget((data.spot * 1.08).toFixed(2));
        }
      }
    } catch {}
  }, [priceTarget]);

  const handleTickerBlur = () => {
    if (ticker.length >= 1) loadExpiries(ticker);
  };

  const handleAnalyse = useCallback(async () => {
    if (!ticker || !priceTarget) return;
    setLoading(true);
    setError(null);
    setSpreads(null);
    setSelected(null);

    try {
      // Fetch chain and spreads in parallel
      const [chainRes, spreadRes] = await Promise.all([
        fetch(`${API}/api/options-chain/${ticker.toUpperCase()}?expiry_index=${expiryIdx}`),
        fetch(`${API}/api/options-spread`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticker:          ticker.toUpperCase(),
            expiry_index:    expiryIdx,
            direction,
            user_prob:       userProb,
            price_target:    parseFloat(priceTarget),
            portfolio_value: parseFloat(portfolio),
            max_loss_pct:    parseFloat(maxLoss),
          }),
        }),
      ]);

      const chainData  = await chainRes.json();
      const spreadData = await spreadRes.json();

      if (chainData.detail)  throw new Error(chainData.detail);
      if (spreadData.detail) throw new Error(spreadData.detail);

      setChain(chainData);
      setSpreads(spreadData);
      if (spreadData.spreads?.length > 0) setSelected(spreadData.spreads[0]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ticker, direction, expiryIdx, userProb, priceTarget, portfolio, maxLoss]);

  const atm = chain?.calls?.find(c => Math.abs(c.strike - chain.spot) < chain.spot * 0.02);
  const marketDelta = direction === "call" ? (atm?.delta || null) : null;

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <div style={S.logo}>Options Desk</div>
        <div style={{ display: "flex", gap: 20, fontSize: 10, color: C.text3 }}>
          {chain && (
            <>
              <span>{chain.ticker} <strong style={{ color: C.text }}>{pr(chain.spot)}</strong></span>
              <span>Expiry: <strong style={{ color: C.amber }}>{chain.expiry}</strong> ({chain.dte}d)</span>
              <span style={{ color: C.text2 }}>Black-Scholes IV · ¼ Kelly sizing</span>
            </>
          )}
        </div>
      </div>

      <div style={S.body}>
        {/* ── Left panel: inputs ── */}
        <div style={S.panel}>
          <PrefillBanner signal={signal} onDismiss={() => setSignal(null)} />

          {/* Ticker */}
          <Field label="Ticker" value={ticker} onChange={v => setTicker(v.toUpperCase())}
            placeholder="e.g. NVDA" />
          <div onBlur={handleTickerBlur} style={{ marginTop: -8 }} />

          {/* Direction */}
          <div style={S.fieldGroup}>
            <div style={S.label}>Direction</div>
            <div style={{ display: "flex", gap: 6 }}>
              {["call", "put"].map(d => (
                <button key={d} style={{ ...S.btn(d === "call" ? C.green : C.red, direction === d), flex: 1 }}
                  onClick={() => setDirection(d)}>
                  {d === "call" ? "▲ BULL" : "▼ BEAR"}
                </button>
              ))}
            </div>
          </div>

          {/* Expiry */}
          {expiries.length > 0 ? (
            <div style={S.fieldGroup}>
              <div style={S.label}>Expiry date</div>
              <select
                value={expiryIdx}
                onChange={e => setExpiryIdx(parseInt(e.target.value))}
                style={{ ...S.input }}
              >
                {expiries.map((exp, i) => {
                  const dte = Math.round((new Date(exp) - new Date()) / 86400000);
                  return <option key={exp} value={i}>{exp} ({dte}d)</option>;
                })}
              </select>
            </div>
          ) : (
            <Field label="Expiry (0=nearest)" value={expiryIdx}
              onChange={v => setExpiryIdx(parseInt(v) || 0)} type="number" min="0" max="10" />
          )}

          <div style={S.divider} />

          {/* Probability slider */}
          <ProbSlider value={userProb} onChange={setUserProb} marketProb={marketDelta} />

          {/* Price target */}
          <Field
            label={direction === "call" ? "Price target (upside)" : "Price target (downside)"}
            value={priceTarget} onChange={setPriceTarget}
            type="number" step="0.50" placeholder={chain ? `Spot: ${pr(chain.spot)}` : "e.g. 550.00"}
            suffix="$"
          />

          <div style={S.divider} />

          {/* Portfolio sizing */}
          <Field label="Portfolio value ($)" value={portfolio} onChange={setPortfolio}
            type="number" step="1000" suffix="$" />
          <Field label="Max loss per trade (%)" value={maxLoss} onChange={setMaxLoss}
            type="number" step="0.5" min="0.5" max="10" suffix="%" />

          <div style={S.divider} />

          <button
            style={{ ...S.btn(C.green, true), width: "100%", padding: "10px", fontSize: 11 }}
            onClick={handleAnalyse}
            disabled={loading || !ticker}
          >
            {loading ? "Analysing..." : "▶ Analyse"}
          </button>

          {error && (
            <div style={{ marginTop: 10, padding: "8px 10px", background: `${C.red}15`, border: `1px solid ${C.red}44`, borderRadius: 3, fontSize: 10, color: C.red }}>
              {error}
            </div>
          )}
        </div>

        {/* ── Right: results ── */}
        <div style={S.main}>
          {!spreads && !chain && !loading && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60%", color: C.text3 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>⚡</div>
              <div style={{ fontSize: 14, marginBottom: 8, color: C.text2 }}>Options Desk</div>
              <div style={{ fontSize: 11, textAlign: "center", maxWidth: 320, lineHeight: 1.6 }}>
                Enter a ticker, set your probability estimate and price target,
                then hit Analyse to find the best spread and Kelly sizing.
              </div>
              <div style={{ marginTop: 20, fontSize: 10, color: C.text3 }}>
                Based on dpg's framework: Convexity · Edge · Risk Management
              </div>
            </div>
          )}

          {loading && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60%", flexDirection: "column", gap: 12 }}>
              <div style={{ fontSize: 11, color: C.green, letterSpacing: 2 }}>FETCHING CHAIN...</div>
              <div style={{ fontSize: 10, color: C.text3 }}>Live data from Yahoo Finance · Running Black-Scholes</div>
            </div>
          )}

          {spreads && chain && (
            <>
              {/* View toggle */}
              <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
                {[["spreads", "Best Spreads"], ["chain", "Full Chain"]].map(([key, label]) => (
                  <button key={key} style={S.btn(C.green, viewMode === key)} onClick={() => setViewMode(key)}>
                    {label}
                  </button>
                ))}
                <div style={{ marginLeft: "auto", fontSize: 10, color: C.text3, alignSelf: "center" }}>
                  {spreads.total_found} combinations evaluated ·
                  Live prices {chain.ticker} {pr(chain.spot)} ·
                  Exp {chain.expiry} ({chain.dte}d)
                </div>
              </div>

              {viewMode === "spreads" && (
                <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 300px" : "1fr", gap: 16 }}>
                  {/* Spread list */}
                  <div>
                    {spreads.spreads.length === 0 ? (
                      <div style={{ color: C.text3, padding: "20px 0" }}>
                        No spreads found with positive EV at these settings. Try lowering your price target or adjusting probability.
                      </div>
                    ) : (
                      spreads.spreads.map((sp, i) => (
                        <SpreadCard
                          key={`${sp.long_strike}-${sp.short_strike}`}
                          spread={sp} spot={chain.spot}
                          direction={direction}
                          selected={selected === sp}
                          onSelect={setSelected}
                        />
                      ))
                    )}
                  </div>

                  {/* Selected detail / Kelly panel */}
                  {selected && (
                    <div>
                      <div style={{ ...S.card, borderColor: `${C.green}44` }}>
                        <div style={{ fontSize: 9, color: C.text3, letterSpacing: 2, marginBottom: 12 }}>SELECTED TRADE</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: C.green, marginBottom: 4 }}>
                          ${selected.long_strike} / ${selected.short_strike} {direction.toUpperCase()} SPREAD
                        </div>
                        <div style={{ fontSize: 10, color: C.text3, marginBottom: 12 }}>
                          Expiry {chain.expiry} · {chain.dte} DTE
                        </div>

                        {/* Trade execution grid */}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                          {[
                            ["Buy",        `${direction === "call" ? "CALL" : "PUT"} $${selected.long_strike}`,  C.green],
                            ["Sell",       `${direction === "call" ? "CALL" : "PUT"} $${selected.short_strike}`, C.red],
                            ["Pay (mid)",  pr(selected.net_debit),  C.text],
                            ["Bid/ask",    `${pr(selected.long_bid)}/${pr(selected.long_ask)}`, C.text2],
                          ].map(([label, val, col]) => (
                            <div key={label} style={{ background: C.bg, borderRadius: 3, padding: "8px" }}>
                              <div style={S.label}>{label}</div>
                              <div style={{ fontSize: 12, fontWeight: 700, color: col }}>{val}</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <KellyGauge
                        fullKelly={selected.kelly_full}
                        fracKelly={selected.kelly_frac}
                        recUsd={selected.rec_usd}
                        contracts={selected.rec_contracts}
                        maxLossPct={parseFloat(maxLoss)}
                      />

                      {/* Dpg checklist */}
                      <div style={{ ...S.card }}>
                        <div style={{ fontSize: 9, color: C.text3, letterSpacing: 2, marginBottom: 10 }}>DPG CHECKLIST</div>
                        {[
                          [selected.reward_risk >= 1.5,        `Convexity: R/R ${selected.reward_risk?.toFixed(1)}x ${selected.reward_risk >= 1.5 ? "✓" : "✗ (need ≥1.5x)"}`],
                          [selected.ev_edge > 0,               `Edge: EV edge ${selected.ev_edge >= 0 ? "+" : ""}${selected.ev_edge?.toFixed(2)} vs market`],
                          [selected.kelly_frac >= 1,           `Kelly: ¼ Kelly = ${selected.kelly_frac?.toFixed(1)}% ${selected.kelly_frac >= 1 ? "✓" : "✗ (edge too thin)"}`],
                          [selected.user_prob_itm > selected.market_prob, `Your P(${selected.user_prob_itm}%) > market P(${selected.market_prob}%) ${selected.user_prob_itm > selected.market_prob ? "✓" : "✗"}`],
                        ].map(([pass, text]) => (
                          <div key={text} style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 10 }}>
                            <span style={{ color: pass ? C.green : C.red, flexShrink: 0 }}>{pass ? "●" : "○"}</span>
                            <span style={{ color: pass ? C.text : C.text3 }}>{text}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {viewMode === "chain" && (
                <div>
                  <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                    {["call", "put"].map(d => (
                      <button key={d} style={S.btn(d === "call" ? C.green : C.red, direction === d)}
                        onClick={() => setDirection(d)}>
                        {d === "call" ? "Calls" : "Puts"}
                      </button>
                    ))}
                    <span style={{ marginLeft: 8, fontSize: 10, color: C.text3, alignSelf: "center" }}>
                      🔥 = unusual vol/OI · <span style={{ color: C.amber }}>ATM highlighted</span>
                    </span>
                  </div>
                  <ChainTable
                    calls={chain.calls} puts={chain.puts}
                    spot={chain.spot} direction={direction}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
