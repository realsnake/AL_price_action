# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project Overview

This repo is a full-stack US stock paper-trading workstation built around Alpaca:

- FastAPI backend for market data, strategy execution, backtesting, and order submission
- React + Vite frontend for charting, signal review, trade entry, and Brooks strategy backtests
- SQLite for cached OHLCV bars and submitted trade history
- A plugin-style strategy system with 3 classic indicator strategies plus a large Al Brooks price action suite

The codebase is lightweight and pragmatic: thin routers/components, most logic in service functions, and local component state instead of a global store.

## Commands

### One-command startup
```bash
./start.sh
```

`start.sh` currently expects a backend virtualenv at `backend/venv`.

### Backend (manual)
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

### Standalone backtest CLI
```bash
cd backend
.venv/bin/python run_backtest.py
```

### Lightweight backend syntax check
```bash
PYTHONPYCACHEPREFIX=/tmp/codex_pycache python3 -m compileall -q backend
```

### Backend targeted tests
```bash
cd backend
.venv/bin/python -m pytest tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

`backend/requirements-dev.txt` extends the runtime requirements with the pytest stack used by the committed backend tests.

## Architecture

### Backend (`backend/`)

**Entry:** `main.py`

- Creates the FastAPI app
- Initializes the SQLite schema during lifespan startup
- Starts/stops the Alpaca live market data stream
- Registers `market`, `trading`, `strategy`, `backtest`, and `ws` routers

**Routers**

- `routers/market.py` — historical bars and latest quote REST endpoints
- `routers/trading.py` — account, positions, orders, cancel, submit, and local trade history
- `routers/strategy.py` — strategy list and ad hoc signal generation
- `routers/backtest.py` — cached backtest runs with performance metrics
- `routers/ws.py` — `/ws/market/{symbol}` live bar push and `/ws/trades` trade notifications

**Services**

- `services/alpaca_client.py` — sync wrapper around Alpaca historical data and trading clients
- `services/analysis_bars.py` — shared historical bar-loading path for strategy scans and backtests
- `services/bars_cache.py` — SQLite-backed incremental OHLCV cache keyed by `(symbol, timeframe, timestamp)`
- `services/market_data.py` — shared Alpaca live stream with callback subscriptions per symbol
- `services/strategy_engine.py` — strategy registry, auto-discovery, and execution
- `services/trade_executor.py` — submits market orders, records local trade rows, broadcasts events
- `services/backtester.py` — bar-by-bar simulator with stop loss, take profit, risk sizing, equity curve, and summary stats

**Persistence**

- `models.py` defines `Trade`, `StrategyConfig`, and `BarCache`
- `database.py` uses async SQLAlchemy with SQLite via `aiosqlite`
- `StrategyConfig` exists in the schema but is not wired into current routers or frontend flows

### Strategy System

All strategies extend `BaseStrategy` in `backend/strategies/base.py` and register via `@register_strategy`.

Current built-in strategies:

- Classic indicator strategies: `ma_crossover`, `rsi`, `macd`
- Price action strategies: 27 `brooks_*` strategies in `backend/strategies/brooks_price_action.py`

Important behavior differences:

- `POST /api/strategy/signals` and `POST /api/backtest/run` both load historical data through `services/analysis_bars.py`
- `services/analysis_bars.py` currently delegates to `bars_cache`, so scan and backtest flows now share the same symbol uppercasing, time window, and default limit behavior
- `backend/run_backtest.py` benchmarks only the 3 classic indicator strategies, not the Brooks suite

### Frontend (`frontend/src/`)

**Entry:** `App.tsx`

- Manages current symbol, timeframe, bars, signals, account snapshot, positions, notifications, and backtest equity curve
- Uses a chart-focused main pane plus a right sidebar with `Trade` and `Backtest` tabs

**Components**

- `Chart.tsx` — candlesticks, volume histogram, and buy/sell markers using `lightweight-charts`
- `StrategyPanel.tsx` — lists all strategies and runs `/api/strategy/signals`
- `TradePanel.tsx` — shows account/positions and submits market buy/sell orders
- `BacktestPanel.tsx` — filters to `brooks_*` strategies, supports single-strategy backtests and "Run All" comparison

**Hooks and services**

- `useWebSocket.ts` — generic reconnecting WebSocket hook
- `useMarketData.ts` — subscribes to `/ws/market/{symbol}` and only handles live bar payloads
- `services/api.ts` — Axios wrapper for REST endpoints

**State management**

- Local `useState` and `useEffect`
- No global state library
- Real-time updates are WebSocket driven

## Data Flow

### Real-time chart updates

Alpaca stream → `services/market_data.py` → `routers/ws.py` broadcast → `useMarketData()` → `App.tsx` bar state → `Chart.tsx`

### Strategy scan from the Trade tab

Frontend `StrategyPanel` → `POST /api/strategy/signals` → `analysis_bars` → selected strategy → signals returned to chart/table

### Backtest flow

Frontend `BacktestPanel` → `POST /api/backtest/run` → `analysis_bars` → selected strategy → `backtester` → metrics/trades/equity curve returned

### Manual trading flow

Frontend `TradePanel` → `POST /api/trading/order` → `trade_executor` → Alpaca order submit + DB insert → `/ws/trades` broadcast

## Current Realities And Gaps

- `README.md` and `PLAN.md` describe an earlier phase of the project and lag behind the actual implementation
- Strategy scan and backtest now share `services/analysis_bars.py`, but both still ultimately depend on the cached historical bar path rather than two independent sources
- Live market WebSocket flow currently pushes bars; quote handling code exists in `market_data.py` but is not subscribed or surfaced in the UI
- Frontend API helpers include orders/cancel support, but the current UI does not expose open orders or local trade history
- `Trade` rows are recorded at submission time with `price=0.0`; there is no fill reconciliation path yet
- `start.sh` uses `backend/venv`, while the manual commands above use `backend/.venv`; keep this in mind when adjusting setup docs or scripts

## Key Conventions

- Keep backend routes async-friendly and push heavy logic into services
- Signals and backtest trade records are immutable dataclasses
- Symbols are generally uppercased before use
- Supported timeframes are `1m`, `5m`, `15m`, `1h`, `1D`
- REST endpoints live under `/api`, WebSockets under `/ws`
- Frontend styling is Tailwind-first and currently uses a dark trading-terminal aesthetic
