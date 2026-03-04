import React, { useState, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "";

const SIGNAL_COLORS = {
  "MA10": "#4ade80",
  "MA21": "#60a5fa",
  "MA50": "#f59e0b",
  "VCP":  "#a78bfa",
  "FLAG": "#fb923c",
  "CUP":  "#34d399",
  "EP":   "#f472b6",
};

function AgeBadge({ days }) {
  const color = days >= 7 ? "#f87171" : days >= 3 ? "#f59e0b" : "#4ade80";
  return (
    <span style={{
      background: color + "22",
      color,
      border: `1px solid ${color}55`,
      borderRadius: 4,
      padding: "1px 6px",
      fontSize: 11,
      fontWeight: 600,
      whiteSpace: "nowrap",
    }}>
      {days === 0 ? "New today" : `${days}d`}
    </span>
  );
}

export default function WatchlistTab() {
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [exporting, setExporting] = useState(false);
  const [minDays, setMinDays]     = useState(0);
  const [minScore, setMinScore]   = useState(0);
  const [exports, setExports]     = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/watchlist/tracker`)
      .then(r => r.json())
      .then(d => { setWatchlist(d.watchlist || []); setLoading(false); })
      .catch(() => setLoading(false));

    fetch(`${API}/api/watchlist/exports`)
      .then(r => r.json())
      .then(d => setExports(d.exports || []))
      .catch(() => {});
  }, []);

  const filtered = watchlist
    .filter(t => t.days_on_watchlist >= minDays)
    .filter(t => (t.score || 0) >= minScore);

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (minDays > 0) params.set("min_days", minDays);
      if (minScore > 0) params.set("min_score", minScore);
      const res = await fetch(`${API}/api/watchlist/export?${params}`);
      const text = await res.text();
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const today = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `watchlist-${today}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      // Refresh export history
      const d = await fetch(`${API}/api/watchlist/exports`).then(r => r.json());
      setExports(d.exports || []);
    } catch (e) {
      alert("Export failed: " + e.message);
    }
    setExporting(false);
  };

  const handleRemove = async (ticker) => {
    if (!window.confirm(`Remove ${ticker} from watchlist tracker?`)) return;
    await fetch(`${API}/api/watchlist/tracker/${ticker}`, { method: "DELETE" });
    setWatchlist(w => w.filter(t => t.ticker !== ticker));
  };

  const openTV = (ticker) => {
    window.open(`https://www.tradingview.com/chart/?symbol=${ticker}`, "_blank");
  };

  if (loading) return <div style={{ padding: 32, color: "#888" }}>Loading watchlist...</div>;

  return (
    <div style={{ padding: "16px 20px", maxWidth: 1100 }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0" }}>📋 Watchlist Tracker</div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
            {watchlist.length} tickers tracked · {filtered.length} shown
          </div>
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginLeft: "auto", flexWrap: "wrap" }}>
          <label style={{ fontSize: 12, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6 }}>
            Min days:
            <select value={minDays} onChange={e => setMinDays(+e.target.value)}
              style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4, padding: "2px 6px", fontSize: 12 }}>
              <option value={0}>All</option>
              <option value={1}>1+</option>
              <option value={3}>3+</option>
              <option value={7}>7+</option>
            </select>
          </label>
          <label style={{ fontSize: 12, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6 }}>
            Min score:
            <select value={minScore} onChange={e => setMinScore(+e.target.value)}
              style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4, padding: "2px 6px", fontSize: 12 }}>
              <option value={0}>All</option>
              <option value={7}>7+</option>
              <option value={8}>8+</option>
              <option value={9}>9+</option>
            </select>
          </label>

          <button onClick={handleExport} disabled={exporting}
            style={{
              background: exporting ? "#1e293b" : "#3b82f6",
              color: "#fff", border: "none", borderRadius: 6,
              padding: "6px 14px", fontSize: 12, fontWeight: 600,
              cursor: exporting ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6,
            }}>
            {exporting ? "Exporting..." : "⬇ Export for TradingView"}
          </button>

          <button onClick={() => setShowHistory(h => !h)}
            style={{
              background: "#1e293b", color: "#94a3b8",
              border: "1px solid #334155", borderRadius: 6,
              padding: "6px 12px", fontSize: 12, cursor: "pointer",
            }}>
            {showHistory ? "Hide" : "📁 History"}
          </button>
        </div>
      </div>

      {/* TV Import instructions */}
      <div style={{
        background: "#0f172a", border: "1px solid #1e3a5f", borderRadius: 8,
        padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#94a3b8",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{ fontSize: 18 }}>💡</span>
        <span>
          To import into TradingView: click <b style={{ color: "#e2e8f0" }}>Export for TradingView</b> →
          in TV open Watchlist panel → click <b style={{ color: "#e2e8f0" }}>⋮ → Import watchlist</b> →
          select the downloaded <code style={{ color: "#60a5fa" }}>.txt</code> file.
          Create a new watchlist named with today's date to keep them separate.
        </span>
      </div>

      {/* Export History */}
      {showHistory && exports.length > 0 && (
        <div style={{
          background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
          padding: 14, marginBottom: 16,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8", marginBottom: 10 }}>Export History</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {exports.map(ex => (
              <div key={ex.id} style={{
                background: "#1e293b", borderRadius: 6, padding: "6px 12px",
                fontSize: 12, color: "#e2e8f0",
              }}>
                <span style={{ color: "#60a5fa", fontWeight: 600 }}>{ex.export_date}</span>
                <span style={{ color: "#64748b", marginLeft: 6 }}>{ex.tickers?.length || 0} tickers</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Watchlist Table */}
      {filtered.length === 0 ? (
        <div style={{ color: "#64748b", padding: 32, textAlign: "center" }}>
          No tickers match filters. Run a scan to populate the watchlist.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #1e293b" }}>
              {["Ticker", "Signal", "Score", "Sector", "First Seen", "Last Seen", "Days", "Actions"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "6px 10px", color: "#64748b", fontWeight: 600, fontSize: 11 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(t => (
              <tr key={t.ticker} style={{ borderBottom: "1px solid #0f172a" }}
                onMouseEnter={e => e.currentTarget.style.background = "#0f172a"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "7px 10px" }}>
                  <span style={{ fontWeight: 700, color: "#e2e8f0", fontSize: 14 }}>{t.ticker}</span>
                </td>
                <td style={{ padding: "7px 10px" }}>
                  <span style={{
                    background: (SIGNAL_COLORS[t.signal_type] || "#94a3b8") + "22",
                    color: SIGNAL_COLORS[t.signal_type] || "#94a3b8",
                    border: `1px solid ${(SIGNAL_COLORS[t.signal_type] || "#94a3b8")}44`,
                    borderRadius: 4, padding: "1px 6px", fontSize: 11, fontWeight: 600,
                  }}>
                    {t.signal_type || "—"}
                  </span>
                </td>
                <td style={{ padding: "7px 10px", color: "#f59e0b", fontWeight: 600 }}>
                  {t.score ? t.score.toFixed(1) : "—"}
                </td>
                <td style={{ padding: "7px 10px", color: "#94a3b8", fontSize: 12 }}>
                  {t.sector || "—"}
                </td>
                <td style={{ padding: "7px 10px", color: "#94a3b8", fontSize: 12 }}>
                  {t.first_seen}
                </td>
                <td style={{ padding: "7px 10px", color: "#94a3b8", fontSize: 12 }}>
                  {t.last_seen}
                </td>
                <td style={{ padding: "7px 10px" }}>
                  <AgeBadge days={t.days_on_watchlist} />
                </td>
                <td style={{ padding: "7px 10px" }}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button onClick={() => openTV(t.ticker)}
                      title="Open in TradingView"
                      style={{
                        background: "#1e293b", color: "#60a5fa",
                        border: "1px solid #334155", borderRadius: 4,
                        padding: "3px 8px", fontSize: 11, cursor: "pointer",
                      }}>
                      📈 TV
                    </button>
                    <button onClick={() => handleRemove(t.ticker)}
                      title="Remove from tracker"
                      style={{
                        background: "#1e293b", color: "#f87171",
                        border: "1px solid #334155", borderRadius: 4,
                        padding: "3px 8px", fontSize: 11, cursor: "pointer",
                      }}>
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
