from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from routers import trading as trading_router
from services.ibkr_client import IBKRSafetyError


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

    async def fake_start_runner_monitor():
        return None

    async def fake_stop_runner_monitor():
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
    monkeypatch.setattr(
        main, "start_phase1_paper_runner_monitor", fake_start_runner_monitor
    )
    monkeypatch.setattr(
        main, "stop_phase1_paper_runner_monitor", fake_stop_runner_monitor
    )

    with TestClient(main.app) as test_client:
        yield test_client


def test_trading_broker_status_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        trading_router.broker_client,
        "status",
        lambda: {
            "broker": "ibkr",
            "configured": True,
            "live_trading_enabled": True,
            "order_transmit": True,
            "allowed_symbols": ["QQQ"],
            "max_order_usd": 750.0,
        },
    )

    response = client.get("/api/trading/broker")

    assert response.status_code == 200
    assert response.json()["broker"] == "ibkr"
    assert response.json()["max_order_usd"] == 750.0


def test_submit_order_forwards_ibkr_live_order_fields(client, monkeypatch):
    captured = {}

    async def fake_execute_order(**kwargs):
        captured.update(kwargs)
        return {
            "type": "trade",
            "broker": "ibkr",
            "broker_order_id": "ibkr:101",
            "status": "submitted",
        }

    monkeypatch.setattr(trading_router, "execute_order", fake_execute_order)

    response = client.post(
        "/api/trading/order",
        json={
            "symbol": "qqq",
            "qty": 1,
            "side": "buy",
            "order_type": "limit",
            "limit_price": 500.0,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "symbol": "QQQ",
        "qty": 1,
        "side": "buy",
        "order_type": "limit",
        "limit_price": 500.0,
        "confirm_live": True,
    }


def test_submit_order_returns_400_for_ibkr_safety_error(client, monkeypatch):
    async def fake_execute_order(**kwargs):
        raise IBKRSafetyError("IBKR live orders require confirm_live=true")

    monkeypatch.setattr(trading_router, "execute_order", fake_execute_order)

    response = client.post(
        "/api/trading/order",
        json={
            "symbol": "QQQ",
            "qty": 1,
            "side": "buy",
            "order_type": "limit",
            "limit_price": 500.0,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "IBKR live orders require confirm_live=true",
    }
