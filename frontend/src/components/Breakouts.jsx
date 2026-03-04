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

const rsCol   = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5bc27a" : r >= 70 ? "var(--yellow)" : "var(--text3)";
const rsBg    = r => r >= 90 ? "rgba(8,153,129,0.15)" : r >= 80 ? "rgba(8,153,129,0.08)" : r >= 70 ? "rgba(245,166,35,0.1)" : "transparent";
const vcsCol  = v => v == null ? "var(--text3)" : v <= 2 ? "var(--green)" : v <= 3.5 ? "#5bc27a" : v <= 5 ? "var(--yellow)" : "var(--red)";
const adrCol  = v => !v ? "var(--text3)" : (v >= 3.5 && v <= 8) ? "var(--green)" : v < 3.5 ? "var(--text3)" : "var(--yellow)";
const e21Col  = v => v == null ? "var(--text3)" : v < 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const chgCol  = v => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text3)";
const distCol = v => v < 2 ? "var(--red)" : v < 5 ? "var(--accent)" : v < 10 ? "var(--text2)" : "var(--text3)";
const scoreCol = v => v >= 8 ? "var(--green)" : v >= 6.5 ? "var(--accent)" : "var(--text3)";

const qualCol = q => q === "ideal" ? "var(--green)" : q === "good" ? "#5bc27a" : "var(--yellow)";
const qualBg  = q => q === "ideal" ? "rgba(8,153,129,0.15)" : q === "good" ? "rgba(8,153,129,0.08)" : "rgba(245,166,35,0.1)";

const watchCol = s => ["approaching_ma10","approaching_ma21"].includes(s) ? "var(--red)" : "var(--text3)";
const watchBg  = s => ["approaching_ma10","approaching_ma21"].includes(s) ? "rgba(242,54,69,0.08)" : "transparent";
const watchLabel = {
  approaching_ma10: "⚡ NEAR MA10",
  approaching_ma21: "⚡ NEAR MA21",
  extended_ma10:    "EXTENDED MA10",
  extended:         "EXTENDED",
};


const stageCol = s => s === "retesting" ? "var(--green)" : s === "launched" ? "var(--accent)" : "var(--yellow)";
const stageLbl = s => s === "retesting" ? "ON LEVEL" : s === "launched" ? "LAUNCHED" : "NEAR";
const maStackCol = v => v >= 3 ? "var(--green)" : v === 2 ? "var(--yellow)" : "var(--red)";

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

// ── Cup & Handle expanded detail ──────────────────────────────────────────────
function ExpandedCH({ s }) {
  return (
    <tr style={{ background: "rgba(8,153,129,0.02)" }}>
      <td colSpan={16} style={{ padding: "10px 16px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>CUP ANATOMY</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {[
                ["Left lip", pr(s.left_lip)], ["Cup bottom", pr(s.cup_bottom)],
                ["Cup depth", pct(s.cup_depth_pct)], ["Recovery", pct(s.recovery_pct)],
                ["Cup weeks", s.cup_weeks ? `${s.cup_weeks}wk` : "—"],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>HANDLE</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {[
                ["Handle days", s.handle_bars ?? "—"], ["Handle range", s.handle_range_pct != null ? `${fmt(s.handle_range_pct)}%` : "—"],
                ["Vol contracting", s.vol_contracting ? "✓ YES" : "—"], ["Vol today", s.vol_ratio ? `${s.vol_ratio}x` : "—"],
              ].map(([label, val]) => (
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
              {[["ENTRY", s.entry_pivot, "var(--accent)"], ["STOP", s.stop_price, "var(--red)"],
                ["T1", s.target_1, "var(--green)"], ["T2", s.target_2, "var(--green)"], ["T3", s.target_3, "var(--green)"]
              ].map(([lbl, val, col]) => val ? (
                <div key={lbl} style={{ padding: "4px 10px", borderRadius: 4, background: `${col}11`, border: `1px solid ${col}33` }}>
                  <div style={{ fontSize: 8, color: "var(--text3)" }}>{lbl}</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: col }}>{pr(val)}</div>
                  {s.entry_pivot && lbl !== "ENTRY" && (
                    <div style={{ fontSize: 8, color: col }}>{pct((val - s.entry_pivot) / s.entry_pivot * 100)}</div>
                  )}
                </div>
              ) : null)}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ── Cup & Handle row ──────────────────────────────────────────────────────────
function CupRow({ s, rank, expanded, onExpand, onQuickAdd, sortKey }) {
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  return (
    <>
      <tr onClick={onExpand} style={{ background: expanded ? "rgba(8,153,129,0.04)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(8,153,129,0.04)" : base}>
        <td style={{ ...TD, textAlign: "right", color: "var(--text3)", width: 28 }}>{rank}</td>
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>
        {/* Quality */}
        <td style={{ ...TD }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 9, fontWeight: 700, background: qualBg(s.cup_quality), color: qualCol(s.cup_quality),
            border: `1px solid ${qualCol(s.cup_quality)}40`, letterSpacing: 0.5 }}>
            {(s.cup_quality || "—").toUpperCase()}
          </span>
        </td>
        {/* RS */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3, fontWeight: 700,
            fontSize: 12, background: rsBg(s.rs), color: rsCol(s.rs),
            border: `1px solid ${rsCol(s.rs)}40`, minWidth: 32, textAlign: "center" }}>{s.rs ?? "—"}</span>
        </td>
        {/* Sector */}
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10 }}>{s.sector || "—"}</td>
        {/* Price */}
        <td style={{ ...TD, fontWeight: 600 }}>{pr(s.price)}</td>
        {/* CHG */}
        <td style={{ ...TD, fontWeight: 600, color: chgCol(s.chg || 0), borderRight: "2px solid var(--border2)" }}>
          {pct(s.chg)}
        </td>
        {/* READY */}
        <td style={{ ...TD, textAlign: "center" }}><ReadinessBadge v={s.entry_readiness} /></td>
        {/* ADR% */}
        <td style={{ ...TD, fontWeight: 600, color: adrCol(s.adr_pct), textAlign: "center" }}>
          {s.adr_pct != null ? `${fmt(s.adr_pct)}%` : "—"}
        </td>
        {/* EMA21L% */}
        <td style={{ ...TD, fontWeight: 600, color: e21Col(s.ema21_low_pct), textAlign: "center" }}>
          {s.ema21_low_pct != null ? `${fmt(s.ema21_low_pct)}%` : "—"}
        </td>
        {/* 3WT */}
        <td style={{ ...TD, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {s.three_weeks_tight
            ? <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 10 }}>✦</span>
            : <span style={{ color: "var(--border2)" }}>·</span>}
        </td>
        {/* VCS */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: vcsCol(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>
        {/* From pivot */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: distCol(s.dist_from_pivot || 99) }}>
          {s.dist_from_pivot != null ? `${fmt(s.dist_from_pivot)}%` : "—"}
        </td>
        {/* Score */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: scoreCol(s.signal_score) }}>
          {s.signal_score != null ? Number(s.signal_score).toFixed(1) : "—"}
        </td>
        {/* Journal */}
        <td style={{ ...TD }} onClick={e => e.stopPropagation()}>
          <button onClick={() => onQuickAdd?.({ ...s, signal_type: "CUP_HANDLE", entry_price: s.entry_pivot })}
            style={{ padding: "2px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--accent)", background: "transparent",
              color: "var(--accent)", fontFamily: "inherit" }}>+ Journal</button>
        </td>
        <td style={{ ...TD, color: "var(--text3)", textAlign: "center", width: 24 }}>{expanded ? "▲" : "▼"}</td>
      </tr>
      {expanded && <ExpandedCH s={s} />}
    </>
  );
}

// ── Extended BO expanded detail ───────────────────────────────────────────────
function ExpandedExt({ s }) {
  return (
    <tr style={{ background: "rgba(245,166,35,0.02)" }}>
      <td colSpan={12} style={{ padding: "10px 16px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>CONTEXT</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {[
                ["52W High", pr(s.high_52w)], ["Dist from high", pct(s.dist_from_high)],
                ["Vol surge", s.vol_surge ? `${s.vol_surge}x` : "—"], ["VCS", s.vcs ?? "—"],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>SECOND ENTRY ZONES</div>
            <div style={{ display: "flex", gap: 8 }}>
              {s.ma10_entry && (
                <div style={{ padding: "4px 10px", borderRadius: 4, background: "rgba(242,54,69,0.08)", border: "1px solid rgba(242,54,69,0.3)" }}>
                  <div style={{ fontSize: 8, color: "var(--text3)" }}>MA10 ENTRY</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--red)" }}>{pr(s.ma10_entry)}</div>
                </div>
              )}
              {s.ma21_entry && (
                <div style={{ padding: "4px 10px", borderRadius: 4, background: "rgba(41,98,255,0.08)", border: "1px solid rgba(41,98,255,0.3)" }}>
                  <div style={{ fontSize: 8, color: "var(--text3)" }}>MA21 ENTRY</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{pr(s.ma21_entry)}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ── Extended BO row ───────────────────────────────────────────────────────────
function ExtRow({ s, rank, expanded, onExpand, onQuickAdd }) {
  const isUrgent = ["approaching_ma10","approaching_ma21"].includes(s.watch_status);
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  return (
    <>
      <tr onClick={onExpand} style={{ background: expanded ? "rgba(41,98,255,0.04)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(41,98,255,0.04)" : base}>
        <td style={{ ...TD, textAlign: "right", color: "var(--text3)", width: 28 }}>{rank}</td>
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>
        {/* Watch status */}
        <td style={{ ...TD }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 8, fontWeight: 700, background: watchBg(s.watch_status),
            color: watchCol(s.watch_status), border: `1px solid ${watchCol(s.watch_status)}40`, letterSpacing: 0.5 }}>
            {watchLabel[s.watch_status] || s.watch_status?.toUpperCase() || "—"}
          </span>
        </td>
        {/* RS */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3, fontWeight: 700,
            fontSize: 12, background: rsBg(s.rs), color: rsCol(s.rs),
            border: `1px solid ${rsCol(s.rs)}40`, minWidth: 32, textAlign: "center" }}>{s.rs ?? "—"}</span>
        </td>
        {/* Sector */}
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10 }}>{s.sector || "—"}</td>
        {/* Price */}
        <td style={{ ...TD, fontWeight: 600 }}>{pr(s.price)}</td>
        {/* CHG */}
        <td style={{ ...TD, fontWeight: 600, color: chgCol(s.chg || 0), borderRight: "2px solid var(--border2)" }}>
          {pct(s.chg)}
        </td>
        {/* From MA10 */}
        <td style={{ ...TD, textAlign: "center", color: (s.pct_from_ma10 || 99) <= 5 ? "var(--red)" : "var(--text2)", fontWeight: 600 }}>
          {s.pct_from_ma10 != null ? `+${fmt(s.pct_from_ma10)}%` : "—"}
        </td>
        {/* From MA21 */}
        <td style={{ ...TD, textAlign: "center", color: (s.pct_from_ma21 || 99) <= 8 ? "var(--accent)" : "var(--text2)", fontWeight: 600, borderRight: "2px solid var(--border2)" }}>
          {s.pct_from_ma21 != null ? `+${fmt(s.pct_from_ma21)}%` : "—"}
        </td>
        {/* VCS */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: vcsCol(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>
        {/* Watch */}
        <td style={{ ...TD }} onClick={e => e.stopPropagation()}>
          <button onClick={() => onQuickAdd?.({ ...s, signal_type: "EXTENDED_BO" })}
            style={{ padding: "2px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--accent)", background: "transparent",
              color: "var(--accent)", fontFamily: "inherit" }}>+ Watch</button>
        </td>
        <td style={{ ...TD, color: "var(--text3)", textAlign: "center", width: 24 }}>{expanded ? "▲" : "▼"}</td>
      </tr>
      {expanded && <ExpandedExt s={s} />}
    </>
  );
}


// ── Weekly Retest expanded ────────────────────────────────────────────────────
function ExpandedRetest({ s }) {
  return (
    <tr style={{ background: "rgba(122,74,138,0.03)" }}>
      <td colSpan={14} style={{ padding: "10px 16px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>RESISTANCE LEVEL</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {[
                ["Resistance", pr(s.resistance)],
                ["Breakout close", pr(s.breakout_close)],
                ["Retest low", pr(s.retest_low)],
                ["Retest candles", s.retest_candles ?? "—"],
                ["Wks since BO", s.weeks_since_bo ?? "—"],
                ["Resistance touches", s.resistance_touches ?? "—"],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, fontWeight: 700, marginBottom: 6 }}>RETEST QUALITY</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {[
                ["Avg weekly range", s.avg_range_pct != null ? `${fmt(s.avg_range_pct)}%` : "—"],
                ["Vol contraction", s.vol_contraction != null ? `${fmt(s.vol_contraction)}x` : "—"],
                ["Weekly MA stack", `${s.ma_stack}/3`],
                ["EMA10w", pr(s.ema10_w)],
                ["SMA21w", pr(s.sma21_w)],
                ["SMA50w", pr(s.sma50_w)],
              ].map(([label, val]) => (
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
              {[["ENTRY", s.entry, "var(--accent)"], ["STOP", s.stop_price, "var(--red)"],
                ["T1", s.target_1, "var(--green)"], ["T2", s.target_2, "var(--green)"], ["T3", s.target_3, "var(--green)"]
              ].map(([lbl, val, col]) => val ? (
                <div key={lbl} style={{ padding: "4px 10px", borderRadius: 4, background: `${col}11`, border: `1px solid ${col}33` }}>
                  <div style={{ fontSize: 8, color: "var(--text3)" }}>{lbl}</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: col }}>{pr(val)}</div>
                  {s.entry && lbl !== "ENTRY" && (
                    <div style={{ fontSize: 8, color: col }}>{pct((val - s.entry) / s.entry * 100)}</div>
                  )}
                </div>
              ) : null)}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ── Weekly Retest row ─────────────────────────────────────────────────────────
function RetestRow({ s, rank, expanded, onExpand, onQuickAdd }) {
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  const distAbs = Math.abs(s.pct_from_resistance || 0);
  const distCol2 = distAbs <= 1 ? "var(--green)" : distAbs <= 3 ? "var(--accent)" : "var(--yellow)";
  return (
    <>
      <tr onClick={onExpand} style={{ background: expanded ? "rgba(122,74,138,0.05)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(122,74,138,0.05)" : base}>
        <td style={{ ...TD, textAlign: "right", color: "var(--text3)", width: 28 }}>{rank}</td>
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>
        {/* Stage */}
        <td style={{ ...TD }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 8, fontWeight: 700,
            background: `${stageCol(s.stage)}18`, color: stageCol(s.stage),
            border: `1px solid ${stageCol(s.stage)}40`, letterSpacing: 0.5 }}>
            {stageLbl(s.stage)}
          </span>
        </td>
        {/* RS */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3, fontWeight: 700,
            fontSize: 12, background: rsBg(s.rs), color: rsCol(s.rs),
            border: `1px solid ${rsCol(s.rs)}40`, minWidth: 32, textAlign: "center" }}>{s.rs ?? "—"}</span>
        </td>
        {/* Sector */}
        <td style={{ ...TD, color: "var(--text3)", fontSize: 10 }}>{s.sector || "—"}</td>
        {/* Price */}
        <td style={{ ...TD, fontWeight: 600 }}>{pr(s.price)}</td>
        {/* CHG */}
        <td style={{ ...TD, fontWeight: 600, color: chgCol(s.chg || 0), borderRight: "2px solid var(--border2)" }}>
          {pct(s.chg)}
        </td>
        {/* Resistance */}
        <td style={{ ...TD, fontWeight: 600 }}>{pr(s.resistance)}</td>
        {/* Dist from resistance */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: distCol2 }}>
          {s.pct_from_resistance != null ? `${s.pct_from_resistance > 0 ? "+" : ""}${fmt(s.pct_from_resistance)}%` : "—"}
        </td>
        {/* Retest candles */}
        <td style={{ ...TD, textAlign: "center", color: "var(--text2)" }}>
          {s.retest_candles ?? "—"}w
        </td>
        {/* Vol contraction */}
        <td style={{ ...TD, textAlign: "center",
          color: (s.vol_contraction || 1) < 0.7 ? "var(--green)" : (s.vol_contraction || 1) < 0.85 ? "var(--yellow)" : "var(--text3)", fontWeight: 600 }}>
          {s.vol_contraction != null ? `${fmt(s.vol_contraction)}x` : "—"}
        </td>
        {/* MA stack */}
        <td style={{ ...TD, textAlign: "center", fontWeight: 700, color: maStackCol(s.ma_stack || 0) }}>
          {s.ma_stack ?? "—"}/3
        </td>
        {/* Score */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: scoreCol(s.signal_score) }}>
          {s.signal_score != null ? Number(s.signal_score).toFixed(1) : "—"}
        </td>
        <td style={{ ...TD }} onClick={e => e.stopPropagation()}>
          <button onClick={() => onQuickAdd?.({ ...s, signal_type: "WEEKLY_BO_RETEST", entry_price: s.entry })}
            style={{ padding: "2px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--accent)", background: "transparent",
              color: "var(--accent)", fontFamily: "inherit" }}>+ Journal</button>
        </td>
        <td style={{ ...TD, color: "var(--text3)", textAlign: "center", width: 24 }}>{expanded ? "▲" : "▼"}</td>
      </tr>
      {expanded && <ExpandedRetest s={s} />}
    </>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Breakouts({ onQuickAdd }) {
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [tab,      setTab]      = useState("cup_handle");
  const [filter,   setFilter]   = useState("all");
  const [sortKey,  setSortKey]  = useState("signal_score");
  const [sortDir,  setSortDir]  = useState(-1);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try { setLoading(true); const r = await fetch(`${API}/api/breakouts`); setData(await r.json()); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: 24, color: "var(--text3)" }}>Loading breakouts…</div>;

  const cupHandle    = data?.cup_handle    || [];
  const extendedBO   = data?.extended_bo   || [];
  const weeklyRetest = data?.weekly_retest || [];
  const urgentExt    = extendedBO.filter(s => ["approaching_ma10","approaching_ma21"].includes(s.watch_status));

  let chRows = filter === "ideal"    ? cupHandle.filter(s => s.cup_quality === "ideal")
             : filter === "imminent" ? cupHandle.filter(s => (s.dist_from_pivot || 99) <= 3)
             : [...cupHandle];
  chRows = chRows.sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  let extRows = [...extendedBO].sort((a, b) => {
    // Urgent first, then by pct_from_ma10
    const ua = ["approaching_ma10","approaching_ma21"].includes(a.watch_status) ? 0 : 1;
    const ub = ["approaching_ma10","approaching_ma21"].includes(b.watch_status) ? 0 : 1;
    if (ua !== ub) return ua - ub;
    return (a.pct_from_ma10 || 99) - (b.pct_from_ma10 || 99);
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

  const page = { fontFamily: "'Inter',sans-serif", fontSize: 12, padding: "16px 16px 40px",
    color: "var(--text)", background: "var(--bg)", minHeight: "100vh" };

  return (
    <div style={page}>
      {/* Header */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 2 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Breakout Setups</h2>
          <span style={{ fontSize: 10, color: "var(--text3)" }}>{data?.scanned_at || "—"}</span>
        </div>
        <p style={{ fontSize: 10, color: "var(--text3)", margin: 0 }}>
          Cup & Handle setups forming near pivot · Extended breakouts watching for MA pullback re-entry
        </p>
      </div>

      {/* Summary chips */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {[
          { l: "Cup & Handle",   n: cupHandle.length,                                              col: "var(--green)",  sub: "forming patterns" },
          { l: "Ideal quality",  n: cupHandle.filter(s=>s.cup_quality==="ideal").length,            col: "var(--green)",  sub: "tight + vol dry" },
          { l: "Within 3%",      n: cupHandle.filter(s=>(s.dist_from_pivot||99)<=3).length,        col: "var(--accent)", sub: "imminent pivot" },
          { l: "Extended watch", n: extendedBO.length,                                              col: "var(--text3)",  sub: "wait for pullback" },
          { l: "Near MA now",    n: urgentExt.length,                                              col: "var(--red)",    sub: "⚡ approaching MA" },
          { l: "Weekly Retests",  n: weeklyRetest.length,                                           col: "var(--purple)", sub: "BO→retest setups" },
        ].map(c => (
          <div key={c.l} style={{ padding: "8px 14px", borderRadius: 6,
            border: `1px solid ${c.col}44`, background: `${c.col}0d`, textAlign: "center", minWidth: 90 }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.col }}>{c.n}</div>
            <div style={{ fontSize: 9, fontWeight: 700, color: c.col }}>{c.l}</div>
            <div style={{ fontSize: 8, color: "var(--text3)" }}>{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: 5, marginBottom: 14 }}>
        {[["cup_handle", `☕ Cup & Handle (${cupHandle.length})`], ["extended", `👀 Extended Watch (${extendedBO.length})`], ["weekly_retest", `🔁 Weekly Retest (${weeklyRetest.length})`]].map(([v, l]) => (
          <button key={v} onClick={() => { setTab(v); setExpanded(null); }} style={{
            padding: "5px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
            border: `1px solid ${tab === v ? "var(--accent)" : "var(--border)"}`,
            background: tab === v ? "rgba(41,98,255,0.08)" : "transparent",
            color: tab === v ? "var(--accent)" : "var(--text3)",
            fontFamily: "inherit", fontWeight: tab === v ? 700 : 400,
          }}>
            {l}
            {v === "extended" && urgentExt.length > 0 && (
              <span style={{ color: "var(--red)", fontWeight: 700, marginLeft: 4 }}>· {urgentExt.length} urgent</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Cup & Handle tab ── */}
      {tab === "cup_handle" && (
        <>
          <div style={{ display: "flex", gap: 5, marginBottom: 12 }}>
            {[["all",`All (${cupHandle.length})`],["ideal","Ideal only"],["imminent","Within 3% of pivot"]].map(([v,l]) => (
              <button key={v} onClick={() => setFilter(v)} style={{
                padding: "3px 9px", fontSize: 9, cursor: "pointer", borderRadius: 3,
                border: `1px solid ${filter===v?"var(--accent)":"var(--border)"}`,
                background: filter===v?"rgba(41,98,255,0.08)":"transparent",
                color: filter===v?"var(--accent)":"var(--text3)", fontFamily: "inherit",
              }}>{l}</button>
            ))}
          </div>
          {chRows.length === 0 ? (
            <div style={{ color: "var(--text3)", padding: 24, textAlign: "center" }}>
              {cupHandle.length === 0 ? "No cup & handle patterns detected." : "No patterns match this filter."}
            </div>
          ) : (
            <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 920 }}>
                <thead>
                  <tr style={{ background: "var(--bg3)" }}>
                    <th colSpan={7} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>SETUP</th>
                    <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>CORE STATS</th>
                    <th colSpan={5} style={{ ...TH, fontSize: 8, textAlign: "center", cursor: "default" }}>METRICS</th>
                  </tr>
                  <tr>
                    <th style={{ ...TH, width: 28, cursor: "default" }}>#</th>
                    {th("TICKER",   "ticker")}
                    {th("QUALITY",  "cup_quality")}
                    {th("RS",       "rs", "center")}
                    {th("SECTOR",   "sector")}
                    {th("PRICE",    "price")}
                    <th style={{ ...TH, borderRight: "2px solid var(--border2)", cursor: "default" }}>CHG</th>
                    {th("READY",    "entry_readiness", "center")}
                    {th("ADR%",     "adr_pct", "center")}
                    {th("EMA21L%",  "ema21_low_pct", "center")}
                    <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)", cursor: "default" }}>3WT</th>
                    {th("VCS",      "vcs", "center")}
                    {th("FROM PIV", "dist_from_pivot", "center")}
                    {th("SCORE",    "signal_score", "center")}
                    <th style={{ ...TH, cursor: "default" }}></th>
                    <th style={{ ...TH, cursor: "default" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {chRows.map((s, i) => (
                    <CupRow key={s.ticker} s={s} rank={i+1}
                      expanded={expanded === `ch-${s.ticker}`}
                      onExpand={() => setExpanded(expanded === `ch-${s.ticker}` ? null : `ch-${s.ticker}`)}
                      onQuickAdd={onQuickAdd} sortKey={sortKey} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Weekly Retest tab ── */}
      {tab === "weekly_retest" && (
        <>
          <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 12 }}>
            Stock broke a major weekly resistance, pulled back to retest it as support, then consolidated tightly.
            <b style={{ color: "var(--purple)" }}> ON LEVEL</b> = sitting right on resistance now (prime entry).
            <b style={{ color: "var(--accent)" }}> LAUNCHED</b> = already moving up from the retest.
          </div>
          {weeklyRetest.length === 0 ? (
            <div style={{ color: "var(--text3)", padding: 24, textAlign: "center" }}>
              No weekly retest setups detected. Scan needed, or no setups qualify.
            </div>
          ) : (
            <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 860 }}>
                <thead>
                  <tr style={{ background: "var(--bg3)" }}>
                    <th colSpan={7} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>SETUP</th>
                    <th colSpan={5} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>RETEST QUALITY</th>
                    <th colSpan={3} style={{ ...TH, fontSize: 8, textAlign: "center", cursor: "default" }}>ACTION</th>
                  </tr>
                  <tr>
                    <th style={{ ...TH, width: 28, cursor: "default" }}>#</th>
                    <th style={{ ...TH }}>TICKER</th>
                    <th style={{ ...TH }}>STAGE</th>
                    <th style={{ ...TH, textAlign: "center" }}>RS</th>
                    <th style={{ ...TH }}>SECTOR</th>
                    <th style={{ ...TH }}>PRICE</th>
                    <th style={{ ...TH, borderRight: "2px solid var(--border2)" }}>CHG</th>
                    <th style={{ ...TH }}>RESIST</th>
                    <th style={{ ...TH, textAlign: "center" }}>FROM LVL</th>
                    <th style={{ ...TH, textAlign: "center" }}>RETEST W</th>
                    <th style={{ ...TH, textAlign: "center" }}>VOL CONT</th>
                    <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)" }}>MA STACK</th>
                    <th style={{ ...TH, textAlign: "center" }}>SCORE</th>
                    <th style={{ ...TH, cursor: "default" }}></th>
                    <th style={{ ...TH, cursor: "default" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {weeklyRetest.map((s, i) => (
                    <RetestRow key={s.ticker} s={s} rank={i + 1}
                      expanded={expanded === `rt-${s.ticker}`}
                      onExpand={() => setExpanded(expanded === `rt-${s.ticker}` ? null : `rt-${s.ticker}`)}
                      onQuickAdd={onQuickAdd} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Extended Watch tab ── */}
      {tab === "extended" && (
        <>
          <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 12 }}>
            Already broke out. Too extended to buy — watch for MA10/MA21 pullback for second entry.
            Urgent rows are approaching the MA right now.
          </div>
          {extRows.length === 0 ? (
            <div style={{ color: "var(--text3)", padding: 24, textAlign: "center" }}>No extended breakouts detected.</div>
          ) : (
            <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 800 }}>
                <thead>
                  <tr style={{ background: "var(--bg3)" }}>
                    <th colSpan={7} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>SETUP</th>
                    <th colSpan={2} style={{ ...TH, fontSize: 8, textAlign: "center",
                      borderRight: "2px solid var(--border2)", cursor: "default" }}>MA DISTANCE</th>
                    <th colSpan={3} style={{ ...TH, fontSize: 8, textAlign: "center", cursor: "default" }}>ACTION</th>
                  </tr>
                  <tr>
                    <th style={{ ...TH, width: 28, cursor: "default" }}>#</th>
                    <th style={{ ...TH }}>TICKER</th>
                    <th style={{ ...TH }}>STATUS</th>
                    <th style={{ ...TH, textAlign: "center" }}>RS</th>
                    <th style={{ ...TH }}>SECTOR</th>
                    <th style={{ ...TH }}>PRICE</th>
                    <th style={{ ...TH, borderRight: "2px solid var(--border2)", cursor: "default" }}>CHG</th>
                    <th style={{ ...TH, textAlign: "center" }}>FROM MA10</th>
                    <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)" }}>FROM MA21</th>
                    <th style={{ ...TH, textAlign: "center" }}>VCS</th>
                    <th style={{ ...TH, cursor: "default" }}></th>
                    <th style={{ ...TH, cursor: "default" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {extRows.map((s, i) => (
                    <ExtRow key={s.ticker} s={s} rank={i+1}
                      expanded={expanded === `ext-${s.ticker}`}
                      onExpand={() => setExpanded(expanded === `ext-${s.ticker}` ? null : `ext-${s.ticker}`)}
                      onQuickAdd={onQuickAdd} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
