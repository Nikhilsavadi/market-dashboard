// Build: 2026-02-28 14:59:09 UTC
import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import MainDashboard from "./App";
import BacktestApp from "./BacktestApp";
import MarketSummary from "./components/MarketSummary";
import Pipeline from "./components/Pipeline";
import Journal from "./components/Journal";
import OptionsDesk from "./components/OptionsDesk";
import EdgeReport from "./components/EdgeReport";
import MicroCaps from "./components/MicroCaps";
import SuggestedTrades from "./components/SuggestedTrades";
import Breakouts from "./components/Breakouts";
import Patterns from "./components/Patterns";

const NAV_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #ffffff; --bg2: #f0f3fa; --bg3: #e9ecf3; --bg4: #dde1eb;
    --border: #d1d4dc; --border2: #b2b5be;
    --text: #131722; --text2: #4a5066; --text3: #787b86;
    --accent: #2962ff; --green: #089981; --red: #f23645;
    --yellow: #f5a623; --orange: #ff9800; --purple: #7c4dff; --cyan: #00bcd4;
  }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, sans-serif; }
  .top-nav {
    display: flex; align-items: center; gap: 0;
    background: var(--bg); border-bottom: 1px solid var(--border);
    padding: 0 20px; position: sticky; top: 0; z-index: 999;
    font-family: 'Inter', -apple-system, sans-serif;
  }
  .top-nav-logo {
    font-size: 10px; letter-spacing: 3px; color: var(--accent);
    padding: 12px 20px 12px 0; border-right: 1px solid var(--border);
    margin-right: 16px; text-transform: uppercase; font-weight: 700;
  }
  .top-nav-btn {
    padding: 12px 18px; cursor: pointer; font-size: 10px;
    letter-spacing: 1.5px; text-transform: uppercase; color: var(--text3);
    border-bottom: 2px solid transparent; transition: all 0.1s;
    background: none; border-top: none; border-left: none; border-right: none;
    font-family: 'Inter', -apple-system, sans-serif;
  }
  .top-nav-btn:hover { color: var(--text2); }
  .top-nav-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
`;

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error("[AppErrorBoundary]", error, info);
  }
  render() {
    if (this.state.hasError) {
      return React.createElement("div", {
        style: { display:"flex", flexDirection:"column", alignItems:"center",
          justifyContent:"center", height:"100vh", fontFamily:"Inter,sans-serif",
          background:"#131722", color:"#d1d4dc", gap:12 }
      },
        React.createElement("div", { style: { fontSize:28 } }, "💥"),
        React.createElement("div", { style: { fontSize:15, fontWeight:700, color:"#f23645" } }, "App crashed — see console"),
        React.createElement("div", { style: { fontSize:11, color:"#787b86", maxWidth:460, textAlign:"center",
          fontFamily:"monospace", background:"#1e222d", padding:"10px 16px", borderRadius:6 } },
          String(this.state.error?.message || this.state.error)
        ),
        React.createElement("button", {
          onClick: () => window.location.reload(),
          style: { marginTop:8, padding:"8px 22px", background:"#2962ff", border:"none",
            color:"#fff", cursor:"pointer", fontFamily:"Inter,sans-serif",
            fontSize:12, borderRadius:4, fontWeight:700 }
        }, "↻ Reload")
      );
    }
    return this.props.children;
  }
}

function Root() {
  const [view, setView] = useState("market");
  const [journalPrefill, setJournalPrefill] = useState(null);
  const [optionsPrefill, setOptionsPrefill] = useState(null);
  const handleOptionsAdd = (signal) => { setOptionsPrefill(signal); setView("options"); };
  const handleQuickAdd = (signal) => { setJournalPrefill(signal); setView("journal"); };
  // Top nav hidden — only Market + EP Dash tabs live inside MainDashboard (App.js)
  // To restore: uncomment the nav bar and view routing below
  return (
    <>
      <style>{NAV_CSS}</style>
      {/* Top nav hidden — all navigation via MainDashboard tabs */}
      <MainDashboard onQuickAdd={handleQuickAdd} />

      {/* Hidden views (code preserved):
      <div className="top-nav">
        <div className="top-nav-logo">Signal Desk</div>
        <button className={`top-nav-btn ${view === "market" ? "active" : ""}`} onClick={() => setView("market")}>Market Overview</button>
        <button className={`top-nav-btn ${view === "dashboard" ? "active" : ""}`} onClick={() => setView("dashboard")}>Live Signals</button>
        <button className={`top-nav-btn ${view === "pipeline" ? "active" : ""}`} onClick={() => setView("pipeline")}>Watchlist Pipeline</button>
        <button className={`top-nav-btn ${view === "breakouts" ? "active" : ""}`} onClick={() => setView("breakouts")}>Breakouts</button>
        <button className={`top-nav-btn ${view === "patterns" ? "active" : ""}`} onClick={() => setView("patterns")}>Patterns</button>
        <button className={`top-nav-btn ${view === "journal" ? "active" : ""}`} onClick={() => setView("journal")}>Journal</button>
        <button className={`top-nav-btn ${view === "options" ? "active" : ""}`} onClick={() => setView("options")}>Options Desk</button>
        <button className={`top-nav-btn ${view === "edge" ? "active" : ""}`} onClick={() => setView("edge")}>Edge Report</button>
        <button className={`top-nav-btn ${view === "micro" ? "active" : ""}`} onClick={() => setView("micro")}>Micro Caps</button>
        <button className={`top-nav-btn ${view === "suggestions" ? "active" : ""}`} onClick={() => setView("suggestions")}>Suggestions</button>
        <button className={`top-nav-btn ${view === "backtest" ? "active" : ""}`} onClick={() => setView("backtest")}>Backtest Lab</button>
      </div>
      {view === "market"    && <MarketSummary />}
      {view === "dashboard" && <MainDashboard onQuickAdd={handleQuickAdd} />}
      {view === "pipeline"  && <Pipeline />}
      {view === "breakouts" && <Breakouts onQuickAdd={handleQuickAdd} />}
      {view === "patterns"  && <Patterns  onQuickAdd={handleQuickAdd} />}
      {view === "journal"   && <Journal prefillEntry={journalPrefill} onPrefillConsumed={() => setJournalPrefill(null)} />}
      {view === "options"   && <OptionsDesk prefillSignal={optionsPrefill} onPrefillConsumed={() => setOptionsPrefill(null)} />}
      {view === "edge"     && <EdgeReport />}
      {view === "micro"    && <MicroCaps onQuickAdd={handleOptionsAdd} />}
      {view === "suggestions" && <SuggestedTrades onQuickAdd={handleQuickAdd} />}
      {view === "backtest"  && <BacktestApp />}
      */}
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<AppErrorBoundary><Root /></AppErrorBoundary>);
