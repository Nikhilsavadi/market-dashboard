import React, { useState, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "";

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3,
      padding: "12px 16px", textAlign: "center", minWidth: 100,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || "var(--text)", fontFamily: "monospace" }}>
        {value}
      </div>
      <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1.5, textTransform: "uppercase", marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}

function BotPanel({ bot, stats }) {
  const [showAll, setShowAll] = useState(false);

  if (!stats || stats.total_trades === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 12 }}>
        No {bot} trades yet. Data will appear after the bot places its first trade.
      </div>
    );
  }

  const s = stats;
  const pnlCol = s.total_pnl >= 0 ? "var(--green)" : "var(--red)";
  const trades = s.trades || [];
  const visibleTrades = showAll ? trades : trades.slice(-30);

  // Equity chart via simple SVG
  const eq = s.equity_curve || [];
  const eqVals = eq.map(e => e.equity);
  const eqMin = Math.min(0, ...eqVals);
  const eqMax = Math.max(1, ...eqVals);
  const eqRange = eqMax - eqMin || 1;
  const W = 600, H = 160, pad = 2;

  const eqPoints = eq.map((e, i) => {
    const x = pad + (i / Math.max(1, eq.length - 1)) * (W - 2 * pad);
    const y = H - pad - ((e.equity - eqMin) / eqRange) * (H - 2 * pad);
    return `${x},${y}`;
  }).join(" ");

  // Daily P&L bars
  const daily = s.daily_pnl || {};
  const dailyEntries = Object.entries(daily);
  const dailyMax = Math.max(1, ...dailyEntries.map(([, v]) => Math.abs(v)));

  // Monthly
  const monthly = s.monthly_pnl || {};
  const monthEntries = Object.entries(monthly);

  return (
    <div>
      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: 8, marginBottom: 16 }}>
        <StatCard label="Total P&L" value={`${s.total_pnl >= 0 ? "+" : ""}${s.total_pnl} pts`} color={pnlCol} />
        <StatCard label="Trades" value={s.total_trades} />
        <StatCard label="Win Rate" value={`${s.win_rate}%`} color={s.win_rate >= 55 ? "var(--green)" : "var(--text)"} />
        <StatCard label="Avg Win" value={`+${s.avg_win}`} color="var(--green)" />
        <StatCard label="Avg Loss" value={`${s.avg_loss}`} color="var(--red)" />
        <StatCard label="Max DD" value={`${s.max_drawdown} pts`} color="var(--red)" />
        <StatCard label="Days" value={s.trading_days} />
        <StatCard label="Avg MFE" value={`${s.avg_mfe} pts`} />
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
        {/* Equity curve */}
        <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3, padding: 12 }}>
          <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1.5, marginBottom: 8, textTransform: "uppercase" }}>
            Equity Curve
          </div>
          {eq.length > 1 ? (
            <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 140 }}>
              <line x1={pad} y1={H - pad - ((0 - eqMin) / eqRange) * (H - 2 * pad)}
                    x2={W - pad} y2={H - pad - ((0 - eqMin) / eqRange) * (H - 2 * pad)}
                    stroke="var(--border)" strokeWidth="0.5" strokeDasharray="4,4" />
              <polyline points={eqPoints} fill="none" stroke={s.total_pnl >= 0 ? "var(--green)" : "var(--red)"}
                        strokeWidth="1.5" />
            </svg>
          ) : <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text3)", fontSize: 10 }}>Need more data</div>}
        </div>

        {/* Daily P&L */}
        <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3, padding: 12 }}>
          <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1.5, marginBottom: 8, textTransform: "uppercase" }}>
            Daily P&L
          </div>
          {dailyEntries.length > 0 ? (
            <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 140 }}>
              <line x1={pad} y1={H / 2} x2={W - pad} y2={H / 2}
                    stroke="var(--border)" strokeWidth="0.5" />
              {dailyEntries.map(([date, val], i) => {
                const x = pad + (i / Math.max(1, dailyEntries.length - 1)) * (W - 2 * pad);
                const barH = (Math.abs(val) / dailyMax) * (H / 2 - pad);
                const y = val >= 0 ? H / 2 - barH : H / 2;
                const bw = Math.max(1, (W - 2 * pad) / dailyEntries.length * 0.7);
                return <rect key={date} x={x - bw / 2} y={y} width={bw} height={barH}
                             fill={val >= 0 ? "var(--green)" : "var(--red)"} opacity={0.8} />;
              })}
            </svg>
          ) : <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text3)", fontSize: 10 }}>No data</div>}
        </div>
      </div>

      {/* Monthly breakdown */}
      {monthEntries.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          {monthEntries.map(([m, v]) => (
            <div key={m} style={{
              background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3,
              padding: "8px 14px", textAlign: "center", minWidth: 80,
            }}>
              <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1 }}>{m}</div>
              <div style={{
                fontSize: 14, fontWeight: 700, fontFamily: "monospace", marginTop: 2,
                color: v >= 0 ? "var(--green)" : "var(--red)",
              }}>
                {v >= 0 ? "+" : ""}{v}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Trade log */}
      <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3, padding: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1.5, textTransform: "uppercase" }}>
            Trade Log ({trades.length})
          </span>
          {trades.length > 30 && (
            <button onClick={() => setShowAll(!showAll)} style={{
              fontSize: 9, padding: "2px 8px", cursor: "pointer",
              background: "var(--bg)", border: "1px solid var(--border)",
              color: "var(--text2)", borderRadius: 2,
            }}>
              {showAll ? "Show Recent" : `Show All ${trades.length}`}
            </button>
          )}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Date", "Dir", bot === "FTSE" ? "Type" : "#", "Entry", "Exit", "P&L", "MFE",
                  bot === "FTSE" ? "Width" : "Phase"].map(h => (
                  <th key={h} style={{ padding: "6px 8px", textAlign: "left", color: "var(--text3)",
                    fontSize: 8, letterSpacing: 1, textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleTrades.slice().reverse().map((t, i) => {
                const pnl = t.pnl_pts || 0;
                return (
                  <tr key={i} style={{ borderBottom: "1px solid var(--bg)" }}>
                    <td style={{ padding: "5px 8px" }}>{t.date}</td>
                    <td style={{ padding: "5px 8px" }}>
                      <span style={{
                        fontSize: 8, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
                        background: t.direction === "LONG" ? "rgba(8,153,129,0.1)" : "rgba(242,54,69,0.1)",
                        color: t.direction === "LONG" ? "var(--green)" : "var(--red)",
                        border: `1px solid ${t.direction === "LONG" ? "var(--green)" : "var(--red)"}33`,
                      }}>
                        {t.direction}
                      </span>
                    </td>
                    <td style={{ padding: "5px 8px" }}>{bot === "FTSE" ? (t.bar_type || "-") : (t.trade_num || 1)}</td>
                    <td style={{ padding: "5px 8px" }}>{t.entry}</td>
                    <td style={{ padding: "5px 8px" }}>{t.exit}</td>
                    <td style={{ padding: "5px 8px", fontWeight: 600, color: pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      {pnl >= 0 ? "+" : ""}{pnl}
                    </td>
                    <td style={{ padding: "5px 8px", color: "var(--text2)" }}>{t.mfe || "-"}</td>
                    <td style={{ padding: "5px 8px", color: "var(--text3)" }}>
                      {bot === "FTSE" ? (t.bar_width || "-") : (t.stop_phase || "-")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function BotDashboard() {
  const [data, setData] = useState(null);
  const [activeBot, setActiveBot] = useState("DAX");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/bot/stats`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
        Loading bot data...
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
        Could not load bot data. Check API connection.
      </div>
    );
  }

  const bots = [
    { key: "DAX", label: "DAX ASRS", desc: "Micro DAX Futures - Bar 4 Candle Trail" },
    { key: "FTSE", label: "FTSE 1BN/1BP", desc: "FTSE 100 CFD - Tom Hougaard Strategy" },
  ];

  const daxStats = data.DAX || {};
  const ftseStats = data.FTSE || {};
  const totalPnl = (daxStats.total_pnl || 0) + (ftseStats.total_pnl || 0);

  return (
    <div style={{ padding: "0 4px" }}>
      {/* Combined header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16, marginBottom: 16,
        padding: "10px 14px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3,
      }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)", letterSpacing: 1 }}>
            AUTOMATED BOTS
          </div>
          <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 2 }}>
            Paper trading via IBKR Gateway
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 12 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>DAX P&L</div>
            <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "monospace",
              color: (daxStats.total_pnl || 0) >= 0 ? "var(--green)" : "var(--red)" }}>
              {(daxStats.total_pnl || 0) >= 0 ? "+" : ""}{daxStats.total_pnl || 0}
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>FTSE P&L</div>
            <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "monospace",
              color: (ftseStats.total_pnl || 0) >= 0 ? "var(--green)" : "var(--red)" }}>
              {(ftseStats.total_pnl || 0) >= 0 ? "+" : ""}{ftseStats.total_pnl || 0}
            </div>
          </div>
          <div style={{ textAlign: "center", borderLeft: "1px solid var(--border)", paddingLeft: 12 }}>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>COMBINED</div>
            <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "monospace",
              color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>
              {totalPnl >= 0 ? "+" : ""}{Math.round(totalPnl * 10) / 10}
            </div>
          </div>
        </div>
      </div>

      {/* Bot sub-tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 16 }}>
        {bots.map(b => (
          <div
            key={b.key}
            onClick={() => setActiveBot(b.key)}
            style={{
              padding: "8px 20px", cursor: "pointer", borderRadius: "3px 3px 0 0",
              fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase",
              border: "1px solid " + (activeBot === b.key ? "var(--border)" : "transparent"),
              borderBottom: activeBot === b.key ? "1px solid var(--bg)" : "1px solid var(--border)",
              color: activeBot === b.key ? "var(--accent)" : "var(--text3)",
              background: activeBot === b.key ? "var(--bg3)" : "transparent",
              fontWeight: activeBot === b.key ? 700 : 400,
            }}
          >
            {b.label}
            {data[b.key]?.total_trades > 0 && (
              <span style={{ marginLeft: 6, fontSize: 8, color: "var(--text3)" }}>
                ({data[b.key].total_trades})
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Active bot panel */}
      <BotPanel bot={activeBot} stats={data[activeBot]} />
    </div>
  );
}
