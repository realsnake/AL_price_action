from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Trade
from services.alpaca_client import alpaca_client

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
        trade_id = trade.id

    trade_info = {
        "type": "trade",
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "strategy": strategy,
        "reason": reason,
        "status": result.get("status", "submitted"),
        "alpaca_order_id": result.get("id"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _notify_trade(trade_info)
    return trade_info


async def get_trade_history(limit: int = 50) -> list[dict]:
    """Get recent trade history from the database."""
    async with async_session() as session:
        stmt = select(Trade).order_by(Trade.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        trades = result.scalars().all()
        return [
            {
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
            for t in trades
        ]
