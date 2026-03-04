/**
 * RegimeGate.jsx
 * --------------
 * Shows current market regime, signal routing mode, and partial exit plan.
 * Fires a prominent banner when regime gate has changed since last scan.
 */

import { useState, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "https://market-dashboard-production-db0b.up.railway.app";

const GATE_STYLE = {
  GO:      { bg: "rgba(8,153,129,0.07)",  border: "rgba(8,153,129,0.25)",  text: "#089981", label: "GO"      },
  CAUTION: { bg: "rgba(245,166,35,0.07)", border: "rgba(245,166,35,0.25)", text: "#f5a623", label: "CAUTION" },
  WARN:    { bg: "rgba(255,152,0,0.07)",  border: "rgba(255,152,0,0.25)",  text: "#ff9800", label: "WARN"    },
  DANGER:  { bg: "rgba(242,54,69,0.07)",  border: "rgba(242,54,69,0.25)",  text: "#f23645", label: "DANGER"  },
};

const MODE_STYLE = {
  LONGS:      { label: "LONGS ACTIVE",  color: "#089981" },
  SELECTIVE:  { label: "SELECTIVE",     color: "#f5a623" },
  EXITS_ONLY: { label: "EXITS ONLY",    color: "#ff9800" },
  SHORTS:     { label: "SHORTS ONLY",   color: "#f23645" },
};

function ScoreBar({ score }) {
  const col = score >= 65 ? "#089981" : score >= 50 ? "#f5a623" : score >= 35 ? "#ff9800" : "#f23645";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 100, height: 5, background: "var(--bg3)", borderRadius: 3, position: "relative", flexShrink: 0 }}>
        <div style={{
          position: "absolute", left: 0, top: 0, bottom: 0,
          width: `${score}%`, borderRadius: 3,
          background: `linear-gradient(90deg, #f23645, #ff9800, #f5a623, ${col})`,
          transition: "width 0.5s ease",
        }} />
        {[35, 50, 65].map(t => (
          <div key={t} style={{
            position: "absolute", top: -2, bottom: -2, left: `${t}%`,
            width: 1, background: "rgba(0,0,0,0.15)",
          }} />
        ))}
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color: col }}>{score}</span>
    </div>
  );
}

function Pill({ label, color }) {
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
      letterSpacing: 0.5, whiteSpace: "nowrap",
      background: `${color}12`, color, border: `1px solid ${color}30`,
    }}>
      {label}
    </span>
  );
}

function PartialExitPlan({ plan }) {
  const [open, setOpen] = useState(false);
  if (!plan || plan.length === 0) return null;
  const PHASE_COLORS = ["#787b86", "#089981", "#f5a623", "#2962ff"];
  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: "none", border: "none", cursor: "pointer",
          fontSize: 9, color: "#787b86", letterSpacing: 0.5,
          padding: 0, fontFamily: "inherit",
          display: "flex", alignItems: "center", gap: 4,
        }}
      >
        {open ? "▲" : "▼"} PARTIAL EXIT PLAN
      </button>
      {open && (
        <div style={{
          marginTop: 6,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
          gap: 6,
        }}>
          {plan.map((p, i) => (
            <div key={i} style={{
              padding: "7px 9px", borderRadius: 3,
              background: "var(--bg2)", border: "1px solid var(--border)",
              borderLeft: `3px solid ${PHASE_COLORS[i] || "#787b86"}`,
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: PHASE_COLORS[i], letterSpacing: 0.5, marginBottom: 3 }}>
                {p.label}
              </div>
              <div style={{ fontSize: 9, color: "var(--text)", marginBottom: 2 }}>{p.action}</div>
              <div style={{ fontSize: 8, color: "var(--text3)" }}>Stop: {p.stop}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RegimeChangeBanner({ oldGate, newGate }) {
  const [visible, setVisible] = useState(true);
  if (!visible || !oldGate || oldGate === newGate) return null;
  const improving = (
    (oldGate === "DANGER"  && ["WARN","CAUTION","GO"].includes(newGate)) ||
    (oldGate === "WARN"    && ["CAUTION","GO"].includes(newGate)) ||
    (oldGate === "CAUTION" && newGate === "GO")
  );
  const color = improving ? "#089981" : "#f23645";
  return (
    <div style={{
      padding: "8px 12px", borderRadius: 3, marginBottom: 8,
      background: improving ? "rgba(8,153,129,0.06)" : "rgba(242,54,69,0.06)",
      border: `1px solid ${color}40`,
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
    }}>
      <span style={{ fontSize: 10, fontWeight: 700, color }}>
        {improving ? "🟢" : "🔴"} REGIME CHANGE: {oldGate} → {newGate}
      </span>
      <button onClick={() => setVisible(false)} style={{
        background: "none", border: "none", cursor: "pointer",
        fontSize: 11, color: "var(--text3)", padding: 0,
      }}>×</button>
    </div>
  );
}

export default function RegimeGate({ onGate, compact = false }) {
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/regime/gate`)
      .then(r => r.json())
      .then(d => { setData(d); onGate && onGate(d); })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: "6px 10px", fontSize: 9, color: "var(--text3)", letterSpacing: 1 }}>
      LOADING REGIME...
    </div>
  );
  if (!data) return null;

  const {
    gate, score, mode, vix, vix_label, vix_warning,
    gate_msg, breadth_50ma_pct, size_multiplier,
    indices, partial_exit_plan, gate_changed, previous_gate,
  } = data;

  const C   = GATE_STYLE[gate]  || GATE_STYLE.CAUTION;
  const M   = MODE_STYLE[mode]  || { label: mode, color: "#787b86" };
  const vixCol = vix > 35 ? "#f23645" : vix > 25 ? "#ff9800" : vix > 20 ? "#f5a623" : "#089981";

  if (compact) {
    return (
      <div style={{
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
        padding: "5px 10px", borderRadius: 3,
        background: C.bg, border: `1px solid ${C.border}`,
        marginBottom: 10,
      }}>
        <span style={{ fontSize: 9, fontWeight: 700, color: C.text, letterSpacing: 1 }}>{C.label}</span>
        <ScoreBar score={score} />
        <Pill label={M.label} color={M.color} />
        {vix != null && <Pill label={`VIX ${vix?.toFixed(1)}`} color={vixCol} />}
        {size_multiplier < 1 && <Pill label={`SIZE ×${size_multiplier}`} color="#ff9800" />}
        <span style={{ fontSize: 9, color: "var(--text3)", flex: 1 }}>{gate_msg}</span>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 14 }}>
      {gate_changed && <RegimeChangeBanner oldGate={previous_gate} newGate={gate} />}

      <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 4, padding: "12px 14px" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, color: C.text, letterSpacing: 1,
            padding: "2px 8px", borderRadius: 2,
            background: `${C.text}12`, border: `1px solid ${C.text}25`,
          }}>
            REGIME {C.label}
          </span>
          <ScoreBar score={score} />
          <span style={{
            fontSize: 10, fontWeight: 700, color: M.color,
            padding: "2px 8px", borderRadius: 2,
            background: `${M.color}10`, border: `1px solid ${M.color}25`,
            letterSpacing: 0.5,
          }}>
            {M.label}
          </span>
          {size_multiplier < 1 && <Pill label={`SIZE ×${size_multiplier}`} color="#ff9800" />}
          {vix != null && <Pill label={`VIX ${vix?.toFixed(1)} — ${vix_label || ""}`} color={vixCol} />}
          {breadth_50ma_pct != null && (
            <Pill
              label={`BREADTH ${breadth_50ma_pct?.toFixed(0)}%`}
              color={breadth_50ma_pct > 60 ? "#089981" : breadth_50ma_pct > 40 ? "#f5a623" : "#f23645"}
            />
          )}
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              marginLeft: "auto", fontSize: 9, color: "var(--text3)",
              background: "none", border: "none", cursor: "pointer",
              letterSpacing: 0.5, fontFamily: "inherit",
            }}
          >
            {expanded ? "▲ LESS" : "▼ MORE"}
          </button>
        </div>

        <div style={{ fontSize: 10, color: "var(--text2)" }}>{gate_msg}</div>
        {vix_warning && (
          <div style={{ fontSize: 9, color: "#ff9800", marginTop: 4 }}>⚠ {vix_warning}</div>
        )}

        <PartialExitPlan plan={partial_exit_plan} />

        {expanded && (
          <div style={{ marginTop: 12 }}>
            {/* Threshold legend */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 12 }}>
              {[
                { gate: "DANGER",  range: "< 35",  mode: "SHORTS",     desc: "Close longs" },
                { gate: "WARN",    range: "35–49", mode: "EXITS ONLY", desc: "No new longs" },
                { gate: "CAUTION", range: "50–64", mode: "SELECTIVE",  desc: "Size ×0.75"  },
                { gate: "GO",      range: "≥ 65",  mode: "LONGS",      desc: "Full size"   },
              ].map(t => {
                const tc = GATE_STYLE[t.gate];
                const active = t.gate === gate;
                return (
                  <div key={t.gate} style={{
                    padding: "7px 9px", borderRadius: 3,
                    background: active ? `${tc.text}10` : "var(--bg2)",
                    border: `1px solid ${active ? tc.text + "40" : "var(--border)"}`,
                  }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: tc.text }}>{t.gate}</div>
                    <div style={{ fontSize: 9, color: "var(--text2)" }}>{t.range}</div>
                    <div style={{ fontSize: 9, color: "var(--text3)" }}>{t.mode}</div>
                    <div style={{ fontSize: 8, color: "var(--text3)" }}>{t.desc}</div>
                  </div>
                );
              })}
            </div>

            {/* Index health */}
            {indices && Object.keys(indices).length > 0 && (
              <div>
                <div style={{ fontSize: 9, fontWeight: 600, color: "var(--text3)", letterSpacing: 1, marginBottom: 6 }}>
                  INDEX HEALTH
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6 }}>
                  {Object.entries(indices).map(([ticker, d]) => (
                    <div key={ticker} style={{
                      padding: "5px 7px", borderRadius: 3,
                      background: d.above_ma200 ? "rgba(8,153,129,0.06)" : "rgba(242,54,69,0.06)",
                      border: `1px solid ${d.above_ma200 ? "rgba(8,153,129,0.2)" : "rgba(242,54,69,0.2)"}`,
                    }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: d.above_ma200 ? "#089981" : "#f23645" }}>
                        {ticker}
                      </div>
                      <div style={{ fontSize: 8, color: "var(--text3)" }}>{d.above_ma200 ? "↑ MA200" : "↓ MA200"}</div>
                      <div style={{ fontSize: 9, color: (d.dist_from_200ma ?? 0) >= 0 ? "#089981" : "#f23645" }}>
                        {(d.dist_from_200ma ?? 0) >= 0 ? "+" : ""}{d.dist_from_200ma?.toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
