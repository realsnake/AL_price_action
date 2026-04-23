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

    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        captured["bars_request"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
            "research_profile": research_profile,
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
        research_profile="qqq_5m_phase1",
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
        "research_profile": "qqq_5m_phase1",
    }
    assert captured["strategy_request"] == {
        "name": "ma_crossover",
        "symbol": "QQQ",
        "bars": bars,
        "params": {"short_period": 10, "long_period": 30},
    }


@pytest.mark.asyncio
async def test_get_signals_returns_400_when_no_bars(monkeypatch):
    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
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
