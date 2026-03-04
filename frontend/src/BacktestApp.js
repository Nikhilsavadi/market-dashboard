import { useState, useEffect, useCallback, useRef } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from "recharts";

/* ─── API ─────────────────────────────────────────────────────────────────── */
const API = process.env.REACT_APP_API_URL || "";
const TRIGGER_SECRET = process.env.REACT_APP_TRIGGER_SECRET || "";

async function api(path, opts = {}, timeoutMs = 15000) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const r = await fetch(`${API}${path}`, { ...opts, signal: controller.signal });
    clearTimeout(timer);
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`[api] ${path} failed:`, e.message);
    return null;
  }
}

/* ─── MOCK DATA (fallback when backend not running) ──────────────────────── */
function mockAnalysis(signalType) {
  const rand = (a, b, d = 1) => +(Math.random() * (b - a) + a).toFixed(d);
  const st = signalType || "ALL";
  const trades = Array.from({ length: 80 }, (_, i) => ({
    ticker: ["NVDA","TSLA","PLTR","AMD","CRWD","PANW","NET","DDOG","APP","CELH"][i % 10],
    signal_type: ["MA10","MA21","MA50","SHORT"][i % 4],
    signal_date: new Date(Date.now() - (80 - i) * 86400000).toISOString().split("T")[0],
    entry_price: rand(50, 500),
    exit_price: rand(50, 500),
    exit_reason: ["t1","t2","stop","ma21_cross","timeout"][i % 5],
    hold_days: Math.floor(rand(1, 10)),
    pnl_pct: rand(-8, 15),
    pnl_r: rand(-1.5, 3),
    vcs: rand(1, 8),
    rs: Math.floor(rand(60, 99)),
    base_score: Math.floor(rand(20, 95)),
    sector: ["Technology","Financials","Healthcare","Consumer Disc","Semiconductors"][i % 5],
    market_score: Math.floor(rand(35, 85)),
  }));

  const pnls = trades.map(t => t.pnl_pct);
  const wins = pnls.filter(p => p > 0);
  const equity = trades.reduce((acc, t, i) => {
    const prev = acc[i - 1]?.value || 10000;
    return [...acc, { curve_date: t.signal_date, portfolio_value: prev * (1 + t.pnl_pct / 100 * 0.1), daily_pnl: t.pnl_pct * 10 }];
  }, []);

  const sectors = ["Technology","Financials","Healthcare","Consumer Disc","Semiconductors"].map(s => ({
    sector: s, win_rate: rand(40, 75), avg_pnl_pct: rand(-2, 8), sharpe: rand(0.2, 2.5), total_trades: Math.floor(rand(5, 25)),
  }));

  const months = Array.from({ length: 12 }, (_, i) => {
    const d = new Date(); d.setMonth(d.getMonth() - 11 + i);
    return { month: d.toISOString().slice(0, 7), trades: Math.floor(rand(5, 20)), win_rate: rand(35, 75), total_pnl: rand(-15, 30), avg_pnl: rand(-3, 8) };
  });

  return {
    signal_type: st, total_trades: trades.length,
    base_stats: {
      win_rate: +(wins.length / pnls.length * 100).toFixed(1),
      avg_pnl_pct: +(pnls.reduce((a, b) => a + b, 0) / pnls.length).toFixed(2),
      avg_pnl_r: rand(0.1, 1.5), avg_hold_days: rand(3, 8),
      best_trade_pct: Math.max(...pnls).toFixed(2), worst_trade_pct: Math.min(...pnls).toFixed(2),
      sharpe: rand(0.3, 2.2), profit_factor: rand(0.8, 2.5), max_drawdown_pct: rand(5, 25),
      gross_profit_pct: rand(50, 200), gross_loss_pct: rand(-80, -20),
      exit_breakdown: { t1: 18, t2: 12, t3: 5, stop: 22, ma21_cross: 13, timeout: 10 },
      max_consec_wins: Math.floor(rand(3, 8)), max_consec_losses: Math.floor(rand(2, 6)),
    },
    equity_curve: equity,
    by_sector: sectors,
    by_vcs: [
      { bucket: "coiled",   label: "VCS 1-3 (Coiled)",   win_rate: rand(60,80), avg_pnl_pct: rand(3,10), sharpe: rand(1.5,3), total_trades: 18 },
      { bucket: "tight",    label: "VCS 3-5 (Tight)",    win_rate: rand(50,65), avg_pnl_pct: rand(1,6),  sharpe: rand(0.8,1.8), total_trades: 28 },
      { bucket: "moderate", label: "VCS 5-7 (Moderate)", win_rate: rand(40,55), avg_pnl_pct: rand(-1,4), sharpe: rand(0.2,1.0), total_trades: 22 },
      { bucket: "loose",    label: "VCS 7+ (Loose)",     win_rate: rand(30,45), avg_pnl_pct: rand(-3,2), sharpe: rand(-0.2,0.5), total_trades: 12 },
    ],
    by_rs: [
      { bucket: "elite",   label: "RS 90-99", win_rate: rand(65,82), avg_pnl_pct: rand(5,12), sharpe: rand(1.8,3.2), total_trades: 15 },
      { bucket: "strong",  label: "RS 80-89", win_rate: rand(55,70), avg_pnl_pct: rand(2,8),  sharpe: rand(1.0,2.0), total_trades: 24 },
      { bucket: "good",    label: "RS 70-79", win_rate: rand(45,60), avg_pnl_pct: rand(0,5),  sharpe: rand(0.4,1.2), total_trades: 22 },
      { bucket: "average", label: "RS 60-69", win_rate: rand(35,50), avg_pnl_pct: rand(-2,3), sharpe: rand(-0.1,0.7), total_trades: 19 },
    ],
    by_base_score: [
      { bucket: "premium", label: "Base 80+",   win_rate: rand(68,85), avg_pnl_pct: rand(6,14), sharpe: rand(2,3.5), total_trades: 12 },
      { bucket: "quality", label: "Base 60-79", win_rate: rand(55,72), avg_pnl_pct: rand(3,9),  sharpe: rand(1.2,2.2), total_trades: 22 },
      { bucket: "average", label: "Base 40-59", win_rate: rand(42,58), avg_pnl_pct: rand(0,5),  sharpe: rand(0.3,1.0), total_trades: 28 },
      { bucket: "weak",    label: "Base <40",   win_rate: rand(30,45), avg_pnl_pct: rand(-4,2), sharpe: rand(-0.3,0.5), total_trades: 18 },
    ],
    by_market_regime: [
      { regime: "positive", label: "Market >65 (Positive)", win_rate: rand(62,80), avg_pnl_pct: rand(4,10), sharpe: rand(1.5,2.8), total_trades: 35 },
      { regime: "neutral",  label: "Market 45-65 (Neutral)",win_rate: rand(48,62), avg_pnl_pct: rand(1,6),  sharpe: rand(0.5,1.4), total_trades: 28 },
      { regime: "negative", label: "Market <45 (Negative)", win_rate: rand(32,48), avg_pnl_pct: rand(-3,3), sharpe: rand(-0.3,0.6), total_trades: 17 },
    ],
    monthly_returns: months,
    entry_type_comparison: {
      close_entry:     { win_rate: rand(48,65), avg_pnl_pct: rand(1,6), sharpe: rand(0.8,1.8) },
      next_open_entry: { win_rate: rand(44,62), avg_pnl_pct: rand(0,5), sharpe: rand(0.6,1.5) },
    },
    trades,
  };
}

function mockOptResults() {
  return Array.from({ length: 8 }, (_, i) => ({
    id: i + 1,
    signal_type: "ALL",
    total_trades: Math.floor(60 - i * 3),
    win_rate: +(65 - i * 2 + Math.random() * 3).toFixed(1),
    avg_pnl_pct: +(4 - i * 0.3 + Math.random()).toFixed(2),
    avg_pnl_r: +(1.2 - i * 0.1).toFixed(2),
    sharpe: +(2.1 - i * 0.2 + Math.random() * 0.1).toFixed(2),
    profit_factor: +(2.0 - i * 0.15).toFixed(2),
    max_drawdown_pct: +(12 + i * 1.5).toFixed(1),
    params: {
      stop_atr_mult: [1.5, 1.0, 2.0, 1.5, 1.0, 2.0, 1.5, 1.0][i],
      t1_atr_mult: [1.5, 2.0, 1.5, 2.0, 1.5, 2.0, 2.0, 1.5][i],
      t2_atr_mult: [3.0, 3.0, 4.0, 3.0, 4.0, 3.0, 4.0, 4.0][i],
      max_vcs: [3.0, 4.0, 3.0, 5.0, 4.0, 6.0, 3.0, 5.0][i],
      min_rs: [85, 80, 85, 75, 80, 70, 90, 80][i],
      min_market_score: [65, 55, 65, 45, 55, 0, 65, 45][i],
    },
  }));
}

/* ─── STYLES ──────────────────────────────────────────────────────────────── */
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne+Mono&family=Syne:wght@400;500;600;700;800&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #060709;
    --bg2:     #f5ede3;
    --bg3:     #0f1319;
    --bg4:     #141b24;
    --bg5:     #1a2330;
    --border:  #d4b89a;
    --border2: #28404f;
    --text:    #c2d8f0;
    --text2:   #5a7a96;
    --text3:   #c4a080;
    --green:   #00f5a0;
    --red:     #ff3366;
    --yellow:  #f5c400;
    --cyan:    #00c8ff;
    --orange:  #ff8c00;
    --purple:  #a855f7;
    --green-d: rgba(0,245,160,0.08);
    --red-d:   rgba(255,51,102,0.08);
  }

  * { scrollbar-width: thin; scrollbar-color: var(--border2) var(--bg); }
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    font-size: 12px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── Layout ── */
  .app { display: flex; flex-direction: column; min-height: 100vh; }

  .hdr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 20px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 200;
  }
  .logo {
    font-family: 'Syne Mono', monospace;
    font-size: 18px; letter-spacing: 3px;
    color: var(--cyan);
    text-shadow: 0 0 30px rgba(0,200,255,0.4);
  }
  .logo-sub { font-size: 9px; color: var(--text3); letter-spacing: 2px; margin-top: 2px; }

  .body { display: flex; flex: 1; overflow: hidden; }

  /* ── Sidebar ── */
  .sidebar {
    width: 260px; flex-shrink: 0;
    background: var(--bg2);
    border-right: 1px solid var(--border);
    overflow-y: auto; padding: 16px 0;
    display: flex; flex-direction: column; gap: 0;
  }

  .sb-section { padding: 0 14px 16px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
  .sb-label { font-size: 9px; letter-spacing: 2px; color: var(--text3); text-transform: uppercase; margin-bottom: 8px; font-weight: 700; }

  .signal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
  .signal-btn {
    padding: 6px 8px; cursor: pointer; border-radius: 2px;
    font-family: 'Syne Mono', monospace; font-size: 10px; font-weight: 700;
    border: 1px solid var(--border); background: var(--bg3); color: var(--text2);
    transition: all 0.12s; text-align: center; letter-spacing: 0.5px;
  }
  .signal-btn:hover { border-color: var(--border2); color: var(--text); }
  .signal-btn.active { background: var(--bg5); border-color: var(--cyan); color: var(--cyan); }
  .signal-btn.short.active { border-color: var(--red); color: var(--red); }
  .signal-btn.all.active { border-color: var(--yellow); color: var(--yellow); }

  /* Filter sliders */
  .filter-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
  .filter-label { display: flex; justify-content: space-between; font-size: 9px; color: var(--text2); }
  .filter-val { color: var(--cyan); font-family: 'Syne Mono', monospace; font-weight: 700; }

  input[type=range] {
    width: 100%; height: 2px; cursor: pointer;
    -webkit-appearance: none; appearance: none;
    background: var(--border2); border-radius: 1px; outline: none;
  }
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 10px; height: 10px;
    border-radius: 50%; background: var(--cyan); cursor: pointer;
    box-shadow: 0 0 8px rgba(0,200,255,0.5);
  }

  select {
    width: 100%; padding: 5px 8px; cursor: pointer;
    background: var(--bg3); border: 1px solid var(--border);
    color: var(--text); border-radius: 2px; font-family: 'Syne', sans-serif;
    font-size: 10px; outline: none;
  }
  select:focus { border-color: var(--border2); }

  .btn {
    padding: 7px 14px; cursor: pointer; border-radius: 2px;
    font-family: 'Syne', sans-serif; font-size: 10px; font-weight: 700;
    letter-spacing: 1px; text-transform: uppercase;
    border: 1px solid var(--border2); background: var(--bg4); color: var(--text);
    transition: all 0.12s; white-space: nowrap;
  }
  .btn:hover { background: var(--bg5); border-color: var(--cyan); color: var(--cyan); }
  .btn.primary { background: rgba(0,200,255,0.1); border-color: var(--cyan); color: var(--cyan); }
  .btn.primary:hover { background: rgba(0,200,255,0.2); }
  .btn.danger { background: rgba(255,51,102,0.08); border-color: var(--red); color: var(--red); }
  .btn.danger:hover { background: rgba(255,51,102,0.15); }
  .btn.wide { width: 100%; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── Main content ── */
  .main { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }

  /* ── Stat cards ── */
  .stats-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; }
  .stat-card {
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 3px; padding: 10px 12px;
    transition: border-color 0.12s;
  }
  .stat-card:hover { border-color: var(--border2); }
  .stat-label { font-size: 8px; letter-spacing: 1.5px; color: var(--text3); text-transform: uppercase; margin-bottom: 4px; }
  .stat-val {
    font-family: 'Syne Mono', monospace;
    font-size: 20px; font-weight: 700; line-height: 1;
  }
  .stat-sub { font-size: 9px; color: var(--text3); margin-top: 3px; }
  .pos { color: var(--green); }
  .neg { color: var(--red); }
  .neu { color: var(--yellow); }
  .info { color: var(--cyan); }

  /* ── Tabs ── */
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); }
  .tab {
    padding: 7px 16px; cursor: pointer; font-size: 10px; letter-spacing: 1px;
    text-transform: uppercase; color: var(--text3); border-bottom: 2px solid transparent;
    transition: all 0.12s; white-space: nowrap;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--cyan); border-bottom-color: var(--cyan); }

  /* ── Panel ── */
  .panel {
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 3px; padding: 14px 16px;
  }
  .panel-hdr {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 12px;
  }
  .panel-title {
    font-family: 'Syne Mono', monospace;
    font-size: 11px; letter-spacing: 2px; color: var(--text2); text-transform: uppercase;
  }

  /* ── Chart ── */
  .chart-wrap { width: 100%; height: 220px; }

  /* ── Dimension table ── */
  .dim-table { width: 100%; border-collapse: collapse; }
  .dim-table th {
    text-align: left; padding: 5px 8px;
    font-size: 8px; letter-spacing: 1.5px; color: var(--text3); text-transform: uppercase;
    border-bottom: 1px solid var(--border); font-weight: 600; white-space: nowrap;
  }
  .dim-table td { padding: 6px 8px; border-bottom: 1px solid rgba(30,45,61,0.5); font-size: 11px; }
  .dim-table tr:hover td { background: rgba(255,255,255,0.02); }
  .dim-table .mono { font-family: 'Syne Mono', monospace; }
  .bar-cell { display: flex; align-items: center; gap: 6px; }
  .bar-bg { flex: 1; height: 3px; background: var(--bg5); border-radius: 1px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 1px; transition: width 0.4s; }

  /* ── Monthly heatmap ── */
  .heatmap { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; }
  .hm-cell {
    padding: 8px 6px; border-radius: 2px; text-align: center; cursor: default;
    border: 1px solid rgba(255,255,255,0.03);
    transition: transform 0.1s;
  }
  .hm-cell:hover { transform: scale(1.03); z-index: 2; }
  .hm-month { font-size: 8px; color: var(--text3); margin-bottom: 3px; letter-spacing: 0.5px; }
  .hm-val { font-family: 'Syne Mono', monospace; font-size: 12px; font-weight: 700; }
  .hm-trades { font-size: 8px; color: var(--text3); margin-top: 2px; }

  /* ── Trade table ── */
  .trade-table { width: 100%; border-collapse: collapse; }
  .trade-table th {
    text-align: left; padding: 5px 8px;
    font-size: 8px; letter-spacing: 1.5px; color: var(--text3); text-transform: uppercase;
    border-bottom: 1px solid var(--border); font-weight: 600; white-space: nowrap;
    cursor: pointer; user-select: none;
  }
  .trade-table th:hover { color: var(--text); }
  .trade-table td { padding: 5px 8px; border-bottom: 1px solid rgba(30,45,61,0.4); font-size: 10px; }
  .trade-table tr:hover td { background: rgba(255,255,255,0.02); }

  /* ── Exit badge ── */
  .exit-badge {
    display: inline-block; padding: 1px 5px; border-radius: 2px;
    font-size: 8px; font-weight: 700; letter-spacing: 0.5px;
    font-family: 'Syne Mono', monospace;
  }

  /* ── Opt table ── */
  .opt-rank { font-family: 'Syne Mono', monospace; font-size: 16px; font-weight: 800; color: var(--text3); }
  .opt-rank.gold { color: var(--yellow); text-shadow: 0 0 12px rgba(245,196,0,0.4); }
  .opt-rank.silver { color: #a0b4c8; }
  .opt-rank.bronze { color: #cd7f32; }

  /* ── Status bar ── */
  .status-bar {
    display: flex; align-items: center; gap: 16px;
    padding: 8px 16px; background: var(--bg3);
    border: 1px solid var(--border); border-radius: 2px;
    font-size: 10px; color: var(--text2);
  }
  .status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.green { background: var(--green); box-shadow: 0 0 8px var(--green); }
  .status-dot.yellow { background: var(--yellow); box-shadow: 0 0 8px var(--yellow); animation: pulse 2s infinite; }
  .status-dot.gray { background: var(--text3); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

  /* ── Loading ── */
  .loading {
    display: flex; align-items: center; justify-content: center;
    height: 200px; color: var(--text3); font-size: 11px; letter-spacing: 1px;
    flex-direction: column; gap: 10px;
  }
  .spinner {
    width: 20px; height: 20px; border: 2px solid var(--border2);
    border-top-color: var(--cyan); border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Empty ── */
  .empty { padding: 32px; text-align: center; color: var(--text3); font-size: 11px; letter-spacing: 1px; }

  /* ── Comparison row ── */
  .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .compare-card {
    background: var(--bg3); border: 1px solid var(--border); border-radius: 2px; padding: 10px 12px;
  }
  .compare-title { font-size: 9px; color: var(--text3); letter-spacing: 1px; margin-bottom: 8px; }
  .compare-row { display: flex; justify-content: space-between; font-size: 10px; padding: 2px 0; }
  .compare-key { color: var(--text2); }

  /* ── Param chip ── */
  .param-chip {
    display: inline-block; padding: 2px 7px; margin: 2px;
    background: var(--bg4); border: 1px solid var(--border2);
    border-radius: 2px; font-family: 'Syne Mono', monospace; font-size: 9px; color: var(--text2);
  }
  .param-chip span { color: var(--cyan); font-weight: 700; }

  /* ── Drill summary ── */
  .drill-summary {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
    padding: 12px; background: var(--bg3); border: 1px solid var(--border); border-radius: 2px; margin-bottom: 12px;
  }
  .drill-item { text-align: center; }
  .drill-val { font-family: 'Syne Mono', monospace; font-size: 18px; font-weight: 700; }
  .drill-label { font-size: 8px; color: var(--text3); letter-spacing: 1px; margin-top: 2px; }

  /* Recharts overrides */
  .recharts-tooltip-wrapper { z-index: 100; }
`;

/* ─── HELPERS ─────────────────────────────────────────────────────────────── */
const pct = (v, dp = 1) => v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(dp)}%`;
const num = (v, dp = 2) => v == null ? "—" : Number(v).toFixed(dp);
const col = (v) => v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "neu";

function exitStyle(reason) {
  const map = {
    t3: { bg: "rgba(0,245,160,0.2)", color: "#00f5a0", label: "T3" },
    t2: { bg: "rgba(0,245,160,0.12)", color: "#00c88a", label: "T2" },
    t1: { bg: "rgba(0,200,255,0.12)", color: "#00c8ff", label: "T1" },
    stop: { bg: "rgba(255,51,102,0.15)", color: "#ff3366", label: "STOP" },
    ma21_cross: { bg: "rgba(245,196,0,0.12)", color: "#f5c400", label: "MA21✗" },
    timeout: { bg: "rgba(90,120,150,0.12)", color: "#5a7896", label: "TIME" },
  };
  return map[reason] || { bg: "rgba(90,120,150,0.1)", color: "#5a7896", label: reason };
}

function SharpeBadge({ v }) {
  const color = v >= 1.5 ? "var(--green)" : v >= 0.8 ? "var(--yellow)" : v >= 0 ? "var(--orange)" : "var(--red)";
  return <span style={{ color, fontFamily: "'Syne Mono',monospace", fontWeight: 700 }}>{num(v)}</span>;
}

function WinBar({ rate, height = 3 }) {
  const color = rate >= 60 ? "var(--green)" : rate >= 50 ? "var(--yellow)" : "var(--red)";
  return (
    <div className="bar-cell">
      <span style={{ fontFamily: "'Syne Mono',monospace", minWidth: 36 }}>{num(rate, 1)}%</span>
      <div className="bar-bg">
        <div className="bar-fill" style={{ width: `${rate}%`, background: color, height }} />
      </div>
    </div>
  );
}

/* ─── SUBCOMPONENTS ───────────────────────────────────────────────────────── */

function StatCards({ stats, totalTrades }) {
  if (!stats) return null;
  const cards = [
    { label: "Win Rate",       val: `${num(stats.win_rate, 1)}%`, cls: stats.win_rate >= 55 ? "pos" : stats.win_rate >= 45 ? "neu" : "neg", sub: `${totalTrades} trades` },
    { label: "Avg Return",     val: pct(stats.avg_pnl_pct),        cls: col(stats.avg_pnl_pct), sub: `${num(stats.avg_pnl_r)}R avg` },
    { label: "Sharpe",         val: num(stats.sharpe),             cls: stats.sharpe >= 1 ? "pos" : stats.sharpe >= 0 ? "neu" : "neg", sub: "annualised" },
    { label: "Profit Factor",  val: num(stats.profit_factor),      cls: stats.profit_factor >= 1.5 ? "pos" : stats.profit_factor >= 1 ? "neu" : "neg", sub: `${pct(stats.gross_profit_pct, 0)} gross` },
    { label: "Max Drawdown",   val: pct(stats.max_drawdown_pct),   cls: stats.max_drawdown_pct < 15 ? "pos" : stats.max_drawdown_pct < 25 ? "neu" : "neg", sub: "peak to trough" },
    { label: "Best Trade",     val: pct(stats.best_trade_pct),     cls: "pos", sub: `Worst: ${pct(stats.worst_trade_pct)}` },
    { label: "Avg Hold",       val: `${num(stats.avg_hold_days, 1)}d`, cls: "info", sub: "trading days" },
    { label: "Consec Wins",    val: stats.max_consec_wins,         cls: "pos", sub: `Max losses: ${stats.max_consec_losses}` },
  ];
  return (
    <div className="stats-row">
      {cards.map(c => (
        <div className="stat-card" key={c.label}>
          <div className="stat-label">{c.label}</div>
          <div className={`stat-val ${c.cls}`}>{c.val}</div>
          <div className="stat-sub">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

function ExitBreakdown({ breakdown }) {
  if (!breakdown) return null;
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const order = ["t3", "t2", "t1", "ma21_cross", "timeout", "stop"];
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {order.filter(k => breakdown[k]).map(k => {
        const s = exitStyle(k);
        const pct = ((breakdown[k] / total) * 100).toFixed(0);
        return (
          <div key={k} style={{ background: s.bg, border: `1px solid ${s.color}33`, borderRadius: 2, padding: "4px 8px", textAlign: "center" }}>
            <div style={{ color: s.color, fontFamily: "'Syne Mono',monospace", fontSize: 11, fontWeight: 700 }}>{breakdown[k]}</div>
            <div style={{ fontSize: 8, color: s.color, opacity: 0.7 }}>{s.label} {pct}%</div>
          </div>
        );
      })}
    </div>
  );
}

function EquityChart({ curve }) {
  if (!curve?.length) return <div className="empty">No equity curve data</div>;
  const start = curve[0]?.portfolio_value || 10000;
  const data = curve.map(c => ({
    date: c.curve_date?.slice(5) || "",
    value: c.portfolio_value,
    dd: c.drawdown_pct || 0,
    pnl: c.daily_pnl,
  }));
  const peak = Math.max(...data.map(d => d.value));
  const final = data[data.length - 1]?.value || start;
  const totalReturn = ((final - start) / start * 100).toFixed(1);
  const maxDd = Math.max(...data.map(d => d.dd)).toFixed(1);
  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 10, color: "var(--text2)" }}>
        <span>Start: <span style={{ color: "var(--text)", fontFamily: "monospace" }}>£{start.toFixed(0)}</span></span>
        <span>End: <span style={{ color: final > start ? "var(--green)" : "var(--red)", fontFamily: "monospace" }}>£{final.toFixed(0)}</span></span>
        <span>Return: <span className={final > start ? "pos" : "neg"}>+{totalReturn}%</span></span>
        <span>Max DD: <span style={{ color: "var(--red)" }}>{maxDd}%</span></span>
      </div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,45,61,0.5)" />
            <XAxis dataKey="date" tick={{ fill: "#c4a080", fontSize: 8 }} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fill: "#c4a080", fontSize: 8 }} tickLine={false} axisLine={false} tickFormatter={v => `£${(v/1000).toFixed(1)}k`} />
            <Tooltip
              contentStyle={{ background: "#f5ede3", border: "1px solid #d4b89a", borderRadius: 2, fontSize: 10 }}
              labelStyle={{ color: "#5a7a96" }}
              formatter={(v, n) => [n === "value" ? `£${v.toFixed(0)}` : `${v.toFixed(1)}%`, n === "value" ? "Portfolio" : "Drawdown"]}
            />
            <ReferenceLine y={start} stroke="rgba(90,120,150,0.3)" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="value" stroke="var(--cyan)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: "var(--cyan)" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DimTable({ data, labelKey, labelTitle = "Category" }) {
  if (!data?.length) return <div className="empty">No data</div>;
  const sorted = [...data].sort((a, b) => (b.sharpe || 0) - (a.sharpe || 0));
  return (
    <table className="dim-table">
      <thead>
        <tr>
          <th>{labelTitle}</th>
          <th>Trades</th>
          <th>Win Rate</th>
          <th>Avg %</th>
          <th>Sharpe</th>
          <th>Prof Factor</th>
          <th>Avg Hold</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((row, i) => (
          <tr key={i}>
            <td style={{ fontWeight: 600 }}>{row[labelKey] || row.label || row.sector || row.bucket}</td>
            <td className="mono">{row.total_trades}</td>
            <td><WinBar rate={row.win_rate} /></td>
            <td className={`mono ${col(row.avg_pnl_pct)}`}>{pct(row.avg_pnl_pct)}</td>
            <td><SharpeBadge v={row.sharpe} /></td>
            <td className={`mono ${row.profit_factor >= 1.5 ? "pos" : row.profit_factor >= 1 ? "neu" : "neg"}`}>
              {num(row.profit_factor)}
            </td>
            <td className="mono" style={{ color: "var(--text2)" }}>{num(row.avg_hold_days, 1)}d</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MonthlyHeatmap({ months }) {
  if (!months?.length) return <div className="empty">No monthly data</div>;
  const max = Math.max(...months.map(m => Math.abs(m.total_pnl)));
  return (
    <div className="heatmap">
      {months.map((m, i) => {
        const intensity = max > 0 ? Math.abs(m.total_pnl) / max : 0;
        const isPos = m.total_pnl >= 0;
        const bg = isPos
          ? `rgba(0,245,160,${0.05 + intensity * 0.25})`
          : `rgba(255,51,102,${0.05 + intensity * 0.25})`;
        const border = isPos
          ? `rgba(0,245,160,${0.1 + intensity * 0.3})`
          : `rgba(255,51,102,${0.1 + intensity * 0.3})`;
        return (
          <div className="hm-cell" key={i} style={{ background: bg, borderColor: border }}>
            <div className="hm-month">{m.month?.slice(2)}</div>
            <div className="hm-val" style={{ color: isPos ? "var(--green)" : "var(--red)" }}>
              {pct(m.total_pnl, 1)}
            </div>
            <div className="hm-trades">{m.trades}t · {num(m.win_rate, 0)}%w</div>
          </div>
        );
      })}
    </div>
  );
}

function TradeTable({ trades }) {
  const [sort, setSort] = useState({ key: "signal_date", dir: -1 });
  const [page, setPage] = useState(0);
  const PER = 20;

  const sorted = [...(trades || [])].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key];
    return typeof av === "number" ? (av - bv) * sort.dir : String(av).localeCompare(String(bv)) * sort.dir;
  });
  const paged = sorted.slice(page * PER, page * PER + PER);
  const pages = Math.ceil(sorted.length / PER);

  const Th = ({ k, children }) => (
    <th onClick={() => setSort(s => ({ key: k, dir: s.key === k ? -s.dir : -1 }))}>
      {children} {sort.key === k ? (sort.dir === -1 ? "↓" : "↑") : ""}
    </th>
  );

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table className="trade-table">
          <thead>
            <tr>
              <Th k="signal_date">Date</Th>
              <Th k="ticker">Ticker</Th>
              <Th k="signal_type">Type</Th>
              <Th k="entry_price">Entry</Th>
              <Th k="exit_price">Exit</Th>
              <Th k="exit_reason">Exit Reason</Th>
              <Th k="hold_days">Days</Th>
              <Th k="pnl_pct">P&L %</Th>
              <Th k="pnl_r">R</Th>
              <Th k="vcs">VCS</Th>
              <Th k="rs">RS</Th>
              <Th k="base_score">Base</Th>
              <Th k="market_score">Mkt</Th>
            </tr>
          </thead>
          <tbody>
            {paged.map((t, i) => {
              const es = exitStyle(t.exit_reason);
              return (
                <tr key={i}>
                  <td style={{ color: "var(--text2)", fontFamily: "monospace" }}>{t.signal_date}</td>
                  <td style={{ fontWeight: 700, color: "var(--cyan)" }}>{t.ticker}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 9, color: "var(--text3)" }}>{t.signal_type}</td>
                  <td style={{ fontFamily: "monospace" }}>${num(t.entry_price)}</td>
                  <td style={{ fontFamily: "monospace" }}>${num(t.exit_price)}</td>
                  <td>
                    <span className="exit-badge" style={{ background: es.bg, color: es.color }}>
                      {es.label}
                    </span>
                  </td>
                  <td style={{ fontFamily: "monospace", color: "var(--text2)" }}>{t.hold_days}d</td>
                  <td className={`${col(t.pnl_pct)}`} style={{ fontFamily: "monospace", fontWeight: 700 }}>{pct(t.pnl_pct)}</td>
                  <td className={`${col(t.pnl_r)}`} style={{ fontFamily: "monospace" }}>{num(t.pnl_r)}R</td>
                  <td style={{ fontFamily: "monospace", color: t.vcs <= 3 ? "var(--green)" : t.vcs <= 5 ? "var(--yellow)" : "var(--text2)" }}>{num(t.vcs, 1)}</td>
                  <td style={{ fontFamily: "monospace", color: t.rs >= 85 ? "var(--green)" : "var(--text2)" }}>{t.rs}</td>
                  <td style={{ fontFamily: "monospace", color: "var(--text2)" }}>{t.base_score}</td>
                  <td style={{ fontFamily: "monospace", color: "var(--text2)" }}>{t.market_score}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 10, alignItems: "center" }}>
          <button className="btn" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
          <span style={{ fontSize: 10, color: "var(--text2)" }}>Page {page + 1} / {pages} ({sorted.length} trades)</span>
          <button className="btn" onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page === pages - 1}>Next →</button>
        </div>
      )}
    </div>
  );
}

function OptResults({ results }) {
  if (!results?.length) return <div className="empty">No optimisation results yet. Run the optimiser first.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {results.map((r, i) => {
        const rankClass = i === 0 ? "gold" : i === 1 ? "silver" : i === 2 ? "bronze" : "";
        return (
          <div key={i} style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 2, padding: "10px 14px", display: "flex", gap: 16, alignItems: "center" }}>
            <div className={`opt-rank ${rankClass}`}>#{i + 1}</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
                {r.params && Object.entries(r.params).map(([k, v]) => (
                  <div className="param-chip" key={k}>{k.replace(/_/g, " ")}: <span>{v}</span></div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 20, fontSize: 11, color: "var(--text2)" }}>
                <span>Sharpe: <SharpeBadge v={r.sharpe} /></span>
                <span>Win: <span className={r.win_rate >= 55 ? "pos" : "neu"}>{num(r.win_rate, 1)}%</span></span>
                <span>Avg: <span className={col(r.avg_pnl_pct)}>{pct(r.avg_pnl_pct)}</span></span>
                <span>PF: <span className={r.profit_factor >= 1.5 ? "pos" : "neu"}>{num(r.profit_factor)}</span></span>
                <span>DD: <span style={{ color: "var(--red)" }}>{pct(r.max_drawdown_pct)}</span></span>
                <span style={{ color: "var(--text3)" }}>{r.total_trades} trades</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── ROOT APP ────────────────────────────────────────────────────────────── */
function EntryComparisonPanel() {
  const [data, setData]     = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const api = process.env.REACT_APP_API_URL || "";
    fetch(`${api}/api/backtest/entry-comparison`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 32, color: "#64748b" }}>Loading entry comparison...</div>;
  if (!data || data.error) return <div style={{ padding: 32, color: "#64748b" }}>{data?.error || "No data"}</div>;

  const { ma_bounce: mb, breakout: bo, verdict } = data;

  const verdictColor = verdict === "breakout_better" ? "#4ade80" : verdict === "ma_bounce_better" ? "#60a5fa" : "#f59e0b";
  const verdictText  = verdict === "breakout_better" ? "Breakout entry shows stronger R-multiple" :
                       verdict === "ma_bounce_better" ? "MA Bounce entry shows stronger R-multiple" :
                       verdict === "similar" ? "Both entries perform similarly" : "Insufficient data";

  const StatBox = ({ label, val, color, sub }) => (
    <div style={{
      background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
      padding: "12px 16px", textAlign: "center", flex: 1, minWidth: 100,
    }}>
      <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || "#e2e8f0" }}>{val ?? "—"}</div>
      {sub && <div style={{ fontSize: 10, color: "#475569", marginTop: 2 }}>{sub}</div>}
    </div>
  );

  const Section = ({ title, stats, color }) => {
    if (!stats || !stats.n_triggered) return (
      <div style={{ flex: 1, minWidth: 300 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color, marginBottom: 12 }}>{title}</div>
        <div style={{ color: "#64748b", fontSize: 12 }}>No data yet — run reconstruction to populate.</div>
      </div>
    );
    return (
      <div style={{ flex: 1, minWidth: 300 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color, marginBottom: 12 }}>{title}</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <StatBox label="Win Rate" val={`${stats.win_rate}%`} color={stats.win_rate >= 50 ? "#4ade80" : "#f87171"} />
          <StatBox label="Avg R" val={stats.avg_r} color={stats.avg_r >= 1 ? "#4ade80" : stats.avg_r >= 0 ? "#f59e0b" : "#f87171"} />
          <StatBox label="Expectancy" val={`${stats.expectancy_pct}%`} color={stats.expectancy_pct >= 0 ? "#4ade80" : "#f87171"} />
          <StatBox label="Profit Factor" val={stats.profit_factor} color={stats.profit_factor >= 1.5 ? "#4ade80" : "#f59e0b"} />
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <StatBox label="Avg Win" val={`${stats.avg_win_pct}%`} color="#4ade80" />
          <StatBox label="Avg Loss" val={`${stats.avg_loss_pct}%`} color="#f87171" />
          <StatBox label="Avg Hold" val={`${stats.avg_hold_days}d`} color="#94a3b8" />
          <StatBox label="Trades" val={stats.n_triggered} color="#94a3b8" sub={`of ${stats.n_signals} signals`} />
        </div>
        {stats.no_trigger_pct > 0 && (
          <div style={{
            background: "#1e293b", borderRadius: 6, padding: "8px 12px",
            fontSize: 12, color: "#94a3b8", marginBottom: 12,
          }}>
            ⚠ <b style={{ color: "#f59e0b" }}>{stats.no_trigger_pct}%</b> of signals never reached the breakout level within 15 days
          </div>
        )}
        {stats.signal_breakdown && Object.keys(stats.signal_breakdown).length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: "#64748b", marginBottom: 6 }}>AVG R BY SIGNAL TYPE</div>
            {Object.entries(stats.signal_breakdown).map(([sig, r]) => (
              <div key={sig} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1e293b", fontSize: 12 }}>
                <span style={{ color: "#94a3b8" }}>{sig}</span>
                <span style={{ color: r >= 1 ? "#4ade80" : r >= 0 ? "#f59e0b" : "#f87171", fontWeight: 700 }}>{r}R</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ padding: 20 }}>
      {/* Verdict banner */}
      <div style={{
        background: verdictColor + "15", border: `1px solid ${verdictColor}44`,
        borderRadius: 8, padding: "12px 16px", marginBottom: 20,
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{ fontSize: 20 }}>🎯</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: verdictColor }}>{verdictText}</div>
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
            Based on R-multiple (reward ÷ risk) across all historical signals. Higher R = better risk-adjusted return.
          </div>
        </div>
      </div>

      {/* Side by side comparison */}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Section title="📈 MA Bounce Entry" stats={mb} color="#60a5fa" />
        <div style={{ width: 1, background: "#1e293b", alignSelf: "stretch" }} />
        <Section title="🚀 Breakout Entry" stats={bo} color="#4ade80" />
      </div>

      <div style={{ marginTop: 20, padding: "12px 16px", background: "#0f172a", borderRadius: 8, fontSize: 11, color: "#64748b" }}>
        <b style={{ color: "#94a3b8" }}>How to read this:</b> MA Bounce enters on the close of the MA touch day with a 1.5× ATR stop below.
        Breakout enters when price crosses the 20-day high (+0.5% buffer) with the base low as stop — typically a wider risk but higher confirmation.
        The "no trigger" % shows how many MA signals never reclaimed the high within 15 days.
      </div>
    </div>
  );
}


export default function BacktestApp() {
  // Signal type selector
  const [signalType, setSignalType] = useState(null);

  // Filters (drill-down)
  const [maxVcs, setMaxVcs] = useState(6);
  const [minRs, setMinRs] = useState(70);
  const [minBase, setMinBase] = useState(0);
  const [minMkt, setMinMkt] = useState(0);
  const [sector, setSector] = useState("");
  const [entryType, setEntryType] = useState("");

  // Data
  const [analysis, setAnalysis] = useState(null);
  const [drillResult, setDrillResult] = useState(null);
  const [optResults, setOptResults] = useState(null);
  const [btStatus, setBtStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drillLoading, setDrillLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [useMock, setUseMock] = useState(false);
  const [splitData, setSplitData] = useState(null);
  const [splitLoading, setSplitLoading] = useState(false);
  const [splitDate, setSplitDate] = useState("");
  const [oosMths, setOosMths] = useState(4);

  // Fetch analysis
  const fetchAnalysis = useCallback(async (st) => {
    setLoading(true);
    const params = st ? `?signal_type=${st}` : "";
    // Use 30s timeout — analysis over 91k trades can be slow when reconstruction is running
    let data = await api(`/api/backtest/analysis${params}`, {}, 30000);
    // Retry once before falling back to mock — transient failures during heavy CPU load
    if (!data || data.error) {
      await new Promise(r => setTimeout(r, 2000));
      data = await api(`/api/backtest/analysis${params}`, {}, 30000);
    }
    if (data && !data.error) {
      setAnalysis(data);
      setUseMock(false);
    } else {
      setAnalysis(mockAnalysis(st));
      setUseMock(true);
    }
    setLoading(false);
  }, []);

  // Fetch backtest status
  const fetchStatus = useCallback(async () => {
    const data = await api("/api/backtest/status");
    setBtStatus(data);
  }, []);

  // Fetch opt results
  const fetchOpt = useCallback(async () => {
    const data = await api("/api/backtest/optimise/results");
    setOptResults(data?.results?.length ? data.results : mockOptResults());
  }, []);

  const fetchSplit = useCallback(async (customDate, customMths) => {
    setSplitLoading(true);
    const params = new URLSearchParams();
    if (signalType) params.set("signal_type", signalType);
    const d = customDate ?? splitDate;
    const m = customMths ?? oosMths;
    if (d) params.set("split_date", d);
    if (m) params.set("oos_months", m);
    const data = await api(`/api/backtest/split?${params}`);
    setSplitData(data && !data.error ? data : null);
    setSplitLoading(false);
  }, [signalType, splitDate, oosMths]);

  useEffect(() => {
    fetchAnalysis(signalType);
    fetchStatus();
    fetchOpt();
  }, [signalType]);

  // Drill-down query
  const runDrill = useCallback(async () => {
    setDrillLoading(true);
    const params = new URLSearchParams();
    if (signalType) params.set("signal_type", signalType);
    if (maxVcs < 10) params.set("max_vcs", maxVcs);
    if (minRs > 0) params.set("min_rs", minRs);
    if (minBase > 0) params.set("min_base_score", minBase);
    if (minMkt > 0) params.set("min_market_score", minMkt);
    if (sector) params.set("sector", sector);
    if (entryType) params.set("entry_type", entryType);

    const data = await api(`/api/backtest/drill?${params}`);
    setDrillResult(data || { stats: null, trades: [] });
    setDrillLoading(false);
    setActiveTab("drill");
  }, [signalType, maxVcs, minRs, minBase, minMkt, sector, entryType]);

  // Trigger reconstruction
  const triggerReconstruct = async (days) => {
    const ok = window.confirm(`Run ${days}-day historical reconstruction? This takes 20-60 mins in the background.`);
    if (!ok) return;
    await api(`/api/backtest/reconstruct?secret=${TRIGGER_SECRET}&lookback_days=${days}`, { method: "POST" });
    alert("Reconstruction started. Check status bar for progress.");
    fetchStatus();
  };

  // Trigger optimiser
  const triggerOpt = async (quick) => {
    const stParam = signalType ? `&signal_type=${signalType}` : "";
    await api(`/api/backtest/optimise?secret=${TRIGGER_SECRET}&quick=${quick}${stParam}`, { method: "POST" });
    alert(`${quick ? "Quick" : "Full"} optimisation started. Results appear in a few minutes.`);
    setTimeout(fetchOpt, 10000);
  };

  const stats = analysis?.base_stats;
  const tabs = [
    { id: "overview",  label: "Overview" },
    { id: "equity",    label: "Equity Curve" },
    { id: "sectors",   label: "By Sector" },
    { id: "vcs",       label: "By VCS" },
    { id: "rs",        label: "By RS" },
    { id: "base",      label: "By Base Score" },
    { id: "regime",    label: "By Market" },
    { id: "monthly",   label: "Monthly" },
    { id: "trades",    label: "All Trades" },
    { id: "drill",     label: "Drill-Down" },
    { id: "split",     label: "▶ Split Test" },
    { id: "entry",     label: "🎯 Entry Type" },
    { id: "optimiser", label: "Optimiser" },
  ];

  const sectors_list = ["", "Technology", "Semiconductors", "Financials", "Healthcare", "Consumer Disc", "Communication", "Biotech", "Gold Miners", "Industrials"];

  return (
    <>
      <style>{CSS}</style>
      <div className="app">

        {/* Header */}
        <div className="hdr">
          <div>
            <div className="logo">BACKTEST LAB</div>
            <div className="logo-sub">Signal Desk · Historical Performance Analysis</div>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {useMock && (
              <span style={{ fontSize: 9, color: "var(--yellow)", background: "rgba(245,196,0,0.08)", border: "1px solid rgba(245,196,0,0.2)", padding: "3px 8px", borderRadius: 2 }}>
                ⚠ DEMO DATA — backend offline
              </span>
            )}
            <button className="btn" onClick={() => fetchAnalysis(signalType)}>↻ Refresh</button>
          </div>
        </div>

        <div className="body">

          {/* Sidebar */}
          <div className="sidebar">

            {/* Signal type */}
            <div className="sb-section">
              <div className="sb-label">Signal Type</div>
              <div className="signal-grid">
                {[
                  { id: null,   label: "ALL",   cls: "all" },
                  { id: "MA10", label: "MA10",  cls: "" },
                  { id: "MA21", label: "MA21",  cls: "" },
                  { id: "MA50", label: "MA50",  cls: "" },
                  { id: "SHORT",label: "SHORT", cls: "short" },
                ].map(s => (
                  <button
                    key={String(s.id)}
                    className={`signal-btn ${s.cls} ${signalType === s.id ? "active" : ""}`}
                    onClick={() => setSignalType(s.id)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Drill filters */}
            <div className="sb-section">
              <div className="sb-label">Drill-Down Filters</div>

              <div className="filter-row">
                <div className="filter-label">
                  <span>Max VCS</span><span className="filter-val">{maxVcs === 10 ? "Any" : `≤ ${maxVcs}`}</span>
                </div>
                <input type="range" min={1} max={10} step={0.5} value={maxVcs} onChange={e => setMaxVcs(+e.target.value)} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, color: "var(--text3)" }}>
                  <span>Coiled</span><span>Loose</span>
                </div>
              </div>

              <div className="filter-row">
                <div className="filter-label">
                  <span>Min RS Rank</span><span className="filter-val">≥ {minRs}</span>
                </div>
                <input type="range" min={0} max={99} step={5} value={minRs} onChange={e => setMinRs(+e.target.value)} />
              </div>

              <div className="filter-row">
                <div className="filter-label">
                  <span>Min Base Score</span><span className="filter-val">{minBase === 0 ? "Any" : `≥ ${minBase}`}</span>
                </div>
                <input type="range" min={0} max={90} step={10} value={minBase} onChange={e => setMinBase(+e.target.value)} />
              </div>

              <div className="filter-row">
                <div className="filter-label">
                  <span>Min Market Score</span><span className="filter-val">{minMkt === 0 ? "Any" : `≥ ${minMkt}`}</span>
                </div>
                <input type="range" min={0} max={80} step={5} value={minMkt} onChange={e => setMinMkt(+e.target.value)} />
              </div>

              <div className="filter-row">
                <div className="filter-label"><span>Sector</span></div>
                <select value={sector} onChange={e => setSector(e.target.value)}>
                  {sectors_list.map(s => <option key={s} value={s}>{s || "All Sectors"}</option>)}
                </select>
              </div>

              <div className="filter-row">
                <div className="filter-label"><span>Entry Type</span></div>
                <select value={entryType} onChange={e => setEntryType(e.target.value)}>
                  <option value="">Both</option>
                  <option value="close">Close price</option>
                  <option value="next_open">Next day open</option>
                </select>
              </div>

              <button className="btn primary wide" onClick={runDrill} disabled={drillLoading}>
                {drillLoading ? "Running..." : "▶ Run Drill-Down"}
              </button>
            </div>

            {/* Reconstruction */}
            <div className="sb-section">
              <div className="sb-label">Historical Reconstruction</div>
              {btStatus && (
                <div style={{ fontSize: 9, color: "var(--text2)", marginBottom: 8, lineHeight: 1.6 }}>
                  <div>Signals: <span style={{ color: "var(--cyan)", fontFamily: "monospace" }}>{btStatus.historical_signals?.toLocaleString() || 0}</span></div>
                  <div>Trades: <span style={{ color: "var(--cyan)", fontFamily: "monospace" }}>{btStatus.historical_trades?.toLocaleString() || 0}</span></div>
                  {btStatus.date_range?.from && (
                    <div style={{ color: "var(--text3)" }}>{btStatus.date_range.from} → {btStatus.date_range.to}</div>
                  )}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <button className="btn wide" onClick={() => triggerReconstruct(90)}>Run 90 Days</button>
                <button className="btn wide" onClick={() => triggerReconstruct(180)}>Run 180 Days</button>
                <button className="btn wide" onClick={() => triggerReconstruct(365)}>Run Full Year</button>
              </div>
            </div>

            {/* Optimiser launcher */}
            <div className="sb-section">
              <div className="sb-label">Parameter Optimiser</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <button className="btn wide" onClick={() => triggerOpt(true)}>Quick Grid (~5 mins)</button>
                <button className="btn wide" onClick={() => triggerOpt(false)}>Full Grid (~20 mins)</button>
                <button className="btn wide" onClick={fetchOpt}>↻ Load Results</button>
              </div>
            </div>

          </div>

          {/* Main */}
          <div className="main">

            {/* Status bar */}
            <div className="status-bar">
              <div className={`status-dot ${btStatus?.ready ? "green" : btStatus ? "yellow" : "gray"}`} />
              <span>
                {btStatus?.ready
                  ? `${btStatus.historical_trades?.toLocaleString()} trades available`
                  : btStatus ? "Reconstruction needed — click a 'Run' button in the sidebar"
                  : "Checking backtest status..."}
              </span>
              {analysis && (
                <span style={{ marginLeft: "auto", color: "var(--text3)" }}>
                  {signalType || "ALL"} · {analysis.total_trades} trades
                </span>
              )}
            </div>

            {/* Stat cards */}
            {loading ? (
              <div className="loading"><div className="spinner" /><span>Loading analysis...</span></div>
            ) : (
              <StatCards stats={stats} totalTrades={analysis?.total_trades} />
            )}

            {/* Tabs */}
            <div className="tabs">
              {tabs.map(t => (
                <div key={t.id} className={`tab ${activeTab === t.id ? "active" : ""}`} onClick={() => setActiveTab(t.id)}>
                  {t.label}
                </div>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === "overview" && analysis && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="panel">
                  <div className="panel-hdr"><span className="panel-title">Exit Breakdown</span></div>
                  <ExitBreakdown breakdown={stats?.exit_breakdown} />
                </div>
                <div className="panel">
                  <div className="panel-hdr"><span className="panel-title">Entry Type Comparison</span></div>
                  <div className="compare-grid">
                    {Object.entries(analysis.entry_type_comparison || {}).map(([k, v]) => v && (
                      <div className="compare-card" key={k}>
                        <div className="compare-title">{k === "close_entry" ? "Close Price Entry" : "Next Day Open Entry"}</div>
                        {[["Win Rate", `${num(v.win_rate, 1)}%`], ["Avg Return", pct(v.avg_pnl_pct)], ["Sharpe", num(v.sharpe)]].map(([l, val]) => (
                          <div className="compare-row" key={l}><span className="compare-key">{l}</span><span style={{ fontFamily: "monospace" }}>{val}</span></div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "equity" && (
              <div className="panel">
                <div className="panel-hdr"><span className="panel-title">Portfolio Equity Curve</span><span style={{ fontSize: 9, color: "var(--text3)" }}>£10k start · £100 risk/trade · max 5 positions</span></div>
                <EquityChart curve={analysis?.equity_curve} />
              </div>
            )}

            {activeTab === "sectors" && (
              <div className="panel">
                <div className="panel-hdr"><span className="panel-title">Performance by Sector</span></div>
                <DimTable data={analysis?.by_sector} labelKey="sector" labelTitle="Sector" />
              </div>
            )}

            {activeTab === "vcs" && (
              <div className="panel">
                <div className="panel-hdr">
                  <span className="panel-title">Performance by VCS Bucket</span>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Lower VCS = tighter coil = better setup</span>
                </div>
                <DimTable data={analysis?.by_vcs} labelKey="label" labelTitle="VCS Range" />
              </div>
            )}

            {activeTab === "rs" && (
              <div className="panel">
                <div className="panel-hdr"><span className="panel-title">Performance by RS Rank</span></div>
                <DimTable data={analysis?.by_rs} labelKey="label" labelTitle="RS Rank" />
              </div>
            )}

            {activeTab === "base" && (
              <div className="panel">
                <div className="panel-hdr"><span className="panel-title">Performance by Base Quality Score</span></div>
                <DimTable data={analysis?.by_base_score} labelKey="label" labelTitle="Base Score" />
              </div>
            )}

            {activeTab === "regime" && (
              <div className="panel">
                <div className="panel-hdr">
                  <span className="panel-title">Performance by Market Regime</span>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Market score at time of signal</span>
                </div>
                <DimTable data={analysis?.by_market_regime} labelKey="label" labelTitle="Market Condition" />
              </div>
            )}

            {activeTab === "monthly" && (
              <div className="panel">
                <div className="panel-hdr"><span className="panel-title">Monthly Returns Heatmap</span></div>
                <MonthlyHeatmap months={analysis?.monthly_returns} />
              </div>
            )}

            {activeTab === "trades" && (
              <div className="panel">
                <div className="panel-hdr">
                  <span className="panel-title">All Trades</span>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Click column headers to sort</span>
                </div>
                <TradeTable trades={analysis?.trades} />
              </div>
            )}

            {activeTab === "drill" && (
              <div className="panel">
                <div className="panel-hdr">
                  <span className="panel-title">Drill-Down Results</span>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Adjust filters in sidebar → Run Drill-Down</span>
                </div>
                {drillLoading ? (
                  <div className="loading"><div className="spinner" /><span>Running query...</span></div>
                ) : drillResult?.stats ? (
                  <>
                    <div className="drill-summary">
                      {[
                        { label: "Trades", val: drillResult.stats.total_trades, cls: "info" },
                        { label: "Win Rate", val: `${num(drillResult.stats.win_rate, 1)}%`, cls: col(drillResult.stats.win_rate - 50) },
                        { label: "Avg Return", val: pct(drillResult.stats.avg_pnl_pct), cls: col(drillResult.stats.avg_pnl_pct) },
                        { label: "Sharpe", val: num(drillResult.stats.sharpe), cls: drillResult.stats.sharpe >= 1 ? "pos" : "neu" },
                        { label: "Profit Factor", val: num(drillResult.stats.profit_factor), cls: drillResult.stats.profit_factor >= 1.5 ? "pos" : "neu" },
                        { label: "Max DD", val: pct(drillResult.stats.max_drawdown_pct), cls: "neg" },
                        { label: "Avg Hold", val: `${num(drillResult.stats.avg_hold_days, 1)}d`, cls: "info" },
                        { label: "Best Trade", val: pct(drillResult.stats.best_trade_pct), cls: "pos" },
                      ].map(c => (
                        <div className="drill-item" key={c.label}>
                          <div className={`drill-val ${c.cls}`}>{c.val}</div>
                          <div className="drill-label">{c.label}</div>
                        </div>
                      ))}
                    </div>
                    <TradeTable trades={drillResult.trades} />
                  </>
                ) : (
                  <div className="empty">Set filters and click Run Drill-Down to see results</div>
                )}
              </div>
            )}

            {activeTab === "split" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                {/* Controls */}
                <div className="panel">
                  <div className="panel-hdr">
                    <span className="panel-title">In-Sample / Out-of-Sample Split Test</span>
                    <span style={{ fontSize: 9, color: "var(--text3)" }}>
                      The most important test before trading real money
                    </span>
                  </div>

                  <div style={{ fontSize: 11, color: "var(--text2)", lineHeight: 1.7, marginBottom: 14, padding: "10px 12px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 2 }}>
                    Splits your historical trades at a boundary date. <strong style={{ color: "var(--text)" }}>In-sample</strong> = the period you tuned parameters against (expect good numbers).{" "}
                    <strong style={{ color: "var(--cyan)" }}>Out-of-sample</strong> = unseen data you never touched (tells you if the edge is real).
                    If both periods show similar results, the edge is genuine. If OOS collapses, the system was overfit.
                  </div>

                  <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1 }}>OOS MONTHS (recent period)</label>
                      <div style={{ display: "flex", gap: 6 }}>
                        {[2, 3, 4, 6].map(m => (
                          <button
                            key={m}
                            className={`btn ${oosMths === m ? "primary" : ""}`}
                            style={{ padding: "5px 12px", fontSize: 11 }}
                            onClick={() => setOosMths(m)}
                          >
                            {m}mo
                          </button>
                        ))}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1 }}>OR CUSTOM SPLIT DATE</label>
                      <input
                        type="date"
                        value={splitDate}
                        onChange={e => setSplitDate(e.target.value)}
                        style={{ padding: "5px 8px", background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 2, fontSize: 11, fontFamily: "inherit" }}
                      />
                    </div>
                    <button
                      className="btn primary"
                      onClick={() => fetchSplit()}
                      disabled={splitLoading}
                      style={{ padding: "7px 20px" }}
                    >
                      {splitLoading ? "Running..." : "▶ Run Split Test"}
                    </button>
                  </div>
                </div>

                {/* Loading */}
                {splitLoading && (
                  <div className="loading"><div className="spinner" /><span>Analysing periods...</span></div>
                )}

                {/* Results */}
                {!splitLoading && splitData && (() => {
                  const v       = splitData.verdict || {};
                  const ins     = splitData.in_sample || {};
                  const oos     = splitData.out_of_sample || {};
                  const is_st   = ins.stats || {};
                  const oos_st  = oos.stats || {};
                  const metrics = v.metrics || {};

                  const verdictColors = {
                    strong:             { bg: "rgba(0,245,160,0.08)", border: "rgba(0,245,160,0.35)", text: "var(--green)",  dot: "#00f5a0" },
                    acceptable:         { bg: "rgba(245,196,0,0.07)", border: "rgba(245,196,0,0.35)", text: "var(--yellow)", dot: "#f5c400" },
                    degraded:           { bg: "rgba(255,140,0,0.08)", border: "rgba(255,140,0,0.35)", text: "var(--orange)", dot: "#ff8c00" },
                    failed:             { bg: "rgba(255,51,102,0.08)", border: "rgba(255,51,102,0.35)", text: "var(--red)",   dot: "#ff3366" },
                    insufficient_data:  { bg: "rgba(90,120,150,0.08)", border: "rgba(90,120,150,0.3)", text: "var(--text2)", dot: "#5a7896" },
                  };
                  const vc = verdictColors[v.result] || verdictColors.insufficient_data;

                  const CompareCol = ({ label, isVal, oosVal, higherBetter = true }) => {
                    const delta = typeof isVal === "number" && typeof oosVal === "number" ? oosVal - isVal : null;
                    const good  = delta == null ? null : higherBetter ? delta >= -5 : delta <= 5;
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, textTransform: "uppercase", marginBottom: 2 }}>{label}</div>
                        <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                          <span style={{ fontFamily: "monospace", color: "var(--text2)", fontSize: 11 }}>{isVal ?? "—"}</span>
                          <span style={{ fontSize: 9, color: "var(--text3)" }}>→</span>
                          <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 13, color: good === null ? "var(--text)" : good ? "var(--green)" : "var(--red)" }}>
                            {oosVal ?? "—"}
                          </span>
                          {delta != null && (
                            <span style={{ fontSize: 9, color: good ? "var(--green)" : "var(--red)" }}>
                              ({delta > 0 ? "+" : ""}{typeof delta === "number" ? delta.toFixed(1) : delta})
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  };

                  return (
                    <>
                      {/* Verdict banner */}
                      <div style={{ background: vc.bg, border: `1px solid ${vc.border}`, borderRadius: 3, padding: "14px 18px", display: "flex", gap: 14, alignItems: "flex-start" }}>
                        <div style={{ width: 10, height: 10, borderRadius: "50%", background: vc.dot, boxShadow: `0 0 12px ${vc.dot}`, flexShrink: 0, marginTop: 3 }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontFamily: "'Syne Mono',monospace", fontSize: 13, color: vc.text, fontWeight: 700, marginBottom: 6, letterSpacing: 1, textTransform: "uppercase" }}>
                            {v.result?.replace(/_/g, " ") || "RESULT"}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--text)", lineHeight: 1.7 }}>{v.summary}</div>
                          {v.detail?.length > 0 && (
                            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 3 }}>
                              {v.detail.map((d, i) => (
                                <div key={i} style={{ fontSize: 10, color: "var(--text2)", fontFamily: "monospace" }}>· {d}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Side-by-side comparison */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>

                        {/* In-sample */}
                        <div className="panel" style={{ borderColor: "var(--border2)" }}>
                          <div className="panel-hdr">
                            <span className="panel-title" style={{ color: "var(--text2)" }}>IN-SAMPLE</span>
                            <span style={{ fontSize: 9, color: "var(--text3)" }}>{ins.trade_count} trades · {splitData.split_date} boundary</span>
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {[
                              { l: "Win Rate",      v: is_st.win_rate != null     ? `${num(is_st.win_rate, 1)}%`       : "—" },
                              { l: "Avg Return",    v: is_st.avg_pnl_pct != null  ? pct(is_st.avg_pnl_pct)            : "—" },
                              { l: "Profit Factor", v: is_st.profit_factor != null ? num(is_st.profit_factor)          : "—" },
                              { l: "Sharpe",        v: is_st.sharpe != null        ? num(is_st.sharpe)                 : "—" },
                              { l: "Max Drawdown",  v: is_st.max_drawdown_pct != null ? pct(is_st.max_drawdown_pct)   : "—" },
                              { l: "Avg Hold",      v: is_st.avg_hold_days != null ? `${num(is_st.avg_hold_days, 1)}d`: "—" },
                            ].map(({ l, v: val }) => (
                              <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", borderBottom: "1px solid rgba(30,45,61,0.4)" }}>
                                <span style={{ color: "var(--text2)" }}>{l}</span>
                                <span style={{ fontFamily: "monospace", color: "var(--text)" }}>{val}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Out-of-sample */}
                        <div className="panel" style={{ borderColor: v.result === "strong" ? "rgba(0,245,160,0.3)" : v.result === "failed" ? "rgba(255,51,102,0.3)" : "var(--border2)" }}>
                          <div className="panel-hdr">
                            <span className="panel-title" style={{ color: "var(--cyan)" }}>OUT-OF-SAMPLE</span>
                            <span style={{ fontSize: 9, color: "var(--text3)" }}>{oos.trade_count} trades · unseen data</span>
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {[
                              { l: "Win Rate",      raw: oos_st.win_rate,        v: oos_st.win_rate != null      ? `${num(oos_st.win_rate, 1)}%`      : "—", good: (oos_st.win_rate||0) >= 50 },
                              { l: "Avg Return",    raw: oos_st.avg_pnl_pct,     v: oos_st.avg_pnl_pct != null   ? pct(oos_st.avg_pnl_pct)            : "—", good: (oos_st.avg_pnl_pct||0) > 0 },
                              { l: "Profit Factor", raw: oos_st.profit_factor,   v: oos_st.profit_factor != null  ? num(oos_st.profit_factor)          : "—", good: (oos_st.profit_factor||0) >= 1 },
                              { l: "Sharpe",        raw: oos_st.sharpe,          v: oos_st.sharpe != null         ? num(oos_st.sharpe)                 : "—", good: (oos_st.sharpe||0) >= 0.5 },
                              { l: "Max Drawdown",  raw: oos_st.max_drawdown_pct,v: oos_st.max_drawdown_pct != null ? pct(oos_st.max_drawdown_pct)    : "—", good: (oos_st.max_drawdown_pct||0) < 20 },
                              { l: "Avg Hold",      raw: oos_st.avg_hold_days,   v: oos_st.avg_hold_days != null  ? `${num(oos_st.avg_hold_days,1)}d` : "—", good: true },
                            ].map(({ l, v: val, good }) => (
                              <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", borderBottom: "1px solid rgba(30,45,61,0.4)" }}>
                                <span style={{ color: "var(--text2)" }}>{l}</span>
                                <span style={{ fontFamily: "monospace", fontWeight: 700, color: good ? "var(--green)" : "var(--red)" }}>{val}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Key metric deltas */}
                      {metrics.in_sample_win_rate != null && (
                        <div className="panel">
                          <div className="panel-hdr"><span className="panel-title">Key Metric Changes (In-Sample → Out-of-Sample)</span></div>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16, padding: "4px 0" }}>
                            <CompareCol
                              label="Win Rate"
                              isVal={`${num(metrics.in_sample_win_rate, 1)}%`}
                              oosVal={`${num(metrics.out_of_sample_win_rate, 1)}%`}
                              higherBetter={true}
                            />
                            <CompareCol
                              label="Avg Return"
                              isVal={pct(metrics.in_sample_expectancy)}
                              oosVal={pct(metrics.out_of_sample_expectancy)}
                              higherBetter={true}
                            />
                            <CompareCol
                              label="Profit Factor"
                              isVal={num(metrics.in_sample_profit_factor)}
                              oosVal={num(metrics.oos_profit_factor)}
                              higherBetter={true}
                            />
                            <CompareCol
                              label="Win Rate Drop"
                              isVal={null}
                              oosVal={`${metrics.win_rate_drop_pp > 0 ? "-" : "+"}${Math.abs(metrics.win_rate_drop_pp).toFixed(1)}pp`}
                              higherBetter={false}
                            />
                          </div>
                        </div>
                      )}

                      {/* Monthly breakdown side by side */}
                      {ins.monthly?.length > 0 && (
                        <div className="panel">
                          <div className="panel-hdr"><span className="panel-title">Monthly Win Rates by Period</span></div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                            {[{ label: "In-Sample", data: ins.monthly, color: "var(--text2)" },
                              { label: "Out-of-Sample", data: oos.monthly, color: "var(--cyan)" }
                            ].map(({ label, data, color }) => (
                              <div key={label}>
                                <div style={{ fontSize: 9, color, letterSpacing: 1, textTransform: "uppercase", marginBottom: 8, fontWeight: 700 }}>{label}</div>
                                {data?.length ? (
                                  <table className="dim-table">
                                    <thead>
                                      <tr>
                                        <th>Month</th>
                                        <th>Trades</th>
                                        <th>Win %</th>
                                        <th>Avg %</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {data.map((m, i) => (
                                        <tr key={i}>
                                          <td style={{ fontFamily: "monospace", color: "var(--text2)" }}>{m.month}</td>
                                          <td style={{ fontFamily: "monospace" }}>{m.trades}</td>
                                          <td><WinBar rate={m.win_rate} /></td>
                                          <td className={`mono ${col(m.avg_pnl)}`}>{pct(m.avg_pnl)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div className="empty" style={{ padding: 16 }}>No data for this period</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Signal type breakdown */}
                      {(ins.by_signal_type || oos.by_signal_type) && (
                        <div className="panel">
                          <div className="panel-hdr"><span className="panel-title">By Signal Type</span></div>
                          <table className="dim-table">
                            <thead>
                              <tr>
                                <th>Signal</th>
                                <th colSpan={2} style={{ textAlign: "center", color: "var(--text2)" }}>In-Sample</th>
                                <th colSpan={2} style={{ textAlign: "center", color: "var(--cyan)" }}>Out-of-Sample</th>
                              </tr>
                              <tr>
                                <th></th>
                                <th>Win %</th><th>Avg %</th>
                                <th>Win %</th><th>Avg %</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.keys({ ...(ins.by_signal_type || {}), ...(oos.by_signal_type || {}) }).map(st => {
                                const isSt  = ins.by_signal_type?.[st] || {};
                                const oosSt = oos.by_signal_type?.[st] || {};
                                return (
                                  <tr key={st}>
                                    <td style={{ fontFamily: "monospace", fontWeight: 700, color: "var(--cyan)" }}>{st}</td>
                                    <td><WinBar rate={isSt.win_rate || 0} /></td>
                                    <td className={`mono ${col(isSt.avg_pnl_pct)}`}>{pct(isSt.avg_pnl_pct)}</td>
                                    <td><WinBar rate={oosSt.win_rate || 0} /></td>
                                    <td className={`mono ${col(oosSt.avg_pnl_pct)}`}>{pct(oosSt.avg_pnl_pct)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  );
                })()}

                {/* Empty state */}
                {!splitLoading && !splitData && (
                  <div className="panel">
                    <div className="empty" style={{ padding: 48 }}>
                      <div style={{ fontSize: 28, marginBottom: 12 }}>▶</div>
                      <div style={{ marginBottom: 8, color: "var(--text)" }}>Run the split test to see if your edge is real</div>
                      <div style={{ fontSize: 10, lineHeight: 1.8, maxWidth: 400, margin: "0 auto" }}>
                        Choose how many recent months to treat as out-of-sample (default 4), then click Run Split Test.<br/>
                        You need at least 10 trades in the OOS period for a meaningful result.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "entry" && (
              <EntryComparisonPanel />
            )}

            {activeTab === "optimiser" && (
              <div className="panel">
                <div className="panel-hdr">
                  <span className="panel-title">Top Parameter Sets</span>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Ranked by Sharpe → Profit Factor</span>
                </div>
                <OptResults results={optResults} />
              </div>
            )}

          </div>
        </div>
      </div>
    </>
  );
}
