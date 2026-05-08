from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import select

from config import PAPER_TRADING
from database import async_session
from models import PaperRunnerConfig
from services import market_data, trade_updates
from services.alpaca_client import alpaca_client
from services.analysis_bars import get_analysis_bars
from services.phase1_exit import build_exit_plan
from services.phase1_exit import (
    build_dynamic_exit_update,
    build_dynamic_exit_visualization,
    compute_ema_series,
)
from services.research_profile import (
    is_rth_bar_timestamp,
    is_session_final_bar_timestamp,
    market_time,
)
from services.strategy_engine import get_strategy
from services.trade_executor import (
    add_trade_listener,
    execute_order,
    get_trade_history,
    refresh_trade_statuses,
    remove_trade_listener,
)
from services.bars_cache import MARKET_TZ, SESSION_OPEN, _is_trading_day, _next_trading_day, _session_close_for
from strategies.base import SignalType

logger = logging.getLogger(__name__)

DEFAULT_PHASE1_STRATEGY = "brooks_small_pb_trend"
BROOKS_COMBO_LABEL = "QQQ 5m Brooks 组合"
SUPPORTED_PHASE1_STRATEGIES = {
    "brooks_small_pb_trend",
    "brooks_breakout_pullback",
    "brooks_pullback_count",
}


@dataclass(frozen=True)
class Phase1PaperConfig:
    strategy: str = DEFAULT_PHASE1_STRATEGY
    symbol: str = "QQQ"
    timeframe: str = "5m"
    research_profile: str = "qqq_5m_phase1"
    fixed_quantity: int = 100
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    exit_policy: str | None = None
    history_days: int = 10
    params: dict[str, Any] | None = None


@dataclass
class LivePosition:
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float | None
    entry_time: str
    signal_time: str
    reason: str
    stop_reason: str
    target_reason: str | None
    initial_risk: float
    max_favorable_price: float


@dataclass
class PendingOrder:
    alpaca_order_id: str
    side: str
    quantity: int
    status: str
    reason: str
    submitted_at: str
    signal_time: str


@dataclass
class LastExit:
    quantity: int
    exit_price: float
    exit_time: str
    reason: str


@dataclass
class RunnerEvent:
    timestamp: str
    type: str
    message: str


class Phase1PaperRunner:
    def __init__(self, config: Phase1PaperConfig):
        self.config = config
        self.strategy = get_strategy(config.strategy, config.params)
        self.bars: list[dict] = []
        self.partial_bar: dict | None = None
        self.partial_slot_time: str | None = None
        self.position: LivePosition | None = None
        self.pending_order: PendingOrder | None = None
        self.last_exit: LastExit | None = None
        self.running = False
        self.lock = asyncio.Lock()
        # Serializes live-bar ingestion without blocking trade-update callbacks.
        # ``_evaluate_completed_bar()`` can submit orders, and order submission can
        # synchronously notify ``_on_trade_update()``, which needs ``self.lock``.
        # Holding ``self.lock`` across live-bar ingestion would therefore deadlock.
        self.live_bar_lock = asyncio.Lock()
        self.orders_submitted = 0
        self.started_at: str | None = None
        self.last_completed_bar_time: str | None = None
        self.last_live_bar_at: str | None = None
        self.last_trade_update_at: str | None = None
        self.last_error: str | None = None
        self.recent_events: deque[RunnerEvent] = deque(maxlen=40)

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
            raise RuntimeError(f"No historical bars available for {BROOKS_COMBO_LABEL}")

        await self._restore_broker_state()
        self.running = True
        self.started_at = _now_utc().isoformat()
        add_trade_listener(self._on_trade_update)
        await market_data.subscribe(self.config.symbol, self._on_live_bar)
        self._record_event(
            "runner_started",
            f"Started {self.config.strategy} on {self.config.symbol} {self.config.timeframe}",
        )
        return self.status()

    async def stop(self, close_position: bool = True) -> dict:
        if not self.running:
            return self.status()

        # Do not hold ``self.lock`` while submitting the exit order.
        # ``execute_order()`` synchronously notifies trade listeners, including
        # ``self._on_trade_update()``, which also acquires ``self.lock``. Holding
        # the lock across ``_submit_exit()`` deadlocks the stop request and makes
        # cron report a TimeoutError even though Alpaca may already have filled
        # the closing order.
        should_close = close_position and self.position is not None and self.bars
        if should_close:
            await self._submit_exit(
                exit_price=self.bars[-1]["close"],
                exit_time=self.bars[-1]["time"],
                reason="manual_stop",
            )

        async with self.lock:
            self.running = False
            self.partial_bar = None
            self.partial_slot_time = None

        await market_data.unsubscribe(self.config.symbol, self._on_live_bar)
        remove_trade_listener(self._on_trade_update)
        self._record_event("runner_stopped", f"{BROOKS_COMBO_LABEL} stopped")
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
            "exit_policy": self.config.exit_policy,
            "history_days": self.config.history_days,
            "params": self.config.params,
            "bar_count": len(self.bars),
            "started_at": self.started_at,
            "last_completed_bar_time": self.last_completed_bar_time,
            "last_live_bar_at": self.last_live_bar_at,
            "last_trade_update_at": self.last_trade_update_at,
            "orders_submitted": self.orders_submitted,
            "position": None if self.position is None else asdict(self.position),
            "dynamic_exit": self._dynamic_exit_status(),
            "last_exit": None if self.last_exit is None else asdict(self.last_exit),
            "pending_order": None if self.pending_order is None else asdict(self.pending_order),
            "last_error": self.last_error,
            "warnings": self._status_warnings(),
            "recent_events": [asdict(event) for event in self.recent_events],
        }

    def _dynamic_exit_status(self) -> dict | None:
        if self.position is None or not self.bars:
            return None

        visualization = build_dynamic_exit_visualization(
            strategy_name=self.config.strategy,
            research_profile=self.config.research_profile,
            exit_policy=self.config.exit_policy,
            bars=self.bars,
            bar_index=len(self.bars) - 1,
            ema_values=compute_ema_series(self.bars, 20),
            side="long",
            signal_time=self.position.signal_time,
            entry_price=self.position.entry_price,
            initial_risk=self.position.initial_risk,
            max_favorable_price=self.position.max_favorable_price,
        )
        return None if visualization is None else asdict(visualization)

    async def _on_live_bar(self, symbol: str, payload: dict) -> None:
        if not self.running or "time" not in payload:
            return

        self.last_live_bar_at = payload["time"]

        async with self.live_bar_lock:
            try:
                await self._ingest_live_bar(payload)
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                self._record_event("runner_error", str(exc))
                logger.exception("%s failed on live bar", BROOKS_COMBO_LABEL)

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
            elif (
                self.position is not None
                and self.position.target_price is not None
                and bar["high"] >= self.position.target_price
            ):
                await self._submit_exit(
                    exit_price=self.position.target_price,
                    exit_time=bar["time"],
                    reason="take_profit",
                )
            else:
                candidate_max_favorable_price = max(
                    self.position.max_favorable_price,
                    float(bar["high"]),
                )
                dynamic_update = build_dynamic_exit_update(
                    strategy_name=self.config.strategy,
                    research_profile=self.config.research_profile,
                    exit_policy=self.config.exit_policy,
                    bars=self.bars,
                    bar_index=len(self.bars) - 1,
                    ema_values=compute_ema_series(self.bars, 20),
                    side="long",
                    signal_time=self.position.signal_time,
                    entry_price=self.position.entry_price,
                    current_stop_price=self.position.stop_price,
                    current_target_price=self.position.target_price,
                    initial_risk=self.position.initial_risk,
                    max_favorable_price=candidate_max_favorable_price,
                )
                if dynamic_update is not None and dynamic_update.exit_reason is not None:
                    await self._submit_exit(
                        exit_price=dynamic_update.exit_price,
                        exit_time=bar["time"],
                        reason=dynamic_update.exit_reason,
                    )
                elif self.position is not None:
                    if (
                        dynamic_update is not None
                        and dynamic_update.stop_price is not None
                        and dynamic_update.stop_price > self.position.stop_price
                    ):
                        self.position.stop_price = dynamic_update.stop_price
                        self.position.stop_reason = (
                            dynamic_update.stop_reason or self.position.stop_reason
                        )
                        self._record_event(
                            "stop_updated",
                            f"Raised stop to {self.position.stop_price:.2f} ({self.position.stop_reason})",
                        )
                    if (
                        dynamic_update is not None
                        and dynamic_update.target_price is not None
                    ):
                        self.position.target_price = dynamic_update.target_price
                        self.position.target_reason = dynamic_update.target_reason
                    self.position.max_favorable_price = candidate_max_favorable_price

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
                self._record_event(
                    "signal_detected",
                    f"Signal at {bar['time']} ({matching_signal.reason})",
                )
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
        self._record_event(
            "order_submitted",
            f"Submitted buy {self.config.fixed_quantity} ({reason})",
        )
        if trade_info.get("status") == "filled":
            filled_price = float(trade_info.get("price") or entry_price)
            exit_plan = build_exit_plan(
                strategy_name=self.config.strategy,
                research_profile=self.config.research_profile,
                bars=self.bars,
                signal_time=entry_time,
                side="long",
                entry_price=filled_price,
                stop_loss_pct=self.config.stop_loss_pct,
                take_profit_pct=self.config.take_profit_pct,
                exit_policy=self.config.exit_policy,
            )
            self.position = LivePosition(
                quantity=int(trade_info.get("qty") or self.config.fixed_quantity),
                entry_price=filled_price,
                stop_price=exit_plan.stop_price,
                target_price=exit_plan.target_price,
                entry_time=entry_time,
                signal_time=entry_time,
                reason=reason,
                stop_reason=exit_plan.stop_reason,
                target_reason=exit_plan.target_reason,
                initial_risk=abs(filled_price - exit_plan.stop_price),
                max_favorable_price=filled_price,
            )
            self.last_exit = None
            self._record_event(
                "position_opened",
                f"Opened {self.position.quantity} @ {filled_price:.2f}",
            )
            return

        self.pending_order = PendingOrder(
            alpaca_order_id=str(trade_info.get("alpaca_order_id")),
            side="buy",
            quantity=int(trade_info.get("qty") or self.config.fixed_quantity),
            status=str(trade_info.get("status") or "submitted"),
            reason=reason,
            submitted_at=_now_utc().isoformat(),
            signal_time=entry_time,
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
        self._record_event(
            "order_submitted",
            f"Submitted sell {self.position.quantity} ({reason})",
        )
        if trade_info.get("status") == "filled":
            filled_price = float(trade_info.get("price") or exit_price)
            self.last_exit = LastExit(
                quantity=self.position.quantity,
                exit_price=filled_price,
                exit_time=exit_time,
                reason=reason,
            )
            self.position = None
            self._record_event(
                "position_closed",
                f"Closed position via {reason} @ {filled_price:.2f}",
            )
            return

        self.pending_order = PendingOrder(
            alpaca_order_id=str(trade_info.get("alpaca_order_id")),
            side="sell",
            quantity=int(trade_info.get("qty") or self.position.quantity),
            status=str(trade_info.get("status") or "submitted"),
            reason=reason,
            submitted_at=_now_utc().isoformat(),
            signal_time=exit_time,
        )

    async def _restore_broker_state(self) -> None:
        recent_trades = await get_trade_history(limit=200)
        strategy_trades = sorted(
            (
                trade
                for trade in recent_trades
                if trade.get("symbol") == self.config.symbol
                and trade.get("strategy") == self.config.strategy
            ),
            key=lambda trade: (
                trade.get("created_at") or "",
                int(trade.get("id") or 0),
            ),
        )

        open_orders = {
            order["id"]: order
            for order in await asyncio.to_thread(alpaca_client.get_orders, "open")
            if order.get("symbol") == self.config.symbol
        }
        broker_position = next(
            (
                position
                for position in await asyncio.to_thread(alpaca_client.get_positions)
                if position.get("symbol") == self.config.symbol
            ),
            None,
        )
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
            submitted_at = str(
                recovered_pending.get("created_at")
                or pending_order.get("created_at")
                or _now_utc().isoformat()
            )
            pending_side = str(pending_order["side"])
            self.pending_order = PendingOrder(
                alpaca_order_id=recovered_pending["alpaca_order_id"],
                side=pending_side,
                quantity=int(float(pending_order["qty"])),
                status=str(pending_order["status"]),
                reason=str(recovered_pending.get("signal_reason") or recovered_pending["side"]),
                submitted_at=submitted_at,
                signal_time=(
                    _previous_five_min_slot_timestamp(submitted_at)
                    if pending_side == "buy"
                    else submitted_at
                ),
            )
            self._record_event(
                "pending_order_recovered",
                f"Recovered {self.pending_order.side} order {self.pending_order.alpaca_order_id}",
            )

        recovered_buys: list[dict] = []
        recovered_quantity = 0
        for trade in strategy_trades:
            if trade.get("status") != "filled":
                continue
            side = str(trade.get("side") or "")
            quantity = int(float(trade.get("quantity") or 0))
            if side == "buy":
                recovered_buys.append(trade)
                recovered_quantity += quantity
            elif side == "sell":
                if quantity >= recovered_quantity:
                    recovered_buys = []
                    recovered_quantity = 0
                else:
                    remaining_to_match = quantity
                    while remaining_to_match > 0 and recovered_buys:
                        latest_buy = recovered_buys[-1]
                        latest_buy_qty = int(float(latest_buy.get("quantity") or 0))
                        if latest_buy_qty <= remaining_to_match:
                            remaining_to_match -= latest_buy_qty
                            recovered_buys.pop()
                        else:
                            latest_buy["quantity"] = latest_buy_qty - remaining_to_match
                            remaining_to_match = 0
                    recovered_quantity -= quantity
                    if recovered_quantity < 0:
                        recovered_quantity = 0

        if recovered_quantity <= 0 or not recovered_buys:
            return

        total_buy_cost = sum(
            int(float(trade.get("quantity") or 0)) * float(trade.get("price") or 0.0)
            for trade in recovered_buys
        )
        quantity = sum(int(float(trade.get("quantity") or 0)) for trade in recovered_buys)
        if quantity <= 0:
            return

        broker_long_quantity = (
            max(0, int(float(broker_position.get("qty") or 0)))
            if broker_position is not None
            else 0
        )
        open_sell_quantity = sum(
            max(
                0,
                int(float(order.get("qty") or 0))
                - int(float(order.get("filled_qty") or 0)),
            )
            for order in open_orders.values()
            if str(order.get("side") or "").lower() == "sell"
        )
        broker_available_quantity = max(0, broker_long_quantity - open_sell_quantity)
        if broker_available_quantity <= 0:
            self._record_event(
                "position_recovery_skipped",
                "Skipped local position recovery: no broker-available long quantity",
            )
            return

        local_quantity = quantity
        quantity = min(local_quantity, broker_available_quantity)
        broker_entry_price = (
            float(broker_position.get("avg_entry") or 0.0)
            if broker_position is not None
            else 0.0
        )
        local_entry_price = total_buy_cost / local_quantity if total_buy_cost > 0 else 0.0
        entry_price = (
            broker_entry_price
            if broker_entry_price > 0 and quantity != local_quantity
            else local_entry_price
        )
        if entry_price <= 0:
            entry_price = float(recovered_buys[-1].get("price") or 0.0)

        recent_buy = recovered_buys[-1]
        recovered_entry_time = str(
            recent_buy.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        )
        recovered_signal_time = _previous_five_min_slot_timestamp(recovered_entry_time)
        exit_plan = build_exit_plan(
            strategy_name=self.config.strategy,
            research_profile=self.config.research_profile,
            bars=self.bars,
            signal_time=recovered_signal_time,
            side="long",
            entry_price=entry_price,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            exit_policy=self.config.exit_policy,
        )
        self.position = LivePosition(
            quantity=quantity,
            entry_price=entry_price,
            stop_price=exit_plan.stop_price,
            target_price=exit_plan.target_price,
            entry_time=recovered_entry_time,
            signal_time=recovered_signal_time,
            reason=str(recent_buy.get("signal_reason") or "recovered_local_position"),
            stop_reason=exit_plan.stop_reason,
            target_reason=exit_plan.target_reason,
            initial_risk=abs(entry_price - exit_plan.stop_price),
            max_favorable_price=self._max_favorable_price_since(
                recovered_signal_time,
                entry_price,
            ),
        )
        self.last_exit = None
        self._record_event(
            "position_recovered",
            f"Recovered {quantity} shares @ {entry_price:.2f}",
        )
        if self.pending_order is not None and self.pending_order.side == "buy":
            self.pending_order = None

    async def _refresh_pending_order(self) -> None:
        if self.pending_order is None:
            return

        order = await asyncio.to_thread(
            alpaca_client.get_order_by_id,
            self.pending_order.alpaca_order_id,
        )
        await refresh_trade_statuses(order_ids=[self.pending_order.alpaca_order_id])

        status = str(order.get("status") or self.pending_order.status)
        self.pending_order.status = status
        if status in {"new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled", "pending_replace", "pending_cancel", "calculated"}:
            return

        if status == "filled":
            if self.pending_order.side == "buy":
                entry_price = float(order.get("filled_avg_price") or 0.0)
                quantity = int(float(order.get("filled_qty") or order.get("qty") or self.pending_order.quantity))
                exit_plan = build_exit_plan(
                    strategy_name=self.config.strategy,
                    research_profile=self.config.research_profile,
                    bars=self.bars,
                    signal_time=self.pending_order.signal_time,
                    side="long",
                    entry_price=entry_price,
                    stop_loss_pct=self.config.stop_loss_pct,
                    take_profit_pct=self.config.take_profit_pct,
                    exit_policy=self.config.exit_policy,
                )
                self.position = LivePosition(
                    quantity=quantity,
                    entry_price=entry_price,
                    stop_price=exit_plan.stop_price,
                    target_price=exit_plan.target_price,
                    entry_time=str(order.get("filled_at") or order.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    signal_time=self.pending_order.signal_time,
                    reason=self.pending_order.reason,
                    stop_reason=exit_plan.stop_reason,
                    target_reason=exit_plan.target_reason,
                    initial_risk=abs(entry_price - exit_plan.stop_price),
                    max_favorable_price=self._max_favorable_price_since(
                        self.pending_order.signal_time,
                        entry_price,
                    ),
                )
                self.last_exit = None
                self._record_event(
                    "position_opened",
                    f"Opened {quantity} @ {entry_price:.2f}",
                )
            else:
                exit_price = float(order.get("filled_avg_price") or 0.0)
                quantity = int(float(order.get("filled_qty") or order.get("qty") or self.pending_order.quantity))
                self.last_exit = LastExit(
                    quantity=quantity,
                    exit_price=exit_price,
                    exit_time=self.pending_order.signal_time,
                    reason=self.pending_order.reason,
                )
                self.position = None
                self._record_event(
                    "position_closed",
                    f"Closed position from broker refresh @ {exit_price:.2f}",
                )

        self.pending_order = None

    async def _on_trade_update(self, trade_info: dict) -> None:
        if not self.running:
            return
        if trade_info.get("symbol") != self.config.symbol:
            return
        if trade_info.get("strategy") != self.config.strategy:
            return

        async with self.lock:
            order_id = str(trade_info.get("alpaca_order_id") or "")
            if self.pending_order is None or order_id != self.pending_order.alpaca_order_id:
                return

            status = str(trade_info.get("status") or "")
            side = str(trade_info.get("side") or "")
            price = float(trade_info.get("price") or 0.0)
            qty = int(float(trade_info.get("qty") or 0))
            reason = str(trade_info.get("reason") or "")
            timestamp = str(trade_info.get("timestamp") or _now_utc().isoformat())
            self.last_trade_update_at = timestamp

            if status == "filled":
                if side == "buy":
                    exit_plan = build_exit_plan(
                        strategy_name=self.config.strategy,
                        research_profile=self.config.research_profile,
                        bars=self.bars,
                        signal_time=self.pending_order.signal_time,
                        side="long",
                        entry_price=price,
                        stop_loss_pct=self.config.stop_loss_pct,
                        take_profit_pct=self.config.take_profit_pct,
                        exit_policy=self.config.exit_policy,
                    )
                    self.position = LivePosition(
                        quantity=qty,
                        entry_price=price,
                        stop_price=exit_plan.stop_price,
                        target_price=exit_plan.target_price,
                        entry_time=timestamp,
                        signal_time=self.pending_order.signal_time,
                        reason=reason or self.pending_order.reason,
                        stop_reason=exit_plan.stop_reason,
                        target_reason=exit_plan.target_reason,
                        initial_risk=abs(price - exit_plan.stop_price),
                        max_favorable_price=self._max_favorable_price_since(
                            self.pending_order.signal_time,
                            price,
                        ),
                    )
                    self.last_exit = None
                    self._record_event(
                        "position_opened",
                        f"Opened {qty} @ {price:.2f}",
                    )
                elif side == "sell":
                    self.last_exit = LastExit(
                        quantity=qty,
                        exit_price=price,
                        exit_time=self.pending_order.signal_time,
                        reason=reason or self.pending_order.reason,
                    )
                    self.position = None
                    self._record_event(
                        "position_closed",
                        f"Closed position from trade update @ {price:.2f}",
                    )
                self.pending_order = None
                return

            if status in {"canceled", "cancelled", "rejected", "expired"}:
                self._record_event(
                    "order_update",
                    f"{side} order {status}",
                )
                self.pending_order = None
                if side == "sell" and self.position is not None:
                    self.last_error = f"Exit order {status}"

    def _record_event(self, event_type: str, message: str) -> None:
        self.recent_events.append(
            RunnerEvent(
                timestamp=_now_utc().isoformat(),
                type=event_type,
                message=message,
            )
        )

    def _max_favorable_price_since(self, signal_time: str | None, fallback: float) -> float:
        if signal_time is None:
            return fallback

        signal_index = next(
            (idx for idx, bar in enumerate(self.bars) if bar["time"] == signal_time),
            None,
        )
        if signal_index is None:
            return fallback

        return max(
            fallback,
            max(float(bar["high"]) for bar in self.bars[signal_index:]),
        )

    def _status_warnings(self) -> list[str]:
        warnings: list[str] = []
        now = _now_utc()

        live_reference = self.last_live_bar_at or self.started_at
        if self.running and live_reference and is_rth_bar_timestamp(now.isoformat()):
            live_age_seconds = _runner_live_bar_age_seconds(self, now)
            if live_age_seconds >= 360:
                warnings.append(
                    f"No live 1m bars observed for {live_age_seconds}s during RTH"
                )

        if self.pending_order is not None:
            submitted_at = datetime.fromisoformat(self.pending_order.submitted_at)
            pending_age_seconds = max(0, int((now - submitted_at).total_seconds()))
            if pending_age_seconds >= 90:
                warnings.append(
                    f"Pending {self.pending_order.side} order open for {pending_age_seconds}s"
                )

        return warnings


_phase1_runners: dict[str, Phase1PaperRunner] = {}
_phase1_monitor_task: asyncio.Task | None = None


def reset_phase1_paper_runner() -> None:
    _phase1_runners.clear()


def _empty_runner_status(strategy: str = DEFAULT_PHASE1_STRATEGY) -> dict:
    return {
        "running": False,
        "strategy": strategy,
        "symbol": "QQQ",
        "timeframe": "5m",
        "research_profile": "qqq_5m_phase1",
        "fixed_quantity": 100,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.0,
        "exit_policy": None,
        "history_days": 10,
        "params": None,
        "bar_count": 0,
        "started_at": None,
        "last_completed_bar_time": None,
        "last_live_bar_at": None,
        "last_trade_update_at": None,
        "orders_submitted": 0,
        "position": None,
        "dynamic_exit": None,
        "last_exit": None,
        "pending_order": None,
        "last_error": None,
        "warnings": [],
        "recent_events": [],
    }


async def start_phase1_paper_runner(
    strategy: str = DEFAULT_PHASE1_STRATEGY,
    fixed_quantity: int = 100,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    exit_policy: str | None = None,
    history_days: int = 10,
    params: dict[str, Any] | None = None,
) -> dict:
    return await _start_phase1_paper_runner(
        strategy=strategy,
        fixed_quantity=fixed_quantity,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        exit_policy=exit_policy,
        history_days=history_days,
        params=params,
        persist_desired=True,
    )


async def _start_phase1_paper_runner(
    strategy: str = DEFAULT_PHASE1_STRATEGY,
    fixed_quantity: int = 100,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    exit_policy: str | None = None,
    history_days: int = 10,
    params: dict[str, Any] | None = None,
    persist_desired: bool = False,
) -> dict:
    if not PAPER_TRADING:
        raise RuntimeError(f"{BROOKS_COMBO_LABEL} requires PAPER_TRADING=true")
    if strategy not in SUPPORTED_PHASE1_STRATEGIES:
        raise ValueError(f"Unsupported {BROOKS_COMBO_LABEL} strategy: {strategy}")
    existing_runner = _phase1_runners.get(strategy)
    if existing_runner is not None and existing_runner.running:
        raise RuntimeError(f"{BROOKS_COMBO_LABEL} is already running for {strategy}")

    runner = Phase1PaperRunner(
        Phase1PaperConfig(
            strategy=strategy,
            fixed_quantity=fixed_quantity,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            exit_policy=exit_policy,
            history_days=history_days,
            params=params,
        )
    )
    _phase1_runners[strategy] = runner
    try:
        status = await runner.start()
    except Exception:
        _phase1_runners.pop(strategy, None)
        raise
    if persist_desired:
        await _set_desired_phase1_runner(
            Phase1PaperConfig(
                strategy=strategy,
                fixed_quantity=fixed_quantity,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                exit_policy=exit_policy,
                history_days=history_days,
                params=params,
            ),
            is_active=True,
        )
    return status


async def stop_phase1_paper_runner(
    strategy: str | None = None,
    close_position: bool = True,
) -> dict:
    if strategy is not None:
        if strategy not in SUPPORTED_PHASE1_STRATEGIES:
            raise ValueError(f"Unsupported {BROOKS_COMBO_LABEL} strategy: {strategy}")
        runner = _phase1_runners.get(strategy)
        if runner is None:
            return _empty_runner_status(strategy)
        status = await runner.stop(close_position=close_position)
        if not runner.running:
            _phase1_runners.pop(strategy, None)
            await _mark_desired_phase1_runner_inactive(strategy)
        return status

    active_runners = [runner for runner in _phase1_runners.values() if runner.running]
    if not active_runners:
        return _empty_runner_status()
    if len(active_runners) > 1:
        raise RuntimeError(f"Multiple {BROOKS_COMBO_LABEL} runners are active; specify a strategy to stop")

    runner = active_runners[0]
    status = await runner.stop(close_position=close_position)
    if not runner.running:
        _phase1_runners.pop(runner.config.strategy, None)
        await _mark_desired_phase1_runner_inactive(runner.config.strategy)
    return status


async def restore_desired_phase1_paper_runners() -> list[dict]:
    if not _phase1_market_is_open():
        await _stop_phase1_runners_for_closed_market()
        return []

    configs = await _get_desired_phase1_runner_configs()
    restored: list[dict] = []
    for config in configs:
        existing_runner = _phase1_runners.get(config.strategy)
        if existing_runner is not None and existing_runner.running:
            pending_refreshed = await _refresh_pending_order_for_runner(existing_runner)
            if pending_refreshed:
                restored.append(existing_runner.status())
                continue
            if await _restart_stale_phase1_runner(existing_runner):
                existing_runner = None
            else:
                restored.append(existing_runner.status())
                continue

        if existing_runner is not None and existing_runner.running:
            restored.append(existing_runner.status())
            continue
        try:
            restored.append(
                await _start_phase1_paper_runner(
                    strategy=config.strategy,
                    fixed_quantity=config.fixed_quantity,
                    stop_loss_pct=config.stop_loss_pct,
                    take_profit_pct=config.take_profit_pct,
                    exit_policy=config.exit_policy,
                    history_days=config.history_days,
                    params=config.params,
                    persist_desired=False,
                )
            )
        except Exception:
            logger.exception("Failed to restore %s for %s", BROOKS_COMBO_LABEL, config.strategy)
    return restored


async def _restart_stale_phase1_runner(runner: Phase1PaperRunner) -> bool:
    if not _phase1_runner_is_stale(runner):
        return False

    logger.warning(
        "Restarting stale %s runner for %s after prolonged live-bar gap",
        BROOKS_COMBO_LABEL,
        runner.config.strategy,
    )
    await runner.stop(close_position=False)
    if not runner.running:
        _phase1_runners.pop(runner.config.strategy, None)
    return True


async def _refresh_pending_order_for_runner(runner: Phase1PaperRunner) -> bool:
    if getattr(runner, "pending_order", None) is None:
        return False

    async def _refresh() -> bool:
        if getattr(runner, "pending_order", None) is None:
            return False
        try:
            await runner._refresh_pending_order()
        except Exception:
            logger.exception(
                "Failed to refresh pending %s order for %s",
                BROOKS_COMBO_LABEL,
                runner.config.strategy,
            )
            return False
        return True

    lock = getattr(runner, "lock", None)
    if lock is None:
        return await _refresh()
    async with lock:
        return await _refresh()


def _phase1_market_is_open() -> bool:
    return _market_session_snapshot()["market_session"] == "open"


async def _stop_phase1_runners_for_closed_market() -> None:
    active_runners = [
        runner for runner in list(_phase1_runners.values()) if runner.running
    ]
    for runner in active_runners:
        try:
            await runner.stop(close_position=True)
        except Exception:
            logger.exception(
                "Failed to stop %s after market close: %s",
                BROOKS_COMBO_LABEL,
                runner.config.strategy,
            )
            continue
        if not runner.running:
            _phase1_runners.pop(runner.config.strategy, None)


async def start_phase1_paper_runner_monitor(interval_seconds: int = 30) -> None:
    global _phase1_monitor_task
    if _phase1_monitor_task is not None and not _phase1_monitor_task.done():
        return

    async def _monitor() -> None:
        while True:
            try:
                await market_data.start_stream()
                await trade_updates.start_trade_updates_stream()
                await restore_desired_phase1_paper_runners()
                await _poll_stale_phase1_runner_bars()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s monitor failed", BROOKS_COMBO_LABEL)
            await asyncio.sleep(interval_seconds)

    _phase1_monitor_task = asyncio.create_task(_monitor())


async def stop_phase1_paper_runner_monitor() -> None:
    global _phase1_monitor_task
    if _phase1_monitor_task is None:
        return
    _phase1_monitor_task.cancel()
    try:
        await _phase1_monitor_task
    except asyncio.CancelledError:
        pass
    _phase1_monitor_task = None


async def _poll_stale_phase1_runner_bars() -> None:
    active_runners = [runner for runner in _phase1_runners.values() if runner.running]
    if not active_runners:
        return

    for runner in active_runners:
        await _refresh_pending_order_for_runner(runner)

    now = _now_utc()
    if not is_rth_bar_timestamp(now.isoformat()):
        return

    stale_runners = [
        runner for runner in active_runners if _runner_live_bar_age_seconds(runner, now) >= 90
    ]
    if not stale_runners:
        return

    symbols = sorted({runner.config.symbol for runner in stale_runners})
    start = (now - timedelta(minutes=45)).isoformat()
    for symbol in symbols:
        try:
            bars = await get_analysis_bars(
                symbol=symbol,
                timeframe="1m",
                start=start,
                limit=60,
            )
        except Exception:
            logger.exception("Failed to poll recent bars for %s", symbol)
            continue

        for runner in stale_runners:
            if runner.config.symbol != symbol:
                continue
            last_live_dt = _parse_utc_datetime(runner.last_live_bar_at or runner.started_at)
            for bar in bars:
                bar_dt = _parse_utc_datetime(bar["time"])
                if last_live_dt is not None and bar_dt <= last_live_dt:
                    continue
                await runner._on_live_bar(symbol, bar)


def _runner_live_bar_age_seconds(runner: Phase1PaperRunner, now: datetime) -> int:
    live_reference = runner.last_live_bar_at or runner.started_at
    live_dt = _parse_utc_datetime(live_reference)
    if live_dt is None:
        return 999999
    return max(0, int((now - live_dt).total_seconds()))


def _phase1_runner_is_stale(runner: Phase1PaperRunner, now: datetime | None = None) -> bool:
    if not runner.running:
        return False
    current = now or _now_utc()
    if not is_rth_bar_timestamp(current.isoformat()):
        return False
    return _runner_live_bar_age_seconds(runner, current) >= 360


def get_phase1_paper_runner_status(
    strategy: str | None = None,
) -> dict:
    if strategy is not None:
        runner = _phase1_runners.get(strategy)
        if runner is None:
            return _empty_runner_status(strategy)
        return runner.status()

    default_runner = _phase1_runners.get(DEFAULT_PHASE1_STRATEGY)
    if default_runner is not None:
        return default_runner.status()

    active_runners = [runner for runner in _phase1_runners.values() if runner.running]
    if len(active_runners) == 1:
        return active_runners[0].status()

    return _empty_runner_status(DEFAULT_PHASE1_STRATEGY)


def get_phase1_paper_runner_statuses() -> list[dict]:
    return [
        get_phase1_paper_runner_status(strategy)
        for strategy in sorted(SUPPORTED_PHASE1_STRATEGIES)
    ]


def get_phase1_paper_runner_readiness() -> dict:
    alpaca_configured = alpaca_client.is_configured()
    account_status = "unavailable"
    account_error: str | None = None
    session = _market_session_snapshot()

    if alpaca_configured:
        try:
            alpaca_client.get_account()
            account_status = "ok"
        except Exception as exc:
            account_status = "error"
            account_error = str(exc)

    market_stream_running = market_data.is_stream_running()
    trade_updates_running = trade_updates.is_trade_updates_running()
    active_runners = [runner for runner in _phase1_runners.values() if runner.running]
    stale_active_strategies = [
        runner.config.strategy
        for runner in active_runners
        if _phase1_runner_is_stale(runner)
    ]

    warnings: list[str] = []
    if not PAPER_TRADING:
        warnings.append("PAPER_TRADING is disabled")
    if not alpaca_configured:
        warnings.append("Alpaca credentials are not configured")
    if alpaca_configured and account_status != "ok":
        warnings.append("Alpaca account access failed")
    if alpaca_configured and not market_stream_running:
        warnings.append("Market data stream is not running")
    if alpaca_configured and not trade_updates_running:
        warnings.append("Trade updates stream is not running")
    for strategy in stale_active_strategies:
        warnings.append(f"Active runner {strategy} has stale live bars")

    return {
        "ready": PAPER_TRADING
        and alpaca_configured
        and account_status == "ok"
        and market_stream_running
        and trade_updates_running
        and not stale_active_strategies,
        "paper_trading": PAPER_TRADING,
        "alpaca_configured": alpaca_configured,
        "account_status": account_status,
        "account_error": account_error,
        "market_stream_running": market_stream_running,
        "trade_updates_running": trade_updates_running,
        "runner_running": bool(active_runners),
        "active_strategies": sorted(
            runner.config.strategy
            for runner in active_runners
        ),
        "market_session": session["market_session"],
        "current_session_open": session["current_session_open"],
        "current_session_close": session["current_session_close"],
        "next_session_open": session["next_session_open"],
        "warnings": warnings,
    }


async def get_phase1_paper_runner_history(
    limit: int = 10,
    strategy: str | None = None,
) -> list[dict]:
    target_strategy = strategy
    if target_strategy is None:
        active_runners = [runner for runner in _phase1_runners.values() if runner.running]
        if len(active_runners) == 1:
            target_strategy = active_runners[0].config.strategy
    target_strategy = target_strategy or DEFAULT_PHASE1_STRATEGY
    if target_strategy not in SUPPORTED_PHASE1_STRATEGIES:
        raise ValueError(f"Unsupported {BROOKS_COMBO_LABEL} strategy: {target_strategy}")

    history = await get_trade_history(limit=max(limit * 5, limit))
    filtered = [
        trade
        for trade in history
        if trade.get("symbol") == "QQQ"
        and trade.get("strategy") == target_strategy
    ]
    return filtered[:limit]


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


async def _set_desired_phase1_runner(
    config: Phase1PaperConfig,
    is_active: bool,
) -> None:
    async with async_session() as session:
        existing = await session.get(PaperRunnerConfig, config.strategy)
        params_json = json.dumps(config.params) if config.params is not None else None
        if existing is None:
            existing = PaperRunnerConfig(
                strategy=config.strategy,
                symbol=config.symbol,
                timeframe=config.timeframe,
                research_profile=config.research_profile,
                fixed_quantity=config.fixed_quantity,
                stop_loss_pct=config.stop_loss_pct,
                take_profit_pct=config.take_profit_pct,
                exit_policy=config.exit_policy,
                history_days=config.history_days,
                params=params_json,
                is_active=is_active,
                updated_at=_now_db(),
            )
            session.add(existing)
        else:
            existing.symbol = config.symbol
            existing.timeframe = config.timeframe
            existing.research_profile = config.research_profile
            existing.fixed_quantity = config.fixed_quantity
            existing.stop_loss_pct = config.stop_loss_pct
            existing.take_profit_pct = config.take_profit_pct
            existing.exit_policy = config.exit_policy
            existing.history_days = config.history_days
            existing.params = params_json
            existing.is_active = is_active
            existing.updated_at = _now_db()
        await session.commit()


async def _mark_desired_phase1_runner_inactive(strategy: str) -> None:
    async with async_session() as session:
        existing = await session.get(PaperRunnerConfig, strategy)
        if existing is not None:
            existing.is_active = False
            existing.updated_at = _now_db()
            await session.commit()


async def _get_desired_phase1_runner_configs() -> list[Phase1PaperConfig]:
    async with async_session() as session:
        result = await session.execute(
            select(PaperRunnerConfig).where(PaperRunnerConfig.is_active.is_(True))
        )
        records = result.scalars().all()

    configs: list[Phase1PaperConfig] = []
    for record in records:
        if record.strategy not in SUPPORTED_PHASE1_STRATEGIES:
            continue
        params = json.loads(record.params) if record.params else None
        configs.append(
            Phase1PaperConfig(
                strategy=record.strategy,
                symbol=record.symbol,
                timeframe=record.timeframe,
                research_profile=record.research_profile,
                fixed_quantity=record.fixed_quantity,
                stop_loss_pct=record.stop_loss_pct,
                take_profit_pct=record.take_profit_pct,
                exit_policy=record.exit_policy,
                history_days=record.history_days,
                params=params,
            )
        )
    return configs


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_db() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _market_session_snapshot() -> dict[str, str | None]:
    now_utc = _now_utc()
    now_local = now_utc.astimezone(MARKET_TZ)
    today = now_local.date()

    if _is_trading_day(today):
        session_open = datetime.combine(today, SESSION_OPEN, tzinfo=MARKET_TZ)
        session_close = _session_close_for(today)
        if session_open <= now_local < session_close:
            return {
                "market_session": "open",
                "current_session_open": session_open.astimezone(timezone.utc).isoformat(),
                "current_session_close": session_close.astimezone(timezone.utc).isoformat(),
                "next_session_open": datetime.combine(
                    _next_trading_day(today),
                    SESSION_OPEN,
                    tzinfo=MARKET_TZ,
                ).astimezone(timezone.utc).isoformat(),
            }
        if now_local < session_open:
            return {
                "market_session": "closed",
                "current_session_open": None,
                "current_session_close": None,
                "next_session_open": session_open.astimezone(timezone.utc).isoformat(),
            }

    next_open_day = _next_trading_day(today) if _is_trading_day(today) else today
    if not _is_trading_day(next_open_day):
        next_open_day = _next_trading_day(next_open_day)
    next_open = datetime.combine(next_open_day, SESSION_OPEN, tzinfo=MARKET_TZ)
    return {
        "market_session": "closed",
        "current_session_open": None,
        "current_session_close": None,
        "next_session_open": next_open.astimezone(timezone.utc).isoformat(),
    }


def _five_min_slot_timestamp(timestamp: str) -> str:
    local = market_time(timestamp)
    floored_minute = (local.minute // 5) * 5
    slot_local = local.replace(minute=floored_minute, second=0, microsecond=0)
    return slot_local.astimezone(timezone.utc).isoformat()


def _previous_five_min_slot_timestamp(timestamp: str) -> str:
    local = market_time(timestamp)
    floored_minute = (local.minute // 5) * 5
    slot_local = local.replace(minute=floored_minute, second=0, microsecond=0)
    return (slot_local - timedelta(minutes=5)).astimezone(timezone.utc).isoformat()


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
