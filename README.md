# Signal Desk — Market Dashboard v4

A personal market scanner and backtest lab. FastAPI backend + React frontend, deployed on Railway.

## Project Structure

```
market-dashboard/
├── backend/
│   ├── main.py              # FastAPI app, scheduler, all API routes
│   ├── scanner.py           # Full scan pipeline orchestrator
│   ├── screener.py          # MA/VCS/RS/ATR calculations
│   ├── base_detector.py     # Pivot/VCP/flat base detection
│   ├── sector_rs.py         # Sector relative strength vs SPY
│   ├── earnings.py          # Next earnings date fetcher
│   ├── alerts.py            # Telegram alerts
│   ├── news.py              # Alpaca news feed
│   ├── intraday.py          # RVOL during market hours
│   ├── database.py          # SQLite: journal, signal history, backtest
│   ├── historical_bt.py     # Historical signal reconstruction (no lookahead)
│   ├── bt_analysis.py       # Dimensional analysis: sector/VCS/RS/regime/monthly
│   ├── bt_optimiser.py      # ATR parameter grid search
│   ├── backtest.py          # Live signal backtest
│   ├── watchlist.py         # ~300 tickers
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── index.js         # Entry point — routes between dashboard and backtest
│   │   ├── App.js           # Live signals dashboard
│   │   └── BacktestApp.js   # Backtest laboratory UI
│   ├── public/index.html
│   └── package.json
└── railway.toml
```

## Deployment (Railway)

### Backend service
- Root directory: `/backend`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Frontend service
- Root directory: `/frontend`
- Build command: `npm install && npm run build`
- Start command: `serve -s build -l $PORT`

### Backend environment variables
```
ALPACA_API_KEY        your_key_id
ALPACA_SECRET_KEY     your_secret_key
TELEGRAM_BOT_TOKEN    your_bot_token
TELEGRAM_CHAT_ID      your_chat_id (get from @userinfobot on Telegram)
TRIGGER_SECRET        any_random_string
DATA_DIR              /app/data  (volume mount path for SQLite persistence)
```

### Frontend environment variables
```
REACT_APP_API_URL           https://your-backend.up.railway.app
REACT_APP_TRIGGER_SECRET    same_string_as_backend_TRIGGER_SECRET
```

## Scan Schedule
- **07:00 UK (Tue–Sat)** — pre-market scan using previous day's close
- **21:00 UK (Mon–Fri)** — post-market EOD scan
- **Every 30 mins (market hours)** — RVOL refresh

## Manual Trigger
```
POST https://your-backend.up.railway.app/api/scan/trigger?secret=your_trigger_secret
```

## Backtest Workflow
1. `POST /api/backtest/reconstruct?secret=xxx&lookback_days=365` — runs in background (~30-60 mins)
2. Check `GET /api/backtest/status` for progress
3. `GET /api/backtest/analysis?signal_type=MA21` — full analysis report
4. `GET /api/backtest/drill?max_vcs=3&min_rs=85&min_market_score=65` — drill-down
5. `POST /api/backtest/optimise?secret=xxx&quick=true` — parameter grid search

## Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```
