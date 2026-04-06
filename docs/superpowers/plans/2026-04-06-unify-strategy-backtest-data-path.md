# Unified Strategy and Backtest Data Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/strategy/signals` and `/api/backtest/run` load historical bars through the same backend service so identical inputs produce identical historical bar sets.

**Architecture:** Introduce a small shared `analysis_bars` service that wraps the existing cached historical-bar path, then migrate both routers to call it. Keep the current product split between `Trade` and `Backtest` UI flows, but align backend request semantics by giving both routes the same `symbol`, `timeframe`, `start`, `end`, and `limit` shape with a shared default limit.

**Tech Stack:** FastAPI, Pydantic, SQLite/SQLAlchemy, Alpaca historical data client, pytest, pytest-asyncio

---

### Task 1: Add a shared historical bar-loading service and test harness

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `backend/services/analysis_bars.py`
- Create: `backend/tests/test_analysis_bars.py`

- [ ] **Step 1: Create backend test dependencies**

```txt
-r requirements.txt
pytest==8.3.5
pytest-asyncio==0.25.3
```

- [ ] **Step 2: Write the failing shared-service tests**

```python
import pytest

from services import analysis_bars


@pytest.mark.asyncio
async def test_get_analysis_bars_uppercases_symbol_and_forwards_arguments(monkeypatch):
    captured = {}
    expected = [
        {
            "time": "2025-01-02T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "volume": 123456,
        }
    ]

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        captured.update(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        return expected

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    result = await analysis_bars.get_analysis_bars(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-31",
        limit=250,
    )

    assert result == expected
    assert captured == {
        "symbol": "QQQ",
        "timeframe": "1D",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 250,
    }


@pytest.mark.asyncio
async def test_get_analysis_bars_uses_default_limit(monkeypatch):
    captured = {}

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    await analysis_bars.get_analysis_bars(
        symbol="spy",
        timeframe="1D",
        start="2025-01-01",
    )

    assert captured["limit"] == analysis_bars.DEFAULT_ANALYSIS_BAR_LIMIT
```

- [ ] **Step 3: Install dev dependencies and run the tests to verify they fail**

Run:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/test_analysis_bars.py -q
```

Expected: failure with `ModuleNotFoundError: No module named 'services.analysis_bars'`.

- [ ] **Step 4: Write the minimal shared service**

```python
from __future__ import annotations

from services.bars_cache import get_bars_with_cache

DEFAULT_ANALYSIS_BAR_LIMIT = 1000


async def get_analysis_bars(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
) -> list[dict]:
    return await get_bars_with_cache(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_analysis_bars.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit the shared service**

```bash
git add backend/requirements-dev.txt backend/services/analysis_bars.py backend/tests/test_analysis_bars.py
git commit -m "test: add shared analysis bars service"
```

### Task 2: Move the strategy route onto the shared service

**Files:**
- Modify: `backend/routers/strategy.py`
- Create: `backend/tests/test_strategy_router.py`

- [ ] **Step 1: Write the failing strategy route tests**

```python
import pytest
from fastapi import HTTPException

from routers import strategy as strategy_router


@pytest.mark.asyncio
async def test_get_signals_uses_analysis_bars_service(monkeypatch):
    bars = [
        {
            "time": "2025-01-02T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 123456,
        }
    ]
    signals = [
        {
            "symbol": "QQQ",
            "signal_type": "buy",
            "price": 100.5,
            "quantity": 1,
            "reason": "test-signal",
            "timestamp": "2025-01-02T00:00:00+00:00",
        }
    ]
    captured = {}

    async def fake_get_analysis_bars(symbol, timeframe, start, end=None, limit=1000):
        captured["bars_request"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
        }
        return bars

    def fake_run_strategy(name, symbol, incoming_bars, params=None):
        captured["strategy_request"] = {
            "name": name,
            "symbol": symbol,
            "bars": incoming_bars,
            "params": params,
        }
        return signals

    monkeypatch.setattr(strategy_router, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(strategy_router, "run_strategy", fake_run_strategy)

    req = strategy_router.RunStrategyRequest(
        name="ma_crossover",
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-31",
        limit=250,
        params={"short_period": 10, "long_period": 30},
    )

    result = await strategy_router.get_signals(req)

    assert result == {
        "strategy": "ma_crossover",
        "symbol": "QQQ",
        "signals": signals,
    }
    assert captured["bars_request"] == {
        "symbol": "QQQ",
        "timeframe": "1D",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 250,
    }
    assert captured["strategy_request"] == {
        "name": "ma_crossover",
        "symbol": "QQQ",
        "bars": bars,
        "params": {"short_period": 10, "long_period": 30},
    }


@pytest.mark.asyncio
async def test_get_signals_returns_400_when_no_bars(monkeypatch):
    async def fake_get_analysis_bars(symbol, timeframe, start, end=None, limit=1000):
        return []

    monkeypatch.setattr(strategy_router, "get_analysis_bars", fake_get_analysis_bars)

    req = strategy_router.RunStrategyRequest(
        name="ma_crossover",
        symbol="QQQ",
        timeframe="1D",
        start="2025-01-01",
    )

    with pytest.raises(HTTPException) as excinfo:
        await strategy_router.get_signals(req)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "No bar data returned"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_strategy_router.py -q
```

Expected: failure because `RunStrategyRequest` does not yet accept `end` and `limit`, and the route is still synchronous and not calling `get_analysis_bars`.

- [ ] **Step 3: Update the strategy route to use the shared service**

```python
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.analysis_bars import DEFAULT_ANALYSIS_BAR_LIMIT, get_analysis_bars
from services.strategy_engine import list_strategies, run_strategy

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class RunStrategyRequest(BaseModel):
    name: str
    symbol: str
    timeframe: str = "1D"
    start: str = "2024-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=1000)
    params: Optional[Dict[str, Any]] = None


@router.get("/list")
def get_strategies():
    return list_strategies()


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
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_strategy_router.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the strategy route migration**

```bash
git add backend/routers/strategy.py backend/tests/test_strategy_router.py
git commit -m "feat: align strategy signals data path"
```

### Task 3: Move the backtest route onto the shared service

**Files:**
- Modify: `backend/routers/backtest.py`
- Create: `backend/tests/test_backtest_router.py`

- [ ] **Step 1: Write the failing backtest route tests**

```python
import pytest
from fastapi import HTTPException

from routers import backtest as backtest_router


class DummyStrategy:
    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, symbol, bars):
        return self._signals


class DummyBacktestResult:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


@pytest.mark.asyncio
async def test_run_backtest_uses_analysis_bars_service(monkeypatch):
    bars = [
        {
            "time": "2025-01-02T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 123456,
        }
    ]
    captured = {}

    async def fake_get_analysis_bars(symbol, timeframe, start, end=None, limit=1000):
        captured["bars_request"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
        }
        return bars

    def fake_get_strategy(name, params=None):
        captured["get_strategy"] = {"name": name, "params": params}
        return DummyStrategy(["BUY_SIGNAL"])

    def fake_run_backtest(**kwargs):
        captured["run_backtest"] = kwargs
        return DummyBacktestResult(
            {
                "strategy": kwargs["strategy_name"],
                "symbol": kwargs["symbol"],
                "timeframe": kwargs["timeframe"],
                "period": "2025-01-01 ~ 2025-01-31",
                "initial_capital": kwargs["initial_capital"],
                "final_capital": kwargs["initial_capital"],
                "total_return": 0.0,
                "total_return_pct": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "trades": [],
                "equity_curve": [],
            }
        )

    monkeypatch.setattr(backtest_router, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(backtest_router, "get_strategy", fake_get_strategy)
    monkeypatch.setattr(backtest_router, "run_backtest", fake_run_backtest)

    req = backtest_router.BacktestRequest(
        strategy="brooks_pullback_count",
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-31",
        limit=250,
        params={"ema_period": 20, "quantity": 1},
        initial_capital=100000.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        risk_per_trade_pct=2.0,
    )

    result = await backtest_router.run_backtest_api(req)

    assert result["strategy"] == "brooks_pullback_count"
    assert result["symbol"] == "QQQ"
    assert captured["bars_request"] == {
        "symbol": "QQQ",
        "timeframe": "1D",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 250,
    }
    assert captured["get_strategy"] == {
        "name": "brooks_pullback_count",
        "params": {"ema_period": 20, "quantity": 1},
    }
    assert captured["run_backtest"]["strategy_name"] == "brooks_pullback_count"
    assert captured["run_backtest"]["symbol"] == "QQQ"
    assert captured["run_backtest"]["bars"] == bars
    assert captured["run_backtest"]["signals"] == ["BUY_SIGNAL"]


@pytest.mark.asyncio
async def test_run_backtest_returns_400_when_no_bars(monkeypatch):
    async def fake_get_analysis_bars(symbol, timeframe, start, end=None, limit=1000):
        return []

    monkeypatch.setattr(backtest_router, "get_analysis_bars", fake_get_analysis_bars)

    req = backtest_router.BacktestRequest(
        strategy="brooks_pullback_count",
        symbol="QQQ",
        timeframe="1D",
        start="2025-01-01",
    )

    with pytest.raises(HTTPException) as excinfo:
        await backtest_router.run_backtest_api(req)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "No bar data returned"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_backtest_router.py -q
```

Expected: failure because `BacktestRequest` does not yet accept `limit` and the route still imports `get_bars_with_cache` directly.

- [ ] **Step 3: Update the backtest route to use the shared service**

```python
from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.analysis_bars import DEFAULT_ANALYSIS_BAR_LIMIT, get_analysis_bars
from services.strategy_engine import get_strategy
from services.backtester import run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "QQQ"
    timeframe: str = "1D"
    start: str = "2025-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=1000)
    params: Optional[Dict[str, Any]] = None
    initial_capital: float = 100000.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    risk_per_trade_pct: float = 2.0


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
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Backtest failed: {str(e)}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_backtest_router.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the backtest route migration**

```bash
git add backend/routers/backtest.py backend/tests/test_backtest_router.py
git commit -m "feat: align backtest data path"
```

### Task 4: Update repo guidance and run the full regression set

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update repo guidance to mention the shared analysis-bar path**

```md
- `backend/services/analysis_bars.py` is the shared historical bar-loading path for `/api/strategy/signals` and `/api/backtest/run`.
```

- [ ] **Step 2: Run the full backend verification set**

Run:

```bash
cd backend
PYTHONPYCACHEPREFIX=/tmp/codex_pycache .venv/bin/python -m compileall -q .
.venv/bin/python -m pytest tests/test_analysis_bars.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 3: Commit the docs and verification completion**

```bash
git add AGENTS.md
git commit -m "docs: document aligned historical bars path"
```
