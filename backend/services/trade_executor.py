from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Trade
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client

logger = logging.getLogger(__name__)

# Callbacks for trade notifications
_trade_listeners: list = []


def add_trade_listener(callback):
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
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


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
    if not alpaca_client.is_configured():
        return

    changed = False
    for trade in trades:
        if not trade.alpaca_order_id:
            continue
        try:
            order = alpaca_client.get_order_by_id(trade.alpaca_order_id)
        except AlpacaNotConfiguredError:
            return
        except Exception:
            logger.exception("Failed to refresh trade %s from Alpaca", trade.id)
            continue

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


async def execute_order(symbol: str, qty: int, side: str, strategy: str | None = None, reason: str | None = None) -> dict:
    """Execute an order via Alpaca and record it in the database."""
    result = alpaca_client.submit_order(symbol, qty, side)

    async with async_session() as session:
        trade = Trade(
            symbol=symbol,
            side=side,
            quantity=qty,
            price=0.0,  # Market order - price filled later
            strategy=strategy,
            signal_reason=reason,
            status=result.get("status", "submitted"),
            alpaca_order_id=result.get("id"),
        )
        session.add(trade)
        await session.commit()

        try:
            await _refresh_trades_from_broker(session, [trade])
        except AlpacaNotConfiguredError:
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
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _notify_trade(trade_info)
    return trade_info


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
                    "timestamp": timestamp.isoformat(),
                }
            )
