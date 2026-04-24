import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from routers import backtest as backtest_router
from routers import market as market_router
from routers import strategy as strategy_router
from routers import trading as trading_router
from routers import ws as ws_router
from services.alpaca_client import AlpacaNotConfiguredError


def _raise_alpaca_not_configured(*args, **kwargs):
    raise AlpacaNotConfiguredError("Alpaca credentials are not configured")


@pytest.fixture
def client(monkeypatch):
    async def fake_init_db():
        return None

    async def fake_start_stream():
        return None

    async def fake_stop_stream():
        return None

    async def fake_start_trade_updates_stream():
        return None

    async def fake_stop_trade_updates_stream():
        return None

    monkeypatch.setattr(main, "init_db", fake_init_db)
    monkeypatch.setattr(main.market_data, "start_stream", fake_start_stream)
    monkeypatch.setattr(main.market_data, "stop_stream", fake_stop_stream)
    monkeypatch.setattr(
        main.trade_updates, "start_trade_updates_stream", fake_start_trade_updates_stream
    )
    monkeypatch.setattr(
        main.trade_updates, "stop_trade_updates_stream", fake_stop_trade_updates_stream
    )

    with TestClient(main.app) as test_client:
        yield test_client


def test_market_bars_returns_normal_response_when_analysis_bars_succeed(client, monkeypatch):
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

    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        return bars

    monkeypatch.setattr(market_router, "get_analysis_bars", fake_get_analysis_bars)

    response = client.get(
        "/api/market/bars/qqq",
        params={"timeframe": "1D", "start": "2025-01-01"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "qqq",
        "timeframe": "1D",
        "bars": bars,
    }


def test_market_bars_returns_503_when_analysis_bars_need_alpaca(client, monkeypatch):
    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(market_router, "get_analysis_bars", fake_get_analysis_bars)

    response = client.get(
        "/api/market/bars/qqq",
        params={"timeframe": "1D", "start": "2025-01-01"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Alpaca credentials are not configured"}


def test_market_quote_returns_503_when_alpaca_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        market_router.alpaca_client, "get_quote", _raise_alpaca_not_configured
    )

    response = client.get("/api/market/quote/AAPL")

    assert response.status_code == 503
    assert response.json() == {"detail": "Alpaca credentials are not configured"}


@pytest.mark.parametrize(
    "method,path,patch_target,patch_name,body",
    [
        ("get", "/api/trading/account", trading_router.alpaca_client, "get_account", None),
        (
            "get",
            "/api/trading/positions",
            trading_router.alpaca_client,
            "get_positions",
            None,
        ),
        (
            "get",
            "/api/trading/orders?status=open",
            trading_router.alpaca_client,
            "get_orders",
            None,
        ),
        (
            "delete",
            "/api/trading/order/order-123",
            trading_router.alpaca_client,
            "cancel_order",
            None,
        ),
        (
            "post",
            "/api/trading/order",
            trading_router,
            "execute_order",
            {"symbol": "AAPL", "qty": 1, "side": "buy"},
        ),
    ],
)
def test_trading_routes_return_503_when_alpaca_unavailable(
    client, monkeypatch, method, path, patch_target, patch_name, body
):
    monkeypatch.setattr(patch_target, patch_name, _raise_alpaca_not_configured)

    response = client.request(method.upper(), path, json=body)

    assert response.status_code == 503
    assert response.json() == {"detail": "Alpaca credentials are not configured"}


@pytest.mark.parametrize(
    "path,patch_name",
    [
        ("/api/trading/account", "get_account"),
        ("/api/trading/positions", "get_positions"),
        ("/api/trading/orders?status=open", "get_orders"),
    ],
)
def test_trading_snapshot_routes_return_503_when_broker_times_out(
    client, monkeypatch, path, patch_name
):
    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("paper api timed out")

    monkeypatch.setattr(trading_router.alpaca_client, patch_name, _raise_timeout)

    response = client.get(path)

    assert response.status_code == 503
    assert response.json() == {"detail": "Broker unavailable: paper api timed out"}


def test_strategy_signals_returns_503_when_analysis_bars_need_alpaca(
    client, monkeypatch
):
    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(strategy_router, "get_analysis_bars", fake_get_analysis_bars)

    response = client.post(
        "/api/strategy/signals",
        json={
            "name": "ma_crossover",
            "symbol": "qqq",
            "timeframe": "1D",
            "start": "2025-01-01",
            "limit": 250,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Alpaca credentials are not configured"}


def test_backtest_returns_503_when_analysis_bars_need_alpaca(client, monkeypatch):
    async def fake_get_analysis_bars(
        symbol, timeframe, start, end=None, limit=1000, research_profile=None
    ):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(backtest_router, "get_analysis_bars", fake_get_analysis_bars)

    response = client.post(
        "/api/backtest/run",
        json={
            "strategy": "brooks_pullback_count",
            "symbol": "qqq",
            "timeframe": "1D",
            "start": "2025-01-01",
            "limit": 250,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Alpaca credentials are not configured"}


def test_market_ws_sends_degraded_status_and_closes(client, monkeypatch):
    async def fake_subscribe(symbol, callback):
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    monkeypatch.setattr(ws_router.market_data, "subscribe", fake_subscribe)

    with client.websocket_connect("/ws/market/qqq") as websocket:
        assert websocket.receive_json() == {
            "type": "status",
            "status": "degraded",
            "reason": "alpaca_not_configured",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()
