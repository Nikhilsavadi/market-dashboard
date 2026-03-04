import React, { useState, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "";

function getBarColor(value, maxAbs) {
  if (value === null || value === undefined) return "#334155";
  const intensity = Math.min(Math.abs(value) / maxAbs, 1);
  if (value > 0) {
    // Cyan/teal for positive — matches screenshot
    const r = Math.round(6  + intensity * 14);
    const g = Math.round(182 + intensity * 50);
    const b = Math.round(212 + intensity * 43);
    return `rgb(${r},${g},${b})`;
  } else {
    // Pink/magenta for negative
    const r = Math.round(236 + intensity * 19);
    const g = Math.round(72  - intensity * 50);
    const b = Math.round(153 - intensity * 30);
    return `rgb(${r},${g},${b})`;
  }
}

function HeatmapRow({ name, value, maxAbs, isTheme, count }) {
  const color = getBarColor(value, maxAbs);
  const barWidth = maxAbs > 0 ? Math.abs(value) / maxAbs * 45 : 0; // max 45% of container

  return (
    <div style={{
      display: "flex", alignItems: "center",
      padding: "2px 0", gap: 0,
      borderBottom: "1px solid rgba(255,255,255,0.03)",
    }}>
      {/* Label */}
      <div style={{
        width: 160, flexShrink: 0,
        fontSize: isTheme ? 11 : 12,
        color: isTheme ? "#94a3b8" : "#cbd5e1",
        fontWeight: isTheme ? 400 : 600,
        textAlign: "right",
        paddingRight: 10,
        paddingLeft: isTheme ? 12 : 0,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {isTheme ? `· ${name}` : name}
      </div>

      {/* Bar container — center pivot */}
      <div style={{ flex: 1, position: "relative", height: 18, display: "flex", alignItems: "center" }}>
        {/* Center line */}
        <div style={{
          position: "absolute", left: "50%", top: 0, bottom: 0,
          width: 1, background: "rgba(255,255,255,0.08)",
        }} />

        {/* Bar */}
        <div style={{
          position: "absolute",
          height: 12,
          width: `${barWidth}%`,
          background: color,
          borderRadius: 2,
          ...(value >= 0
            ? { left: "50%" }
            : { right: "50%" }),
        }} />
      </div>

      {/* Value */}
      <div style={{
        width: 58, flexShrink: 0,
        fontSize: 11, fontWeight: 700,
        color: color,
        textAlign: "right",
        paddingLeft: 8,
      }}>
        {value != null ? `${value > 0 ? "+" : ""}${value.toFixed(2)}%` : "—"}
      </div>
    </div>
  );
}

export default function SectorHeatmap() {
  const [data, setData]         = useState(null);
  const [loading, setLoading]   = useState(true);
  const [view, setView]         = useState("sectors"); // "themes" | "sectors"
  const [timeframe, setTimeframe] = useState("rs");    // "rs" | "rs_1m" | "rs_3m"

  useEffect(() => {
    fetch(`${API}/api/sector-heatmap`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "#64748b", padding: 16, fontSize: 12 }}>Loading sector data...</div>;
  if (!data) return null;

  const rows = view === "themes"
    ? (data.themes || []).map(t => ({ name: t.name, value: t.avg_rs, isTheme: true, count: t.count }))
    : (data.sectors || []).map(s => ({ name: s.name, value: s.rs_1m, isTheme: false, sub: s.etf }));

  const values = rows.map(r => r.value).filter(v => v != null);
  const maxAbs = values.length > 0 ? Math.max(...values.map(Math.abs)) : 10;

  return (
    <div style={{ background: "#0a1628", borderRadius: 8, border: "1px solid #1e293b", overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid #1e293b",
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", letterSpacing: 1 }}>
          SECTOR / THEME RS HEATMAP
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["themes", "sectors"].map(v => (
            <button key={v} onClick={() => setView(v)}
              style={{
                background: view === v ? "#1e3a5f" : "transparent",
                color: view === v ? "#60a5fa" : "#64748b",
                border: `1px solid ${view === v ? "#1e3a5f" : "#1e293b"}`,
                borderRadius: 4, padding: "2px 10px", fontSize: 11,
                cursor: "pointer", fontWeight: view === v ? 600 : 400,
              }}>
              {v === "themes" ? "Themes" : "Sectors"}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div style={{
        display: "flex", gap: 16, padding: "6px 14px",
        borderBottom: "1px solid #1e293b", fontSize: 10, color: "#475569",
      }}>
        <span>
          {view === "themes"
            ? `${rows.length} themes · avg RS rank vs universe`
            : `${rows.length} sectors · 1-month RS vs SPY`}
        </span>
        <span style={{ color: "#06b6d4" }}>■ outperforming</span>
        <span style={{ color: "#ec4899" }}>■ underperforming</span>
      </div>

      {/* Rows */}
      <div style={{ padding: "4px 14px 8px", maxHeight: 520, overflowY: "auto" }}>
        {rows.length === 0 ? (
          <div style={{ color: "#64748b", padding: 16, textAlign: "center", fontSize: 12 }}>
            Run a scan to populate sector data
          </div>
        ) : (
          rows.map((row, i) => (
            <HeatmapRow
              key={i}
              name={row.name}
              value={row.value}
              maxAbs={maxAbs}
              isTheme={row.isTheme}
              count={row.count}
            />
          ))
        )}
      </div>

      {data.scanned_at && (
        <div style={{ padding: "4px 14px 8px", fontSize: 10, color: "#334155" }}>
          Last updated: {new Date(data.scanned_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
