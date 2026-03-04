import React, { useState } from "react";

const API = process.env.REACT_APP_API_URL || "";

// ── colour helpers (same as Pipeline) ────────────────────────────────────────
const rsCol  = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5bc27a" : r >= 70 ? "var(--yellow)" : "var(--text3)";
const rsBg   = r => r >= 90 ? "rgba(8,153,129,0.15)" : r >= 80 ? "rgba(8,153,129,0.08)" : r >= 70 ? "rgba(245,166,35,0.1)" : "transparent";
const adrCol = v => !v ? "var(--text3)" : (v >= 3.5 && v <= 8) ? "var(--green)" : v < 3.5 ? "var(--text3)" : "var(--yellow)";
const adrBg  = v => (v >= 3.5 && v <= 8) ? "rgba(8,153,129,0.1)" : "transparent";
const e21Col = v => v == null ? "var(--text3)" : v < 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const e21Bg  = v => v == null ? "transparent" : v < 5 ? "rgba(8,153,129,0.1)" : v <= 8 ? "rgba(245,166,35,0.08)" : "rgba(242,54,69,0.08)";
const vcsCol = v => v == null ? "var(--text3)" : v <= 2 ? "var(--green)" : v <= 3.5 ? "#5bc27a" : v <= 5 ? "var(--yellow)" : "var(--red)";
const scoreCol = v => v >= 8 ? "var(--green)" : v >= 6.5 ? "var(--accent)" : "var(--text3)";
const distCol = v => v < 2 ? "var(--red)" : v < 5 ? "var(--accent)" : v < 10 ? "var(--text2)" : "var(--text3)";

// Entry Readiness 1–5 pill
function ReadinessBadge({ v }) {
  if (v == null) return <span style={{ color: "var(--text3)" }}>—</span>;
  const configs = [
    null,
    { bg: "rgba(242,54,69,0.12)",  col: "var(--red)",    label: "1 ✗" },
    { bg: "rgba(242,54,69,0.08)",  col: "var(--red)",    label: "2 ✗" },
    { bg: "rgba(245,166,35,0.12)", col: "var(--yellow)", label: "3 ~" },
    { bg: "rgba(8,153,129,0.1)",   col: "var(--green)",  label: "4 ✓" },
    { bg: "rgba(8,153,129,0.18)",  col: "var(--green)",  label: "5 ★" },
  ];
  const c = configs[Math.min(5, Math.max(1, Math.round(v)))];
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 3,
      fontSize: 11, fontWeight: 700, background: c.bg, color: c.col,
      border: `1px solid ${c.col}40`, minWidth: 36, textAlign: "center",
    }}>{c.label}</span>
  );
}

const MA_COLORS = { MA10: "var(--cyan)", MA21: "var(--purple)", MA50: "var(--yellow)" };
const NYSE = new Set(["V","MA","JPM","BAC","GS","MS","WFC","C","AXP","BLK","KO","PEP","PG","JNJ","MRK","LLY","PFE","CVX","XOM","BA","CAT","DE","HON","GE","ETN","UPS","RTX","LMT","HD","WMT","TGT","COST","NKE","MCD","T","VZ","DIS","NEE","AMT","SPG","MCO","SPGI","SYK","TMO","UNH","USB","IBM"]);
const tvUrl = t => `https://www.tradingview.com/chart/?symbol=${NYSE.has(t)?"NYSE":"NASDAQ"}:${t}`;

const TD = { padding: "5px 9px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", fontSize: 11 };
const TH = { padding: "5px 9px", borderBottom: "2px solid var(--border)", fontSize: 9, letterSpacing: 1,
  textTransform: "uppercase", color: "var(--text3)", fontWeight: 700, whiteSpace: "nowrap",
  background: "var(--bg2)", cursor: "pointer", userSelect: "none" };

// ── PRESET DATES ──────────────────────────────────────────────────────────────
const PRESETS = [
  { label: "Oct 2023 Bull Start",  date: "2023-10-26", desc: "Market bottomed, RS leaders ignited" },
  { label: "Nov 2023 Breakout",    date: "2023-11-03", desc: "QQQ breakout, momentum surge" },
  { label: "Jan 2024 Continuation",date: "2024-01-12", desc: "New year continuation, AI leaders" },
  { label: "Apr 2024 Pullback",    date: "2024-04-19", desc: "VIX spike, MA bounces forming" },
  { label: "Aug 2024 Recovery",    date: "2024-08-16", desc: "Post-carry-unwind recovery" },
  { label: "Nov 2024 Election",    date: "2024-11-06", desc: "Post-election momentum surge" },
  { label: "Jan 2025 High",        date: "2025-01-15", desc: "Near all-time highs, extended" },
];

// ── Signal row ────────────────────────────────────────────────────────────────
function SignalRow({ s, type, rank }) {
  const [open, setOpen] = useState(false);
  const maC = MA_COLORS[s.bouncing_from] || "var(--text3)";
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";

  return (
    <>
      <tr onClick={() => setOpen(!open)} style={{ background: open ? "rgba(41,98,255,0.05)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = open ? "rgba(41,98,255,0.05)" : base}>

        <td style={{ ...TD, textAlign: "center", width: 28, color: "var(--text3)" }}>{rank}</td>

        {/* Ticker */}
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>

        {/* RS */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 3,
            fontWeight: 700, fontSize: 11, background: rsBg(s.rs), color: rsCol(s.rs) }}>{s.rs}</span>
        </td>

        {/* Sector */}
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10 }}>{s.sector || "—"}</td>

        {/* Price */}
        <td style={{ ...TD, fontWeight: 600 }}>${s.price != null ? Number(s.price).toFixed(2) : "—"}</td>

        {/* CHG */}
        <td style={{ ...TD, fontWeight: 600, borderRight: "2px solid var(--border2)",
          color: (s.chg||0) > 0 ? "var(--green)" : (s.chg||0) < 0 ? "var(--red)" : "var(--text3)" }}>
          {s.chg != null ? `${s.chg > 0?"+":""}${s.chg.toFixed(1)}%` : "—"}
        </td>

        {/* Readiness */}
        <td style={{ ...TD, textAlign: "center" }}><ReadinessBadge v={s.entry_readiness} /></td>

        {/* ADR % */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: adrCol(s.adr_pct), background: adrBg(s.adr_pct) }}>
          {s.adr_pct != null ? `${s.adr_pct.toFixed(1)}%` : "—"}
        </td>

        {/* EMA21L % */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: e21Col(s.ema21_low_pct || s.ema21LowPct), background: e21Bg(s.ema21_low_pct || s.ema21LowPct) }}>
          {(s.ema21_low_pct ?? s.ema21LowPct) != null ? `${(s.ema21_low_pct ?? s.ema21LowPct).toFixed(1)}%` : "—"}
        </td>

        {/* 3WT */}
        <td style={{ ...TD, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {(s.three_weeks_tight || s.threeWeeksTight)
            ? <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 13 }}>✦</span>
            : <span style={{ color: "var(--border2)" }}>·</span>}
        </td>

        {/* VCS */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: vcsCol(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>

        {/* MA (signals only) */}
        {type === "signal" && (
          <td style={{ ...TD, textAlign: "center" }}>
            {s.bouncing_from ? (
              <span style={{ padding: "2px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                background: `${maC}18`, color: maC, border: `1px solid ${maC}40` }}>{s.bouncing_from}</span>
            ) : "—"}
          </td>
        )}

        {/* Near / Dist (pipeline) */}
        {type === "pipeline" && <>
          <td style={{ ...TD, textAlign: "center" }}>
            {s.closest_ma ? (
              <span style={{ padding: "2px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                background: `${MA_COLORS[s.closest_ma]||"var(--text3)"}18`,
                color: MA_COLORS[s.closest_ma]||"var(--text3)",
                border: `1px solid ${MA_COLORS[s.closest_ma]||"var(--text3)"}40` }}>{s.closest_ma}</span>
            ) : "—"}
          </td>
          <td style={{ ...TD, fontWeight: 700, color: distCol(s.closest_pct || 99) }}>
            {s.closest_pct != null ? `${s.closest_pct.toFixed(1)}%` : "—"}
          </td>
        </>}

        {/* Score */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: scoreCol(s.signal_score || 0) }}>
          {s.signal_score != null ? s.signal_score.toFixed(1) : "—"}
        </td>
      </tr>

      {open && (
        <tr style={{ background: "rgba(41,98,255,0.03)" }}>
          <td colSpan={type === "signal" ? 13 : 14} style={{ padding: "8px 16px 10px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap", fontSize: 11, alignItems: "center" }}>
              {[["EMA21", s.ma21], ["MA50", s.ma50], ["EMA21 LOW", s.ema21_low ?? s.ema21Low],
                ["STOP", s.stop_price], ["T1", s.target_1]].map(([l, v]) => v != null && (
                <div key={l}>
                  <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 4 }}>{l}</span>
                  <span style={{ fontWeight: 600, color: l.startsWith("T") || l === "EMA21 LOW" ? "var(--green)" : l === "STOP" ? "var(--red)" : "var(--text)" }}>
                    ${Number(v).toFixed(2)}
                  </span>
                </div>
              ))}
              {(s.ema21_low_pct ?? s.ema21LowPct) != null && (
                <span style={{ padding: "2px 8px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: e21Bg(s.ema21_low_pct ?? s.ema21LowPct), color: e21Col(s.ema21_low_pct ?? s.ema21LowPct),
                  border: `1px solid ${e21Col(s.ema21_low_pct ?? s.ema21LowPct)}40` }}>
                  {(s.ema21_low_pct ?? s.ema21LowPct).toFixed(1)}% to EMA21 Low
                  {(s.ema21_low_pct ?? s.ema21LowPct) < 5 ? " · LOW RISK ✓" : (s.ema21_low_pct ?? s.ema21LowPct) <= 8 ? " · MODERATE" : " · TOO WIDE"}
                </span>
              )}
              {(s.three_weeks_tight || s.threeWeeksTight) && (
                <span style={{ padding: "2px 8px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(8,153,129,0.12)", color: "var(--green)", border: "1px solid rgba(8,153,129,0.3)" }}>✦ 3-WEEKS TIGHT</span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Table wrapper ─────────────────────────────────────────────────────────────
function ReplayTable({ rows, type, title, color }) {
  const [sortKey, setSortKey] = useState("signal_score");
  const [sortDir, setSortDir] = useState(-1);

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function th(label, k, align = "left", title = "") {
    const active = sortKey === k;
    return (
      <th title={title} onClick={() => { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : -1); }}
        style={{ ...TH, textAlign: align, color: active ? "var(--accent)" : "var(--text3)" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  const colSpanTotal = type === "signal" ? 13 : 14;

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, color }}>{title}</h3>
        <span style={{ fontSize: 10, color: "var(--text3)" }}>{rows.length} stocks</span>
      </div>
      {rows.length === 0 ? (
        <div style={{ padding: "16px 20px", background: "var(--bg2)", borderRadius: 6,
          border: "1px solid var(--border)", color: "var(--text3)", fontSize: 11 }}>
          No signals on this date with current criteria.
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 860 }}>
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                <th colSpan={6} style={{ ...TH, fontSize: 8, textAlign: "center", borderRight: "2px solid var(--border2)" }}>STOCK</th>
                <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center", color: "var(--accent)", borderRight: "2px solid var(--border2)" }}>CORE STATS</th>
                <th colSpan={type === "signal" ? 3 : 4} style={{ ...TH, fontSize: 8, textAlign: "center" }}>ENTRY</th>
              </tr>
              <tr>
                <th style={{ ...TH, width: 28 }}>#</th>
                {th("TICKER",   "ticker",           "left")}
                {th("RS",       "rs",               "center")}
                {th("SECTOR",   "sector",           "left")}
                {th("PRICE",    "price",            "left")}
                <th onClick={() => { setSortKey("chg"); setSortDir(sortKey==="chg"?sortDir*-1:-1); }}
                  style={{ ...TH, borderRight: "2px solid var(--border2)", color: sortKey==="chg"?"var(--accent)":"var(--text3)" }}>
                  CHG{sortKey==="chg"?(sortDir>0?" ↑":" ↓"):" ↕"}
                </th>
                {th("READY",    "entry_readiness",  "center", "Entry Readiness 1–5")}
                {th("ADR %",    "adr_pct",          "center", "Avg Daily Range % — ideal 3.5–8%")}
                {th("EMA21L %", "ema21_low_pct",    "center", "Distance to EMA21 Low — <5% low risk")}
                <th style={{ ...TH, textAlign: "center", cursor: "default", borderRight: "2px solid var(--border2)" }}>3WT</th>
                {th("VCS",     "vcs",              "center")}
                {type === "signal"
                  ? th("MA",    "bouncing_from",    "center")
                  : <>{th("NEAR", "closest_ma",    "center")}{th("DIST %","closest_pct","left")}</>
                }
                {th("SCORE",   "signal_score",     "center")}
              </tr>
            </thead>
            <tbody>
              {sorted.map((s, i) => (
                <SignalRow key={`${s.ticker}-${i}`} s={s} type={type} rank={i + 1} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Market regime summary bar ─────────────────────────────────────────────────
function RegimeSummary({ market }) {
  if (!market) return null;
  const score = market.score || 0;
  const gate  = market.gate || "—";
  const gateCol = gate === "GO" ? "var(--green)" : gate === "CAUTION" ? "var(--yellow)" :
                  gate === "WARN" ? "var(--red)" : gate === "DANGER" ? "var(--red)" : "var(--text3)";

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", padding: "10px 16px",
      background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6, marginBottom: 16, fontSize: 11 }}>
      <div>
        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 6 }}>REGIME</span>
        <span style={{ fontWeight: 700, color: gateCol, fontSize: 13 }}>{gate}</span>
      </div>
      <div>
        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 6 }}>SCORE</span>
        <span style={{ fontWeight: 600 }}>{score}/100</span>
      </div>
      <div>
        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 6 }}>MODE</span>
        <span style={{ fontWeight: 600 }}>{market.mode || "—"}</span>
      </div>
      {market.vix && <div>
        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 6 }}>VIX</span>
        <span style={{ fontWeight: 600, color: market.vix > 25 ? "var(--red)" : "var(--text)" }}>{market.vix.toFixed(1)}</span>
      </div>}
      <div>
        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 6 }}>LABEL</span>
        <span style={{ fontWeight: 600 }}>{market.label || "—"}</span>
      </div>
    </div>
  );
}

// ── Outcome colour helpers ────────────────────────────────────────────────────
function outcomeColor(o) {
  if (o === "WIN")     return "var(--green)";
  if (o === "LOSS")    return "var(--red)";
  if (o === "TIMEOUT") return "var(--yellow)";
  if (o === "OPEN")    return "var(--accent)";
  return "var(--text3)";
}
function outcomeBg(o) {
  if (o === "WIN")     return "rgba(8,153,129,0.1)";
  if (o === "LOSS")    return "rgba(242,54,69,0.08)";
  if (o === "TIMEOUT") return "rgba(245,166,35,0.08)";
  if (o === "OPEN")    return "rgba(41,98,255,0.08)";
  return "transparent";
}
function rColor(r) {
  if (r == null) return "var(--text3)";
  if (r >= 2)   return "var(--green)";
  if (r >= 0.5) return "#5bc27a";
  if (r >= 0)   return "var(--yellow)";
  return "var(--red)";
}

// ── Summary stat chip ─────────────────────────────────────────────────────────
function StatChip({ label, value, color, sub }) {
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

// ── Per-trade row ─────────────────────────────────────────────────────────────
function TradeRow({ r, rank }) {
  const [open, setOpen] = useState(false);
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  const oc   = outcomeColor(r.outcome);
  const ob   = outcomeBg(r.outcome);

  return (
    <>
      <tr onClick={() => setOpen(!open)}
        style={{ background: open ? "rgba(41,98,255,0.04)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = open ? "rgba(41,98,255,0.04)" : base}>

        <td style={{ ...TD, textAlign: "right", color: "var(--text3)", width: 28 }}>{rank}</td>

        {/* Ticker */}
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(r.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {r.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>

        {/* Outcome badge */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 3,
            fontSize: 10, fontWeight: 700, background: ob, color: oc, border: `1px solid ${oc}40` }}>
            {r.outcome}
          </span>
        </td>

        {/* R multiple */}
        <td style={{ ...TD, fontWeight: 700, fontSize: 13, color: rColor(r.r_multiple), textAlign: "center" }}>
          {r.r_multiple != null ? `${r.r_multiple > 0 ? "+" : ""}${r.r_multiple.toFixed(2)}R` : "—"}
        </td>

        {/* % gain */}
        <td style={{ ...TD, fontWeight: 600,
          color: (r.pct_gain||0) > 0 ? "var(--green)" : (r.pct_gain||0) < 0 ? "var(--red)" : "var(--text3)" }}>
          {r.pct_gain != null ? `${r.pct_gain > 0 ? "+" : ""}${r.pct_gain.toFixed(1)}%` : "—"}
        </td>

        {/* Max gain */}
        <td style={{ ...TD, color: "var(--green)" }}>
          {r.max_gain_pct != null ? `+${r.max_gain_pct.toFixed(1)}%` : "—"}
        </td>

        {/* Days held */}
        <td style={{ ...TD, textAlign: "center", color: "var(--text2)" }}>
          {r.days_held != null ? r.days_held : "—"}
        </td>

        {/* Trail activated */}
        <td style={{ ...TD, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {r.trail_activated
            ? <span style={{ color: "var(--green)", fontWeight: 700 }}>✓</span>
            : <span style={{ color: "var(--border2)" }}>·</span>}
        </td>

        {/* Entry / Exit */}
        <td style={{ ...TD, color: "var(--text2)" }}>
          ${r.entry_price != null ? r.entry_price.toFixed(2) : "—"}
        </td>
        <td style={{ ...TD, color: "var(--text2)" }}>
          ${r.exit_price != null ? r.exit_price.toFixed(2) : "—"}
        </td>
        <td style={{ ...TD, color: "var(--red)", fontSize: 10 }}>
          ${r.initial_stop != null ? r.initial_stop.toFixed(2) : "—"}
        </td>

        {/* Signal quality */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 6px", borderRadius: 3,
            fontWeight: 700, fontSize: 10, background: rsBg(r.rs), color: rsCol(r.rs) }}>{r.rs || "—"}</span>
        </td>
        <td style={{ ...TD, fontWeight: 600, textAlign: "center", color: vcsCol(r.vcs) }}>
          {r.vcs != null ? r.vcs.toFixed(1) : "—"}
        </td>
        <td style={{ ...TD, textAlign: "center" }}>
          <ReadinessBadge v={r.entry_readiness} />
        </td>
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10 }}>{r.sector || "—"}</td>
      </tr>

      {/* Expanded: exit reason + bar-by-bar trail */}
      {open && (
        <tr style={{ background: "rgba(41,98,255,0.02)" }}>
          <td colSpan={16} style={{ padding: "10px 16px 12px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 11, marginBottom: 8 }}>
              <div>
                <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 5 }}>EXIT DATE</span>
                <span style={{ fontWeight: 600 }}>{r.exit_date || "—"}</span>
              </div>
              <div>
                <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 5 }}>EXIT REASON</span>
                <span style={{ fontWeight: 600, color: oc }}>{r.exit_reason || "—"}</span>
              </div>
              <div>
                <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 5 }}>ENTRY DATE</span>
                <span style={{ fontWeight: 600 }}>{r.entry_date}</span>
              </div>
              {r.adr_pct != null && <div>
                <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 5 }}>ADR %</span>
                <span style={{ fontWeight: 600, color: adrCol(r.adr_pct) }}>{r.adr_pct.toFixed(1)}%</span>
              </div>}
              {r.ema21_low_pct != null && <div>
                <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 5 }}>EMA21L %</span>
                <span style={{ fontWeight: 600, color: e21Col(r.ema21_low_pct) }}>{r.ema21_low_pct.toFixed(1)}%</span>
              </div>}
              {r.three_weeks_tight && <span style={{ padding: "2px 8px", borderRadius: 3, fontSize: 9,
                fontWeight: 700, background: "rgba(8,153,129,0.12)", color: "var(--green)",
                border: "1px solid rgba(8,153,129,0.3)" }}>✦ 3WT</span>}
            </div>

            {/* Mini trail chart — last 10 bars of detail */}
            {r.bars_detail && r.bars_detail.length > 0 && (
              <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 4 }}>
                <span style={{ letterSpacing: 1, fontWeight: 700 }}>TRAIL LOG (last {Math.min(10, r.bars_detail.length)} bars):</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                  {r.bars_detail.slice(-10).map((b, i) => (
                    <div key={i} style={{ padding: "3px 7px", borderRadius: 3, fontSize: 9,
                      background: b.trail_active ? "rgba(8,153,129,0.08)" : "var(--bg3)",
                      border: "1px solid var(--border)" }}>
                      <span style={{ color: "var(--text3)" }}>{b.date.slice(5)}</span>
                      <span style={{ margin: "0 4px", color: "var(--text2)", fontWeight: 600 }}>${b.close}</span>
                      <span style={{ color: b.trail_active ? "var(--green)" : "var(--red)" }}>
                        stop ${b.stop}{b.trail_active ? " 🔒" : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Backtest results panel ────────────────────────────────────────────────────
function BacktestResults({ result }) {
  const [sortKey, setSortKey] = useState("r_multiple");
  const [sortDir, setSortDir] = useState(-1);
  const [filter,  setFilter]  = useState("all");

  const s   = result.summary || {};
  const all = result.results || [];

  const filterMap = {
    wins:     r => r.outcome === "WIN",
    losses:   r => r.outcome === "LOSS",
    timeout:  r => r.outcome === "TIMEOUT",
    open:     r => r.outcome === "OPEN",
    trailed:  r => r.trail_activated,
    readyHigh:r => (r.entry_readiness || 0) >= 4,
  };

  let rows = filterMap[filter] ? all.filter(filterMap[filter]) : [...all];
  rows = [...rows].sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function thClick(k) { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : -1); }
  function th(label, k, align = "left", tip = "") {
    const active = sortKey === k;
    return (
      <th title={tip} onClick={() => thClick(k)}
        style={{ ...TH, textAlign: align, color: active ? "var(--accent)" : "var(--text3)" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  // Expectancy bar colour
  const expColor = s.expectancy > 0.5 ? "var(--green)" : s.expectancy > 0 ? "var(--yellow)" : "var(--red)";
  const totalRColor = s.total_r > 0 ? "var(--green)" : "var(--red)";

  const filterBtns = [
    { v: "all",       l: `All (${all.length})` },
    { v: "wins",      l: `Wins (${s.wins || 0})` },
    { v: "losses",    l: `Losses (${s.losses || 0})` },
    { v: "timeout",   l: `Timeout (${s.timeouts || 0})` },
    { v: "trailed",   l: "Trail activated" },
    { v: "readyHigh", l: "Readiness 4–5★" },
  ];

  return (
    <div>
      {/* Summary stats */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <StatChip label="WIN RATE"    value={`${s.win_rate || 0}%`}
          color={(s.win_rate||0) >= 55 ? "var(--green)" : (s.win_rate||0) >= 40 ? "var(--yellow)" : "var(--red)"}
          sub={`${s.wins}W / ${s.losses}L`} />
        <StatChip label="TOTAL R"     value={`${s.total_r > 0 ? "+" : ""}${s.total_r}R`} color={totalRColor} />
        <StatChip label="EXPECTANCY"  value={`${s.expectancy > 0 ? "+" : ""}${s.expectancy}R`} color={expColor}
          sub="per trade" />
        <StatChip label="AVG WIN"     value={`+${s.avg_win_r}R`}   color="var(--green)" />
        <StatChip label="AVG LOSS"    value={`${s.avg_loss_r}R`}   color="var(--red)"   />
        <StatChip label="AVG HOLD"    value={`${s.avg_days_held}d`} />
        <StatChip label="TRAIL %"     value={`${s.trail_activated_pct}%`}
          color="var(--accent)" sub="activated" />
        <StatChip label="COMPLETED"   value={s.completed || 0} sub={`of ${s.total}`} />
      </div>

      {/* Expectancy bar */}
      <div style={{ marginBottom: 14, padding: "10px 14px", background: "var(--bg2)",
        border: "1px solid var(--border)", borderRadius: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 10 }}>
          <span style={{ color: "var(--text3)", letterSpacing: 1, fontWeight: 700 }}>SYSTEM EDGE</span>
          <span style={{ color: expColor, fontWeight: 700 }}>
            Expectancy {s.expectancy > 0 ? "+" : ""}{s.expectancy}R per trade ·
            {s.expectancy > 0.5 ? " ✓ Positive edge" : s.expectancy > 0 ? " ~ Marginal edge" : " ✗ Negative edge — review setup"}
          </span>
        </div>
        <div style={{ height: 6, background: "var(--bg4)", borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            height: "100%", borderRadius: 3,
            width: `${Math.min(100, Math.max(2, (s.expectancy + 1) / 3 * 100))}%`,
            background: expColor, transition: "width 0.4s",
          }} />
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 9, color: "var(--text3)" }}>
          <span>Trail logic: +3% activates · lowest low 3 bars · 20-bar max</span>
          <span>Date: {result.as_of_date}</span>
          <span>{s.completed} completed trades</span>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 10 }}>
        {filterBtns.map(({ v, l }) => (
          <button key={v} onClick={() => setFilter(v)} style={{
            padding: "3px 10px", fontSize: 9, textTransform: "uppercase", cursor: "pointer",
            borderRadius: 3, fontFamily: "inherit", letterSpacing: 0.5,
            border: `1px solid ${filter === v ? "var(--accent)" : "var(--border)"}`,
            background: filter === v ? "rgba(41,98,255,0.1)" : "transparent",
            color: filter === v ? "var(--accent)" : "var(--text3)",
          }}>{l}</button>
        ))}
      </div>

      {/* Trade table */}
      <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 900 }}>
          <thead>
            <tr style={{ background: "var(--bg3)" }}>
              <th colSpan={8} style={{ ...TH, fontSize: 8, textAlign: "center",
                borderRight: "2px solid var(--border2)" }}>TRADE RESULT</th>
              <th colSpan={3} style={{ ...TH, fontSize: 8, textAlign: "center",
                borderRight: "2px solid var(--border2)" }}>LEVELS</th>
              <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center" }}>SIGNAL QUALITY</th>
            </tr>
            <tr>
              <th style={{ ...TH, width: 28 }}>#</th>
              {th("TICKER",   "ticker",          "left")}
              {th("OUTCOME",  "outcome",         "center")}
              {th("R MULT",   "r_multiple",      "center", "R multiple: how many R gained or lost")}
              {th("GAIN %",   "pct_gain",        "left")}
              {th("MAX %",    "max_gain_pct",    "left",   "Highest % reached before exit")}
              {th("DAYS",     "days_held",       "center")}
              <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)",
                cursor: "default" }}>TRAIL ✓</th>
              {th("ENTRY",    "entry_price",     "left")}
              {th("EXIT",     "exit_price",      "left")}
              <th style={{ ...TH, borderRight: "2px solid var(--border2)", cursor: "default" }}>STOP</th>
              {th("RS",       "rs",              "center")}
              {th("VCS",      "vcs",             "center")}
              {th("READY",    "entry_readiness", "center")}
              {th("SECTOR",   "sector",          "left")}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0
              ? <tr><td colSpan={16} style={{ ...TD, textAlign: "center", padding: 24,
                  color: "var(--text3)" }}>No trades match this filter.</td></tr>
              : rows.map((r, i) => <TradeRow key={r.ticker} r={r} rank={i + 1} />)
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ── Main component ────────────────────────────────────────────────────────────
export default function Replay() {
  const [date,     setDate]    = useState("2023-10-26");
  const [loading,  setLoading] = useState(false);
  const [result,   setResult]  = useState(null);
  const [error,    setError]   = useState(null);
  const [view,     setView]    = useState("signals"); // signals | pipeline | backtest
  const [btLoading, setBtLoading] = useState(false);
  const [btResult,  setBtResult]  = useState(null);
  const [btError,   setBtError]   = useState(null);

  async function runBacktest(signals) {
    if (!signals || signals.length === 0) return;
    setBtLoading(true);
    setBtError(null);
    setBtResult(null);
    try {
      const res = await fetch(`${API}/api/replay/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ as_of_date: date, signals, max_bars: 20 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setBtResult(data);
      setView("backtest");
    } catch (e) {
      setBtError(e.message);
    } finally {
      setBtLoading(false);
    }
  }

  async function runReplay() {
    if (!date) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API}/api/replay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ as_of_date: date }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const page = {
    fontFamily: "'Inter',-apple-system,sans-serif", fontSize: 12,
    background: "var(--bg)", minHeight: "100vh", color: "var(--text)",
    padding: "16px 16px 40px",
  };

  // Pipeline rows from all_stocks
  const pipelineRows = (result?.all_stocks || []).filter(s => {
    const rs = s.rs || 0; const price = s.price || 0;
    const ma10 = s.ma10; const ma21 = s.ma21; const ma50 = s.ma50;
    if (rs < 80 || !ma10 || !ma21 || !ma50) return false;
    if (!(price > ma10 && price > ma21 && price > ma50)) return false;
    if (s.ma10_touch || s.ma21_touch || s.ma50_touch) return false;
    const pcts = [s.pct_from_ma10, s.pct_from_ma21, s.pct_from_ma50].filter(p => p != null && p > 0 && p <= 25);
    if (!pcts.length) return false;
    s.closest_pct = Math.min(...pcts);
    const idx = [s.pct_from_ma10, s.pct_from_ma21, s.pct_from_ma50].indexOf(s.closest_pct);
    s.closest_ma = ["MA10","MA21","MA50"][idx];
    return true;
  }).sort((a, b) => (a.closest_pct || 99) - (b.closest_pct || 99));

  const longSignals  = result?.long_signals  || [];
  const shortSignals = result?.short_signals || [];
  const allSignals   = [...longSignals, ...shortSignals];

  return (
    <div style={page}>
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px" }}>Historical Replay</h2>
        <p style={{ fontSize: 10, color: "var(--text3)", margin: 0 }}>
          Re-run the full scan as of any past date. See exactly which signals and pipeline stocks would have appeared — with your Core Stats and Entry Readiness scores.
        </p>
      </div>

      {/* Date picker + presets */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
        padding: "14px 16px", marginBottom: 16 }}>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <span style={{ fontSize: 10, color: "var(--text3)", fontWeight: 700, letterSpacing: 1 }}>DATE</span>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            max={new Date().toISOString().split("T")[0]}
            min="2020-01-01"
            style={{
              background: "var(--bg)", border: "1px solid var(--border2)", color: "var(--text)",
              padding: "6px 10px", borderRadius: 3, fontFamily: "inherit", fontSize: 12,
            }}
          />
          <button
            onClick={runReplay}
            disabled={loading || !date}
            style={{
              padding: "7px 20px", fontSize: 11, fontWeight: 700, cursor: loading ? "wait" : "pointer",
              borderRadius: 3, border: "1px solid var(--accent)", letterSpacing: 0.5,
              background: loading ? "rgba(41,98,255,0.3)" : "var(--accent)",
              color: loading ? "var(--text3)" : "#fff", fontFamily: "inherit", transition: "all 0.15s",
            }}>
            {loading ? "⏳ Running scan…" : "▶ Run Replay"}
          </button>
          {loading && (
            <span style={{ fontSize: 10, color: "var(--text3)" }}>
              Fetching historical data + running screener — takes 5–8 min for full universe…
            </span>
          )}
        </div>

        {/* Preset buttons */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, alignSelf: "center", marginRight: 4 }}>PRESETS:</span>
          {PRESETS.map(p => (
            <button key={p.date} title={p.desc}
              onClick={() => setDate(p.date)}
              style={{
                padding: "3px 10px", fontSize: 9, cursor: "pointer", borderRadius: 3,
                border: `1px solid ${date === p.date ? "var(--accent)" : "var(--border)"}`,
                background: date === p.date ? "rgba(41,98,255,0.1)" : "transparent",
                color: date === p.date ? "var(--accent)" : "var(--text3)",
                fontFamily: "inherit", letterSpacing: 0.3,
              }}>{p.label}</button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: "10px 14px", background: "rgba(242,54,69,0.08)", border: "1px solid rgba(242,54,69,0.3)",
          borderRadius: 6, color: "var(--red)", fontSize: 11, marginBottom: 14 }}>
          ✗ {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Replay banner */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 14px",
            background: "rgba(41,98,255,0.08)", border: "1px solid rgba(41,98,255,0.25)",
            borderRadius: 6, marginBottom: 14 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>
              ⏪ REPLAY: {result.replay_date}
            </span>
            <span style={{ fontSize: 10, color: "var(--text3)" }}>
              {result.total_scanned} stocks scanned · {(result.long_signals||[]).length} longs · {(result.short_signals||[]).length} shorts · {result.scan_duration_s}s
            </span>
            <span style={{ fontSize: 9, color: "var(--text3)", marginLeft: "auto" }}>
              Not cached — live historical data
            </span>
          </div>

          {/* Regime summary */}
          <RegimeSummary market={result.market} />

          {/* View toggle */}
          <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
            {[["signals", `Signals (${allSignals.length})`], ["pipeline", `Pipeline (${pipelineRows.length})`],
              ...(btResult ? [["backtest", `Backtest Results`]] : [])
            ].map(([v, l]) => (
              <button key={v} onClick={() => setView(v)} style={{
                padding: "5px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
                border: `1px solid ${view === v ? "var(--accent)" : "var(--border)"}`,
                background: view === v ? "rgba(41,98,255,0.1)" : "transparent",
                color: view === v ? "var(--accent)" : "var(--text3)",
                fontFamily: "inherit", fontWeight: view === v ? 700 : 400,
              }}>{l}</button>
            ))}
            <button
              onClick={() => runBacktest(longSignals)}
              disabled={btLoading || longSignals.length === 0}
              style={{
                marginLeft: "auto", padding: "5px 16px", fontSize: 10, fontWeight: 700,
                cursor: btLoading || !longSignals.length ? "not-allowed" : "pointer",
                borderRadius: 3, fontFamily: "inherit",
                border: "1px solid var(--green)",
                background: btLoading ? "rgba(8,153,129,0.1)" : "rgba(8,153,129,0.15)",
                color: btLoading ? "var(--text3)" : "var(--green)",
              }}>
              {btLoading ? "⏳ Running backtest…" : `▶ Backtest ${longSignals.length} Signals`}
            </button>
          </div>
          {btError && (
            <div style={{ padding: "8px 12px", background: "rgba(242,54,69,0.08)",
              border: "1px solid rgba(242,54,69,0.3)", borderRadius: 4,
              color: "var(--red)", fontSize: 11, marginBottom: 10 }}>✗ {btError}</div>
          )}

          {/* Readiness legend */}
          <div style={{ display: "flex", gap: 12, marginBottom: 12, fontSize: 9, color: "var(--text3)", flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontWeight: 700, letterSpacing: 1 }}>READINESS:</span>
            {[["5 ★","var(--green)","All criteria"],["4 ✓","var(--green)","ADR+EMA21L+ceiling OK"],
              ["3 ~","var(--yellow)","Partial — review"],["2 ✗","var(--red)","Issues present"],["1 ✗","var(--red)","Multiple issues — wait"]].map(([l,c,d]) => (
              <span key={l}><span style={{ fontWeight: 700, color: c }}>{l}</span> = {d}</span>
            ))}
          </div>

          {view === "signals" && (
            <>
              <ReplayTable rows={longSignals}  type="signal" title="Long Signals"  color="var(--green)" />
              <ReplayTable rows={shortSignals} type="signal" title="Short Signals" color="var(--red)"   />
            </>
          )}
          {view === "pipeline" && (
            <ReplayTable rows={pipelineRows} type="pipeline" title="Watchlist Pipeline" color="var(--accent)" />
          )}
          {view === "backtest" && btResult && (
            <BacktestResults result={btResult} />
          )}
        </>
      )}

      {!result && !loading && !error && (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--text3)",
          background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)" }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>⏪</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Pick a date and run replay</div>
          <div style={{ fontSize: 11 }}>The scan will fetch historical bar data and re-run your full screener pipeline as of that date.</div>
          <div style={{ fontSize: 11, marginTop: 6, opacity: 0.7 }}>Start with a known bull market date like Oct 26 2023 to validate signal quality.</div>
        </div>
      )}
    </div>
  );
}
