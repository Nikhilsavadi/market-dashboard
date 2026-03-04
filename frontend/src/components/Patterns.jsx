import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const pr    = (v, dp=2) => v == null ? "—" : `$${Number(v).toFixed(dp)}`;
const pct   = (v, dp=1) => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(dp)}%`;
const fmt   = (v, dp=1) => v == null ? "—" : Number(v).toFixed(dp);

const NYSE = new Set([
  "V","MA","JPM","BAC","GS","MS","WFC","C","AXP","BLK","BX","KO","PEP","PG",
  "JNJ","MRK","ABT","LLY","PFE","CVX","XOM","OXY","COP","SLB","BA","CAT",
  "DE","HON","GE","ETN","UPS","RTX","LMT","HD","WMT","TGT","COST","LOW","NKE",
  "MCD","SBUX","CMG","T","VZ","DIS","CMCSA","NEE","DUK","SO","AMT","CCI","SPG",
  "MCO","SPGI","SYK","BSX","MDT","TMO","UNH","CVS","IBM",
]);
const tvUrl = t => `https://www.tradingview.com/chart/?symbol=${NYSE.has(t)?"NYSE":"NASDAQ"}:${t.replace(".","–")}`;

const rsCol  = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5bc27a" : r >= 70 ? "var(--yellow)" : "var(--text3)";
const rsBg   = r => r >= 90 ? "rgba(8,153,129,0.15)" : r >= 80 ? "rgba(8,153,129,0.08)" : r >= 70 ? "rgba(245,166,35,0.1)" : "transparent";
const vcsCol = v => v == null ? "var(--text3)" : v <= 2 ? "var(--green)" : v <= 3.5 ? "#5bc27a" : v <= 5 ? "var(--yellow)" : "var(--red)";
const adrCol = v => !v ? "var(--text3)" : (v >= 3.5 && v <= 8) ? "var(--green)" : v < 3.5 ? "var(--text3)" : "var(--yellow)";
const e21Col = v => v == null ? "var(--text3)" : v < 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const chgCol = v => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text3)";
const scoreCol = v => v >= 8 ? "var(--green)" : v >= 6.5 ? "var(--accent)" : "var(--text3)";

const PATTERN_META = {
  FLAG:         { label: "Bull Flag",    emoji: "🚩", col: "var(--accent)",  short: "FLAG" },
  VCP:          { label: "VCP",          emoji: "🌀", col: "var(--purple)",  short: "VCP"  },
  CUP_HANDLE:   { label: "Cup & Handle", emoji: "☕", col: "var(--green)",   short: "C&H"  },
  ASC_TRIANGLE: { label: "Asc. Triangle",emoji: "△",  col: "var(--yellow)",  short: "TRI"  },
};
const STAGE_META = {
  breaking_out:   { col: "var(--red)",    label: "BREAKING" },
  forming:        { col: "var(--yellow)", label: "FORMING"  },
  coiling:        { col: "var(--accent)", label: "COILING"  },
  handle_forming: { col: "var(--accent)", label: "HANDLE"   },
  right_side:     { col: "var(--yellow)", label: "RIGHT"    },
  stage_2:        { col: "var(--accent)", label: "NEAR PIV" },
};

const TD = { padding: "6px 10px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", fontSize: 12 };
const TH = {
  padding: "6px 10px", borderBottom: "2px solid var(--border)", fontSize: 9,
  letterSpacing: 1, textTransform: "uppercase", color: "var(--text3)", fontWeight: 700,
  whiteSpace: "nowrap", background: "var(--bg2)", cursor: "pointer", userSelect: "none",
};

function ReadinessBadge({ v }) {
  if (v == null) return <span style={{ color: "var(--text3)" }}>—</span>;
  const map = [null,
    { bg: "rgba(242,54,69,0.12)",  col: "var(--red)",    label: "1 ✗" },
    { bg: "rgba(242,54,69,0.08)",  col: "var(--red)",    label: "2 ✗" },
    { bg: "rgba(245,166,35,0.12)", col: "var(--yellow)", label: "3 ~" },
    { bg: "rgba(8,153,129,0.1)",   col: "var(--green)",  label: "4 ✓" },
    { bg: "rgba(8,153,129,0.18)",  col: "var(--green)",  label: "5 ★" },
  ];
  const c = map[Math.min(5, Math.max(1, Math.round(v)))];
  return (
    <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 3,
      fontSize: 11, fontWeight: 700, background: c.bg, color: c.col,
      border: `1px solid ${c.col}40`, minWidth: 36, textAlign: "center" }}>{c.label}</span>
  );
}

function ExpandedPattern({ p }) {
  const meta = PATTERN_META[p.pattern_type] || {};
  const fields = p.pattern_type === "FLAG" ? [
    ["Pole move", pct(p.pole_move_pct)], ["Pole length", p.pole_len_days ? `${p.pole_len_days}d` : "—"],
    ["Flag depth", pct(p.flag_depth_pct)], ["Flag days", p.flag_len_days ?? "—"],
    ["Vol dry-up", p.vol_dry_ratio ? `${p.vol_dry_ratio}x` : "—"], ["Higher lows", p.higher_lows ? "✓ YES" : "—"],
  ] : p.pattern_type === "VCP" ? [
    ["Contractions", p.contractions ?? "—"], ["Ratio", p.contraction_ratio ?? "—"],
    ["Depths", p.depths?.join(" → ") ?? "—"], ["Vol declining", p.vol_declining ? "✓ YES" : "—"],
    ["Pivot", pr(p.pivot_high)], ["From pivot", pct(p.pct_from_pivot)],
  ] : p.pattern_type === "CUP_HANDLE" ? [
    ["Cup length", p.cup_weeks ? `${p.cup_weeks}wk` : "—"], ["Cup depth", pct(p.cup_depth_pct)],
    ["Recovery", pct(p.cup_recovery)], ["Shape", p.cup_rounded ? "Rounded ☕" : "V-shape"],
    ["Handle depth", pct(p.handle_depth_pct)], ["Vol dry-up", p.vol_dry_ratio ? `${p.vol_dry_ratio}x` : "—"],
    ["Pivot", pr(p.pivot)],
  ] : [
    ["Resistance", pr(p.resistance)], ["Support now", pr(p.support_now)],
    ["Range", pct(p.range_pct)], ["Touches", p.touches ?? "—"],
    ["Low rise", pct(p.low_rise_pct)], ["Vol decline", p.vol_declining ? "✓ YES" : "—"],
  ];

  return (
    <tr style={{ background: "rgba(41,98,255,0.02)" }}>
      <td colSpan={16} style={{ padding: "10px 16px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>
              {meta.emoji} {meta.label} METRICS
            </div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {fields.map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>LEVELS</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[["ENTRY", p.entry, "var(--accent)"], ["STOP", p.stop_price, "var(--red)"],
                ["T1", p.target_1, "var(--green)"], ["T2", p.target_2, "var(--green)"], ["T3", p.target_3, "var(--green)"]
              ].map(([lbl, val, col]) => val ? (
                <div key={lbl} style={{ padding: "4px 10px", borderRadius: 4, background: `${col}11`, border: `1px solid ${col}33` }}>
                  <div style={{ fontSize: 8, color: "var(--text3)" }}>{lbl}</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: col }}>{pr(val)}</div>
                  {p.price && lbl !== "ENTRY" && (
                    <div style={{ fontSize: 8, color: col }}>{pct((val - p.price) / p.price * 100)}</div>
                  )}
                </div>
              ) : null)}
            </div>
          </div>
          {p.description && (
            <div style={{ alignSelf: "center", fontSize: 10, color: "var(--text3)", maxWidth: 280 }}>
              {p.description}
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

function PatternRow({ p, rank, expanded, onExpand, onQuickAdd }) {
  const meta  = PATTERN_META[p.pattern_type] || { col: "var(--text3)", short: "?", emoji: "◈" };
  const stage = STAGE_META[p.stage] || { col: "var(--text3)", label: (p.stage || "").toUpperCase() };
  const base  = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  return (
    <>
      <tr onClick={onExpand} style={{ background: expanded ? "rgba(41,98,255,0.04)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(41,98,255,0.04)" : base}>
        <td style={{ ...TD, textAlign: "right", color: "var(--text3)", width: 28 }}>{rank}</td>
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(p.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {p.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>
        <td style={{ ...TD }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 9, fontWeight: 700, background: `${meta.col}18`, color: meta.col,
            border: `1px solid ${meta.col}40`, letterSpacing: 0.5 }}>{meta.emoji} {meta.short}</span>
        </td>
        <td style={{ ...TD }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 8, fontWeight: 700, background: `${stage.col}18`, color: stage.col,
            border: `1px solid ${stage.col}40`, letterSpacing: 0.5 }}>{stage.label}</span>
        </td>
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3, fontWeight: 700,
            fontSize: 12, background: rsBg(p.rs), color: rsCol(p.rs),
            border: `1px solid ${rsCol(p.rs)}40`, minWidth: 32, textAlign: "center" }}>{p.rs ?? "—"}</span>
        </td>
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10, maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis" }}>
          {p.sector || "—"}
        </td>
        <td style={{ ...TD, fontWeight: 600 }}>{pr(p.price)}</td>
        <td style={{ ...TD, fontWeight: 600, color: chgCol(p.chg || 0), borderRight: "2px solid var(--border2)" }}>
          {pct(p.chg)}
        </td>
        <td style={{ ...TD, textAlign: "center" }}><ReadinessBadge v={p.entry_readiness} /></td>
        <td style={{ ...TD, fontWeight: 600, color: adrCol(p.adr_pct), textAlign: "center" }}>
          {p.adr_pct != null ? `${fmt(p.adr_pct)}%` : "—"}
        </td>
        <td style={{ ...TD, fontWeight: 600, color: e21Col(p.ema21_low_pct), textAlign: "center" }}>
          {p.ema21_low_pct != null ? `${fmt(p.ema21_low_pct)}%` : "—"}
        </td>
        <td style={{ ...TD, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {p.three_weeks_tight
            ? <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 10 }}>✦</span>
            : <span style={{ color: "var(--border2)" }}>·</span>}
        </td>
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: vcsCol(p.vcs) }}>
          {p.vcs != null ? p.vcs.toFixed(1) : "—"}
        </td>
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: scoreCol(p.signal_score) }}>
          {p.signal_score != null ? Number(p.signal_score).toFixed(1) : "—"}
        </td>
        <td style={{ ...TD }} onClick={e => e.stopPropagation()}>
          <button onClick={() => onQuickAdd?.({ ...p, signal_type: p.pattern_type })}
            style={{ padding: "2px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--accent)", background: "transparent",
              color: "var(--accent)", fontFamily: "inherit" }}>+ Journal</button>
        </td>
        <td style={{ ...TD, color: "var(--text3)", textAlign: "center", width: 24 }}>
          {expanded ? "▲" : "▼"}
        </td>
      </tr>
      {expanded && <ExpandedPattern p={p} />}
    </>
  );
}

export default function Patterns({ onQuickAdd }) {
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [filter,   setFilter]   = useState("all");
  const [sortKey,  setSortKey]  = useState("signal_score");
  const [sortDir,  setSortDir]  = useState(-1);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try { setLoading(true); const r = await fetch(`${API}/api/patterns`); setData(await r.json()); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: 24, color: "var(--text3)" }}>Loading patterns…</div>;

  const patterns = data?.patterns || [];
  const summary  = data?.summary  || {};
  let rows = filter === "all" ? [...patterns]
    : filter === "breaking" ? patterns.filter(p => p.stage === "breaking_out")
    : patterns.filter(p => p.pattern_type === filter);
  rows = rows.sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function thClick(k) { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : -1); }
  function th(label, k, align = "left") {
    const active = sortKey === k;
    return (
      <th onClick={() => thClick(k)}
        style={{ ...TH, textAlign: align, color: active ? "var(--accent)" : "var(--text3)" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  const pills = [
    { v: "all",          l: `All (${patterns.length})` },
    { v: "FLAG",         l: `🚩 Flag (${summary.FLAG || 0})` },
    { v: "VCP",          l: `🌀 VCP (${summary.VCP || 0})` },
    { v: "CUP_HANDLE",   l: `☕ Cup (${summary.CUP_HANDLE || 0})` },
    { v: "ASC_TRIANGLE", l: `△ Triangle (${summary.ASC_TRIANGLE || 0})` },
    { v: "breaking",     l: `🔥 Breaking (${patterns.filter(p => p.stage === "breaking_out").length})` },
  ];

  return (
    <div style={{ fontFamily: "'Inter',sans-serif", fontSize: 12, padding: "16px 16px 40px",
      color: "var(--text)", background: "var(--bg)", minHeight: "100vh" }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 2 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Chart Patterns</h2>
          <span style={{ fontSize: 10, color: "var(--text3)" }}>
            {patterns.length} detected · {data?.scanned_at || "—"}
          </span>
        </div>
        <p style={{ fontSize: 10, color: "var(--text3)", margin: 0 }}>
          Flag · VCP · Cup & Handle · Triangle — RS leaders only. Click row to expand.
        </p>
      </div>
      <div style={{ display: "flex", gap: 5, marginBottom: 14, flexWrap: "wrap" }}>
        {pills.map(({ v, l }) => (
          <button key={v} onClick={() => setFilter(v)} style={{
            padding: "4px 10px", fontSize: 9, cursor: "pointer", borderRadius: 3,
            border: `1px solid ${filter === v ? "var(--accent)" : "var(--border)"}`,
            background: filter === v ? "rgba(41,98,255,0.08)" : "transparent",
            color: filter === v ? "var(--accent)" : "var(--text3)",
            fontFamily: "inherit", letterSpacing: 0.5, fontWeight: filter === v ? 700 : 400,
          }}>{l}</button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div style={{ color: "var(--text3)", padding: "24px 0", textAlign: "center" }}>
          {patterns.length === 0 ? "No patterns detected. Run a scan." : "No patterns match this filter."}
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 920 }}>
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                <th colSpan={8} style={{ ...TH, fontSize: 8, textAlign: "center",
                  borderRight: "2px solid var(--border2)", cursor: "default" }}>SIGNAL</th>
                <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center",
                  borderRight: "2px solid var(--border2)", cursor: "default" }}>CORE STATS</th>
                <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center", cursor: "default" }}>SCORE</th>
              </tr>
              <tr>
                <th style={{ ...TH, width: 28, cursor: "default" }}>#</th>
                {th("TICKER",  "ticker")}
                {th("PATTERN", "pattern_type")}
                {th("STAGE",   "stage")}
                {th("RS",      "rs", "center")}
                {th("SECTOR",  "sector")}
                {th("PRICE",   "price")}
                <th style={{ ...TH, borderRight: "2px solid var(--border2)", cursor: "default" }}>CHG</th>
                {th("READY",   "entry_readiness", "center")}
                {th("ADR%",    "adr_pct", "center")}
                {th("EMA21L%", "ema21_low_pct", "center")}
                <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)", cursor: "default" }}>3WT</th>
                {th("VCS",     "vcs", "center")}
                {th("SCORE",   "signal_score", "center")}
                <th style={{ ...TH, cursor: "default" }}></th>
                <th style={{ ...TH, cursor: "default" }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => (
                <PatternRow
                  key={`${p.ticker}-${p.pattern_type}`}
                  p={p} rank={i + 1}
                  expanded={expanded === `${p.ticker}-${p.pattern_type}`}
                  onExpand={() => setExpanded(
                    expanded === `${p.ticker}-${p.pattern_type}` ? null : `${p.ticker}-${p.pattern_type}`
                  )}
                  onQuickAdd={onQuickAdd}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
