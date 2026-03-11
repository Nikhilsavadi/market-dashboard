import RegimeGate from './components/RegimeGate';
import Pipeline from './components/Pipeline';
import Replay from './components/Replay';
import Correlation from './components/Correlation';
import WatchlistTab from './components/WatchlistTab';
import SectorHeatmap from './components/SectorHeatmap';
import SectorRotation from './components/SectorRotation';
import BotDashboard from './components/BotDashboard';
import React, { useState, useEffect, useCallback } from "react";


/* ─── TRADINGVIEW LINK ───────────────────────────────────────────────────── */
// NYSE-listed tickers (not on NASDAQ)
const NYSE_TICKERS = new Set([
  "V","MA","JPM","BAC","GS","MS","WFC","C","AXP","BLK","BX","KO","PEP","PG",
  "JNJ","MRK","ABT","LLY","PFE","CVX","XOM","OXY","COP","SLB","HAL","BA",
  "CAT","DE","HON","GE","GEV","ETN","EMR","UPS","RTX","LMT","NOC","GD",
  "HD","WMT","TGT","COST","LOW","NKE","MCD","SBUX","CMG","YUM","DPZ",
  "T","VZ","DIS","CMCSA","FOX","PARA","WBD","NEE","DUK","SO","D","AEP",
  "AMT","CCI","EQIX","SPG","PSA","O","VTR","WELL","EQR","AVB",
  "BRK.B","MCO","SPGI","AIG","MET","PRU","AFL","TRV","CB","ALL",
  "SYK","BSX","EW","MDT","DHR","TMO","A","IQV","IDXX","ISRG",
  "UNH","CVS","HUM","CI","ELV","HCA","MOH",
  "USB","PNC","TFC","KEY","HBAN","MTB","CFG","RF",
  "IBM","HPE","HPQ","DELL","WDC","STX",
  "LIN","APD","ECL","SHW","PPG","DOW","DD","LYB",
  "WM","RSG","CTAS","FAST","ODFL","UPS","FDX",
  "GLD","SLV","GDX","TLT","HYG","SPY","QQQ","IWM","DIA",
  "XLK","XLF","XLE","XLV","XLC","XLI","XLB","XLP","XLRE","XLU",
]);

function tvUrl(ticker) {
  if (!ticker) return "#";
  const sym = ticker.replace(".", "-");
  const exchange = NYSE_TICKERS.has(ticker) ? "NYSE" : "NASDAQ";
  return `https://www.tradingview.com/chart/?symbol=${exchange}:${sym}`;
}

function TVLink({ ticker, children, style = {} }) {
  return (
    <a
      href={tvUrl(ticker)}
      target="_blank"
      rel="noopener noreferrer"
      style={{ textDecoration: "none", color: "inherit", ...style }}
      onClick={e => e.stopPropagation()}
      title={`Open ${ticker} on TradingView`}
    >
      {children || ticker}
    </a>
  );
}

function SectorAlignBadge({ s }) {
  const aligned = s.sector_aligned;
  const rs1m    = s.sector_rs_1m;
  if (aligned == null || rs1m == null) return null;
  const col = aligned ? "#2d7a3a" : "#c43a2a";
  const bg  = aligned ? "rgba(45,122,58,0.1)" : "rgba(196,58,42,0.08)";
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: bg, color: col, border: `1px solid ${col}44`,
      whiteSpace: "nowrap",
    }}>
      {aligned ? "\u2713" : "\u2717"} SECTOR {rs1m >= 0 ? "+" : ""}{rs1m?.toFixed(1)}%
    </span>
  );
}

function EarningsBadge({ s }) {
  const days = s.days_to_earnings;
  const flag = s.earnings_flag;
  if (!days || days < 0 || days > 30) return null;

  const col = days <= 5  ? "#c43a2a"
            : days <= 14 ? "var(--orange)"
            : "#b8820a";
  const bg  = days <= 5  ? "rgba(196,58,42,0.12)"
            : days <= 14 ? "rgba(201,100,66,0.1)"
            : "rgba(184,130,10,0.08)";
  const label = days === 0 ? "EARNINGS TODAY"
              : days === 1 ? "EARNINGS TMR"
              : `EARNINGS ${days}D`;
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: bg, color: col, border: `1px solid ${col}44`,
      whiteSpace: "nowrap",
    }}>
      ⚠ {label}
    </span>
  );
}
function MASlopeBadge({ s }) {
  const slope = s.ma21_slope;
  if (slope == null) return null;
  const strong  = slope > 1.0;
  const rising  = slope > 0.5;
  const flat    = slope > -0.3 && slope <= 0.5;
  const fading  = slope <= -0.3;
  const col = strong ? "#2d7a3a" : rising ? "#5a9a3a" : flat ? "#b8820a" : "#c43a2a";
  const bg  = strong ? "rgba(45,122,58,0.1)" : rising ? "rgba(90,154,58,0.08)" : flat ? "rgba(184,130,10,0.08)" : "rgba(196,58,42,0.08)";
  const arrow = strong ? "↑↑" : rising ? "↑" : flat ? "→" : "↓";
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: bg, color: col, border: `1px solid ${col}44`,
      whiteSpace: "nowrap",
    }}>
      {arrow} MA21 {slope >= 0 ? "+" : ""}{slope.toFixed(2)}%
    </span>
  );
}

function CoilingBadge({ s }) {
  if (!s.coiling) return null;
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: "rgba(41,98,255,0.08)", color: "var(--accent)",
      border: "1px solid rgba(201,100,66,0.4)",
      whiteSpace: "nowrap",
    }}>
      ⟳ COILING
    </span>
  );
}

// Colours and icons keyed by setup_tag value
const SETUP_TAG_STYLES = {
  "LL-HL + DARVAS": { bg: "rgba(45,122,58,0.15)",  color: "#2d7a3a", border: "rgba(45,122,58,0.5)",  icon: "▲" },
  "LL-HL PIVOT":    { bg: "rgba(45,122,58,0.12)",  color: "#2d7a3a", border: "rgba(45,122,58,0.4)",  icon: "⬆" },
  "DARVAS":         { bg: "rgba(124,77,255,0.12)", color: "#7c4dff", border: "rgba(124,77,255,0.4)", icon: "⬜" },
  "LL-HL":          { bg: "rgba(45,122,58,0.08)",  color: "#5a8a3a", border: "rgba(45,122,58,0.3)",  icon: "↑" },
  "IN BOX":         { bg: "rgba(124,77,255,0.08)", color: "#9c6de0", border: "rgba(124,77,255,0.3)", icon: "▣" },
  "DARVAS BO":      { bg: "rgba(184,130,10,0.12)", color: "#b8820a", border: "rgba(184,130,10,0.4)", icon: "🔥" },
  // Flag & Pennant
  "FLAG BREAK":     { bg: "rgba(255,82,82,0.18)",  color: "#ff5252", border: "rgba(255,82,82,0.6)",  icon: "🚩" },
  "FLAG BO":        { bg: "rgba(255,82,82,0.12)",  color: "#ff7070", border: "rgba(255,82,82,0.4)",  icon: "⚡" },
  "FLAG WATCH":     { bg: "rgba(201,100,66,0.12)", color: "#e07048", border: "rgba(201,100,66,0.4)", icon: "⛳" },
};

function SetupTagBadge({ s }) {
  const tag = s.setupTag || s.setup_tag;
  if (!tag) return null;
  const style = SETUP_TAG_STYLES[tag];
  if (!style) return null;
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: style.bg, color: style.color,
      border: `1px solid ${style.border}`,
      whiteSpace: "nowrap",
    }}>
      {style.icon} {tag}
    </span>
  );
}

// ── Theme badge — narrative investment theme shown on every signal card ──────
const THEME_STYLES = {
  "Defence":       { label: "🛡 Defence",   color: "#4a90c8", bg: "rgba(28,61,90,0.85)",  border: "rgba(74,144,200,0.5)" },
  "DefenceTech":   { label: "🚁 Def-Tech",  color: "#5ab0d8", bg: "rgba(26,58,82,0.85)",  border: "rgba(90,176,216,0.5)" },
  "Space":         { label: "🚀 Space",      color: "#9b7de8", bg: "rgba(45,27,110,0.85)", border: "rgba(155,125,232,0.5)" },
  "Gold":          { label: "🥇 Gold",       color: "#e8b84b", bg: "rgba(90,62,0,0.85)",   border: "rgba(232,184,75,0.5)" },
  "Energy":        { label: "⛽ Energy",     color: "#e07040", bg: "rgba(74,32,0,0.85)",   border: "rgba(224,112,64,0.5)" },
  "AI":            { label: "🤖 AI",         color: "#4ac891", bg: "rgba(13,61,38,0.85)",  border: "rgba(74,200,145,0.5)" },
  "Semis":         { label: "💾 Semis",      color: "#4aa8e8", bg: "rgba(10,45,74,0.85)",  border: "rgba(74,168,232,0.5)" },
  "MegaTech":      { label: "📱 Mega",       color: "#4888c0", bg: "rgba(10,34,53,0.85)",  border: "rgba(72,136,192,0.5)" },
  "Crypto":        { label: "₿ Crypto",      color: "#e8963a", bg: "rgba(61,30,0,0.85)",   border: "rgba(232,150,58,0.5)" },
  "Fintech":       { label: "💳 Fintech",    color: "#4ac878", bg: "rgba(10,45,26,0.85)",  border: "rgba(74,200,120,0.5)" },
  "ConsumerGrowth":{ label: "🛍 Consumer",   color: "#c87848", bg: "rgba(45,26,10,0.85)",  border: "rgba(200,120,72,0.5)" },
  "Biotech":       { label: "🧬 Biotech",    color: "#68c868", bg: "rgba(10,45,10,0.85)",  border: "rgba(104,200,104,0.5)" },
};

function ThemeBadge({ s }) {
  const theme = s.theme;
  if (!theme) return null;
  const st = THEME_STYLES[theme];
  if (!st) return null;
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 6px", borderRadius: 3,
      background: st.bg, color: st.color,
      border: `1px solid ${st.border}`,
      whiteSpace: "nowrap",
    }}>
      {st.label}
    </span>
  );
}

function WeeklyStackBadge({ s }) {
  // Only show when weekly data is available (w_ema10 populated by backend)
  const wEma10 = s.wEma10 ?? s.w_ema10;
  if (wEma10 == null) return null;

  const ok = s.wStackOk ?? s.w_stack_ok ?? false;
  if (ok) {
    return (
      <span style={{
        fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
        padding: "2px 5px", borderRadius: 2,
        background: "rgba(45,122,58,0.1)", color: "#2d7a3a",
        border: "1px solid rgba(45,122,58,0.25)",
        whiteSpace: "nowrap",
      }}>
        W ✓
      </span>
    );
  }
  // Weekly trend is broken — this signals the daily+weekly misalignment
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 5px", borderRadius: 2,
      background: "rgba(184,130,10,0.1)", color: "#b8820a",
      border: "1px solid rgba(184,130,10,0.25)",
      whiteSpace: "nowrap",
    }}>
      W ✗
    </span>
  );
}

// Weekly timeframe confirmation badge
// Green = daily AND weekly aligned (highest conviction)
// Amber = weekly data present but stack not fully confirmed
const rand = (min, max, dp = 2) => +(Math.random() * (max - min) + min).toFixed(dp);
const pick = arr => arr[Math.floor(Math.random() * arr.length)];

function generateStock(ticker, bias = "neutral") {
  const price = rand(10, 800);

  // For longs: MAs must be BELOW price (stock is above its MAs = healthy uptrend)
  // MA10 closest to price, then MA21, then MA50 furthest below
  const ma10 = price * (bias === "long" ? rand(0.975, 0.999) : rand(1.005, 1.04));
  const ma21 = price * (bias === "long" ? rand(0.950, 0.998) : rand(1.01, 1.06));
  const ma50 = price * (bias === "long" ? rand(0.900, 0.990) : rand(1.02, 1.08));

  const vol = rand(500000, 50000000, 0);
  const avgVol = vol * rand(0.6, 1.8);
  const volRatio = +(vol / avgVol).toFixed(2);
  const chg = bias === "long" ? rand(0.5, 8) : rand(-8, -0.5);
  const rs = bias === "long" ? rand(80, 99) : rand(1, 30);
  const eps = rand(5, 120);
  const vcs = rand(1, 10, 1);

  // MA proximity — positive = price above MA, negative = price below
  const ma10PctFromMA = (price - ma10) / price;
  const ma21PctFromMA = (price - ma21) / price;
  const ma50PctFromMA = (price - ma50) / price;

  // MA10: must be above (no dipping below MA10 for longs)
  const ma10Touch = ma10PctFromMA >= 0 && ma10PctFromMA < 0.015;
  // MA21: up to 1.5% BELOW or 2% ABOVE — VCP dip under MA21 is acceptable if VCS is tight
  const ma21Touch = ma21PctFromMA >= -0.015 && ma21PctFromMA < 0.020;
  // MA50: must be above — dipping below MA50 is a red flag, not a setup
  const ma50Touch = ma50PctFromMA >= 0 && ma50PctFromMA < 0.025;

  const ma21BelowMA = ma21Touch && ma21PctFromMA < 0;  // price slightly under MA21
  const bouncingFrom = ma10Touch ? "MA10" : ma21Touch ? "MA21" : ma50Touch ? "MA50" : null;

  return {
    ticker,
    price: +price.toFixed(2),
    chg: +chg.toFixed(2),
    ma10: +ma10.toFixed(2),
    ma21: +ma21.toFixed(2),
    ma50: +ma50.toFixed(2),
    vol: +vol.toFixed(0),
    avgVol: +avgVol.toFixed(0),
    volRatio,
    rs,
    eps: +eps.toFixed(1),
    vcs: +vcs.toFixed(1),
    bouncingFrom,
    ma10Touch,
    ma21Touch,
    ma50Touch,
    ma21BelowMA,
    ma21PctFromMA: +ma21PctFromMA.toFixed(4),
    sector: pick(["Tech", "Health", "Finance", "Energy", "Consumer", "Industrial"]),
    theme:  pick(["Defence", "DefenceTech", "Space", "Gold", "AI", "Energy", null, null]),
  };
}

function generateShortStock(ticker) {
  const price = rand(15, 400);
  const ma10 = price * rand(1.01, 1.05);   // price below MA10
  const ma21 = ma10 * rand(1.01, 1.04);
  const ma50 = ma21 * rand(1.01, 1.03);
  const vol = rand(800000, 30000000, 0);
  const avgVol = vol * rand(0.7, 1.5);
  const volRatio = +(vol / avgVol).toFixed(2);
  const chg = rand(-9, -0.8);
  const rs = rand(1, 25);
  const daysBelow = Math.floor(rand(1, 15));
  const failedRally = Math.random() > 0.4;
  // shortScore comes from backend MA-rejection scoring — don't recalculate
  // shortScore already destructured from signal object above

  const catalyst = pick([
    "Failed rally at MA21",
    "Coiling at MA50",
    "Dry rally → MA200",
    "Weekly wEMA10 fail",
    "Failed rally at MA50",
    "Weekly wEMA40 fail",
    "Coiling at MA21",
  ]);

  const setupType = pick([
    "MA21 Fail",
    "MA50 Fail",
    "MA200 Fail",
    "Weekly Fail",
    "MA Rejection",
  ]);

  return {
    ticker,
    price: +price.toFixed(2),
    chg: +chg.toFixed(2),
    ma10: +ma10.toFixed(2),
    ma21: +ma21.toFixed(2),
    ma50: +ma50.toFixed(2),
    vol: +vol.toFixed(0),
    avgVol: +avgVol.toFixed(0),
    volRatio,
    rs,
    daysBelow,
    failedRally,
    catalyst,
    setupType,
    shortScore,
    sector: pick(["Tech", "Health", "Finance", "Energy", "Consumer", "Industrial"]),
    theme:  pick(["Defence", "DefenceTech", "Space", "Gold", "AI", "Energy", null, null]),
  };
}

/* --- API CONFIG ----------------------------------------------------------- */
// Development: create frontend/.env with REACT_APP_API_URL=http://localhost:8000
// Production:  set REACT_APP_API_URL to your Railway backend URL in Railway env vars
const API_BASE = process.env.REACT_APP_API_URL || "";

async function fetchDashboardData(rawData) {
  let raw = rawData;
  if (!raw) {
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), 30000);
    let res;
    try {
      res = await fetch(API_BASE + "/api/scan", { signal: controller.signal });
    } finally {
      clearTimeout(tid);
    }
    if (!res.ok) throw new Error("API error: " + res.status);
    raw = await res.json();
  }

  const norm = s => ({
    ...s,
    volRatio: s.vol_ratio,
    ma10Touch: s.ma10_touch,
    ma21Touch: s.ma21_touch,
    ma50Touch: s.ma50_touch,
    ma21BelowMA: s.ma21_below,
    ma21PctFromMA: s.pct_from_ma21,
    bouncingFrom: s.bouncing_from,
    shortScore:       s.short_score,
    shortSetupType:   s.short_setup_type,
    rejectionMa:      s.rejection_ma,
    rallyVolDry:      s.rally_vol_dry,
    shortCoiling:     s.short_coiling,
    wShortRejection:  s.w_short_rejection,
    failedRally:      s.failed_rally,
    daysBelow:        s.days_below_ma21,
    setupType: s.short_setup_type
      ? (s.short_setup_type.includes("MA200") ? "MA200 Fail"
        : s.short_setup_type.includes("MA50")  ? "MA50 Fail"
        : s.short_setup_type.includes("MA21")  ? "MA21 Fail"
        : s.short_setup_type.includes("WEEKLY") ? "Weekly Fail"
        : "MA Rejection")
      : "Weakness",
    catalyst: s.rejection_ma
      ? (s.short_coiling ? "Coiling at " + s.rejection_ma
        : s.rally_vol_dry ? "Dry rally → " + s.rejection_ma
        : "Failed rally at " + s.rejection_ma)
      : s.w_short_rejection
        ? "Weekly " + s.w_short_rejection + " fail"
        : "Breakdown",
    // oratnek pattern fields
    setupTag:        s.setup_tag,
    llHlDetected:    s.ll_hl_detected,
    approachingPivot:s.approaching_pivot,
    pivotLine:       s.pivot_line,
    hlPrice:         s.hl_price,
    pctFromPivot:    s.pct_from_pivot,
    pivotBroken:     s.pivot_broken,
    darvasDetected:  s.darvas_detected,
    darvasStatus:    s.darvas_status,
    boxTop:          s.box_top,
    boxBottom:       s.box_bottom,
    boxBars:         s.box_bars,
    pctFromBoxTop:   s.pct_from_box_top,
    // weekly timeframe fields
    wStackOk:        s.w_stack_ok,
    // Flag / Pennant fields
    flagDetected:    s.flag_detected,
    flagType:        s.flag_type,
    flagStatus:      s.flag_status,
    polePct:         s.pole_pct,
    poleBars:        s.pole_bars,
    poleHighPrice:   s.pole_high_price,
    flagBars:        s.flag_bars,
    flagLow:         s.flag_low,
    flagRetracePct:  s.flag_retrace_pct,
    tlTouches:       s.tl_touches,
    flagBreakoutLevel: s.flag_breakout_level,
    flagStopPrice:   s.flag_stop_price,
    flagTargetPrice: s.flag_target_price,
    volDryFlag:      s.vol_dry_flag,
    poleVolRatio:    s.pole_vol_ratio,
    wEma10:          s.w_ema10,
    wEma40:          s.w_ema40,
    wAboveEma10:     s.w_above_ema10,
    wAboveEma40:     s.w_above_ema40,
    wEma10Slope:     s.w_ema10_slope,
    // Core Stats
    adrPct:           s.adr_pct,
    ema21Low:         s.ema21_low,
    ema21LowPct:      s.ema21_low_pct,
    within1AtrEma21:  s.within_1atr_ema21,
    within1AtrWEma10: s.within_1atr_wema10,
    within3AtrSma50:  s.within_3atr_sma50,
    threeWeeksTight:  s.three_weeks_tight,
    entryReadiness:   s.entry_readiness,
    entry_readiness:  s.entry_readiness,
  });

  const mkt = (raw.market && typeof raw.market === "object") ? raw.market : {};
  const color = (mkt.score || 0) >= 65 ? "#2d7a3a" : (mkt.score || 0) >= 45 ? "#b8820a" : "#c43a2a";
  const idx = (mkt.indices && typeof mkt.indices === "object") ? mkt.indices : {};
  const spy = idx["SPY"] || {};
  const qqq = idx["QQQ"] || {};
  const iwm = idx["IWM"] || {};
  const sectorRs = (raw.sector_rs && typeof raw.sector_rs === "object") ? raw.sector_rs : {};
  const allStocksNorm = Array.isArray(raw.all_stocks) ? raw.all_stocks.map(norm) : [];
  const topRsGainers = [...allStocksNorm]
    .filter(s => s.rs >= 80 && s.chg > 0)
    .sort((a, b) => b.rs - a.rs)
    .slice(0, 6);

  return {
    scannedAt: raw.scanned_at,
    totalScanned: raw.total_scanned,
    market: { ...mkt, color },
    nasdaq: { chg: qqq.chg_1d || qqq.chg || 0, above21ema: qqq.above_ma21 || false },
    sp500:  { chg: spy.chg_1d || spy.chg || 0, above21ema: spy.above_ma21 || false },
    longStocks:  allStocksNorm,
    ma10Bounces: Array.isArray(raw.ma10_bounces) ? raw.ma10_bounces.map(norm) : [],
    ma21Bounces: Array.isArray(raw.ma21_bounces) ? raw.ma21_bounces.map(norm) : [],
    ma50Bounces: Array.isArray(raw.ma50_bounces) ? raw.ma50_bounces.map(norm) : [],
    topShorts:   Array.isArray(raw.short_signals) ? raw.short_signals.slice(0, 12).map(norm) : [],
    epSignals:   Array.isArray(raw.ep_signals)    ? raw.ep_signals.map(norm)    : [],
    hveSignals:  Array.isArray(raw.hve_signals)   ? raw.hve_signals.map(norm)   : [],
    indices: {
      SPY: { ...spy, name: "S&P 500",      ticker: "SPY" },
      QQQ: { ...qqq, name: "NASDAQ 100",   ticker: "QQQ" },
      IWM: { ...iwm, name: "RUSSELL 2000", ticker: "IWM" },
    },
    vix:          mkt.vix,
    vixLabel:     mkt.vix_label,
    breadth:      mkt.breadth || {},
    sectorRs,
    topRsGainers,
    portfolioHeat: raw.portfolio_heat || {},
  };
}

/* ─── HELPERS ────────────────────────────────────────────────────────────── */
const fmtVol = v => {
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v;
};

const fmtPrice = p => `$${p.toFixed(2)}`;

const Pill = ({ value, suffix = "%", reverse = false }) => {
  const pos = reverse ? value < 0 : value > 0;
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: 2,
      fontSize: 10,
      fontWeight: 700,
      background: pos ? "rgba(45,122,58,0.12)" : "rgba(196,58,42,0.12)",
      color: pos ? "#2d7a3a" : "#c43a2a",
      border: `1px solid ${pos ? "rgba(45,122,58,0.4)" : "rgba(196,58,42,0.4)"}`,
    }}>
      {value > 0 && "+"}{value}{suffix}
    </span>
  );
};

const MABadge = ({ ma }) => {
  const colors = { MA10: "#2962ff", MA21: "#7c4dff", MA50: "#f5a623" };
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 5px",
      borderRadius: 2,
      fontSize: 9,
      fontWeight: 700,
      background: `${colors[ma]}22`,
      color: colors[ma],
      border: `1px solid ${colors[ma]}44`,
    }}>
      {ma}
    </span>
  );
};

const ScoreBadge = ({ score }) => {
  const color = score >= 80 ? "#f23645" : score >= 60 ? "#ff9800" : "#f5a623";
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 7px",
      borderRadius: 2,
      fontSize: 10,
      fontWeight: 700,
      background: `${color}22`,
      color,
      border: `1px solid ${color}44`,
    }}>
      {score}
    </span>
  );
};

/* ─── STYLES ─────────────────────────────────────────────────────────────── */
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #ffffff;
    --bg2:     #f0f3fa;
    --bg3:     #e9ecf3;
    --bg4:     #dde1eb;
    --border:  #d1d4dc;
    --border2: #b2b5be;
    --text:    #131722;
    --text2:   #4a5066;
    --text3:   #787b86;
    --accent:  #2962ff;
    --green:   #089981;
    --red:     #f23645;
    --yellow:  #f5a623;
    --orange:  #ff9800;
    --purple:  #7c4dff;
    --cyan:    #00bcd4;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 11px;
    min-height: 100vh;
  }

  .dash { display: flex; flex-direction: column; min-height: 100vh; }

  /* Header */
  .hdr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 16px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 100;
  }
  .hdr-left { display: flex; align-items: center; gap: 16px; }
  .hdr-logo {
    font-family: 'Inter', sans-serif;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
    color: var(--accent);
    text-shadow: none;
  }
  .hdr-sub { font-size: 9px; color: var(--text3); letter-spacing: 2px; }
  .hdr-meta { display: flex; gap: 16px; align-items: center; }
  .hdr-time { color: var(--text2); font-size: 10px; }
  .live-dot {
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: var(--green);
    box-shadow: 0 0 6px rgba(45,122,58,0.4);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  /* Market bar */
  .market-bar {
    display: flex; gap: 8px; padding: 6px 16px;
    background: var(--bg2); border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }
  .mkt-chip {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 10px;
    background: var(--bg3); border: 1px solid var(--border);
    border-radius: 2px; white-space: nowrap; flex-shrink: 0;
  }
  .mkt-chip-label { color: var(--text2); font-size: 9px; letter-spacing: 1px; }

  /* Tabs */
  .tabs {
    display: flex; gap: 2px; padding: 8px 16px 0;
    border-bottom: 1px solid var(--border);
    background: var(--bg2);
  }
  .tab {
    padding: 6px 18px; cursor: pointer; border-radius: 2px 2px 0 0;
    font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
    border: 1px solid transparent; border-bottom: none;
    color: var(--text2); background: transparent;
    transition: all 0.15s;
  }
  .tab:hover { color: var(--text); background: var(--bg3); }
  .tab.active {
    color: var(--accent); background: var(--bg3);
    border-color: var(--border); border-bottom-color: var(--bg3);
  }
  .tab-short.active { color: var(--red); }

  /* Body */
  .body { padding: 12px 16px; flex: 1; }

  /* Section */
  .section { margin-bottom: 16px; }
  .section-hdr {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 8px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  .section-title {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 13px; letter-spacing: 1px;
  }
  .section-count {
    font-size: 9px; color: var(--text3);
    background: var(--bg4); border: 1px solid var(--border);
    padding: 1px 6px; border-radius: 2px;
  }

  /* Tables */
  .tbl { width: 100%; border-collapse: collapse; }
  .tbl th {
    text-align: left; padding: 4px 8px;
    font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase;
    color: var(--text3); border-bottom: 1px solid var(--border);
    white-space: nowrap; font-weight: 400;
  }
  .tbl td {
    padding: 5px 8px; border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  .tbl tr:hover td { background: rgba(0,0,0,0.03); }
  .tbl .ticker-cell {
    font-weight: 700; color: var(--accent); font-size: 12px;
    cursor: pointer; letter-spacing: 0.5px;
  }
  .tbl .ticker-cell:hover { text-decoration: underline; }

  /* Bounce cards */
  .bounce-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 8px;
  }
  .bounce-card {
    background: var(--bg3); border: 1px solid var(--border);
    border-radius: 2px; padding: 10px 12px;
    transition: border-color 0.15s;
  }
  .bounce-card:hover { border-color: var(--border2); }
  .bounce-card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
  .bounce-card-ticker { font-weight: 700; font-size: 14px; color: var(--accent); letter-spacing: 1px; }
  .bounce-card-body { display: flex; gap: 16px; font-size: 10px; color: var(--text2); }
  .bounce-stat { display: flex; flex-direction: column; gap: 1px; }
  .bounce-stat-label { font-size: 8px; letter-spacing: 1px; color: var(--text3); }
  .bounce-stat-val { color: var(--text); font-weight: 500; }

  /* Short cards */
  .short-card {
    background: rgba(255,61,94,0.04);
    border: 1px solid rgba(196,58,42,0.12);
    border-radius: 2px; padding: 10px 12px;
    transition: border-color 0.15s;
  }
  .short-card:hover { border-color: rgba(196,58,42,0.4); }
  .short-card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
  .short-card-ticker { font-weight: 700; font-size: 14px; color: var(--red); letter-spacing: 1px; }
  .short-badge {
    font-size: 9px; padding: 1px 6px; border-radius: 2px;
    background: rgba(255,145,0,0.15); color: var(--orange);
    border: 1px solid rgba(255,145,0,0.3);
  }
  .short-catalyst {
    font-size: 9px; color: var(--text2); margin-top: 5px;
    padding-top: 5px; border-top: 1px solid rgba(255,61,94,0.1);
    display: flex; gap: 12px;
  }
  .short-catalyst-item { display: flex; flex-direction: column; gap: 1px; }
  .short-catalyst-label { font-size: 8px; color: var(--text3); letter-spacing: 1px; }
  .short-catalyst-val { color: var(--text); }

  /* Criteria box */
  .criteria-box {
    background: var(--bg3); border: 1px solid var(--border);
    border-radius: 2px; padding: 12px 16px; margin-bottom: 12px;
  }
  .criteria-box.short-criteria {
    background: rgba(255,61,94,0.03);
    border-color: rgba(255,61,94,0.2);
  }
  .criteria-title {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 11px; letter-spacing: 1px; color: var(--text2);
    margin-bottom: 8px;
  }
  .criteria-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }
  .criteria-item {
    display: flex; align-items: flex-start; gap: 6px;
    font-size: 10px; color: var(--text2);
  }
  .criteria-dot { width: 4px; height: 4px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }

  /* Regime warning */
  .regime-warn {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 14px; margin-bottom: 12px;
    background: rgba(255,214,0,0.05); border: 1px solid rgba(255,214,0,0.2);
    border-radius: 2px; font-size: 10px; color: var(--yellow);
  }

  /* MA legend */
  .ma-legend { display: flex; gap: 12px; font-size: 9px; }
  .ma-legend-item { display: flex; align-items: center; gap: 4px; color: var(--text2); }
  .ma-dot { width: 8px; height: 8px; border-radius: 50%; }

  /* Empty */
  .empty { padding: 24px; text-align: center; color: var(--text3); font-size: 11px; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }
`;

/* ─── SUBCOMPONENTS ───────────────────────────────────────────────────────── */

function MarketBadge({ score, label, color }) {
  return (
    <div className="mkt-chip" style={{ borderColor: `${color}33` }}>
      <span className="mkt-chip-label">MARKET</span>
      <span style={{ color, fontWeight: 700, fontSize: 12 }}>{label}</span>
      <span style={{ color, fontWeight: 700 }}>{score}%</span>
    </div>
  );
}

function IndexChip({ name, chg, above21ema }) {
  const col = chg >= 0 ? "var(--green)" : "var(--red)";
  return (
    <div className="mkt-chip">
      <span className="mkt-chip-label">{name}</span>
      <span style={{ color: col, fontWeight: 700 }}>{chg > 0 ? "+" : ""}{chg.toFixed(2)}%</span>
      <span style={{ fontSize: 9, color: above21ema ? "var(--green)" : "var(--red)" }}>
        {above21ema ? "▲21EMA" : "▼21EMA"}
      </span>
    </div>
  );
}


// ── EP + HVE Tab ──────────────────────────────────────────────────────────────

function HVECard({ s, onQuickAdd }) {
  const entryOk   = s.hve_entry_ok;
  const borderCol = entryOk ? "#ff9f43" : "var(--border)";

  return (
    <div style={{ marginBottom:8, padding:"10px 14px", borderRadius:4,
      background:"var(--bg2)", border:`1px solid ${borderCol}`,
      borderLeft:`3px solid ${borderCol}` }}>
      <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>

        {/* Ticker */}
        <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
          style={{ fontWeight:700, fontSize:14, color:"#ff9f43", textDecoration:"none" }}>
          {s.ticker}
        </a>

        {/* Entry badge */}
        <span style={{ fontSize:9, fontWeight:700, padding:"2px 7px", borderRadius:2,
          background: entryOk ? "rgba(255,159,67,0.15)" : "var(--bg3)",
          color: entryOk ? "#ff9f43" : "var(--text3)",
          border: `1px solid ${entryOk ? "rgba(255,159,67,0.4)" : "var(--border)"}` }}>
          {entryOk ? "🔁 AT RETEST" : "👁 WATCHING"}
        </span>

        {/* Gap info */}
        <span style={{ fontSize:10, color:"var(--text2)" }}>
          Gap <strong>{s.hve_gap_pct}%</strong> · {s.hve_days_since_gap}d ago · vol {s.hve_vol_ratio}×
        </span>

        {/* Test count */}
        <span style={{ fontSize:10, color:"var(--text3)" }}>
          {s.hve_test_count} test{s.hve_test_count !== 1 ? "s" : ""} so far
        </span>

        {/* % from support */}
        {s.hve_pct_from_level != null && (
          <span style={{ fontSize:10, fontWeight:600,
            color: Math.abs(s.hve_pct_from_level) <= 3 ? "#ff9f43" : "var(--text3)" }}>
            {s.hve_pct_from_level > 0 ? "+" : ""}{s.hve_pct_from_level}% from support
          </span>
        )}

        {/* Key levels */}
        <span style={{ fontSize:10, color:"var(--text3)", marginLeft:"auto" }}>
          Support <strong style={{ color:"var(--text)" }}>${s.hve_support_level}</strong>
          {s.hve_stop && <> · Stop <strong style={{ color:"var(--red)" }}>${s.hve_stop}</strong></>}
        </span>

        {/* Log button */}
        {onQuickAdd && (
          <button onClick={() => onQuickAdd({ ...s, signal_type:"HVE" })}
            style={{ padding:"2px 8px", fontSize:9, cursor:"pointer", borderRadius:3,
              border:"1px solid #ff9f43", background:"transparent",
              color:"#ff9f43", fontFamily:"inherit" }}>+ Log</button>
        )}
      </div>
    </div>
  );
}

function EPTab({ data, onQuickAdd }) {
  // Redirect to StockbeeEPDashboard (legacy tab kept for routing)
  return <StockbeeEPDashboard onQuickAdd={onQuickAdd} />;
}

/* Legacy EP helpers removed — using Kelly-based EPCard + StockbeeEPDashboard */

function ShortsTab({ data }) {
  const { topShorts = [], market = {} } = data || {};
  const regimeMode = market?.mode;
  const [sortKey, setSortKey] = React.useState("shortScore");
  const [sortDir, setSortDir] = React.useState(-1);

  const rows = [...topShorts].sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function Th({ label, k, align = "left", def = -1 }) {
    const active = sortKey === k;
    return (
      <th onClick={() => { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : def); }}
        style={{ ...TH_STYLE, textAlign: align, color: active ? "var(--red)" : "var(--text3)" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  return (
    <div>
      {/* Regime callout */}
      {regimeMode === "SHORTS" && (
        <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 4,
          background: "rgba(242,54,69,0.07)", border: "1px solid rgba(242,54,69,0.3)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#f23645", marginBottom: 4 }}>
            🔴 REGIME DANGER — SHORT CANDIDATES ACTIVE
          </div>
          <div style={{ fontSize: 10, color: "var(--text2)" }}>
            Market score {market?.score}/100. SHORTS ONLY mode. Exit longs, size 25% on shorts.
          </div>
        </div>
      )}
      {regimeMode === "EXITS_ONLY" && (
        <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 4,
          background: "rgba(255,152,0,0.07)", border: "1px solid rgba(255,152,0,0.3)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#ff9800", marginBottom: 4 }}>
            🟠 REGIME WARN — EXITS ONLY
          </div>
          <div style={{ fontSize: 10, color: "var(--text2)" }}>
            Market score {market?.score}/100. No new longs. Trail stops, take partial profits.
          </div>
        </div>
      )}
      {market.label === "Positive" && regimeMode !== "SHORTS" && (
        <div style={{ marginBottom: 10, padding: "8px 12px", borderRadius: 3, fontSize: 10,
          background: "rgba(255,152,0,0.06)", border: "1px solid rgba(255,152,0,0.2)",
          color: "#ff9800" }}>
          ⚠ Market POSITIVE — shorts face headwind. Highest conviction only (score ≥ 80), reduce size.
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--red)", letterSpacing: 1 }}>
          ▼ SHORT SETUPS
        </span>
        <span style={{ fontSize: 9, color: "var(--text3)" }}>{rows.length} candidates</span>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: 24, textAlign: "center", color: "var(--text3)", fontSize: 11,
          background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)" }}>
          No short setups. Run a scan first.
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 650 }}>
            <thead>
              <tr>
                <Th label="Ticker"      k="ticker"     def={1} />
                <Th label="Score"       k="shortScore" align="center" />
                <Th label="RS"          k="rs"         align="center" />
                <Th label="Price"       k="price"      />
                <Th label="Chg"         k="chg"        align="center" />
                <Th label="Vol Ratio"   k="volRatio"   align="center" />
                <Th label="Days Below"  k="daysBelow"  align="center" />
                <th style={{ ...TH_STYLE, cursor: "default" }}>Setup</th>
                <th style={{ ...TH_STYLE, cursor: "default" }}>Catalyst</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.ticker}
                  onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <td style={{ ...TD, fontWeight: 700 }}>
                    <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
                      style={{ color: "var(--red)", textDecoration: "none" }}>
                      ▼ {s.ticker}
                    </a>
                    {s.failedRally && (
                      <span style={{ marginLeft: 6, fontSize: 8, fontWeight: 700, padding: "1px 4px",
                        borderRadius: 2, background: "rgba(242,54,69,0.1)", color: "var(--red)",
                        border: "1px solid rgba(242,54,69,0.3)" }}>FAILED RALLY</span>
                    )}
                  </td>
                  <td style={{ ...TD, textAlign: "center" }}>
                    <span style={{ fontWeight: 700, fontSize: 12,
                      color: (s.shortScore||0) >= 80 ? "var(--red)" : (s.shortScore||0) >= 60 ? "var(--orange)" : "var(--text3)" }}>
                      {s.shortScore != null ? s.shortScore.toFixed(0) : "—"}
                    </span>
                  </td>
                  <td style={{ ...TD, textAlign: "center", fontWeight: 700,
                    color: (s.rs||50) < 20 ? "var(--red)" : (s.rs||50) < 35 ? "var(--orange)" : "var(--text3)" }}>
                    {s.rs != null ? s.rs.toFixed(0) : "—"}
                  </td>
                  <td style={{ ...TD, fontWeight: 600 }}>
                    {s.price != null ? `$${Number(s.price).toFixed(2)}` : "—"}
                  </td>
                  <td style={{ ...TD, textAlign: "center", fontWeight: 600,
                    color: (s.chg||0) < 0 ? "var(--red)" : (s.chg||0) > 0 ? "var(--green)" : "var(--text3)" }}>
                    {s.chg != null ? `${s.chg > 0 ? "+" : ""}${s.chg.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...TD, textAlign: "center", fontWeight: 600,
                    color: (s.volRatio||0) > 1.5 ? "var(--red)" : "var(--text3)" }}>
                    {s.volRatio != null ? `${s.volRatio.toFixed(1)}×` : "—"}
                  </td>
                  <td style={{ ...TD, textAlign: "center", color: "var(--text3)" }}>
                    {s.daysBelow != null ? `${s.daysBelow}d` : "—"}
                  </td>
                  <td style={{ ...TD, fontSize: 10, color: "var(--text3)" }}>
                    {s.setupType || "—"}
                  </td>
                  <td style={{ ...TD, fontSize: 10, color: "var(--text3)" }}>
                    {s.catalyst || "—"}
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

// ── Core Stats colour helpers ────────────────────────────────────────────────
const adrCol  = v => !v ? "var(--text3)" : (v >= 3.5 && v <= 8) ? "var(--green)" : v < 3.5 ? "var(--text3)" : "var(--yellow)";
const adrBg   = v => (v >= 3.5 && v <= 8) ? "rgba(8,153,129,0.1)" : "transparent";
const e21Col  = v => v == null ? "var(--text3)" : v < 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const e21Bg   = v => v == null ? "transparent" : v < 5 ? "rgba(8,153,129,0.1)" : v <= 8 ? "rgba(245,166,35,0.08)" : "rgba(242,54,69,0.08)";
const vcsColS = v => v == null ? "var(--text3)" : v <= 2 ? "var(--green)" : v <= 3.5 ? "#5bc27a" : v <= 5 ? "var(--yellow)" : "var(--red)";
const rsColS  = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5bc27a" : r >= 70 ? "var(--yellow)" : "var(--text3)";
const rsBgS   = r => r >= 90 ? "rgba(8,153,129,0.15)" : r >= 80 ? "rgba(8,153,129,0.08)" : r >= 70 ? "rgba(245,166,35,0.1)" : "transparent";
const scoreColS = v => v >= 8 ? "var(--green)" : v >= 6.5 ? "var(--accent)" : "var(--text3)";

const TDLS = { padding: "6px 10px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", fontSize: 12 };
const THLS = {
  padding: "6px 10px", borderBottom: "2px solid var(--border)", fontSize: 9,
  letterSpacing: 1, textTransform: "uppercase", color: "var(--text3)", fontWeight: 700,
  whiteSpace: "nowrap", background: "var(--bg2)", cursor: "pointer", userSelect: "none",
};

const MA_COLORS = { MA10: "var(--cyan)", MA21: "var(--purple)", MA50: "var(--yellow)" };

// ── Signal helpers ───────────────────────────────────────────────────────────

function SignalRow({ s, onQuickAdd }) {
  const [exp, setExp] = React.useState(false);
  const maLabel = s.bouncingFrom || s._ma || "—";
  const maC = MA_COLORS[maLabel] || "var(--text3)";

  // Setup badge (HVE, EP, 3WT, etc.)
  const badges = [];
  if (s.hve_entry_ok)      badges.push({ label: "HVE↩", col: "#ff9f43" });
  else if (s.hve_detected) badges.push({ label: "HVE?",  col: "#ffd89b" });
  if (s.ep_entry_ok)       badges.push({ label: "EP✓",  col: "#00cec9" });
  else if (s.ep_detected)  badges.push({ label: "EP?",   col: "#81ecec" });
  if (s.threeWeeksTight)   badges.push({ label: "3WT",   col: "#a29bfe" });
  if (s.coiling)           badges.push({ label: "⟳",    col: "#fd79a8" });

  return (
    <>
      <tr
        onClick={() => setExp(e => !e)}
        style={{ cursor: "pointer", background: exp ? "rgba(41,98,255,0.04)" : "transparent" }}
        onMouseEnter={e  => { if (!exp) e.currentTarget.style.background = "var(--bg2)"; }}
        onMouseLeave={e  => { e.currentTarget.style.background = exp ? "rgba(41,98,255,0.04)" : "transparent"; }}
      >
        {/* MA */}
        <td style={TD}>
          <span style={{ display:"inline-block", padding:"2px 6px", borderRadius:3, fontSize:9,
            fontWeight:700, background:`${maC}18`, color:maC, border:`1px solid ${maC}40` }}>
            {maLabel}
          </span>
        </td>

        {/* Ticker + badges */}
        <td style={{ ...TD, fontWeight:700 }}>
          <div style={{ display:"flex", alignItems:"center", gap:5 }}>
            <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ color:"var(--accent)", textDecoration:"none", fontSize:13 }}>
              {s.ticker}
            </a>
            {badges.map(b => (
              <span key={b.label} style={{ fontSize:8, fontWeight:700, padding:"1px 4px",
                borderRadius:2, background:`${b.col}20`, color:b.col, border:`1px solid ${b.col}40` }}>
                {b.label}
              </span>
            ))}
          </div>
          {s.sector && <div style={{ fontSize:9, color:"var(--text3)", marginTop:1 }}>{s.sector}</div>}
        </td>

        {/* RS */}
        <td style={{ ...TD, textAlign:"center" }}>
          <span style={{ display:"inline-block", padding:"2px 7px", borderRadius:3,
            fontWeight:700, fontSize:12, background:rsBgS(s.rs), color:rsColS(s.rs),
            minWidth:30, textAlign:"center" }}>{s.rs}</span>
        </td>

        {/* Price + chg */}
        <td style={TD}>
          <span style={{ fontWeight:600 }}>${s.price != null ? Number(s.price).toFixed(2) : "—"}</span>
          {s.chg != null && (
            <span style={{ fontSize:10, marginLeft:5,
              color:(s.chg>0)?"var(--green)":(s.chg<0)?"var(--red)":"var(--text3)" }}>
              {s.chg>0?"+":""}{s.chg.toFixed(1)}%
            </span>
          )}
        </td>

        {/* VCS */}
        <td style={{ ...TD, textAlign:"center", fontWeight:700, color:vcsColS(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>

        {/* ADR */}
        <td style={{ ...TD, textAlign:"center", fontWeight:700,
          color:adrCol(s.adrPct), background:adrBg(s.adrPct) }}>
          {s.adrPct != null ? `${s.adrPct.toFixed(1)}%` : "—"}
        </td>

        {/* Stop / Target */}
        <td style={{ ...TD, fontSize:11 }}>
          {s.stop_price != null && (
            <span style={{ color:"var(--red)", fontWeight:600 }}>${Number(s.stop_price).toFixed(2)}</span>
          )}
          {s.target_1 != null && (
            <span style={{ color:"var(--green)", fontWeight:600, marginLeft:6 }}>→${Number(s.target_1).toFixed(2)}</span>
          )}
        </td>

        {/* Score */}
        <td style={{ ...TD, textAlign:"center", fontWeight:700, color:scoreColS(s.signal_score||0) }}>
          {s.signal_score != null ? s.signal_score.toFixed(1) : "—"}
        </td>

        {/* Log */}
        <td style={{ ...TD, textAlign:"center" }} onClick={e => e.stopPropagation()}>
          {onQuickAdd && (
            <button onClick={() => onQuickAdd({ ...s, signal_type: maLabel })}
              style={{ padding:"2px 7px", fontSize:9, cursor:"pointer", borderRadius:3,
                border:"1px solid var(--accent)", background:"transparent",
                color:"var(--accent)", fontFamily:"inherit" }}>+ Log</button>
          )}
        </td>
      </tr>

      {/* Inline expand — just key extra numbers, no chart */}
      {exp && (
        <tr style={{ background:"rgba(41,98,255,0.02)" }}>
          <td colSpan={9} style={{ padding:"6px 14px 8px", borderBottom:"1px solid var(--border)" }}>
            <div style={{ display:"flex", gap:14, flexWrap:"wrap", fontSize:11, alignItems:"center" }}>
              {[
                ["MA21",      s.ma21     != null && `$${Number(s.ma21).toFixed(2)}`],
                ["MA50",      s.ma50     != null && `$${Number(s.ma50).toFixed(2)}`],
                ["EMA21 LOW", s.ema21Low != null && `$${Number(s.ema21Low).toFixed(2)}`],
                ["ATR",       s.atr      != null && `$${Number(s.atr).toFixed(2)}`],
                ["EMA21L %",  s.ema21LowPct != null && `${s.ema21LowPct.toFixed(1)}%`],
                ["T2",        s.target_2 != null && `$${Number(s.target_2).toFixed(2)}`],
                ["T3",        s.target_3 != null && `$${Number(s.target_3).toFixed(2)}`],
              ].filter(([,v]) => v).map(([l,v]) => (
                <div key={l}>
                  <span style={{ fontSize:8, color:"var(--text3)", letterSpacing:1, marginRight:3 }}>{l}</span>
                  <span style={{ fontWeight:600,
                    color: l.startsWith("T") ? "var(--green)" : l === "EMA21L %" ? e21Col(s.ema21LowPct) : "var(--text)" }}>{v}</span>
                </div>
              ))}
              {s.setupTag && (
                <span style={{ padding:"1px 7px", borderRadius:3, fontSize:9, fontWeight:700,
                  background:"rgba(245,166,35,0.1)", color:"var(--yellow)", border:"1px solid rgba(245,166,35,0.3)" }}>
                  {s.setupTag}
                </span>
              )}
              {s.hve_detected && (
                <span style={{ fontSize:9, color:"#ff9f43" }}>
                  HVE gap {s.hve_gap_pct}% · {s.hve_days_since_gap}d ago · support ${s.hve_support_level} · tested {s.hve_test_count}×
                </span>
              )}
              {s.ep_detected && (
                <span style={{ fontSize:9, color:"#00cec9" }}>
                  EP gap {s.ep_gap_pct}% · {s.ep_days_ago}d ago · vol {s.ep_vol_ratio}×
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

const TD = { padding:"6px 10px", borderBottom:"1px solid var(--border)", whiteSpace:"nowrap", fontSize:12 };
const TH_STYLE = {
  padding:"5px 10px", borderBottom:"2px solid var(--border)", fontSize:9,
  letterSpacing:1, textTransform:"uppercase", color:"var(--text3)", fontWeight:700,
  whiteSpace:"nowrap", background:"var(--bg2)", cursor:"pointer", userSelect:"none",
};

function SignalTable({ ma10, ma21, ma50, onQuickAdd }) {
  const [sortKey, setSortKey] = React.useState("signal_score");
  const [sortDir, setSortDir] = React.useState(-1);
  const [maFilter, setMaFilter] = React.useState("all");

  const allSignals = [
    ...ma10.map(s => ({ ...s, _ma:"MA10" })),
    ...ma21.map(s => ({ ...s, _ma:"MA21" })),
    ...ma50.map(s => ({ ...s, _ma:"MA50" })),
  ];

  let rows = maFilter === "all" ? allSignals : allSignals.filter(s => s._ma === maFilter);
  rows = [...rows].sort((a,b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function Th({ label, k, align="left", def=-1 }) {
    const active = sortKey === k;
    return (
      <th onClick={() => { setSortKey(k); setSortDir(sortKey===k ? sortDir*-1 : def); }}
        style={{ ...TH_STYLE, textAlign:align, color:active?"var(--accent)":"var(--text3)" }}>
        {label}{active ? (sortDir>0?" ↑":" ↓") : " ↕"}
      </th>
    );
  }

  const hveCount = allSignals.filter(s => s.hve_detected).length;
  const epCount  = allSignals.filter(s => s.ep_detected).length;

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display:"flex", gap:5, marginBottom:10, flexWrap:"wrap", alignItems:"center" }}>
        {[
          ["all",  `All · ${allSignals.length}`],
          ["MA10", `MA10 · ${ma10.length}`],
          ["MA21", `MA21 · ${ma21.length}`],
          ["MA50", `MA50 · ${ma50.length}`],
        ].map(([v,l]) => {
          const c = v === "all" ? "var(--accent)" : (MA_COLORS[v] || "var(--accent)");
          const active = maFilter === v;
          return (
            <button key={v} onClick={() => setMaFilter(v)} style={{
              padding:"3px 10px", fontSize:9, textTransform:"uppercase", cursor:"pointer",
              borderRadius:3, fontFamily:"inherit", letterSpacing:0.5,
              border:`1px solid ${active ? c : "var(--border)"}`,
              background: active ? `${c}18` : "transparent",
              color: active ? c : "var(--text3)",
            }}>{l}</button>
          );
        })}
        {hveCount > 0 && (
          <span style={{ fontSize:9, color:"#ff9f43", marginLeft:4 }}>
            {hveCount} HVE retest{hveCount>1?"s":""}
          </span>
        )}
        {epCount > 0 && (
          <span style={{ fontSize:9, color:"#00cec9", marginLeft:4 }}>
            {epCount} EP setup{epCount>1?"s":""}
          </span>
        )}
        <span style={{ marginLeft:"auto", fontSize:9, color:"var(--text3)" }}>
          click row to expand · {rows.length} signals
        </span>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding:24, color:"var(--text3)", textAlign:"center", fontSize:12,
          background:"var(--bg2)", borderRadius:6, border:"1px solid var(--border)" }}>
          No signals. Run a scan first.
        </div>
      ) : (
        <div style={{ overflowX:"auto", border:"1px solid var(--border)", borderRadius:6 }}>
          <table style={{ borderCollapse:"collapse", width:"100%", minWidth:700 }}>
            <thead>
              <tr>
                <th style={{ ...TH_STYLE, width:55, cursor:"default" }}>MA</th>
                <Th label="Ticker"  k="ticker"       def={1}  />
                <Th label="RS"      k="rs"            align="center" />
                <Th label="Price"   k="price"         />
                <Th label="VCS"     k="vcs"           align="center" def={1} />
                <Th label="ADR %"   k="adrPct"        align="center" def={1} />
                <th style={{ ...TH_STYLE, cursor:"default" }}>Stop → T1</th>
                <Th label="Score"   k="signal_score"  align="center" />
                <th style={{ ...TH_STYLE, cursor:"default" }}>Log</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <SignalRow
                  key={`${s.ticker}-${s._ma}`}
                  s={s}
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

// Kept for backward-compat references but stripped down — no extra fetch
function TopPicksBar() { return null; }
function IntradayAlerts() { return null; }

function LongsTab({ data, onQuickAdd }) {
  const { ma10Bounces = [], ma21Bounces = [], ma50Bounces = [] } = data || {};
  const allLongs = [
    ...ma10Bounces.map(s => ({ ...s, _ma:"MA10" })),
    ...ma21Bounces.map(s => ({ ...s, _ma:"MA21" })),
    ...ma50Bounces.map(s => ({ ...s, _ma:"MA50" })),
  ];
  const hveReady  = allLongs.filter(s => s.hve_entry_ok);
  const epReady   = allLongs.filter(s => s.ep_entry_ok);
  const topByScore = [...allLongs].sort((a,b) => (b.signal_score||0)-(a.signal_score||0)).slice(0,5);

  return (
    <div>
      <RegimeGate compact={true} />

      {/* Focus strip — top picks at a glance */}
      {(hveReady.length > 0 || epReady.length > 0 || topByScore.length > 0) && (
        <div style={{ display:"flex", gap:6, marginBottom:12, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:9, color:"var(--text3)", letterSpacing:1, textTransform:"uppercase",
            marginRight:4, alignSelf:"center" }}>Focus →</span>

          {/* HVE retest first — highest conviction */}
          {hveReady.map(s => (
            <a key={"hve"+s.ticker} href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
              style={{ textDecoration:"none" }}>
              <span style={{ padding:"3px 9px", borderRadius:3, fontSize:10, fontWeight:700,
                background:"rgba(255,159,67,0.15)", color:"#ff9f43",
                border:"1px solid rgba(255,159,67,0.5)", cursor:"pointer" }}>
                {s.ticker} <span style={{ fontSize:8, opacity:0.7 }}>HVE↩</span>
              </span>
            </a>
          ))}

          {/* EP entry ready */}
          {epReady.map(s => (
            <a key={"ep"+s.ticker} href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
              style={{ textDecoration:"none" }}>
              <span style={{ padding:"3px 9px", borderRadius:3, fontSize:10, fontWeight:700,
                background:"rgba(0,206,201,0.12)", color:"#00cec9",
                border:"1px solid rgba(0,206,201,0.4)", cursor:"pointer" }}>
                {s.ticker} <span style={{ fontSize:8, opacity:0.7 }}>EP✓</span>
              </span>
            </a>
          ))}

          {/* Top 5 by score (deduped from above) */}
          {topByScore
            .filter(s => !hveReady.find(x=>x.ticker===s.ticker) && !epReady.find(x=>x.ticker===s.ticker))
            .slice(0,5)
            .map(s => (
              <a key={"top"+s.ticker} href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
                style={{ textDecoration:"none" }}>
                <span style={{ padding:"3px 9px", borderRadius:3, fontSize:10, fontWeight:700,
                  background:"rgba(41,98,255,0.1)", color:"var(--accent)",
                  border:"1px solid rgba(41,98,255,0.3)", cursor:"pointer" }}>
                  {s.ticker}
                  <span style={{ fontSize:8, opacity:0.6, marginLeft:4 }}>{s.signal_score?.toFixed(1)}</span>
                </span>
              </a>
          ))}
        </div>
      )}

      <SignalTable ma10={ma10Bounces} ma21={ma21Bounces} ma50={ma50Bounces} onQuickAdd={onQuickAdd} />
    </div>
  );
}


function AllStocksTab({ data }) {
  const [filter, setFilter] = useState("all");
  const [page, setPage]     = useState(0);
  const [search, setSearch] = useState("");
  const PAGE_SIZE = 50;
  const { longStocks = [] } = data || {};

  const filtered = (filter === "all"  ? longStocks
    : filter === "ma10" ? longStocks.filter(s => s.ma10Touch)
    : filter === "ma21" ? longStocks.filter(s => s.ma21Touch)
    : filter === "ma50" ? longStocks.filter(s => s.ma50Touch)
    : longStocks.filter(s => s.rs > 90)
  ).filter(s => !search || s.ticker.toUpperCase().includes(search.toUpperCase()));

  const pages   = Math.ceil(filtered.length / PAGE_SIZE);
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const btnStyle = (active) => ({
    padding: "3px 10px", cursor: "pointer", fontSize: 9,
    letterSpacing: 1, textTransform: "uppercase",
    background: active ? "var(--bg4)" : "var(--bg3)",
    border: `1px solid ${active ? "var(--border2)" : "var(--border)"}`,
    color: active ? "var(--text)" : "var(--text3)",
    borderRadius: 2, fontFamily: "inherit",
  });

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center", flexWrap: "wrap" }}>
        {[["all","All"], ["ma10","MA10"], ["ma21","MA21"], ["ma50","MA50"], ["rs90","RS > 90"]].map(([k,l]) => (
          <button key={k} style={btnStyle(filter === k)} onClick={() => { setFilter(k); setPage(0); }}>{l}</button>
        ))}
        <input
          placeholder="Search ticker..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0); }}
          style={{
            marginLeft: "auto", padding: "3px 8px", fontSize: 10, background: "var(--bg3)",
            border: "1px solid var(--border)", color: "var(--text)", borderRadius: 2,
            fontFamily: "inherit", outline: "none", width: 120,
          }}
        />
        <span style={{ fontSize: 9, color: "var(--text3)" }}>{filtered.length} stocks</span>
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th>TICKER</th><th>PRICE</th><th>CHG%</th>
            <th>MA10</th><th>MA21</th><th>MA50</th>
            <th>BOUNCE</th><th>VOL RATIO</th><th>RS (M)</th><th>VCS</th><th>W TF</th><th>SECTOR</th>
          </tr>
        </thead>
        <tbody>
          {visible.map(s => (
            <tr key={s.ticker}>
              <td className="ticker-cell"><TVLink ticker={s.ticker}>{s.ticker} ↗</TVLink></td>
              <td>{fmtPrice(s.price)}</td>
              <td><Pill value={s.chg} /></td>
              <td style={{ color: s.ma10Touch ? "var(--cyan)" : "var(--text2)" }}>{fmtPrice(s.ma10)}</td>
              <td style={{ color: s.ma21Touch ? "var(--purple)" : "var(--text2)" }}>{fmtPrice(s.ma21)}</td>
              <td style={{ color: s.ma50Touch ? "var(--yellow)" : "var(--text2)" }}>{fmtPrice(s.ma50)}</td>
              <td>{s.bouncingFrom ? <MABadge ma={s.bouncingFrom} /> : <span style={{ color: "var(--text3)" }}>—</span>}</td>
              <td style={{ color: s.volRatio > 1.5 ? "var(--green)" : s.volRatio > 1.2 ? "var(--yellow)" : "var(--text2)" }}>
                {s.volRatio != null ? `${s.volRatio}x` : "—"}
              </td>
              <td style={{ color: s.rs > 90 ? "var(--green)" : s.rs > 80 ? "var(--yellow)" : "var(--text2)" }}>
                {s.rs != null ? s.rs.toFixed(0) : "—"}
              </td>
              <td style={{ color: "var(--text2)" }}>{s.vcs != null ? s.vcs : "—"}</td>
              <td style={{
                color: (s.wEma10 ?? s.w_ema10) == null ? "var(--text3)"
                     : (s.wStackOk ?? s.w_stack_ok) ? "var(--green)" : "var(--orange)",
                fontWeight: 700, fontSize: 10,
              }}>
                {(s.wEma10 ?? s.w_ema10) == null ? "—" : (s.wStackOk ?? s.w_stack_ok) ? "✓" : "✗"}
              </td>
              <td style={{ color: "var(--text3)" }}>{s.sector}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      {pages > 1 && (
        <div style={{ display: "flex", gap: 6, marginTop: 10, alignItems: "center" }}>
          <button style={btnStyle(false)} onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
          <span style={{ fontSize: 10, color: "var(--text2)" }}>Page {page + 1} / {pages}</span>
          <button style={btnStyle(false)} onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page === pages - 1}>Next →</button>
        </div>
      )}
    </div>
  );
}


/* ─── MARKET OVERVIEW TAB ────────────────────────────────────────────────── */
// ── Focus Tab — top 8 names across all signal types ──────────────────────────

// ── Weekly Tab ────────────────────────────────────────────────────────────────

const SIGNAL_TYPE_META = {
  WEEKLY_MA_BOUNCE:    { label: "wEMA Bounce",  color: "#7c4dff", bg: "rgba(124,77,255,0.1)" },
  WEEKLY_VCP:          { label: "Weekly VCP",   color: "#00cec9", bg: "rgba(0,206,201,0.1)"  },
  WEEKLY_BO_RETEST:    { label: "BO Retest",    color: "#00b894", bg: "rgba(0,184,148,0.1)"  },
};

function WeeklySignalRow({ s, onQuickAdd }) {
  const [expanded, setExpanded] = useState(false);
  const meta = SIGNAL_TYPE_META[s.signal_type] || { label: s.signal_type, color: "var(--text3)", bg: "var(--bg3)" };
  const riskPct = s.stop_price && s.price ? ((s.price - s.stop_price) / s.price * 100).toFixed(1) : null;
  const t1rr    = s.target_1 && s.price && s.stop_price
    ? ((s.target_1 - s.price) / (s.price - s.stop_price)).toFixed(1)
    : null;

  return (
    <>
      <tr onClick={() => setExpanded(e => !e)} style={{ cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(124,77,255,0.03)" : "transparent"}>

        {/* Signal type badge */}
        <td style={{ ...TD, width: 110 }}>
          <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
            background: meta.bg, color: meta.color, border: `1px solid ${meta.color}40`,
            whiteSpace: "nowrap" }}>
            {meta.label}
          </span>
        </td>

        {/* Ticker */}
        <td style={{ ...TD, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: meta.color, textDecoration: "none", fontWeight: 700 }}>
            {s.ticker}
          </a>
          {s.bounce_ma && (
            <span style={{ marginLeft: 6, fontSize: 9, color: "var(--text3)" }}>{s.bounce_ma}</span>
          )}
          {s.stage && s.stage === "retesting" && (
            <span style={{ marginLeft: 6, fontSize: 8, padding: "1px 4px", borderRadius: 2,
              background: "rgba(0,184,148,0.12)", color: "#00b894",
              border: "1px solid rgba(0,184,148,0.3)" }}>AT LEVEL</span>
          )}
        </td>

        {/* RS */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ fontWeight: 700, fontSize: 12, color: rsColS(s.rs || 50) }}>
            {s.rs != null ? Math.round(s.rs) : "—"}
          </span>
        </td>

        {/* Price */}
        <td style={{ ...TD }}>
          <span style={{ fontWeight: 600 }}>${s.price != null ? Number(s.price).toFixed(2) : "—"}</span>
          {s.chg != null && (
            <span style={{ fontSize: 10, marginLeft: 6,
              color: s.chg > 0 ? "var(--green)" : s.chg < 0 ? "var(--red)" : "var(--text3)" }}>
              {s.chg > 0 ? "+" : ""}{s.chg.toFixed(1)}%
            </span>
          )}
        </td>

        {/* Weekly score */}
        <td style={{ ...TD, textAlign: "center" }}>
          <span style={{ fontWeight: 700, fontSize: 12,
            color: (s.signal_score||0) >= 8 ? "var(--green)" : (s.signal_score||0) >= 6.5 ? meta.color : "var(--text3)" }}>
            {s.signal_score != null ? s.signal_score.toFixed(1) : "—"}
          </span>
        </td>

        {/* Stop → T1 */}
        <td style={{ ...TD, fontSize: 10 }}>
          {s.stop_price && <span style={{ color: "var(--red)" }}>${Number(s.stop_price).toFixed(2)}</span>}
          {s.target_1   && <span style={{ color: "var(--green)", marginLeft: 6 }}>→ ${Number(s.target_1).toFixed(2)}</span>}
        </td>

        {/* Risk / RR */}
        <td style={{ ...TD, textAlign: "center", fontSize: 10, color: "var(--text3)" }}>
          {riskPct && <span style={{ color: "var(--red)" }}>{riskPct}%</span>}
          {t1rr && <span style={{ color: "var(--green)", marginLeft: 6 }}>{t1rr}R</span>}
        </td>

        {/* Expand indicator */}
        <td style={{ ...TD, textAlign: "center", color: "var(--text3)", fontSize: 10 }}>
          {expanded ? "▲" : "▼"}
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr style={{ background: "rgba(124,77,255,0.03)" }}>
          <td colSpan={8} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 10 }}>
              {s.wema10 && <span><span style={{ color: "var(--text3)" }}>wEMA10 </span><strong>${Number(s.wema10).toFixed(2)}</strong></span>}
              {s.wema40 && <span><span style={{ color: "var(--text3)" }}>wEMA40 </span><strong>${Number(s.wema40).toFixed(2)}</strong></span>}
              {s.resistance && <span><span style={{ color: "var(--text3)" }}>Resistance </span><strong>${Number(s.resistance).toFixed(2)}</strong></span>}
              {s.vol_ratio != null && <span><span style={{ color: "var(--text3)" }}>Vol ratio </span>
                <strong style={{ color: s.vol_contracted ? "var(--green)" : "var(--text)" }}>
                  {Number(s.vol_ratio).toFixed(2)}× {s.vol_contracted ? "✓ contracting" : ""}
                </strong>
              </span>}
              {s.avg_weekly_range != null && <span><span style={{ color: "var(--text3)" }}>Avg weekly range </span><strong>{s.avg_weekly_range}%</strong></span>}
              {s.contracting_weeks && <span><span style={{ color: "var(--text3)" }}>Contracting weeks </span><strong>{s.contracting_weeks}</strong></span>}
              {s.spread_3w_pct != null && <span><span style={{ color: "var(--text3)" }}>3w spread </span><strong>{s.spread_3w_pct}%</strong></span>}
              {s.weeks_since_bo != null && <span><span style={{ color: "var(--text3)" }}>Weeks since BO </span><strong>{s.weeks_since_bo}</strong></span>}
              {s.ma_stack != null && <span><span style={{ color: "var(--text3)" }}>MA stack </span><strong>{s.ma_stack}/3</strong></span>}
              {s.target_2 && <span><span style={{ color: "var(--text3)" }}>T2 </span><strong style={{ color: "var(--green)" }}>${Number(s.target_2).toFixed(2)}</strong></span>}
              {onQuickAdd && (
                <button onClick={e => { e.stopPropagation(); onQuickAdd({ ...s, signal_type: s.signal_type }); }}
                  style={{ padding: "2px 8px", fontSize: 9, cursor: "pointer", borderRadius: 3,
                    border: `1px solid ${meta.color}`, background: "transparent",
                    color: meta.color, fontFamily: "inherit", marginLeft: "auto" }}>+ Log</button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function WeeklyBtPanel() {
  const [stats, setStats]     = useState(null);
  const [progress, setProgress] = useState(null);
  const [running, setRunning]   = useState(false);

  const loadStats = () => {
    fetch("/api/weekly-bt/stats").then(r => r.json()).then(setStats).catch(() => {});
    fetch("/api/weekly-bt/status").then(r => r.json()).then(p => {
      setProgress(p);
      setRunning(p?.status === "running");
    }).catch(() => {});
  };

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 8000);
    return () => clearInterval(interval);
  }, []);

  const triggerReconstruct = () => {
    const secret = prompt("Enter trigger secret:");
    if (!secret) return;
    setRunning(true);
    fetch(`/api/weekly-bt/reconstruct?secret=${encodeURIComponent(secret)}&lookback_weeks=250`, { method: "POST" })
      .then(r => r.json()).then(() => loadStats()).catch(() => setRunning(false));
  };

  const ExitBar = ({ reasons, total }) => {
    const cols = { stop: "var(--red)", t1: "var(--green)", t2: "#00b894", timeout: "var(--text3)", data_end: "var(--border)" };
    return (
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", gap: 1, marginTop: 6 }}>
        {Object.entries(reasons || {}).filter(([k]) => k !== "data_end").map(([k, v]) => (
          <div key={k} style={{ flex: v, background: cols[k] || "var(--text3)" }} title={`${k}: ${v}`} />
        ))}
      </div>
    );
  };

  return (
    <div style={{ marginTop: 20, padding: "12px 14px", borderRadius: 6,
      background: "var(--bg2)", border: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text3)", letterSpacing: 1 }}>
          📊 WEEKLY BACKTEST
        </span>
        {progress?.status === "running" && (
          <span style={{ fontSize: 9, color: "var(--yellow)" }}>
            Running… {progress.done_weeks}/{progress.total_weeks} weeks ({progress.pct}%)
          </span>
        )}
        {progress?.status === "complete" && (
          <span style={{ fontSize: 9, color: "var(--green)" }}>
            ✓ {progress.trades} trades · {progress.total_weeks} weeks
          </span>
        )}
        <button onClick={triggerReconstruct} disabled={running}
          style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 9, cursor: running ? "not-allowed" : "pointer",
            borderRadius: 3, border: "1px solid var(--border)", background: "transparent",
            color: running ? "var(--text3)" : "var(--text)", fontFamily: "inherit" }}>
          {running ? "Running…" : "▶ Run Backtest"}
        </button>
      </div>

      {(!stats || stats.total_trades === 0) ? (
        <div style={{ fontSize: 10, color: "var(--text3)", textAlign: "center", padding: "16px 0" }}>
          No weekly backtest data yet. Click "Run Backtest" to generate 52-week results.
        </div>
      ) : (
        <>
          {/* Key stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 10, marginBottom: 14 }}>
            {[
              { label: "WIN RATE",    val: `${stats.win_rate}%`,       col: stats.win_rate >= 50 ? "var(--green)" : "var(--red)" },
              { label: "AVG WIN",     val: `+${stats.avg_win_pct}%`,   col: "var(--green)" },
              { label: "AVG LOSS",    val: `${stats.avg_loss_pct}%`,   col: "var(--red)" },
              { label: "AVG R",       val: `${stats.avg_r}R`,          col: stats.avg_r >= 1 ? "var(--green)" : "var(--text3)" },
              { label: "EXPECTANCY",  val: `${stats.expectancy}%`,     col: stats.expectancy > 0 ? "var(--green)" : "var(--red)" },
              { label: "AVG HOLD",    val: `${stats.avg_hold_weeks}w`, col: "var(--text)" },
              { label: "TOTAL",       val: stats.total_trades,         col: "var(--text3)" },
            ].map(({ label, val, col }) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: col }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Exit reason bar */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>EXIT REASONS</div>
            <ExitBar reasons={stats.exit_reasons} total={stats.total_trades} />
            <div style={{ display: "flex", gap: 12, marginTop: 4, flexWrap: "wrap" }}>
              {Object.entries(stats.exit_reasons || {}).filter(([k]) => k !== "data_end").map(([k, v]) => (
                <span key={k} style={{ fontSize: 9, color: "var(--text3)" }}>
                  {k}: <strong style={{ color: "var(--text)" }}>{v}</strong>
                </span>
              ))}
            </div>
          </div>

          {/* By signal type */}
          {stats.by_signal_type && Object.keys(stats.by_signal_type).length > 0 && (
            <div>
              <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 6 }}>BY SETUP TYPE</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {Object.entries(stats.by_signal_type).map(([type, d]) => {
                  const meta = SIGNAL_TYPE_META[type] || { label: type, color: "var(--text3)" };
                  return (
                    <div key={type} style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 10 }}>
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 2,
                        background: meta.bg, color: meta.color, minWidth: 90 }}>{meta.label}</span>
                      <span style={{ color: "var(--text3)" }}>{d.trades} trades</span>
                      <span style={{ color: d.win_rate >= 50 ? "var(--green)" : "var(--red)" }}>{d.win_rate}% WR</span>
                      <span style={{ color: d.avg_r >= 1 ? "var(--green)" : "var(--text3)" }}>{d.avg_r}R avg</span>
                      <span style={{ color: d.avg_pnl >= 0 ? "var(--green)" : "var(--red)" }}>{d.avg_pnl > 0 ? "+" : ""}{d.avg_pnl}% avg</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function WeeklyTab({ onQuickAdd }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView]       = useState("all");   // "all" | "bounce" | "vcp" | "retest"
  const [sortKey, setSortKey] = useState("signal_score");
  const [sortDir, setSortDir] = useState(-1);
  const [showBt, setShowBt]   = useState(false);

  useEffect(() => {
    fetch("/api/weekly-scan")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 12 }}>
      Loading weekly signals…
    </div>
  );

  const signals = data?.status === "ok" ? (
    view === "bounce" ? (data.ma_bounces || []) :
    view === "vcp"    ? (data.vcps       || []) :
    view === "retest" ? (data.bo_retests || []) :
    (data.all_weekly  || [])
  ) : [];

  const sorted = [...signals].sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function Th({ label, k, align = "left", def = -1 }) {
    const active = sortKey === k;
    return (
      <th onClick={() => { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : def); }}
        style={{ ...TH_STYLE, textAlign: align, color: active ? "#7c4dff" : "var(--text3)", cursor: "pointer" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  const counts = data?.status === "ok" ? {
    all:    (data.all_weekly  || []).length,
    bounce: (data.ma_bounces  || []).length,
    vcp:    (data.vcps        || []).length,
    retest: (data.bo_retests  || []).length,
  } : {};

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#7c4dff", letterSpacing: 1 }}>
            📅 WEEKLY SETUPS
          </div>
          <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 2 }}>
            Weekly timeframe signals — fewer, higher conviction, longer holds
            {data?.scanned_at && ` · Updated ${new Date(data.scanned_at).toLocaleDateString()}`}
          </div>
        </div>

        {/* Backtest toggle */}
        <button onClick={() => setShowBt(b => !b)}
          style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 9, cursor: "pointer",
            borderRadius: 3, border: `1px solid ${showBt ? "#7c4dff" : "var(--border)"}`,
            background: showBt ? "rgba(124,77,255,0.1)" : "transparent",
            color: showBt ? "#7c4dff" : "var(--text3)", fontFamily: "inherit" }}>
          📊 Backtest
        </button>
      </div>

      {/* Backtest panel */}
      {showBt && <WeeklyBtPanel />}

      {/* No data state */}
      {(!data || data.status === "no_data") && (
        <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text3)", fontSize: 11,
          background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)", marginTop: 12 }}>
          <div style={{ fontSize: 16, marginBottom: 8 }}>📅</div>
          <div>No weekly scan data yet.</div>
          <div style={{ marginTop: 6, fontSize: 10 }}>
            Weekly signals are generated automatically every <strong>Saturday at 10:30 UK</strong> after the weekend scan.
            You can also trigger manually via the API.
          </div>
        </div>
      )}

      {data?.status === "ok" && (
        <>
          {/* Filter pills */}
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            {[
              { key: "all",    label: "All Signals",    count: counts.all    },
              { key: "bounce", label: "wEMA Bounce",    count: counts.bounce },
              { key: "vcp",    label: "Weekly VCP",     count: counts.vcp    },
              { key: "retest", label: "BO Retest",      count: counts.retest },
            ].map(({ key, label, count }) => {
              const active = view === key;
              const meta = key === "bounce" ? SIGNAL_TYPE_META.WEEKLY_MA_BOUNCE
                         : key === "vcp"    ? SIGNAL_TYPE_META.WEEKLY_VCP
                         : key === "retest" ? SIGNAL_TYPE_META.WEEKLY_BO_RETEST
                         : { color: "#7c4dff", bg: "rgba(124,77,255,0.1)" };
              return (
                <button key={key} onClick={() => setView(key)} style={{
                  padding: "4px 12px", fontSize: 10, cursor: "pointer", borderRadius: 3,
                  fontFamily: "inherit",
                  border: `1px solid ${active ? meta.color : "var(--border)"}`,
                  background: active ? meta.bg : "transparent",
                  color: active ? meta.color : "var(--text3)",
                }}>
                  {label} {count != null && <span style={{ fontSize: 9 }}>({count})</span>}
                </button>
              );
            })}
          </div>

          {sorted.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text3)", fontSize: 11,
              background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)" }}>
              No signals in this category.
            </div>
          ) : (
            <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 700 }}>
                <thead>
                  <tr>
                    <th style={{ ...TH_STYLE, cursor: "default" }}>Type</th>
                    <Th label="Ticker"  k="ticker"       def={1} />
                    <Th label="RS"      k="rs"           align="center" />
                    <Th label="Price"   k="price"        />
                    <Th label="Score"   k="signal_score" align="center" />
                    <th style={{ ...TH_STYLE, cursor: "default" }}>Stop → T1</th>
                    <th style={{ ...TH_STYLE, cursor: "default", textAlign: "center" }}>Risk / RR</th>
                    <th style={{ ...TH_STYLE, cursor: "default", textAlign: "center" }}>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(s => (
                    <WeeklySignalRow key={s.ticker + s.signal_type} s={s} onQuickAdd={onQuickAdd} />
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

function FocusTab({ data, onQuickAdd }) {
  const [focus, setFocus]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [maxPicks, setMaxPicks] = useState(8);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/focus-list?max_picks=${maxPicks}`)
      .then(r => r.json())
      .then(d => { setFocus(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [maxPicks]);

  const SOURCE_STYLE = {
    HVE_RETEST: { label:"HVE↩ RETEST",  col:"#ff9f43", bg:"rgba(255,159,67,0.12)" },
    HVE_WATCH:  { label:"HVE WATCH",     col:"#ffd89b", bg:"rgba(255,216,155,0.08)" },
    EP_READY:   { label:"EP ✓",          col:"#00cec9", bg:"rgba(0,206,201,0.1)" },
    EP_WATCH:   { label:"EP WATCH",      col:"#81ecec", bg:"rgba(129,236,236,0.07)" },
    MA10:       { label:"MA10 BOUNCE",   col:"var(--cyan)",   bg:"rgba(0,229,255,0.07)" },
    MA21:       { label:"MA21 BOUNCE",   col:"var(--purple)", bg:"rgba(124,77,255,0.07)" },
    MA50:       { label:"MA50 BOUNCE",   col:"var(--yellow)", bg:"rgba(245,166,35,0.07)" },
    PATTERN:    { label:"PATTERN",       col:"var(--text3)",  bg:"var(--bg3)" },
  };

  const TIER_STYLE = {
    TAKE:    { label:"ACT NOW",  col:"#00f5a0", dot:"●" },
    WATCH:   { label:"WATCH",    col:"#00c8ff", dot:"◉" },
    MONITOR: { label:"MONITOR",  col:"var(--text3)", dot:"○" },
  };

  if (loading) return (
    <div style={{ padding:40, textAlign:"center", color:"var(--text3)", fontSize:12 }}>
      Loading focus list…
    </div>
  );

  if (!focus || !focus.focus_list) return (
    <div style={{ padding:40, textAlign:"center", color:"var(--text3)", fontSize:12 }}>
      No focus data. Run a scan first.
    </div>
  );

  const { focus_list = [], summary = {}, market_score, market_label, scanned_at } = focus;

  return (
    <div>
      <RegimeGate compact={true} />

      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14, flexWrap:"wrap" }}>
        <div>
          <div style={{ fontSize:11, fontWeight:700, color:"var(--accent)", letterSpacing:1 }}>
            🎯 FOCUS LIST
          </div>
          <div style={{ fontSize:9, color:"var(--text3)", marginTop:2 }}>
            Top names across all signal types · {summary.total_scanned || 0} candidates ranked
            {scanned_at && ` · ${new Date(scanned_at).toLocaleTimeString()}`}
          </div>
        </div>

        {/* Stats */}
        <div style={{ display:"flex", gap:8, marginLeft:"auto", flexWrap:"wrap" }}>
          {summary.hve_in_list > 0 && (
            <span style={{ fontSize:9, padding:"2px 8px", borderRadius:3,
              background:"rgba(255,159,67,0.12)", color:"#ff9f43",
              border:"1px solid rgba(255,159,67,0.3)" }}>
              {summary.hve_in_list} HVE
            </span>
          )}
          {summary.ep_in_list > 0 && (
            <span style={{ fontSize:9, padding:"2px 8px", borderRadius:3,
              background:"rgba(0,206,201,0.1)", color:"#00cec9",
              border:"1px solid rgba(0,206,201,0.3)" }}>
              {summary.ep_in_list} EP
            </span>
          )}
          {summary.ma_in_list > 0 && (
            <span style={{ fontSize:9, padding:"2px 8px", borderRadius:3,
              background:"rgba(41,98,255,0.08)", color:"var(--accent)",
              border:"1px solid rgba(41,98,255,0.25)" }}>
              {summary.ma_in_list} MA bounce
            </span>
          )}
        </div>

        {/* Max picks control */}
        <div style={{ display:"flex", gap:4, alignItems:"center" }}>
          <span style={{ fontSize:9, color:"var(--text3)" }}>Show</span>
          {[5, 8, 12].map(n => (
            <button key={n} onClick={() => setMaxPicks(n)} style={{
              padding:"2px 7px", fontSize:9, cursor:"pointer", borderRadius:3,
              fontFamily:"inherit",
              border:`1px solid ${maxPicks===n ? "var(--accent)" : "var(--border)"}`,
              background: maxPicks===n ? "rgba(41,98,255,0.1)" : "transparent",
              color: maxPicks===n ? "var(--accent)" : "var(--text3)",
            }}>{n}</button>
          ))}
        </div>
      </div>

      {/* Cards */}
      {focus_list.length === 0 ? (
        <div style={{ padding:32, textAlign:"center", color:"var(--text3)", fontSize:11,
          background:"var(--bg2)", borderRadius:6, border:"1px solid var(--border)" }}>
          No signals found. Run a scan first.
        </div>
      ) : (
        <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
          {focus_list.map((s, i) => {
            const tier = TIER_STYLE[s.priority_tier] || TIER_STYLE.MONITOR;
            const src  = SOURCE_STYLE[s.focus_source] || SOURCE_STYLE.PATTERN;
            const isTop3 = i < 3;
            return (
              <div key={s.ticker} style={{
                padding:"10px 14px", borderRadius:5,
                background: isTop3 ? "rgba(41,98,255,0.04)" : "var(--bg2)",
                border:`1px solid ${isTop3 ? "rgba(41,98,255,0.2)" : "var(--border)"}`,
                borderLeft:`3px solid ${tier.col}`,
              }}>
                <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>

                  {/* Rank */}
                  <span style={{ fontSize:11, fontWeight:700, color:"var(--text3)",
                    minWidth:18, textAlign:"center" }}>#{i+1}</span>

                  {/* Tier dot */}
                  <span style={{ fontSize:10, color:tier.col }} title={tier.label}>{tier.dot}</span>

                  {/* Ticker */}
                  <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
                    style={{ fontWeight:700, fontSize:14, color:"var(--accent)", textDecoration:"none" }}>
                    {s.ticker}
                  </a>

                  {/* Source badge */}
                  <span style={{ fontSize:8, fontWeight:700, padding:"2px 6px", borderRadius:2,
                    background:src.bg, color:src.col, border:`1px solid ${src.col}30` }}>
                    {src.label}
                  </span>

                  {/* MA type if bounce */}
                  {s._ma && (
                    <span style={{ fontSize:9, color: MA_COLORS[s._ma] || "var(--text3)" }}>
                      {s._ma}
                    </span>
                  )}

                  {/* Sector */}
                  {s.sector && (
                    <span style={{ fontSize:10, color:"var(--text3)" }}>{s.sector}</span>
                  )}

                  {/* Key stats */}
                  <div style={{ marginLeft:"auto", display:"flex", gap:14, alignItems:"center", flexWrap:"wrap" }}>
                    <span>
                      <span style={{ fontSize:8, color:"var(--text3)", marginRight:3 }}>RS</span>
                      <span style={{ fontSize:12, fontWeight:700, color:rsColS(s.rs) }}>{s.rs}</span>
                    </span>
                    <span>
                      <span style={{ fontSize:8, color:"var(--text3)", marginRight:3 }}>VCS</span>
                      <span style={{ fontSize:12, fontWeight:700, color:vcsColS(s.vcs) }}>
                        {s.vcs != null ? s.vcs.toFixed(1) : "—"}
                      </span>
                    </span>
                    <span style={{ fontSize:11, fontWeight:600 }}>
                      ${s.price != null ? Number(s.price).toFixed(2) : "—"}
                      {s.chg != null && (
                        <span style={{ fontSize:10, marginLeft:5,
                          color:(s.chg>0)?"var(--green)":(s.chg<0)?"var(--red)":"var(--text3)" }}>
                          {s.chg>0?"+":""}{s.chg.toFixed(1)}%
                        </span>
                      )}
                    </span>
                    <span>
                      <span style={{ fontSize:8, color:"var(--text3)", marginRight:3 }}>SCORE</span>
                      <span style={{ fontSize:11, fontWeight:700, color:scoreColS(s.focus_score/10) }}>
                        {s.focus_score != null ? s.focus_score.toFixed(0) : "—"}
                      </span>
                    </span>
                    {s.stop_price && (
                      <span style={{ fontSize:10 }}>
                        <span style={{ color:"var(--red)" }}>SL ${Number(s.stop_price).toFixed(2)}</span>
                        {s.target_1 && <span style={{ color:"var(--green)", marginLeft:6 }}>T1 ${Number(s.target_1).toFixed(2)}</span>}
                      </span>
                    )}
                    {onQuickAdd && (
                      <button onClick={() => onQuickAdd({ ...s, signal_type: s.focus_source || s._ma })}
                        style={{ padding:"2px 8px", fontSize:9, cursor:"pointer", borderRadius:3,
                          border:"1px solid var(--accent)", background:"transparent",
                          color:"var(--accent)", fontFamily:"inherit" }}>+ Log</button>
                    )}
                  </div>
                </div>

                {/* Priority reasoning */}
                {s.priority_reason && (
                  <div style={{ fontSize:9, color:"var(--text3)", marginTop:5, paddingLeft:28 }}>
                    {s.priority_reason}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MarketTab({ data }) {
  const { indices = {}, vix, vixLabel, breadth = {}, sectorRs = {}, topRsGainers = [], market = {} } = data || {};

  const chgColor = v => v > 0 ? "#2d7a3a" : v < 0 ? "#c43a2a" : "var(--text3)";
  const rsColor  = v => v >= 90 ? "#2d7a3a" : v >= 70 ? "#b8820a" : v >= 50 ? "var(--text2)" : "#c43a2a";
  const rsLabel  = v => v >= 90 ? "#2d7a3a" : v >= 70 ? "#7a9a2a" : v >= 50 ? "#b8820a" : "#c43a2a";

  const indexList = [
    { ticker: "SPY",  name: "S&P 500",      ...(indices.SPY || {}) },
    { ticker: "QQQ",  name: "NASDAQ 100",   ...(indices.QQQ || {}) },
    { ticker: "IWM",  name: "RUSSELL 2000", ...(indices.IWM || {}) },
    { ticker: "VIX",  name: "VOLATILITY",   price: vix, chg_1d: null, special: "vix", label: vixLabel },
  ];

  // Sector table from sector_rs
  const sectors = Object.entries(sectorRs || {})
    .map(([name, d]) => ({ name, ...d }))
    .sort((a, b) => (a.rank || 99) - (b.rank || 99));

  const cardStyle = {
    background: "var(--bg2)", border: "1px solid var(--border)",
    borderRadius: 4, padding: "14px 18px", minWidth: 160, flex: 1,
  };

  return (
    <div>
      {/* Index cards row */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {indexList.map(idx => (
          <div key={idx.ticker} style={cardStyle}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)", letterSpacing: 1 }}>{idx.ticker}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: "4px 0" }}>
              {idx.price ? `$${Number(idx.price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
            </div>
            {idx.chg_1d != null ? (
              <div style={{ fontSize: 12, fontWeight: 700, color: chgColor(idx.chg_1d) }}>
                {idx.chg_1d > 0 ? "+" : ""}{idx.chg_1d?.toFixed(2)}%
              </div>
            ) : idx.special === "vix" && idx.label ? (
              <div style={{ fontSize: 11, color: vix > 25 ? "#c43a2a" : "#b8820a" }}>{idx.label}</div>
            ) : null}
            <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 4, letterSpacing: 1 }}>{idx.name}</div>
            {idx.above_ma50 != null && (
              <div style={{ fontSize: 9, marginTop: 4, color: idx.above_ma50 ? "#2d7a3a" : "#c43a2a" }}>
                {idx.above_ma50 ? "▲ Above 50MA" : "▼ Below 50MA"}
                {idx.above_ma200 != null && (
                  <span style={{ marginLeft: 6, color: idx.above_ma200 ? "#2d7a3a" : "#c43a2a" }}>
                    · {idx.above_ma200 ? "▲ 200MA" : "▼ 200MA"}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
        {/* Market health card */}
        <div style={{ ...cardStyle, borderLeft: `3px solid ${market.color}` }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, color: "var(--text)" }}>MARKET HEALTH</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: market.color, margin: "4px 0" }}>
            {market.label} {market.score}%
          </div>
          {breadth.breadth_50ma_pct != null && (
            <div style={{ fontSize: 10, color: "var(--text2)", marginTop: 2 }}>
              Breadth: {breadth.breadth_50ma_pct}% above 50MA
            </div>
          )}
          {market.regime_warning && (
            <div style={{ fontSize: 9, color: "#b8820a", marginTop: 4 }}>⚠ {market.regime_warning}</div>
          )}
          <div style={{ fontSize: 9, color: "var(--text3)", marginTop: 4, letterSpacing: 1 }}>REGIME SCORE</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16 }}>
        {/* Left: Top RS gainers */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, color: "var(--text3)", marginBottom: 8 }}>
            TOP RS GAINERS (TODAY)
          </div>
          {topRsGainers.length === 0 && (
            <div style={{ fontSize: 10, color: "var(--text3)" }}>Run a scan to see RS gainers</div>
          )}
          {topRsGainers.map(s => (
            <div key={s.ticker} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "8px 10px", marginBottom: 4,
              background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 3,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 2,
                  background: rsLabel(s.rs), color: "#fff", minWidth: 32, textAlign: "center",
                }}>RS:{s.rs}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>{s.ticker}</div>
                  <div style={{ fontSize: 9, color: "var(--text3)" }}>{s.sector || "—"}</div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>${s.price?.toFixed(2)}</div>
                <div style={{ fontSize: 10, fontWeight: 700, color: chgColor(s.chg) }}>
                  {s.chg > 0 ? "+" : ""}{s.chg?.toFixed(2)}%
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Right: Sector leaders table */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, color: "var(--text3)", marginBottom: 8 }}>
            SECTOR LEADERS
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr>
                {["#","SECTOR","ETF","1D RS","1W RS","1M RS","TREND"].map(h => (
                  <th key={h} style={{
                    textAlign: h === "#" ? "center" : "left", padding: "4px 8px", fontSize: 9,
                    color: "var(--text3)", borderBottom: "1px solid var(--border)",
                    letterSpacing: 1,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sectors.map((s, i) => {
                const etfName = s.etf || "—";
                const fmtRs = v => v != null ? `${v > 0 ? "+" : ""}${v.toFixed(2)}%` : "—";
                return (
                  <tr key={s.name} style={{ background: i % 2 === 0 ? "transparent" : "var(--bg2)" }}>
                    <td style={{ padding: "6px 8px", textAlign: "center" }}>
                      <span style={{
                        display: "inline-block", minWidth: 22, textAlign: "center",
                        padding: "1px 4px", borderRadius: 2, fontSize: 10, fontWeight: 700,
                        background: rsColor(s.rank ? Math.max(0, (16 - s.rank) / 15 * 100) : 50),
                        color: "#fff",
                      }}>{s.rank || "—"}</span>
                    </td>
                    <td style={{ padding: "6px 8px", fontWeight: 600, color: "var(--text)" }}>{s.name}</td>
                    <td style={{ padding: "6px 8px", color: "var(--accent)", fontWeight: 700 }}>{etfName}</td>
                    <td style={{ padding: "6px 8px", color: chgColor(s.rs_vs_spy_1d), fontWeight: 600, fontSize: 10 }}>
                      {fmtRs(s.rs_vs_spy_1d)}
                    </td>
                    <td style={{ padding: "6px 8px", color: chgColor(s.rs_vs_spy_1w), fontWeight: 600, fontSize: 10 }}>
                      {fmtRs(s.rs_vs_spy_1w)}
                    </td>
                    <td style={{ padding: "6px 8px", color: chgColor(s.rs_vs_spy_1m), fontWeight: 600, fontSize: 10 }}>
                      {fmtRs(s.rs_vs_spy_1m)}
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <span style={{
                        fontSize: 9, padding: "1px 6px", borderRadius: 2,
                        background: s.trend === "leading" ? "rgba(45,122,58,0.15)" :
                                    s.trend === "lagging" ? "rgba(242,54,69,0.1)" : "rgba(0,0,0,0.03)",
                        color: s.trend === "leading" ? "#2d7a3a" :
                               s.trend === "lagging" ? "#c43a2a" : "var(--text3)",
                      }}>
                        {s.trend || "neutral"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sector / Theme RS Heatmap */}
      <div style={{ marginTop: 20 }}>
        <SectorHeatmap />
      </div>

      {/* Sector Rotation — RRG, Line Chart, Multi-timeframe Table */}
      <div style={{ marginTop: 20 }}>
        <SectorRotation />
      </div>
    </div>
  );
}


/* ─── STOCKBEE EP DASHBOARD ──────────────────────────────────────────────── */

const MAGNA_LABELS = {
  M: { name: "Massive Acceleration", tip: "Earnings beat 20%+ OR sales growth 30%+ for 2 consecutive quarters" },
  G: { name: "Guidance", tip: "Company raised forward guidance or analysts raised estimates in last 30 days" },
  N: { name: "Neglect", tip: "Low analyst coverage (<10), not in major news, low social mentions" },
  A_analyst: { name: "Analyst Upgrades", tip: "At least one analyst upgrade or price target raise in last 14 days" },
  "53+": { name: "Technical Position", tip: "Stock trading above 50-day MA AND within 3% of 52-week high" },
  CAP: { name: "Small/Mid Cap", tip: "Market cap under $10 billion" },
  "10x10": { name: "Young Company", tip: "IPO within last 10 years" },
};

const EP_TYPE_STYLES = {
  CLASSIC:       { bg: "rgba(255,152,0,0.12)", color: "#ff9800", border: "rgba(255,152,0,0.4)", label: "CLASSIC EP" },
  DELAYED:       { bg: "rgba(41,98,255,0.12)", color: "#2962ff", border: "rgba(41,98,255,0.4)", label: "DELAYED EP" },
  "9M":          { bg: "rgba(156,39,176,0.12)", color: "#9c27b0", border: "rgba(156,39,176,0.4)", label: "9M EP" },
  STORY:         { bg: "rgba(255,87,34,0.12)", color: "#ff5722", border: "rgba(255,87,34,0.4)", label: "STORY EP" },
  MOM_BURST:     { bg: "rgba(0,150,136,0.12)", color: "#009688", border: "rgba(0,150,136,0.4)", label: "MOM BURST" },
  SHORT_CLASSIC: { bg: "rgba(211,47,47,0.12)", color: "#d32f2f", border: "rgba(211,47,47,0.4)", label: "SHORT EP" },
  SHORT_DELAYED: { bg: "rgba(211,47,47,0.12)", color: "#d32f2f", border: "rgba(211,47,47,0.4)", label: "SHORT DELAYED" },
  SHORT_STORY:   { bg: "rgba(211,47,47,0.12)", color: "#d32f2f", border: "rgba(211,47,47,0.4)", label: "SHORT STORY" },
};

const ENTRY_APPROACH_STYLES = {
  AGGRESSIVE:     { bg: "rgba(255,82,82,0.12)", color: "#ff5252", label: "AGGRESSIVE" },
  STANDARD:       { bg: "rgba(255,152,0,0.12)", color: "#ff9800", label: "STANDARD" },
  CONSERVATIVE:   { bg: "rgba(41,98,255,0.12)", color: "#2962ff", label: "CONSERVATIVE" },
  "VOLUME CONFIRM": { bg: "rgba(156,39,176,0.12)", color: "#9c27b0", label: "VOLUME CONFIRM" },
  "QUICK PROFIT":   { bg: "rgba(255,87,34,0.12)", color: "#ff5722", label: "QUICK PROFIT" },
  "PULLBACK ENTRY": { bg: "rgba(0,150,136,0.12)", color: "#009688", label: "PULLBACK ENTRY" },
  WATCH:            { bg: "var(--bg3)", color: "var(--text3)", label: "WATCH" },
};

function MagnaScoreBadge({ score, size = "normal" }) {
  const color = score >= 5 ? "#2d7a3a" : score >= 3 ? "#b8820a" : "#c43a2a";
  const bg = score >= 5 ? "rgba(45,122,58,0.15)" : score >= 3 ? "rgba(184,130,10,0.12)" : "rgba(196,58,42,0.1)";
  const label = score >= 5 ? "HIGH" : score >= 3 ? "MOD" : "LOW";
  const fontSize = size === "large" ? 16 : 12;
  return (
    <span title={`MAGNA Score: ${score}/7 - ${label} conviction`} style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize, fontWeight: 800, padding: size === "large" ? "4px 10px" : "2px 7px",
      borderRadius: 3, background: bg, color,
      border: `1px solid ${color}55`, letterSpacing: 0.5,
    }}>
      {score}/7
      <span style={{ fontSize: size === "large" ? 9 : 7, fontWeight: 600, opacity: 0.8 }}>{label}</span>
    </span>
  );
}

function MagnaDetails({ details }) {
  if (!details) return null;
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
      gap: 4, padding: "8px 10px", borderRadius: 3,
      background: "var(--bg)", border: "1px solid var(--border)",
    }}>
      {Object.entries(details).map(([key, d]) => {
        const meta = MAGNA_LABELS[key] || { name: key, tip: "" };
        return (
          <div key={key} title={meta.tip} style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "3px 6px", borderRadius: 2,
            background: d.met ? "rgba(45,122,58,0.08)" : "transparent",
          }}>
            <span style={{
              width: 14, height: 14, borderRadius: "50%", display: "flex",
              alignItems: "center", justifyContent: "center",
              fontSize: 8, fontWeight: 800,
              background: d.met ? "#2d7a3a" : "var(--bg3)",
              color: d.met ? "#fff" : "var(--text3)",
            }}>
              {d.met ? "\u2713" : "\u2717"}
            </span>
            <div>
              <div style={{ fontSize: 8, fontWeight: 700, color: d.met ? "#2d7a3a" : "var(--text3)", letterSpacing: 0.5 }}>
                {key.replace("A_analyst", "A")}
              </div>
              <div style={{ fontSize: 7, color: "var(--text3)", lineHeight: 1.3, maxWidth: 120 }}>
                {d.reason}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EPTypeBadge({ type }) {
  const style = EP_TYPE_STYLES[type] || EP_TYPE_STYLES.CLASSIC;
  return (
    <span style={{
      fontSize: 9, fontWeight: 800, padding: "2px 8px", borderRadius: 2,
      background: style.bg, color: style.color,
      border: `1px solid ${style.border}`, letterSpacing: 0.8,
    }}>
      {style.label}
    </span>
  );
}

function EntryTacticCard({ tactic }) {
  if (!tactic) return null;
  const style = ENTRY_APPROACH_STYLES[tactic.entry_approach] || ENTRY_APPROACH_STYLES.WATCH;
  return (
    <div style={{
      padding: "8px 12px", borderRadius: 3,
      background: style.bg, border: `1px solid ${style.color}30`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 800, color: style.color, letterSpacing: 1 }}>
          {style.label}
        </span>
        {tactic.risk_label && (
          <span style={{ fontSize: 8, color: "var(--text3)" }}>{tactic.risk_label}</span>
        )}
      </div>
      <div style={{ fontSize: 9, color: "var(--text2)", marginBottom: 6 }}>
        {tactic.entry_description}
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 10 }}>
        {tactic.entry_price && (
          <span>
            <span style={{ color: "var(--text3)", fontSize: 8 }}>ENTRY </span>
            <span style={{ fontWeight: 700, color: "var(--accent)" }}>${tactic.entry_price?.toFixed(2)}</span>
          </span>
        )}
        {tactic.stop_price && (
          <span>
            <span style={{ color: "var(--text3)", fontSize: 8 }}>STOP </span>
            <span style={{ fontWeight: 700, color: "var(--red)" }}>${tactic.stop_price?.toFixed(2)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

function ShortInterestBadge({ shortData }) {
  if (!shortData || shortData.short_pct_float == null) return null;
  const pct = shortData.short_pct_float;
  const squeeze = shortData.squeeze_potential;
  const col = squeeze ? "#9c27b0" : pct > 10 ? "#ff9800" : "var(--text3)";
  return (
    <span title={`Short interest: ${pct}% of float. Days to cover: ${shortData.days_to_cover || "N/A"}`} style={{
      fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
      background: squeeze ? "rgba(156,39,176,0.1)" : "var(--bg3)",
      color: col, border: `1px solid ${col}33`,
    }}>
      SI {pct}%{squeeze ? " SQUEEZE" : ""}
    </span>
  );
}

function SalesSparkline({ data }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data.map(Math.abs), 1);
  const h = 20;
  const w = data.length * 14;
  return (
    <svg width={w} height={h} style={{ verticalAlign: "middle" }}>
      {data.map((v, i) => {
        const barH = Math.abs(v) / max * (h - 4);
        const y = h - barH - 2;
        const fill = v >= 100 ? "#2d7a3a" : v >= 0 ? "#5a9a3a" : "#c43a2a";
        return <rect key={i} x={i * 14} y={y} width={10} height={barH} rx={1} fill={fill} />;
      })}
    </svg>
  );
}

function BreadthGauge({ breadth }) {
  if (!breadth || breadth.pct_above_50ma == null) return null;
  const pct = breadth.pct_above_50ma;
  const col = breadth.regime_color === "green" ? "#2d7a3a"
            : breadth.regime_color === "red" ? "#c43a2a" : "#b8820a";
  const bg = breadth.regime_color === "green" ? "rgba(45,122,58,0.1)"
           : breadth.regime_color === "red" ? "rgba(196,58,42,0.08)" : "rgba(184,130,10,0.08)";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
      borderRadius: 4, background: bg, border: `1px solid ${col}40`,
    }}>
      <div>
        <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>S&P BREADTH</div>
        <div style={{ fontSize: 20, fontWeight: 800, color: col }}>{pct}%</div>
        <div style={{ fontSize: 8, color: "var(--text3)" }}>above 50MA</div>
      </div>
      <div style={{
        width: 60, height: 8, background: "var(--bg3)", borderRadius: 4, overflow: "hidden",
      }}>
        <div style={{
          width: `${Math.min(100, pct)}%`, height: "100%",
          background: col, borderRadius: 4, transition: "width 0.3s",
        }} />
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 800, color: col }}>{breadth.regime}</div>
        <div style={{ fontSize: 8, color: "var(--text3)", maxWidth: 150 }}>{breadth.trade_guidance}</div>
      </div>
      {breadth.vix_level && (
        <div style={{ marginLeft: "auto" }}>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>VIX</div>
          <div style={{
            fontSize: 14, fontWeight: 700,
            color: breadth.vix_level > 25 ? "#c43a2a" : breadth.vix_level > 18 ? "#b8820a" : "#2d7a3a",
          }}>{breadth.vix_level}</div>
        </div>
      )}
      {breadth.spy_above_50ma != null && (
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>SPY</div>
          <div style={{ fontSize: 10, fontWeight: 700, color: breadth.spy_above_50ma ? "#2d7a3a" : "#c43a2a" }}>
            {breadth.spy_above_50ma ? "Above" : "Below"} 50MA
          </div>
        </div>
      )}
      {breadth.breadth_ad_ratio != null && (
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>A/D</div>
          <div style={{ fontSize: 10, fontWeight: 700, color: breadth.breadth_ad_ratio >= 1 ? "#2d7a3a" : "#c43a2a" }}>
            {breadth.breadth_ad_ratio}
          </div>
        </div>
      )}
    </div>
  );
}

function ConvictionTierBadge({ tier, label, color }) {
  if (!tier && tier !== 0) return null;
  const styles = {
    1: { bg: "rgba(45,122,58,0.12)", color: "#2d7a3a", border: "rgba(45,122,58,0.4)" },
    2: { bg: "rgba(255,109,0,0.12)", color: "#ff6d00", border: "rgba(255,109,0,0.4)" },
    0: { bg: "rgba(100,100,100,0.08)", color: "#888", border: "rgba(100,100,100,0.2)" },
  };
  const st = styles[tier] || styles[0];
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
      background: st.bg, color: st.color, border: `1px solid ${st.border}`,
      letterSpacing: 0.5,
    }}>
      {label || (tier === 1 ? "TIER 1" : tier === 2 ? "TIER 2" : "WATCH")}
    </span>
  );
}

function ExitStrategyCard({ exit, sizing }) {
  if (!exit) return null;
  return (
    <div style={{
      fontSize: 9, padding: "8px 10px", borderRadius: 3, marginTop: 6,
      background: "rgba(41,98,255,0.04)", border: "1px solid rgba(41,98,255,0.15)",
    }}>
      <div style={{ fontWeight: 700, fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 4 }}>
        EXIT STRATEGY (BE{exit.be_trigger_pct}% + TRAIL {exit.trail_pct}%)
      </div>
      <div style={{ color: "var(--text2)", lineHeight: 1.5 }}>
        <span style={{ fontWeight: 600 }}>Stop:</span> ${exit.stop_price} ({exit.stop_dist_pct}% risk)
        {" | "}
        <span style={{ fontWeight: 600 }}>Breakeven at:</span> +{exit.be_trigger_pct}%
        {" | "}
        <span style={{ fontWeight: 600 }}>Trail:</span> {exit.trail_pct}% from highs
      </div>
      {sizing && (
        <div style={{ color: "var(--text3)", marginTop: 3 }}>
          Risk {sizing.risk_pct}% equity per trade at stop
        </div>
      )}
    </div>
  );
}

function EPCard({ s, onQuickAdd }) {
  const isShort = (s.ep_side === "SHORT" || (s.ep_type || "").startsWith("SHORT"));
  const epStyle = EP_TYPE_STYLES[s.ep_type] || EP_TYPE_STYLES.CLASSIC;
  const [expanded, setExpanded] = React.useState(false);
  const intel = s.entry_intel || {};
  const rLevels = intel.r_levels || {};
  const gapPct = s.ep_gap_pct || s.gap_pct || 0;
  const volRatio = s.ep_vol_ratio || s.vol_ratio || 0;

  // Tier colors
  const tierColors = { "MAX BET": "#d4af37", "STRONG": "#ff6d00", "NORMAL": "#2d7a3a" };
  const tierBg = { "MAX BET": "rgba(212,175,55,0.08)", "STRONG": "rgba(255,109,0,0.06)", "NORMAL": "rgba(45,122,58,0.04)" };
  const borderColor = isShort ? "#d32f2f" : (tierColors[s.tier_label] || epStyle.color);

  return (
    <div style={{
      background: isShort ? "rgba(211,47,47,0.03)" : (tierBg[s.tier_label] || "var(--bg2)"),
      borderRadius: 4, padding: "10px 14px", marginBottom: 8,
      border: `1px solid ${borderColor}30`, borderLeft: `4px solid ${borderColor}`,
      cursor: "pointer",
    }} onClick={() => setExpanded(!expanded)}>

      {/* Row 1: Ticker, price, badges */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <TVLink ticker={s.ticker}>
          <span style={{ fontWeight: 700, fontSize: 14, color: isShort ? "#d32f2f" : "var(--accent)" }}>{s.ticker}</span>
        </TVLink>
        {s.name && <span style={{ fontSize: 10, color: "var(--text3)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>}
        <span style={{ fontSize: 12, fontWeight: 600 }}>${s.price?.toFixed(2)}</span>

        {/* EP type badge */}
        <span style={{
          fontSize: 8, fontWeight: 800, padding: "2px 6px", borderRadius: 2,
          background: epStyle.bg, color: epStyle.color, border: `1px solid ${epStyle.border}`,
          letterSpacing: 0.5,
        }}>{epStyle.label}</span>

        {/* Kelly tier badge (long only) */}
        {!isShort && s.tier_label && s.tier_label !== "WATCHLIST" && (
          <span style={{
            fontSize: 8, fontWeight: 800, padding: "2px 8px", borderRadius: 2,
            background: `${tierColors[s.tier_label] || "#666"}18`,
            color: tierColors[s.tier_label] || "#666",
            border: `1px solid ${tierColors[s.tier_label] || "#666"}40`,
          }}>
            {s.tier_label} {s.tier_sizing}
          </span>
        )}

        {/* Short MAGNA (short only) */}
        {isShort && s.short_magna_score != null && (
          <span style={{
            fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
            background: s.short_magna_score >= 4 ? "rgba(211,47,47,0.12)" : "var(--bg3)",
            color: s.short_magna_score >= 4 ? "#d32f2f" : "var(--text3)",
          }}>MAGNA {s.short_magna_score}/6</span>
        )}

        {/* Micro-cap */}
        {s.is_micro && (
          <span style={{ fontSize: 7, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
            background: "rgba(156,39,176,0.08)", color: "#9c27b0" }}>MICRO</span>
        )}

        {/* Entry quality */}
        {intel.entry_quality && intel.entry_quality !== "POOR" && (
          <span style={{
            fontSize: 7, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
            background: intel.entry_quality === "EXCELLENT" ? "rgba(45,122,58,0.12)"
              : intel.entry_quality === "GOOD" ? "rgba(255,152,0,0.1)" : "var(--bg3)",
            color: intel.entry_quality === "EXCELLENT" ? "#2d7a3a"
              : intel.entry_quality === "GOOD" ? "#ff9800" : "var(--text3)",
          }}>{intel.entry_quality}</span>
        )}

        {onQuickAdd && (
          <button onClick={(e) => { e.stopPropagation(); onQuickAdd(s); }} style={{
            marginLeft: "auto", fontSize: 8, padding: "2px 8px",
            background: "var(--bg3)", border: "1px solid var(--border)",
            color: "var(--text2)", borderRadius: 2, cursor: "pointer", fontFamily: "inherit",
          }}>+ Journal</button>
        )}
      </div>

      {/* Row 2: Key metrics inline */}
      <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10, color: "var(--text2)", flexWrap: "wrap" }}>
        <span>Gap <b style={{ color: gapPct >= 0 ? "var(--green)" : "var(--red)" }}>{gapPct > 0 ? "+" : ""}{gapPct}%</b></span>
        <span>Vol <b>{volRatio}x</b></span>
        {!isShort && <span>MAGNA <b>{s.magna_score || 0}</b>/7</span>}
        {s.ti65_label && s.ti65_label !== "N/A" && <span>TI65 <b>{s.ti65_label}</b></span>}
        {s.tt_score > 0 && <span>TT <b>{s.tt_score}</b>/7</span>}
        {isShort && s.ep_catalyst_label && (
          <span style={{ color: "#d32f2f" }}>{s.ep_catalyst_label}</span>
        )}
      </div>

      {/* Row 3: Entry zone + stop + R1 */}
      {intel.entry_zone_low && (
        <div style={{ display: "flex", gap: 14, marginTop: 5, fontSize: 10, flexWrap: "wrap" }}>
          <span>
            <span style={{ color: "var(--text3)", fontSize: 8 }}>ENTRY </span>
            <b>${intel.entry_zone_low}-${intel.entry_zone_high}</b>
          </span>
          {intel.stop_price && (
            <span>
              <span style={{ color: "var(--text3)", fontSize: 8 }}>STOP </span>
              <b style={{ color: "var(--red)" }}>${intel.stop_price}</b>
            </span>
          )}
          {rLevels.r1 && (
            <span>
              <span style={{ color: "var(--text3)", fontSize: 8 }}>T1 </span>
              <b style={{ color: "var(--green)" }}>${rLevels.r1}</b>
            </span>
          )}
          {intel.risk_reward && (
            <span>
              <span style={{ color: "var(--text3)", fontSize: 8 }}>R:R </span>
              <b>{intel.risk_reward}:1</b>
            </span>
          )}
        </div>
      )}

      {/* Expanded: full details */}
      {expanded && (
        <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
          {/* EP type details */}
          <div style={{ fontSize: 9, color: "var(--text3)", marginBottom: 8 }}>{s.ep_type_details}</div>

          {/* Tier reason */}
          {s.tier_description && (
            <div style={{ fontSize: 9, color: tierColors[s.tier_label] || "var(--text3)", marginBottom: 8, fontWeight: 600 }}>
              {s.tier_description}
            </div>
          )}

          {/* Price levels grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 6, marginBottom: 8 }}>
            {intel.gap_fill_level && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>GAP FILL</div>
                <div style={{ fontWeight: 700 }}>${intel.gap_fill_level}</div>
              </div>
            )}
            {intel.ema10 && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>EMA10</div>
                <div style={{ fontWeight: 700 }}>${intel.ema10}</div>
              </div>
            )}
            {intel.ema20 && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>EMA20</div>
                <div style={{ fontWeight: 700 }}>${intel.ema20}</div>
              </div>
            )}
            {intel.atr && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>ATR(14)</div>
                <div style={{ fontWeight: 700 }}>${intel.atr}</div>
              </div>
            )}
            {rLevels.r2 && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>T2 (2R)</div>
                <div style={{ fontWeight: 700, color: "var(--green)" }}>${rLevels.r2}</div>
              </div>
            )}
            {rLevels.r3 && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>T3 (3R)</div>
                <div style={{ fontWeight: 700, color: "var(--green)" }}>${rLevels.r3}</div>
              </div>
            )}
            {intel.risk_dollars && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>RISK/SHARE</div>
                <div style={{ fontWeight: 700, color: "var(--red)" }}>${intel.risk_dollars}</div>
              </div>
            )}
            {isShort && intel.bounce_resistance && (
              <div style={{ fontSize: 9, padding: "4px 8px", background: "var(--bg3)", borderRadius: 2 }}>
                <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 1 }}>BOUNCE HIGH</div>
                <div style={{ fontWeight: 700 }}>${intel.bounce_resistance}</div>
              </div>
            )}
          </div>

          {/* Entry notes */}
          {intel.entry_notes && intel.entry_notes.length > 0 && (
            <div style={{ fontSize: 8, color: "var(--text3)" }}>
              {intel.entry_notes.map((n, i) => (
                <div key={i} style={{ marginBottom: 2, color: n.startsWith("WARNING") || n.startsWith("CAUTION") ? "var(--red)" : "var(--text3)" }}>
                  {n}
                </div>
              ))}
            </div>
          )}

          {/* Sector theme */}
          {s.sector_theme_score >= 2 && (
            <div style={{ fontSize: 9, color: "#ff6d00", fontWeight: 600, marginTop: 6 }}>
              🔥 {s.sector} theme — {s.sector_theme_score} peer EPs
            </div>
          )}
          {s.sector && s.sector_theme_score < 2 && (
            <div style={{ fontSize: 8, color: "var(--text3)", marginTop: 4 }}>Sector: {s.sector}</div>
          )}

          {/* Earnings countdown */}
          {s.days_until_earnings != null && s.days_until_earnings > 0 && (
            <div style={{
              fontSize: 9, marginTop: 4, fontWeight: 600,
              color: s.days_until_earnings <= 7 ? "var(--red)" : s.days_until_earnings <= 42 ? "#ff9800" : "var(--text3)",
            }}>
              {s.days_until_earnings <= 7 ? "⚠️" : "📅"} Earnings in {s.days_until_earnings} days ({s.earnings_date})
            </div>
          )}

          {/* Pyramid plan */}
          {s.pyramid_plan && s.pyramid_plan.has_plan && (
            <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--bg)", borderRadius: 3, border: "1px solid var(--border)" }}>
              <div style={{ fontSize: 8, fontWeight: 700, color: "var(--text3)", letterSpacing: 1, marginBottom: 4 }}>PYRAMID PLAN ({s.pyramid_plan.half_kelly_pct}% Kelly)</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: 9 }}>
                <div>
                  <div style={{ fontSize: 7, color: "var(--text3)" }}>INITIAL</div>
                  <div style={{ fontWeight: 700 }}>{s.pyramid_plan.initial?.shares} sh @ ${s.pyramid_plan.initial?.price}</div>
                </div>
                {s.pyramid_plan.add1?.price && (
                  <div>
                    <div style={{ fontSize: 7, color: "var(--text3)" }}>ADD @ T1</div>
                    <div style={{ fontWeight: 700 }}>{s.pyramid_plan.add1.shares} sh @ ${s.pyramid_plan.add1.price}</div>
                  </div>
                )}
                {s.pyramid_plan.add2?.price && (
                  <div>
                    <div style={{ fontSize: 7, color: "var(--text3)" }}>ADD @ T2</div>
                    <div style={{ fontWeight: 700 }}>{s.pyramid_plan.add2.shares} sh @ ${s.pyramid_plan.add2.price}</div>
                  </div>
                )}
              </div>
              <div style={{ fontSize: 8, color: "var(--text3)", marginTop: 4 }}>
                Full: {s.pyramid_plan.full_position?.total_shares} shares · ${s.pyramid_plan.full_position?.total_dollar} · {s.pyramid_plan.full_position?.pct_equity}% equity
              </div>
            </div>
          )}

          {/* Short MAGNA details */}
          {isShort && s.short_magna_details && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 4, fontWeight: 600 }}>SHORT MAGNA CRITERIA</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(s.short_magna_details).map(([k, v]) => (
                  <span key={k} style={{
                    fontSize: 8, padding: "2px 6px", borderRadius: 2,
                    background: v.met ? "rgba(211,47,47,0.08)" : "var(--bg3)",
                    color: v.met ? "#d32f2f" : "var(--text3)",
                    border: `1px solid ${v.met ? "rgba(211,47,47,0.3)" : "var(--border)"}`,
                  }}>
                    {v.met ? "+" : "-"} {v.label}: {v.reason}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StockbeeEPDashboard({ onQuickAdd }) {
  const [epData, setEpData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [view, setView] = React.useState("actionable");

  const API = process.env.REACT_APP_API_URL || "";

  const fetchData = React.useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/ep-dashboard`)
      .then(r => r.json())
      .then(d => { setEpData(d); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [API]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  const triggerScan = () => {
    fetch(`${API}/api/ep-dashboard/scan`, { method: "POST" })
      .then(r => r.json())
      .then(() => { setTimeout(fetchData, 5000); })
      .catch(e => setError(e.message));
  };

  if (loading && !epData) return (
    <div style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>Loading EP Scanner...</div>
  );
  if (error && !epData) return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <div style={{ color: "#c43a2a", fontSize: 11, marginBottom: 8 }}>Error: {error}</div>
      <button onClick={fetchData} style={{ fontSize: 10, padding: "4px 12px", cursor: "pointer" }}>Retry</button>
    </div>
  );

  const data = epData || {};
  const summary = data.summary || {};
  const breadth = data.sp500_breadth || {};
  const bearRegime = data.bear_regime || false;
  const actionable = data.actionable_eps || [];
  const overflow = data.actionable_overflow || [];
  const shortEps = data.all_short_eps || [];
  const watchlistEps = data.watchlist_eps || [];
  const displayEps = data.display_eps || [...actionable, ...shortEps];

  return (
    <div>
      {/* Market regime bar */}
      <BreadthGauge breadth={breadth} />

      {/* Bear regime warning */}
      {bearRegime && (
        <div style={{
          marginTop: 8, padding: "8px 14px", borderRadius: 3, fontSize: 10, fontWeight: 600,
          background: "rgba(211,47,47,0.08)", border: "1px solid rgba(211,47,47,0.3)", color: "#d32f2f",
        }}>
          BEAR REGIME — S&amp;P breadth below 40%. Short EPs promoted. Only A+ long setups.
        </div>
      )}

      {/* Summary chips + actions */}
      <div style={{ display: "flex", gap: 6, marginTop: 10, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        {/* Tier counts */}
        {summary.tier1_max > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, padding: "4px 10px", borderRadius: 3,
            background: "rgba(212,175,55,0.1)", color: "#d4af37", border: "1px solid rgba(212,175,55,0.3)" }}>
            {summary.tier1_max} MAX
          </span>
        )}
        {summary.tier2_strong > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, padding: "4px 10px", borderRadius: 3,
            background: "rgba(255,109,0,0.08)", color: "#ff6d00", border: "1px solid rgba(255,109,0,0.3)" }}>
            {summary.tier2_strong} STRONG
          </span>
        )}
        {summary.tier3_normal > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, padding: "4px 10px", borderRadius: 3,
            background: "rgba(45,122,58,0.06)", color: "#2d7a3a", border: "1px solid rgba(45,122,58,0.2)" }}>
            {summary.tier3_normal} NORMAL
          </span>
        )}
        {summary.total_short_eps > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, padding: "4px 10px", borderRadius: 3,
            background: "rgba(211,47,47,0.08)", color: "#d32f2f", border: "1px solid rgba(211,47,47,0.3)" }}>
            {summary.total_short_eps} SHORT
          </span>
        )}
        <span style={{ fontSize: 9, padding: "4px 10px", borderRadius: 3,
          background: "var(--bg2)", border: "1px solid var(--border)", color: "var(--text3)" }}>
          {summary.watchlist_only || 0} watchlist
        </span>

        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button onClick={triggerScan} style={{
            fontSize: 9, padding: "3px 10px", cursor: "pointer",
            background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text2)", borderRadius: 2,
          }}>Run Scan</button>
          <button onClick={fetchData} style={{
            fontSize: 9, padding: "3px 10px", cursor: "pointer",
            background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text2)", borderRadius: 2,
          }}>Refresh</button>
        </div>
      </div>

      {/* Hot sectors banner */}
      {(summary.hot_sectors || []).length > 0 && (
        <div style={{
          marginBottom: 10, padding: "6px 12px", borderRadius: 3, fontSize: 10,
          background: "rgba(255,109,0,0.06)", border: "1px solid rgba(255,109,0,0.2)", color: "#ff6d00",
          display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
        }}>
          <span style={{ fontWeight: 700 }}>🔥 HOT:</span>
          {(summary.hot_sectors || []).map(s => <span key={s} style={{ fontWeight: 600 }}>{s}</span>)}
        </div>
      )}

      {/* VCP formations banner */}
      {(data.vcp_formations || []).length > 0 && (
        <div style={{
          marginBottom: 10, padding: "6px 12px", borderRadius: 3, fontSize: 10,
          background: "rgba(41,98,255,0.06)", border: "1px solid rgba(41,98,255,0.2)", color: "#2962ff",
          display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
        }}>
          <span style={{ fontWeight: 700 }}>📐 VCP forming:</span>
          {(data.vcp_formations || []).map(v => (
            <span key={v.ticker} style={{ fontWeight: 600 }}>
              {v.ticker} ({v.contractions} contractions, pivot ${v.pivot_price})
            </span>
          ))}
        </div>
      )}

      {/* View tabs — simple */}
      <div style={{ display: "flex", gap: 2, marginBottom: 12 }}>
        {[
          { key: "actionable", label: `Actionable (${displayEps.length})` },
          { key: "shorts", label: `Shorts (${shortEps.length})` },
          { key: "watchlist", label: `Watchlist (${watchlistEps.length})` },
          { key: "all", label: `All (${(data.all_eps || []).length})` },
        ].map(t => (
          <button key={t.key} onClick={() => setView(t.key)} style={{
            fontSize: 9, padding: "5px 14px", cursor: "pointer",
            background: view === t.key ? "var(--accent)" : "var(--bg3)",
            color: view === t.key ? "#fff" : "var(--text2)",
            border: `1px solid ${view === t.key ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 2, fontWeight: view === t.key ? 700 : 400,
          }}>{t.label}</button>
        ))}
      </div>

      {/* Actionable view — the default */}
      {view === "actionable" && (
        <div>
          {displayEps.length === 0 ? (
            <div style={{
              padding: "20px 14px", borderRadius: 3, fontSize: 10,
              background: "var(--bg2)", border: "1px solid var(--border)", color: "var(--text3)",
              textAlign: "center",
            }}>
              No actionable setups today. Kelly tiers (MAX/STRONG/NORMAL) trigger ~2-3x/month. This is normal.
              {data.status === "no_data" && " Run a scan to populate."}
            </div>
          ) : (
            <>
              {/* Long actionable */}
              {actionable.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "#2d7a3a", letterSpacing: 1, marginBottom: 6,
                    paddingBottom: 4, borderBottom: "1px solid rgba(45,122,58,0.2)" }}>
                    LONG ({actionable.length})
                  </div>
                  {actionable.map(s => <EPCard key={s.ticker + "L"} s={s} onQuickAdd={onQuickAdd} />)}
                </div>
              )}

              {/* Overflow (extra tier 1-3 beyond max positions) */}
              {overflow.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 9, fontWeight: 600, color: "var(--text3)", letterSpacing: 1, marginBottom: 6,
                    paddingBottom: 4, borderBottom: "1px solid var(--border)" }}>
                    OVERFLOW ({overflow.length}) — beyond max 3 positions
                  </div>
                  {overflow.map(s => <EPCard key={s.ticker + "O"} s={s} onQuickAdd={onQuickAdd} />)}
                </div>
              )}

              {/* Short EPs */}
              {shortEps.length > 0 && (
                <div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "#d32f2f", letterSpacing: 1, marginBottom: 6,
                    paddingBottom: 4, borderBottom: "1px solid rgba(211,47,47,0.2)" }}>
                    SHORT ({shortEps.length})
                  </div>
                  {shortEps.map(s => <EPCard key={s.ticker + "S"} s={s} onQuickAdd={onQuickAdd} />)}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Shorts only */}
      {view === "shorts" && (
        <div>
          {shortEps.length === 0 ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
              No short EPs detected. Requires gap down 20%+ on 3x volume.
            </div>
          ) : (
            shortEps.map(s => <EPCard key={s.ticker} s={s} onQuickAdd={onQuickAdd} />)
          )}
        </div>
      )}

      {/* Watchlist */}
      {view === "watchlist" && (
        <div>
          {watchlistEps.length === 0 ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
              No watchlist EPs. All detected setups met Kelly tier criteria.
            </div>
          ) : (
            watchlistEps.slice(0, 25).map(s => <EPCard key={s.ticker} s={s} onQuickAdd={onQuickAdd} />)
          )}
          {watchlistEps.length > 25 && (
            <div style={{ fontSize: 9, color: "var(--text3)", textAlign: "center", padding: 8 }}>
              +{watchlistEps.length - 25} more watchlist setups not shown
            </div>
          )}
        </div>
      )}

      {/* All */}
      {view === "all" && (
        <div>
          {(data.all_eps || []).length === 0 ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
              No EP setups detected.{data.status === "no_data" && " Run a scan."}
            </div>
          ) : (
            (data.all_eps || []).slice(0, 50).map(s => <EPCard key={s.ticker} s={s} onQuickAdd={onQuickAdd} />)
          )}
        </div>
      )}
    </div>
  );
}


/* ─── ERROR BOUNDARY ─────────────────────────────────────────────────────── */
export class AppErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(e) { return { hasError: true, error: e }; }
  componentDidCatch(e, info) { console.error("[AppErrorBoundary]", e, info); }
  render() {
    if (this.state.hasError) return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", height: "100vh", background: "var(--bg)",
        fontFamily: "Inter, sans-serif", gap: 12, color: "var(--text)" }}>
        <div style={{ fontSize: 22 }}>💥</div>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--red)" }}>Something crashed</div>
        <div style={{ fontSize: 10, color: "var(--text3)", maxWidth: 360, textAlign: "center" }}>
          {this.state.error?.message || "Unknown error"}
        </div>
        <button onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
          style={{ marginTop: 8, padding: "7px 20px", background: "var(--bg2)",
            border: "1px solid var(--border)", color: "var(--text)",
            cursor: "pointer", fontFamily: "Inter, sans-serif", fontSize: 11, borderRadius: 4 }}>
          ↻ Reload
        </button>
      </div>
    );
    return this.props.children;
  }
}

/* ─── ROOT APP ────────────────────────────────────────────────────────────── */

export default function App({ onQuickAdd }) {
  const [data,        setData]        = useState(null);
  const [tab,         setTab]         = useState("Longs");
  const [lastRefresh, setLastRefresh] = useState(null);
  const [error,       setError]       = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [noScanYet,   setNoScanYet]   = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const controller = new AbortController();
      const tid = setTimeout(() => controller.abort(), 30000);
      let res;
      try {
        res = await fetch(API_BASE + "/api/scan", { signal: controller.signal });
      } finally {
        clearTimeout(tid);
      }
      if (!res.ok) throw new Error("API " + res.status);
      const raw = await res.json();

      if (raw._empty) {
        setNoScanYet(true);
        setData(null);
        return;
      }

      setNoScanYet(false);
      const result = await fetchDashboardData(raw);
      setData(result);
      setLastRefresh(new Date().toLocaleTimeString("en-GB"));
    } catch (e) {
      console.error("[refresh]", e);
      if (e.name === "AbortError") {
        // Timeout — backend scan probably still running
        setNoScanYet(true);
        setData(null);
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [refresh]);

  // No-scan-yet state
  if (noScanYet) return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
      height:"100vh", background:"var(--bg)", color:"var(--text)", fontFamily:"Inter,sans-serif", gap:12 }}>
      <div style={{ fontSize:22 }}>⏳</div>
      <div style={{ fontSize:14, fontWeight:700 }}>No scan data yet</div>
      <div style={{ fontSize:11, color:"var(--text3)", textAlign:"center", maxWidth:320 }}>
        Scans run at <b>07:00</b> and <b>21:00 UK</b>.<br/>Trigger one manually from the header, or wait.
      </div>
      <button onClick={refresh} style={{ marginTop:8, padding:"7px 20px", background:"var(--accent)",
        border:"none", color:"#fff", cursor:"pointer", fontFamily:"Inter,sans-serif",
        fontSize:11, borderRadius:4, fontWeight:700 }}>↻ Check again</button>
    </div>
  );

  // Error state
  if (error && !data) return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
      height:"100vh", background:"var(--bg)", color:"var(--text)", fontFamily:"Inter,sans-serif", gap:10 }}>
      <div style={{ fontSize:22 }}>⚠</div>
      <div style={{ fontSize:13, fontWeight:700, color:"var(--red)" }}>Connection Error</div>
      <div style={{ fontSize:10, color:"var(--text3)", maxWidth:300, textAlign:"center" }}>{error}</div>
      <button onClick={refresh} style={{ marginTop:8, padding:"7px 20px", background:"var(--bg2)",
        border:"1px solid var(--border)", color:"var(--text)", cursor:"pointer",
        fontFamily:"Inter,sans-serif", fontSize:11, borderRadius:4 }}>↻ Retry</button>
    </div>
  );

  // Initial loading
  if (!data) return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
      height:"100vh", background:"var(--bg)", color:"var(--accent)", fontFamily:"Inter,sans-serif", gap:8 }}>
      <div style={{ fontSize:13, fontWeight:600 }}>Loading signals...</div>
      <div style={{ fontSize:10, color:"var(--text3)" }}>Fetching from backend...</div>
    </div>
  );
  const tabs = ["Market", "EP Dash", "Bots"];
  // Hidden tabs (code preserved): "Focus", "Weekly", "Longs", "EP", "Shorts", "All Stocks", "Pipeline", "Replay", "Correlation", "Watchlist"

  return (
    <>
      <style>{CSS}</style>
      <div className="dash">

        {/* Header */}
        <div className="hdr">
          <div className="hdr-left">
            <span className="hdr-logo">SIGNAL DESK</span>
            <div>
              <div className="hdr-sub">EPISODIC PIVOT SCANNER</div>
            </div>
          </div>
          <div className="hdr-meta">
            <span className="live-dot" />
            <span className="hdr-time">
              {data.scannedAt ? "Scan: " + data.scannedAt.split(" ")[0] : ""} · Refreshed {lastRefresh}
            </span>
            {data.totalScanned && (
              <span style={{ fontSize: 9, color: "var(--text3)", background: "var(--bg3)", border: "1px solid var(--border)", padding: "2px 8px", borderRadius: 2 }}>
                {data.totalScanned} stocks scanned
              </span>
            )}
            <button onClick={refresh} style={{
              padding: "3px 10px", cursor: "pointer", fontSize: 9,
              background: "var(--bg3)", border: "1px solid var(--border)",
              color: "var(--text2)", borderRadius: 2, letterSpacing: 1,
            }}>↻ REFRESH</button>
          </div>
        </div>

        {/* Market bar */}
        <div className="market-bar">
          <MarketBadge {...data.market} />
          <IndexChip name="NASDAQ" chg={data.nasdaq.chg} above21ema={data.nasdaq.above21ema} />
          <IndexChip name="S&P 500" chg={data.sp500.chg} above21ema={data.sp500.above21ema} />
          <div className="mkt-chip">
            <span className="mkt-chip-label">EP SETUPS</span>
            <span style={{ color: "#ff9800", fontWeight: 700 }}>
              {(data.epSignals || []).filter(s => s.ep_entry_ok).length}
              <span style={{ color: "var(--text3)", fontWeight: 400, fontSize: 8 }}>
                /{(data.epSignals || []).length}
              </span>
            </span>
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {tabs.map(t => (
            <div
              key={t}
              className={`tab ${t === tab ? "active" : ""} ${t === "Shorts" ? "tab-short" : ""}`}
              onClick={() => setTab(t)}
            >
              {t === "Shorts" ? "▼ " : t === "Longs" ? "▲ " : t === "Market" ? "◈ " : t === "Focus" ? "🎯 " : t === "Weekly" ? "📅 " : t === "EP" ? "⚡ " : t === "EP Dash" ? "🔥 " : t === "Replay" ? "⏪ " : t === "Pipeline" ? "◎ " : t === "Correlation" ? "📊 " : t === "Watchlist" ? "📋 " : t === "Bots" ? "⚙ " : ""}{t}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="body">
          {tab === "Market" && <MarketTab data={data} />}
          {tab === "Focus" && <FocusTab data={data} onQuickAdd={onQuickAdd} />}
          {tab === "Weekly" && <WeeklyTab onQuickAdd={onQuickAdd} />}
          {tab === "Longs" && <LongsTab data={data} onQuickAdd={onQuickAdd} />}
          {tab === "EP" && <EPTab data={data} onQuickAdd={onQuickAdd} />}
          {tab === "EP Dash" && <StockbeeEPDashboard onQuickAdd={onQuickAdd} />}
          {tab === "Shorts" && <ShortsTab data={data} />}
          {tab === "All Stocks" && <AllStocksTab data={data} />}
          {tab === "Pipeline" && <Pipeline />}
          {tab === "Replay" && <Replay />}
          {tab === "Correlation" && <Correlation />}
          {tab === "Watchlist" && <WatchlistTab />}
          {tab === "Bots" && <BotDashboard />}
        </div>

      </div>
    </>
  );
}
