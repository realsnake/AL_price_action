# Alpaca Degraded Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the backend to boot without Alpaca credentials, return explicit degraded-mode responses for Alpaca-dependent features, and keep cache-backed historical flows usable when local data is sufficient.

**Architecture:** Replace import-time Alpaca SDK construction with a lazy service that exposes capability checks and raises a single degraded-mode exception only when real Alpaca access is required. Then propagate that exception through cache, routers, health reporting, and WebSocket behavior so startup stays available while quote, live, and trading paths fail honestly with `503`.

**Tech Stack:** FastAPI, Starlette WebSockets, SQLAlchemy async SQLite, Alpaca Python SDK, pytest, pytest-asyncio

---

## File Map

- Modify: `backend/tests/conftest.py`
  - Remove hardcoded Alpaca test credentials and add fixtures for missing-credential tests.
- Create: `backend/tests/test_alpaca_client.py`
  - Verifies lazy import behavior and the new missing-credentials exception.
- Modify: `backend/services/alpaca_client.py`
  - Introduce `AlpacaNotConfiguredError`, lazy SDK creation, and capability helpers.
- Create: `backend/tests/test_degraded_startup.py`
  - Verifies `/api/health` degraded response and no-op stream startup.
- Modify: `backend/services/market_data.py`
  - Make stream lifecycle degraded-safe.
- Modify: `backend/main.py`
  - Report degraded health state.
- Create: `backend/tests/test_bars_cache_degraded.py`
  - Verifies cache-hit returns and cache-miss `503` path prerequisites.
- Modify: `backend/services/bars_cache.py`
  - Make cache sufficiency explicit and only fetch Alpaca when really needed.
- Create: `backend/tests/test_degraded_routes.py`
  - Verifies HTTP `503` mapping and market WebSocket degraded behavior.
- Modify: `backend/routers/market.py`
- Modify: `backend/routers/trading.py`
- Modify: `backend/routers/strategy.py`
- Modify: `backend/routers/backtest.py`
- Modify: `backend/routers/ws.py`
  - Map `AlpacaNotConfiguredError` to `503` or degraded WebSocket status.
- Modify: `AGENTS.md`
  - Document degraded startup behavior and updated smoke-test expectations.

### Task 1: Add lazy Alpaca client primitives and degraded-mode test harness

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_alpaca_client.py`
- Modify: `backend/services/alpaca_client.py`

- [ ] **Step 1: Write the failing degraded-client tests**

```python
# backend/tests/test_alpaca_client.py
import importlib
import sys

import pytest


def _reload_alpaca_client_module():
    sys.modules.pop("services.alpaca_client", None)
    return importlib.import_module("services.alpaca_client")


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_alpaca_client_imports_without_credentials():
    module = _reload_alpaca_client_module()

    assert module.alpaca_client.is_configured() is False


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_alpaca_client_raises_only_on_real_usage():
    module = _reload_alpaca_client_module()

    with pytest.raises(
        module.AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        module.alpaca_client.get_quote("AAPL")
```

- [ ] **Step 2: Update the shared test bootstrap so missing-credential tests are possible**

```python
# backend/tests/conftest.py
import sys
from pathlib import Path

import pytest


backend_dir = Path(__file__).resolve().parents[1]
backend_dir_str = str(backend_dir)
if backend_dir_str not in sys.path:
    sys.path.insert(0, backend_dir_str)


@pytest.fixture
def without_alpaca_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    return None
```

- [ ] **Step 3: Run the tests to verify they fail against the eager client**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_alpaca_client.py -q
```

Expected: fail during import or with `AttributeError` because the client still initializes eagerly and `AlpacaNotConfiguredError` does not exist yet.

- [ ] **Step 4: Implement the lazy client and explicit degraded-mode exception**

```python
# backend/services/alpaca_client.py
from __future__ import annotations

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, PAPER_TRADING


class AlpacaNotConfiguredError(RuntimeError):
    pass


def _timeframe_from_str(tf: str) -> TimeFrame:
    mapping = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "1D": TimeFrame(1, TimeFrameUnit.Day),
    }
    return mapping.get(tf, TimeFrame(1, TimeFrameUnit.Day))


class AlpacaClient:
    def __init__(self):
        self._data_client = None
        self._trading_client = None

    def is_configured(self) -> bool:
        return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    def _get_data_client(self) -> StockHistoricalDataClient:
        self._ensure_configured()
        if self._data_client is None:
            self._data_client = StockHistoricalDataClient(
                ALPACA_API_KEY,
                ALPACA_SECRET_KEY,
            )
        return self._data_client

    def _get_trading_client(self) -> TradingClient:
        self._ensure_configured()
        if self._trading_client is None:
            self._trading_client = TradingClient(
                ALPACA_API_KEY,
                ALPACA_SECRET_KEY,
                paper=PAPER_TRADING,
            )
        return self._trading_client

    def get_bars(self, symbol: str, timeframe: str, start: str, end: str | None = None, limit: int = 200) -> list[dict]:
        tf = _timeframe_from_str(timeframe)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
            feed=DataFeed.IEX,
        )
        bars = self._get_data_client().get_stock_bars(request)
        return [
            {
                "time": bar.timestamp.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
            }
            for bar in bars[symbol]
        ]

    def get_quote(self, symbol: str) -> dict:
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        quote = self._get_data_client().get_stock_latest_quote(request)
        q = quote[symbol]
        return {
            "symbol": symbol,
            "bid": float(q.bid_price),
            "ask": float(q.ask_price),
            "bid_size": int(q.bid_size),
            "ask_size": int(q.ask_size),
            "timestamp": q.timestamp.isoformat(),
        }

    def get_account(self) -> dict:
        account = self._get_trading_client().get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "pnl": float(account.equity) - float(account.last_equity),
            "pnl_pct": (float(account.equity) - float(account.last_equity)) / float(account.last_equity) * 100 if float(account.last_equity) > 0 else 0,
        }

    def get_positions(self) -> list[dict]:
        positions = self._get_trading_client().get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": int(p.qty),
                "avg_entry": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
            }
            for p in positions
        ]

    def submit_order(self, symbol: str, qty: int, side: str) -> dict:
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._get_trading_client().submit_order(request)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": str(order.qty),
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
        }

    def cancel_order(self, order_id: str):
        self._get_trading_client().cancel_order_by_id(order_id)

    def get_orders(self, status: str = "open") -> list[dict]:
        query_status = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
        request = GetOrdersRequest(status=query_status, limit=50)
        orders = self._get_trading_client().get_orders(request)
        return [
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value,
                "qty": str(o.qty),
                "filled_qty": str(o.filled_qty) if o.filled_qty else "0",
                "status": o.status.value,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ]


alpaca_client = AlpacaClient()
```

- [ ] **Step 5: Run the lazy-client tests and existing backend router tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_alpaca_client.py tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 6: Commit the lazy-client foundation**

```bash
git add backend/tests/conftest.py backend/tests/test_alpaca_client.py backend/services/alpaca_client.py
git commit -m "feat: add lazy Alpaca client for degraded mode"
```

### Task 2: Make startup, health, and live-stream lifecycle degraded-safe

**Files:**
- Create: `backend/tests/test_degraded_startup.py`
- Modify: `backend/services/market_data.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing startup and health tests**

```python
# backend/tests/test_degraded_startup.py
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from services import market_data


def _reload_main_module():
    sys.modules.pop("main", None)
    return importlib.import_module("main")


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_health_reports_degraded_without_credentials():
    main = _reload_main_module()

    with TestClient(main.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "alpaca_configured": False,
        "live_stream_enabled": False,
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("without_alpaca_credentials")
async def test_start_stream_is_noop_without_credentials(monkeypatch):
    called = {"value": False}

    def fake_get_stream():
        called["value"] = True
        raise AssertionError("stream should not be created without credentials")

    monkeypatch.setattr(market_data, "_get_stream", fake_get_stream)
    market_data._stream_task = None

    await market_data.start_stream()

    assert called["value"] is False
    assert market_data._stream_task is None
```

- [ ] **Step 2: Run the tests to verify health is still broken**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_degraded_startup.py -q
```

Expected: fail because `/api/health` still returns `{ "status": "ok" }` and `start_stream()` still tries to create a real Alpaca stream.

- [ ] **Step 3: Implement degraded-safe market data lifecycle**

```python
# backend/services/market_data.py
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client


def is_live_stream_enabled() -> bool:
    return alpaca_client.is_configured()


def _get_stream() -> StockDataStream:
    global _stream
    if not alpaca_client.is_configured():
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")
    if _stream is None:
        _stream = StockDataStream(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    return _stream


async def start_stream():
    global _stream_task
    if _stream_task is not None:
        return
    if not alpaca_client.is_configured():
        logger.warning("Alpaca stream disabled: credentials are not configured")
        return
    stream = _get_stream()

    async def _run():
        try:
            await stream._run_forever()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Alpaca stream error")

    _stream_task = asyncio.create_task(_run())
    logger.info("Alpaca data stream started")


async def subscribe(symbol: str, callback):
    symbol = symbol.upper()
    if not alpaca_client.is_configured():
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")
    if symbol not in _callbacks:
        _callbacks[symbol] = []
        stream = _get_stream()
        stream.subscribe_bars(_on_bar, symbol)
        logger.info("Subscribed to bars for %s", symbol)
    _callbacks[symbol].append(callback)


async def unsubscribe(symbol: str, callback):
    symbol = symbol.upper()
    if not alpaca_client.is_configured():
        return
    if symbol in _callbacks:
        try:
            _callbacks[symbol].remove(callback)
        except ValueError:
            pass
        if not _callbacks[symbol]:
            del _callbacks[symbol]
            stream = _get_stream()
            stream.unsubscribe_bars(symbol)
            logger.info("Unsubscribed from bars for %s", symbol)
```

- [ ] **Step 4: Update `/api/health` to report degraded state**

```python
# backend/main.py
from services import market_data
from services.alpaca_client import alpaca_client


@app.get("/api/health")
def health():
    alpaca_configured = alpaca_client.is_configured()
    return {
        "status": "ok" if alpaca_configured else "degraded",
        "alpaca_configured": alpaca_configured,
        "live_stream_enabled": market_data.is_live_stream_enabled(),
    }
```

- [ ] **Step 5: Run startup tests plus a direct health smoke check**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_degraded_startup.py -q
PYTHONPYCACHEPREFIX=/tmp/codex_pycache .venv/bin/python -m compileall -q .
```

Expected:

```text
2 passed
```

and no compile errors.

- [ ] **Step 6: Commit the degraded startup behavior**

```bash
git add backend/tests/test_degraded_startup.py backend/services/market_data.py backend/main.py
git commit -m "feat: report degraded health without Alpaca credentials"
```

### Task 3: Make cached historical bars usable in degraded mode

**Files:**
- Create: `backend/tests/test_bars_cache_degraded.py`
- Modify: `backend/services/bars_cache.py`

- [ ] **Step 1: Write the failing cache-hit and cache-miss tests**

```python
# backend/tests/test_bars_cache_degraded.py
from datetime import datetime, timezone

import pytest

from services import bars_cache
from services.alpaca_client import AlpacaNotConfiguredError


class DummySessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyRow:
    def __init__(self, ts: str, open_: float, high: float, low: float, close: float, volume: int):
        self.timestamp = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


@pytest.mark.asyncio
@pytest.mark.usefixtures("without_alpaca_credentials")
async def test_get_bars_with_cache_returns_cached_rows_without_remote_fetch(monkeypatch):
    cached_rows = [
        DummyRow("2025-01-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        DummyRow("2025-01-02T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        return cached_rows

    async def fake_latest_cached_timestamp(session, symbol, timeframe):
        return cached_rows[-1].timestamp

    monkeypatch.setattr(bars_cache, "async_session", lambda: DummySessionContext())
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache, "_latest_cached_timestamp", fake_latest_cached_timestamp)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remote fetch should not run")))
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)

    result = await bars_cache.get_bars_with_cache(
        symbol="QQQ",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-02",
        limit=2,
    )

    assert len(result) == 2
    assert result[-1]["close"] == 101.5


@pytest.mark.asyncio
@pytest.mark.usefixtures("without_alpaca_credentials")
async def test_get_bars_with_cache_raises_when_remote_fill_is_required(monkeypatch):
    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        return []

    async def fake_latest_cached_timestamp(session, symbol, timeframe):
        return None

    monkeypatch.setattr(bars_cache, "async_session", lambda: DummySessionContext())
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache, "_latest_cached_timestamp", fake_latest_cached_timestamp)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)

    with pytest.raises(
        AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        await bars_cache.get_bars_with_cache(
            symbol="QQQ",
            timeframe="1D",
            start="2025-01-01",
            end="2025-01-31",
            limit=200,
        )
```

- [ ] **Step 2: Run the cache tests to verify degraded-mode semantics do not exist yet**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_bars_cache_degraded.py -q
```

Expected: fail because `bars_cache.get_bars_with_cache()` still attempts remote fetch and silently swallows Alpaca fetch failures.

- [ ] **Step 3: Refactor `bars_cache.py` so cache sufficiency is explicit**

```python
# backend/services/bars_cache.py
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client


async def _latest_cached_timestamp(session, symbol: str, timeframe: str):
    result = await session.execute(
        select(func.max(BarCache.timestamp)).where(
            BarCache.symbol == symbol,
            BarCache.timeframe == timeframe,
        )
    )
    return result.scalar_one_or_none()


async def _read_cached_rows(session, symbol: str, timeframe: str, start_dt, end_dt, limit: int):
    result = await session.execute(
        select(BarCache)
        .where(
            BarCache.symbol == symbol,
            BarCache.timeframe == timeframe,
            BarCache.timestamp >= start_dt,
            BarCache.timestamp <= end_dt,
        )
        .order_by(BarCache.timestamp)
        .limit(limit)
    )
    return result.scalars().all()


def _cache_satisfies_request(rows, end: str | None, end_dt, limit: int) -> bool:
    if not rows:
        return False
    if end is not None:
        last_ts = rows[-1].timestamp
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        return last_ts >= end_dt
    return len(rows) >= limit


async def get_bars_with_cache(symbol: str, timeframe: str, start: str, end: str | None = None, limit: int = 1000) -> list[dict]:
    symbol = symbol.upper()
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else datetime.now(timezone.utc)

    async with async_session() as session:
        cached_rows = await _read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit)
        if _cache_satisfies_request(cached_rows, end, end_dt, limit):
            return [
                {
                    "time": row.timestamp.isoformat(),
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                for row in cached_rows
            ]

        if not alpaca_client.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

        latest_cached = await _latest_cached_timestamp(session, symbol, timeframe)
        api_start = latest_cached.isoformat() if latest_cached is not None else start_dt.isoformat()
        new_bars = alpaca_client.get_bars(symbol, timeframe, api_start, end_dt.isoformat(), limit)
        if new_bars:
            await _upsert_bars(session, symbol, timeframe, new_bars)

        refreshed_rows = await _read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit)
        return [
            {
                "time": row.timestamp.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in refreshed_rows
        ]
```

- [ ] **Step 4: Run the degraded cache tests plus existing strategy/backtest tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_bars_cache_degraded.py tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Commit the cache-aware degraded behavior**

```bash
git add backend/tests/test_bars_cache_degraded.py backend/services/bars_cache.py
git commit -m "feat: allow cache-only historical flows in degraded mode"
```

### Task 4: Map degraded-mode errors to HTTP `503` and WebSocket status

**Files:**
- Create: `backend/tests/test_degraded_routes.py`
- Modify: `backend/routers/market.py`
- Modify: `backend/routers/trading.py`
- Modify: `backend/routers/strategy.py`
- Modify: `backend/routers/backtest.py`
- Modify: `backend/routers/ws.py`

- [ ] **Step 1: Write the failing route and WebSocket tests**

```python
# backend/tests/test_degraded_routes.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from routers import backtest as backtest_router
from routers import market as market_router
from routers import strategy as strategy_router
from routers import trading as trading_router
from routers import ws as ws_router
from services.alpaca_client import AlpacaNotConfiguredError


def build_app():
    app = FastAPI()
    app.include_router(market_router.router)
    app.include_router(trading_router.router)
    app.include_router(strategy_router.router)
    app.include_router(backtest_router.router)
    app.include_router(ws_router.router)
    return app


def test_quote_route_returns_503_when_alpaca_is_unavailable(monkeypatch):
    app = build_app()
    client = TestClient(app)
    monkeypatch.setattr(
        market_router.alpaca_client,
        "get_quote",
        lambda symbol: (_ for _ in ()).throw(AlpacaNotConfiguredError("Alpaca credentials are not configured")),
    )

    response = client.get("/api/market/quote/AAPL")

    assert response.status_code == 503
    assert response.json()["detail"] == "Alpaca credentials are not configured"


def test_market_bars_route_returns_503_when_cache_needs_alpaca(monkeypatch):
    app = build_app()
    client = TestClient(app)

    async def fake_get_bars_with_cache(*args, **kwargs):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(market_router, "get_bars_with_cache", fake_get_bars_with_cache)
    response = client.get("/api/market/bars/QQQ", params={"timeframe": "1D", "start": "2025-01-01", "limit": 200})

    assert response.status_code == 503


def test_trading_account_route_returns_503_when_alpaca_is_unavailable(monkeypatch):
    app = build_app()
    client = TestClient(app)
    monkeypatch.setattr(
        trading_router.alpaca_client,
        "get_account",
        lambda: (_ for _ in ()).throw(AlpacaNotConfiguredError("Alpaca credentials are not configured")),
    )

    response = client.get("/api/trading/account")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_strategy_route_returns_503_when_analysis_bars_need_alpaca(monkeypatch):
    async def fake_get_analysis_bars(*args, **kwargs):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(strategy_router, "get_analysis_bars", fake_get_analysis_bars)
    req = strategy_router.RunStrategyRequest(name="ma_crossover", symbol="QQQ", timeframe="1D", start="2025-01-01")

    with pytest.raises(strategy_router.HTTPException) as excinfo:
        await strategy_router.get_signals(req)

    assert excinfo.value.status_code == 503


def test_market_websocket_sends_degraded_status_and_closes(monkeypatch):
    app = build_app()
    client = TestClient(app)

    async def fake_subscribe(symbol, callback):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(ws_router.market_data, "subscribe", fake_subscribe)

    with client.websocket_connect("/ws/market/QQQ") as websocket:
        assert websocket.receive_json() == {
            "type": "status",
            "status": "degraded",
            "reason": "alpaca_not_configured",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


@pytest.mark.asyncio
async def test_backtest_route_returns_503_when_analysis_bars_need_alpaca(monkeypatch):
    async def fake_get_analysis_bars(*args, **kwargs):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(backtest_router, "get_analysis_bars", fake_get_analysis_bars)
    req = backtest_router.BacktestRequest(
        strategy="brooks_pullback_count",
        symbol="QQQ",
        timeframe="1D",
        start="2025-01-01",
    )

    with pytest.raises(backtest_router.HTTPException) as excinfo:
        await backtest_router.run_backtest_api(req)

    assert excinfo.value.status_code == 503
```

- [ ] **Step 2: Run the route tests to verify the routers still leak raw service failures**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_degraded_routes.py -q
```

Expected: fail because the routers do not yet map `AlpacaNotConfiguredError` to `503`, and the market WebSocket does not send degraded status.

- [ ] **Step 3: Implement consistent HTTP `503` mapping and WebSocket degraded status**

```python
# backend/routers/market.py
from fastapi import APIRouter, HTTPException, Query
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client


@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    timeframe: str = Query("1D", regex="^(1m|5m|15m|1h|1D)$"),
    start: str = Query(..., description="Start date ISO format, e.g. 2024-01-01"),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        bars = await get_bars_with_cache(symbol, timeframe, start, end, limit)
        return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": bars}
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))


@router.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        return alpaca_client.get_quote(symbol.upper())
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))
```

```python
# backend/routers/trading.py
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client


@router.get("/account")
def get_account():
    try:
        return alpaca_client.get_account()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))


@router.get("/positions")
def get_positions():
    try:
        return alpaca_client.get_positions()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))


@router.get("/orders")
def get_orders(status: str = "open"):
    try:
        return alpaca_client.get_orders(status)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))


@router.post("/order")
async def submit_order(req: OrderRequest):
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if req.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    try:
        return await execute_order(req.symbol, req.qty, req.side)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    try:
        alpaca_client.cancel_order(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))
```

```python
# backend/routers/strategy.py and backend/routers/backtest.py
from services.alpaca_client import AlpacaNotConfiguredError

@router.post("/signals")
async def get_signals(req: RunStrategyRequest):
    try:
        symbol = req.symbol.upper()
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            limit=req.limit,
        )
        if not bars:
            raise HTTPException(400, "No bar data returned")
        signals = run_strategy(req.name, symbol, bars, req.params)
        return {"strategy": req.name, "symbol": symbol, "signals": signals}
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/run")
async def run_backtest_api(req: BacktestRequest):
    try:
        symbol = req.symbol.upper()
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            limit=req.limit,
        )
        if not bars:
            raise HTTPException(400, "No bar data returned")
        strategy = get_strategy(req.strategy, req.params)
        signals = strategy.generate_signals(symbol, bars)
        result = run_backtest(
            strategy_name=req.strategy,
            signals=signals,
            bars=bars,
            initial_capital=req.initial_capital,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            risk_per_trade_pct=req.risk_per_trade_pct,
            symbol=symbol,
            timeframe=req.timeframe,
        )
        return result.to_dict()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(503, str(exc))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
```

```python
# backend/routers/ws.py
from services.alpaca_client import AlpacaNotConfiguredError


@router.websocket("/ws/market/{symbol}")
async def market_ws(websocket: WebSocket, symbol: str):
    await websocket.accept()
    symbol = symbol.upper()
    _market_subscribers.setdefault(symbol, set()).add(websocket)

    try:
        await market_data.subscribe(symbol, _broadcast_bar)
    except AlpacaNotConfiguredError:
        await websocket.send_json(
            {
                "type": "status",
                "status": "degraded",
                "reason": "alpaca_not_configured",
            }
        )
        _market_subscribers.get(symbol, set()).discard(websocket)
        await websocket.close(code=1013)
        if not _market_subscribers.get(symbol):
            _market_subscribers.pop(symbol, None)
        return

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
```

- [ ] **Step 4: Run all degraded route tests plus the existing backend suite**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_alpaca_client.py tests/test_degraded_startup.py tests/test_bars_cache_degraded.py tests/test_degraded_routes.py tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
18 passed
```

- [ ] **Step 5: Commit the degraded router behavior**

```bash
git add backend/tests/test_degraded_routes.py backend/routers/market.py backend/routers/trading.py backend/routers/strategy.py backend/routers/backtest.py backend/routers/ws.py
git commit -m "feat: return degraded responses when Alpaca is unavailable"
```

### Task 5: Update repo docs and run final verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the repo guidance for degraded startup**

```markdown
## Current Realities And Gaps

- The backend now supports degraded startup without Alpaca credentials.
- `/api/health` reports `degraded` with `alpaca_configured=false` when credentials are missing.
- Cache-backed historical endpoints can still work when local bars already exist, but quote, live-stream, and trading endpoints return `503` until Alpaca is configured.
- `backend/.env` is optional for local UI work, but missing Alpaca credentials disables live market data and all trading/account endpoints.
```

- [ ] **Step 2: Run the full backend verification and frontend static checks**

Run:

```bash
cd backend
PYTHONPYCACHEPREFIX=/tmp/codex_pycache .venv/bin/python -m compileall -q .
.venv/bin/python -m pytest tests/test_alpaca_client.py tests/test_degraded_startup.py tests/test_bars_cache_degraded.py tests/test_degraded_routes.py tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q

cd ../frontend
npm run lint
npm run build
```

Expected:

```text
18 passed
```

and successful frontend lint/build output.

- [ ] **Step 3: Run the no-credentials smoke check**

Run:

```bash
cd backend
env -u ALPACA_API_KEY -u ALPACA_SECRET_KEY .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
curl -s http://127.0.0.1:8000/api/health
```

Expected response:

```json
{"status":"degraded","alpaca_configured":false,"live_stream_enabled":false}
```

- [ ] **Step 4: Commit the docs update and verification checkpoint**

```bash
git add AGENTS.md
git commit -m "docs: describe degraded Alpaca startup behavior"
```

## Self-Review

- Spec coverage:
  - lazy client and explicit error model are covered in Task 1
  - degraded health and startup lifecycle are covered in Task 2
  - `A1` cache-hit/cache-miss historical semantics are covered in Task 3
  - HTTP `503` and WebSocket degraded status are covered in Task 4
  - docs and final smoke verification are covered in Task 5
- Placeholder scan:
  - no `TBD`, `TODO`, or cross-task “similar to Task N” shortcuts remain
- Type consistency:
  - the plan consistently uses `AlpacaNotConfiguredError`, `is_configured()`, and `is_live_stream_enabled()`
