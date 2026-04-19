from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from config import PAPER_TRADING
from services import market_data
from services.alpaca_client import alpaca_client
from services.analysis_bars import get_analysis_bars
from services.research_profile import (
    is_rth_bar_timestamp,
    is_session_final_bar_timestamp,
    market_time,
)
from services.strategy_engine import get_strategy
from services.trade_executor import execute_order, get_trade_history, refresh_trade_statuses
from strategies.base import SignalType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase1PaperConfig:
    strategy: str = "brooks_small_pb_trend"
    symbol: str = "QQQ"
    timeframe: str = "5m"
    research_profile: str = "qqq_5m_phase1"
    fixed_quantity: int = 100
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    history_days: int = 10
    params: dict[str, Any] | None = None


@dataclass
class LivePosition:
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float
    entry_time: str
    reason: str


@dataclass
class PendingOrder:
    alpaca_order_id: str
    side: str
    quantity: int
    status: str
    reason: str


class Phase1PaperRunner:
    def __init__(self, config: Phase1PaperConfig):
        self.config = config
        self.strategy = get_strategy(config.strategy, config.params)
        self.bars: list[dict] = []
        self.partial_bar: dict | None = None
        self.partial_slot_time: str | None = None
        self.position: LivePosition | None = None
        self.pending_order: PendingOrder | None = None
        self.running = False
        self.lock = asyncio.Lock()
        self.orders_submitted = 0
        self.last_completed_bar_time: str | None = None
        self.last_error: str | None = None

    async def start(self) -> dict:
        start_day = (
            datetime.now(timezone.utc) - timedelta(days=self.config.history_days)
        ).date().isoformat()
        self.bars = await get_analysis_bars(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            start=start_day,
            limit=1000,
            research_profile=self.config.research_profile,
        )
        if not self.bars:
            raise RuntimeError("No historical bars available for phase-1 paper runner")

        await self._restore_broker_state()
        self.running = True
        await market_data.subscribe(self.config.symbol, self._on_live_bar)
        return self.status()

    async def stop(self, close_position: bool = True) -> dict:
        if not self.running:
            return self.status()

        async with self.lock:
            if close_position and self.position is not None and self.bars:
                await self._submit_exit(
                    exit_price=self.bars[-1]["close"],
                    exit_time=self.bars[-1]["time"],
                    reason="manual_stop",
                )
            self.running = False
            self.partial_bar = None
            self.partial_slot_time = None

        await market_data.unsubscribe(self.config.symbol, self._on_live_bar)
        return self.status()

    def status(self) -> dict:
        return {
            "running": self.running,
            "strategy": self.config.strategy,
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe,
            "research_profile": self.config.research_profile,
            "fixed_quantity": self.config.fixed_quantity,
            "stop_loss_pct": self.config.stop_loss_pct,
            "take_profit_pct": self.config.take_profit_pct,
            "history_days": self.config.history_days,
            "params": self.config.params,
            "bar_count": len(self.bars),
            "last_completed_bar_time": self.last_completed_bar_time,
            "orders_submitted": self.orders_submitted,
            "position": None if self.position is None else asdict(self.position),
            "pending_order": None if self.pending_order is None else asdict(self.pending_order),
            "last_error": self.last_error,
        }

    async def _on_live_bar(self, symbol: str, payload: dict) -> None:
        if not self.running or "time" not in payload:
            return

        async with self.lock:
            try:
                await self._ingest_live_bar(payload)
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Phase-1 paper runner failed on live bar")

    async def _ingest_live_bar(self, bar: dict) -> None:
        if not is_rth_bar_timestamp(bar["time"]):
            if self.partial_bar is not None:
                await self._finalize_partial_bar()
            self.partial_bar = None
            self.partial_slot_time = None
            return

        slot_time = _five_min_slot_timestamp(bar["time"])
        if self.partial_slot_time is None:
            self.partial_slot_time = slot_time
            self.partial_bar = _start_aggregate_bar(slot_time, bar)
            return

        if slot_time == self.partial_slot_time:
            self.partial_bar = _merge_aggregate_bar(self.partial_bar, bar)
            return

        await self._finalize_partial_bar()
        self.partial_slot_time = slot_time
        self.partial_bar = _start_aggregate_bar(slot_time, bar)

    async def _finalize_partial_bar(self) -> None:
        if self.partial_bar is None:
            return

        completed_bar = self.partial_bar
        self.partial_bar = None
        self.partial_slot_time = None

        self._upsert_completed_bar(completed_bar)
        self.last_completed_bar_time = completed_bar["time"]

        await self._evaluate_completed_bar(completed_bar)

    def _upsert_completed_bar(self, completed_bar: dict) -> None:
        if self.bars and self.bars[-1]["time"] == completed_bar["time"]:
            self.bars[-1] = completed_bar
            return
        self.bars.append(completed_bar)
        if len(self.bars) > 1000:
            self.bars = self.bars[-1000:]

    async def _evaluate_completed_bar(self, bar: dict) -> None:
        await self._refresh_pending_order()
        if self.pending_order is not None:
            return

        if self.position is not None:
            if bar["low"] <= self.position.stop_price:
                await self._submit_exit(
                    exit_price=self.position.stop_price,
                    exit_time=bar["time"],
                    reason="stop_loss",
                )
            elif self.position is not None and bar["high"] >= self.position.target_price:
                await self._submit_exit(
                    exit_price=self.position.target_price,
                    exit_time=bar["time"],
                    reason="take_profit",
                )

        if self.position is None:
            signals = self.strategy.generate_signals(self.config.symbol, self.bars)
            matching_signal = next(
                (
                    signal
                    for signal in reversed(signals)
                    if signal.timestamp.isoformat() == bar["time"]
                    and signal.signal_type == SignalType.BUY
                ),
                None,
            )
            if matching_signal is not None:
                await self._submit_entry(matching_signal.price, bar["time"], matching_signal.reason)

        if self.position is not None and is_session_final_bar_timestamp(bar["time"], 5):
            await self._submit_exit(
                exit_price=bar["close"],
                exit_time=bar["time"],
                reason="session_close",
            )

    async def _submit_entry(self, entry_price: float, entry_time: str, reason: str) -> None:
        trade_info = await execute_order(
            symbol=self.config.symbol,
            qty=self.config.fixed_quantity,
            side="buy",
            strategy=self.config.strategy,
            reason=reason,
        )
        self.orders_submitted += 1
        if trade_info.get("status") == "filled":
            filled_price = float(trade_info.get("price") or entry_price)
            self.position = LivePosition(
                quantity=int(trade_info.get("qty") or self.config.fixed_quantity),
                entry_price=filled_price,
                stop_price=filled_price * (1 - self.config.stop_loss_pct / 100.0),
                target_price=filled_price * (1 + self.config.take_profit_pct / 100.0),
                entry_time=entry_time,
                reason=reason,
            )
            return

        self.pending_order = PendingOrder(
            alpaca_order_id=str(trade_info.get("alpaca_order_id")),
            side="buy",
            quantity=int(trade_info.get("qty") or self.config.fixed_quantity),
            status=str(trade_info.get("status") or "submitted"),
            reason=reason,
        )

    async def _submit_exit(self, exit_price: float, exit_time: str, reason: str) -> None:
        if self.position is None:
            return

        trade_info = await execute_order(
            symbol=self.config.symbol,
            qty=self.position.quantity,
            side="sell",
            strategy=self.config.strategy,
            reason=reason,
        )
        self.orders_submitted += 1
        if trade_info.get("status") == "filled":
            self.position = None
            return

        self.pending_order = PendingOrder(
            alpaca_order_id=str(trade_info.get("alpaca_order_id")),
            side="sell",
            quantity=int(trade_info.get("qty") or self.position.quantity),
            status=str(trade_info.get("status") or "submitted"),
            reason=reason,
        )

    async def _restore_broker_state(self) -> None:
        recent_trades = await get_trade_history(limit=25)
        strategy_trades = [
            trade
            for trade in recent_trades
            if trade.get("symbol") == self.config.symbol
            and trade.get("strategy") == self.config.strategy
        ]

        open_orders = {
            order["id"]: order
            for order in alpaca_client.get_orders("open")
            if order.get("symbol") == self.config.symbol
        }
        recovered_pending = next(
            (
                trade
                for trade in strategy_trades
                if trade.get("alpaca_order_id") in open_orders
            ),
            None,
        )
        if recovered_pending is not None:
            pending_order = open_orders[recovered_pending["alpaca_order_id"]]
            self.pending_order = PendingOrder(
                alpaca_order_id=recovered_pending["alpaca_order_id"],
                side=str(pending_order["side"]),
                quantity=int(float(pending_order["qty"])),
                status=str(pending_order["status"]),
                reason=str(recovered_pending.get("signal_reason") or recovered_pending["side"]),
            )

        broker_position = next(
            (
                position
                for position in alpaca_client.get_positions()
                if position.get("symbol") == self.config.symbol
                and int(float(position.get("qty", 0))) > 0
            ),
            None,
        )
        if broker_position is None:
            return

        recent_buy = next(
            (trade for trade in strategy_trades if trade.get("side") == "buy"),
            None,
        )
        entry_price = float(broker_position["avg_entry"])
        quantity = int(float(broker_position["qty"]))
        self.position = LivePosition(
            quantity=quantity,
            entry_price=entry_price,
            stop_price=entry_price * (1 - self.config.stop_loss_pct / 100.0),
            target_price=entry_price * (1 + self.config.take_profit_pct / 100.0),
            entry_time=str(
                (recent_buy or {}).get("created_at")
                or datetime.now(timezone.utc).isoformat()
            ),
            reason=str((recent_buy or {}).get("signal_reason") or "recovered_broker_position"),
        )
        if self.pending_order is not None and self.pending_order.side == "buy":
            self.pending_order = None

    async def _refresh_pending_order(self) -> None:
        if self.pending_order is None:
            return

        order = alpaca_client.get_order_by_id(self.pending_order.alpaca_order_id)
        await refresh_trade_statuses(order_ids=[self.pending_order.alpaca_order_id])

        status = str(order.get("status") or self.pending_order.status)
        self.pending_order.status = status
        if status in {"new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled", "pending_replace", "pending_cancel", "calculated"}:
            return

        if status == "filled":
            if self.pending_order.side == "buy":
                entry_price = float(order.get("filled_avg_price") or 0.0)
                quantity = int(float(order.get("filled_qty") or order.get("qty") or self.pending_order.quantity))
                self.position = LivePosition(
                    quantity=quantity,
                    entry_price=entry_price,
                    stop_price=entry_price * (1 - self.config.stop_loss_pct / 100.0),
                    target_price=entry_price * (1 + self.config.take_profit_pct / 100.0),
                    entry_time=str(order.get("filled_at") or order.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    reason=self.pending_order.reason,
                )
            else:
                self.position = None

        self.pending_order = None


_phase1_runner: Phase1PaperRunner | None = None


def reset_phase1_paper_runner() -> None:
    global _phase1_runner
    _phase1_runner = None


async def start_phase1_paper_runner(
    fixed_quantity: int = 100,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    history_days: int = 10,
    params: dict[str, Any] | None = None,
) -> dict:
    global _phase1_runner

    if not PAPER_TRADING:
        raise RuntimeError("Phase-1 paper runner requires PAPER_TRADING=true")
    if _phase1_runner is not None and _phase1_runner.running:
        raise RuntimeError("Phase-1 paper runner is already running")

    runner = Phase1PaperRunner(
        Phase1PaperConfig(
            fixed_quantity=fixed_quantity,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            history_days=history_days,
            params=params,
        )
    )
    _phase1_runner = runner
    return await runner.start()


async def stop_phase1_paper_runner(close_position: bool = True) -> dict:
    if _phase1_runner is None:
        return {
            "running": False,
            "strategy": "brooks_small_pb_trend",
            "symbol": "QQQ",
            "timeframe": "5m",
            "research_profile": "qqq_5m_phase1",
            "position": None,
            "orders_submitted": 0,
            "bar_count": 0,
            "last_completed_bar_time": None,
            "pending_order": None,
            "last_error": None,
        }
    return await _phase1_runner.stop(close_position=close_position)


def get_phase1_paper_runner_status() -> dict:
    if _phase1_runner is None:
        return {
            "running": False,
            "strategy": "brooks_small_pb_trend",
            "symbol": "QQQ",
            "timeframe": "5m",
            "research_profile": "qqq_5m_phase1",
            "fixed_quantity": 100,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 4.0,
            "history_days": 10,
            "params": None,
            "bar_count": 0,
            "last_completed_bar_time": None,
            "orders_submitted": 0,
            "position": None,
            "pending_order": None,
            "last_error": None,
        }
    return _phase1_runner.status()


def _five_min_slot_timestamp(timestamp: str) -> str:
    local = market_time(timestamp)
    floored_minute = (local.minute // 5) * 5
    slot_local = local.replace(minute=floored_minute, second=0, microsecond=0)
    return slot_local.astimezone(timezone.utc).isoformat()


def _start_aggregate_bar(slot_time: str, minute_bar: dict) -> dict:
    return {
        "time": slot_time,
        "open": float(minute_bar["open"]),
        "high": float(minute_bar["high"]),
        "low": float(minute_bar["low"]),
        "close": float(minute_bar["close"]),
        "volume": int(minute_bar["volume"]),
    }


def _merge_aggregate_bar(current_bar: dict, minute_bar: dict) -> dict:
    return {
        "time": current_bar["time"],
        "open": current_bar["open"],
        "high": max(float(current_bar["high"]), float(minute_bar["high"])),
        "low": min(float(current_bar["low"]), float(minute_bar["low"])),
        "close": float(minute_bar["close"]),
        "volume": int(current_bar["volume"]) + int(minute_bar["volume"]),
    }
