from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import IBKR_ALLOW_STRATEGY_TRADING, IBKR_DAILY_MAX_NOTIONAL_USD
from database import async_session
from models import Trade
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client
from services.broker_client import broker_client
from services.ibkr_client import IBKRNotConfiguredError, IBKRSafetyError

logger = logging.getLogger(__name__)

# Callbacks for trade notifications
_trade_listeners: list = []

_ALPACA_REFRESH_BACKOFF_SECONDS = 30.0
_alpaca_refresh_backoff_until: dict[str, float] = {}


def _now_monotonic() -> float:
    return time.monotonic()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_transient_alpaca_refresh_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return True

    text = str(exc).lower()
    exc_name = exc.__class__.__name__.lower()
    return (
        "429" in text
        or "rate limit" in text
        or "too many requests" in text
        or "readtimeout" in exc_name
        or "read timed out" in text
        or "timed out" in text
    )


def add_trade_listener(callback):
    if callback not in _trade_listeners:
        _trade_listeners.append(callback)


def remove_trade_listener(callback):
    try:
        _trade_listeners.remove(callback)
    except ValueError:
        pass


async def _notify_trade(trade_info: dict):
    for cb in _trade_listeners:
        try:
            await cb(trade_info)
        except Exception:
            logger.exception("Error in trade listener")


def _serialize_trade(t: Trade) -> dict:
    broker_order_id = t.alpaca_order_id
    broker = _broker_name_for_order_id(broker_order_id)
    return {
        "id": t.id,
        "symbol": t.symbol,
        "side": t.side,
        "quantity": t.quantity,
        "price": t.price,
        "strategy": t.strategy,
        "signal_reason": t.signal_reason,
        "status": t.status,
        "alpaca_order_id": t.alpaca_order_id,
        "broker_order_id": broker_order_id,
        "broker": broker,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _broker_name_for_order_id(order_id: str | None) -> str:
    if order_id and str(order_id).startswith("ibkr:"):
        return "ibkr"
    return "alpaca"


def _apply_order_snapshot(trade: Trade, order: dict) -> bool:
    changed = False

    status = order.get("status")
    if status and trade.status != status:
        trade.status = status
        changed = True

    filled_avg_price = order.get("filled_avg_price")
    if filled_avg_price not in (None, ""):
        price = float(filled_avg_price)
        if trade.price != price:
            trade.price = price
            changed = True

    filled_qty = order.get("filled_qty")
    if filled_qty not in (None, ""):
        quantity = int(float(filled_qty))
        if trade.quantity != quantity:
            trade.quantity = quantity
            changed = True

    return changed


async def _refresh_trades_from_broker(session: AsyncSession, trades: list[Trade]) -> None:
    if not broker_client.is_configured():
        return

    changed = False
    for trade in trades:
        order_id = trade.alpaca_order_id
        if not order_id:
            continue
        if not broker_client.owns_order_id(order_id):
            continue

        now = _now_monotonic()
        backoff_until = _alpaca_refresh_backoff_until.get(order_id, 0.0)
        if now < backoff_until:
            logger.debug(
                "Skipping Alpaca refresh for trade %s during broker backoff",
                trade.id,
            )
            continue

        try:
            order = await asyncio.to_thread(
                broker_client.get_order_by_id,
                order_id,
            )
        except (AlpacaNotConfiguredError, IBKRNotConfiguredError):
            return
        except Exception as exc:
            if _is_transient_alpaca_refresh_error(exc):
                _alpaca_refresh_backoff_until[order_id] = now + _ALPACA_REFRESH_BACKOFF_SECONDS
                logger.warning(
                    "Alpaca refresh temporarily throttled/timed out for trade %s; "
                    "skipping broker refresh for %.0fs: %s",
                    trade.id,
                    _ALPACA_REFRESH_BACKOFF_SECONDS,
                    exc,
                )
                continue

            logger.exception("Failed to refresh trade %s from Alpaca", trade.id)
            continue

        _alpaca_refresh_backoff_until.pop(order_id, None)
        if _apply_order_snapshot(trade, order):
            changed = True

    if changed:
        await session.commit()


async def refresh_trade_statuses(
    limit: int = 50, order_ids: list[str] | None = None
) -> list[dict]:
    async with async_session() as session:
        stmt = select(Trade)
        if order_ids:
            stmt = stmt.where(Trade.alpaca_order_id.in_(order_ids))
        else:
            stmt = stmt.order_by(Trade.created_at.desc()).limit(limit)

        result = await session.execute(stmt)
        trades = result.scalars().all()

        try:
            await _refresh_trades_from_broker(session, trades)
        except AlpacaNotConfiguredError:
            pass

        return [_serialize_trade(t) for t in trades]


async def execute_order(
    symbol: str,
    qty: int,
    side: str,
    strategy: str | None = None,
    reason: str | None = None,
    *,
    order_type: str = "market",
    limit_price: float | None = None,
    confirm_live: bool = False,
) -> dict:
    """Execute an order via the active broker and record it in the database."""
    normalized_symbol = symbol.upper()
    normalized_side = side.lower()
    async with async_session() as session:
        await _validate_order_before_submit(
            session,
            normalized_symbol,
            qty,
            normalized_side,
            strategy=strategy,
            order_type=order_type,
            limit_price=limit_price,
        )
        result = await asyncio.to_thread(
            broker_client.submit_order,
            normalized_symbol,
            qty,
            normalized_side,
            order_type=order_type,
            limit_price=limit_price,
            confirm_live=confirm_live,
        )
        broker_order_id = result.get("id")
        submitted_price = _submitted_price_for_trade(result, limit_price)
        trade = Trade(
            symbol=normalized_symbol,
            side=normalized_side,
            quantity=qty,
            price=submitted_price,
            strategy=strategy,
            signal_reason=reason,
            status=result.get("status", "submitted"),
            alpaca_order_id=broker_order_id,
        )
        session.add(trade)
        await session.commit()

        try:
            await _refresh_trades_from_broker(session, [trade])
        except (AlpacaNotConfiguredError, IBKRNotConfiguredError):
            pass

        trade_id = trade.id

    trade_info = {
        "type": "trade",
        "trade_id": trade_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "qty": trade.quantity,
        "price": trade.price,
        "strategy": strategy,
        "reason": reason,
        "status": trade.status,
        "alpaca_order_id": trade.alpaca_order_id,
        "broker_order_id": trade.alpaca_order_id,
        "broker": _broker_name_for_order_id(trade.alpaca_order_id),
        "timestamp": _now_utc().isoformat(),
    }
    await _notify_trade(trade_info)
    return trade_info


async def _validate_order_before_submit(
    session: AsyncSession,
    symbol: str,
    qty: int,
    side: str,
    *,
    strategy: str | None,
    order_type: str,
    limit_price: float | None,
) -> None:
    if broker_client.name != "ibkr":
        return
    if strategy is not None and not IBKR_ALLOW_STRATEGY_TRADING:
        raise IBKRSafetyError(
            "IBKR strategy trading is disabled; use manual orders for live experiments"
        )
    if order_type.lower() != "limit" or limit_price is None:
        return

    current_notional = await _ibkr_daily_notional(session)
    next_notional = qty * float(limit_price)
    if current_notional + next_notional > IBKR_DAILY_MAX_NOTIONAL_USD:
        raise IBKRSafetyError(
            "daily IBKR notional "
            f"${current_notional + next_notional:.2f} exceeds "
            f"IBKR_DAILY_MAX_NOTIONAL_USD ${IBKR_DAILY_MAX_NOTIONAL_USD:.2f}"
        )


async def _ibkr_daily_notional(session: AsyncSession) -> float:
    result = await session.execute(select(Trade))
    trades = result.scalars().all()
    today = _now_utc().date()
    total = 0.0
    for trade in trades:
        order_id = getattr(trade, "alpaca_order_id", None)
        created_at = getattr(trade, "created_at", None)
        if not order_id or not str(order_id).startswith("ibkr:") or created_at is None:
            continue
        if created_at.date() != today:
            continue
        total += abs(float(getattr(trade, "price", 0.0) or 0.0)) * int(
            getattr(trade, "quantity", 0) or 0
        )
    return total


def _submitted_price_for_trade(result: dict, limit_price: float | None) -> float:
    filled_avg_price = result.get("filled_avg_price")
    if filled_avg_price not in (None, ""):
        return float(filled_avg_price)
    if _broker_name_for_order_id(result.get("id")) == "ibkr" and limit_price is not None:
        return float(limit_price)
    return 0.0


async def get_trade_history(limit: int = 50) -> list[dict]:
    """Get recent trade history from the database."""
    return await refresh_trade_statuses(limit=limit)


async def apply_trade_update(update) -> None:
    order = getattr(update, "order", None)
    if order is None:
        return

    order_id = str(getattr(order, "id", "") or "")
    if not order_id:
        return

    status_value = getattr(getattr(order, "status", None), "value", None) or getattr(
        order, "status", None
    )
    side_value = getattr(getattr(order, "side", None), "value", None) or getattr(
        order, "side", None
    )
    order_snapshot = {
        "id": order_id,
        "symbol": getattr(order, "symbol", None),
        "side": side_value,
        "qty": getattr(order, "qty", None),
        "filled_qty": getattr(order, "filled_qty", None) or getattr(update, "qty", None),
        "filled_avg_price": getattr(order, "filled_avg_price", None) or getattr(
            update, "price", None
        ),
        "status": status_value,
    }

    async with async_session() as session:
        result = await session.execute(
            select(Trade).where(Trade.alpaca_order_id == order_id)
        )
        trades = result.scalars().all()
        if not trades:
            return

        changed = False
        for trade in trades:
            if _apply_order_snapshot(trade, order_snapshot):
                changed = True

        if changed:
            await session.commit()

        timestamp = getattr(update, "timestamp", None)
        if timestamp is None:
            timestamp = datetime.utcnow()

        for trade in trades:
            await _notify_trade(
                {
                    "type": "trade_update",
                    "trade_id": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "qty": trade.quantity,
                    "price": trade.price,
                    "strategy": trade.strategy,
                    "reason": trade.signal_reason,
                    "status": trade.status,
                    "alpaca_order_id": trade.alpaca_order_id,
                    "broker_order_id": trade.alpaca_order_id,
                    "broker": _broker_name_for_order_id(trade.alpaca_order_id),
                    "timestamp": timestamp.isoformat(),
                }
            )
