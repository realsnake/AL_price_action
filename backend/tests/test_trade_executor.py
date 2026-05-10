from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import trade_executor
from services.ibkr_client import IBKRSafetyError


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


class _FakeBrokerClient:
    def __init__(self, name: str = "alpaca", submit_result: dict | None = None):
        self.name = name
        self.submit_result = submit_result or {
            "id": "ord-1",
            "symbol": "QQQ",
            "side": "buy",
            "qty": "1",
            "status": "submitted",
            "created_at": "2026-05-10T12:00:00+00:00",
        }
        self.submit_calls: list[tuple[tuple, dict]] = []
        self.order_refreshes: list[str] = []

    def is_configured(self) -> bool:
        return True

    def owns_order_id(self, order_id: str | None) -> bool:
        if self.name == "ibkr":
            return bool(order_id and order_id.startswith("ibkr:"))
        return bool(order_id and not order_id.startswith("ibkr:"))

    def submit_order(self, *args, **kwargs) -> dict:
        self.submit_calls.append((args, kwargs))
        return dict(self.submit_result)

    def get_order_by_id(self, order_id: str) -> dict:
        self.order_refreshes.append(order_id)
        return {
            "id": order_id,
            "symbol": "QQQ",
            "side": "buy",
            "qty": "1",
            "filled_qty": "0",
            "filled_avg_price": None,
            "status": "submitted",
            "created_at": "2026-05-10T12:00:00+00:00",
        }


@pytest.fixture
def alpaca_broker(monkeypatch):
    broker = _FakeBrokerClient(name="alpaca")
    monkeypatch.setattr(trade_executor, "broker_client", broker)
    return broker


@pytest.mark.asyncio
async def test_get_trade_history_refreshes_price_and_status_from_broker(
    monkeypatch, alpaca_broker
):
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
    alpaca_broker.get_order_by_id = lambda order_id: {
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
    }

    history = await trade_executor.get_trade_history(limit=10)

    assert trade.price == 501.25
    assert trade.status == "filled"
    assert history[0]["price"] == 501.25
    assert history[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_broker_rate_limit_uses_warning_and_short_backoff(
    monkeypatch, alpaca_broker
):
    trade = _FakeTrade(
        id=16,
        symbol="QQQ",
        side="buy",
        quantity=100,
        price=0.0,
        strategy="brooks_small_pb_trend",
        signal_reason="entry",
        status="submitted",
        alpaca_order_id="ord-rate-limit",
        created_at=datetime(2025, 1, 6, 15, 1),
    )
    session = _FakeSession([trade])
    calls = []
    warnings = []
    exceptions = []

    class FakeLogger:
        def warning(self, message, *args, **kwargs):
            warnings.append((message, args, kwargs))

        def exception(self, message, *args, **kwargs):
            exceptions.append((message, args, kwargs))

        def debug(self, *args, **kwargs):
            pass

    def raise_rate_limit(order_id):
        calls.append(order_id)
        raise RuntimeError('{"code":42910000,"message":"rate limit exceeded"}')

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(trade_executor, "logger", FakeLogger())
    alpaca_broker.get_order_by_id = raise_rate_limit
    monkeypatch.setattr(trade_executor, "_now_monotonic", lambda: 100.0, raising=False)
    monkeypatch.setattr(trade_executor, "_alpaca_refresh_backoff_until", {}, raising=False)

    first = await trade_executor.get_trade_history(limit=10)
    second = await trade_executor.get_trade_history(limit=10)

    assert first[0]["status"] == "submitted"
    assert second[0]["status"] == "submitted"
    assert calls == ["ord-rate-limit"]
    assert exceptions == []
    assert len(warnings) == 1
    assert "temporarily throttled" in warnings[0][0]


@pytest.mark.asyncio
async def test_execute_order_returns_reconciled_fill_when_available(
    monkeypatch, alpaca_broker
):
    session = _FakeSession([])

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    alpaca_broker.submit_order = lambda symbol, qty, side, **kwargs: {
        "id": "ord-2",
        "symbol": symbol,
        "side": side,
        "qty": str(qty),
        "status": "accepted",
        "created_at": "2025-01-06T15:05:00+00:00",
    }
    alpaca_broker.get_order_by_id = lambda order_id: {
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
    }

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
async def test_execute_order_forwards_ibkr_limit_order_options(monkeypatch):
    session = _FakeSession([])
    broker = _FakeBrokerClient(
        name="ibkr",
        submit_result={
            "id": "ibkr:101",
            "symbol": "QQQ",
            "side": "buy",
            "qty": "1",
            "status": "submitted",
            "created_at": "2026-05-10T12:00:00+00:00",
            "broker": "ibkr",
        },
    )

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(trade_executor, "broker_client", broker)
    monkeypatch.setattr(trade_executor, "IBKR_DAILY_MAX_NOTIONAL_USD", 1500.0)

    trade_info = await trade_executor.execute_order(
        symbol="qqq",
        qty=1,
        side="buy",
        order_type="limit",
        limit_price=500.0,
        confirm_live=True,
    )

    assert broker.submit_calls == [
        (
            ("QQQ", 1, "buy"),
            {
                "order_type": "limit",
                "limit_price": 500.0,
                "confirm_live": True,
            },
        )
    ]
    assert session.added[0].symbol == "QQQ"
    assert session.added[0].alpaca_order_id == "ibkr:101"
    assert trade_info["broker"] == "ibkr"
    assert trade_info["broker_order_id"] == "ibkr:101"


@pytest.mark.asyncio
async def test_execute_order_blocks_ibkr_strategy_orders_by_default(monkeypatch):
    session = _FakeSession([])
    broker = _FakeBrokerClient(name="ibkr")

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(trade_executor, "broker_client", broker)
    monkeypatch.setattr(trade_executor, "IBKR_ALLOW_STRATEGY_TRADING", False)

    with pytest.raises(IBKRSafetyError, match="IBKR strategy trading is disabled"):
        await trade_executor.execute_order(
            symbol="QQQ",
            qty=1,
            side="buy",
            strategy="brooks_small_pb_trend",
            reason="entry",
            order_type="limit",
            limit_price=500.0,
            confirm_live=True,
        )

    assert broker.submit_calls == []
    assert session.added == []


@pytest.mark.asyncio
async def test_execute_order_enforces_ibkr_daily_notional_cap(monkeypatch):
    today_trade = _FakeTrade(
        id=4,
        symbol="QQQ",
        side="buy",
        quantity=1,
        price=700.0,
        strategy=None,
        signal_reason=None,
        status="submitted",
        alpaca_order_id="ibkr:100",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session = _FakeSession([today_trade])
    broker = _FakeBrokerClient(name="ibkr")

    monkeypatch.setattr(trade_executor, "async_session", _session_factory(session))
    monkeypatch.setattr(trade_executor, "broker_client", broker)
    monkeypatch.setattr(trade_executor, "IBKR_DAILY_MAX_NOTIONAL_USD", 1000.0)

    with pytest.raises(IBKRSafetyError, match="daily IBKR notional"):
        await trade_executor.execute_order(
            symbol="QQQ",
            qty=1,
            side="buy",
            order_type="limit",
            limit_price=500.0,
            confirm_live=True,
        )

    assert broker.submit_calls == []


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
