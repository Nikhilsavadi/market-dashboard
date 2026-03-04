import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const pr   = (v, dp = 2) => v == null ? "—" : `$${Number(v).toFixed(dp)}`;
const pct  = (v, dp = 1) => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(dp)}%`;
const chgC = (v) => v == null ? "var(--text3)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text3)";

const S = {
  page:    { fontFamily: "'Inter', sans-serif", fontSize: 12, color: "var(--text)", padding: "16px 16px 40px", background: "var(--bg)", minHeight: "100vh" },
  title:   { fontSize: 18, fontFamily: "'Inter', sans-serif", color: "var(--text)", margin: "0 0 4px" },
  sub:     { fontSize: 11, color: "var(--text3)", margin: "0 0 16px" },
  card:    { background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 14px", marginBottom: 8 },
  label:   { fontSize: 9, color: "var(--text3)", letterSpacing: 1, textTransform: "uppercase" },
  val:     { fontSize: 12, color: "var(--text)", fontWeight: 600 },
  btn:     (col="var(--accent)") => ({
    padding: "5px 12px", fontSize: 10, cursor: "pointer", borderRadius: 3,
    border: `1px solid ${col}`, background: "transparent", color: col,
    fontFamily: "inherit", letterSpacing: 0.5,
  }),
  btnFill: (col="var(--accent)") => ({
    padding: "5px 12px", fontSize: 10, cursor: "pointer", borderRadius: 3,
    border: `1px solid ${col}`, background: col, color: "#fff",
    fontFamily: "inherit", letterSpacing: 0.5,
  }),
  input: {
    padding: "5px 8px", fontSize: 11, background: "var(--bg3)",
    border: "1px solid var(--border)", borderRadius: 3, color: "var(--text)",
    fontFamily: "inherit", width: "100%", boxSizing: "border-box",
  },
  row: { display: "flex", gap: 12, marginBottom: 10 },
  field: { flex: 1 },
};

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    watching: { col: "var(--yellow)", bg: "rgba(245,166,35,0.1)",   label: "WATCHING" },
    open:     { col: "var(--green)", bg: "rgba(45,122,58,0.1)",    label: "OPEN"     },
    closed:   { col: "var(--text3)", bg: "rgba(122,74,42,0.08)",   label: "CLOSED"   },
    stopped:  { col: "var(--red)", bg: "rgba(242,54,69,0.08)",    label: "STOPPED"  },
    skipped:  { col: "var(--text3)", bg: "rgba(41,98,255,0.06)",    label: "SKIPPED"  },
  };
  const { col, bg, label } = map[status] || map.watching;
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
      background: bg, color: col, border: `1px solid ${col}44`, letterSpacing: 1,
    }}>
      {label}
    </span>
  );
}

// ── Add / Edit form modal ─────────────────────────────────────────────────────
function JournalForm({ prefill = {}, onSave, onCancel, isEdit = false }) {
  const [form, setForm] = useState({
    ticker:        prefill.ticker       || "",
    signal_type:   prefill.signal_type  || "MA21",
    entry_price:   prefill.entry_price  || prefill.price || "",
    stop_price:    prefill.stop_price   || "",
    target_1:      prefill.target_1     || "",
    target_2:      prefill.target_2     || "",
    target_3:      prefill.target_3     || "",
    vcs:           prefill.vcs          || "",
    rs:            prefill.rs           || "",
    sector:        prefill.sector       || "",
    notes:         prefill.notes        || "",
    status:        prefill.status       || "watching",
    // Pre-trade prompt fields
    thesis:        prefill.thesis        || "",
    invalidation:  prefill.invalidation  || "",
    exit_plan:     prefill.exit_plan     || "",
    confidence:    prefill.confidence    || "3",
    regime_score:  prefill.regime_score  || "",
    iv_note:       prefill.iv_note       || "",
  });

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  // Auto-fill regime score on mount (fetch live gate)
  useEffect(() => {
    if (form.regime_score) return; // already prefilled
    const API = process.env.REACT_APP_API_URL || "";
    fetch(`${API}/api/regime/gate`)
      .then(r => r.json())
      .then(d => {
        const note = d.gate && d.score
          ? `${d.gate} (${d.score}/100)${d.vix ? " · VIX " + d.vix.toFixed(1) : ""}`
          : "";
        setForm(f => ({
          ...f,
          regime_score: d.score || f.regime_score,
          iv_note: f.iv_note || (d.vix_warning ? d.vix_warning : (d.vix ? `VIX ${d.vix.toFixed(1)} — ${d.vix_label || ""}` : "")),
        }));
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!form.ticker || !form.entry_price) return;
    const payload = {
      ...form,
      entry_price:  parseFloat(form.entry_price)  || null,
      stop_price:   parseFloat(form.stop_price)   || null,
      target_1:     parseFloat(form.target_1)     || null,
      target_2:     parseFloat(form.target_2)     || null,
      target_3:     parseFloat(form.target_3)     || null,
      vcs:          parseFloat(form.vcs)          || null,
      rs:           parseInt(form.rs)             || null,
      confidence:   parseInt(form.confidence)     || 3,
      regime_score: parseFloat(form.regime_score) || null,
      added_date:   new Date().toISOString().slice(0, 10),
    };
    await onSave(payload);
  };

  const inputRow = (label, key, type = "text", placeholder = "") => (
    <div style={S.field}>
      <div style={{ ...S.label, marginBottom: 3 }}>{label}</div>
      <input
        type={type} style={S.input}
        value={form[key]} onChange={set(key)}
        placeholder={placeholder}
      />
    </div>
  );

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(19,23,34,0.5)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div style={{
        background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8,
        padding: 24, width: 560, maxHeight: "90vh", overflowY: "auto",
        boxShadow: "0 8px 32px rgba(19,23,34,0.15)",
      }}>
        <h3 style={{ ...S.title, fontSize: 16, marginBottom: 16 }}>
          {isEdit ? "Edit Position" : "Add to Journal"}
        </h3>

        <div style={S.row}>
          {inputRow("TICKER", "ticker", "text", "e.g. NVDA")}
          <div style={S.field}>
            <div style={{ ...S.label, marginBottom: 3 }}>SIGNAL TYPE</div>
            <select value={form.signal_type} onChange={set("signal_type")} style={S.input}>
              <option>MA10</option><option>MA21</option><option>MA50</option>
              <option>BREAKOUT</option><option>VCP</option><option>MANUAL</option>
            </select>
          </div>
          <div style={S.field}>
            <div style={{ ...S.label, marginBottom: 3 }}>STATUS</div>
            <select value={form.status} onChange={set("status")} style={S.input}>
              <option value="watching">Watching</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="skipped">Skipped</option>
            </select>
          </div>
        </div>

        <div style={S.row}>
          {inputRow("ENTRY PRICE", "entry_price", "number", "0.00")}
          {inputRow("STOP PRICE", "stop_price", "number", "0.00")}
        </div>
        <div style={S.row}>
          {inputRow("TARGET 1", "target_1", "number", "0.00")}
          {inputRow("TARGET 2", "target_2", "number", "0.00")}
          {inputRow("TARGET 3", "target_3", "number", "0.00")}
        </div>
        <div style={S.row}>
          {inputRow("VCS", "vcs", "number", "e.g. 2.5")}
          {inputRow("RS RANK", "rs", "number", "e.g. 92")}
          {inputRow("SECTOR", "sector", "text", "e.g. Technology")}
        </div>
        {/* ── Pre-trade prompt ── */}
        <div style={{
          background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
          padding: "14px 16px", marginBottom: 14,
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text3)", letterSpacing: 1, marginBottom: 12 }}>
            PRE-TRADE CHECKLIST
          </div>

          {/* Thesis */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ ...S.label, marginBottom: 3 }}>
              THESIS <span style={{ color: "var(--red)", fontWeight: 400 }}>*</span>
              <span style={{ fontWeight: 400, color: "var(--text3)", marginLeft: 4 }}>— one sentence, why this trade</span>
            </div>
            <textarea
              value={form.thesis} onChange={set("thesis")}
              placeholder="e.g. MA21 bounce with RS 91 in leading sector, vol 2.3x confirming demand"
              style={{ ...S.input, height: 52, resize: "vertical" }}
            />
          </div>

          {/* Invalidation */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ ...S.label, marginBottom: 3 }}>
              WHAT INVALIDATES THIS TRADE
              <span style={{ fontWeight: 400, color: "var(--text3)", marginLeft: 4 }}>— what would make you exit immediately</span>
            </div>
            <textarea
              value={form.invalidation} onChange={set("invalidation")}
              placeholder="e.g. Close below MA21, or vol dries up without follow-through within 3 days"
              style={{ ...S.input, height: 52, resize: "vertical" }}
            />
          </div>

          {/* Exit plan */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ ...S.label, marginBottom: 3 }}>
              EXIT PLAN
              <span style={{ fontWeight: 400, color: "var(--text3)", marginLeft: 4 }}>— target + time stop</span>
            </div>
            <textarea
              value={form.exit_plan} onChange={set("exit_plan")}
              placeholder="e.g. Sell at T1 ($142). If no move in 10 trading days, exit regardless."
              style={{ ...S.input, height: 52, resize: "vertical" }}
            />
          </div>

          {/* Confidence + auto-filled context */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div>
              <div style={{ ...S.label, marginBottom: 3 }}>CONFIDENCE 1-5</div>
              <select value={form.confidence} onChange={set("confidence")} style={S.input}>
                <option value="1">1 — Low conviction</option>
                <option value="2">2 — Below average</option>
                <option value="3">3 — Neutral</option>
                <option value="4">4 — High conviction</option>
                <option value="5">5 — Maximum conviction</option>
              </select>
            </div>
            <div>
              <div style={{ ...S.label, marginBottom: 3 }}>REGIME SCORE</div>
              <input type="number" style={S.input} value={form.regime_score}
                onChange={set("regime_score")} placeholder="auto-filled" />
            </div>
            <div>
              <div style={{ ...S.label, marginBottom: 3 }}>IV NOTE</div>
              <input type="text" style={S.input} value={form.iv_note}
                onChange={set("iv_note")} placeholder="e.g. IV 38%, normal" />
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ ...S.label, marginBottom: 3 }}>NOTES</div>
          <textarea
            value={form.notes} onChange={set("notes")}
            placeholder="Anything else — catalyst, chart pattern, concerns..."
            style={{ ...S.input, height: 52, resize: "vertical" }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn()} onClick={onCancel}>Cancel</button>
          <button style={S.btnFill()} onClick={handleSave}>
            {isEdit ? "Save Changes" : "Add to Journal"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Close position form ───────────────────────────────────────────────────────
function CloseForm({ entry, onClose, onCancel }) {
  const [exitPrice, setExitPrice] = useState("");
  const [reason, setReason]       = useState("target");

  const pnl = exitPrice && entry.entry_price
    ? ((parseFloat(exitPrice) - entry.entry_price) / entry.entry_price * 100).toFixed(1)
    : null;

  const handleClose = () => {
    if (!exitPrice) return;
    onClose({
      exit_price:  parseFloat(exitPrice),
      exit_reason: reason,
      exit_date:   new Date().toISOString().slice(0, 10),
      pnl_pct:     pnl ? parseFloat(pnl) : null,
      status:      reason === "stop" ? "stopped" : "closed",
    });
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(19,23,34,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 24, width: 360, boxShadow: "0 8px 32px rgba(19,23,34,0.15)" }}>
        <h3 style={{ ...S.title, fontSize: 16, marginBottom: 4 }}>Close {entry.ticker}</h3>
        <p style={{ fontSize: 11, color: "var(--text3)", marginBottom: 16 }}>Entry: {pr(entry.entry_price)} · Stop: {pr(entry.stop_price)}</p>

        <div style={{ marginBottom: 10 }}>
          <div style={{ ...S.label, marginBottom: 3 }}>EXIT PRICE</div>
          <input type="number" value={exitPrice} onChange={e => setExitPrice(e.target.value)}
            placeholder="0.00" style={S.input} autoFocus />
          {pnl && (
            <div style={{ fontSize: 11, color: chgC(parseFloat(pnl)), marginTop: 4, fontWeight: 600 }}>
              P&L: {pnl >= 0 ? "+" : ""}{pnl}%
            </div>
          )}
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ ...S.label, marginBottom: 3 }}>EXIT REASON</div>
          <select value={reason} onChange={e => setReason(e.target.value)} style={S.input}>
            <option value="target">Hit target</option>
            <option value="stop">Stop hit</option>
            <option value="manual">Manual exit</option>
            <option value="trailing">Trailing stop</option>
            <option value="earnings">Earnings approaching</option>
          </select>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn()} onClick={onCancel}>Cancel</button>
          <button style={S.btnFill(reason === "stop" ? "var(--red)" : "var(--green)")} onClick={handleClose}>
            Close Position
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Journal entry card ────────────────────────────────────────────────────────
function JournalCard({ entry, onEdit, onClose, onDelete, currentPrices }) {
  const [expanded, setExpanded] = useState(false);

  const currentPrice = currentPrices?.[entry.ticker];
  const pnlLive = currentPrice && entry.entry_price
    ? ((currentPrice - entry.entry_price) / entry.entry_price * 100)
    : null;
  const finalPnl = entry.pnl_pct ?? pnlLive;

  const isOpen    = entry.status === "open";
  const isWatching = entry.status === "watching";
  const isClosed  = ["closed", "stopped"].includes(entry.status);

  return (
    <div style={{
      ...S.card,
      borderLeft: `3px solid ${isOpen ? "var(--green)" : isWatching ? "var(--yellow)" : isClosed && finalPnl > 0 ? "var(--green)" : "var(--red)"}`,
    }}>
      {/* Main row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }} onClick={() => setExpanded(!expanded)}>
        <StatusBadge status={entry.status} />

        <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", minWidth: 70 }}>
          {entry.ticker}
        </span>

        <span style={{ fontSize: 10, color: "var(--accent)", minWidth: 60 }}>
          {entry.signal_type}
        </span>

        <span style={{ fontSize: 11, color: "var(--text3)", minWidth: 80 }}>
          Entry {pr(entry.entry_price)}
        </span>

        {currentPrice && isOpen && (
          <span style={{ fontSize: 11, color: "var(--text3)" }}>
            Now {pr(currentPrice)}
          </span>
        )}

        {finalPnl != null && (
          <span style={{ fontSize: 12, fontWeight: 700, color: chgC(finalPnl), minWidth: 60 }}>
            {pct(finalPnl)}
          </span>
        )}

        <span style={{ fontSize: 9, color: "var(--text3)", marginLeft: "auto" }}>
          {entry.added_date}
        </span>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 4 }} onClick={e => e.stopPropagation()}>
          {!isClosed && (
            <>
              <button style={S.btn("var(--text3)")} onClick={() => onEdit(entry)}>Edit</button>
              {isOpen && (
                <button style={S.btnFill("var(--green)")} onClick={() => onClose(entry)}>Close</button>
              )}
              {isWatching && (
                <button style={S.btnFill()} onClick={() => onEdit({ ...entry, status: "open" })}>Open</button>
              )}
            </>
          )}
          <button style={S.btn("var(--red)")} onClick={() => onDelete(entry.id)}>✕</button>
        </div>

        <span style={{ fontSize: 10, color: "var(--text3)" }}>{expanded ? "▲" : "▼"}</span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 8 }}>
            {[
              ["Stop",     pr(entry.stop_price)],
              ["T1",       pr(entry.target_1)],
              ["T2",       pr(entry.target_2)],
              ["T3",       pr(entry.target_3)],
              ["VCS",      entry.vcs ?? "—"],
              ["RS",       entry.rs ?? "—"],
              ["Sector",   entry.sector ?? "—"],
              ["Score",    entry.signal_score ? `${entry.signal_score}/10` : "—"],
            ].map(([label, val]) => (
              <div key={label}>
                <div style={S.label}>{label}</div>
                <div style={S.val}>{val}</div>
              </div>
            ))}
          </div>

          {/* P&L vs targets */}
          {entry.entry_price && entry.target_1 && (
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              {[
                ["T1", entry.target_1],
                ["T2", entry.target_2],
                ["T3", entry.target_3],
              ].filter(([, t]) => t).map(([label, target]) => {
                const r = ((target - entry.entry_price) / entry.entry_price * 100).toFixed(1);
                return (
                  <div key={label} style={{
                    padding: "3px 8px", borderRadius: 3, background: "rgba(8,153,129,0.08)",
                    border: "1px solid rgba(8,153,129,0.2)",
                  }}>
                    <span style={{ fontSize: 9, color: "var(--text3)" }}>{label} </span>
                    <span style={{ fontSize: 11, color: "var(--green)", fontWeight: 600 }}>+{r}%</span>
                  </div>
                );
              })}
              {entry.stop_price && (
                <div style={{ padding: "3px 8px", borderRadius: 3, background: "rgba(242,54,69,0.08)", border: "1px solid rgba(196,58,42,0.2)" }}>
                  <span style={{ fontSize: 9, color: "var(--text3)" }}>Stop </span>
                  <span style={{ fontSize: 11, color: "var(--red)", fontWeight: 600 }}>
                    {((entry.stop_price - entry.entry_price) / entry.entry_price * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Pre-trade prompt display */}
          {(entry.thesis || entry.invalidation || entry.exit_plan) && (
            <div style={{
              background: "var(--bg2)", border: "1px solid var(--border)",
              borderRadius: 4, padding: "8px 10px", marginTop: 6,
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text3)", letterSpacing: 1, marginBottom: 6 }}>
                PRE-TRADE CHECKLIST
                {entry.confidence && (
                  <span style={{
                    marginLeft: 8, fontWeight: 400, color: "var(--text3)",
                  }}>Confidence: {"★".repeat(parseInt(entry.confidence))}{"☆".repeat(5 - parseInt(entry.confidence))}</span>
                )}
                {entry.regime_score && (
                  <span style={{
                    marginLeft: 8, fontWeight: 400, color: entry.regime_score >= 65 ? "var(--green)" : entry.regime_score >= 50 ? "var(--yellow)" : "var(--red)",
                  }}>Regime: {entry.regime_score}</span>
                )}
                {entry.iv_note && (
                  <span style={{ marginLeft: 8, fontWeight: 400, color: "var(--text3)" }}>IV: {entry.iv_note}</span>
                )}
              </div>
              {entry.thesis && (
                <div style={{ marginBottom: 5 }}>
                  <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text3)" }}>THESIS: </span>
                  <span style={{ fontSize: 11, color: "var(--text2)" }}>{entry.thesis}</span>
                </div>
              )}
              {entry.invalidation && (
                <div style={{ marginBottom: 5 }}>
                  <span style={{ fontSize: 9, fontWeight: 700, color: "var(--red)" }}>INVALIDATION: </span>
                  <span style={{ fontSize: 11, color: "var(--text2)" }}>{entry.invalidation}</span>
                </div>
              )}
              {entry.exit_plan && (
                <div>
                  <span style={{ fontSize: 9, fontWeight: 700, color: "var(--green)" }}>EXIT PLAN: </span>
                  <span style={{ fontSize: 11, color: "var(--text2)" }}>{entry.exit_plan}</span>
                </div>
              )}
            </div>
          )}

          {entry.notes && (
            <div style={{ fontSize: 11, color: "var(--text3)", background: "var(--bg3)", padding: "6px 8px", borderRadius: 3, marginTop: 4 }}>
              {entry.notes}
            </div>
          )}

          {/* Skip info */}
          {entry.status === "skipped" && (
            <div style={{ marginTop: 6, background: "rgba(41,98,255,0.05)", border: "1px solid rgba(41,98,255,0.15)", borderRadius: 3, padding: "6px 8px" }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text3)", letterSpacing: 1, marginBottom: 4 }}>SKIP RECORD</div>
              <div style={{ fontSize: 11, color: "var(--text3)" }}>
                <strong>Reason:</strong> {entry.skip_reason?.replace(/_/g, " ") || "—"}
                {entry.skip_note && <span> · {entry.skip_note}</span>}
              </div>
              {entry.suggestion_score && (
                <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 2 }}>
                  Score: {entry.suggestion_score?.toFixed(1)} · EV: ${entry.suggestion_ev?.toFixed(2)} · {entry.suggestion_structure}
                </div>
              )}
              {entry.outcome_if_taken != null ? (
                <div style={{ fontSize: 11, fontWeight: 700, color: entry.outcome_if_taken > 0 ? "var(--red)" : "var(--green)", marginTop: 4 }}>
                  Actual outcome if taken: {entry.outcome_if_taken > 0 ? "+" : ""}{entry.outcome_if_taken}%
                  {entry.outcome_if_taken > 0 ? " ← missed gain" : " ← good skip"}
                </div>
              ) : (
                <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 4, fontStyle: "italic" }}>
                  Update outcome_if_taken once you can see how this played out
                </div>
              )}
            </div>
          )}

          {isClosed && (
            <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6 }}>
              Closed {entry.exit_date} · {entry.exit_reason} · Exit {pr(entry.exit_price)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────
function StatsBar({ entries }) {
  const closed = entries.filter(e => ["closed", "stopped"].includes(e.status) && e.pnl_pct != null);
  if (!closed.length) return null;

  const wins     = closed.filter(e => e.pnl_pct > 0);
  const winRate  = Math.round(wins.length / closed.length * 100);
  const avgPnl   = (closed.reduce((s, e) => s + e.pnl_pct, 0) / closed.length).toFixed(1);
  const bestTrade = Math.max(...closed.map(e => e.pnl_pct)).toFixed(1);
  const worstTrade = Math.min(...closed.map(e => e.pnl_pct)).toFixed(1);

  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
      {[
        ["Closed trades", closed.length, "var(--text3)"],
        ["Win rate", `${winRate}%`, winRate >= 50 ? "var(--green)" : "var(--red)"],
        ["Avg P&L", `${avgPnl >= 0 ? "+" : ""}${avgPnl}%`, chgC(parseFloat(avgPnl))],
        ["Best", `+${bestTrade}%`, "var(--green)"],
        ["Worst", `${worstTrade}%`, "var(--red)"],
      ].map(([label, val, col]) => (
        <div key={label} style={{ ...S.card, padding: "8px 14px", textAlign: "center", minWidth: 80 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: col, fontFamily: "'Inter', sans-serif" }}>{val}</div>
          <div style={{ ...S.label }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// ── Main Journal component ────────────────────────────────────────────────────
export default function Journal({ prefillEntry = null, onPrefillConsumed }) {
  const [entries,  setEntries]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [tab,      setTab]      = useState("open");
  const [showForm, setShowForm] = useState(false);
  const [editEntry, setEditEntry] = useState(null);
  const [closeEntry, setCloseEntry] = useState(null);
  const [formPrefill, setFormPrefill] = useState({});

  const load = useCallback(async () => {
    try {
      const res  = await fetch(`${API}/api/journal`);
      const data = await res.json();
      setEntries(data.entries || []);
    } catch (e) {
      console.error("Journal load error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Handle prefill from signal card quick-add
  useEffect(() => {
    if (prefillEntry) {
      setFormPrefill(prefillEntry);
      setShowForm(true);
      setTab("watching");
      onPrefillConsumed?.();
    }
  }, [prefillEntry, onPrefillConsumed]);

  const handleSave = async (payload) => {
    if (editEntry) {
      await fetch(`${API}/api/journal/${editEntry.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await fetch(`${API}/api/journal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    setShowForm(false);
    setEditEntry(null);
    setFormPrefill({});
    await load();
  };

  const handleClose = async (payload) => {
    await fetch(`${API}/api/journal/${closeEntry.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setCloseEntry(null);
    await load();
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this journal entry?")) return;
    await fetch(`${API}/api/journal/${id}`, { method: "DELETE" });
    await load();
  };

  const handleEdit = (entry) => {
    setEditEntry(entry);
    setFormPrefill(entry);
    setShowForm(true);
  };

  const filtered = entries.filter(e =>
    tab === "all"      ? true :
    tab === "open"     ? e.status === "open" :
    tab === "watching" ? e.status === "watching" :
    tab === "skipped"  ? e.status === "skipped" :
    ["closed", "stopped"].includes(e.status)
  );

  const openCount     = entries.filter(e => e.status === "open").length;
  const watchingCount = entries.filter(e => e.status === "watching").length;
  const skippedCount  = entries.filter(e => e.status === "skipped").length;
  const closedCount   = entries.filter(e => ["closed","stopped"].includes(e.status)).length;

  const tabBtn = (key, label, count) => (
    <button onClick={() => setTab(key)} style={{
      padding: "6px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
      border: `1px solid ${tab === key ? "var(--accent)" : "var(--border)"}`,
      background: tab === key ? "rgba(41,98,255,0.08)" : "transparent",
      color: tab === key ? "var(--accent)" : "var(--text3)",
      fontFamily: "inherit", letterSpacing: 0.5,
    }}>
      {label} {count > 0 && <span style={{ fontWeight: 700 }}>({count})</span>}
    </button>
  );

  return (
    <div style={S.page}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h2 style={S.title}>Trade Journal</h2>
        <button style={S.btnFill()} onClick={() => { setFormPrefill({}); setEditEntry(null); setShowForm(true); }}>
          + Add Position
        </button>
      </div>
      <p style={S.sub}>Track setups, manage positions, measure P&L</p>

      <StatsBar entries={entries} />

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {tabBtn("open",     "Open",     openCount)}
        {tabBtn("watching", "Watching", watchingCount)}
        {tabBtn("closed",   "Closed",   closedCount)}
        {tabBtn("all",      "All",      entries.length)}
      </div>

      {loading ? (
        <div style={{ color: "var(--text3)" }}>Loading journal...</div>
      ) : filtered.length === 0 ? (
        <div style={{ color: "var(--text3)", padding: "16px 0" }}>
          No {tab} positions.{tab === "open" ? " Add a signal from the Live Signals tab." : ""}
        </div>
      ) : (
        filtered.map(e => (
          <JournalCard
            key={e.id}
            entry={e}
            onEdit={handleEdit}
            onClose={setCloseEntry}
            onDelete={handleDelete}
            currentPrices={{}}
          />
        ))
      )}

      {showForm && (
        <JournalForm
          prefill={formPrefill}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditEntry(null); setFormPrefill({}); }}
          isEdit={!!editEntry}
        />
      )}

      {closeEntry && (
        <CloseForm
          entry={closeEntry}
          onClose={handleClose}
          onCancel={() => setCloseEntry(null)}
        />
      )}
    </div>
  );
}
