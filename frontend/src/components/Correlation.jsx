import React, { useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

// ── helpers ───────────────────────────────────────────────────────────────────
const fmt  = (v, d = 2) => v == null ? "—" : Number(v).toFixed(d);
const fmtK = v => v == null ? "—" : v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v.toFixed(0)}`;
const fmtR = v => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}R`;
const fmtPct = v => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(1)}%`;

// ── colour logic ──────────────────────────────────────────────────────────────
const gateCol  = g => ({ GO: "var(--green)", CAUTION: "var(--yellow)", WARN: "var(--red)", DANGER: "var(--red)" }[g] || "var(--text3)");
const gateBg   = g => ({ GO: "rgba(8,153,129,0.12)", CAUTION: "rgba(245,166,35,0.1)", WARN: "rgba(242,54,69,0.08)", DANGER: "rgba(242,54,69,0.12)" }[g] || "transparent");
const rCol     = v => v >= 1.5 ? "var(--green)" : v >= 0.5 ? "#5bc27a" : v >= 0 ? "var(--yellow)" : "var(--red)";
const wrCol    = v => v >= 60 ? "var(--green)" : v >= 45 ? "var(--yellow)" : "var(--red)";
const pfCol    = v => v >= 1.5 ? "var(--green)" : v >= 1.0 ? "var(--yellow)" : "var(--red)";
const eqCol    = v => v >= 10000 ? "var(--green)" : "var(--red)";
const readyStars = n => "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));

const GATE_ORDER = { GO: 0, CAUTION: 1, WARN: 2, DANGER: 3, UNKNOWN: 4 };

const TD = { padding: "6px 10px", borderBottom: "1px solid var(--border)", fontSize: 11, whiteSpace: "nowrap" };
const TH = { padding: "6px 10px", borderBottom: "2px solid var(--border)", fontSize: 9, letterSpacing: 1,
  textTransform: "uppercase", color: "var(--text3)", fontWeight: 700, background: "var(--bg2)", whiteSpace: "nowrap" };

// ── Recommended rules derived from cross_tab ──────────────────────────────────
function deriveRules(crossTab) {
  if (!crossTab || crossTab.length === 0) return [];
  const rules = [];
  // Group by gate
  const byGate = {};
  crossTab.forEach(row => {
    if (!byGate[row.regime_gate]) byGate[row.regime_gate] = [];
    byGate[row.regime_gate].push(row);
  });

  for (const [gate, rows] of Object.entries(byGate)) {
    // Find minimum readiness with positive expectancy and >40% win rate
    const viable = rows.filter(r => r.expectancy > 0 && r.win_rate >= 40 && r.trades >= 3)
                       .sort((a, b) => a.readiness - b.readiness);
    const best   = rows.filter(r => r.trades >= 3).sort((a, b) => b.expectancy - a.expectancy)[0];

    if (viable.length > 0) {
      const minR = viable[0].readiness;
      rules.push({
        gate,
        action: "TAKE",
        rule: `Take signals with Readiness ≥ ${minR}★`,
        detail: `${viable.length} readiness levels viable · Best: ${best?.readiness}★ (${fmt(best?.expectancy)}R expectancy)`,
        color: "var(--green)",
      });
    } else {
      rules.push({
        gate,
        action: "SKIP",
        rule: "No viable readiness level found",
        detail: `All ${rows.length} buckets showed negative expectancy or <40% win rate`,
        color: "var(--red)",
      });
    }
  }
  rules.sort((a, b) => (GATE_ORDER[a.gate] || 9) - (GATE_ORDER[b.gate] || 9));
  return rules;
}

// ── Mini equity sparkline (SVG) ───────────────────────────────────────────────
function EquitySparkline({ curve, width = 120, height = 36 }) {
  if (!curve || curve.length < 2) return null;
  const vals  = curve.map(p => p.equity);
  const minV  = Math.min(...vals);
  const maxV  = Math.max(...vals);
  const range = maxV - minV || 1;
  const pts   = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * width;
    const y = height - ((v - minV) / range) * height;
    return `${x},${y}`;
  }).join(" ");
  const endVal  = vals[vals.length - 1];
  const color   = endVal >= 10000 ? "var(--green)" : "var(--red)";
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={(vals.length-1)/(vals.length-1)*width} cy={height-((endVal-minV)/range)*height}
        r={3} fill={color} />
    </svg>
  );
}

// ── Cross-tab matrix ──────────────────────────────────────────────────────────
function CrossTab({ crossTab }) {
  if (!crossTab || crossTab.length === 0) return (
    <div style={{ padding: 20, color: "var(--text3)", textAlign: "center" }}>No data yet.</div>
  );

  const cols = [
    { label: "REGIME",         key: "regime_gate"   },
    { label: "READY",          key: "readiness"     },
    { label: "TRADES",         key: "trades"        },
    { label: "WIN RATE",       key: "win_rate"      },
    { label: "AVG R",          key: "avg_r"         },
    { label: "TOTAL R",        key: "total_r"       },
    { label: "PROFIT FACTOR",  key: "profit_factor" },
    { label: "EXPECTANCY",     key: "expectancy"    },
    { label: "AVG HOLD",       key: "avg_days_held" },
    { label: "TRAIL %",        key: "trail_pct"     },
    { label: "VERDICT",        key: "_verdict"      },
  ];

  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 860 }}>
        <thead>
          <tr>
            {cols.map(c => <th key={c.key} style={{ ...TH, textAlign: c.key === "trades" || c.key === "win_rate" || c.key === "_verdict" ? "center" : "left" }}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {crossTab.map((row, i) => {
            const verdict = row.expectancy > 0.5 && row.win_rate >= 50
              ? { label: "✓ TAKE",  col: "var(--green)", bg: "rgba(8,153,129,0.08)" }
              : row.expectancy > 0 && row.win_rate >= 40
              ? { label: "~ SELECTIVE", col: "var(--yellow)", bg: "rgba(245,166,35,0.08)" }
              : { label: "✗ SKIP",  col: "var(--red)",   bg: "rgba(242,54,69,0.06)" };

            const base = i % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
            return (
              <tr key={i} style={{ background: base }}>
                {/* Regime */}
                <td style={{ ...TD }}>
                  <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 3,
                    fontSize: 10, fontWeight: 700, background: gateBg(row.regime_gate),
                    color: gateCol(row.regime_gate), border: `1px solid ${gateCol(row.regime_gate)}40` }}>
                    {row.regime_gate}
                  </span>
                </td>
                {/* Readiness */}
                <td style={{ ...TD, fontWeight: 700 }}>
                  <span style={{ color: row.readiness >= 4 ? "var(--green)" : row.readiness >= 3 ? "var(--yellow)" : "var(--text3)" }}>
                    {readyStars(row.readiness)} {row.readiness}
                  </span>
                </td>
                {/* Trades */}
                <td style={{ ...TD, textAlign: "center", color: row.trades < 3 ? "var(--text3)" : "var(--text)" }}>
                  {row.trades}
                  {row.trades < 3 && <span style={{ fontSize: 8, color: "var(--red)", marginLeft: 3 }}>low n</span>}
                </td>
                {/* Win rate */}
                <td style={{ ...TD, fontWeight: 700, color: wrCol(row.win_rate) }}>{fmt(row.win_rate, 1)}%</td>
                {/* Avg R */}
                <td style={{ ...TD, fontWeight: 700, color: rCol(row.avg_r) }}>{fmtR(row.avg_r)}</td>
                {/* Total R */}
                <td style={{ ...TD, color: row.total_r >= 0 ? "var(--green)" : "var(--red)" }}>{fmtR(row.total_r)}</td>
                {/* Profit factor */}
                <td style={{ ...TD, fontWeight: 700, color: pfCol(row.profit_factor) }}>
                  {row.profit_factor >= 99 ? "∞" : fmt(row.profit_factor)}
                </td>
                {/* Expectancy */}
                <td style={{ ...TD, fontWeight: 700, color: rCol(row.expectancy) }}>{fmtR(row.expectancy)}</td>
                {/* Avg hold */}
                <td style={{ ...TD, color: "var(--text2)" }}>{fmt(row.avg_days_held, 1)}d</td>
                {/* Trail % */}
                <td style={{ ...TD, color: "var(--text3)" }}>{fmt(row.trail_pct, 0)}%</td>
                {/* Verdict */}
                <td style={{ ...TD, textAlign: "center" }}>
                  <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 3,
                    fontSize: 9, fontWeight: 700, background: verdict.bg,
                    color: verdict.col, border: `1px solid ${verdict.col}40`, letterSpacing: 0.5 }}>
                    {verdict.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Equity curve chart (pure SVG, no recharts dep) ───────────────────────────
function EquityCurve({ curve }) {
  if (!curve || curve.length < 2) return null;

  const W = 900, H = 220, PAD = { t: 16, r: 20, b: 36, l: 72 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const vals  = curve.map(p => p.equity);
  const minV  = Math.min(...vals) * 0.98;
  const maxV  = Math.max(...vals) * 1.02;
  const range = maxV - minV || 1;

  const xScale = i => PAD.l + (i / (curve.length - 1)) * innerW;
  const yScale = v => PAD.t + innerH - ((v - minV) / range) * innerH;

  // Build polyline
  const pts = curve.map((p, i) => `${xScale(i)},${yScale(p.equity)}`).join(" ");

  // Y axis labels
  const yTicks = 5;
  const yLabels = Array.from({ length: yTicks }, (_, i) => {
    const v = minV + (range * i) / (yTicks - 1);
    return { v, y: yScale(v) };
  });

  // X axis labels — show week dates, max 8
  const step = Math.max(1, Math.floor(curve.length / 8));
  const xLabels = curve.filter((_, i) => i % step === 0 || i === curve.length - 1);

  // Colour each segment
  const segments = [];
  for (let i = 1; i < curve.length; i++) {
    const x1 = xScale(i - 1), y1 = yScale(curve[i-1].equity);
    const x2 = xScale(i),     y2 = yScale(curve[i].equity);
    const col = curve[i].outcome === "WIN" ? "rgba(8,153,129,0.9)"
              : curve[i].outcome === "LOSS" ? "rgba(242,54,69,0.8)"
              : "rgba(245,166,35,0.7)";
    segments.push({ x1, y1, x2, y2, col });
  }

  const finalEq  = curve[curve.length - 1].equity;
  const finalCol = finalEq >= 10000 ? "var(--green)" : "var(--red)";

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={W} height={H} style={{ fontFamily: "inherit", display: "block", maxWidth: "100%" }}>
        {/* Grid lines */}
        {yLabels.map((l, i) => (
          <g key={i}>
            <line x1={PAD.l} y1={l.y} x2={W - PAD.r} y2={l.y}
              stroke="var(--border)" strokeWidth={0.5} strokeDasharray="3,3" />
            <text x={PAD.l - 6} y={l.y + 4} textAnchor="end" fontSize={9} fill="var(--text3)">
              {fmtK(l.v)}
            </text>
          </g>
        ))}

        {/* $10k baseline */}
        <line x1={PAD.l} y1={yScale(10000)} x2={W - PAD.r} y2={yScale(10000)}
          stroke="var(--text3)" strokeWidth={1} strokeDasharray="6,3" opacity={0.4} />
        <text x={W - PAD.r + 4} y={yScale(10000) + 4} fontSize={8} fill="var(--text3)">$10k</text>

        {/* Coloured trade segments */}
        {segments.map((s, i) => (
          <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
            stroke={s.col} strokeWidth={2} />
        ))}

        {/* Start/end markers */}
        <circle cx={xScale(0)} cy={yScale(curve[0].equity)} r={4} fill="var(--text3)" />
        <circle cx={xScale(curve.length-1)} cy={yScale(finalEq)} r={5} fill={finalCol} />
        <text x={xScale(curve.length-1)+8} y={yScale(finalEq)+4} fontSize={10} fill={finalCol} fontWeight={700}>
          {fmtK(finalEq)}
        </text>

        {/* X labels */}
        {xLabels.map((p, i) => {
          const xi = curve.indexOf(p);
          return (
            <text key={i} x={xScale(xi)} y={H - 6} textAnchor="middle" fontSize={8} fill="var(--text3)">
              {p.week || ""}
            </text>
          );
        })}

        {/* Axes */}
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="var(--border)" strokeWidth={1} />
        <line x1={PAD.l} y1={H-PAD.b} x2={W-PAD.r} y2={H-PAD.b} stroke="var(--border)" strokeWidth={1} />

        {/* Legend */}
        <g transform={`translate(${PAD.l + 8}, ${PAD.t + 8})`}>
          {[["WIN","rgba(8,153,129,0.9)"],["LOSS","rgba(242,54,69,0.8)"],["TIMEOUT","rgba(245,166,35,0.7)"]].map(([l,c],i) => (
            <g key={l} transform={`translate(${i*72}, 0)`}>
              <line x1={0} y1={5} x2={14} y2={5} stroke={c} strokeWidth={2.5} />
              <text x={18} y={9} fontSize={8} fill="var(--text3)">{l}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

// ── Weeks progress table ──────────────────────────────────────────────────────
function WeeksTable({ weeksData }) {
  if (!weeksData || weeksData.length === 0) return null;
  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6, marginBottom: 20 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 600 }}>
        <thead>
          <tr>
            {["WEEK","REGIME","SCORE","VIX","SIGNALS","COMPLETED","WIN RATE","TOTAL R"].map(h => (
              <th key={h} style={{ ...TH, textAlign: h === "WIN RATE" || h === "TOTAL R" ? "center" : "left" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeksData.map((w, i) => {
            const s   = w.summary || {};
            const base = i % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
            return (
              <tr key={w.week} style={{ background: base }}>
                <td style={{ ...TD, fontWeight: 700, color: "var(--accent)" }}>{w.week}</td>
                <td style={{ ...TD }}>
                  <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
                    fontSize: 9, fontWeight: 700, background: gateBg(w.regime_gate),
                    color: gateCol(w.regime_gate), border: `1px solid ${gateCol(w.regime_gate)}40` }}>
                    {w.regime_gate || "—"}
                  </span>
                </td>
                <td style={{ ...TD, color: "var(--text2)" }}>{w.regime_score != null ? Math.round(w.regime_score) : "—"}/100</td>
                <td style={{ ...TD, color: w.vix > 25 ? "var(--red)" : "var(--text2)" }}>
                  {w.vix != null ? w.vix.toFixed(1) : "—"}
                </td>
                <td style={{ ...TD }}>{w.total_signals}</td>
                <td style={{ ...TD }}>{s.completed || 0}</td>
                <td style={{ ...TD, textAlign: "center", fontWeight: 700, color: wrCol(s.win_rate || 0) }}>
                  {s.win_rate != null ? `${s.win_rate}%` : "—"}
                </td>
                <td style={{ ...TD, textAlign: "center", fontWeight: 700,
                  color: (s.total_r||0) >= 0 ? "var(--green)" : "var(--red)" }}>
                  {s.total_r != null ? fmtR(s.total_r) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Derived rules panel ───────────────────────────────────────────────────────
function RulesPanel({ crossTab }) {
  const rules = deriveRules(crossTab);
  if (!rules.length) return null;
  return (
    <div style={{ marginBottom: 20 }}>
      <h3 style={{ fontSize: 13, fontWeight: 700, margin: "0 0 10px", color: "var(--text)" }}>
        Derived Entry Rules
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rules.map(r => (
          <div key={r.gate} style={{ display: "flex", alignItems: "center", gap: 12,
            padding: "10px 14px", borderRadius: 6, border: `1px solid ${r.color}35`,
            background: `${r.color}08` }}>
            <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 3,
              fontSize: 10, fontWeight: 700, background: gateBg(r.gate),
              color: gateCol(r.gate), border: `1px solid ${gateCol(r.gate)}40`, minWidth: 70, textAlign: "center" }}>
              {r.gate}
            </span>
            <span style={{ fontSize: 11, fontWeight: 700, color: r.color }}>{r.action}</span>
            <span style={{ fontSize: 11, color: "var(--text)" }}>{r.rule}</span>
            <span style={{ fontSize: 10, color: "var(--text3)", marginLeft: "auto" }}>{r.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Summary stat chip ─────────────────────────────────────────────────────────
function Chip({ label, value, color, sub }) {
  return (
    <div style={{ padding: "10px 16px", background: "var(--bg2)", border: "1px solid var(--border)",
      borderRadius: 6, minWidth: 90, textAlign: "center" }}>
      <div style={{ fontSize: 20, fontWeight: 700, color: color || "var(--text)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Correlation() {
  const [weekInput,  setWeekInput]  = useState("2023-10-23");
  const [weeks,      setWeeks]      = useState([]);
  const [running,    setRunning]    = useState(false);
  const [progress,   setProgress]   = useState([]);   // per-week status
  const [result,     setResult]     = useState(null);
  const [activeTab,  setActiveTab]  = useState("matrix");
  const [error,      setError]      = useState(null);

  // Add week to queue
  function addWeek() {
    if (!weekInput || weeks.includes(weekInput)) return;
    if (weeks.length >= 12) { setError("Max 12 weeks"); return; }
    setWeeks(prev => [...prev, weekInput].sort());
    setError(null);
  }

  function removeWeek(w) { setWeeks(prev => prev.filter(x => x !== w)); }

  // Preset week sets
  const PRESET_SETS = [
    { label: "2023 Bull Run", weeks: ["2023-10-23","2023-11-06","2023-11-20","2023-12-04"] },
    { label: "2024 Q1",       weeks: ["2024-01-08","2024-01-22","2024-02-05","2024-02-19"] },
    { label: "2024 Mixed",    weeks: ["2024-03-04","2024-04-08","2024-07-08","2024-08-19"] },
    { label: "2024 Q4",       weeks: ["2024-10-07","2024-10-28","2024-11-04","2024-11-18"] },
    { label: "2025 Highs",    weeks: ["2025-01-06","2025-01-20","2025-02-03","2025-02-17"] },
  ];

  // Run analysis week-by-week with streaming progress
  const runAnalysis = useCallback(async () => {
    if (weeks.length === 0) { setError("Add at least one week date"); return; }
    setRunning(true);
    setError(null);
    setResult(null);
    setProgress(weeks.map(w => ({ week: w, status: "pending" })));

    const weeksData = [];

    for (let i = 0; i < weeks.length; i++) {
      const w = weeks[i];
      setProgress(prev => prev.map((p, j) => j === i ? { ...p, status: "running" } : p));

      try {
        const res = await fetch(`${API}/api/correlation/week`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ week_start: w, max_bars: 20 }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        weeksData.push(data);
        setProgress(prev => prev.map((p, j) => j === i
          ? { ...p, status: "done", signals: data.total_signals, regime: data.regime_gate, trades: data.summary?.completed }
          : p));
      } catch (e) {
        setProgress(prev => prev.map((p, j) => j === i ? { ...p, status: "error", error: e.message } : p));
        weeksData.push({ week: w, error: e.message, trades: [] });
      }
    }

    // Aggregate client-side
    try {
      const res = await fetch(`${API}/api/correlation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weeks, max_bars: 20 }),
      });
      const agg = await res.json();
      if (!res.ok) throw new Error(agg.detail || `HTTP ${res.status}`);
      setResult(agg);
      setActiveTab("matrix");
    } catch (e) {
      setError(`Aggregation failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  }, [weeks]);

  const page = { fontFamily: "'Inter',-apple-system,sans-serif", fontSize: 12,
    background: "var(--bg)", minHeight: "100vh", color: "var(--text)", padding: "16px 16px 40px" };

  const s   = result?.summary || {};
  const eqGrowth = s.equity_growth_pct;
  const eqColor  = (eqGrowth || 0) >= 0 ? "var(--green)" : "var(--red)";

  return (
    <div style={page}>
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px" }}>Correlation Analysis</h2>
        <p style={{ fontSize: 10, color: "var(--text3)", margin: 0 }}>
          Add week-start dates (Mondays). The scanner runs a full replay + trailing-stop backtest for each week,
          then cross-tabulates Regime × Readiness to derive your optimal entry rules.
        </p>
      </div>

      {/* Week builder */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
        padding: "14px 16px", marginBottom: 16 }}>

        {/* Date input */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
          <span style={{ fontSize: 10, color: "var(--text3)", fontWeight: 700, letterSpacing: 1 }}>ADD WEEK</span>
          <input
            type="date"
            value={weekInput}
            onChange={e => setWeekInput(e.target.value)}
            max={new Date().toISOString().split("T")[0]}
            min="2020-01-01"
            style={{ background: "var(--bg)", border: "1px solid var(--border2)", color: "var(--text)",
              padding: "5px 10px", borderRadius: 3, fontFamily: "inherit", fontSize: 12 }}
          />
          <button onClick={addWeek} disabled={!weekInput || weeks.includes(weekInput)} style={{
            padding: "5px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
            border: "1px solid var(--accent)", background: "rgba(41,98,255,0.1)",
            color: "var(--accent)", fontFamily: "inherit", fontWeight: 700,
          }}>+ Add</button>
          <span style={{ fontSize: 9, color: "var(--text3)" }}>{weeks.length}/12 weeks · Enter a Monday date for each scan period</span>
        </div>

        {/* Preset sets */}
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
          <span style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, alignSelf: "center", marginRight: 4 }}>PRESETS:</span>
          {PRESET_SETS.map(p => (
            <button key={p.label} onClick={() => { setWeeks(p.weeks); setError(null); }} style={{
              padding: "3px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--border)", background: "transparent",
              color: "var(--text3)", fontFamily: "inherit",
            }}>{p.label}</button>
          ))}
          <button onClick={() => setWeeks([])} style={{
            padding: "3px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
            border: "1px solid var(--border)", background: "transparent",
            color: "var(--red)", fontFamily: "inherit", marginLeft: 4,
          }}>✕ Clear</button>
        </div>

        {/* Week chips */}
        {weeks.length > 0 && (
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 12 }}>
            {weeks.map(w => {
              const prog = progress.find(p => p.week === w);
              const statusCol = !prog ? "var(--text3)" : prog.status === "done" ? "var(--green)" :
                prog.status === "running" ? "var(--accent)" : prog.status === "error" ? "var(--red)" : "var(--text3)";
              const statusIcon = !prog ? "" : prog.status === "done" ? " ✓" :
                prog.status === "running" ? " ⏳" : prog.status === "error" ? " ✗" : "";
              return (
                <div key={w} style={{ display: "flex", alignItems: "center", gap: 4,
                  padding: "3px 8px", borderRadius: 3, border: `1px solid ${statusCol}40`,
                  background: `${statusCol}08`, fontSize: 10 }}>
                  <span style={{ color: statusCol, fontWeight: 600 }}>{w}{statusIcon}</span>
                  {prog?.regime && <span style={{ fontSize: 8, color: gateCol(prog.regime) }}>{prog.regime}</span>}
                  {!running && <button onClick={() => removeWeek(w)} style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: "var(--text3)", fontSize: 10, padding: "0 2px",
                  }}>×</button>}
                </div>
              );
            })}
          </div>
        )}

        {/* Run button */}
        <button onClick={runAnalysis} disabled={running || weeks.length === 0} style={{
          padding: "8px 24px", fontSize: 11, fontWeight: 700, cursor: running ? "wait" : "pointer",
          borderRadius: 3, border: "1px solid var(--green)", letterSpacing: 0.5,
          background: running ? "rgba(8,153,129,0.1)" : "rgba(8,153,129,0.15)",
          color: running ? "var(--text3)" : "var(--green)", fontFamily: "inherit",
        }}>
          {running ? `⏳ Running… (${progress.filter(p=>p.status==="done").length}/${weeks.length} weeks)` : `▶ Run Correlation Analysis (${weeks.length} weeks)`}
        </button>
        {running && (
          <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 6 }}>
            Each week takes 5–8 min (full scan + backtest). Weeks run sequentially.
            Est: ~{weeks.length * 6} min total.
          </div>
        )}
      </div>

      {error && (
        <div style={{ padding: "8px 12px", background: "rgba(242,54,69,0.08)",
          border: "1px solid rgba(242,54,69,0.3)", borderRadius: 4,
          color: "var(--red)", fontSize: 11, marginBottom: 12 }}>✗ {error}</div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Summary chips */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            <Chip label="WEEKS"         value={s.total_weeks}   />
            <Chip label="TOTAL TRADES"  value={s.total_trades}  />
            <Chip label="WIN RATE"      value={`${s.win_rate}%`}
              color={wrCol(s.win_rate)}  sub={`${s.wins}W / ${s.losses}L`} />
            <Chip label="AVG R"         value={fmtR(s.avg_r)}   color={rCol(s.avg_r || 0)} />
            <Chip label="TOTAL R"       value={fmtR(s.total_r)} color={(s.total_r||0)>=0?"var(--green)":"var(--red)"} />
            <Chip label="PROFIT FACTOR" value={s.profit_factor >= 99 ? "∞" : fmt(s.profit_factor)}
              color={pfCol(s.profit_factor || 0)} />
            <Chip label="EXPECTANCY"    value={fmtR(s.expectancy)} color={rCol(s.expectancy || 0)} sub="per trade" />
            <Chip label="$10K → "       value={fmtK(s.final_equity)} color={eqColor}
              sub={`${fmtPct(eqGrowth)} growth`} />
            <Chip label="MAX DRAWDOWN"  value={`${s.max_drawdown_pct}%`}
              color={(s.max_drawdown_pct||0) < 15 ? "var(--green)" : (s.max_drawdown_pct||0) < 25 ? "var(--yellow)" : "var(--red)"} />
          </div>

          {/* Tab nav */}
          <div style={{ display: "flex", gap: 5, marginBottom: 14 }}>
            {[["matrix","Cross-Tab Matrix"],["equity","$10K Equity Curve"],["weeks","Per-Week Detail"],["rules","Entry Rules"]].map(([v,l]) => (
              <button key={v} onClick={() => setActiveTab(v)} style={{
                padding: "5px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
                border: `1px solid ${activeTab===v?"var(--accent)":"var(--border)"}`,
                background: activeTab===v?"rgba(41,98,255,0.1)":"transparent",
                color: activeTab===v?"var(--accent)":"var(--text3)",
                fontFamily: "inherit", fontWeight: activeTab===v?700:400,
              }}>{l}</button>
            ))}
          </div>

          {/* Cross-tab matrix */}
          {activeTab === "matrix" && (
            <div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10 }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>Regime × Readiness Matrix</h3>
                <span style={{ fontSize: 10, color: "var(--text3)" }}>
                  Each cell = all trades in that regime/readiness bucket. Sort by Verdict to find optimal conditions.
                </span>
              </div>
              <CrossTab crossTab={result.cross_tab} />
            </div>
          )}

          {/* Equity curve */}
          {activeTab === "equity" && (
            <div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10 }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>$10,000 Equity Curve</h3>
                <span style={{ fontSize: 10, color: "var(--text3)" }}>
                  1% risk per trade · trailing stop · chronological order across all weeks
                </span>
              </div>
              <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
                padding: "12px 16px", marginBottom: 16 }}>
                <EquityCurve curve={result.equity_curve} />
              </div>
              <div style={{ display: "flex", gap: 16, fontSize: 10, color: "var(--text3)", flexWrap: "wrap" }}>
                <span>Start: $10,000</span>
                <span style={{ color: eqColor, fontWeight: 700 }}>
                  End: {fmtK(s.final_equity)} ({fmtPct(eqGrowth)})
                </span>
                <span>Max drawdown: {s.max_drawdown_pct}%</span>
                <span>Profit factor: {s.profit_factor >= 99 ? "∞" : fmt(s.profit_factor)}</span>
                <span>{result.equity_curve?.length - 1} trades plotted</span>
              </div>
            </div>
          )}

          {/* Per-week detail */}
          {activeTab === "weeks" && (
            <div>
              <h3 style={{ fontSize: 13, fontWeight: 700, margin: "0 0 10px" }}>Per-Week Breakdown</h3>
              <WeeksTable weeksData={result.weeks_data} />
            </div>
          )}

          {/* Entry rules */}
          {activeTab === "rules" && (
            <div>
              <p style={{ fontSize: 10, color: "var(--text3)", marginBottom: 14 }}>
                Rules derived automatically from your backtest data. A bucket needs ≥ 3 trades to qualify.
                Expectancy &gt; 0 and win rate ≥ 40% = viable. Expectancy &gt; 0.5 and win rate ≥ 50% = high conviction.
              </p>
              <RulesPanel crossTab={result.cross_tab} />
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!result && !running && (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--text3)",
          background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)" }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>📊</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Add weeks and run analysis</div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>
            Start with a preset like "2023 Bull Run" to validate your system on known good conditions.
          </div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>
            Each week = full replay scan + trailing-stop backtest. ~6 min per week.
          </div>
        </div>
      )}
    </div>
  );
}
