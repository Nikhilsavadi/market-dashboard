import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const NYSE = new Set([
  "V","MA","JPM","BAC","GS","MS","WFC","C","AXP","BLK","BX","KO","PEP","PG",
  "JNJ","MRK","ABT","LLY","PFE","CVX","XOM","OXY","COP","SLB","BA","CAT",
  "DE","HON","GE","GEV","ETN","UPS","RTX","LMT","HD","WMT","TGT","COST",
  "LOW","NKE","MCD","SBUX","CMG","T","VZ","DIS","CMCSA","NEE","DUK","SO",
  "AMT","CCI","SPG","PSA","O","MCO","SPGI","AIG","MET","PRU","SYK",
  "BSX","MDT","TMO","UNH","CVS","HUM","USB","PNC","IBM","HPE","WDC",
]);
const tvUrl = t => `https://www.tradingview.com/chart/?symbol=${NYSE.has(t)?"NYSE":"NASDAQ"}:${t.replace(".","–")}`;

// ── colour helpers ────────────────────────────────────────────────────────────
const rsCol  = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5bc27a" : r >= 70 ? "var(--yellow)" : "var(--text3)";
const rsBg   = r => r >= 90 ? "rgba(8,153,129,0.15)" : r >= 80 ? "rgba(8,153,129,0.08)" : r >= 70 ? "rgba(245,166,35,0.1)" : "transparent";
const adrCol = v => !v ? "var(--text3)" : (v >= 3.5 && v <= 8) ? "var(--green)" : v < 3.5 ? "var(--text3)" : "var(--yellow)";
const adrBg  = v => (v >= 3.5 && v <= 8) ? "rgba(8,153,129,0.1)" : "transparent";
const e21Col = v => v == null ? "var(--text3)" : v < 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const e21Bg  = v => v == null ? "transparent" : v < 5 ? "rgba(8,153,129,0.1)" : v <= 8 ? "rgba(245,166,35,0.08)" : "rgba(242,54,69,0.08)";
const vcsCol = v => v == null ? "var(--text3)" : v <= 2 ? "var(--green)" : v <= 3.5 ? "#5bc27a" : v <= 5 ? "var(--yellow)" : "var(--red)";
const chgCol = v => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text3)";
const distCol = v => v < 2 ? "var(--red)" : v < 5 ? "var(--accent)" : v < 10 ? "var(--text2)" : "var(--text3)";
const scoreCol = v => v >= 8 ? "var(--green)" : v >= 6.5 ? "var(--accent)" : "var(--text3)";


function ReadinessBadge({ v }) {
  if (v == null) return <span style={{ color: "var(--text3)" }}>—</span>;
  const map = [
    null,
    { bg: "rgba(242,54,69,0.12)",  col: "var(--red)",    label: "1 ✗" },
    { bg: "rgba(242,54,69,0.08)",  col: "var(--red)",    label: "2 ✗" },
    { bg: "rgba(245,166,35,0.12)", col: "var(--yellow)", label: "3 ~" },
    { bg: "rgba(8,153,129,0.1)",   col: "var(--green)",  label: "4 ✓" },
    { bg: "rgba(8,153,129,0.18)",  col: "var(--green)",  label: "5 ★" },
  ];
  const c = map[Math.min(5, Math.max(1, Math.round(v)))];
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 3,
      fontSize: 11, fontWeight: 700, background: c.bg, color: c.col,
      border: `1px solid ${c.col}40`, minWidth: 36, textAlign: "center",
    }}>{c.label}</span>
  );
}

const TD = { padding: "6px 10px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", fontSize: 12 };
const TH = {
  padding: "6px 10px", borderBottom: "2px solid var(--border)", fontSize: 9,
  letterSpacing: 1, textTransform: "uppercase", color: "var(--text3)", fontWeight: 700,
  whiteSpace: "nowrap", background: "var(--bg2)", cursor: "pointer", userSelect: "none",
};

const maBadgeCol = { MA10: "var(--cyan)", MA21: "var(--purple)", MA50: "var(--yellow)" };

function Row({ s, rank, expanded, onExpand }) {
  const base = rank % 2 === 0 ? "var(--bg)" : "rgba(240,243,250,0.4)";
  const hl   = "rgba(41,98,255,0.05)";

  return (
    <>
      <tr
        onClick={onExpand}
        style={{ background: expanded ? hl : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? hl : base}
      >
        {/* # */}
        <td style={{ ...TD, color: "var(--text3)", textAlign: "right", width: 28, paddingRight: 6 }}>{rank}</td>

        {/* Ticker */}
        <td style={{ ...TD, fontWeight: 700, width: 80 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>

        {/* RS — prominent */}
        <td style={{ ...TD, textAlign: "center", width: 56 }}>
          <span style={{
            display: "inline-block", padding: "3px 8px", borderRadius: 3,
            fontWeight: 700, fontSize: 12, background: rsBg(s.rs), color: rsCol(s.rs),
            minWidth: 32, textAlign: "center",
          }}>{s.rs}</span>
        </td>

        {/* Sector */}
        <td style={{ ...TD, color: "var(--text3)", fontSize: 11, maxWidth: 100,
          overflow: "hidden", textOverflow: "ellipsis" }}>{s.sector || "—"}</td>

        {/* Price */}
        <td style={{ ...TD, fontWeight: 600, color: "var(--text)" }}>
          ${s.price != null ? Number(s.price).toFixed(2) : "—"}
        </td>

        {/* CHG — separator after */}
        <td style={{ ...TD, fontWeight: 600, color: chgCol(s.chg || 0),
          borderRight: "2px solid var(--border2)" }}>
          {s.chg != null ? `${s.chg > 0 ? "+" : ""}${s.chg.toFixed(1)}%` : "—"}
        </td>

        {/* Readiness */}
        <td style={{ ...TD, textAlign: "center" }}>
          <ReadinessBadge v={s.entry_readiness} />
        </td>

        {/* ADR % */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center",
          color: adrCol(s.adr_pct), background: adrBg(s.adr_pct) }}>
          {s.adr_pct != null ? `${s.adr_pct.toFixed(1)}%` : "—"}
        </td>

        {/* EMA21L % */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center",
          color: e21Col(s.ema21_low_pct), background: e21Bg(s.ema21_low_pct) }}>
          {s.ema21_low_pct != null ? `${s.ema21_low_pct.toFixed(1)}%` : "—"}
        </td>

        {/* 3WT — separator after */}
        <td style={{ ...TD, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {s.three_weeks_tight
            ? <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 14 }}>✦</span>
            : <span style={{ color: "var(--border2)", fontSize: 10 }}>·</span>}
        </td>

        {/* VCS */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center", color: vcsCol(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>

        {/* Near MA */}
        <td style={{ ...TD, textAlign: "center" }}>
          {s.closest_ma ? (
            <span style={{
              display: "inline-block", padding: "2px 7px", borderRadius: 3,
              fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
              background: `${maBadgeCol[s.closest_ma] || "var(--text3)"}18`,
              color: maBadgeCol[s.closest_ma] || "var(--text3)",
              border: `1px solid ${maBadgeCol[s.closest_ma] || "var(--text3)"}40`,
            }}>{s.closest_ma}</span>
          ) : "—"}
        </td>

        {/* Dist % */}
        <td style={{ ...TD, fontWeight: 700, color: distCol(s.closest_pct || 99) }}>
          {s.closest_pct != null ? `${s.closest_pct.toFixed(1)}%` : "—"}
        </td>

        {/* Score */}
        <td style={{ ...TD, fontWeight: 700, textAlign: "center",
          color: scoreCol(s.signal_score || 0) }}>
          {s.signal_score != null ? s.signal_score.toFixed(1) : "—"}
        </td>
      </tr>

      {/* Expanded detail */}
      {expanded && (
        <tr style={{ background: "rgba(41,98,255,0.03)" }}>
          <td colSpan={13} style={{ padding: "10px 16px 12px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 11, alignItems: "center" }}>
              {[
                ["MA10",     s.ma10],
                ["MA21",     s.ma21],
                ["MA50",     s.ma50],
                ["EMA21 LOW", s.ema21_low],
                ["ATR",      s.atr ? `$${Number(s.atr).toFixed(2)}` : null],
                ["52W HIGH", s.w52_high],
              ].map(([l, v]) => (
                <div key={l}>
                  <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 4 }}>{l}</span>
                  <span style={{ fontWeight: 600, color: l === "EMA21 LOW" ? "var(--green)" : "var(--text)" }}>
                    {l === "ATR" ? (v || "—") : (v != null ? `$${Number(v).toFixed(2)}` : "—")}
                  </span>
                </div>
              ))}
              {/* Risk label */}
              {s.ema21_low_pct != null && (
                <span style={{
                  padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700, letterSpacing: 0.8,
                  background: e21Bg(s.ema21_low_pct), color: e21Col(s.ema21_low_pct),
                  border: `1px solid ${e21Col(s.ema21_low_pct)}40`,
                }}>
                  {s.ema21_low_pct.toFixed(1)}% to EMA21 Low —
                  {s.ema21_low_pct < 5 ? " LOW RISK ✓" : s.ema21_low_pct <= 8 ? " MODERATE" : " TOO WIDE — SKIP"}
                </span>
              )}
              {s.three_weeks_tight && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(8,153,129,0.12)", color: "var(--green)", border: "1px solid rgba(8,153,129,0.3)" }}>
                  ✦ 3-WEEKS TIGHT
                </span>
              )}
              {s.vol_ratio >= 1.5 && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(8,153,129,0.1)", color: "var(--green)", border: "1px solid rgba(8,153,129,0.25)" }}>
                  VOL {s.vol_ratio.toFixed(2)}×
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Pipeline() {
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [filter,   setFilter]   = useState("all");
  const [sortKey,  setSortKey]  = useState("rs");
  const [sortDir,  setSortDir]  = useState(-1);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const r = await fetch(`${API}/api/pipeline`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const page = {
    fontFamily: "'Inter',-apple-system,sans-serif", fontSize: 12,
    background: "var(--bg)", minHeight: "100vh", color: "var(--text)",
    padding: "16px 16px 40px",
  };

  if (loading) return <div style={{ ...page, color: "var(--text3)" }}>Loading pipeline...</div>;
  if (error || !data?.pipeline?.length) return (
    <div style={page}>
      <p style={{ color: "var(--red)" }}>{error || "No pipeline stocks. Run a scan first."}</p>
    </div>
  );

  const pipeline = data.pipeline;

  const filterMap = {
    imminent: s => s.closest_pct < 3,
    close:    s => s.closest_pct < 7,
    ma10:     s => s.closest_ma === "MA10",
    ma21:     s => s.closest_ma === "MA21",
    ma50:     s => s.closest_ma === "MA50",
    valid:    s => s.adr_pct >= 3.5 && s.adr_pct <= 8 && s.ema21_low_pct != null && s.ema21_low_pct < 8,
    tight:    s => s.three_weeks_tight,
  };

  let stocks = filterMap[filter] ? pipeline.filter(filterMap[filter]) : [...pipeline];
  stocks.sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  const counts = {
    imminent: pipeline.filter(s => s.closest_pct < 3).length,
    close:    pipeline.filter(s => s.closest_pct >= 3 && s.closest_pct < 7).length,
    watching: pipeline.filter(s => s.closest_pct >= 7).length,
    valid:    pipeline.filter(filterMap.valid).length,
    tight:    pipeline.filter(filterMap.tight).length,
  };

  function thClick(key, defaultDir = -1) {
    setSortKey(key);
    setSortDir(sortKey === key ? sortDir * -1 : defaultDir);
  }

  function Th({ label, k, align = "left", title = "", defaultDir = -1, sep = false }) {
    const active = sortKey === k;
    return (
      <th title={title} onClick={() => thClick(k, defaultDir)}
        style={{
          ...TH, textAlign: align,
          color: active ? "var(--accent)" : "var(--text3)",
          borderRight: sep ? "2px solid var(--border2)" : undefined,
        }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  const filterBtns = [
    { val: "all",      label: `All  ${pipeline.length}` },
    { val: "imminent", label: `< 3%  ${counts.imminent}` },
    { val: "close",    label: `< 7%  ${counts.close}` },
    { val: "ma10",     label: "MA10" },
    { val: "ma21",     label: "MA21" },
    { val: "ma50",     label: "MA50" },
    { val: "valid",    label: `ADR+Risk ✓  ${counts.valid}` },
    { val: "tight",    label: `3WT ✦  ${counts.tight}` },
  ];

  return (
    <div style={page}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Watchlist Pipeline</h2>
        <span style={{ fontSize: 10, color: "var(--text3)" }}>
          {pipeline.length} RS leaders approaching buy zones · {data.scanned_at || "—"}
        </span>
        <button onClick={load} style={{
          marginLeft: "auto", padding: "3px 10px", fontSize: 9,
          border: "1px solid var(--border)", borderRadius: 3, background: "transparent",
          color: "var(--text3)", cursor: "pointer", fontFamily: "inherit",
        }}>↻ Refresh</button>
      </div>

      {/* Summary chips */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        {[
          { l: "Imminent",   n: counts.imminent, c: "var(--red)"    },
          { l: "Close",      n: counts.close,    c: "var(--accent)" },
          { l: "Watching",   n: counts.watching, c: "var(--yellow)" },
          { l: "ADR+Risk ✓", n: counts.valid,    c: "var(--green)"  },
          { l: "3WT ✦",      n: counts.tight,    c: "var(--green)"  },
        ].map(c => (
          <div key={c.l} style={{ padding: "4px 12px", borderRadius: 4,
            border: `1px solid ${c.c}35`, background: `${c.c}0d`, cursor: "pointer" }}
            onClick={() => setFilter(
              c.l === "Imminent" ? "imminent" : c.l === "Close" ? "close" :
              c.l.startsWith("ADR") ? "valid" : c.l.startsWith("3WT") ? "tight" : "all"
            )}>
            <span style={{ fontSize: 16, fontWeight: 700, color: c.c }}>{c.n}</span>
            <span style={{ fontSize: 9, color: c.c, marginLeft: 6 }}>{c.l}</span>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
        {filterBtns.map(({ val, label }) => (
          <button key={val} onClick={() => setFilter(val)} style={{
            padding: "3px 10px", fontSize: 9, letterSpacing: 0.5, textTransform: "uppercase",
            cursor: "pointer", borderRadius: 3, fontFamily: "inherit",
            border: `1px solid ${filter === val ? "var(--accent)" : "var(--border)"}`,
            background: filter === val ? "rgba(41,98,255,0.1)" : "transparent",
            color: filter === val ? "var(--accent)" : "var(--text3)",
          }}>{label}</button>
        ))}
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 14, marginBottom: 10, fontSize: 9, color: "var(--text3)", flexWrap: "wrap" }}>
        <span><b style={{ color: "var(--green)" }}>■</b> Good</span>
        <span><b style={{ color: "var(--yellow)" }}>■</b> Caution</span>
        <span><b style={{ color: "var(--red)" }}>■</b> Skip</span>
        <span style={{ opacity: 0.4 }}>|</span>
        <span>ADR 3.5–8% ideal</span>
        <span>EMA21L &lt;5% low risk · &gt;8% skip</span>
        <span>Dist% = how far price is above nearest MA</span>
        <span>✦ = 3-Weeks Tight</span>
        <span style={{ color: "var(--text3)", opacity: 0.6 }}>Click row to expand</span>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 820 }}>
          <thead>
            {/* Group labels */}
            <tr style={{ background: "var(--bg3)" }}>
              <th colSpan={6} style={{ ...TH, fontSize: 8, textAlign: "center",
                borderRight: "2px solid var(--border2)", letterSpacing: 2 }}>
                STOCK
              </th>
              <th colSpan={4} style={{ ...TH, fontSize: 8, textAlign: "center", color: "var(--accent)",
                borderRight: "2px solid var(--border2)", letterSpacing: 2 }}>
                CORE STATS
              </th>
              <th colSpan={3} style={{ ...TH, fontSize: 8, textAlign: "center", letterSpacing: 2 }}>
                ENTRY
              </th>
            </tr>
            {/* Column headers */}
            <tr>
              <th style={{ ...TH, width: 28, textAlign: "right" }}>#</th>
              <Th label="TICKER" k="ticker"       defaultDir={1}  />
              <Th label="RS"     k="rs"            align="center" defaultDir={-1} />
              <Th label="SECTOR" k="sector"        defaultDir={1}  />
              <Th label="PRICE"  k="price"         defaultDir={-1} />
              <th onClick={() => thClick("chg", -1)}
                style={{ ...TH, borderRight: "2px solid var(--border2)",
                  color: sortKey === "chg" ? "var(--accent)" : "var(--text3)" }}>
                CHG{sortKey === "chg" ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
              </th>
              <Th label="READY"   k="entry_readiness"  align="center" title="Entry Readiness 1–5 — combines ADR, EMA21L, 3WT and ceilings" defaultDir={-1} />
              <Th label="ADR %"   k="adr_pct"       align="center" title="Avg Daily Range % — ideal 3.5–8%" defaultDir={1} />
              <Th label="EMA21L %" k="ema21_low_pct" align="center" title="Distance to EMA21 Low — stop width proxy. <5% low risk, >8% skip" defaultDir={1} />
              <th style={{ ...TH, textAlign: "center", borderRight: "2px solid var(--border2)",
                cursor: "default" }}>3WT</th>
              <Th label="VCS"     k="vcs"           align="center" title="Volatility Contraction Score — lower is tighter" defaultDir={1} />
              <Th label="NEAR"    k="closest_ma"    align="center" defaultDir={1} />
              <Th label="DIST %"  k="closest_pct"   defaultDir={1} title="How far price is above nearest MA — lower means closer to entry" />
              <Th label="SCORE"   k="signal_score"  align="center" defaultDir={-1} />
            </tr>
          </thead>
          <tbody>
            {stocks.length === 0 ? (
              <tr><td colSpan={13} style={{ ...TD, textAlign: "center", padding: 28,
                color: "var(--text3)" }}>No stocks match this filter.</td></tr>
            ) : (
              stocks.map((s, i) => (
                <Row key={s.ticker} s={s} rank={i + 1}
                  expanded={expanded === s.ticker}
                  onExpand={() => setExpanded(expanded === s.ticker ? null : s.ticker)} />
              ))
            )}
          </tbody>
        </table>
      </div>
      <div style={{ height: 24 }} />
    </div>
  );
}
