import React, { useState, useEffect, useRef } from "react";

const API = process.env.REACT_APP_API_URL || "";

const QUADRANT_CONFIG = {
  leading:   { color: "#22d3ee", bg: "rgba(34,211,238,0.06)",  label: "Leading",   desc: "Strong RS, accelerating" },
  weakening: { color: "#f59e0b", bg: "rgba(245,158,11,0.06)",  label: "Weakening", desc: "Strong RS, decelerating" },
  improving: { color: "#a78bfa", bg: "rgba(167,139,250,0.06)", label: "Improving", desc: "Weak RS, accelerating" },
  lagging:   { color: "#f87171", bg: "rgba(248,113,113,0.06)", label: "Lagging",   desc: "Weak RS, decelerating" },
};

const LINE_COLORS = [
  "#22d3ee","#f59e0b","#a78bfa","#4ade80","#f87171",
  "#fb923c","#38bdf8","#e879f9","#86efac","#fde68a",
  "#c4b5fd","#6ee7b7","#fca5a5","#93c5fd","#fdba74",
];

// ── RRG Scatter ───────────────────────────────────────────────────────────────
function RRGScatter({ items, title }) {
  const [hovered, setHovered] = useState(null);
  const W = 500, H = 440, PAD = 50;
  const CX = W / 2, CY = H / 2;

  if (!items || items.length === 0) {
    return <div style={{ color: "#475569", padding: 40, textAlign: "center", fontSize: 12 }}>No data — run a scan first</div>;
  }

  const ratios   = items.map(i => i.rs_ratio);
  const momenta  = items.map(i => i.rs_momentum);
  const minR = Math.min(...ratios),   maxR = Math.max(...ratios);
  const minM = Math.min(...momenta),  maxM = Math.max(...momenta);
  const rRange = Math.max(maxR - minR, 4);
  const mRange = Math.max(maxM - minM, 4);
  const plotW = W - PAD * 2, plotH = H - PAD * 2;

  const toX = v => PAD + ((v - minR) / rRange) * plotW;
  const toY = v => H - PAD - ((v - minM) / mRange) * plotH;

  // Centre line positions
  const midR = (minR + maxR) / 2;
  const midM = (minM + maxM) / 2;
  const cx = toX(midR), cy = toY(midM);

  return (
    <div style={{ position: "relative" }}>
      <svg width={W} height={H} style={{ display: "block", margin: "0 auto" }}>
        {/* Quadrant backgrounds */}
        <rect x={cx} y={PAD}    width={W - PAD - cx} height={cy - PAD}    fill="rgba(34,211,238,0.04)" />
        <rect x={cx} y={cy}     width={W - PAD - cx} height={H - PAD - cy} fill="rgba(245,158,11,0.04)" />
        <rect x={PAD} y={PAD}   width={cx - PAD}     height={cy - PAD}    fill="rgba(167,139,250,0.04)" />
        <rect x={PAD} y={cy}    width={cx - PAD}     height={H - PAD - cy} fill="rgba(248,113,113,0.04)" />

        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map(t => (
          <g key={t}>
            <line x1={PAD} y1={PAD + t * plotH} x2={W - PAD} y2={PAD + t * plotH} stroke="rgba(255,255,255,0.04)" />
            <line x1={PAD + t * plotW} y1={PAD} x2={PAD + t * plotW} y2={H - PAD} stroke="rgba(255,255,255,0.04)" />
          </g>
        ))}

        {/* Centre axes */}
        <line x1={cx} y1={PAD} x2={cx} y2={H - PAD} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
        <line x1={PAD} y1={cy} x2={W - PAD} y2={cy} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />

        {/* Quadrant labels */}
        <text x={W - PAD - 4} y={PAD + 14} textAnchor="end" fill="#22d3ee" fontSize={10} opacity={0.6}>LEADING ▶</text>
        <text x={W - PAD - 4} y={H - PAD - 6} textAnchor="end" fill="#f59e0b" fontSize={10} opacity={0.6}>WEAKENING</text>
        <text x={PAD + 4}     y={PAD + 14}    textAnchor="start" fill="#a78bfa" fontSize={10} opacity={0.6}>◀ IMPROVING</text>
        <text x={PAD + 4}     y={H - PAD - 6} textAnchor="start" fill="#f87171" fontSize={10} opacity={0.6}>LAGGING</text>

        {/* Axis labels */}
        <text x={W / 2} y={H - 8} textAnchor="middle" fill="#475569" fontSize={9}>RS RATIO →</text>
        <text x={12} y={H / 2} textAnchor="middle" fill="#475569" fontSize={9} transform={`rotate(-90, 12, ${H / 2})`}>RS MOMENTUM →</text>

        {/* Points */}
        {items.map((item, i) => {
          const x = toX(item.rs_ratio);
          const y = toY(item.rs_momentum);
          const col = QUADRANT_CONFIG[item.quadrant]?.color || "#94a3b8";
          const isHov = hovered === item.name;
          const r = isHov ? 9 : 6;
          return (
            <g key={item.name} onMouseEnter={() => setHovered(item.name)} onMouseLeave={() => setHovered(null)}
              style={{ cursor: "pointer" }}>
              <circle cx={x} cy={y} r={r + 4} fill={col} opacity={0.08} />
              <circle cx={x} cy={y} r={r} fill={col} opacity={isHov ? 1 : 0.85} />
              <text
                x={x} y={y - r - 3}
                textAnchor="middle" fill={col}
                fontSize={isHov ? 11 : 9}
                fontWeight={isHov ? 700 : 500}
              >
                {item.name.length > 10 ? item.name.slice(0, 9) + "…" : item.name}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Hover tooltip */}
      {hovered && (() => {
        const item = items.find(i => i.name === hovered);
        if (!item) return null;
        const q = QUADRANT_CONFIG[item.quadrant];
        return (
          <div style={{
            position: "absolute", top: 10, right: 10,
            background: "#0f172a", border: `1px solid ${q.color}44`,
            borderRadius: 8, padding: "10px 14px", minWidth: 180,
            pointerEvents: "none",
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: q.color, marginBottom: 6 }}>{item.label || item.name}</div>
            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>{q.label} — {q.desc}</div>
            {[["RS Ratio", item.rs_ratio], ["RS Momentum", item.rs_momentum],
              ["Avg RS Rank", item.avg_rs], ["Constituents", item.count]].map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 2 }}>
                <span style={{ color: "#64748b" }}>{k}</span>
                <span style={{ color: "#e2e8f0", fontWeight: 600 }}>{v != null ? (typeof v === "number" ? v.toFixed(1) : v) : "—"}</span>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 12, flexWrap: "wrap" }}>
        {Object.entries(QUADRANT_CONFIG).map(([k, v]) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: v.color }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: v.color }} />
            {v.label}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── RS Line Chart ─────────────────────────────────────────────────────────────
function RSLineChart({ sectors, history }) {
  const [selected, setSelected] = useState(new Set());
  const allNames = sectors.map(s => s.name);

  // Default: top 6 by RS ratio
  const defaultSelected = new Set(
    [...sectors].sort((a, b) => b.rs_ratio - a.rs_ratio).slice(0, 6).map(s => s.name)
  );
  const active = selected.size > 0 ? selected : defaultSelected;

  const W = 620, H = 300, PAD = { t: 20, r: 20, b: 40, l: 50 };
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;

  const activeData = sectors.filter(s => active.has(s.name));
  const allVals = activeData.flatMap(s => (history[s.name] || []));
  if (allVals.length === 0) return <div style={{ color: "#475569", padding: 40, textAlign: "center", fontSize: 12 }}>No history data</div>;

  const minV = Math.min(...allVals) - 0.5;
  const maxV = Math.max(...allVals) + 0.5;
  const vRange = maxV - minV || 1;
  const days = history[activeData[0]?.name]?.length || 60;

  const toX = i => PAD.l + (i / (days - 1)) * plotW;
  const toY = v => PAD.t + plotH - ((v - minV) / vRange) * plotH;

  const yTicks = 5;
  const yStep  = (maxV - minV) / yTicks;

  return (
    <div>
      {/* Sector toggles */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {allNames.map((name, i) => {
          const on = active.has(name);
          const col = LINE_COLORS[i % LINE_COLORS.length];
          return (
            <button key={name} onClick={() => {
              const next = new Set(active);
              if (on && next.size > 1) next.delete(name);
              else next.add(name);
              setSelected(next);
            }} style={{
              background: on ? col + "22" : "transparent",
              color: on ? col : "#475569",
              border: `1px solid ${on ? col + "88" : "#1e293b"}`,
              borderRadius: 4, padding: "2px 8px", fontSize: 11,
              cursor: "pointer", fontWeight: on ? 600 : 400,
              transition: "all 0.15s",
            }}>{name}</button>
          );
        })}
      </div>

      <svg width={W} height={H} style={{ display: "block", overflow: "visible" }}>
        {/* Y grid + labels */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const v = minV + i * yStep;
          const y = toY(v);
          return (
            <g key={i}>
              <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} stroke="rgba(255,255,255,0.05)" />
              <text x={PAD.l - 6} y={y + 4} textAnchor="end" fill="#475569" fontSize={9}>
                {v > 0 ? "+" : ""}{v.toFixed(1)}%
              </text>
            </g>
          );
        })}

        {/* Zero line */}
        {minV < 0 && maxV > 0 && (
          <line x1={PAD.l} y1={toY(0)} x2={W - PAD.r} y2={toY(0)}
            stroke="rgba(255,255,255,0.2)" strokeDasharray="4 3" />
        )}

        {/* X axis labels */}
        {[0, 15, 30, 45, 59].map(i => (
          <text key={i} x={toX(i)} y={H - PAD.b + 14} textAnchor="middle" fill="#475569" fontSize={9}>
            -{days - 1 - i}d
          </text>
        ))}
        <text x={toX(days - 1)} y={H - PAD.b + 14} textAnchor="middle" fill="#64748b" fontSize={9}>Now</text>

        {/* Lines */}
        {activeData.map((sector, idx) => {
          const pts = history[sector.name];
          if (!pts || pts.length < 2) return null;
          const col = LINE_COLORS[allNames.indexOf(sector.name) % LINE_COLORS.length];
          const d = pts.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
          return (
            <g key={sector.name}>
              <path d={d} fill="none" stroke={col} strokeWidth={2} strokeLinecap="round" opacity={0.85} />
              {/* End dot */}
              <circle cx={toX(pts.length - 1)} cy={toY(pts[pts.length - 1])} r={3} fill={col} />
            </g>
          );
        })}
      </svg>

      <div style={{ fontSize: 10, color: "#334155", textAlign: "center", marginTop: 4 }}>
        RS vs SPY (%) — positive = outperforming · negative = underperforming
      </div>
    </div>
  );
}

// ── Multi-Timeframe Table ─────────────────────────────────────────────────────
function MTFTable({ items }) {
  const [sortBy, setSortBy] = useState("rs_1m");

  const sorted = [...items].sort((a, b) => (b[sortBy] ?? -99) - (a[sortBy] ?? -99));
  const col = v => v == null ? "#475569" : v > 2 ? "#22d3ee" : v > 0 ? "#4ade80" : v > -2 ? "#f59e0b" : "#f87171";
  const fmt = v => v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;

  const headers = [
    { key: "name",        label: "SECTOR / THEME", align: "left" },
    { key: "rs_1d",       label: "1D RS" },
    { key: "rs_1w",       label: "1W RS" },
    { key: "rs_1m",       label: "1M RS" },
    { key: "rs_3m",       label: "3M RS" },
    { key: "rs_ratio",    label: "RRG RATIO" },
    { key: "quadrant",    label: "PHASE" },
  ];

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #1e293b" }}>
            {headers.map(h => (
              <th key={h.key}
                onClick={() => h.key !== "name" && h.key !== "quadrant" && setSortBy(h.key)}
                style={{
                  padding: "6px 10px", fontSize: 10, fontWeight: 600,
                  color: sortBy === h.key ? "#60a5fa" : "#475569",
                  textAlign: h.align || "right",
                  cursor: h.key !== "name" && h.key !== "quadrant" ? "pointer" : "default",
                  letterSpacing: 0.5,
                  userSelect: "none",
                }}>
                {h.label} {sortBy === h.key ? "↓" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, i) => {
            const q = QUADRANT_CONFIG[item.quadrant] || {};
            return (
              <tr key={item.name} style={{ borderBottom: "1px solid rgba(30,41,59,0.5)" }}
                onMouseEnter={e => e.currentTarget.style.background = "#0f172a"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "7px 10px", fontWeight: 600, color: "#e2e8f0" }}>
                  {item.label || item.name}
                  {item.etf && <span style={{ marginLeft: 6, fontSize: 10, color: "#475569" }}>{item.etf}</span>}
                </td>
                {["rs_1d", "rs_1w", "rs_1m", "rs_3m"].map(k => (
                  <td key={k} style={{ padding: "7px 10px", textAlign: "right", fontWeight: 600, color: col(item[k]) }}>
                    {fmt(item[k])}
                  </td>
                ))}
                <td style={{ padding: "7px 10px", textAlign: "right", color: "#94a3b8", fontSize: 11 }}>
                  {item.rs_ratio?.toFixed(1)}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right" }}>
                  <span style={{
                    background: q.bg, color: q.color,
                    border: `1px solid ${q.color}44`,
                    borderRadius: 4, padding: "1px 7px", fontSize: 10, fontWeight: 600,
                  }}>
                    {q.label || item.quadrant}
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

// ── Main Component ────────────────────────────────────────────────────────────
export default function SectorRotation() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView]     = useState("rrg");      // rrg | line | table
  const [scope, setScope]   = useState("sectors");  // sectors | themes

  useEffect(() => {
    fetch(`${API}/api/sector-rotation`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: 40, color: "#475569", textAlign: "center", fontSize: 12 }}>
      <div style={{ fontSize: 20, marginBottom: 8 }}>⟳</div>
      Loading rotation data...
    </div>
  );

  if (!data || data.error) return (
    <div style={{ padding: 40, color: "#475569", textAlign: "center", fontSize: 12 }}>
      {data?.error || "No data — run a scan first"}
    </div>
  );

  const items = scope === "sectors" ? (data.sectors || []) : (data.themes || []);

  return (
    <div style={{ background: "#080f1a", borderRadius: 10, border: "1px solid #1e293b", overflow: "hidden" }}>

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px", borderBottom: "1px solid #1e293b",
        background: "linear-gradient(90deg, #0a1628 0%, #080f1a 100%)",
      }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", letterSpacing: 1.5 }}>
            SECTOR ROTATION
          </div>
          {data.scanned_at && (
            <div style={{ fontSize: 10, color: "#334155", marginTop: 1 }}>
              {new Date(data.scanned_at).toLocaleTimeString()}
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {/* Scope toggle */}
          <div style={{ display: "flex", background: "#0f172a", borderRadius: 6, padding: 2, gap: 2 }}>
            {[["sectors", "Sectors"], ["themes", "Themes"]].map(([v, l]) => (
              <button key={v} onClick={() => setScope(v)} style={{
                background: scope === v ? "#1e3a5f" : "transparent",
                color: scope === v ? "#60a5fa" : "#475569",
                border: "none", borderRadius: 4, padding: "3px 10px",
                fontSize: 11, cursor: "pointer", fontWeight: scope === v ? 600 : 400,
              }}>{l}</button>
            ))}
          </div>

          {/* View toggle */}
          <div style={{ display: "flex", background: "#0f172a", borderRadius: 6, padding: 2, gap: 2 }}>
            {[["rrg", "RRG"], ["line", "Lines"], ["table", "Table"]].map(([v, l]) => (
              <button key={v} onClick={() => setView(v)} style={{
                background: view === v ? "#1e293b" : "transparent",
                color: view === v ? "#e2e8f0" : "#475569",
                border: "none", borderRadius: 4, padding: "3px 10px",
                fontSize: 11, cursor: "pointer", fontWeight: view === v ? 600 : 400,
              }}>{l}</button>
            ))}
          </div>
        </div>
      </div>

      {/* RRG explanation strip */}
      {view === "rrg" && (
        <div style={{
          display: "flex", gap: 0, borderBottom: "1px solid #1e293b",
        }}>
          {Object.entries(QUADRANT_CONFIG).map(([k, v]) => (
            <div key={k} style={{
              flex: 1, padding: "6px 10px", background: v.bg,
              borderRight: "1px solid #1e293b",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: v.color }}>{v.label}</div>
              <div style={{ fontSize: 9, color: "#475569", marginTop: 1 }}>{v.desc}</div>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      <div style={{ padding: view === "table" ? "0" : "16px 20px" }}>
        {view === "rrg" && <RRGScatter items={items} />}
        {view === "line" && <RSLineChart sectors={data.sectors || []} history={data.history || {}} />}
        {view === "table" && <MTFTable items={[...(data.sectors || []), ...(data.themes || [])].sort((a, b) => (b.rs_1m ?? 0) - (a.rs_1m ?? 0))} />}
      </div>
    </div>
  );
}
