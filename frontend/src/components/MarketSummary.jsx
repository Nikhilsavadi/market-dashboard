import React, { useEffect, useState, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "";

const pct = (v, d = 2) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}%`;

const price = (v) =>
  v == null ? "—"
  : v > 1000 ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : `$${Number(v).toFixed(2)}`;

const chgColor = (v) =>
  v == null ? "var(--text3)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text3)";

const rsColor = (score) => {
  if (score >= 80) return "var(--green)";
  if (score >= 60) return "#26a69a";
  if (score >= 40) return "var(--yellow)";
  return "var(--red)";
};
const rsBg = (score) => {
  if (score >= 80) return "rgba(8,153,129,0.1)";
  if (score >= 60) return "rgba(38,166,154,0.08)";
  if (score >= 40) return "rgba(245,166,35,0.1)";
  return "rgba(242,54,69,0.1)";
};

const RSBadge = ({ score }) => (
  <span style={{
    display: "inline-block", minWidth: 36, padding: "2px 6px",
    borderRadius: 3, fontSize: 11, fontWeight: 700, textAlign: "center",
    background: rsBg(score), color: rsColor(score),
    border: `1px solid ${rsColor(score)}44`,
  }}>
    {score}
  </span>
);

function tvUrl(ticker) {
  if (!ticker) return "#";
  const NYSE = new Set(["V","MA","JPM","BAC","GS","MS","WFC","AXP","BLK","KO","PEP","PG",
    "JNJ","MRK","LLY","CVX","XOM","BA","CAT","DE","HON","GE","UPS","HD","WMT","NKE",
    "MCD","SBUX","T","VZ","DIS","NEE","AMT","SPG","SPGI","SYK","TMO","UNH",
    "GLD","TLT","SPY","QQQ","IWM",
    "XLK","XLF","XLE","XLV","XLC","XLI","XLB","XLP","XLRE","XLU"]);
  const exchange = NYSE.has(ticker) ? "NYSE" : "NASDAQ";
  return `https://www.tradingview.com/chart/?symbol=${exchange}:${ticker.replace(".", "-")}`;
}

export default function MarketSummary() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API}/api/market-summary`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const wrap = {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: 12, color: "var(--text)", padding: "16px 16px 0",
    background: "var(--bg)",
  };
  const sectionTitle = {
    fontSize: 10, fontWeight: 700, color: "var(--text)",
    letterSpacing: 1, textTransform: "uppercase",
    borderLeft: "3px solid var(--accent)", paddingLeft: 8, marginBottom: 10,
  };
  const card = {
    flex: "0 0 auto", minWidth: 140,
    background: "var(--bg2)", border: "1px solid var(--border)",
    borderRadius: 4, padding: "12px 14px", textAlign: "center",
  };
  const gainerCard = {
    background: "var(--bg2)", border: "1px solid var(--border)",
    borderRadius: 4, padding: "8px 10px", marginBottom: 6,
    display: "flex", alignItems: "center", justifyContent: "space-between",
  };
  const th = {
    fontSize: 9, color: "var(--text3)", letterSpacing: 1,
    textTransform: "uppercase", textAlign: "right", padding: "4px 8px",
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", fontWeight: 600,
  };
  const td = {
    fontSize: 11, padding: "6px 8px", textAlign: "right",
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", color: "var(--text)",
  };

  if (loading) return <div style={{ ...wrap, padding: 24, color: "var(--text3)" }}>Loading market overview...</div>;
  if (error)   return (
    <div style={{ ...wrap, padding: 24 }}>
      <div style={{ color: "var(--red)", marginBottom: 8 }}>Market data unavailable: {error}</div>
      <button onClick={load} style={{
        padding: "5px 14px", fontSize: 10, cursor: "pointer", borderRadius: 3,
        border: "1px solid var(--border)", background: "var(--bg3)",
        color: "var(--text2)", fontFamily: "inherit",
      }}>Retry</button>
    </div>
  );
  if (!data) return <div style={{ ...wrap, padding: 24, color: "var(--text3)" }}>No data yet...</div>;

  const { indices = [], sectors = [], top_rs_daily = [], top_rs_weekly = [] } = data;

  return (
    <div style={wrap}>

      {/* Index cards */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, overflowX: "auto", paddingBottom: 4 }}>
        {indices.map((idx) => (
          <div key={idx.symbol || idx.ticker} style={card}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
              {price(idx.price)}
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: chgColor(idx.chg_1d) }}>
              {pct(idx.chg_1d)}
            </div>
            <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, marginTop: 4 }}>
              {idx.label || idx.symbol || idx.ticker}
            </div>
          </div>
        ))}
      </div>

      {/* Two-col: gainers + sector table */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>

        {/* Left: RS gainers */}
        <div style={{ flex: "0 0 240px" }}>
          {top_rs_daily.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={sectionTitle}>Top RS Gainers (Daily)</div>
              {top_rs_daily.map((s) => (
                <div key={s.ticker} style={gainerCard}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <RSBadge score={s.rs_rank} />
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>
                        <a href={tvUrl(s.ticker)} target="_blank" rel="noopener noreferrer"
                           style={{ textDecoration: "none", color: "var(--accent)" }}>
                          {s.ticker} ↗
                        </a>
                      </div>
                      <div style={{ fontSize: 9, color: "var(--text3)" }}>{s.sector}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, fontSize: 11 }}>{price(s.price)}</div>
                    <div style={{ color: chgColor(s.chg_pct), fontSize: 11 }}>{pct(s.chg_pct)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {top_rs_weekly.length > 0 && (
            <div>
              <div style={sectionTitle}>Top Sectors (Weekly RS)</div>
              {top_rs_weekly.map((s) => (
                <div key={s.ticker || s.etf} style={gainerCard}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <RSBadge score={s.rs_rank || s.rs_score} />
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                        {s.ticker || s.etf}
                      </div>
                      <div style={{ fontSize: 9, color: "var(--text3)" }}>{s.sector}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: chgColor(s.chg_pct), fontSize: 11, fontWeight: 600 }}>
                      {pct(s.chg_pct)} wk
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Sector table */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={sectionTitle}>Sector Leaders</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["RS","SECTOR","ETF","DAY %","WK %","MTH %","RS WK%","RS MTH%","52W HIGH"].map((h, i) => (
                    <th key={h} style={i === 1 ? { ...th, textAlign: "left", paddingLeft: 10 } : th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sectors.map((s) => (
                  <tr key={s.etf}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--bg2)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    <td style={td}><RSBadge score={s.rs_score} /></td>
                    <td style={{ ...td, textAlign: "left", fontWeight: 600, paddingLeft: 10 }}>{s.sector}</td>
                    <td style={{ ...td, color: "var(--accent)", fontWeight: 600 }}>
                      <a href={tvUrl(s.etf)} target="_blank" rel="noopener noreferrer"
                         style={{ textDecoration: "none", color: "var(--accent)" }}>
                        {s.etf} ↗
                      </a>
                    </td>
                    <td style={{ ...td, color: chgColor(s.chg_1d) }}>{pct(s.chg_1d)}</td>
                    <td style={{ ...td, color: chgColor(s.chg_1w) }}>{pct(s.chg_1w)}</td>
                    <td style={{ ...td, color: chgColor(s.chg_1m) }}>{pct(s.chg_1m)}</td>
                    <td style={{ ...td, color: chgColor(s.rs_1w) }}>{pct(s.rs_1w)}</td>
                    <td style={{ ...td, color: chgColor(s.rs_1m) }}>{pct(s.rs_1m)}</td>
                    <td style={{ ...td, color: s.dist_52h != null && s.dist_52h < -10 ? "var(--red)" : "var(--text3)" }}>
                      {s.dist_52h != null ? `${s.dist_52h}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div style={{ height: 20 }} />
    </div>
  );
}
