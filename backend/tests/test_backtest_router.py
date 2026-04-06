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
