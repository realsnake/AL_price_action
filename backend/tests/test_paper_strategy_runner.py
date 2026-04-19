from __future__ import annotations

from datetime import datetime
from datetime import timezone

import pytest

from services import paper_strategy_runner
from strategies.base import Signal, SignalType


def _bar(timestamp: str, open_: float, high: float, low: float, close: float, volume: int = 1000) -> dict:
    return {
        "time": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class _SignalOnBarStrategy:
    def __init__(self, signal_bar_time: str):
        self._signal_bar_time = signal_bar_time

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        if not bars or bars[-1]["time"] != self._signal_bar_time:
            return []
        return [
            Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=bars[-1]["close"],
                quantity=1,
                reason="paper-entry",
                timestamp=datetime.fromisoformat(self._signal_bar_time),
            )
        ]


@pytest.mark.asyncio
async def test_phase1_paper_runner_enters_on_completed_5m_signal_and_exits_on_session_close(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}
    unsubscribe_calls = []
    orders = []

    history_bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
        _bar("2025-01-06T14:35:00+00:00", 500.2, 500.8, 500.0, 500.6),
        _bar("2025-01-06T14:40:00+00:00", 500.6, 501.0, 500.5, 500.9),
    ]

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        assert symbol == "QQQ"
        assert timeframe == "5m"
        assert research_profile == "qqq_5m_phase1"
        return history_bars

    async def fake_subscribe(symbol: str, callback):
        subscribed["symbol"] = symbol
        subscribed["callback"] = callback

    async def fake_unsubscribe(symbol: str, callback):
        unsubscribe_calls.append((symbol, callback))

    async def fake_execute_order(
        symbol: str,
        qty: int,
        side: str,
        strategy: str | None = None,
        reason: str | None = None,
    ) -> dict:
        orders.append(
            {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "strategy": strategy,
                "reason": reason,
            }
        )
        return {
            "status": "filled",
            "qty": qty,
            "price": 501.55 if side == "buy" else 501.85,
            "alpaca_order_id": f"{side}-filled",
        }

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    async def fake_get_trade_history(limit=50):
        return []
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    started = await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)

    assert started["running"] is True
    assert started["symbol"] == "QQQ"
    assert subscribed["symbol"] == "QQQ"

    callback = subscribed["callback"]

    live_open = [
        _bar("2025-01-06T15:00:00+00:00", 501.0, 501.2, 500.9, 501.1),
        _bar("2025-01-06T15:01:00+00:00", 501.1, 501.3, 501.0, 501.2),
        _bar("2025-01-06T15:02:00+00:00", 501.2, 501.4, 501.1, 501.3),
        _bar("2025-01-06T15:03:00+00:00", 501.3, 501.5, 501.2, 501.4),
        _bar("2025-01-06T15:04:00+00:00", 501.4, 501.6, 501.3, 501.5),
        _bar("2025-01-06T15:05:00+00:00", 501.5, 501.7, 501.4, 501.55),
    ]
    for minute_bar in live_open:
        await callback("QQQ", minute_bar)

    mid_status = paper_strategy_runner.get_phase1_paper_runner_status()

    assert [order["side"] for order in orders] == ["buy"]
    assert orders[0]["qty"] == 25
    assert mid_status["position"]["quantity"] == 25
    assert mid_status["last_completed_bar_time"] == "2025-01-06T15:00:00+00:00"

    live_close = [
        _bar("2025-01-06T20:55:00+00:00", 502.0, 502.2, 501.9, 502.1),
        _bar("2025-01-06T20:56:00+00:00", 502.1, 502.3, 502.0, 502.15),
        _bar("2025-01-06T20:57:00+00:00", 502.15, 502.25, 502.0, 502.05),
        _bar("2025-01-06T20:58:00+00:00", 502.05, 502.2, 501.95, 502.0),
        _bar("2025-01-06T20:59:00+00:00", 502.0, 502.1, 501.9, 501.95),
        _bar("2025-01-06T21:00:00+00:00", 501.9, 502.0, 501.8, 501.85),
    ]
    for minute_bar in live_close:
        await callback("QQQ", minute_bar)

    final_status = paper_strategy_runner.get_phase1_paper_runner_status()

    assert [order["side"] for order in orders] == ["buy", "sell"]
    assert orders[1]["reason"] == "session_close"
    assert final_status["position"] is None
    assert final_status["orders_submitted"] == 2

    stopped = await paper_strategy_runner.stop_phase1_paper_runner()

    assert stopped["running"] is False
    assert unsubscribe_calls == [("QQQ", callback)]
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_requires_paper_mode(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", False)

    with pytest.raises(RuntimeError, match="requires PAPER_TRADING=true"):
        await paper_strategy_runner.start_phase1_paper_runner()

    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_stop_flattens_open_position_by_default(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}
    orders = []

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        return [
            _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
            _bar("2025-01-06T14:35:00+00:00", 500.2, 500.8, 500.0, 500.6),
            _bar("2025-01-06T14:40:00+00:00", 500.6, 501.0, 500.5, 500.9),
        ]

    async def fake_subscribe(symbol: str, callback):
        subscribed["callback"] = callback

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_execute_order(
        symbol: str,
        qty: int,
        side: str,
        strategy: str | None = None,
        reason: str | None = None,
    ) -> dict:
        orders.append({"side": side, "qty": qty, "reason": reason})
        return {
            "status": "filled",
            "qty": qty,
            "price": 501.55 if side == "buy" else 501.55,
            "alpaca_order_id": f"{side}-filled",
        }

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    async def fake_get_trade_history(limit=50):
        return []
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=10)
    callback = subscribed["callback"]

    for minute_bar in [
        _bar("2025-01-06T15:00:00+00:00", 501.0, 501.2, 500.9, 501.1),
        _bar("2025-01-06T15:01:00+00:00", 501.1, 501.3, 501.0, 501.2),
        _bar("2025-01-06T15:02:00+00:00", 501.2, 501.4, 501.1, 501.3),
        _bar("2025-01-06T15:03:00+00:00", 501.3, 501.5, 501.2, 501.4),
        _bar("2025-01-06T15:04:00+00:00", 501.4, 501.6, 501.3, 501.5),
        _bar("2025-01-06T15:05:00+00:00", 501.5, 501.7, 501.4, 501.55),
    ]:
        await callback("QQQ", minute_bar)

    stopped = await paper_strategy_runner.stop_phase1_paper_runner()

    assert [order["side"] for order in orders] == ["buy", "sell"]
    assert orders[-1]["reason"] == "manual_stop"
    assert stopped["position"] is None
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_recovers_open_broker_position_on_start(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        return [
            _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
            _bar("2025-01-06T14:35:00+00:00", 500.2, 500.8, 500.0, 500.6),
            _bar("2025-01-06T14:40:00+00:00", 500.6, 501.0, 500.5, 500.9),
        ]

    async def fake_subscribe(symbol: str, callback):
        return None

    async def fake_unsubscribe(symbol: str, callback):
        return None

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    async def fake_get_trade_history(limit=50):
        return [
                {
                    "id": 1,
                    "symbol": "QQQ",
                    "side": "buy",
                "quantity": 25,
                "price": 501.25,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "recovered-entry",
                "status": "filled",
                "alpaca_order_id": "ord-fill",
                    "created_at": "2025-01-06T15:00:02+00:00",
                }
            ]
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_positions",
        lambda: [
            {
                "symbol": "QQQ",
                "qty": 25,
                "avg_entry": 501.25,
                "current_price": 502.0,
                "market_value": 12550.0,
                "unrealized_pnl": 18.75,
                "unrealized_pnl_pct": 0.15,
            }
        ],
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    started = await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)

    assert started["position"]["quantity"] == 25
    assert started["position"]["entry_price"] == 501.25
    assert started["position"]["reason"] == "recovered-entry"

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_recovers_pending_entry_and_blocks_duplicate_signal(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}
    orders = []

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        return [
            _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
            _bar("2025-01-06T14:35:00+00:00", 500.2, 500.8, 500.0, 500.6),
            _bar("2025-01-06T14:40:00+00:00", 500.6, 501.0, 500.5, 500.9),
        ]

    async def fake_subscribe(symbol: str, callback):
        subscribed["callback"] = callback

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_execute_order(*args, **kwargs):
        orders.append(kwargs)
        return {"status": "submitted"}

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    async def fake_get_trade_history(limit=50):
        return [
                {
                    "id": 2,
                    "symbol": "QQQ",
                    "side": "buy",
                "quantity": 25,
                "price": 0.0,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "pending-entry",
                "status": "accepted",
                "alpaca_order_id": "ord-open",
                    "created_at": "2025-01-06T15:00:00+00:00",
                }
            ]
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_orders",
        lambda status="open": [
            {
                "id": "ord-open",
                "symbol": "QQQ",
                "side": "buy",
                "qty": "25",
                "filled_qty": "0",
                "status": "accepted",
                "created_at": "2025-01-06T15:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_order_by_id",
        lambda order_id: {
            "id": order_id,
            "symbol": "QQQ",
            "side": "buy",
            "qty": "25",
            "filled_qty": "0",
            "filled_avg_price": None,
            "status": "accepted",
            "created_at": "2025-01-06T15:00:00+00:00",
            "client_order_id": "client-open",
            "filled_at": None,
        },
    )
    async def fake_refresh_trade_statuses(limit=50, order_ids=None):
        return []
    monkeypatch.setattr(paper_strategy_runner, "refresh_trade_statuses", fake_refresh_trade_statuses)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )

    started = await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)
    assert started["pending_order"]["alpaca_order_id"] == "ord-open"

    callback = subscribed["callback"]
    for minute_bar in [
        _bar("2025-01-06T15:00:00+00:00", 501.0, 501.2, 500.9, 501.1),
        _bar("2025-01-06T15:01:00+00:00", 501.1, 501.3, 501.0, 501.2),
        _bar("2025-01-06T15:02:00+00:00", 501.2, 501.4, 501.1, 501.3),
        _bar("2025-01-06T15:03:00+00:00", 501.3, 501.5, 501.2, 501.4),
        _bar("2025-01-06T15:04:00+00:00", 501.4, 501.6, 501.3, 501.5),
        _bar("2025-01-06T15:05:00+00:00", 501.5, 501.7, 501.4, 501.55),
    ]:
        await callback("QQQ", minute_bar)

    assert orders == []

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_consumes_trade_update_for_pending_entry(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        return [
            _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
            _bar("2025-01-06T14:35:00+00:00", 500.2, 500.8, 500.0, 500.6),
            _bar("2025-01-06T14:40:00+00:00", 500.6, 501.0, 500.5, 500.9),
        ]

    async def fake_subscribe(symbol: str, callback):
        subscribed["callback"] = callback

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_execute_order(
        symbol: str,
        qty: int,
        side: str,
        strategy: str | None = None,
        reason: str | None = None,
    ) -> dict:
        return {
            "status": "accepted",
            "qty": qty,
            "price": 0.0,
            "alpaca_order_id": "ord-pending",
        }

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )

    await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)
    callback = subscribed["callback"]

    for minute_bar in [
        _bar("2025-01-06T15:00:00+00:00", 501.0, 501.2, 500.9, 501.1),
        _bar("2025-01-06T15:01:00+00:00", 501.1, 501.3, 501.0, 501.2),
        _bar("2025-01-06T15:02:00+00:00", 501.2, 501.4, 501.1, 501.3),
        _bar("2025-01-06T15:03:00+00:00", 501.3, 501.5, 501.2, 501.4),
        _bar("2025-01-06T15:04:00+00:00", 501.4, 501.6, 501.3, 501.5),
        _bar("2025-01-06T15:05:00+00:00", 501.5, 501.7, 501.4, 501.55),
    ]:
        await callback("QQQ", minute_bar)

    status = paper_strategy_runner.get_phase1_paper_runner_status()
    assert status["pending_order"]["alpaca_order_id"] == "ord-pending"

    await paper_strategy_runner._phase1_runner._on_trade_update(
        {
            "type": "trade_update",
            "alpaca_order_id": "ord-pending",
            "symbol": "QQQ",
            "strategy": "brooks_small_pb_trend",
            "status": "filled",
            "side": "buy",
            "qty": 25,
            "price": 501.8,
            "reason": "paper-entry",
            "timestamp": "2025-01-06T15:05:03+00:00",
        }
    )

    status = paper_strategy_runner.get_phase1_paper_runner_status()
    assert status["pending_order"] is None
    assert status["position"]["entry_price"] == 501.8
    assert status["position"]["quantity"] == 25

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()
