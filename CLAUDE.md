# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A full-stack automated US stock trading system with real-time K-line charts, pluggable strategy framework, backtesting engine, and paper trading via Alpaca API.

## Commands

### Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  # first time
.venv/bin/uvicorn main:app --reload --port 8000
```

### Frontend (Vite + React)
```bash
cd frontend
npm install    # first time
npm run dev    # dev server on :5173
npm run build  # tsc -b && vite build
npm run lint   # eslint
```

### Standalone Backtest CLI
```bash
cd backend
.venv/bin/python run_backtest.py
```

## Architecture

### Backend (`backend/`)

**Entry:** `main.py` — FastAPI app with async lifespan that initializes DB and starts/stops the Alpaca market data stream.

**Layered structure:**
- **Routers** (`routers/`) — Thin HTTP/WS handlers. `market.py`, `trading.py`, `strategy.py`, `backtest.py`, `ws.py`
- **Services** (`services/`) — Business logic singletons:
  - `alpaca_client.py` — Wraps Alpaca SDK (bars, quotes, orders, positions, account)
  - `market_data.py` — Real-time Alpaca WebSocket stream with callback-based per-symbol subscriptions
  - `bars_cache.py` — Incremental bar caching in SQLite (fetches only new bars from API, upserts into DB)
  - `strategy_engine.py` — Strategy plugin registry with `@register_strategy` decorator
  - `trade_executor.py` — Executes orders via Alpaca, records in DB, notifies WebSocket listeners
  - `backtester.py` — Bar-by-bar simulation with stop-loss/take-profit, computes equity curve and metrics (Sharpe, drawdown, win rate)
- **Strategies** (`strategies/`) — All extend `BaseStrategy` (ABC) from `base.py`. Must implement `generate_signals(symbol, bars)` and `default_params()`. Signal is a frozen dataclass.
- **Models** (`models.py`) — SQLAlchemy ORM: `Trade`, `StrategyConfig`, `BarCache`
- **Database** (`database.py`) — Async SQLAlchemy engine with aiosqlite

**Strategy plugin pattern:** Decorate a `BaseStrategy` subclass with `@register_strategy` in `strategy_engine.py`. The engine auto-imports all modules in `strategies/`.

### Frontend (`frontend/src/`)

**Entry:** `App.tsx` — Main layout with symbol/timeframe controls, chart, signal table, and tabbed sidebar (Trade/Backtest).

- **Components:** `Chart.tsx` (lightweight-charts candlestick + volume), `TradePanel.tsx` (account/orders/positions), `StrategyPanel.tsx` (strategy selector + params), `BacktestPanel.tsx` (backtest config + results)
- **Hooks:** `useWebSocket.ts` (generic with auto-reconnect), `useMarketData.ts` (subscribes to `/ws/market/{symbol}`)
- **Services:** `api.ts` — Axios client wrapping all REST endpoints
- **Types:** `types/index.ts` — Shared TypeScript interfaces

**State management:** Component-level `useState` — no global store. WebSocket hooks provide reactive real-time updates.

### Data Flow

Real-time: Alpaca WebSocket → `market_data` service → `ws.router` broadcast → frontend `useMarketData` → Chart update

Strategy: Frontend → `POST /api/strategy/signals` → `bars_cache` → `strategy_engine.run_strategy()` → signals returned → Chart markers

Trading: Frontend → `POST /api/trading/order` → `trade_executor` → Alpaca API → DB record → WebSocket broadcast

### Dev Proxy

`vite.config.ts` proxies `/api` → `http://localhost:8000` and `/ws` → `ws://localhost:8000`.

## Key Conventions

- **Async everywhere** — All backend routes, DB operations, and WebSocket handlers are async
- **Immutable signals** — `Signal` and `TradeRecord` use `@dataclass(frozen=True)`
- **Config via .env** — Copy `.env.example` to `.env` with Alpaca API keys. Paper trading is default
- **API prefix** — All REST endpoints under `/api/`, WebSocket under `/ws/`
- **Timeframes** — Valid values: `1m`, `5m`, `15m`, `1h`, `1D`
