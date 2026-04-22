# QQQ 5-Minute Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first trustworthy `QQQ 5m` validation loop by adding a fixed `qqq_5m_phase1` research profile, fixing intraday backtest semantics, and wiring the UI to run that constrained path end-to-end.

**Architecture:** Introduce one small backend `research_profile` module that owns the phase-1 rules instead of scattering session, long-only, and day-flat logic across routers and UI code. Use that shared profile in `analysis_bars` for RTH filtering and in `backtester` for execution rules, then pass the profile explicitly through the strategy/backtest APIs and lock the frontend backtest lab onto the `QQQ 5m` path.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, SQLAlchemy/SQLite historical bars cache, React, TypeScript, Axios, pytest, pytest-asyncio

---

## File Map

- `backend/services/research_profile.py`
  Owns the named `qqq_5m_phase1` profile and helper functions for RTH filtering, session grouping, opening-bar counting, and entry-cutoff checks.
- `backend/services/analysis_bars.py`
  Loads cached historical bars and optionally filters them through a research profile before strategies and backtests use them.
- `backend/services/backtester.py`
  Applies exact timestamp matching, long-only enforcement, opening-bar skip, entry cutoff, and day-flat exits for the selected research profile.
- `backend/routers/strategy.py`
  Accepts `research_profile` on strategy scan requests and forwards it into `analysis_bars`.
- `backend/routers/backtest.py`
  Accepts `research_profile` on backtest requests and forwards it into both `analysis_bars` and `run_backtest`.
- `backend/tests/test_analysis_bars.py`
  Verifies `analysis_bars` still forwards arguments correctly and now applies RTH filtering for the named research profile.
- `backend/tests/test_strategy_router.py`
  Verifies the strategy route forwards `research_profile` to `analysis_bars`.
- `backend/tests/test_backtest_router.py`
  Verifies the backtest route forwards `research_profile` into both bar loading and execution.
- `backend/tests/test_backtester_intraday.py`
  New test file for exact intraday alignment, long-only rejection of short signals, opening-bar skip, entry cutoff, and day-flat flattening.
- `frontend/src/types/index.ts`
  Adds the `ResearchProfile` type used by the API helpers and backtest UI.
- `frontend/src/services/api.ts`
  Adds optional `research_profile` support to `getSignals` and `runBacktest`.
- `frontend/src/components/BacktestPanel.tsx`
  Locks the backtest lab to `QQQ 5m`, sets the named research profile, and activates the chart context before a run.
- `frontend/src/App.tsx`
  Starts the workspace on `QQQ 5m` and provides the callback that keeps the chart aligned with the research context.

### Task 1: Add the shared `qqq_5m_phase1` research profile and RTH analysis-bar filtering

**Files:**
- Create: `backend/services/research_profile.py`
- Modify: `backend/services/analysis_bars.py`
- Modify: `backend/tests/test_analysis_bars.py`

- [ ] **Step 1: Extend the analysis-bars tests with profile-based RTH filtering**

```python
import pytest

from services import analysis_bars


@pytest.mark.asyncio
async def test_get_analysis_bars_filters_to_rth_for_qqq_5m_phase1(monkeypatch):
    raw_bars = [
        {
            "time": "2025-01-06T14:25:00+00:00",
            "open": 498.0,
            "high": 499.0,
            "low": 497.5,
            "close": 498.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 498.5,
            "high": 499.5,
            "low": 498.0,
            "close": 499.0,
            "volume": 1200,
        },
        {
            "time": "2025-01-06T20:55:00+00:00",
            "open": 501.0,
            "high": 501.5,
            "low": 500.5,
            "close": 501.2,
            "volume": 1400,
        },
        {
            "time": "2025-01-06T21:00:00+00:00",
            "open": 501.2,
            "high": 501.4,
            "low": 500.8,
            "close": 501.0,
            "volume": 900,
        },
    ]

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        return raw_bars

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    result = await analysis_bars.get_analysis_bars(
        symbol="qqq",
        timeframe="5m",
        start="2025-01-06",
        research_profile="qqq_5m_phase1",
    )

    assert [bar["time"] for bar in result] == [
        "2025-01-06T14:30:00+00:00",
        "2025-01-06T20:55:00+00:00",
    ]


@pytest.mark.asyncio
async def test_get_analysis_bars_rejects_unknown_research_profile(monkeypatch):
    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        return []

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    with pytest.raises(ValueError, match="Unknown research profile"):
        await analysis_bars.get_analysis_bars(
            symbol="qqq",
            timeframe="5m",
            start="2025-01-06",
            research_profile="unknown_profile",
        )
```

- [ ] **Step 2: Run the analysis-bars tests to verify the new cases fail**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_analysis_bars.py -q
```

Expected: failure because `get_analysis_bars()` does not accept `research_profile` yet.

- [ ] **Step 3: Add the research profile module and thread it into `analysis_bars`**

`backend/services/research_profile.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class ResearchProfile:
    name: str
    session: str
    long_only: bool
    skip_opening_bars: int
    entry_cutoff: time | None
    flatten_daily: bool


def get_research_profile(name: str | None) -> ResearchProfile | None:
    if name is None:
        return None
    if name == "qqq_5m_phase1":
        return ResearchProfile(
            name=name,
            session="rth",
            long_only=True,
            skip_opening_bars=2,
            entry_cutoff=time(15, 30),
            flatten_daily=True,
        )
    raise ValueError(f"Unknown research profile: {name}")


def filter_bars_for_research_profile(
    bars: list[dict], research_profile: str | None
) -> list[dict]:
    profile = get_research_profile(research_profile)
    if profile is None or profile.session != "rth":
        return bars
    return [bar for bar in bars if _is_rth_bar(bar["time"])]


def market_time(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(MARKET_TZ)


def session_day(timestamp: str) -> str:
    return market_time(timestamp).date().isoformat()


def _is_rth_bar(timestamp: str) -> bool:
    local = market_time(timestamp)
    local_time = local.time()
    return local.weekday() < 5 and RTH_OPEN <= local_time < RTH_CLOSE
```

`backend/services/analysis_bars.py`

```python
from __future__ import annotations

from services.bars_cache import get_bars_with_cache
from services.research_profile import filter_bars_for_research_profile

MAX_ANALYSIS_BAR_LIMIT = 1000
DEFAULT_ANALYSIS_BAR_LIMIT = MAX_ANALYSIS_BAR_LIMIT


async def get_analysis_bars(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
    research_profile: str | None = None,
) -> list[dict]:
    bars = await get_bars_with_cache(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )
    return filter_bars_for_research_profile(bars, research_profile)
```

- [ ] **Step 4: Re-run the analysis-bars tests to verify they pass**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_analysis_bars.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit the research-profile filtering slice**

```bash
cd /Users/bytedance/personalProject/AL_price_action
git add backend/services/research_profile.py backend/services/analysis_bars.py backend/tests/test_analysis_bars.py
git commit -m "feat: add QQQ 5m research profile filtering"
```

### Task 2: Fix intraday backtest semantics for exact timestamps, long-only, opening-bar skip, cutoff, and day-flat exits

**Files:**
- Modify: `backend/services/backtester.py`
- Create: `backend/tests/test_backtester_intraday.py`
- Use: `backend/services/research_profile.py`

- [ ] **Step 1: Add failing intraday backtester tests**

`backend/tests/test_backtester_intraday.py`

```python
from datetime import datetime

from services.backtester import run_backtest
from strategies.base import Signal, SignalType


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


def test_run_backtest_uses_exact_intraday_signal_timestamp():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.8, 500.0, 500.7),
        _bar("2025-01-06T14:40:00+00:00", 500.7, 501.0, 500.6, 500.9),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.0, 500.6, 500.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.9,
            quantity=1,
            reason="timestamp-match",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_breakout_pullback",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"


def test_run_backtest_ignores_short_signals_for_long_only_profile():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 499.8, 500.0),
        _bar("2025-01-06T14:40:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T20:55:00+00:00", 500.0, 500.1, 499.7, 499.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.SELL,
            price=500.0,
            quantity=1,
            reason="short-not-allowed",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_pullback_count",
        signals=signals,
        bars=bars,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 0


def test_run_backtest_skips_opening_bars_enforces_cutoff_and_flattens_daily():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T14:40:00+00:00", 500.2, 500.7, 500.1, 500.6),
        _bar("2025-01-06T20:35:00+00:00", 500.6, 500.8, 500.5, 500.7),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.0, 500.6, 500.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.2,
            quantity=1,
            reason="skip-open",
            timestamp=datetime.fromisoformat("2025-01-06T14:35:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.6,
            quantity=1,
            reason="valid-entry",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.7,
            quantity=1,
            reason="after-cutoff",
            timestamp=datetime.fromisoformat("2025-01-06T20:35:00+00:00"),
        ),
    ]

    result = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"
    assert result.trades[0]["exit_time"] == "2025-01-06T20:55:00+00:00"
    assert result.trades[0]["exit_reason"] == "session_close"
```

- [ ] **Step 2: Run the new backtester tests to verify they fail**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_backtester_intraday.py -q
```

Expected: failure because `run_backtest()` does not accept `research_profile` and still matches by date only.

- [ ] **Step 3: Implement the minimal intraday execution rules**

`backend/services/backtester.py`

```python
from services.research_profile import get_research_profile, session_day, market_time


def _bars_by_session(bars: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for bar in bars:
        grouped.setdefault(session_day(bar["time"]), []).append(bar["time"])
    return grouped


def _close_position(position: dict, exit_time: str, exit_price: float, exit_reason: str) -> TradeRecord:
    pnl = (exit_price - position["entry_price"]) * position["qty"]
    pnl_pct = pnl / (position["entry_price"] * position["qty"]) * 100
    return TradeRecord(
        entry_time=position["entry_time"],
        exit_time=exit_time,
        side=position["side"],
        entry_price=position["entry_price"],
        exit_price=exit_price,
        stop_loss=position["stop"],
        quantity=position["qty"],
        pnl=pnl,
        pnl_pct=pnl_pct,
        reason=position["reason"],
        exit_reason=exit_reason,
    )


def run_backtest(
    strategy_name: str,
    signals: list[Signal],
    bars: list[dict],
    initial_capital: float = 100000.0,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    risk_per_trade_pct: float = 2.0,
    symbol: str = "QQQ",
    timeframe: str = "1D",
    research_profile: str | None = None,
) -> BacktestResult:
    profile = get_research_profile(research_profile)
    session_bars = _bars_by_session(bars)
    signal_by_time: dict[str, list[Signal]] = {}
    for sig in sorted(signals, key=lambda s: s.timestamp):
        signal_by_time.setdefault(sig.timestamp.isoformat(), []).append(sig)
```

```python
    for i, bar in enumerate(bars):
        current_time = bar["time"]
        current_session = session_day(current_time)
        bar_times = session_bars[current_session]
        bar_index = bar_times.index(current_time)
        is_last_bar_of_session = current_time == bar_times[-1]

        if position is not None:
            hit_stop = bar["low"] <= position["stop"]
            hit_target = bar["high"] >= position["target"]
            if hit_stop or hit_target:
                exit_price = position["stop"] if hit_stop else position["target"]
                closed = _close_position(
                    position,
                    exit_time=current_time,
                    exit_price=exit_price,
                    exit_reason="stop_loss" if hit_stop else "take_profit",
                )
                trades.append(closed)
                capital += closed.pnl
                position = None

        if (
            position is None
            and current_time in signal_by_time
            and not (profile and bar_index < profile.skip_opening_bars)
            and not (
                profile
                and profile.entry_cutoff is not None
                and market_time(current_time).time() > profile.entry_cutoff
            )
        ):
            for sig in signal_by_time[current_time]:
                if profile and profile.long_only and sig.signal_type != SignalType.BUY:
                    continue
                if sig.signal_type not in (SignalType.BUY, SignalType.SELL):
                    continue
                entry_price = sig.price
                risk_amount = capital * (risk_per_trade_pct / 100.0)
                stop_distance = entry_price * (stop_loss_pct / 100.0)
                qty = max(1, int(risk_amount / stop_distance))
                position = {
                    "side": "long" if sig.signal_type == SignalType.BUY else "short",
                    "entry_price": entry_price,
                    "stop": entry_price * (1 - stop_loss_pct / 100.0)
                    if sig.signal_type == SignalType.BUY
                    else entry_price * (1 + stop_loss_pct / 100.0),
                    "target": entry_price * (1 + take_profit_pct / 100.0)
                    if sig.signal_type == SignalType.BUY
                    else entry_price * (1 - take_profit_pct / 100.0),
                    "qty": qty,
                    "entry_time": current_time,
                    "reason": sig.reason,
                }
                break

        if position is not None and profile and profile.flatten_daily and is_last_bar_of_session:
            closed = _close_position(
                position,
                exit_time=current_time,
                exit_price=bar["close"],
                exit_reason="session_close",
            )
            trades.append(closed)
            capital += closed.pnl
            position = None
```

Keep the rest of the existing stop/target and equity-curve logic unchanged unless needed to support the new profile parameter.

- [ ] **Step 4: Re-run the intraday backtester tests**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_backtester_intraday.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit the intraday backtester slice**

```bash
cd /Users/bytedance/personalProject/AL_price_action
git add backend/services/backtester.py backend/tests/test_backtester_intraday.py
git commit -m "feat: enforce QQQ 5m intraday backtest rules"
```

### Task 3: Pass `research_profile` through the strategy and backtest routers

**Files:**
- Modify: `backend/routers/strategy.py`
- Modify: `backend/routers/backtest.py`
- Modify: `backend/tests/test_strategy_router.py`
- Modify: `backend/tests/test_backtest_router.py`

- [ ] **Step 1: Add failing router tests for `research_profile` forwarding**

`backend/tests/test_strategy_router.py`

```python
@pytest.mark.asyncio
async def test_get_signals_forwards_research_profile(monkeypatch):
    bars = [
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 500.0,
            "high": 500.5,
            "low": 499.8,
            "close": 500.2,
            "volume": 1000,
        }
    ]
    captured = {}

    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        captured["research_profile"] = research_profile
        return bars

    monkeypatch.setattr(strategy_router, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(strategy_router, "run_strategy", lambda *args, **kwargs: [])

    req = strategy_router.RunStrategyRequest(
        name="brooks_breakout_pullback",
        symbol="qqq",
        timeframe="5m",
        start="2025-01-06",
        research_profile="qqq_5m_phase1",
    )

    await strategy_router.get_signals(req)

    assert captured["research_profile"] == "qqq_5m_phase1"
```

`backend/tests/test_backtest_router.py`

```python
@pytest.mark.asyncio
async def test_run_backtest_forwards_research_profile(monkeypatch):
    bars = [
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 500.0,
            "high": 500.5,
            "low": 499.8,
            "close": 500.2,
            "volume": 1000,
        }
    ]
    captured = {}

    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        captured["bars_profile"] = research_profile
        return bars

    def fake_get_strategy(name, params=None):
        return DummyStrategy([])

    def fake_run_backtest(**kwargs):
        captured["run_backtest_profile"] = kwargs["research_profile"]
        return DummyBacktestResult({"strategy": kwargs["strategy_name"], "symbol": kwargs["symbol"]})

    monkeypatch.setattr(backtest_router, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(backtest_router, "get_strategy", fake_get_strategy)
    monkeypatch.setattr(backtest_router, "run_backtest", fake_run_backtest)

    req = backtest_router.BacktestRequest(
        strategy="brooks_breakout_pullback",
        symbol="qqq",
        timeframe="5m",
        start="2025-01-06",
        research_profile="qqq_5m_phase1",
    )

    await backtest_router.run_backtest_api(req)

    assert captured["bars_profile"] == "qqq_5m_phase1"
    assert captured["run_backtest_profile"] == "qqq_5m_phase1"
```

- [ ] **Step 2: Run the router tests to verify they fail**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected: failures because the request models and service calls do not accept `research_profile`.

- [ ] **Step 3: Add the request field and forward it end-to-end**

`backend/routers/strategy.py`

```python
class RunStrategyRequest(BaseModel):
    name: str
    symbol: str
    timeframe: str = "1D"
    start: str = "2024-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=MAX_ANALYSIS_BAR_LIMIT)
    params: Optional[Dict[str, Any]] = None
    research_profile: str | None = None
```

```python
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            limit=req.limit,
            research_profile=req.research_profile,
        )
```

`backend/routers/backtest.py`

```python
class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "QQQ"
    timeframe: str = "1D"
    start: str = "2025-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=MAX_ANALYSIS_BAR_LIMIT)
    params: Optional[Dict[str, Any]] = None
    initial_capital: float = 100000.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    risk_per_trade_pct: float = 2.0
    research_profile: str | None = None
```

```python
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            limit=req.limit,
            research_profile=req.research_profile,
        )
```

```python
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
            research_profile=req.research_profile,
        )
```

- [ ] **Step 4: Re-run the router tests**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit the router wiring slice**

```bash
cd /Users/bytedance/personalProject/AL_price_action
git add backend/routers/strategy.py backend/routers/backtest.py backend/tests/test_strategy_router.py backend/tests/test_backtest_router.py
git commit -m "feat: thread research profiles through analysis routes"
```

### Task 4: Lock the frontend backtest lab to the `QQQ 5m` research path and align the chart context

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/BacktestPanel.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update the frontend types and API helpers**

`frontend/src/types/index.ts`

```ts
export type ResearchProfile = "qqq_5m_phase1";
```

`frontend/src/services/api.ts`

```ts
import type {
  Account,
  BacktestResult,
  Bar,
  DataSnapshot,
  Order,
  Position,
  ResearchProfile,
  Signal,
  StrategyInfo,
} from "../types";
```

```ts
export async function getSignals(
  name: string,
  symbol: string,
  timeframe: string,
  start: string,
  params?: Record<string, unknown>,
  researchProfile?: ResearchProfile,
): Promise<Signal[]> {
  const { data } = await api.post("/strategy/signals", {
    name,
    symbol,
    timeframe,
    start,
    params,
    research_profile: researchProfile,
  });
  return data.signals;
}
```

```ts
export async function runBacktest(req: {
  strategy: string;
  symbol: string;
  timeframe: string;
  start: string;
  end?: string;
  params?: Record<string, unknown>;
  initial_capital: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  risk_per_trade_pct: number;
  research_profile?: ResearchProfile;
}): Promise<BacktestResult> {
  const { data } = await api.post("/backtest/run", req);
  return data;
}
```

- [ ] **Step 2: Run the frontend lint once after the helper changes**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/frontend
npm run lint
```

Expected: success, because adding optional `research_profile` support should not break the existing UI before the panel refactor lands.

- [ ] **Step 3: Refactor `BacktestPanel` into a fixed QQQ 5m lab and sync the chart context before runs**

`frontend/src/components/BacktestPanel.tsx`

```tsx
interface BacktestPanelProps {
  onSignals: (signals: Signal[]) => void;
  onEquityCurve: (curve: { time: string; equity: number }[]) => void;
  onActivateResearchContext: () => void;
  disabledReason?: string | null;
}
```

```tsx
const RESEARCH_SYMBOL = "QQQ";
const RESEARCH_TIMEFRAME = "5m";
const RESEARCH_PROFILE = "qqq_5m_phase1";
```

```tsx
const [config, setConfig] = useState({
  start: "2025-01-01",
  initial_capital: 100000,
  stop_loss_pct: 2,
  take_profit_pct: 4,
  risk_per_trade_pct: 2,
});
```

```tsx
const handleRun = async () => {
  if (!selected) return;
  onActivateResearchContext();
  setLoading(true);
  setResult(null);
  try {
    const res = await runBacktest({
      strategy: selected,
      symbol: RESEARCH_SYMBOL,
      timeframe: RESEARCH_TIMEFRAME,
      start: config.start,
      params,
      initial_capital: config.initial_capital,
      stop_loss_pct: config.stop_loss_pct,
      take_profit_pct: config.take_profit_pct,
      risk_per_trade_pct: config.risk_per_trade_pct,
      research_profile: RESEARCH_PROFILE,
    });
    setResult(res);
    onEquityCurve(res.equity_curve);
    const signals: Signal[] = res.trades.flatMap((t) => [
      {
        symbol: RESEARCH_SYMBOL,
        signal_type: "buy",
        price: t.entry_price,
        quantity: t.quantity,
        reason: t.reason,
        timestamp: t.entry_time,
      },
      {
        symbol: RESEARCH_SYMBOL,
        signal_type: "sell",
        price: t.exit_price,
        quantity: t.quantity,
        reason: `Exit: ${t.exit_reason} (${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(0)})`,
        timestamp: t.exit_time,
      },
    ]);
    onSignals(signals);
  } finally {
    setLoading(false);
  }
};
```

```tsx
<p className="max-w-[180px] text-right text-[11px] text-slate-500">
  QQQ · 5m · RTH · long-only
</p>
```

Remove the editable symbol field from the backtest panel so the first-stage lab stays honest.

- [ ] **Step 4: Make the app start in the research context and pass the activation callback**

`frontend/src/App.tsx`

```tsx
const [symbol, setSymbol] = useState("QQQ");
const [symbolInput, setSymbolInput] = useState("QQQ");
const [timeframe, setTimeframe] = useState<Timeframe>("5m");
```

```tsx
const activateResearchContext = useCallback(() => {
  setSymbol("QQQ");
  setSymbolInput("QQQ");
  setTimeframe("5m");
  setSignals([]);
  setEquityCurve([]);
}, []);
```

```tsx
<BacktestPanel
  onSignals={(sigs) => {
    setSignals(sigs);
  }}
  onEquityCurve={setEquityCurve}
  onActivateResearchContext={activateResearchContext}
  disabledReason={analysisDisabledReason}
/>
```

- [ ] **Step 5: Re-run lint and build to verify the backtest lab compiles cleanly**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/frontend
npm run lint
npm run build
```

Expected:

```text
> frontend@ lint
0 problems
vite build exits successfully
```

- [ ] **Step 6: Commit the frontend research-path slice**

```bash
cd /Users/bytedance/personalProject/AL_price_action
git add frontend/src/types/index.ts frontend/src/services/api.ts frontend/src/components/BacktestPanel.tsx frontend/src/App.tsx
git commit -m "feat: lock backtest lab to QQQ 5m research path"
```

### Task 5: Run the full verification set and record the baseline execution checkpoint

**Files:**
- Modify: `docs/superpowers/specs/2026-04-18-qqq-5m-validation-design.md` only if a verification contradiction is discovered
- No new code files expected

- [ ] **Step 1: Run the backend compile check**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action
PYTHONPYCACHEPREFIX=/tmp/codex_pycache python3 -m compileall -q backend
```

Expected: no output.

- [ ] **Step 2: Run the targeted backend tests**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/backend
.venv/bin/python -m pytest tests/test_analysis_bars.py tests/test_backtester_intraday.py tests/test_strategy_router.py tests/test_backtest_router.py -q
```

Expected:

```text
13 passed
```

- [ ] **Step 3: Run the frontend verification again after backend changes are in place**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action/frontend
npm run lint
npm run build
```

Expected:

```text
> frontend@ lint
0 problems
vite build exits successfully
```

- [ ] **Step 4: Perform a manual smoke of the constrained research path**

Run:

```bash
cd /Users/bytedance/personalProject/AL_price_action
./start.sh
```

Then verify in the browser:

- the app loads with `QQQ` selected
- the chart starts on `5m`
- opening the `Backtest` tab shows `QQQ · 5m · RTH · long-only`
- running a backtest sends `research_profile: "qqq_5m_phase1"`
- the chart markers and equity curve correspond to the same `QQQ 5m` context

- [ ] **Step 5: Commit only if a smoke-fix was needed during verification**

If the smoke found no new bug, skip this step. If a small smoke-only fix was required, stage only that fix and commit it separately:

```bash
cd /Users/bytedance/personalProject/AL_price_action
git add backend/services/backtester.py frontend/src/components/BacktestPanel.tsx frontend/src/App.tsx
git commit -m "fix: address QQQ 5m validation smoke issues"
```

## Self-Review

- Spec coverage check:
  - `QQQ 5m / RTH / long-only / day-flat` is covered by Tasks 1, 2, and 4.
  - strategy validation order is not encoded in code yet; this plan intentionally prepares the engine and UI so the ordered validation can begin after implementation.
  - paper-trading gate remains a research decision after baseline results, not part of this coding slice.
- Placeholder scan:
  - no `TODO`, `TBD`, or "similar to above" shortcuts remain in task steps.
- Type consistency:
  - the plan uses one shared field name, `research_profile`, in backend requests and frontend API calls.

## Execution Notes

- Do not broaden the research profile beyond `qqq_5m_phase1` in this implementation pass.
- Do not change Brooks strategy logic yet; this slice is for trustworthy execution semantics and a locked research path.
- If the smoke test shows strategy markers still desynchronize from the chart, fix that before any optimization work begins.
