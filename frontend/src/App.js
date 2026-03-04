import RegimeGate from './components/RegimeGate';
import Pipeline from './components/Pipeline';
import Replay from './components/Replay';
import Correlation from './components/Correlation';
import WatchlistTab from './components/WatchlistTab';
import SectorHeatmap from './components/SectorHeatmap';
import SectorRotation from './components/SectorRotation';
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

/* ─── INLINE SIGNAL CHART ────────────────────────────────────────────────── */
function SignalChart({ s }) {
  const [open, setOpen] = useState(false);

  const data = s.chart_data || s.chartData;
  if (!data || data.length === 0) return null;

  // ── Layout constants
  const W = 420, H = 200;
  const PAD = { top: 8, right: 8, bottom: 28, left: 44 };
  const VOL_H = 36;                          // height of volume sub-panel
  const PRICE_H = H - PAD.top - PAD.bottom - VOL_H - 4;
  const innerW  = W - PAD.left - PAD.right;

  // ── Price scale
  const highs  = data.map(d => d.h);
  const lows   = data.map(d => d.l);
  const pMin   = Math.min(...lows)   * 0.998;
  const pMax   = Math.max(...highs)  * 1.002;
  const py = v => PAD.top + PRICE_H - ((v - pMin) / (pMax - pMin)) * PRICE_H;

  // ── Volume scale
  const vMax = Math.max(...data.map(d => d.v));
  const vy = v => VOL_H - (v / vMax) * VOL_H;   // bar height, drawn from bottom

  // ── X scale
  const n  = data.length;
  const bw = innerW / n;                        // bar slot width
  const cx = i => PAD.left + (i + 0.5) * bw;   // candle centre x

  // ── Y-axis labels (4 price levels)
  const yTicks = [0, 0.33, 0.66, 1].map(t => pMin + t * (pMax - pMin));

  // ── X-axis labels (show ~5 dates, evenly spaced)
  const xStep = Math.max(1, Math.floor(n / 5));
  const xLabels = data
    .map((d, i) => ({ i, label: d.d.slice(5) }))  // MM-DD
    .filter((_, i) => i % xStep === 0);

  // ── Key levels for reference lines
  const levels = [
    s.ma200  && { y: py(s.ma200),  color: "rgba(120,123,134,0.5)", dash: "4,3", label: "200" },
    s.pivot_line && s.ll_hl_detected && { y: py(s.pivot_line), color: "rgba(45,180,60,0.6)",  dash: "3,2", label: "PVT" },
    s.box_top    && s.darvas_detected && { y: py(s.box_top),   color: "rgba(124,77,255,0.6)", dash: "3,2", label: "BOX" },
  ].filter(Boolean).filter(l => l.y >= PAD.top && l.y <= PAD.top + PRICE_H);

  const volY = PAD.top + PRICE_H + 4;   // top of volume panel

  return (
    <div style={{ marginBottom: 8 }}>
      {/* Toggle button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", padding: "4px 0", cursor: "pointer",
          background: "var(--bg2)", border: "1px solid var(--border)",
          borderRadius: 2, color: "var(--text3)", fontSize: 9,
          letterSpacing: 1, fontFamily: "inherit",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
        }}
      >
        <span style={{ fontSize: 10 }}>{open ? "▲" : "▼"}</span>
        {open ? "HIDE CHART" : "SHOW CHART  ·  60D"}
      </button>

      {open && (
        <div style={{
          marginTop: 4, borderRadius: 3, overflow: "hidden",
          border: "1px solid var(--border)", background: "var(--bg2)",
        }}>
          <svg
            width="100%" viewBox={`0 0 ${W} ${H}`}
            style={{ display: "block", fontFamily: "inherit" }}
          >
            {/* ── Background */}
            <rect width={W} height={H} fill="var(--bg2)" />

            {/* ── Grid lines */}
            {yTicks.map((v, i) => (
              <line key={i}
                x1={PAD.left} x2={W - PAD.right}
                y1={py(v)} y2={py(v)}
                stroke="rgba(0,0,0,0.06)" strokeWidth="1"
              />
            ))}

            {/* ── Y-axis price labels */}
            {yTicks.map((v, i) => (
              <text key={i}
                x={PAD.left - 4} y={py(v) + 3.5}
                textAnchor="end" fontSize="8" fill="var(--text3)"
              >
                {v >= 1000 ? v.toFixed(0) : v.toFixed(2)}
              </text>
            ))}

            {/* ── X-axis date labels */}
            {xLabels.map(({ i, label }) => (
              <text key={i}
                x={cx(i)} y={H - PAD.bottom + 12}
                textAnchor="middle" fontSize="7.5" fill="var(--text3)"
              >
                {label}
              </text>
            ))}

            {/* ── Key level reference lines */}
            {levels.map((lv, i) => (
              <g key={i}>
                <line
                  x1={PAD.left} x2={W - PAD.right}
                  y1={lv.y} y2={lv.y}
                  stroke={lv.color} strokeWidth="1" strokeDasharray={lv.dash}
                />
                <text x={W - PAD.right + 2} y={lv.y + 3.5}
                  fontSize="7" fill={lv.color} textAnchor="start"
                >{lv.label}</text>
              </g>
            ))}

            {/* ── EMA lines */}
            {[
              { key: "e5", color: "rgba(245,166,35,0.8)",   label: "EMA50" },
              { key: "e2", color: "rgba(124,77,255,0.75)",  label: "EMA21" },
              { key: "e1", color: "rgba(41,98,255,0.8)",    label: "EMA10" },
            ].map(({ key, color }) => {
              const pts = data
                .map((d, i) => `${cx(i)},${py(d[key])}`)
                .join(" ");
              return (
                <polyline key={key}
                  points={pts} fill="none"
                  stroke={color} strokeWidth="1.2"
                />
              );
            })}

            {/* ── Candlesticks */}
            {data.map((d, i) => {
              const bull = d.c >= d.o;
              const bodyColor  = bull ? "#2d7a3a" : "#c43a2a";
              const wickColor  = bull ? "#3a9a4a" : "#d44a3a";
              const bodyTop    = py(Math.max(d.o, d.c));
              const bodyBot    = py(Math.min(d.o, d.c));
              const bodyH      = Math.max(1, bodyBot - bodyTop);
              const candleW    = Math.max(1, bw * 0.65);
              const x          = cx(i);

              return (
                <g key={i}>
                  {/* Wick */}
                  <line
                    x1={x} x2={x}
                    y1={py(d.h)} y2={py(d.l)}
                    stroke={wickColor} strokeWidth="0.8"
                  />
                  {/* Body */}
                  <rect
                    x={x - candleW / 2} y={bodyTop}
                    width={candleW} height={bodyH}
                    fill={bodyColor}
                    opacity={bull ? 0.85 : 0.9}
                  />
                </g>
              );
            })}

            {/* ── Volume bars */}
            {data.map((d, i) => {
              const bull    = d.c >= d.o;
              const barH    = (d.v / vMax) * VOL_H;
              const barW    = Math.max(1, bw * 0.65);
              return (
                <rect key={i}
                  x={cx(i) - barW / 2}
                  y={volY + VOL_H - barH}
                  width={barW} height={barH}
                  fill={bull ? "rgba(45,122,58,0.45)" : "rgba(196,58,42,0.35)"}
                />
              );
            })}

            {/* ── Volume panel separator */}
            <line
              x1={PAD.left} x2={W - PAD.right}
              y1={volY} y2={volY}
              stroke="rgba(0,0,0,0.08)" strokeWidth="1"
            />

            {/* ── Legend: EMA colours */}
            {[
              { color: "rgba(41,98,255,0.9)",   label: "EMA10" },
              { color: "rgba(124,77,255,0.9)",  label: "EMA21" },
              { color: "rgba(245,166,35,0.9)",  label: "EMA50" },
            ].map(({ color, label }, i) => (
              <g key={i} transform={`translate(${PAD.left + i * 56}, ${PAD.top})`}>
                <line x1="0" x2="10" y1="4" y2="4" stroke={color} strokeWidth="1.5" />
                <text x="13" y="7" fontSize="7.5" fill="var(--text3)">{label}</text>
              </g>
            ))}
          </svg>
        </div>
      )}
    </div>
  );
}

function BounceSection({ title, color, stocks, maKey, onQuickAdd }) {
  if (!stocks.length) return (
    <div className="section">
      <div className="section-hdr">
        <span className="section-title" style={{ color }}>{title}</span>
        <span className="section-count">0 signals</span>
      </div>
      <div className="empty">No {title} bounce signals today</div>
    </div>
  );

  return (
    <div className="section">
      <div className="section-hdr">
        <span className="section-title" style={{ color }}>{title} Bounce</span>
        <span className="section-count">{stocks.length} signals</span>
        {(() => {
          const themed = stocks.filter(s => s.theme);
          const themeGroups = {};
          themed.forEach(s => { themeGroups[s.theme] = (themeGroups[s.theme] || 0) + 1; });
          const top = Object.entries(themeGroups).sort((a,b) => b[1]-a[1]).slice(0,3);
          if (!top.length) return null;
          return (
            <span style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
              {top.map(([theme, cnt]) => {
                const st = THEME_STYLES[theme];
                if (!st) return null;
                return (
                  <span key={theme} style={{
                    fontSize: 8, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
                    background: st.bg, color: st.color, border: `1px solid ${st.border}`,
                  }}>
                    {st.label} {cnt > 1 ? `×${cnt}` : ""}
                  </span>
                );
              })}
            </span>
          );
        })()}
        <div className="ma-legend">
          <span style={{ fontSize: 9, color: "var(--text3)" }}>vol &gt; 1.2x avg · price ABOVE MA, within threshold</span>
        </div>
      </div>
      <div className="bounce-grid">
        {stocks.map(s => (
          <div className="bounce-card" key={s.ticker} style={{ borderLeftColor: color, borderLeftWidth: 2 }}>
            <div className="bounce-card-top">
              <span className="bounce-card-ticker"><TVLink ticker={s.ticker}>{s.ticker} ↗</TVLink></span>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <MABadge ma={maKey} />
                {s.ma21BelowMA && maKey === "MA21" && (
                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 2, background: "rgba(255,214,0,0.12)", color: "var(--yellow)", border: "1px solid rgba(255,214,0,0.3)", fontWeight: 700 }}>
                    ▼ VCP DIP
                  </span>
                )}
                <Pill value={s.chg} />
                <ThemeBadge s={s} />
                <ThemeBadge s={s} />
                <EarningsBadge s={s} />
                <SectorAlignBadge s={s} />
                <MASlopeBadge s={s} />
                <CoilingBadge s={s} />
                <SetupTagBadge s={s} />
                <WeeklyStackBadge s={s} />
                {onQuickAdd && (
                  <button onClick={() => onQuickAdd({ ...s, signal_type: maKey })} style={{
                    padding: "2px 8px", fontSize: 9, cursor: "pointer", borderRadius: 3,
                    border: "1px solid var(--accent)", background: "transparent", color: "var(--accent)",
                    fontFamily: "inherit", letterSpacing: 0.5, whiteSpace: "nowrap",
                  }}>+ Journal</button>
                )}
              </div>
            </div>

            {/* VCS bar — critical signal */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                <span style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1 }}>VCS (VOLATILITY CONTRACTION)</span>
                <span style={{
                  fontSize: 11, fontWeight: 700,
                  color: s.vcs <= 3 ? "var(--green)" : s.vcs <= 5 ? "var(--yellow)" : "var(--orange)"
                }}>
                  {s.vcs}/10 {s.vcs <= 3 ? "🔥 COILED" : s.vcs <= 5 ? "✓ TIGHT" : "~OK"}
                </span>
              </div>
              <div style={{ height: 3, background: "var(--bg4)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 2,
                  width: `${(s.vcs / 10) * 100}%`,
                  background: s.vcs <= 3 ? "var(--green)" : s.vcs <= 5 ? "var(--yellow)" : "var(--orange)",
                  transition: "width 0.3s",
                }} />
              </div>
            </div>

            {/* Inline price chart */}
            <SignalChart s={s} />

            {/* LL-HL Pivot + Darvas detail row */}
            {(s.ll_hl_detected || s.darvas_detected) && (
              <div style={{
                display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap",
                padding: "5px 7px", borderRadius: 3,
                background: "var(--bg2)", border: "1px solid var(--border)",
              }}>
                {s.ll_hl_detected && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>LL-HL</span>
                    <span style={{ fontSize: 9, fontWeight: 700, color: "#2d7a3a" }}>
                      HL: {s.hl_price != null ? `$${s.hl_price}` : "—"}
                    </span>
                    <span style={{ fontSize: 9, color: "var(--text3)" }}>→</span>
                    <span style={{
                      fontSize: 9, fontWeight: 700,
                      color: s.approaching_pivot ? "#2d7a3a" : s.pivot_broken ? "#b8820a" : "var(--text)",
                    }}>
                      Pivot: {s.pivot_line != null ? `$${s.pivot_line}` : "—"}
                      {s.pct_from_pivot != null && (
                        <span style={{ fontWeight: 400, marginLeft: 3, opacity: 0.8 }}>
                          ({s.pct_from_pivot > 0 ? "+" : ""}{s.pct_from_pivot}%)
                        </span>
                      )}
                    </span>
                    {s.approaching_pivot && (
                      <span style={{ fontSize: 8, color: "#2d7a3a", fontWeight: 700 }}>⚡ NEAR</span>
                    )}
                  </div>
                )}
                {s.ll_hl_detected && s.darvas_detected && (
                  <span style={{ color: "var(--text3)", fontSize: 9 }}>|</span>
                )}
                {s.darvas_detected && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>DARVAS</span>
                    <span style={{ fontSize: 9, fontWeight: 700, color: "#7c4dff" }}>
                      Box: {s.box_bottom != null ? `$${s.box_bottom}` : "—"} – {s.box_top != null ? `$${s.box_top}` : "—"}
                    </span>
                    {s.box_bars != null && (
                      <span style={{ fontSize: 8, color: "var(--text3)" }}>({s.box_bars}d)</span>
                    )}
                    {s.darvas_status === "approaching" && (
                      <span style={{ fontSize: 8, color: "#7c4dff", fontWeight: 700 }}>⚡ NEAR TOP</span>
                    )}
                    {s.darvas_status === "breakout" && (
                      <span style={{ fontSize: 8, color: "#b8820a", fontWeight: 700 }}>🔥 BO</span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Flag / Pennant detail panel ─────────────────────────── */}
            {(s.flagDetected || s.flag_detected) && (() => {
              const fd = s.flagDetected || s.flag_detected;
              const ft = s.flagType     || s.flag_type;
              const fs = s.flagStatus   || s.flag_status;
              const pp = s.polePct      || s.pole_pct;
              const pb = s.poleBars     || s.pole_bars;
              const fb = s.flagBars     || s.flag_bars;
              const fr = s.flagRetracePct || s.flag_retrace_pct;
              const tt = s.tlTouches    || s.tl_touches;
              const bl = s.flagBreakoutLevel || s.flag_breakout_level;
              const st = s.flagStopPrice || s.flag_stop_price;
              const tg = s.flagTargetPrice || s.flag_target_price;
              const vd = s.volDryFlag   || s.vol_dry_flag;
              const pv = s.poleVolRatio || s.pole_vol_ratio;

              const statusColor = fs === "breaking"  ? "#ff5252"
                                : fs === "broken_out" ? "#ff7070"
                                : "#e07048";
              const statusLabel = fs === "breaking"  ? "⚡ AT TRIGGER"
                                : fs === "broken_out" ? "🔥 BROKEN OUT"
                                : "👁 WATCH";
              const typeLabel = ft === "pennant" ? "PENNANT" : "BULL FLAG";
              const rr = bl && st && tg
                ? ((tg - bl) / (bl - st)).toFixed(1)
                : null;

              return (
                <div style={{
                  marginBottom: 8, padding: "8px 10px", borderRadius: 4,
                  background: "rgba(255,82,82,0.05)",
                  border: `1px solid ${statusColor}44`,
                  borderLeft: `3px solid ${statusColor}`,
                }}>
                  {/* Header row */}
                  <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 1, color: statusColor }}>
                      🚩 {typeLabel}
                    </span>
                    <span style={{
                      fontSize: 8, fontWeight: 700, padding: "1px 6px", borderRadius: 2,
                      background: `${statusColor}22`, color: statusColor,
                      border: `1px solid ${statusColor}55`,
                    }}>{statusLabel}</span>
                    {vd && (
                      <span style={{
                        fontSize: 8, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
                        background: "rgba(45,122,58,0.12)", color: "#4ac891",
                        border: "1px solid rgba(74,200,145,0.4)",
                      }}>📉 VOL DRY</span>
                    )}
                  </div>

                  {/* Pole stats */}
                  <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 5 }}>
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>POLE </span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--green)" }}>
                        +{pp?.toFixed(1)}%
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>
                        in {pb}d
                      </span>
                      {pv && (
                        <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 4 }}>
                          vol {pv}×
                        </span>
                      )}
                    </div>
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>FLAG </span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text)" }}>
                        {fb}d
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>
                        -{fr?.toFixed(0)}% retrace
                      </span>
                    </div>
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>TL TOUCHES </span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: tt >= 4 ? "var(--green)" : "var(--yellow)" }}>
                        {tt}
                      </span>
                    </div>
                  </div>

                  {/* Entry / Stop / Target row */}
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {bl && (
                      <div>
                        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>TRIGGER </span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: statusColor }}>
                          ${bl.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {st && (
                      <div>
                        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>STOP </span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--red)" }}>
                          ${st.toFixed(2)}
                        </span>
                        {s.price && st && (
                          <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>
                            {((s.price - st) / s.price * 100).toFixed(1)}% risk
                          </span>
                        )}
                      </div>
                    )}
                    {tg && (
                      <div>
                        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>TARGET </span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--green)" }}>
                          ${tg.toFixed(2)}
                        </span>
                        <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>
                          (measured move)
                        </span>
                      </div>
                    )}
                    {rr && (
                      <div>
                        <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>R:R </span>
                        <span style={{ fontSize: 10, fontWeight: 700,
                          color: parseFloat(rr) >= 2.5 ? "var(--green)" : parseFloat(rr) >= 1.5 ? "var(--yellow)" : "var(--text3)" }}>
                          1:{rr}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* ── Stop / Target / Exit plan ─────────────────────────────── */}
            {s.stop_price != null && (
              <div style={{
                marginBottom: 8, padding: "7px 9px", borderRadius: 3,
                background: "var(--bg2)", border: "1px solid var(--border)",
              }}>
                {/* Stop + Targets row */}
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 5 }}>
                  <div>
                    <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>STOP </span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: "var(--red)" }}>
                      ${s.stop_price.toFixed(2)}
                    </span>
                    {s.stop_basis && (
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>
                        ({s.stop_basis === "swing_low" ? "swing" : "atr"})
                      </span>
                    )}
                    {s.price && s.stop_price && (
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 4 }}>
                        {((s.price - s.stop_price) / s.price * 100).toFixed(1)}% risk
                      </span>
                    )}
                  </div>
                  {s.target_1 != null && (
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>T1 </span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--green)" }}>
                        ${s.target_1.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>1R</span>
                    </div>
                  )}
                  {s.target_2 != null && (
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>T2 </span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--green)" }}>
                        ${s.target_2.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>2R</span>
                    </div>
                  )}
                  {s.target_3 != null && (
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>T3 </span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--green)" }}>
                        ${s.target_3.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>3.5R</span>
                    </div>
                  )}
                  {s.ema21_trail != null && (
                    <div>
                      <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>EMA21 </span>
                      <span style={{ fontSize: 10, color: "var(--purple)" }}>
                        ${s.ema21_trail.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 3 }}>trail anchor</span>
                    </div>
                  )}
                </div>

                {/* Partial exit plan — inline 4-step strip */}
                {s.partial_plan && (
                  <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                    {[
                      { label: "Entry→T1", action: "Hold full",         color: "#787b86" },
                      { label: "T1 hit",   action: "Sell 1/3 · BE",     color: "#089981" },
                      { label: "T2 hit",   action: "Sell 1/3 · EMA21",  color: "#f5a623" },
                      { label: "T3 hit",   action: "Sell 1/3 · EMA10",  color: "#2962ff" },
                    ].map((step, i) => (
                      <div key={i} style={{
                        display: "flex", alignItems: "center", gap: 3,
                        padding: "2px 6px", borderRadius: 2,
                        background: "var(--bg3)", border: `1px solid var(--border)`,
                        borderLeft: `2px solid ${step.color}`,
                      }}>
                        <span style={{ fontSize: 8, color: step.color, fontWeight: 700 }}>{step.label}</span>
                        <span style={{ fontSize: 7, color: "var(--text3)" }}>{step.action}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="bounce-card-body">
              <div className="bounce-stat">
                <span className="bounce-stat-label">PRICE</span>
                <span className="bounce-stat-val">{fmtPrice(s.price)}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">{maKey}</span>
                <span className="bounce-stat-val">{fmtPrice(s[maKey.toLowerCase()])}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">{s.ma21BelowMA && maKey === "MA21" ? "% BELOW" : "% ABOVE"}</span>
                <span className="bounce-stat-val" style={{
                  color: s.ma21BelowMA && maKey === "MA21" ? "var(--yellow)" : "var(--green)",
                  fontWeight: 700
                }}>
                  {s.ma21BelowMA && maKey === "MA21" ? "" : "+"}{(((s.price - s[maKey.toLowerCase()]) / s.price) * 100).toFixed(2)}%
                </span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">VOL RATIO</span>
                <span className="bounce-stat-val" style={{ color: s.volRatio > 1.5 ? "var(--green)" : "var(--text)" }}>
                  {s.volRatio}x
                </span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">VOL</span>
                <span className="bounce-stat-val">{fmtVol(s.vol)}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">RS (M)</span>
                <span className="bounce-stat-val" style={{ color: s.rs > 90 ? "var(--green)" : "var(--text)" }}>
                  {s.rs.toFixed(0)}
                </span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">SECTOR</span>
                <span className="bounce-stat-val" style={{ color: "var(--text3)", fontSize: 9 }}>
                  {s.sector || "—"}
                  {s.theme && THEME_STYLES[s.theme] && (
                    <span style={{
                      marginLeft: 5, fontSize: 8, fontWeight: 700,
                      color: THEME_STYLES[s.theme].color,
                    }}>
                      · {THEME_STYLES[s.theme].label}
                    </span>
                  )}
                </span>
              </div>
              {(s.wEma10 ?? s.w_ema10) != null && (
                <div className="bounce-stat">
                  <span className="bounce-stat-label">W EMA10</span>
                  <span className="bounce-stat-val" style={{
                    color: (s.wAboveEma10 ?? s.w_above_ema10) ? "var(--green)" : "var(--orange)",
                  }}>
                    ${(s.wEma10 ?? s.w_ema10).toFixed(2)}
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── EP Tab ────────────────────────────────────────────────────────────────────

function EPCard({ s, onQuickAdd }) {
  const entryOk   = s.ep_entry_ok;
  const borderCol = entryOk ? "#ff9800" : "var(--border)";
  const tagCol    = entryOk ? "#ff9800" : "var(--text3)";

  return (
    <div style={{
      background: "var(--bg2)",
      border: `1px solid ${borderCol}`,
      borderTop: `3px solid ${entryOk ? "#ff9800" : "var(--border)"}`,
      borderRadius: 4,
      padding: "12px 14px",
      marginBottom: 10,
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <a href={`https://finviz.com/quote.ashx?t=${s.ticker}`}
           target="_blank" rel="noreferrer"
           style={{ fontWeight: 700, fontSize: 14, color: "var(--accent)", textDecoration: "none" }}>
          {s.ticker}
        </a>

        {entryOk ? (
          <span style={{
            fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 2,
            background: "rgba(255,152,0,0.12)", color: "#ff9800",
            border: "1px solid rgba(255,152,0,0.3)", letterSpacing: 0.5,
          }}>⚡ ENTRY ZONE</span>
        ) : (
          <span style={{
            fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 2,
            background: "var(--bg3)", color: "var(--text3)",
            border: "1px solid var(--border)", letterSpacing: 0.5,
          }}>👁 WATCHLIST</span>
        )}

        <span style={{
          fontSize: 9, padding: "2px 7px", borderRadius: 2,
          background: "var(--bg3)", color: tagCol,
          border: "1px solid var(--border)",
        }}>
          EP {s.ep_days_ago}d ago · +{s.ep_gap_pct}% gap · {s.ep_vol_ratio}× vol
        </span>

        {s.ep_neglect === true && (
          <span style={{
            fontSize: 9, padding: "2px 6px", borderRadius: 2,
            background: "rgba(41,98,255,0.08)", color: "#2962ff",
            border: "1px solid rgba(41,98,255,0.2)",
          }}>NEGLECTED ✓</span>
        )}

        {onQuickAdd && (
          <button onClick={() => onQuickAdd(s)} style={{
            marginLeft: "auto", fontSize: 9, padding: "2px 8px",
            background: "var(--bg3)", border: "1px solid var(--border)",
            color: "var(--text2)", borderRadius: 2, cursor: "pointer",
            fontFamily: "inherit", letterSpacing: 0.5,
          }}>+ Journal</button>
        )}
      </div>

      {/* EP day stats */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))",
        gap: 8, marginBottom: 10,
        padding: "8px 10px", borderRadius: 3,
        background: "var(--bg)", border: "1px solid var(--border)",
      }}>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>EP DATE</div>
          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text)" }}>{s.ep_day || "—"}</div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>GAP</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#ff9800" }}>+{s.ep_gap_pct}%</div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>VOL RATIO</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: s.ep_vol_ratio >= 5 ? "var(--green)" : "var(--text)" }}>
            {s.ep_vol_ratio}×
          </div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>EP HIGH</div>
          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text)" }}>${s.ep_day_high?.toFixed(2)}</div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>PULLBACK</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: s.ep_pullback_pct > 10 ? "var(--yellow)" : "var(--green)" }}>
            -{s.ep_pullback_pct}%
          </div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>NOW</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>${s.price?.toFixed(2)}</div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>RS (M)</div>
          <div style={{ fontSize: 10, fontWeight: 600, color: s.rs > 85 ? "var(--green)" : "var(--text)" }}>
            {s.rs?.toFixed(0)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginBottom: 2 }}>VCS</div>
          <div style={{ fontSize: 10, fontWeight: 600, color: s.vcs <= 4 ? "var(--green)" : "var(--text)" }}>
            {s.vcs}/10
          </div>
        </div>
      </div>

      {/* EP-specific stop / target row */}
      <div style={{
        display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap",
        padding: "7px 10px", borderRadius: 3,
        background: entryOk ? "rgba(255,152,0,0.05)" : "var(--bg)",
        border: `1px solid ${entryOk ? "rgba(255,152,0,0.2)" : "var(--border)"}`,
      }}>
        <div>
          <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>EP STOP </span>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)" }}>
            ${s.ep_stop?.toFixed(2)}
          </span>
          <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 4 }}>
            (below EP day low ${s.ep_day_low?.toFixed(2)})
          </span>
        </div>
        <div>
          <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>EP TARGET </span>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--green)" }}>
            ${s.ep_target?.toFixed(2)}
          </span>
          <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 4 }}>
            (2× gap magnitude)
          </span>
        </div>
        {s.ep_stop && s.price && (
          <div style={{ fontSize: 8, color: "var(--text3)" }}>
            Risk: {((s.price - s.ep_stop) / s.price * 100).toFixed(1)}%
          </div>
        )}
      </div>

      {/* Inline chart */}
      <SignalChart s={s} />
    </div>
  );
}

function EPTab({ data, onQuickAdd }) {
  const { epSignals = [], market } = data;
  const entryReady = epSignals.filter(s => s.ep_entry_ok);
  const watchlist  = epSignals.filter(s => !s.ep_entry_ok);

  return (
    <div>
      <RegimeGate compact={true} />

      {/* Explanation box */}
      <div style={{
        marginBottom: 14, padding: "12px 14px", borderRadius: 4,
        background: "rgba(255,152,0,0.06)", border: "1px solid rgba(255,152,0,0.2)",
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#ff9800", marginBottom: 6, letterSpacing: 0.5 }}>
          ⚡ EPISODIC PIVOT — DELAYED REACTION SETUPS
        </div>
        <div style={{ fontSize: 10, color: "var(--text2)", lineHeight: 1.6 }}>
          Stocks that had a major earnings-driven gap (≥10%, ≥3× volume) in the last 5 days
          and have since pulled back into a lower-risk entry zone. The original EP day signals
          institutional repricing — the delayed entry catches the second leg after early holders take profits.
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
          {[
            { label: "Entry zone", desc: "3–20% pullback from EP high, above EP day open" },
            { label: "EP stop",    desc: "Below EP day low — thesis dead if lost" },
            { label: "Target",     desc: "2× initial gap magnitude from entry" },
            { label: "Neglect",    desc: "Stock flat/down 3 months before EP = higher conviction" },
          ].map((tip, i) => (
            <div key={i} style={{ fontSize: 9, color: "var(--text3)" }}>
              <span style={{ color: "#ff9800", fontWeight: 700 }}>{tip.label}: </span>{tip.desc}
            </div>
          ))}
        </div>
      </div>

      {epSignals.length === 0 ? (
        <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text3)", fontSize: 11 }}>
          No EP setups detected in the last 5 days.
          {" "}EP setups are most common around earnings season (Jan, Apr, Jul, Oct).
        </div>
      ) : (
        <>
          {/* Entry-ready */}
          {entryReady.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: "#ff9800",
                letterSpacing: 1, marginBottom: 10,
                display: "flex", alignItems: "center", gap: 8,
              }}>
                ⚡ ENTRY ZONE
                <span style={{
                  fontSize: 9, padding: "1px 6px", borderRadius: 2,
                  background: "rgba(255,152,0,0.12)", color: "#ff9800",
                  border: "1px solid rgba(255,152,0,0.2)",
                }}>{entryReady.length}</span>
              </div>
              {entryReady.map(s => (
                <EPCard key={s.ticker} s={s} onQuickAdd={onQuickAdd} />
              ))}
            </div>
          )}

          {/* Watchlist */}
          {watchlist.length > 0 && (
            <div>
              <div style={{
                fontSize: 10, fontWeight: 700, color: "var(--text3)",
                letterSpacing: 1, marginBottom: 10,
                display: "flex", alignItems: "center", gap: 8,
              }}>
                👁 WATCHING — NOT YET IN ENTRY ZONE
                <span style={{
                  fontSize: 9, padding: "1px 6px", borderRadius: 2,
                  background: "var(--bg3)", color: "var(--text3)",
                  border: "1px solid var(--border)",
                }}>{watchlist.length}</span>
              </div>
              {watchlist.map(s => (
                <EPCard key={s.ticker} s={s} onQuickAdd={onQuickAdd} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ShortsTab({ data }) {
  const { topShorts = [], market = {} } = data || {};
  const regimeMode = market?.mode;

  const criteria = [
    { label: "Price below MA10, MA21 & MA50", color: "var(--red)" },
    { label: "Volume above average on down days", color: "var(--red)" },
    { label: "Failed rally back to broken MA", color: "var(--red)" },
    { label: "RS rank below 30 (relative weakness)", color: "var(--red)" },
    { label: "Market in downtrend or distribution", color: "var(--orange)" },
    { label: "Clear catalyst (earnings miss, downgrade)", color: "var(--orange)" },
    { label: "Short score ≥ 60 for high conviction", color: "var(--orange)" },
    { label: "Cover into panic/washout, not at target", color: "var(--yellow)" },
    { label: "Stop just above broken MA level", color: "var(--yellow)" },
    { label: "Target: 1:1 to 1.5:1 R (take profits fast)", color: "var(--yellow)" },
  ];

  return (
    <div>
      {/* Regime mode callout — prominent when system is routing to SHORTS */}
      {regimeMode === "SHORTS" && (
        <div style={{
          marginBottom: 12, padding: "10px 14px", borderRadius: 4,
          background: "rgba(242,54,69,0.07)", border: "1px solid rgba(242,54,69,0.3)",
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#f23645", marginBottom: 4, letterSpacing: 0.5 }}>
            🔴 REGIME DANGER — SHORT CANDIDATES ACTIVE
          </div>
          <div style={{ fontSize: 10, color: "var(--text2)" }}>
            Market score {market?.score}/100. System is in SHORTS ONLY mode.
            No new long setups. Review open longs for exit. Size 25% on short entries.
          </div>
        </div>
      )}
      {regimeMode === "EXITS_ONLY" && (
        <div style={{
          marginBottom: 12, padding: "10px 14px", borderRadius: 4,
          background: "rgba(255,152,0,0.07)", border: "1px solid rgba(255,152,0,0.3)",
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#ff9800", marginBottom: 4, letterSpacing: 0.5 }}>
            🟠 REGIME WARN — EXITS ONLY
          </div>
          <div style={{ fontSize: 10, color: "var(--text2)" }}>
            Market score {market?.score}/100. No new longs. Manage existing positions: trail stops, take partial profits at targets.
          </div>
        </div>
      )}

      {market.label === "Positive" && regimeMode !== "SHORTS" && (
        <div className="regime-warn">
          ⚠ Market score {market.score}/100 POSITIVE — shorts face significant headwind. Only highest-conviction setups (score ≥ 80). Reduce size.
        </div>
      )}

      <IntradayAlerts />
      <TopPicksBar mode="short" />

      <div className="criteria-box short-criteria">
        <div className="criteria-title">Short Entry Criteria</div>
        <div className="criteria-grid">
          {criteria.map((c, i) => (
            <div className="criteria-item" key={i}>
              <div className="criteria-dot" style={{ background: c.color }} />
              <span>{c.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="section-hdr">
        <span className="section-title" style={{ color: "var(--red)" }}>Top Short Setups</span>
        <span className="section-count">{topShorts.length} candidates</span>
        <span style={{ fontSize: 9, color: "var(--text3)", marginLeft: 8 }}>
          sorted by short score ↓
        </span>
      </div>

      <div className="bounce-grid">
        {topShorts.map(s => (
          <div className="short-card" key={s.ticker}>
            <div className="short-card-top">
              <span className="short-card-ticker">▼ <TVLink ticker={s.ticker}>{s.ticker} ↗</TVLink></span>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <ScoreBadge score={s.shortScore} />
                <Pill value={s.chg} />
              </div>
            </div>

            <div className="bounce-card-body" style={{ marginBottom: 6 }}>
              <div className="bounce-stat">
                <span className="bounce-stat-label">PRICE</span>
                <span className="bounce-stat-val">{fmtPrice(s.price)}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">MA10</span>
                <span className="bounce-stat-val" style={{ color: "var(--red)" }}>{fmtPrice(s.ma10)}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">MA21</span>
                <span className="bounce-stat-val" style={{ color: "var(--red)" }}>{fmtPrice(s.ma21)}</span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">VOL RATIO</span>
                <span className="bounce-stat-val" style={{ color: s.volRatio > 1.5 ? "var(--red)" : "var(--text)" }}>
                  {s.volRatio}x
                </span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label" title="Mansfield-weighted RS: 12M×0.4 + 9M×0.2 + 6M×0.2 + 3M×0.2 vs SPY">MANSFIELD RS</span>
                <span className="bounce-stat-val" style={{ color: s.rs < 20 ? "var(--red)" : "var(--orange)" }}>
                  {s.rs.toFixed(0)}
                </span>
              </div>
              <div className="bounce-stat">
                <span className="bounce-stat-label">DAYS BELOW</span>
                <span className="bounce-stat-val">{s.daysBelow}d</span>
              </div>
            </div>

            <div className="short-catalyst">
              <div className="short-catalyst-item">
                <span className="short-catalyst-label">CATALYST</span>
                <span className="short-catalyst-val">{s.catalyst}</span>
              </div>
              <div className="short-catalyst-item">
                <span className="short-catalyst-label">SETUP</span>
                <span className="short-catalyst-val">{s.setupType}</span>
              </div>
              <div className="short-catalyst-item">
                <span className="short-catalyst-label">FAILED RALLY</span>
                <span className="short-catalyst-val" style={{ color: s.failedRally ? "var(--red)" : "var(--text3)" }}>
                  {s.failedRally ? "YES ✓" : "NO"}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Short scoring legend */}
      <div style={{ marginTop: 16, padding: "10px 14px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 2 }}>
        <div className="criteria-title">Short Score Breakdown</div>
        <div style={{ display: "flex", gap: 20, fontSize: 10, color: "var(--text2)" }}>
          <span>RS &lt; 20 → +30 pts</span>
          <span>Vol ratio &gt; 1.5x → +25 pts</span>
          <span>Failed rally → +25 pts</span>
          <span>Days below &gt; 5 → +20 pts</span>
          <span style={{ color: "var(--red)" }}>≥80 HIGH · ≥60 MED · &lt;60 LOW</span>
        </div>
      </div>
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

function SignalRow({ s, expanded, onExpand, onQuickAdd }) {
  const maLabel = s.bouncingFrom || s._ma || "—";
  const maC = MA_COLORS[maLabel] || "var(--text3)";
  const base = "var(--bg)";

  return (
    <>
      <tr
        onClick={onExpand}
        style={{ background: expanded ? "rgba(41,98,255,0.05)" : base, cursor: "pointer" }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
        onMouseLeave={e => e.currentTarget.style.background = expanded ? "rgba(41,98,255,0.05)" : base}
      >
        {/* MA badge */}
        <td style={{ ...TDLS, textAlign: "center", width: 60 }}>
          <span style={{
            display: "inline-block", padding: "2px 7px", borderRadius: 3,
            fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
            background: `${maC}18`, color: maC, border: `1px solid ${maC}40`,
          }}>{maLabel}</span>
        </td>

        {/* Ticker */}
        <td style={{ ...TDLS, fontWeight: 700 }}>
          <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 8, opacity: 0.5 }}>↗</span>
          </a>
        </td>

        {/* RS */}
        <td style={{ ...TDLS, textAlign: "center" }}>
          <span style={{
            display: "inline-block", padding: "3px 8px", borderRadius: 3,
            fontWeight: 700, fontSize: 12, background: rsBgS(s.rs), color: rsColS(s.rs),
            minWidth: 32, textAlign: "center",
          }}>{s.rs}</span>
        </td>

        {/* Sector */}
        <td style={{ ...TDLS, color: "var(--text3)", fontSize: 11 }}>
          {s.sector || "—"}
          {s.theme && THEME_STYLES[s.theme] && (
            <span style={{
              marginLeft: 4, fontSize: 8, fontWeight: 700,
              padding: "1px 4px", borderRadius: 2,
              background: THEME_STYLES[s.theme].bg,
              color: THEME_STYLES[s.theme].color,
              border: `1px solid ${THEME_STYLES[s.theme].border}`,
              display: "inline-block",
            }}>{THEME_STYLES[s.theme].label}</span>
          )}
        </td>

        {/* Price */}
        <td style={{ ...TDLS, fontWeight: 600 }}>
          ${s.price != null ? Number(s.price).toFixed(2) : "—"}
        </td>

        {/* CHG — sep */}
        <td style={{ ...TDLS, fontWeight: 600, borderRight: "2px solid var(--border2)",
          color: (s.chg||0) > 0 ? "var(--green)" : (s.chg||0) < 0 ? "var(--red)" : "var(--text3)" }}>
          {s.chg != null ? `${s.chg > 0 ? "+" : ""}${s.chg.toFixed(1)}%` : "—"}
        </td>

        {/* Readiness */}
        <td style={{ ...TDLS, textAlign: "center" }}>
          <ReadinessBadge v={s.entry_readiness} />
        </td>

        {/* ADR % */}
        <td style={{ ...TDLS, fontWeight: 700, textAlign: "center",
          color: adrCol(s.adrPct), background: adrBg(s.adrPct) }}>
          {s.adrPct != null ? `${s.adrPct.toFixed(1)}%` : "—"}
        </td>

        {/* EMA21L % */}
        <td style={{ ...TDLS, fontWeight: 700, textAlign: "center",
          color: e21Col(s.ema21LowPct), background: e21Bg(s.ema21LowPct) }}>
          {s.ema21LowPct != null ? `${s.ema21LowPct.toFixed(1)}%` : "—"}
        </td>

        {/* 3WT — sep */}
        <td style={{ ...TDLS, textAlign: "center", borderRight: "2px solid var(--border2)" }}>
          {s.threeWeeksTight
            ? <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 14 }}>✦</span>
            : <span style={{ color: "var(--border2)", fontSize: 10 }}>·</span>}
        </td>

        {/* VCS */}
        <td style={{ ...TDLS, fontWeight: 700, textAlign: "center", color: vcsColS(s.vcs) }}>
          {s.vcs != null ? s.vcs.toFixed(1) : "—"}
        </td>

        {/* Stop */}
        <td style={{ ...TDLS, color: "var(--red)", fontWeight: 600 }}>
          {s.stop_price != null ? `$${Number(s.stop_price).toFixed(2)}` : "—"}
        </td>

        {/* T1 */}
        <td style={{ ...TDLS, color: "var(--green)", fontWeight: 600 }}>
          {s.target_1 != null ? `$${Number(s.target_1).toFixed(2)}` : "—"}
        </td>

        {/* Score */}
        <td style={{ ...TDLS, fontWeight: 700, textAlign: "center", color: scoreColS(s.signal_score || 0) }}>
          {s.signal_score != null ? s.signal_score.toFixed(1) : "—"}
        </td>

        {/* Log — stop propagation */}
        <td style={{ ...TDLS, textAlign: "center" }} onClick={e => e.stopPropagation()}>
          {onQuickAdd && (
            <button onClick={() => onQuickAdd({ ...s, signal_type: maLabel })} style={{
              padding: "2px 8px", fontSize: 9, cursor: "pointer", borderRadius: 3,
              border: "1px solid var(--accent)", background: "transparent",
              color: "var(--accent)", fontFamily: "inherit",
            }}>+ Log</button>
          )}
        </td>
      </tr>

      {/* Expanded */}
      {expanded && (
        <tr style={{ background: "rgba(41,98,255,0.03)" }}>
          <td colSpan={14} style={{ padding: "10px 16px 12px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 11, alignItems: "center" }}>
              {[
                ["MA21",      s.ma21],
                ["MA50",      s.ma50],
                ["EMA21 LOW", s.ema21Low],
                ["ATR",       s.atr ? `$${Number(s.atr).toFixed(2)}` : null],
                ["T2",        s.target_2],
                ["T3",        s.target_3],
              ].map(([l, v]) => v != null && (
                <div key={l}>
                  <span style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1, marginRight: 4 }}>{l}</span>
                  <span style={{ fontWeight: 600, color: l === "EMA21 LOW" ? "var(--green)" : l.startsWith("T") ? "var(--green)" : "var(--text)" }}>
                    {l === "ATR" ? v : `$${Number(v).toFixed(2)}`}
                  </span>
                </div>
              ))}
              {s.ema21LowPct != null && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: e21Bg(s.ema21LowPct), color: e21Col(s.ema21LowPct),
                  border: `1px solid ${e21Col(s.ema21LowPct)}40` }}>
                  {s.ema21LowPct.toFixed(1)}% to EMA21 Low —
                  {s.ema21LowPct < 5 ? " LOW RISK ✓" : s.ema21LowPct <= 8 ? " MODERATE" : " TOO WIDE — SKIP"}
                </span>
              )}
              {s.threeWeeksTight && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(8,153,129,0.12)", color: "var(--green)", border: "1px solid rgba(8,153,129,0.3)" }}>
                  ✦ 3-WEEKS TIGHT
                </span>
              )}
              {s.coiling && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(124,77,255,0.1)", color: "var(--purple)", border: "1px solid rgba(124,77,255,0.3)" }}>
                  ⟳ COILING
                </span>
              )}
              {s.setupTag && (
                <span style={{ padding: "2px 10px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  background: "rgba(245,166,35,0.1)", color: "var(--yellow)", border: "1px solid rgba(245,166,35,0.3)" }}>
                  {s.setupTag}
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SignalTable({ ma10, ma21, ma50, onQuickAdd }) {
  const [sortKey,  setSortKey]  = React.useState("signal_score");
  const [sortDir,  setSortDir]  = React.useState(-1);
  const [expanded, setExpanded] = React.useState(null);
  const [maFilter, setMaFilter] = React.useState("all");

  const allSignals = [
    ...ma10.map(s => ({ ...s, _ma: "MA10" })),
    ...ma21.map(s => ({ ...s, _ma: "MA21" })),
    ...ma50.map(s => ({ ...s, _ma: "MA50" })),
  ];

  let rows = maFilter === "all"
    ? allSignals
    : maFilter.startsWith("theme_")
      ? allSignals.filter(s => s.theme === maFilter.replace("theme_", ""))
      : allSignals.filter(s => s._ma === maFilter);
  rows = [...rows].sort((a, b) => {
    const av = a[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    const bv = b[sortKey] ?? (sortDir > 0 ? Infinity : -Infinity);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  function thClick(k, def = -1) { setSortKey(k); setSortDir(sortKey === k ? sortDir * -1 : def); }

  function Th({ label, k, align = "left", title = "", def = -1, sep = false }) {
    const active = sortKey === k;
    return (
      <th title={title} onClick={() => thClick(k, def)}
        style={{ ...THLS, textAlign: align, borderRight: sep ? "2px solid var(--border2)" : undefined,
          color: active ? "var(--accent)" : "var(--text3)" }}>
        {label}{active ? (sortDir > 0 ? " ↑" : " ↓") : " ↕"}
      </th>
    );
  }

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 5, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
        {[
          ["all",  `All  ${allSignals.length}`],
          ["MA10", `MA10  ${ma10.length}`],
          ["MA21", `MA21  ${ma21.length}`],
          ["MA50", `MA50  ${ma50.length}`],
        ].map(([v, l]) => (
          <button key={v} onClick={() => setMaFilter(v)} style={{
            padding: "3px 10px", fontSize: 9, textTransform: "uppercase", cursor: "pointer",
            borderRadius: 3, fontFamily: "inherit", letterSpacing: 0.5,
            border: `1px solid ${maFilter === v ? (MA_COLORS[v] || "var(--accent)") : "var(--border)"}`,
            background: maFilter === v ? `${(MA_COLORS[v] || "var(--accent)")}18` : "transparent",
            color: maFilter === v ? (MA_COLORS[v] || "var(--accent)") : "var(--text3)",
          }}>{l}</button>
        ))}
        <span style={{ width: 1, background: "var(--border)", height: 16, margin: "0 4px" }} />
        {/* Theme quick-filter pills */}
        {[...new Set([...ma10, ...ma21, ...ma50].map(s => s.theme).filter(Boolean))].sort().map(theme => {
          const st = THEME_STYLES[theme];
          if (!st) return null;
          const active = maFilter === "theme_" + theme;
          return (
            <button key={theme} onClick={() => setMaFilter(active ? "all" : "theme_" + theme)} style={{
              padding: "3px 8px", fontSize: 8, cursor: "pointer", borderRadius: 3,
              fontFamily: "inherit", letterSpacing: 0.3, fontWeight: 700,
              border: `1px solid ${active ? st.color : st.border}`,
              background: active ? st.bg : "transparent",
              color: active ? st.color : "var(--text3)",
            }}>{st.label}</button>
          );
        })}
        <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--text3)" }}>
          ADR 3.5–8% · EMA21L &lt;5% low risk · &gt;8% skip · ✦ 3-Wk Tight · click row to expand
        </span>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: 24, color: "var(--text3)", textAlign: "center", fontSize: 12,
          background: "var(--bg2)", borderRadius: 6, border: "1px solid var(--border)" }}>
          No signals. Run a scan first.
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 860 }}>
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                <th colSpan={7} style={{ ...THLS, fontSize: 8, textAlign: "center",
                  borderRight: "2px solid var(--border2)", letterSpacing: 2 }}>SIGNAL</th>
                <th colSpan={3} style={{ ...THLS, fontSize: 8, textAlign: "center", color: "var(--accent)",
                  borderRight: "2px solid var(--border2)", letterSpacing: 2 }}>CORE STATS</th>
                <th colSpan={4} style={{ ...THLS, fontSize: 8, textAlign: "center", letterSpacing: 2 }}>TRADE</th>
              </tr>
              <tr>
                <th style={{ ...THLS, width: 60, cursor: "default" }}>MA</th>
                <Th label="TICKER" k="ticker"       def={1}  />
                <Th label="RS"     k="rs"            align="center" def={-1} />
                <Th label="SECTOR" k="sector"        def={1}  />
                <Th label="PRICE"  k="price"         def={-1} />
                <Th label="CHG"    k="chg"           def={-1} sep={true} />
                <Th label="READY"  k="signal_score"  align="center" def={-1}
                  title="Entry Readiness 1–5" />
                <Th label="ADR %"  k="adrPct"        align="center" def={1}
                  title="Avg Daily Range % — ideal 3.5–8%" />
                <Th label="EMA21L %" k="ema21LowPct" align="center" def={1}
                  title="Distance to EMA21 Low — <5% low risk, >8% skip" />
                <th style={{ ...THLS, textAlign: "center", cursor: "default",
                  borderRight: "2px solid var(--border2)" }}>3WT</th>
                <Th label="VCS"   k="vcs"          align="center" def={1}
                  title="Volatility Contraction Score — lower is tighter" />
                <Th label="STOP"  k="stop_price"   def={1}  />
                <Th label="T1"    k="target_1"     def={-1} />
                <Th label="SCORE" k="signal_score" align="center" def={-1} />
                <th style={{ ...THLS, cursor: "default" }}>LOG</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <SignalRow
                  key={`${s.ticker}-${s._ma}`}
                  s={s}
                  expanded={expanded === `${s.ticker}-${s._ma}`}
                  onExpand={() => setExpanded(expanded === `${s.ticker}-${s._ma}` ? null : `${s.ticker}-${s._ma}`)}
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


// ── TopPicksBar ────────────────────────────────────────────────────────────

function TopPicksBar({ onQuickAdd, mode = 'long' }) {
  const [picks, setPicks]   = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/top-picks?max_take=2")
      .then(r => r.json())
      .then(d => {
        // New response has longs{} and shorts{} keys
        const section = mode === "short" ? d.shorts : d.longs;
        setPicks(section || d);  // fallback for backward compat
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [mode]);

  if (loading) return null;
  if (!picks || !picks.take?.length) return null;

  const isShort = mode === "short";
  const tierStyle = (tier) => (isShort ? {
    TAKE:    { bg: "rgba(255,51,102,0.07)", border: "rgba(255,51,102,0.4)",  label: "🔴 TAKE SHORT",  dot: "#ff3366" },
    WATCH:   { bg: "rgba(255,140,0,0.06)",  border: "rgba(255,140,0,0.35)",  label: "🟠 WATCH SHORT", dot: "#ff8c00" },
    MONITOR: { bg: "rgba(90,120,150,0.05)", border: "rgba(90,120,150,0.2)",  label: "📋 MONITOR",     dot: "#5a7896" },
  } : {
    TAKE:    { bg: "rgba(0,245,160,0.07)", border: "rgba(0,245,160,0.4)",  label: "✅ TAKE",    dot: "#00f5a0" },
    WATCH:   { bg: "rgba(0,200,255,0.06)", border: "rgba(0,200,255,0.35)", label: "👀 WATCH",   dot: "#00c8ff" },
    MONITOR: { bg: "rgba(90,120,150,0.05)", border: "rgba(90,120,150,0.2)", label: "📋 MONITOR", dot: "#5a7896" },
  })[tier] || {};

  const ScoreBar = ({ score }) => {
    const pct = Math.min(100, score);
    const col = pct >= 60 ? "#00f5a0" : pct >= 40 ? "#f5c400" : "#ff3366";
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
        <div style={{ flex: 1, height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 1 }}>
          <div style={{ width: `${pct}%`, height: "100%", background: col, borderRadius: 1, transition: "width 0.5s" }} />
        </div>
        <span style={{ fontFamily: "monospace", fontSize: 9, color: col, minWidth: 28 }}>{score}</span>
      </div>
    );
  };

  const allActional = [...(picks.take || []), ...(picks.watch || [])];
  const monitor     = picks.monitor || [];

  return (
    <div style={{ marginBottom: 14 }}>

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            fontFamily: "monospace", fontSize: 11, letterSpacing: 2,
            color: isShort ? "#ff3366" : "#00f5a0", textTransform: "uppercase", fontWeight: 700,
          }}>
            {isShort ? "🔴 Priority Shorts" : "🎯 Priority Picks"}
          </span>
          <span style={{ fontSize: 9, color: "var(--text3)" }}>
            {picks.summary?.total} signals ranked · act on TAKE first
          </span>
        </div>
        {monitor.length > 0 && (
          <span style={{ fontSize: 9, color: "var(--text3)" }}>
            +{monitor.length} monitoring
          </span>
        )}
      </div>

      {/* TAKE + WATCH cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 8 }}>
        {allActional.map((s, i) => {
          const tier = s.priority_tier;
          const ts   = tierStyle(tier);
          const bd   = s.priority_breakdown || {};
          return (
            <div key={i} style={{
              background: ts.bg,
              border: `1px solid ${ts.border}`,
              borderRadius: 4,
              padding: "12px 14px",
              position: "relative",
            }}>
              {/* Tier badge */}
              <div style={{
                position: "absolute", top: 10, right: 12,
                fontSize: 9, fontWeight: 700, letterSpacing: 1,
                color: ts.dot, fontFamily: "monospace",
              }}>{ts.label}</div>

              {/* Ticker + price */}
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: "var(--text)", fontFamily: "monospace" }}>
                  {s.ticker}
                </span>
                <span style={{ fontSize: 11, color: "var(--text2)" }}>
                  ${s.price?.toFixed(2)}
                </span>
                <span style={{ fontSize: 9, color: "var(--text3)" }}>
                  {s.bouncing_from || s.signal_type}
                </span>
              </div>

              {/* Priority score bar */}
              <ScoreBar score={s.priority_score || 0} />

              {/* Reason */}
              <div style={{ fontSize: 10, color: "var(--text2)", marginTop: 6, lineHeight: 1.6 }}>
                {s.priority_reason}
              </div>

              {/* Key stats row */}
              <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                {[
                  { l: "VCS",  v: s.vcs?.toFixed(1),                     hi: s.vcs <= 3 },
                  { l: "RS",   v: s.rs,                                   hi: s.rs >= 85 },
                  { l: "Vol",  v: s.vol_ratio ? `${s.vol_ratio.toFixed(1)}×` : "—", hi: s.vol_ratio >= 1.5 },
                  { l: "Stop", v: s.stop_price ? `$${s.stop_price.toFixed(2)}` : "—", hi: false },
                  { l: "T1",   v: s.target_1   ? `$${s.target_1.toFixed(2)}` : "—",   hi: true  },
                ].map(({ l, v, hi }) => (
                  <div key={l} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 8, color: "var(--text3)", letterSpacing: 1 }}>{l}</div>
                    <div style={{
                      fontFamily: "monospace", fontSize: 11, fontWeight: 700,
                      color: hi ? ts.dot : "var(--text)",
                    }}>{v ?? "—"}</div>
                  </div>
                ))}
              </div>

              {/* Score breakdown mini-bar */}
              <div style={{ display: "flex", gap: 3, marginTop: 8 }}>
                {[
                  { l: "VCS",  v: bd.vcs_score,  max: 30, c: "#00f5a0" },
                  { l: "Prox", v: bd.prox_score, max: 25, c: "#00c8ff" },
                  { l: "Vol",  v: bd.vol_score,  max: 20, c: "#f5c400" },
                  { l: "Sect", v: bd.sect_score, max: 15, c: "#a855f7" },
                  { l: "RS",   v: bd.rs_score,   max: 10, c: "#ff8c00" },
                ].map(({ l, v, max, c }) => (
                  <div key={l} style={{ flex: 1, textAlign: "center" }}>
                    <div style={{ height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 1, marginBottom: 2 }}>
                      <div style={{ width: `${Math.min(100, (v||0)/max*100)}%`, height: "100%", background: c, borderRadius: 1 }} />
                    </div>
                    <div style={{ fontSize: 7, color: "var(--text3)", letterSpacing: 0.5 }}>{l}</div>
                  </div>
                ))}
              </div>

              {/* Quick add */}
              {onQuickAdd && (
                <button
                  onClick={() => onQuickAdd(s)}
                  style={{
                    marginTop: 10, width: "100%", padding: "5px 0",
                    background: `${ts.dot}18`, border: `1px solid ${ts.border}`,
                    color: ts.dot, borderRadius: 2, cursor: "pointer",
                    fontSize: 9, letterSpacing: 1, fontFamily: "monospace", fontWeight: 700,
                  }}
                >
                  + ADD TO JOURNAL
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Monitor strip */}
      {monitor.length > 0 && (
        <div style={{
          marginTop: 8, padding: "8px 12px",
          background: "rgba(90,120,150,0.04)",
          border: "1px solid rgba(90,120,150,0.15)",
          borderRadius: 3,
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        }}>
          <span style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, fontWeight: 700 }}>
            📋 MONITOR — review, don't act yet:
          </span>
          {monitor.slice(0, 10).map((s, i) => (
            <span key={i} style={{
              fontSize: 10, fontFamily: "monospace", fontWeight: 700,
              color: "var(--text2)",
              padding: "1px 6px", background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2,
            }}>
              {s.ticker}
              <span style={{ fontSize: 8, color: "var(--text3)", marginLeft: 4 }}>
                {s.priority_score}
              </span>
            </span>
          ))}
          {monitor.length > 10 && (
            <span style={{ fontSize: 9, color: "var(--text3)" }}>+{monitor.length - 10} more</span>
          )}
        </div>
      )}
    </div>
  );
}


// ── IntradayAlerts ─────────────────────────────────────────────────────────

function IntradayAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [lastCheck, setLastCheck] = useState(null);

  const fetchAlerts = () => {
    fetch("/api/intraday-ma/alerts")
      .then(r => r.json())
      .then(d => {
        setAlerts(d.alerts || []);
        setLastCheck(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5 * 60 * 1000); // refresh every 5 min
    return () => clearInterval(interval);
  }, []);

  if (!alerts.length) return null;

  return (
    <div style={{
      marginBottom: 12, padding: "10px 14px",
      background: "rgba(255,152,0,0.05)",
      border: "1px solid rgba(255,152,0,0.3)",
      borderRadius: 3,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#ff9800", fontFamily: "monospace", letterSpacing: 1 }}>
          ⚡ INTRADAY ALERTS TODAY
        </span>
        <span style={{ fontSize: 9, color: "var(--text3)" }}>
          {alerts.length} triggered · checked {lastCheck}
        </span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {alerts.map((a, i) => {
          const [ticker, ma] = a.split(":");
          const isShort = ma?.includes("SHORT");
          return (
            <div key={i} style={{
              padding: "3px 10px",
              background: isShort ? "rgba(255,51,102,0.08)" : "rgba(255,152,0,0.08)",
              border: `1px solid ${isShort ? "rgba(255,51,102,0.3)" : "rgba(255,152,0,0.3)"}`,
              borderRadius: 2,
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 11, color: "var(--text)" }}>
                {ticker}
              </span>
              <span style={{ fontSize: 9, color: "#ff9800", fontFamily: "monospace" }}>
                {ma}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LongsTab({ data, onQuickAdd }) {
  const { ma10Bounces = [], ma21Bounces = [], ma50Bounces = [], longStocks = [], market = {} } = data || {};

  const longCriteria = [
    { label: "MA21: within 2% above OR up to 1.5% below — VCP dip under MA21 is valid", color: "var(--cyan)" },
    { label: "MA10: price above and within 1.5% — tighter faster signal", color: "var(--cyan)" },
    { label: "MA50: price must be above — dipping below MA50 is a red flag", color: "var(--cyan)" },
    { label: "VCS ≤ 5 required — volatility contraction is the primary qualifier", color: "var(--green)" },
    { label: "Volume above average on bounce day (≥1.2x)", color: "var(--green)" },
    { label: "Mansfield RS above 80 — weighted 12M/9M/6M/3M vs SPY (recent periods count more)", color: "var(--green)" },
    { label: "Market in uptrend (conditions ≥ 50%)", color: "var(--green)" },
    { label: "Stock above all 3 MAs = tier 1 setup (highest conviction)", color: "var(--green)" },
    { label: "VCS tightening before bounce (coiled)", color: "var(--yellow)" },
    { label: "Stop just below the MA being tested", color: "var(--orange)" },
    { label: "Target: 2:1 R minimum, hold in uptrend", color: "var(--orange)" },
  ];

  return (
    <div>
      <IntradayAlerts />
      <TopPicksBar onQuickAdd={onQuickAdd} />
      <RegimeGate compact={true} />

      <div className="criteria-box">
        <div className="criteria-title">Long Entry Criteria</div>
        <div className="criteria-grid">
          {longCriteria.map((c, i) => (
            <div className="criteria-item" key={i}>
              <div className="criteria-dot" style={{ background: c.color }} />
              <span>{c.label}</span>
            </div>
          ))}
        </div>
      </div>



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
                {["RS","SECTOR","ETF","1M %","RS TREND","DIST 200MA"].map(h => (
                  <th key={h} style={{
                    textAlign: "left", padding: "4px 8px", fontSize: 9,
                    color: "var(--text3)", borderBottom: "1px solid var(--border)",
                    letterSpacing: 1,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sectors.map((s, i) => {
                const rs1m = s.rs_vs_spy_1m;
                const etfName = s.etf || "—";
                return (
                  <tr key={s.name} style={{ background: i % 2 === 0 ? "transparent" : "var(--bg2)" }}>
                    <td style={{ padding: "6px 8px" }}>
                      <span style={{
                        display: "inline-block", minWidth: 28, textAlign: "center",
                        padding: "1px 5px", borderRadius: 2, fontSize: 10, fontWeight: 700,
                        background: rsColor(s.rank ? (11 - s.rank) * 10 : 50),
                        color: "#fff",
                      }}>{s.rank || "—"}</span>
                    </td>
                    <td style={{ padding: "6px 8px", fontWeight: 600, color: "var(--text)" }}>{s.name}</td>
                    <td style={{ padding: "6px 8px", color: "var(--accent)", fontWeight: 700 }}>{etfName}</td>
                    <td style={{ padding: "6px 8px", color: chgColor(rs1m), fontWeight: 600 }}>
                      {rs1m != null ? `${rs1m > 0 ? "+" : ""}${rs1m?.toFixed(1)}%` : "—"}
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
                    <td style={{ padding: "6px 8px", color: "var(--text2)", fontSize: 10 }}>
                      {s.dist_from_200ma != null ? `${s.dist_from_200ma > 0 ? "+" : ""}${s.dist_from_200ma?.toFixed(1)}%` : "—"}
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
  const tabs = ["Market", "Longs", "EP", "Shorts", "All Stocks", "Pipeline", "Replay", "Correlation", "Watchlist"];

  return (
    <>
      <style>{CSS}</style>
      <div className="dash">

        {/* Header */}
        <div className="hdr">
          <div className="hdr-left">
            <span className="hdr-logo">SIGNAL DESK</span>
            <div>
              <div className="hdr-sub">MA BOUNCE · SHORT SETUP · MOMENTUM SCREENER</div>
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
            <span className="mkt-chip-label">MA10 BOUNCES</span>
            <span style={{ color: "var(--cyan)", fontWeight: 700 }}>{data.ma10Bounces.length}</span>
          </div>
          <div className="mkt-chip">
            <span className="mkt-chip-label">MA21 BOUNCES</span>
            <span style={{ color: "var(--purple)", fontWeight: 700 }}>{data.ma21Bounces.length}</span>
          </div>
          <div className="mkt-chip">
            <span className="mkt-chip-label">MA50 BOUNCES</span>
            <span style={{ color: "var(--yellow)", fontWeight: 700 }}>{data.ma50Bounces.length}</span>
          </div>
          <div className="mkt-chip">
            <span className="mkt-chip-label">TOP SHORTS</span>
            <span style={{ color: "var(--red)", fontWeight: 700 }}>{data.topShorts.length}</span>
          </div>
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
              {t === "Shorts" ? "▼ " : t === "Longs" ? "▲ " : t === "Market" ? "◈ " : t === "EP" ? "⚡ " : t === "Replay" ? "⏪ " : t === "Pipeline" ? "◎ " : t === "Correlation" ? "📊 " : t === "Watchlist" ? "📋 " : ""}{t}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="body">
          {tab === "Market" && <MarketTab data={data} />}
          {tab === "Longs" && <LongsTab data={data} onQuickAdd={onQuickAdd} />}
          {tab === "EP" && <EPTab data={data} onQuickAdd={onQuickAdd} />}
          {tab === "Shorts" && <ShortsTab data={data} />}
          {tab === "All Stocks" && <AllStocksTab data={data} />}
          {tab === "Pipeline" && <Pipeline />}
          {tab === "Replay" && <Replay />}
          {tab === "Correlation" && <Correlation />}
          {tab === "Watchlist" && <WatchlistTab />}
        </div>

      </div>
    </>
  );
}
