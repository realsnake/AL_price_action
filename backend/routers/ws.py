import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services import market_data
from services.trade_executor import add_trade_listener, remove_trade_listener

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients per symbol
_market_subscribers: dict[str, set[WebSocket]] = {}

# Connected WebSocket clients for trade notifications
_trade_subscribers: set[WebSocket] = set()


async def _broadcast_bar(symbol: str, bar: dict):
    """Push a new bar to all WebSocket subscribers of a symbol."""
    clients = _market_subscribers.get(symbol, set()).copy()
    if not clients:
        return
    payload = json.dumps({"type": "bar", "symbol": symbol, "data": bar})
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            _market_subscribers.get(symbol, set()).discard(ws)


async def _broadcast_trade(trade_info: dict):
    """Push trade notification to all trade WebSocket subscribers."""
    clients = _trade_subscribers.copy()
    if not clients:
        return
    payload = json.dumps(trade_info)
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            _trade_subscribers.discard(ws)


@router.websocket("/ws/market/{symbol}")
async def market_ws(websocket: WebSocket, symbol: str):
    await websocket.accept()
    symbol = symbol.upper()
    _market_subscribers.setdefault(symbol, set()).add(websocket)

    # Subscribe to Alpaca real-time data and forward to this symbol's clients
    await market_data.subscribe(symbol, _broadcast_bar)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _market_subscribers.get(symbol, set()).discard(websocket)
        # If no more clients for this symbol, unsubscribe
        if not _market_subscribers.get(symbol):
            await market_data.unsubscribe(symbol, _broadcast_bar)
            _market_subscribers.pop(symbol, None)


@router.websocket("/ws/trades")
async def trades_ws(websocket: WebSocket):
    await websocket.accept()
    _trade_subscribers.add(websocket)
    add_trade_listener(_broadcast_trade)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _trade_subscribers.discard(websocket)
        if not _trade_subscribers:
            remove_trade_listener(_broadcast_trade)
