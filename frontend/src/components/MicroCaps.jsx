import RegimeGate from "./RegimeGate";
import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const C = {
  bg: "var(--bg)", bg2: "var(--bg2)", bg3: "var(--bg3)", bg4: "var(--bg4)",
  border: "var(--border)", border2: "var(--border2)",
  amber: "var(--yellow)", amberL: "rgba(245,166,35,0.12)", amberD: "var(--yellow)",
  green: "var(--green)", greenL: "rgba(8,153,129,0.1)",
  red: "var(--red)", redL: "rgba(242,54,69,0.08)",
  blue: "var(--cyan)", purple: "var(--purple)",
  text: "var(--text)", text2: "var(--text2)", text3: "var(--text3)",
  rust: "var(--accent)",
  hot: "var(--orange)", hotL: "rgba(255,152,0,0.12)",
};

const pr  = (v) => v == null ? "—" : `$${Number(v).toFixed(2)}`;
const pct = (v) => v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(1)}%`;
const num = (v, dp=1) => v == null ? "—" : Number(v).toFixed(dp);

const S = {
  page: { background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Inter', -apple-system, sans-serif", fontSize: 12, padding: "0 0 60px" },
  header: { background: C.bg2, borderBottom: `1px solid ${C.border}`, padding: "14px 24px 12px", position: "sticky", top: 0, zIndex: 100 },
  label: { fontSize: 9, color: C.text3, letterSpacing: 2, textTransform: "uppercase", marginBottom: 3 },
  tag: (col) => ({ fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 2, background: `${col}22`, color: col, border: `1px solid ${col}44`, letterSpacing: 1, textTransform: "uppercase", whiteSpace: "nowrap" }),
  card: { background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 3, padding: "12px 14px", marginBottom: 8, cursor: "pointer", transition: "border-color 0.15s" },
  btn: (col=C.amber, fill=false) => ({ padding: "5px 12px", fontSize: 10, cursor: "pointer", borderRadius: 2, border: `1px solid ${col}`, background: fill ? col : "transparent", color: fill ? "#000" : col, fontFamily: "inherit", letterSpacing: 1, fontWeight: 700, textTransform: "uppercase", transition: "all 0.12s" }),
  divider: { borderTop: `1px solid ${C.border}`, margin: "10px 0" },
};

// ── Social score badge ────────────────────────────────────────────────────────
function SocialBadge({ score, label }) {
  if (score == null) return null;
  const col = score >= 7 ? C.hot : score >= 5 ? C.amber : score >= 3 ? C.blue : C.text3;
  const icon = score >= 7 ? "🔥" : score >= 5 ? "📈" : score >= 3 ? "💬" : "·";
  return (
    <span style={{ ...S.tag(col), display: "inline-flex", alignItems: "center", gap: 3 }}>
      {icon} {label || `SOCIAL ${score}`}
    </span>
  );
}

// ── Social detail panel ───────────────────────────────────────────────────────
function SocialPanel({ ticker, data, onFetch }) {
  const [loading, setLoading] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try { await onFetch(ticker); }
    finally { setLoading(false); }
  };

  if (!data && !loading) {
    return (
      <div style={{ background: C.bg4, borderRadius: 2, padding: "10px 12px", marginTop: 10 }}>
        <button style={S.btn(C.amber)} onClick={(e) => { e.stopPropagation(); fetch(); }}>
          Fetch Social Intel
        </button>
        <span style={{ fontSize: 10, color: C.text3, marginLeft: 10 }}>
          StockTwits · Reddit · News
        </span>
      </div>
    );
  }

  if (loading) return (
    <div style={{ background: C.bg4, borderRadius: 2, padding: "10px 12px", marginTop: 10, color: C.text3, fontSize: 10 }}>
      Fetching social intelligence...
    </div>
  );

  if (!data) return null;

  const { stocktwits: st, reddit: rd, news, composite } = data;

  return (
    <div style={{ background: C.bg4, borderRadius: 2, padding: "12px 14px", marginTop: 10 }} onClick={e => e.stopPropagation()}>

      {/* Composite header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={S.label}>Social Score</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: composite.score >= 7 ? C.hot : composite.score >= 5 ? C.amber : C.text }}>
            {composite.score}<span style={{ fontSize: 11, color: C.text3 }}>/10</span>
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ width: "100%", height: 6, background: C.bg, borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${composite.score * 10}%`, height: "100%", background: composite.score >= 7 ? C.hot : composite.score >= 5 ? C.amber : C.blue, borderRadius: 3, transition: "width 0.4s" }} />
          </div>
        </div>
        <span style={S.tag(composite.score >= 7 ? C.hot : composite.score >= 5 ? C.amber : C.text3)}>
          {composite.label}
        </span>
      </div>

      {/* Alerts */}
      {composite.alerts?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {composite.alerts.map((a, i) => (
            <div key={i} style={{ fontSize: 10, color: C.amber, marginBottom: 3 }}>
              ⚡ {a}
            </div>
          ))}
        </div>
      )}

      {/* Three source columns */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>

        {/* StockTwits */}
        <div>
          <div style={{ ...S.label, color: C.blue, marginBottom: 6 }}>StockTwits</div>
          {st?.error === "not_found" ? (
            <div style={{ fontSize: 10, color: C.text3 }}>Not listed</div>
          ) : st?.error ? (
            <div style={{ fontSize: 10, color: C.text3 }}>Unavailable</div>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{st?.msg_count_24h || 0}</div>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 6 }}>messages today</div>
              {st?.bull_pct != null && (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, marginBottom: 2 }}>
                    <span style={{ color: C.green }}>Bull {st.bull_pct}%</span>
                    <span style={{ color: C.red }}>Bear {100 - st.bull_pct}%</span>
                  </div>
                  <div style={{ height: 4, background: C.red, borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${st.bull_pct}%`, height: "100%", background: C.green, borderRadius: 2 }} />
                  </div>
                </div>
              )}
              {st?.trending && <div style={{ marginTop: 6, ...S.tag(C.amber) }}>🔥 TRENDING</div>}
              {st?.watchlist_count > 0 && (
                <div style={{ fontSize: 9, color: C.text3, marginTop: 4 }}>
                  {(st.watchlist_count / 1000).toFixed(1)}K watchlists
                </div>
              )}
            </>
          )}
        </div>

        {/* Reddit */}
        <div>
          <div style={{ ...S.label, color: C.rust, marginBottom: 6 }}>Reddit</div>
          {rd?.error === "no_credentials" ? (
            <div style={{ fontSize: 10, color: C.text3 }}>Add REDDIT_CLIENT_ID<br/>+ REDDIT_CLIENT_SECRET<br/>to Railway env vars</div>
          ) : rd?.error ? (
            <div style={{ fontSize: 10, color: C.text3 }}>Unavailable</div>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{rd?.mentions_24h || 0}</div>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 4 }}>
                mentions today
                {rd?.daily_avg_7d > 0 && ` (avg ${rd.daily_avg_7d}/day)`}
              </div>
              {rd?.is_spiking && (
                <div style={{ ...S.tag(C.hot), marginBottom: 4 }}>
                  ↑ {rd.spike_ratio}x SPIKE
                </div>
              )}
              {rd?.dd_posts > 0 && (
                <div style={{ ...S.tag(C.purple), marginBottom: 4 }}>
                  {rd.dd_posts} DD POST{rd.dd_posts > 1 ? "S" : ""}
                </div>
              )}
              <div style={{ fontSize: 9, color: rd?.sentiment === "bullish" ? C.green : rd?.sentiment === "bearish" ? C.red : C.text3 }}>
                {rd?.sentiment?.toUpperCase() || "NEUTRAL"}
              </div>
              {/* Top Reddit post */}
              {rd?.top_posts?.[0] && (
                <div style={{ marginTop: 6 }}>
                  <a href={rd.top_posts[0].url} target="_blank" rel="noreferrer"
                    style={{ fontSize: 9, color: C.text3, textDecoration: "none", lineHeight: 1.4, display: "block" }}
                    title={rd.top_posts[0].title}>
                    r/{rd.top_posts[0].subreddit}: {rd.top_posts[0].title?.slice(0, 60)}...
                  </a>
                  <div style={{ fontSize: 8, color: C.text3 }}>▲{rd.top_posts[0].score} · {rd.top_posts[0].comments} comments</div>
                </div>
              )}
            </>
          )}
        </div>

        {/* News */}
        <div>
          <div style={{ ...S.label, color: C.green, marginBottom: 6 }}>News</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{news?.headline_count || 0}</div>
          <div style={{ fontSize: 9, color: C.text3, marginBottom: 4 }}>
            headlines (7d)
            {news?.recent_24h > 0 && ` · ${news.recent_24h} today`}
          </div>
          {news?.catalyst_count > 0 && (
            <div style={{ ...S.tag(C.amber), marginBottom: 6, display: "inline-block" }}>
              {news.catalyst_count} CATALYST{news.catalyst_count > 1 ? "S" : ""}
            </div>
          )}
          {news?.catalysts?.slice(0, 2).map((c, i) => (
            <div key={i} style={{ marginBottom: 4 }}>
              <a href={c.url} target="_blank" rel="noreferrer"
                style={{ fontSize: 9, color: C.text3, textDecoration: "none", lineHeight: 1.4, display: "block" }}>
                {c.headline?.slice(0, 70)}
              </a>
              <div style={{ fontSize: 8, color: C.amber }}>
                {c.keywords?.slice(0, 3).join(" · ")}
              </div>
            </div>
          ))}
          {/* Sentiment bar */}
          {news?.sentiments && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 2 }}>News sentiment</div>
              <div style={{ display: "flex", gap: 6, fontSize: 9 }}>
                <span style={{ color: C.green }}>+{news.sentiments.positive || 0}</span>
                <span style={{ color: C.text3 }}>{news.sentiments.neutral || 0}</span>
                <span style={{ color: C.red }}>-{news.sentiments.negative || 0}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ fontSize: 9, color: C.text3, marginTop: 10 }}>
        Fetched {data.fetched_at?.slice(0, 16)?.replace("T", " ")} UTC · 4hr cache
      </div>
    </div>
  );
}

// ── Signal card ───────────────────────────────────────────────────────────────
function MicroCapCard({ s, topSectors, socialCache, onFetchSocial, onQuickAdd }) {
  const [expanded, setExpanded] = useState(false);
  const isTop   = topSectors?.includes(s.sector);
  const maCol   = s.bouncing_from === "MA10" ? C.amber : s.bouncing_from === "MA21" ? C.green : C.blue;
  const chgCol  = (s.chg || 0) >= 0 ? C.green : C.red;
  const isHot   = (s.social_score || 0) >= 5;
  const hasSoc  = s.social_score != null;

  // Combined score bar colour
  const combinedCol = (s.combined_score || 0) >= 8 ? C.hot
                    : (s.combined_score || 0) >= 7 ? C.amber
                    : C.green;

  return (
    <div style={{
      ...S.card,
      borderColor: expanded ? C.amber : isHot ? `${C.hot}60` : s.signal_score >= 8 ? `${C.amber}40` : C.border,
      borderLeft: `3px solid ${isHot ? C.hot : maCol}`,
    }} onClick={() => setExpanded(e => !e)}>

      {/* Main row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>

        {/* Ticker */}
        <div style={{ minWidth: 130 }}>
          <a href={`https://www.tradingview.com/chart/?symbol=${s.ticker}`}
            target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
            style={{ color: C.amber, fontWeight: 700, fontSize: 14, textDecoration: "none" }}>
            {s.ticker}
          </a>
          <span style={{ marginLeft: 6, fontSize: 9, color: maCol, fontWeight: 700 }}>
            ↗ {s.bouncing_from || "—"}
          </span>
        </div>

        {/* Price */}
        <div style={{ minWidth: 90 }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>{pr(s.price)}</div>
          <div style={{ fontSize: 10, color: chgCol }}>{pct(s.chg)}</div>
        </div>

        {/* Combined score */}
        <div style={{ minWidth: 110 }}>
          <div style={S.label}>Combined</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 60, height: 4, background: C.bg4, borderRadius: 2, overflow: "hidden" }}>
              <div style={{ width: `${(s.combined_score || 0) * 10}%`, height: "100%", background: combinedCol, borderRadius: 2 }} />
            </div>
            <span style={{ color: combinedCol, fontWeight: 700 }}>{s.combined_score || s.signal_score || "—"}</span>
          </div>
          <div style={{ fontSize: 9, color: C.text3 }}>
            T:{s.signal_score} · S:{hasSoc ? s.social_score : "?"}
          </div>
        </div>

        {/* RS */}
        <div style={{ minWidth: 70 }}>
          <div style={S.label}>RS</div>
          <div style={{ color: s.rs >= 90 ? C.amber : s.rs >= 80 ? C.green : C.text, fontWeight: 700 }}>{s.rs || "—"}</div>
        </div>

        {/* Badges */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", flex: 1 }}>
          {hasSoc && <SocialBadge score={s.social_score} label={s.social_label} />}
          <span style={S.tag(s.market_cap && s.market_cap < 300e6 ? C.rust : C.text3)}>
            {s.market_cap && s.market_cap < 300e6 ? "MICRO" : "SMALL"} {s.mktcap_str || ""}
          </span>
          <span style={S.tag(isTop ? C.amber : C.text3)}>{s.sector}</span>
          {s.vcs != null && <span style={S.tag(s.vcs <= 4 ? C.green : C.text3)}>VCS {s.vcs}</span>}
          {s.vol_ratio != null && <span style={S.tag(s.vol_ratio >= 2 ? C.amber : C.text3)}>{num(s.vol_ratio)}x VOL</span>}
          {/* Social alerts inline */}
          {s.social_alerts?.slice(0, 1).map((a, i) => (
            <span key={i} style={S.tag(C.hot)}>⚡ {a.slice(0, 30)}</span>
          ))}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 6, marginLeft: "auto" }} onClick={e => e.stopPropagation()}>
          {onQuickAdd && (
            <button style={S.btn(C.amber)} onClick={() => onQuickAdd({ ...s, signal_type: `MICRO_${s.bouncing_from || "MA"}` })}>
              + Journal
            </button>
          )}
        </div>
      </div>

      {/* Expanded */}
      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>

          {/* Technical grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 12 }}>
            {[
              ["Stop",     pr(s.stop_price)],
              ["Target 1", pr(s.target_1)],
              ["Target 2", pr(s.target_2)],
              ["ATR",      pr(s.atr)],
              ["MA10",     pr(s.ma10)],
              ["MA21",     pr(s.ma21)],
              ["MA50",     pr(s.ma50)],
              ["MA200",    s.ma200 ? pr(s.ma200) : "< 200 bars"],
              ["ADV",      s.adv ? `${(s.adv/1000).toFixed(0)}K` : "—"],
              ["52w High", pr(s.w52_high)],
              ["Sector RS",pct(s.sector_rs_1m)],
              ["Mkt Cap",  s.mktcap_str || "—"],
            ].map(([label, val]) => (
              <div key={label}>
                <div style={S.label}>{label}</div>
                <div style={{ fontSize: 11, fontWeight: 600 }}>{val}</div>
              </div>
            ))}
          </div>

          {/* R/R strip */}
          <div style={{ background: C.bg4, borderRadius: 2, padding: "7px 10px", fontSize: 10, display: "flex", gap: 20, marginBottom: 10 }}>
            {s.stop_price && s.price && (
              <span>Risk: <strong style={{ color: C.red }}>{pct(((s.stop_price - s.price) / s.price) * 100)}</strong></span>
            )}
            {s.target_1 && s.price && s.stop_price && (
              <span>R/R T1: <strong style={{ color: C.green }}>
                {(Math.abs(s.target_1 - s.price) / Math.abs(s.price - s.stop_price)).toFixed(1)}x
              </strong></span>
            )}
            <span style={{ color: s.sector_aligned ? C.green : C.red }}>
              Sector: {s.sector_aligned ? "✓ tailwind" : "✗ headwind"}
            </span>
          </div>

          {/* Social panel */}
          <SocialPanel
            ticker={s.ticker}
            data={socialCache?.[s.ticker] || s.social_detail || null}
            onFetch={onFetchSocial}
          />
        </div>
      )}
    </div>
  );
}

// ── Top sectors bar ───────────────────────────────────────────────────────────
function TopSectorBar({ sectors }) {
  if (!sectors?.length) return null;
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <span style={{ fontSize: 9, color: C.text3, letterSpacing: 2 }}>TOP SECTORS</span>
      {sectors.map((s, i) => (
        <span key={s} style={{ ...S.tag(i === 0 ? C.amber : i === 1 ? C.green : C.blue), fontSize: 9 }}>
          #{i + 1} {s}
        </span>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MicroCaps({ onQuickAdd }) {
  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);
  const [tab,         setTab]         = useState("all");
  const [minScore,    setMinScore]    = useState(6);
  const [sortBy,      setSortBy]      = useState("combined");
  const [trigger,     setTrigger]     = useState(null);
  const [socialCache, setSocialCache] = useState({});
  const [socialTab,   setSocialTab]   = useState("all"); // all | hot | nosocial

  const load = useCallback(async () => {
    try { setLoading(true); setError(null);
      const res  = await fetch(`${API}/api/microcap`);
      if (res.status === 503) { setError((await res.json()).detail); return; }
      setData(await res.json());
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fetchSocial = useCallback(async (ticker) => {
    try {
      const res  = await fetch(`${API}/api/social/${ticker}`);
      const json = await res.json();
      setSocialCache(prev => ({ ...prev, [ticker]: json }));
    } catch (e) { console.error("Social fetch error:", e); }
  }, []);

  const handleTrigger = async () => {
    const secret = prompt("Scan secret:");
    if (!secret) return;
    setTrigger("running");
    try {
      const res  = await fetch(`${API}/api/microcap/trigger?secret=${secret}`, { method: "POST" });
      const json = await res.json();
      setTrigger(json.message || "Scan started — check back in ~10 minutes");
      setTimeout(() => { load(); setTrigger(null); }, 10 * 60 * 1000);
    } catch (e) { setTrigger("Error: " + e.message); }
  };

  const allSignals  = data?.all_signals || [];
  const topSectors  = data?.top_sectors || [];

  // Merge social cache into signals for display
  const enriched = allSignals.map(s => ({
    ...s,
    ...(socialCache[s.ticker] ? {
      social_score:  socialCache[s.ticker].composite?.score,
      social_label:  socialCache[s.ticker].composite?.label,
      social_alerts: socialCache[s.ticker].composite?.alerts,
      social_detail: socialCache[s.ticker],
      combined_score: Math.round((s.signal_score * 0.7 + socialCache[s.ticker].composite?.score * 0.3) * 10) / 10,
    } : {}),
  }));

  const filtered = enriched
    .filter(s => (s.combined_score || s.signal_score || 0) >= minScore)
    .filter(s => {
      if (tab === "ma10")  return s.ma10_touch;
      if (tab === "ma21")  return s.ma21_touch && !s.ma10_touch;
      if (tab === "ma50")  return s.ma50_touch && !s.ma10_touch && !s.ma21_touch;
      if (tab === "micro") return s.market_cap && s.market_cap < 300e6;
      return true;
    })
    .filter(s => {
      if (socialTab === "hot")      return (s.social_score || 0) >= 5;
      if (socialTab === "nosocial") return s.social_score == null;
      return true;
    })
    .sort((a, b) => {
      if (sortBy === "combined") return (b.combined_score || b.signal_score || 0) - (a.combined_score || a.signal_score || 0);
      if (sortBy === "social")   return (b.social_score || 0) - (a.social_score || 0);
      if (sortBy === "rs")       return (b.rs || 0) - (a.rs || 0);
      if (sortBy === "mktcap")   return (a.market_cap || 9e9) - (b.market_cap || 9e9);
      return 0;
    });

  const ma10Count   = allSignals.filter(s => s.ma10_touch).length;
  const ma21Count   = allSignals.filter(s => s.ma21_touch && !s.ma10_touch).length;
  const ma50Count   = allSignals.filter(s => s.ma50_touch && !s.ma10_touch && !s.ma21_touch).length;
  const microCount  = allSignals.filter(s => s.market_cap && s.market_cap < 300e6).length;
  const hotCount    = enriched.filter(s => (s.social_score || 0) >= 5).length;

  return (
    <div style={S.page}>
      {/* Regime compact banner */}
      <RegimeGate compact={true} />

      {/* Header */}
      <div style={S.header}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <span style={{ fontSize: 11, color: C.amber, letterSpacing: 4, fontWeight: 700, textTransform: "uppercase" }}>
              Micro Cap Hunter
            </span>
            <span style={{ fontSize: 9, color: C.text3, marginLeft: 12 }}>
              Russell 2000 · Sector-gated · Social intelligence
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={S.btn(C.text3)} onClick={load}>↺</button>
            <button style={S.btn(C.amber)} onClick={handleTrigger} disabled={trigger === "running"}>
              {trigger === "running" ? "Scanning..." : "▶ Run Scan"}
            </button>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <TopSectorBar sectors={topSectors} />
          <div style={{ display: "flex", gap: 16, fontSize: 10, color: C.text3 }}>
            {data && <>
              <span>Gated: <strong style={{ color: C.text }}>{data.total_gated}</strong></span>
              <span>Signals: <strong style={{ color: C.amber }}>{data.total_signals}</strong></span>
              {data.hot_social > 0 && <span>🔥 Social HOT: <strong style={{ color: C.hot }}>{data.hot_social}</strong></span>}
              <span style={{ color: C.text3 }}>{data.scanned_at}</span>
            </>}
          </div>
        </div>
        {trigger && trigger !== "running" && (
          <div style={{ marginTop: 8, fontSize: 10, color: C.amber }}>{trigger}</div>
        )}
      </div>

      <div style={{ padding: "16px 20px" }}>
        {/* Controls row */}
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
          {/* MA tabs */}
          {[["all",`All (${allSignals.length})`],["ma10",`MA10 (${ma10Count})`],["ma21",`MA21 (${ma21Count})`],["ma50",`MA50 (${ma50Count})`],["micro",`Micro <$300M (${microCount})`]].map(([key,label]) => (
            <button key={key} style={S.btn(C.amber, tab === key)} onClick={() => setTab(key)}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
          {/* Social filter tabs */}
          {[["all","All social"],["hot",`🔥 HOT social (${hotCount})`],["nosocial","Not yet fetched"]].map(([key,label]) => (
            <button key={key} style={S.btn(C.hot, socialTab === key)} onClick={() => setSocialTab(key)}>{label}</button>
          ))}
          {/* Score + sort */}
          <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
            <div style={{ fontSize: 10, color: C.text3 }}>
              Min:
              <input type="range" min="4" max="9" step="0.5" value={minScore}
                onChange={e => setMinScore(parseFloat(e.target.value))}
                style={{ marginLeft: 6, accentColor: C.amber, width: 70, cursor: "pointer" }} />
              <span style={{ color: C.amber, marginLeft: 4 }}>{minScore}</span>
            </div>
            <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ background: C.bg3, border: `1px solid ${C.border2}`, color: C.text, padding: "4px 8px", fontFamily: "inherit", fontSize: 10, cursor: "pointer", borderRadius: 2 }}>
              <option value="combined">Sort: Combined score</option>
              <option value="social">Sort: Social score</option>
              <option value="rs">Sort: RS rank</option>
              <option value="mktcap">Sort: Smallest first</option>
            </select>
          </div>
        </div>

        {/* States */}
        {loading && <div style={{ color: C.text3, padding: "40px 0", textAlign: "center" }}>Loading micro cap signals...</div>}

        {error && !loading && (
          <div style={{ color: C.amber, padding: "30px 0", textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🔭</div>
            <div style={{ marginBottom: 8 }}>{error}</div>
            <div style={{ fontSize: 10, color: C.text3, marginBottom: 16 }}>Scan runs at 22:00 UK (Mon–Fri). Trigger manually or wait for tonight.</div>
            <button style={S.btn(C.amber, true)} onClick={handleTrigger}>▶ Run Scan Now</button>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div style={{ color: C.text3, padding: "30px 0", textAlign: "center" }}>No signals match current filters.</div>
        )}

        {!loading && filtered.length > 0 && (
          <div style={{ marginBottom: 12, fontSize: 10, color: C.text3 }}>
            Showing <strong style={{ color: C.amber }}>{filtered.length}</strong> signals
            {filtered.length !== allSignals.length && ` (of ${allSignals.length})`}
            {" · "}Combined score = 70% technical + 30% social
          </div>
        )}

        {/* Cards */}
        {filtered.map(s => (
          <MicroCapCard
            key={s.ticker}
            s={s}
            topSectors={topSectors}
            socialCache={socialCache}
            onFetchSocial={fetchSocial}
            onQuickAdd={onQuickAdd}
          />
        ))}
      </div>
    </div>
  );
}
