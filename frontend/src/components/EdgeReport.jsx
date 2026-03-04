import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const pct  = (v, dp=1) => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(dp)}%`;
const num  = (v, dp=1) => v == null ? "—" : Number(v).toFixed(dp);

const C = {
  bg:     "var(--bg)", bg2: "var(--bg2)", bg3: "var(--bg3)",
  border: "var(--border)", border2: "var(--border2)",
  green:  "var(--green)", greenL: "rgba(8,153,129,0.1)",
  red:    "var(--red)", redL:   "rgba(242,54,69,0.08)",
  amber:  "var(--yellow)", amberL: "rgba(184,130,10,0.10)",
  coral:  "var(--accent)", text:   "var(--text)", text2: "var(--text3)", text3: "var(--text3)",
};

const S = {
  page:   { fontFamily: "'Inter', sans-serif", fontSize: 12, padding: "20px 24px 60px", background: C.bg, minHeight: "100vh", color: C.text },
  title:  { fontFamily: "'Inter', sans-serif", fontSize: 22, color: C.text, margin: "0 0 4px" },
  sub:    { fontSize: 10, color: C.text3, marginBottom: 24 },
  card:   { background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 6, padding: "16px 18px", marginBottom: 12 },
  label:  { fontSize: 9, color: C.text3, letterSpacing: 2, textTransform: "uppercase", marginBottom: 3 },
  val:    { fontSize: 18, fontWeight: 700, color: C.text, fontFamily: "'Inter', sans-serif" },
  th:     { padding: "6px 12px", textAlign: "left", fontSize: 9, color: C.text3, letterSpacing: 1, textTransform: "uppercase", borderBottom: `1px solid ${C.border}`, fontWeight: 400 },
  td:     { padding: "7px 12px", borderBottom: `1px solid ${C.border}22`, fontSize: 11 },
  secTitle: { fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 10 },
};

function colForPnl(v) {
  if (v == null) return C.text3;
  return v > 0 ? C.green : v < 0 ? C.red : C.text2;
}

function WinRateBar({ rate, trades }) {
  if (rate == null) return <span style={{ color: C.text3 }}>—</span>;
  const col = rate >= 55 ? C.green : rate >= 45 ? C.amber : C.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 80, height: 6, background: C.bg3, borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${rate}%`, height: "100%", background: col, borderRadius: 3 }} />
      </div>
      <span style={{ color: col, fontWeight: 700 }}>{rate}%</span>
      <span style={{ color: C.text3 }}>({trades})</span>
    </div>
  );
}

function StatCard({ label, value, sub, col }) {
  return (
    <div style={{ ...S.card, flex: 1, minWidth: 120 }}>
      <div style={S.label}>{label}</div>
      <div style={{ ...S.val, color: col || C.text }}>{value}</div>
      {sub && <div style={{ fontSize: 9, color: C.text3, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function EquityCurve({ data }) {
  if (!data || data.length === 0) return null;
  const vals    = data.map(d => d.cumulative);
  const min_v   = Math.min(...vals);
  const max_v   = Math.max(...vals);
  const range   = max_v - min_v || 1;
  const W = 500, H = 120;

  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((d.cumulative - min_v) / range) * H;
    return `${x},${y}`;
  }).join(" ");

  const finalVal = vals[vals.length - 1];
  const col = finalVal >= 0 ? C.green : C.red;

  return (
    <div style={{ ...S.card }}>
      <div style={S.secTitle}>Equity Curve (cumulative % P&L)</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible" }}>
        <defs>
          <linearGradient id="eq_grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={col} stopOpacity="0.3" />
            <stop offset="100%" stopColor={col} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Zero line */}
        {min_v < 0 && max_v > 0 && (
          <line x1="0" x2={W}
            y1={H - ((0 - min_v) / range) * H}
            y2={H - ((0 - min_v) / range) * H}
            stroke={C.border} strokeDasharray="4,4" strokeWidth="1" />
        )}
        <polyline fill={`url(#eq_grad)`} stroke="none"
          points={`0,${H} ${points} ${W},${H}`} />
        <polyline fill="none" stroke={col} strokeWidth="2" points={points} />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: C.text3, marginTop: 4 }}>
        <span>{data[0]?.date}</span>
        <span style={{ color: col, fontWeight: 700 }}>
          Total: {pct(finalVal)}
        </span>
        <span>{data[data.length - 1]?.date}</span>
      </div>
    </div>
  );
}

function BreakdownTable({ title, rows, keyCol, cols }) {
  if (!rows || rows.length === 0) return null;
  return (
    <div style={{ ...S.card, marginBottom: 16 }}>
      <div style={S.secTitle}>{title}</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={S.th}>{keyCol}</th>
            {cols.map(c => <th key={c.key} style={{ ...S.th, textAlign: "right" }}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : `${C.bg3}50` }}>
              <td style={{ ...S.td, fontWeight: 700, color: C.text }}>{row[keyCol.toLowerCase().replace(" ","_")] || row[Object.keys(row)[0]]}</td>
              {cols.map(c => (
                <td key={c.key} style={{ ...S.td, textAlign: "right" }}>
                  {c.render ? c.render(row[c.key], row) : (
                    <span style={{ color: c.color ? c.color(row[c.key]) : C.text }}>
                      {c.format ? c.format(row[c.key]) : row[c.key]}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeLog({ trades }) {
  if (!trades || trades.length === 0) return null;
  return (
    <div style={S.card}>
      <div style={S.secTitle}>Recent Trades</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Date", "Ticker", "Signal", "Entry", "Exit", "P&L", "Days", "Exit Reason"].map(h => (
              <th key={h} style={S.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : `${C.bg3}50` }}>
              <td style={S.td}>{t.exit_date || "—"}</td>
              <td style={{ ...S.td, fontWeight: 700 }}>{t.ticker}</td>
              <td style={{ ...S.td, color: C.text3 }}>{t.signal_type || "—"}</td>
              <td style={S.td}>${t.entry_price?.toFixed(2) || "—"}</td>
              <td style={S.td}>${t.exit_price?.toFixed(2) || "—"}</td>
              <td style={{ ...S.td, fontWeight: 700, color: colForPnl(t.pnl_pct) }}>
                {pct(t.pnl_pct)}
              </td>
              <td style={{ ...S.td, color: C.text3 }}>
                {t.added_date && t.exit_date
                  ? `${Math.round((new Date(t.exit_date) - new Date(t.added_date)) / 86400000)}d`
                  : "—"}
              </td>
              <td style={{ ...S.td, color: C.text3 }}>{t.exit_reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ── Skip Analytics Panel ───────────────────────────────────────────────────────

function SkipAnalyticsPanel({ sa }) {
  if (!sa) return <div style={{ padding: 20, color: C.text3, fontSize: 12 }}>No skip data yet — skip some suggestions to build this report.</div>;

  const { taken_vs_skipped: tvs, skip_reason_breakdown: srb,
          override_tracking: ot, weekly_tally: wt,
          taken_count, skipped_count, take_rate } = sa;

  const SKIP_LABELS = {
    regime_warn:     "Regime warning",
    high_iv:         "High IV",
    low_conviction:  "Low conviction",
    low_score:       "Low score",
    poor_ev:         "Poor EV",
    position_limit:  "Position limit",
    earnings_risk:   "Earnings risk",
    sector_headwind: "Sector headwind",
    capital:         "Capital",
    other:           "Other",
    unspecified:     "Unspecified",
  };

  return (
    <div>
      {/* Header stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 16 }}>
        {[
          { label: "Total Suggestions", val: (taken_count||0)+(skipped_count||0) },
          { label: "Taken",   val: taken_count||0,   col: C.green },
          { label: "Skipped", val: skipped_count||0, col: "var(--red)" },
          { label: "Take Rate",        val: take_rate ? `${take_rate}%` : "—" },
          { label: "Taken Win Rate",   val: tvs?.taken?.win_rate  ? `${tvs.taken.win_rate}%`  : "—", col: colForPnl(tvs?.taken?.win_rate - 50) },
          { label: "Opportunity Cost", val: tvs?.opportunity_cost != null ? `${tvs.opportunity_cost > 0 ? "+" : ""}${tvs.opportunity_cost}%` : "—", col: colForPnl(-(tvs?.opportunity_cost||0)) },
        ].map(({ label, val, col }) => (
          <div key={label} style={{ ...S.card, padding: "10px 12px" }}>
            <div style={S.label}>{label}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: col || C.text, marginTop: 2 }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Verdict */}
      {tvs?.verdict && (
        <div style={{
          padding: "10px 14px", borderRadius: 4, marginBottom: 14,
          background: tvs.opportunity_cost <= 0 ? "rgba(8,153,129,0.07)" : "rgba(245,166,35,0.07)",
          border: `1px solid ${tvs.opportunity_cost <= 0 ? "rgba(8,153,129,0.2)" : "var(--yellow)30"}`,
          fontSize: 12, color: C.text2,
        }}>
          {tvs.opportunity_cost <= 0 ? "✅" : "⚠️"} {tvs.verdict}
        </div>
      )}

      {/* Skip reason breakdown */}
      {srb?.by_reason?.length > 0 && (
        <div style={{ ...S.card, marginBottom: 14 }}>
          <div style={S.secTitle}>Skip Reason Breakdown</div>
          <div style={{ fontSize: 10, color: C.text3, marginBottom: 10 }}>
            Avg missed gain = estimated return if you had taken the trade (T1 target or actual if updated).
            Flagged (🚩) = this reason cost you {">"}5% vs taken avg.
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr style={{ color: C.text3, fontSize: 9, letterSpacing: 1 }}>
                {["REASON","COUNT","AVG SCORE","AVG MISSED GAIN","VS TAKEN AVG",""].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "3px 8px", borderBottom: `1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {srb.by_reason.map(r => (
                <tr key={r.reason} style={{ borderBottom: `1px solid ${C.border}10` }}>
                  <td style={{ padding: "5px 8px", color: C.text }}>{SKIP_LABELS[r.reason] || r.reason}</td>
                  <td style={{ padding: "5px 8px", color: C.text3 }}>{r.count}</td>
                  <td style={{ padding: "5px 8px", color: C.text3 }}>{r.avg_score?.toFixed(1) || "—"}</td>
                  <td style={{ padding: "5px 8px", color: r.avg_missed_gain > 0 ? C.green : C.text3 }}>
                    {r.avg_missed_gain != null ? `${r.avg_missed_gain > 0 ? "+" : ""}${r.avg_missed_gain.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "5px 8px", color: (r.cost_vs_taken||0) > 2 ? "var(--yellow)" : C.text3 }}>
                    {r.cost_vs_taken != null ? `${r.cost_vs_taken > 0 ? "+" : ""}${r.cost_vs_taken.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "5px 8px" }}>{r.flag ? "🚩" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Override tracking */}
      {ot && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          {[
            { title: "High-Score Skips (≥8.0)", data: ot.high_score_skips,
              rows: [
                ["Count", ot.high_score_skips.count],
                ["Avg Score", ot.high_score_skips.avg_score?.toFixed(1)],
                ["Avg Estimated Missed", ot.high_score_skips.avg_missed != null ? `${ot.high_score_skips.avg_missed.toFixed(1)}%` : "—"],
                ["Top Reasons", (ot.high_score_skips.top_reasons||[]).join(", ") || "—"],
              ]
            },
            { title: "Below-Threshold Takes (<7.0)", data: ot.low_score_takes,
              rows: [
                ["Count", ot.low_score_takes.count],
                ["Avg Score", ot.low_score_takes.avg_score?.toFixed(1)],
                ["Win Rate", ot.low_score_takes.win_rate != null ? `${ot.low_score_takes.win_rate}%` : "—"],
                ["Avg P&L",  ot.low_score_takes.avg_pnl  != null ? `${ot.low_score_takes.avg_pnl.toFixed(1)}%` : "—"],
              ]
            },
          ].map(({ title, data, rows }) => (
            <div key={title} style={{ ...S.card }}>
              <div style={S.secTitle}>{title}</div>
              {rows.map(([label, val]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", borderBottom: `1px solid ${C.border}20` }}>
                  <span style={{ color: C.text3 }}>{label}</span>
                  <span style={{ color: C.text, fontWeight: 600 }}>{val ?? "—"}</span>
                </div>
              ))}
              <div style={{ fontSize: 10, color: C.text3, marginTop: 8, fontStyle: "italic" }}>
                {data.verdict}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Weekly tally */}
      {wt?.length > 0 && (
        <div style={S.card}>
          <div style={S.secTitle}>Weekly Tally (last 12 weeks)</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr style={{ color: C.text3, fontSize: 9, letterSpacing: 1 }}>
                {["WEEK","TAKEN","SKIPPED","TAKE RATE","CLOSED","WIN RATE","AVG P&L"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "3px 8px", borderBottom: `1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {wt.map(w => (
                <tr key={w.week} style={{ borderBottom: `1px solid ${C.border}10` }}>
                  <td style={{ padding: "5px 8px", color: C.text,  fontFamily: "monospace" }}>{w.week}</td>
                  <td style={{ padding: "5px 8px", color: C.green }}>{w.taken}</td>
                  <td style={{ padding: "5px 8px", color: "var(--red)" }}>{w.skipped}</td>
                  <td style={{ padding: "5px 8px", color: C.text3 }}>{w.take_rate != null ? `${w.take_rate}%` : "—"}</td>
                  <td style={{ padding: "5px 8px", color: C.text3 }}>{w.closed}</td>
                  <td style={{ padding: "5px 8px", color: w.win_rate >= 55 ? C.green : w.win_rate != null ? "var(--red)" : C.text3 }}>
                    {w.win_rate != null ? `${w.win_rate}%` : "—"}
                  </td>
                  <td style={{ padding: "5px 8px", color: colForPnl(w.avg_pnl) }}>
                    {w.avg_pnl != null ? `${w.avg_pnl > 0 ? "+" : ""}${w.avg_pnl.toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function EdgeReport() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [tab,     setTab]     = useState("overview");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res  = await fetch(`${API}/api/edge-report`);
      const json = await res.json();
      if (json.detail) throw new Error(json.detail);
      setData(json);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ ...S.page, color: C.text3 }}>Loading edge report...</div>;
  if (error)   return <div style={{ ...S.page, color: C.red }}>{error}</div>;
  if (!data)   return null;

  if (data.trades === 0) return (
    <div style={S.page}>
      <h2 style={S.title}>Edge Report</h2>
      <div style={{ color: C.text3, marginTop: 20, lineHeight: 1.8 }}>
        {data.message}
      </div>
    </div>
  );

  const { overall, signal_breakdown, rs_breakdown, vcs_breakdown,
          sector_breakdown, score_calibration, exit_breakdown,
          hold_breakdown, recent_form, equity_curve, raw_trades } = data;

  const streak = recent_form?.streak;

  const TABS = ["overview", "by signal", "calibration", "trades", "skip analysis"];

  return (
    <div style={S.page}>
      <h2 style={S.title}>Edge Report</h2>
      <p style={S.sub}>
        {overall.total_trades} closed trades · Generated {data.generated_at?.split("T")[0]}
        {streak?.count >= 3 && (
          <span style={{ color: streak.type === "win" ? C.green : C.red, marginLeft: 12, fontWeight: 700 }}>
            {streak.count} {streak.type === "win" ? "WIN" : "LOSS"} STREAK
          </span>
        )}
      </p>

      {/* Tab nav */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "6px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
            border: `1px solid ${tab === t ? C.coral : C.border}`,
            background: tab === t ? `${C.coral}15` : "transparent",
            color: tab === t ? C.coral : C.text3,
            fontFamily: "inherit", letterSpacing: 1, textTransform: "uppercase",
          }}>
            {t}
          </button>
        ))}
      </div>

      {/* ── Overview ── */}
      {tab === "overview" && (
        <>
          {/* KPI row */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
            <StatCard label="Win Rate"      value={`${overall.win_rate}%`}    col={overall.win_rate >= 55 ? C.green : overall.win_rate >= 45 ? C.amber : C.red} />
            <StatCard label="Expectancy"    value={pct(overall.expectancy)}   col={colForPnl(overall.expectancy)} sub="avg P&L per trade" />
            <StatCard label="Profit Factor" value={num(overall.profit_factor)} col={overall.profit_factor >= 1.5 ? C.green : C.amber} sub="gross wins / losses" />
            <StatCard label="Avg P&L"       value={pct(overall.avg_pnl)}      col={colForPnl(overall.avg_pnl)} />
            <StatCard label="Avg Hold"      value={`${num(overall.avg_hold_days)}d`} />
            <StatCard label="Best Trade"    value={pct(overall.best_trade)}   col={C.green} />
            <StatCard label="Worst Trade"   value={pct(overall.worst_trade)}  col={C.red} />
          </div>

          {/* Recent form */}
          <div style={{ ...S.card, borderLeft: `3px solid ${recent_form?.win_rate >= 55 ? C.green : C.red}` }}>
            <div style={S.secTitle}>Recent Form (last {recent_form?.trades} trades)</div>
            <div style={{ display: "flex", gap: 24 }}>
              <div><div style={S.label}>Win Rate</div><div style={{ ...S.val, fontSize: 14, color: recent_form?.win_rate >= 55 ? C.green : C.red }}>{recent_form?.win_rate}%</div></div>
              <div><div style={S.label}>Avg P&L</div><div style={{ ...S.val, fontSize: 14, color: colForPnl(recent_form?.avg_pnl) }}>{pct(recent_form?.avg_pnl)}</div></div>
              <div><div style={S.label}>Streak</div><div style={{ ...S.val, fontSize: 14, color: streak?.type === "win" ? C.green : C.red }}>{streak?.count} {streak?.type}</div></div>
            </div>
          </div>

          <EquityCurve data={equity_curve} />

          {/* Hold time */}
          <BreakdownTable title="Hold Duration Analysis" keyCol="days" rows={hold_breakdown} cols={[
            { key: "trades",   label: "Trades" },
            { key: "win_rate", label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",  label: "Avg P&L",  format: pct, color: colForPnl },
          ]} />

          {/* Exit reason */}
          <BreakdownTable title="Exit Reason Breakdown" keyCol="reason" rows={exit_breakdown} cols={[
            { key: "trades",   label: "Trades" },
            { key: "win_rate", label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",  label: "Avg P&L",  format: pct, color: colForPnl },
          ]} />
        </>
      )}

      {/* ── By Signal ── */}
      {tab === "by signal" && (
        <>
          <BreakdownTable title="Performance by Signal Type" keyCol="signal_type" rows={signal_breakdown} cols={[
            { key: "trades",     label: "Trades" },
            { key: "win_rate",   label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",    label: "Avg P&L",   format: pct, color: colForPnl },
            { key: "expectancy", label: "Expectancy", format: pct, color: colForPnl },
            { key: "best",       label: "Best",       format: pct, color: () => C.green },
            { key: "worst",      label: "Worst",      format: pct, color: () => C.red },
          ]} />

          <BreakdownTable title="Performance by RS Band" keyCol="band" rows={rs_breakdown} cols={[
            { key: "trades",     label: "Trades" },
            { key: "win_rate",   label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",    label: "Avg P&L",   format: pct, color: colForPnl },
            { key: "expectancy", label: "Expectancy", format: pct, color: colForPnl },
          ]} />

          <BreakdownTable title="Performance by VCS Band" keyCol="band" rows={vcs_breakdown} cols={[
            { key: "trades",   label: "Trades" },
            { key: "win_rate", label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",  label: "Avg P&L",  format: pct, color: colForPnl },
          ]} />

          <BreakdownTable title="Performance by Sector" keyCol="sector" rows={sector_breakdown} cols={[
            { key: "trades",     label: "Trades" },
            { key: "win_rate",   label: "Win Rate", render: (v, r) => <WinRateBar rate={v} trades={r.trades} /> },
            { key: "avg_pnl",    label: "Avg P&L",   format: pct, color: colForPnl },
            { key: "expectancy", label: "Expectancy", format: pct, color: colForPnl },
          ]} />
        </>
      )}

      {/* ── Calibration ── */}
      {tab === "calibration" && (
        <>
          <div style={{ ...S.card, marginBottom: 16 }}>
            <div style={S.secTitle}>Score Calibration</div>
            <div style={{ fontSize: 11, color: C.text3, marginBottom: 12 }}>
              Does a higher signal_score actually predict better outcomes?
              If calibrated, 8-9 score should have better win rate and P&L than 5-7.
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Score Band", "Trades", "Win Rate", "Avg P&L"].map(h => <th key={h} style={S.th}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {score_calibration.map((r, i) => (
                  <tr key={i}>
                    <td style={{ ...S.td, fontWeight: 700 }}>{r.score_band}</td>
                    <td style={S.td}>{r.trades}</td>
                    <td style={S.td}><WinRateBar rate={r.win_rate} trades={r.trades} /></td>
                    <td style={{ ...S.td, color: colForPnl(r.avg_pnl), fontWeight: 700 }}>{pct(r.avg_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ ...S.card }}>
            <div style={S.secTitle}>VCS Calibration</div>
            <div style={{ fontSize: 11, color: C.text3, marginBottom: 12 }}>
              Lower VCS = tighter volatility = should mean cleaner moves. Does it?
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["VCS Band", "Trades", "Win Rate", "Avg P&L"].map(h => <th key={h} style={S.th}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {vcs_breakdown.map((r, i) => (
                  <tr key={i}>
                    <td style={{ ...S.td, fontWeight: 700 }}>{r.band}</td>
                    <td style={S.td}>{r.trades}</td>
                    <td style={S.td}><WinRateBar rate={r.win_rate} trades={r.trades} /></td>
                    <td style={{ ...S.td, color: colForPnl(r.avg_pnl), fontWeight: 700 }}>{pct(r.avg_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Trade Log ── */}
      {tab === "trades" && <TradeLog trades={raw_trades} />}
      {tab === "skip analysis" && <SkipAnalyticsPanel sa={skip_analytics} />}
    </div>
  );
}
