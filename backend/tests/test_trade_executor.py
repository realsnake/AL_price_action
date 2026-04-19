from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest

from services import trade_executor


@dataclass
class _FakeTrade:
    id: int
    symbol: str
    side: str
    quantity: int
    price: float
    strategy: str | None
    signal_reason: str | None
    status: str
    alpaca_order_id: str | None
    created_at: datetime


class _FakeScalarResult:
    def __init__(self, trades: list[_FakeTrade]):
        self._trades = trades

    def all(self):
        return self._trades


class _FakeExecuteResult:
    def __init__(self, trades: list[_FakeTrade]):
        self._trades = trades

    def scalars(self):
        return _FakeScalarResult(self._trades)


class _FakeSession:
    def __init__(self, trades: list[_FakeTrade]):
        self._trades = trades
        self.added: list[_FakeTrade] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, stmt):
        return _FakeExecuteResult(self._trades)

    def add(self, trade: _FakeTrade):
        trade.id = 42
        self._trades.insert(0, trade)
        self.added.append(trade)

    async def commit(self):
        self.commits += 1


def _session_factory(session: _FakeSession):
    def factory():
        return session

    return factory


@pytest.mark.asyncio
async def test_get_trade_history_refreshes_price_and_status_from_broker(monkeypatch):
    trade = _FakeTrade(
        id=1,
        symbol="QQQ",
        side="buy",
        quantity=100,
        price=0.0,
        strategy="brooks_small_pb_trend",
        signal_reason="entry",
        status="submitted",
        alpaca_order_id="ord-1",
        created_at=datetime(2025, 1, 6, 15, 1),
    )
    session = _FakeSession([trade])

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(
        trade_executor.alpaca_client,
        "get_order_by_id",
        lambda order_id: {
            "id": order_id,
            "symbol": "QQQ",
            "side": "buy",
            "qty": "100",
            "filled_qty": "100",
            "filled_avg_price": "501.25",
            "status": "filled",
            "created_at": "2025-01-06T15:01:00+00:00",
            "client_order_id": "client-1",
            "filled_at": "2025-01-06T15:01:02+00:00",
        },
    )

    history = await trade_executor.get_trade_history(limit=10)

    assert trade.price == 501.25
    assert trade.status == "filled"
    assert history[0]["price"] == 501.25
    assert history[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_execute_order_returns_reconciled_fill_when_available(monkeypatch):
    session = _FakeSession([])

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(
        trade_executor.alpaca_client,
        "submit_order",
        lambda symbol, qty, side: {
            "id": "ord-2",
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "status": "accepted",
            "created_at": "2025-01-06T15:05:00+00:00",
        },
    )
    monkeypatch.setattr(
        trade_executor.alpaca_client,
        "get_order_by_id",
        lambda order_id: {
            "id": order_id,
            "symbol": "QQQ",
            "side": "buy",
            "qty": "25",
            "filled_qty": "25",
            "filled_avg_price": "502.10",
            "status": "filled",
            "created_at": "2025-01-06T15:05:00+00:00",
            "client_order_id": "client-2",
            "filled_at": "2025-01-06T15:05:03+00:00",
        },
    )

    trade_info = await trade_executor.execute_order(
        symbol="QQQ",
        qty=25,
        side="buy",
        strategy="brooks_small_pb_trend",
        reason="entry",
    )

    assert trade_info["status"] == "filled"
    assert trade_info["price"] == 502.1
    assert session.added[0].price == 502.1
    assert session.added[0].status == "filled"


@pytest.mark.asyncio
async def test_apply_trade_update_updates_trade_and_notifies(monkeypatch):
    trade = _FakeTrade(
        id=3,
        symbol="QQQ",
        side="buy",
        quantity=25,
        price=0.0,
        strategy="brooks_small_pb_trend",
        signal_reason="entry",
        status="accepted",
        alpaca_order_id="ord-update",
        created_at=datetime(2025, 1, 6, 15, 1),
    )
    session = _FakeSession([trade])
    notifications = []

    async def fake_notify_trade(payload):
        notifications.append(payload)

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(trade_executor, "_notify_trade", fake_notify_trade)

    update = SimpleNamespace(
        event="fill",
        order=SimpleNamespace(
            id="ord-update",
            symbol="QQQ",
            side=SimpleNamespace(value="buy"),
            qty="25",
            filled_qty="25",
            filled_avg_price="503.2",
            status=SimpleNamespace(value="filled"),
        ),
        timestamp=datetime(2025, 1, 6, 15, 1, 5),
        qty=25.0,
        price=503.2,
    )

    await trade_executor.apply_trade_update(update)

    assert trade.status == "filled"
    assert trade.price == 503.2
    assert notifications[0]["type"] == "trade_update"
    assert notifications[0]["trade_id"] == 3
    assert notifications[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_add_trade_listener_deduplicates_same_callback():
    trade_executor._trade_listeners.clear()
    notifications = []

    async def listener(payload):
        notifications.append(payload)

    trade_executor.add_trade_listener(listener)
    trade_executor.add_trade_listener(listener)

    await trade_executor._notify_trade({"type": "trade", "symbol": "QQQ"})

    assert len(notifications) == 1

    trade_executor.remove_trade_listener(listener)
