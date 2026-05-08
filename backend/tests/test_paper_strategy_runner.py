from __future__ import annotations

import asyncio
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


@pytest.fixture(autouse=True)
def disable_desired_runner_persistence(monkeypatch):
    async def fake_set_desired(*args, **kwargs):
        return None

    async def fake_mark_inactive(*args, **kwargs):
        return None

    monkeypatch.setattr(
        paper_strategy_runner,
        "_set_desired_phase1_runner",
        fake_set_desired,
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_mark_desired_phase1_runner_inactive",
        fake_mark_inactive,
    )


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
    event_types = [event["type"] for event in final_status["recent_events"]]

    assert [order["side"] for order in orders] == ["buy", "sell"]
    assert orders[1]["reason"] == "session_close"
    assert final_status["position"] is None
    assert final_status["orders_submitted"] == 2
    assert "signal_detected" in event_types
    assert "order_submitted" in event_types
    assert "position_opened" in event_types
    assert "position_closed" in event_types

    stopped = await paper_strategy_runner.stop_phase1_paper_runner()

    assert stopped["running"] is False
    assert unsubscribe_calls == [("QQQ", callback)]
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_entry_fill_callback_does_not_deadlock_live_bar(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}
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
        return history_bars

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
        trade_info = {
            "symbol": symbol,
            "strategy": strategy,
            "status": "filled",
            "side": side,
            "qty": qty,
            "price": 501.55,
            "alpaca_order_id": f"{side}-filled",
            "reason": reason,
            "timestamp": "2025-01-06T15:05:01+00:00",
        }
        await runner._on_trade_update(trade_info)
        return trade_info

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)
    runner = paper_strategy_runner._phase1_runners[paper_strategy_runner.DEFAULT_PHASE1_STRATEGY]
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
        await asyncio.wait_for(callback("QQQ", minute_bar), timeout=0.5)

    status = paper_strategy_runner.get_phase1_paper_runner_status()
    assert status["position"]["quantity"] == 25
    assert status["orders_submitted"] == 1

    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_allows_two_strategies_to_run_in_parallel(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed_callbacks: list[tuple[str, object]] = []
    unsubscribed_callbacks: list[tuple[str, object]] = []

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
        return history_bars

    async def fake_subscribe(symbol: str, callback):
        subscribed_callbacks.append((symbol, callback))

    async def fake_unsubscribe(symbol: str, callback):
        unsubscribed_callbacks.append((symbol, callback))

    async def fake_execute_order(
        symbol: str,
        qty: int,
        side: str,
        strategy: str | None = None,
        reason: str | None = None,
    ) -> dict:
        return {
            "status": "filled",
            "qty": qty,
            "price": 501.55 if side == "buy" else 501.85,
            "alpaca_order_id": f"{strategy}-{side}",
        }

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    small_pb_status = await paper_strategy_runner.start_phase1_paper_runner(
        strategy="brooks_small_pb_trend",
        fixed_quantity=25,
    )
    breakout_status = await paper_strategy_runner.start_phase1_paper_runner(
        strategy="brooks_breakout_pullback",
        fixed_quantity=10,
    )

    assert small_pb_status["running"] is True
    assert breakout_status["running"] is True
    assert len(subscribed_callbacks) == 2

    statuses = paper_strategy_runner.get_phase1_paper_runner_statuses()
    statuses_by_strategy = {status["strategy"]: status for status in statuses}
    assert statuses_by_strategy["brooks_breakout_pullback"]["running"] is True
    assert statuses_by_strategy["brooks_small_pb_trend"]["running"] is True
    assert statuses_by_strategy["brooks_pullback_count"]["running"] is False

    stopped_small_pb = await paper_strategy_runner.stop_phase1_paper_runner(
        strategy="brooks_small_pb_trend",
        close_position=False,
    )

    assert stopped_small_pb["running"] is False
    assert paper_strategy_runner.get_phase1_paper_runner_status(
        "brooks_breakout_pullback",
    )["running"] is True

    stopped_breakout = await paper_strategy_runner.stop_phase1_paper_runner(
        strategy="brooks_breakout_pullback",
        close_position=False,
    )

    assert stopped_breakout["running"] is False
    assert len(unsubscribed_callbacks) == 2
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_uses_structural_stop_for_phase1_entry(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    subscribed = {}

    history_bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.2),
        _bar("2025-01-06T14:35:00+00:00", 500.2, 500.7, 500.0, 500.5),
        _bar("2025-01-06T14:40:00+00:00", 500.5, 500.6, 499.4, 500.1),
    ]

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
        research_profile: str | None = None,
    ) -> list[dict]:
        return history_bars

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
            "status": "filled",
            "qty": qty,
            "price": 501.55 if side == "buy" else 501.55,
            "alpaca_order_id": f"{side}-filled",
        }

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

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

    assert status["position"]["entry_price"] == 501.55
    assert status["position"]["stop_price"] == 499.4
    assert status["position"]["target_price"] is None
    assert status["position"]["target_reason"] is None

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_status_tracks_runner_lifecycle_events(monkeypatch):
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
        ]

    async def fake_subscribe(symbol: str, callback):
        return None

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    started = await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=10)
    start_types = [event["type"] for event in started["recent_events"]]
    assert start_types[-1] == "runner_started"

    stopped = await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    stop_types = [event["type"] for event in stopped["recent_events"]]
    assert stop_types[-1] == "runner_stopped"

    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_requires_paper_mode(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", False)

    with pytest.raises(RuntimeError, match="requires PAPER_TRADING=true"):
        await paper_strategy_runner.start_phase1_paper_runner()

    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.parametrize(
    "strategy_name",
    [
        "brooks_breakout_pullback",
        "brooks_pullback_count",
    ],
)
@pytest.mark.asyncio
async def test_phase1_paper_runner_accepts_phase1_strategy(monkeypatch, strategy_name):
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

    async def fake_get_trade_history(limit=50):
        return []

    captured = {}

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    def fake_get_strategy(name, params=None):
        captured["strategy_name"] = name
        return _SignalOnBarStrategy("2025-01-06T15:00:00+00:00")
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        fake_get_strategy,
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    started = await paper_strategy_runner.start_phase1_paper_runner(
        strategy=strategy_name,
        fixed_quantity=25,
    )

    assert captured["strategy_name"] == strategy_name
    assert started["strategy"] == strategy_name

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_tightens_breakout_stop_to_break_even_after_1r(monkeypatch):
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
            _bar("2025-01-06T14:30:00+00:00", 100.0, 100.2, 99.9, 100.1),
            _bar("2025-01-06T14:35:00+00:00", 100.1, 100.5, 100.0, 100.4),
            _bar("2025-01-06T14:40:00+00:00", 100.4, 103.4, 100.4, 102.7),
            _bar("2025-01-06T14:45:00+00:00", 102.7, 102.8, 101.2, 101.8),
            _bar("2025-01-06T14:50:00+00:00", 101.8, 103.2, 101.7, 103.0),
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
            "status": "filled",
            "qty": qty,
            "price": 103.0,
            "alpaca_order_id": f"{side}-filled",
        }

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T14:50:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    await paper_strategy_runner.start_phase1_paper_runner(
        strategy="brooks_breakout_pullback",
        fixed_quantity=10,
        exit_policy="breakout_break_even_after_1r",
    )
    callback = subscribed["callback"]

    for minute_bar in [
        _bar("2025-01-06T14:51:00+00:00", 103.0, 103.2, 102.9, 103.1),
        _bar("2025-01-06T14:52:00+00:00", 103.1, 103.3, 103.0, 103.2),
        _bar("2025-01-06T14:53:00+00:00", 103.2, 103.5, 103.1, 103.3),
        _bar("2025-01-06T14:54:00+00:00", 103.3, 103.6, 103.2, 103.4),
        _bar("2025-01-06T14:55:00+00:00", 103.4, 106.0, 103.3, 105.8),
        _bar("2025-01-06T14:56:00+00:00", 105.8, 105.9, 105.5, 105.7),
        _bar("2025-01-06T14:57:00+00:00", 105.7, 105.8, 105.4, 105.6),
        _bar("2025-01-06T14:58:00+00:00", 105.6, 105.7, 105.2, 105.4),
        _bar("2025-01-06T14:59:00+00:00", 105.4, 105.5, 105.0, 105.2),
        _bar("2025-01-06T15:00:00+00:00", 105.2, 105.3, 105.0, 105.1),
    ]:
        await callback("QQQ", minute_bar)

    status = paper_strategy_runner.get_phase1_paper_runner_status(
        strategy="brooks_breakout_pullback",
    )

    assert status["position"]["stop_price"] == 103.0
    assert status["position"]["stop_reason"] == "breakout_break_even_after_1r"

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_breakout_2_5r_policy_sets_target_and_break_even(monkeypatch):
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
            _bar("2025-01-06T14:30:00+00:00", 100.0, 100.2, 99.9, 100.1),
            _bar("2025-01-06T14:35:00+00:00", 100.1, 100.5, 100.0, 100.4),
            _bar("2025-01-06T14:40:00+00:00", 100.4, 103.4, 100.4, 102.7),
            _bar("2025-01-06T14:45:00+00:00", 102.7, 102.8, 101.2, 101.8),
            _bar("2025-01-06T14:50:00+00:00", 101.8, 103.2, 101.7, 103.0),
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
            "status": "filled",
            "qty": qty,
            "price": 103.0,
            "alpaca_order_id": f"{side}-filled",
        }

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "execute_order", fake_execute_order)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T14:50:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])

    await paper_strategy_runner.start_phase1_paper_runner(
        strategy="brooks_breakout_pullback",
        fixed_quantity=10,
        exit_policy="breakout_target_2_5r_break_even_after_0_75r",
    )
    callback = subscribed["callback"]

    for minute_bar in [
        _bar("2025-01-06T14:51:00+00:00", 103.0, 103.2, 102.9, 103.1),
        _bar("2025-01-06T14:52:00+00:00", 103.1, 103.3, 103.0, 103.2),
        _bar("2025-01-06T14:53:00+00:00", 103.2, 103.6, 103.1, 103.4),
        _bar("2025-01-06T14:54:00+00:00", 103.4, 104.9, 103.3, 104.8),
        _bar("2025-01-06T14:55:00+00:00", 104.8, 105.1, 104.7, 104.9),
        _bar("2025-01-06T14:56:00+00:00", 104.9, 105.0, 104.8, 104.95),
        _bar("2025-01-06T14:57:00+00:00", 104.95, 105.0, 104.9, 104.96),
        _bar("2025-01-06T14:58:00+00:00", 104.96, 105.0, 104.9, 104.97),
        _bar("2025-01-06T14:59:00+00:00", 104.97, 105.0, 104.9, 104.98),
        _bar("2025-01-06T15:00:00+00:00", 104.98, 105.0, 104.9, 104.99),
    ]:
        await callback("QQQ", minute_bar)

    status = paper_strategy_runner.get_phase1_paper_runner_status(
        strategy="brooks_breakout_pullback",
    )

    assert status["position"]["target_price"] == pytest.approx(109.5)
    assert (
        status["position"]["target_reason"]
        == "breakout_target_2_5r_break_even_after_0_75r"
    )
    assert status["position"]["stop_price"] == 103.0
    assert (
        status["position"]["stop_reason"]
        == "breakout_target_2_5r_break_even_after_0_75r"
    )

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_get_phase1_paper_runner_history_filters_by_requested_strategy(monkeypatch):
    async def fake_get_trade_history(limit=50):
        return [
            {
                "id": 1,
                "symbol": "QQQ",
                "strategy": "brooks_breakout_pullback",
                "created_at": "2025-01-06T15:00:00+00:00",
            },
            {
                "id": 2,
                "symbol": "QQQ",
                "strategy": "brooks_small_pb_trend",
                "created_at": "2025-01-06T15:05:00+00:00",
            },
            {
                "id": 3,
                "symbol": "SPY",
                "strategy": "brooks_breakout_pullback",
                "created_at": "2025-01-06T15:10:00+00:00",
            },
        ]

    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)

    history = await paper_strategy_runner.get_phase1_paper_runner_history(
        limit=5,
        strategy="brooks_breakout_pullback",
    )

    assert [trade["id"] for trade in history] == [1]


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
            _bar("2025-01-06T14:55:00+00:00", 500.0, 500.6, 499.7, 500.5),
            _bar("2025-01-06T15:00:00+00:00", 500.5, 501.1, 500.1, 500.9),
            _bar("2025-01-06T15:05:00+00:00", 500.9, 501.4, 500.8, 501.2),
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
                    "created_at": "2025-01-06T15:05:02+00:00",
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
    assert started["position"]["stop_price"] == 499.7
    assert started["position"]["target_price"] is None
    assert (
        started["position"]["stop_reason"]
        == "phase1_structural_below_signal_pullback_low"
    )
    assert started["position"]["target_reason"] is None

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_caps_recovered_position_to_broker_available_quantity(monkeypatch):
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
            _bar("2025-01-06T14:55:00+00:00", 500.0, 500.6, 499.7, 500.5),
            _bar("2025-01-06T15:00:00+00:00", 500.5, 501.1, 500.1, 500.9),
            _bar("2025-01-06T15:05:00+00:00", 500.9, 501.4, 500.8, 501.2),
        ]

    async def fake_subscribe(symbol: str, callback):
        return None

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_get_trade_history(limit=50):
        return [
            {
                "id": 1,
                "symbol": "QQQ",
                "side": "buy",
                "quantity": 150,
                "price": 501.25,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "recovered-entry",
                "status": "filled",
                "alpaca_order_id": "ord-fill",
                "created_at": "2025-01-06T15:05:02+00:00",
            }
        ]

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(
        paper_strategy_runner,
        "get_strategy",
        lambda name, params=None: _SignalOnBarStrategy("2025-01-06T15:00:00+00:00"),
    )
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_positions",
        lambda: [
            {
                "symbol": "QQQ",
                "qty": 100,
                "avg_entry": 501.25,
                "current_price": 502.0,
                "market_value": 50200.0,
                "unrealized_pnl": 75.0,
                "unrealized_pnl_pct": 0.15,
            }
        ],
    )
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_orders",
        lambda status="open": [
            {
                "id": "open-sell",
                "symbol": "QQQ",
                "side": "sell",
                "qty": "75",
                "status": "accepted",
            }
        ],
    )

    started = await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=25)

    assert started["position"]["quantity"] == 25

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

    await paper_strategy_runner._phase1_runners["brooks_small_pb_trend"]._on_trade_update(
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
    assert status["last_trade_update_at"] == "2025-01-06T15:05:03+00:00"

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_status_warns_when_pending_order_is_stale(monkeypatch):
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
        ]

    async def fake_subscribe(symbol: str, callback):
        return None

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2025-01-06T15:03:00+00:00"),
    )

    await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=10)
    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"].pending_order = paper_strategy_runner.PendingOrder(
        alpaca_order_id="ord-stale",
        side="buy",
        quantity=10,
        status="accepted",
        reason="stale-entry",
        submitted_at="2025-01-06T15:00:00+00:00",
        signal_time="2025-01-06T15:00:00+00:00",
    )

    status = paper_strategy_runner.get_phase1_paper_runner_status()

    assert status["warnings"] == ["Pending buy order open for 180s"]

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_phase1_paper_runner_status_warns_when_live_bars_go_stale_during_rth(monkeypatch):
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
        ]

    async def fake_subscribe(symbol: str, callback):
        return None

    async def fake_unsubscribe(symbol: str, callback):
        return None

    async def fake_get_trade_history(limit=50):
        return []

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner, "get_analysis_bars", fake_get_analysis_bars)
    monkeypatch.setattr(paper_strategy_runner.market_data, "subscribe", fake_subscribe)
    monkeypatch.setattr(paper_strategy_runner.market_data, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_positions", lambda: [])
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_orders", lambda status="open": [])
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2025-01-06T15:07:00+00:00"),
    )

    await paper_strategy_runner.start_phase1_paper_runner(fixed_quantity=10)
    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"].started_at = "2025-01-06T15:00:00+00:00"
    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"].last_live_bar_at = "2025-01-06T15:00:30+00:00"

    status = paper_strategy_runner.get_phase1_paper_runner_status()

    assert status["warnings"] == ["No live 1m bars observed for 390s during RTH"]

    await paper_strategy_runner.stop_phase1_paper_runner(close_position=False)
    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_get_phase1_paper_runner_history_filters_to_strategy_symbol_and_limit(
    monkeypatch,
):
    async def fake_get_trade_history(limit=50):
        assert limit == 15
        return [
            {
                "id": 5,
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 1,
                "price": 101.0,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "wrong-symbol",
                "status": "filled",
                "alpaca_order_id": "ord-5",
                "created_at": "2025-01-06T15:06:00+00:00",
            },
            {
                "id": 4,
                "symbol": "QQQ",
                "side": "sell",
                "quantity": 25,
                "price": 502.3,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "session-close",
                "status": "filled",
                "alpaca_order_id": "ord-4",
                "created_at": "2025-01-06T15:05:00+00:00",
            },
            {
                "id": 3,
                "symbol": "QQQ",
                "side": "buy",
                "quantity": 25,
                "price": 501.8,
                "strategy": "ma_crossover",
                "signal_reason": "wrong-strategy",
                "status": "filled",
                "alpaca_order_id": "ord-3",
                "created_at": "2025-01-06T15:04:00+00:00",
            },
            {
                "id": 2,
                "symbol": "QQQ",
                "side": "sell",
                "quantity": 25,
                "price": 502.1,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "take-profit",
                "status": "canceled",
                "alpaca_order_id": "ord-2",
                "created_at": "2025-01-06T15:03:00+00:00",
            },
            {
                "id": 1,
                "symbol": "QQQ",
                "side": "buy",
                "quantity": 25,
                "price": 501.5,
                "strategy": "brooks_small_pb_trend",
                "signal_reason": "entry",
                "status": "filled",
                "alpaca_order_id": "ord-1",
                "created_at": "2025-01-06T15:02:00+00:00",
            },
        ]

    monkeypatch.setattr(paper_strategy_runner, "get_trade_history", fake_get_trade_history)

    history = await paper_strategy_runner.get_phase1_paper_runner_history(limit=3)

    assert [trade["id"] for trade in history] == [4, 2, 1]


def test_get_phase1_paper_runner_readiness_reports_broker_and_stream_health(
    monkeypatch,
):
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2026-04-20T14:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "get_account",
        lambda: {"equity": 100000.0},
    )
    monkeypatch.setattr(
        paper_strategy_runner.market_data,
        "is_stream_running",
        lambda: True,
    )
    monkeypatch.setattr(
        paper_strategy_runner.trade_updates,
        "is_trade_updates_running",
        lambda: True,
    )

    readiness = paper_strategy_runner.get_phase1_paper_runner_readiness()

    assert readiness["ready"] is True
    assert readiness["paper_trading"] is True
    assert readiness["alpaca_configured"] is True
    assert readiness["account_status"] == "ok"
    assert readiness["market_session"] == "open"
    assert readiness["current_session_open"] == "2026-04-20T13:30:00+00:00"
    assert readiness["current_session_close"] == "2026-04-20T20:00:00+00:00"
    assert readiness["next_session_open"] == "2026-04-21T13:30:00+00:00"
    assert readiness["market_stream_running"] is True
    assert readiness["trade_updates_running"] is True
    assert readiness["warnings"] == []


def test_get_phase1_paper_runner_readiness_surfaces_configuration_warnings(
    monkeypatch,
):
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2026-04-19T12:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", False)
    monkeypatch.setattr(
        paper_strategy_runner.alpaca_client,
        "is_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        paper_strategy_runner.market_data,
        "is_stream_running",
        lambda: False,
    )
    monkeypatch.setattr(
        paper_strategy_runner.trade_updates,
        "is_trade_updates_running",
        lambda: False,
    )

    readiness = paper_strategy_runner.get_phase1_paper_runner_readiness()

    assert readiness["ready"] is False
    assert readiness["account_status"] == "unavailable"
    assert readiness["market_session"] == "closed"
    assert readiness["current_session_open"] is None
    assert readiness["current_session_close"] is None
    assert readiness["next_session_open"] == "2026-04-20T13:30:00+00:00"
    assert "PAPER_TRADING is disabled" in readiness["warnings"]
    assert "Alpaca credentials are not configured" in readiness["warnings"]


@pytest.mark.asyncio
async def test_restore_desired_phase1_runners_waits_until_market_open(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    start_calls = []

    async def fake_configs():
        return [
            paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
            )
        ]

    async def fake_start(**kwargs):
        start_calls.append(kwargs)
        return {"running": True}

    monkeypatch.setattr(
        paper_strategy_runner,
        "_market_session_snapshot",
        lambda: {
            "market_session": "closed",
            "current_session_open": None,
            "current_session_close": None,
            "next_session_open": "2026-04-27T13:30:00+00:00",
        },
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_get_desired_phase1_runner_configs",
        fake_configs,
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_start_phase1_paper_runner",
        fake_start,
    )

    restored = await paper_strategy_runner.restore_desired_phase1_paper_runners()

    assert restored == []
    assert start_calls == []


@pytest.mark.asyncio
async def test_restore_desired_phase1_runners_stops_active_runners_after_close(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    stop_calls = []
    inactive_calls = []

    class FakeRunner:
        def __init__(self):
            self.running = True
            self.config = paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
            )

        async def stop(self, close_position: bool = True):
            stop_calls.append(close_position)
            self.running = False
            return {"running": False}

    async def fake_mark_inactive(strategy: str):
        inactive_calls.append(strategy)

    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"] = FakeRunner()
    monkeypatch.setattr(
        paper_strategy_runner,
        "_market_session_snapshot",
        lambda: {
            "market_session": "closed",
            "current_session_open": None,
            "current_session_close": None,
            "next_session_open": "2026-04-27T13:30:00+00:00",
        },
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_mark_desired_phase1_runner_inactive",
        fake_mark_inactive,
    )

    restored = await paper_strategy_runner.restore_desired_phase1_paper_runners()

    assert restored == []
    assert stop_calls == [True]
    assert inactive_calls == []
    assert "brooks_small_pb_trend" not in paper_strategy_runner._phase1_runners


@pytest.mark.asyncio
async def test_restore_desired_phase1_runners_restarts_stale_open_market_runner(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    stop_calls = []
    start_calls = []

    class FakeRunner:
        def __init__(self):
            self.running = True
            self.config = paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
                fixed_quantity=25,
            )
            self.started_at = "2025-01-06T14:30:00+00:00"
            self.last_live_bar_at = "2025-01-06T14:31:00+00:00"

        async def stop(self, close_position: bool = True):
            stop_calls.append(close_position)
            self.running = False
            return {"running": False}

        def status(self):
            return {
                "running": self.running,
                "strategy": self.config.strategy,
                "warnings": ["No live 1m bars observed for 600s during RTH"],
            }

    async def fake_configs():
        return [
            paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
                fixed_quantity=25,
            )
        ]

    async def fake_start(**kwargs):
        start_calls.append(kwargs)
        return {"running": True, "strategy": kwargs["strategy"]}

    monkeypatch.setattr(
        paper_strategy_runner,
        "_market_session_snapshot",
        lambda: {
            "market_session": "open",
            "current_session_open": "2025-01-06T14:30:00+00:00",
            "current_session_close": "2025-01-06T21:00:00+00:00",
            "next_session_open": "2025-01-07T14:30:00+00:00",
        },
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2025-01-06T14:41:00+00:00"),
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_get_desired_phase1_runner_configs",
        fake_configs,
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_start_phase1_paper_runner",
        fake_start,
    )

    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"] = FakeRunner()

    restored = await paper_strategy_runner.restore_desired_phase1_paper_runners()

    assert stop_calls == [False]
    assert start_calls == [
        {
            "strategy": "brooks_small_pb_trend",
            "fixed_quantity": 25,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 4.0,
            "exit_policy": None,
            "history_days": 10,
            "params": None,
            "persist_desired": False,
        }
    ]
    assert restored == [{"running": True, "strategy": "brooks_small_pb_trend"}]


@pytest.mark.asyncio
async def test_restore_desired_phase1_runners_refreshes_pending_orders_before_restart(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()
    refresh_calls = []
    stop_calls = []
    start_calls = []

    class FakeRunner:
        def __init__(self):
            self.running = True
            self.config = paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
                fixed_quantity=25,
            )
            self.started_at = "2025-01-06T14:30:00+00:00"
            self.last_live_bar_at = "2025-01-06T14:31:00+00:00"
            self.pending_order = paper_strategy_runner.PendingOrder(
                alpaca_order_id="ord-1",
                side="buy",
                quantity=25,
                status="new",
                reason="entry",
                submitted_at="2025-01-06T14:31:00+00:00",
                signal_time="2025-01-06T14:30:00+00:00",
            )

        async def _refresh_pending_order(self):
            refresh_calls.append(self.pending_order.alpaca_order_id)
            self.pending_order = None
            self.position = paper_strategy_runner.LivePosition(
                quantity=25,
                entry_price=501.0,
                stop_price=500.0,
                target_price=None,
                entry_time="2025-01-06T14:32:00+00:00",
                signal_time="2025-01-06T14:30:00+00:00",
                reason="entry",
                stop_reason="test_stop",
                target_reason=None,
                initial_risk=1.0,
                max_favorable_price=501.0,
            )

        async def stop(self, close_position: bool = True):
            stop_calls.append(close_position)
            self.running = False
            return {"running": False}

        def status(self):
            return {
                "running": self.running,
                "strategy": self.config.strategy,
                "position": None if getattr(self, "position", None) is None else {"quantity": 25},
                "pending_order": None,
            }

    async def fake_configs():
        return [
            paper_strategy_runner.Phase1PaperConfig(
                strategy="brooks_small_pb_trend",
                fixed_quantity=25,
            )
        ]

    async def fake_start(**kwargs):
        start_calls.append(kwargs)
        return {"running": True, "strategy": kwargs["strategy"]}

    monkeypatch.setattr(
        paper_strategy_runner,
        "_market_session_snapshot",
        lambda: {
            "market_session": "open",
            "current_session_open": "2025-01-06T14:30:00+00:00",
            "current_session_close": "2025-01-06T21:00:00+00:00",
            "next_session_open": "2025-01-07T14:30:00+00:00",
        },
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2025-01-06T14:41:00+00:00"),
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_get_desired_phase1_runner_configs",
        fake_configs,
    )
    monkeypatch.setattr(
        paper_strategy_runner,
        "_start_phase1_paper_runner",
        fake_start,
    )

    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"] = FakeRunner()

    restored = await paper_strategy_runner.restore_desired_phase1_paper_runners()

    assert refresh_calls == ["ord-1"]
    assert stop_calls == []
    assert start_calls == []
    assert restored == [
        {
            "running": True,
            "strategy": "brooks_small_pb_trend",
            "position": {"quantity": 25},
            "pending_order": None,
        }
    ]


def test_get_phase1_paper_runner_readiness_is_not_ready_when_active_runner_stale(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    class FakeRunner:
        running = True
        started_at = "2026-04-20T13:30:00+00:00"
        last_live_bar_at = "2026-04-20T13:31:00+00:00"
        config = paper_strategy_runner.Phase1PaperConfig(strategy="brooks_small_pb_trend")

    paper_strategy_runner._phase1_runners["brooks_small_pb_trend"] = FakeRunner()
    monkeypatch.setattr(
        paper_strategy_runner,
        "_now_utc",
        lambda: datetime.fromisoformat("2026-04-20T14:00:00+00:00"),
    )
    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(paper_strategy_runner.alpaca_client, "get_account", lambda: {"equity": 100000.0})
    monkeypatch.setattr(paper_strategy_runner.market_data, "is_stream_running", lambda: True)
    monkeypatch.setattr(paper_strategy_runner.trade_updates, "is_trade_updates_running", lambda: True)

    readiness = paper_strategy_runner.get_phase1_paper_runner_readiness()

    assert readiness["ready"] is False
    assert readiness["runner_running"] is True
    assert "Active runner brooks_small_pb_trend has stale live bars" in readiness["warnings"]

    paper_strategy_runner.reset_phase1_paper_runner()


@pytest.mark.asyncio
async def test_start_phase1_paper_runner_removes_runner_when_start_fails(monkeypatch):
    paper_strategy_runner.reset_phase1_paper_runner()

    async def fake_start(self):
        raise RuntimeError("bars fetch timed out")

    monkeypatch.setattr(paper_strategy_runner, "PAPER_TRADING", True)
    monkeypatch.setattr(paper_strategy_runner.Phase1PaperRunner, "start", fake_start)

    with pytest.raises(RuntimeError, match="bars fetch timed out"):
        await paper_strategy_runner.start_phase1_paper_runner(
            strategy="brooks_small_pb_trend",
        )

    assert "brooks_small_pb_trend" not in paper_strategy_runner._phase1_runners
