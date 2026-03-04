import RegimeGate from "./RegimeGate";
import React, { useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const C = {
  bg: "var(--bg)", bg2: "var(--bg2)", bg3: "var(--bg3)", bg4: "var(--bg4)",
  border: "var(--border)", border2: "var(--border2)",
  teal: "var(--cyan)", green: "var(--green)", amber: "var(--yellow)",
  red: "var(--red)", blue: "var(--cyan)", purple: "var(--purple)",
  text: "var(--text)", text2: "var(--text2)", text3: "var(--text3)",
};

const pr  = (v, d=2) => v == null ? "—" : `$${Number(v).toFixed(d)}`;
const pct = (v, d=1) => v == null ? "—" : `${Number(v).toFixed(d)}%`;
const num = (v, d=1) => v == null ? "—" : Number(v).toFixed(d);

const S = {
  page: {
    background: C.bg, minHeight: "100vh", color: C.text,
    fontFamily: "'Inter', -apple-system, sans-serif", fontSize: 12, padding: "0 0 60px",
  },
  header: {
    background: C.bg2, borderBottom: `1px solid ${C.border}`,
    padding: "14px 24px 12px", position: "sticky", top: 0, zIndex: 100,
  },
  label: { fontSize: 9, color: C.text3, letterSpacing: 2, textTransform: "uppercase", marginBottom: 3 },
  tag: col => ({
    fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 2,
    background: `${col}18`, color: col, border: `1px solid ${col}35`,
    letterSpacing: 1, textTransform: "uppercase", whiteSpace: "nowrap",
  }),
  btn: (col = C.teal, fill = false) => ({
    padding: "7px 16px", fontSize: 10, cursor: "pointer", borderRadius: 3,
    border: `1px solid ${col}`, background: fill ? col : "transparent",
    color: fill ? "#000" : col, fontFamily: "inherit", letterSpacing: 1,
    fontWeight: 700, textTransform: "uppercase", transition: "all 0.12s",
  }),
  input: {
    background: C.bg3, border: `1px solid ${C.border2}`, color: C.text,
    padding: "7px 10px", fontFamily: "inherit", fontSize: 11,
    borderRadius: 3, width: "100%", boxSizing: "border-box",
  },
};

// ── Core Stats color helpers ───────────────────────────────────────────────────
const adrCol = v => v == null ? C.text3 : (v >= 3.5 && v <= 8) ? "var(--green)" : v > 8 ? "var(--yellow)" : C.text3;
const adrBg  = v => v != null && v >= 3.5 && v <= 8 ? "rgba(8,153,129,0.08)" : "transparent";
const ema21Col = v => v == null ? C.text3 : v <= 5 ? "var(--green)" : v <= 8 ? "var(--yellow)" : "var(--red)";
const ema21Bg  = v => v == null ? "transparent" : v <= 5 ? "rgba(8,153,129,0.10)" : v <= 8 ? "rgba(245,166,35,0.10)" : "rgba(242,54,69,0.10)";
const ceilCol  = v => v == null ? C.text3 : v ? "var(--green)" : "var(--red)";
const ceilTxt  = v => v == null ? "—" : v ? "✓" : "✗";
const rsCol    = r => r >= 90 ? "var(--green)" : r >= 80 ? "#5aaa6a" : "var(--yellow)";
const rsBg     = r => r >= 90 ? "rgba(8,153,129,0.12)" : r >= 80 ? "rgba(8,153,129,0.07)" : "rgba(245,166,35,0.1)";

// ── Sub-components ─────────────────────────────────────────────────────────────

function StructureBadge({ structure }) {
  const map = {
    OTM_CALL:     { col: "var(--yellow)", label: "OTM CALL" },
    RATIO_SPREAD: { col: "var(--purple)", label: "RATIO 1:2" },
    CALL_SPREAD:  { col: C.teal,    label: "CALL SPREAD" },
    NAKED_CALL:   { col: "var(--yellow)", label: "NAKED CALL" },
  };
  const { col, label } = map[structure] || map.CALL_SPREAD;
  return <span style={S.tag(col)}>{label}</span>;
}

// ── Settings Panel ─────────────────────────────────────────────────────────────
function SettingsPanel({ settings, onChange }) {
  const field = (label, key, type = "number", props = {}) => (
    <div key={key} style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 120 }}>
      <div style={S.label}>{label}</div>
      <input
        type={type} value={settings[key]}
        onChange={e => onChange(prev => ({ ...prev, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
        style={S.input} {...props}
      />
    </div>
  );
  return (
    <div style={{
      background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 4,
      padding: "14px 16px", marginBottom: 16,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.teal, letterSpacing: 2, marginBottom: 12 }}>
        SETTINGS
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {field("Portfolio ($)", "portfolioValue", "number", { min: 1000, step: 5000 })}
        {field("Min Score",    "minScore",        "number", { min: 0, max: 10, step: 0.5 })}
        {field("Max Results",  "maxSuggestions",  "number", { min: 1, max: 20, step: 1 })}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 120 }}>
          <div style={S.label}>Source</div>
          <select value={settings.source}
            onChange={e => onChange(prev => ({ ...prev, source: e.target.value }))}
            style={{ ...S.input, cursor: "pointer" }}>
            <option value="both">Main + Micro</option>
            <option value="main">Main scan only</option>
            <option value="microcap">Micro cap only</option>
          </select>
        </div>
      </div>
    </div>
  );
}

// ── Regime Banner ──────────────────────────────────────────────────────────────
function RegimeBanner({ regime }) {
  if (!regime) return null;
  const { score, gate, vix, label } = regime;
  const cfg = {
    DANGER:  { bg: "rgba(242,54,69,0.1)",   bd: "var(--red)",    tx: "var(--red)",    icon: "🚨", msg: `Score ${score}/100 — very high long failure rate.` },
    WARN:    { bg: "rgba(245,166,35,0.08)", bd: "var(--yellow)", tx: "var(--yellow)", icon: "⚠️", msg: `Score ${score}/100 — market under pressure. Reduce size 50%.` },
    CAUTION: { bg: "rgba(245,166,35,0.06)", bd: "var(--yellow)", tx: "var(--yellow)", icon: "🟡", msg: `Score ${score}/100 — neutral market. Standard filters apply.` },
    GO:      { bg: "rgba(8,153,129,0.06)",  bd: "var(--green)",  tx: "var(--green)",  icon: "✅", msg: `Score ${score}/100 — confirmed uptrend. Full playbook active.` },
  }[gate] || { bg: "transparent", bd: C.border, tx: C.text3, icon: "—", msg: "" };

  return (
    <div style={{
      background: cfg.bg, border: `1px solid ${cfg.bd}50`,
      borderRadius: 4, padding: "8px 14px", marginBottom: 12,
      display: "flex", alignItems: "center", gap: 10,
    }}>
      <span style={{ fontSize: 14 }}>{cfg.icon}</span>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: cfg.tx }}>REGIME {gate}</span>
        <span style={{ fontSize: 10, color: C.text3 }}>{label}</span>
        {vix && <span style={{ fontSize: 10, color: C.text3 }}>VIX {typeof vix === "number" ? vix.toFixed(1) : vix}</span>}
        <span style={{ fontSize: 10, color: C.text2 }}>{cfg.msg}</span>
      </div>
    </div>
  );
}

// ── Skip Modal ─────────────────────────────────────────────────────────────────
const SKIP_REASONS = [
  { value: "regime_warn",     label: "Regime warning — market conditions unfavourable" },
  { value: "high_iv",         label: "IV too high — premium not worth it" },
  { value: "low_conviction",  label: "Low conviction — chart doesn't feel right" },
  { value: "poor_ev",         label: "EV too low / risk:reward insufficient" },
  { value: "position_limit",  label: "Already at max positions" },
  { value: "earnings_risk",   label: "Earnings too close" },
  { value: "sector_headwind", label: "Sector not cooperating" },
  { value: "other",           label: "Other" },
];

function SkipModal({ s, onConfirm, onCancel }) {
  const [reason, setReason] = React.useState("");
  const [note,   setNote]   = React.useState("");
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2000 }}>
      <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 6, padding: 24, width: 440, boxShadow: "0 8px 32px rgba(0,0,0,0.4)" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: C.teal, marginBottom: 12 }}>Skip — {s.ticker}</div>
        {SKIP_REASONS.map(r => (
          <label key={r.value} style={{
            display: "flex", gap: 8, alignItems: "center", padding: "4px 6px", borderRadius: 3, cursor: "pointer", marginBottom: 2,
            background: reason === r.value ? `${C.teal}15` : "transparent",
          }}>
            <input type="radio" name="skip" value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} style={{ accentColor: C.teal }} />
            <span style={{ fontSize: 11, color: reason === r.value ? C.teal : C.text2 }}>{r.label}</span>
          </label>
        ))}
        <textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note..."
          style={{ ...S.input, marginTop: 10, height: 56, resize: "vertical" }} />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
          <button onClick={onCancel} style={S.btn(C.text3)}>Cancel</button>
          <button onClick={() => reason && onConfirm({ skip_reason: reason, skip_note: note })}
            disabled={!reason} style={S.btn("var(--red)", !!reason)}>Log as Skipped</button>
        </div>
      </div>
    </div>
  );
}

// ── Expandable detail row ──────────────────────────────────────────────────────
function DetailRow({ s, onQuickAdd, onSkip, colCount }) {
  const [showSkip, setShowSkip] = useState(false);
  const sugg = s.suggestion || {};
  const sig  = s.signal_summary || {};
  const kw   = s.kelly_workings || {};
  const prob = s.probability || {};

  return (
    <tr style={{ background: "var(--bg2)" }}>
      <td colSpan={colCount} style={{ padding: "12px 16px", borderBottom: "2px solid var(--border)" }}>
        {showSkip && (
          <SkipModal s={s} onCancel={() => setShowSkip(false)}
            onConfirm={d => { onSkip && onSkip(s, d); setShowSkip(false); }} />
        )}
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 11 }}>
          {/* Trade */}
          <div style={{ minWidth: 200 }}>
            <div style={{ fontSize: 9, color: C.text3, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>TRADE</div>
            <div style={{ color: C.text, lineHeight: 1.6 }}>
              <div>Structure: <b style={{ color: C.teal }}>{sugg.structure}</b></div>
              <div>Long: <b>${sugg.long_strike || sugg.buy_strike || "?"}</b>
                {(sugg.short_strike || sugg.sell_strike) && <span> / Short: <b>${sugg.short_strike || sugg.sell_strike}</b></span>}
              </div>
              <div>Premium: <b>{pr(sugg.premium || sugg.net_debit)}</b></div>
              <div>Expiry: <b>{s.chain_expiry || s.expiry?.dte_label || "—"}</b></div>
              <div>IV: <b>{s.chain_iv ? `${(s.chain_iv * 100).toFixed(0)}%` : "—"}</b></div>
            </div>
          </div>
          {/* Kelly */}
          <div style={{ minWidth: 160 }}>
            <div style={{ fontSize: 9, color: C.text3, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>KELLY SIZING</div>
            <div style={{ color: C.text, lineHeight: 1.6 }}>
              <div>Full Kelly: <b style={{ color: C.teal }}>{kw.full_kelly}%</b></div>
              <div>Fractional (×0.25): <b style={{ color: C.teal }}>{kw.fractional_kelly}%</b></div>
              <div>Applied: <b style={{ color: "var(--green)" }}>{kw.applied_size}%</b></div>
              <div>Contracts: <b>{sugg.contracts || 1}</b> · Cost: <b>{pr(sugg.cost, 0)}</b></div>
            </div>
          </div>
          {/* Probability */}
          <div style={{ minWidth: 160 }}>
            <div style={{ fontSize: 9, color: C.text3, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>PROBABILITY</div>
            <div style={{ color: C.text, lineHeight: 1.6 }}>
              <div>Base rate: <b>{prob.base_rate != null ? `${Math.round(prob.base_rate * 100)}%` : "—"}</b></div>
              <div>Adjustments: <b style={{ color: (prob.adjustments || 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                {prob.adjustments != null ? `${prob.adjustments >= 0 ? "+" : ""}${Math.round(prob.adjustments * 100)}%` : "—"}
              </b></div>
              <div>Final P: <b style={{ color: C.teal }}>{prob.probability != null ? `${Math.round(prob.probability * 100)}%` : "—"}</b></div>
            </div>
          </div>
          {/* Targets */}
          <div style={{ minWidth: 140 }}>
            <div style={{ fontSize: 9, color: C.text3, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>TARGETS</div>
            <div style={{ color: C.text, lineHeight: 1.6 }}>
              <div>T1: <b style={{ color: "var(--green)" }}>{pr(sig.target_1)}</b></div>
              <div>Stop: <b style={{ color: "var(--red)" }}>{pr(sig.stop_price)}</b></div>
              <div>EMA21 Low: <b>{pr(sig.ema21_low)}</b></div>
              <div>52W High: <b>{pr(sig.w52_high)}</b></div>
            </div>
          </div>
          {/* Rationale */}
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 9, color: C.text3, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>RATIONALE</div>
            <div style={{ color: C.text2, lineHeight: 1.6, fontSize: 10 }}>{s.rationale}</div>
            {s.warning && (
              <div style={{ marginTop: 6, color: "var(--yellow)", fontSize: 9, lineHeight: 1.5 }}>⚠ {s.warning}</div>
            )}
          </div>
        </div>
        {/* Action buttons */}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {onQuickAdd && (
            <button onClick={() => onQuickAdd(s)} style={S.btn(C.teal, true)}>
              + Add to Journal
            </button>
          )}
          <button onClick={() => setShowSkip(true)} style={S.btn("var(--red)")}>
            Skip
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Table header ───────────────────────────────────────────────────────────────
const TH = ({ children, title, center, width, sortKey, sortBy, onSort }) => (
  <th title={title} onClick={() => sortKey && onSort && onSort(sortKey)} style={{
    padding: "6px 8px", fontSize: 9, fontWeight: 700, letterSpacing: 1,
    textTransform: "uppercase", color: sortBy === sortKey ? C.teal : C.text3,
    borderBottom: "2px solid var(--border)", whiteSpace: "nowrap",
    textAlign: center ? "center" : "left", width: width || "auto",
    background: C.bg2, position: "sticky", top: 0, zIndex: 1,
    cursor: sortKey ? "pointer" : "default",
  }}>
    {children}{sortBy === sortKey ? " ▼" : ""}
  </th>
);

const TD = ({ children, style = {} }) => (
  <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--border)", verticalAlign: "middle", ...style }}>
    {children}
  </td>
);

// ── Suggestion row ─────────────────────────────────────────────────────────────
function SuggestionRow({ s, rank, onQuickAdd, onSkip, regime }) {
  const [expanded, setExpanded] = useState(false);
  const COL_COUNT = 18;

  if (s.status !== "ok") {
    return (
      <tr style={{ opacity: 0.5 }}>
        <TD style={{ color: C.text3 }}>{rank}</TD>
        <TD><span style={{ fontWeight: 700, color: "var(--red)" }}>{s.ticker}</span></TD>
        <TD colSpan={COL_COUNT - 2} style={{ color: C.text3, fontSize: 10 }}>{s.error || s.status}</TD>
      </tr>
    );
  }

  const sugg = s.suggestion || {};
  const sig  = s.signal_summary || {};
  const prob = s.probability?.probability || 0;
  const evVal = sugg.ev || sugg.expected_value || 0;
  const prem  = sugg.premium || sugg.net_debit || 0;
  const struct = sugg.structure || "CALL_SPREAD";
  const longS  = sugg.long_strike  || sugg.buy_strike  || "?";
  const shortS = sugg.short_strike || sugg.sell_strike || null;

  const evCol = evVal > 0.5 ? "var(--green)" : evVal > 0 ? C.teal : "var(--red)";
  const probCol = prob >= 0.6 ? "var(--green)" : prob >= 0.45 ? C.teal : prob >= 0.35 ? "var(--yellow)" : "var(--red)";

  return (
    <>
      <tr
        onClick={() => setExpanded(e => !e)}
        style={{
          background: expanded ? "var(--bg2)" : s._skipped ? "rgba(242,54,69,0.04)" : "var(--bg)",
          cursor: "pointer", opacity: s._skipped ? 0.45 : 1,
        }}
        onMouseEnter={e => !expanded && (e.currentTarget.style.background = "var(--bg2)")}
        onMouseLeave={e => !expanded && (e.currentTarget.style.background = s._skipped ? "rgba(242,54,69,0.04)" : "var(--bg)")}
      >
        {/* # */}
        <TD style={{ color: C.text3, textAlign: "right", width: 24 }}>{rank}</TD>

        {/* Ticker */}
        <TD>
          <a href={`https://www.tradingview.com/chart/?symbol=${s.ticker}`}
            target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
            style={{ fontWeight: 700, fontSize: 13, color: "var(--accent)", textDecoration: "none" }}>
            {s.ticker} <span style={{ fontSize: 9, opacity: 0.5 }}>↗</span>
          </a>
          <div style={{ fontSize: 9, color: C.text3, marginTop: 1 }}>{sig.sector}</div>
        </TD>

        {/* Score */}
        <TD style={{ textAlign: "center" }}>
          <span style={{
            fontWeight: 700, fontSize: 12,
            color: s.score >= 8 ? "var(--green)" : s.score >= 6.5 ? C.teal : "var(--yellow)",
          }}>{s.score?.toFixed(1)}</span>
        </TD>

        {/* Price */}
        <TD>
          <div style={{ fontWeight: 600, color: C.text }}>{pr(sig.price)}</div>
        </TD>

        {/* RS */}
        <TD style={{ textAlign: "center" }}>
          <span style={{
            padding: "2px 6px", borderRadius: 3, fontSize: 10, fontWeight: 700,
            color: rsCol(sig.rs), background: rsBg(sig.rs), border: `1px solid ${rsCol(sig.rs)}44`,
          }}>{sig.rs || "—"}</span>
        </TD>

        {/* Structure */}
        <TD style={{ textAlign: "center" }}>
          <StructureBadge structure={struct} />
        </TD>

        {/* Strike */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontWeight: 600, color: C.text }}>
            ${longS}{shortS ? <span style={{ color: C.text3 }}> / ${shortS}</span> : null}
          </span>
        </TD>

        {/* Premium */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ color: C.text }}>{pr(prem)}</span>
        </TD>

        {/* EV */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontWeight: 700, color: evCol }}>
            {evVal >= 0 ? "+" : ""}${Number(evVal).toFixed(2)}
          </span>
        </TD>

        {/* P(win) */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontWeight: 600, color: probCol }}>{Math.round(prob * 100)}%</span>
        </TD>

        {/* Size % */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ color: C.teal, fontWeight: 600 }}>
            {s.kelly_workings?.applied_size?.toFixed(1) || "—"}%
          </span>
        </TD>

        {/* ── CORE STATS ── */}

        {/* ADR % */}
        <TD style={{ textAlign: "center" }}>
          <span style={{
            fontSize: 11, fontWeight: 600, color: adrCol(sig.adr_pct),
            background: adrBg(sig.adr_pct), padding: "1px 5px", borderRadius: 3,
          }} title="ADR% — target 3.5–8%">
            {sig.adr_pct != null ? `${num(sig.adr_pct)}%` : "—"}
          </span>
        </TD>

        {/* EMA21 Low */}
        <TD style={{ textAlign: "center" }}>
          <div style={{ fontSize: 11, color: C.text2 }}>{pr(sig.ema21_low)}</div>
        </TD>

        {/* Risk % (EMA21 Low %) */}
        <TD style={{ textAlign: "center" }}>
          <span style={{
            fontSize: 11, fontWeight: 700, color: ema21Col(sig.ema21_low_pct),
            background: ema21Bg(sig.ema21_low_pct), padding: "2px 6px", borderRadius: 3,
          }} title="Distance price→EMA21 Low. <5% low risk, >8% no entry">
            {sig.ema21_low_pct != null ? `${num(sig.ema21_low_pct)}%` : "—"}
          </span>
        </TD>

        {/* ATR 21 EMA ceiling */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontSize: 13, color: ceilCol(sig.within_1atr_ema21) }}
            title="Within 1×ATR of EMA21">{ceilTxt(sig.within_1atr_ema21)}</span>
        </TD>

        {/* ATR 10 WMA ceiling */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontSize: 13, color: ceilCol(sig.within_1atr_wema10) }}
            title="Within 1×ATR of weekly EMA10">{ceilTxt(sig.within_1atr_wema10)}</span>
        </TD>

        {/* ATR 50 SMA ceiling */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontSize: 13, color: ceilCol(sig.within_3atr_sma50) }}
            title="Within 3×ATR of SMA50">{ceilTxt(sig.within_3atr_sma50)}</span>
        </TD>

        {/* 3-Weeks Tight */}
        <TD style={{ textAlign: "center" }}>
          <span style={{ fontSize: 13, color: sig.three_weeks_tight ? "var(--green)" : C.text3 }}
            title="3-Weeks Tight">
            {sig.three_weeks_tight ? "✓" : "·"}
          </span>
        </TD>

        {/* VCS */}
        <TD style={{ textAlign: "center" }}>
          <span style={{
            fontWeight: 600, fontSize: 11,
            color: sig.vcs == null ? C.text3 : sig.vcs <= 3 ? "var(--green)" : sig.vcs <= 5 ? "var(--yellow)" : C.text3,
          }}>{sig.vcs != null ? num(sig.vcs) : "—"}</span>
        </TD>

        {/* Expand */}
        <TD style={{ textAlign: "center", color: C.text3, fontSize: 10 }}>
          {expanded ? "▲" : "▼"}
        </TD>
      </tr>

      {expanded && (
        <DetailRow s={s} onQuickAdd={onQuickAdd} onSkip={onSkip} colCount={COL_COUNT + 1} />
      )}
    </>
  );
}

// ── Summary strip ──────────────────────────────────────────────────────────────
function SummaryStrip({ suggestions }) {
  const valid = suggestions.filter(s => s.status === "ok");
  const totalCost = valid.reduce((sum, s) => {
    const sugg = s.suggestion || {};
    return sum + (sugg.contracts || 1) * (sugg.premium || sugg.net_debit || 0) * 100;
  }, 0);
  const avgEv = valid.length
    ? valid.reduce((sum, s) => sum + (s.suggestion?.ev || 0), 0) / valid.length : 0;
  const validEntry = valid.filter(s => {
    const sig = s.signal_summary || {};
    return sig.adr_pct >= 3.5 && sig.adr_pct <= 8 && sig.ema21_low_pct <= 8;
  }).length;

  return (
    <div style={{
      display: "flex", gap: 20, padding: "8px 14px", background: C.bg3,
      borderRadius: 3, border: `1px solid ${C.border}`, marginBottom: 12,
      fontSize: 10, color: C.text3, flexWrap: "wrap", alignItems: "center",
    }}>
      <span>Suggestions: <b style={{ color: C.teal }}>{valid.length}</b></span>
      <span>✓ Valid Entry: <b style={{ color: "var(--green)" }}>{validEntry}</b></span>
      <span>Total outlay: <b style={{ color: "var(--yellow)" }}>${totalCost.toFixed(0)}</b></span>
      <span>Avg EV: <b style={{ color: avgEv >= 0 ? "var(--green)" : "var(--red)" }}>{avgEv >= 0 ? "+" : ""}${avgEv.toFixed(2)}</b></span>
      <span style={{ marginLeft: "auto", fontSize: 9 }}>Click row to expand · Core Stats: ADR% · Risk% · Ceiling ✓/✗</span>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function SuggestedTrades({ onQuickAdd }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);
  const [settings,    setSettings]    = useState({
    portfolioValue: 50000, minScore: 7.0, maxSuggestions: 10, source: "both",
  });
  const [sortBy,       setSortBy]       = useState("ev");
  const [showSettings, setShowSettings] = useState(true);
  const [regime,       setRegime]       = useState(null);

  const generate = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/suggest-batch`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: settings.source, portfolio_value: settings.portfolioValue,
          min_score: settings.minScore, max_suggestions: settings.maxSuggestions,
        }),
      });
      if (!res.ok) { const j = await res.json(); setError(j.detail || "Request failed"); return; }
      const data = await res.json();
      setSuggestions(data.suggestions || []);
      if (data.regime) setRegime(data.regime);
      setShowSettings(false);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [settings]);

  const handleSkip = async (s, skipData) => {
    const sugg = s.suggestion || {};
    const sig  = s.signal_summary || {};
    try {
      await fetch(`${API}/api/journal`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: s.ticker, added_date: new Date().toISOString().slice(0, 10),
          signal_type: sig.ma_bounce || "MA_BOUNCE", entry_price: sig.price,
          vcs: sig.vcs, rs: sig.rs, sector: sig.sector, status: "skipped",
          notes: `Skipped: ${sugg.structure || ""} EV $${(sugg.ev || 0).toFixed(2)}`,
          skip_reason: skipData.skip_reason, skip_note: skipData.skip_note,
          suggestion_score: s.score, suggestion_ev: sugg.ev,
          suggestion_structure: sugg.structure,
          regime_score: regime?.score || s.regime_score,
          iv_note: s.chain_iv ? `IV ${(s.chain_iv * 100).toFixed(0)}%` : "",
          target_1: sugg.close_target || sig.target_1, stop_price: sig.stop_price,
        }),
      });
      setSuggestions(prev => prev.map(x => x.ticker === s.ticker ? { ...x, _skipped: true } : x));
    } catch (e) { console.error("Skip log failed:", e); }
  };

  const sorted = [...suggestions].sort((a, b) => {
    if (a.status !== "ok") return 1;
    if (b.status !== "ok") return -1;
    if (sortBy === "ev")    return (b.suggestion?.ev || 0) - (a.suggestion?.ev || 0);
    if (sortBy === "score") return (b.score || 0) - (a.score || 0);
    if (sortBy === "prob")  return (b.probability?.probability || 0) - (a.probability?.probability || 0);
    if (sortBy === "size")  return (b.kelly_workings?.applied_size || 0) - (a.kelly_workings?.applied_size || 0);
    if (sortBy === "risk")  return (a.signal_summary?.ema21_low_pct || 99) - (b.signal_summary?.ema21_low_pct || 99);
    return 0;
  });

  const valid = suggestions.filter(s => s.status === "ok");
  const COL_COUNT = 19;

  const sortBtn = (key, label) => (
    <button key={key} onClick={() => setSortBy(key)} style={{
      padding: "3px 8px", fontSize: 10, cursor: "pointer", borderRadius: 3,
      border: `1px solid ${sortBy === key ? C.teal : C.border}`,
      background: sortBy === key ? `${C.teal}15` : "transparent",
      color: sortBy === key ? C.teal : C.text3, fontFamily: "inherit",
    }}>{label}</button>
  );

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span style={{ fontSize: 11, color: C.teal, letterSpacing: 3, fontWeight: 700, textTransform: "uppercase" }}>
              Suggested Trades
            </span>
            <span style={{ fontSize: 9, color: C.text3, marginLeft: 10 }}>
              Options spreads · Signal-driven · Kelly-sized
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={S.btn(C.text3)} onClick={() => setShowSettings(s => !s)}>⚙ Settings</button>
            <button style={S.btn(C.teal, true)} onClick={generate} disabled={loading}>
              {loading ? "Generating..." : "▶ Generate"}
            </button>
          </div>
        </div>
      </div>

      <div style={{ padding: "14px 20px" }}>
        {showSettings && <SettingsPanel settings={settings} onChange={setSettings} />}

        {suggestions.length > 0 && <RegimeBanner regime={regime} />}

        {!loading && suggestions.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: "50px 20px", color: C.text3 }}>
            <div style={{ fontSize: 38, marginBottom: 14 }}>⚡</div>
            <div style={{ fontSize: 14, color: C.teal, marginBottom: 8, fontWeight: 700 }}>Options Spread Suggestion Engine</div>
            <div style={{ fontSize: 11, color: C.text3, maxWidth: 440, margin: "0 auto 20px", lineHeight: 1.8 }}>
              Pulls top signals from your scan, estimates P(win) from RS + VCS + sector alignment,
              then selects the optimal structure with Kelly sizing.
            </div>
            <button style={S.btn(C.teal, true)} onClick={generate}>▶ Generate Suggestions</button>
          </div>
        )}

        {loading && (
          <div style={{ textAlign: "center", padding: "40px 0", color: C.text3 }}>
            <div style={{ marginBottom: 6 }}>Fetching live options chains...</div>
            <div style={{ fontSize: 10 }}>Takes 10–30s depending on signal count.</div>
          </div>
        )}

        {error && !loading && (
          <div style={{
            color: "var(--yellow)", background: "rgba(245,166,35,0.08)",
            border: "1px solid rgba(245,166,35,0.3)", borderRadius: 3, padding: "10px 14px", marginBottom: 12,
          }}>⚠ {error}</div>
        )}

        {valid.length > 0 && !loading && (
          <>
            <SummaryStrip suggestions={suggestions} />

            {/* Sort controls */}
            <div style={{ display: "flex", gap: 4, marginBottom: 10, alignItems: "center" }}>
              <span style={{ fontSize: 9, color: C.text3, marginRight: 4, letterSpacing: 1 }}>SORT</span>
              {sortBtn("ev", "Best EV")}
              {sortBtn("score", "Score")}
              {sortBtn("prob", "P(win)")}
              {sortBtn("risk", "Risk %")}
              {sortBtn("size", "Size")}
            </div>

            {/* Legend */}
            <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 9, color: C.text3, flexWrap: "wrap" }}>
              <span><b style={{ color: "var(--green)" }}>ADR%</b> 3.5–8% ideal</span>
              <span><b style={{ color: "var(--green)" }}>Risk%</b> &lt;5% low · &gt;8% no entry</span>
              <span><b>ATR/21 · ATR/W10 · ATR/50</b> ✓ = within ceiling</span>
              <span><b style={{ color: "var(--green)" }}>3WT</b> = 3-Weeks Tight</span>
            </div>

            {/* Table */}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr>
                    <TH width={24}>#</TH>
                    <TH width={100}>Ticker</TH>
                    <TH center width={44} sortKey="score" sortBy={sortBy} onSort={setSortBy} title="Signal score">Scr</TH>
                    <TH width={72}>Price</TH>
                    <TH center width={48} title="Relative Strength">RS</TH>
                    <TH center width={90} title="Options structure">Structure</TH>
                    <TH center width={100} title="Long / Short strike">Strike</TH>
                    <TH center width={60} title="Net debit / premium">Prem</TH>
                    <TH center width={64} sortKey="ev" sortBy={sortBy} onSort={setSortBy} title="Expected value per contract">EV</TH>
                    <TH center width={52} sortKey="prob" sortBy={sortBy} onSort={setSortBy} title="Probability of reaching T1">P(win)</TH>
                    <TH center width={52} sortKey="size" sortBy={sortBy} onSort={setSortBy} title="Kelly position size">Size%</TH>
                    {/* Core Stats */}
                    <TH center width={56} title="Average Daily Range % — target 3.5–8%">ADR%</TH>
                    <TH center width={72} title="EMA21 Low — stop anchor">EMA21 L</TH>
                    <TH center width={56} sortKey="risk" sortBy={sortBy} onSort={setSortBy} title="Distance price→EMA21 Low. <5% low risk, >8% no entry">Risk%</TH>
                    <TH center width={44} title="Within 1×ATR of EMA21">ATR/21</TH>
                    <TH center width={44} title="Within 1×ATR of weekly EMA10">ATR/W10</TH>
                    <TH center width={44} title="Within 3×ATR of SMA50">ATR/50</TH>
                    <TH center width={36} title="3-Weeks Tight">3WT</TH>
                    <TH center width={36} title="VCS — lower is tighter">VCS</TH>
                    <TH center width={28}></TH>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((s, i) => (
                    <SuggestionRow
                      key={s.ticker || i} s={s} rank={i + 1}
                      onQuickAdd={onQuickAdd} onSkip={handleSkip} regime={regime}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
