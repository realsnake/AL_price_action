from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from alpaca.data.live import StockDataStream

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

logger = logging.getLogger(__name__)

# Active subscriptions: symbol -> set of callback coroutines
_callbacks: dict[str, list] = {}
_stream: StockDataStream | None = None
_stream_task: asyncio.Task | None = None


async def _on_bar(bar):
    """Handle incoming bar from Alpaca WebSocket."""
    symbol = bar.symbol
    bar_dict = {
        "time": bar.timestamp.isoformat(),
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": int(bar.volume),
    }
    for cb in _callbacks.get(symbol, []):
        try:
            await cb(symbol, bar_dict)
        except Exception:
            logger.exception("Error in bar callback for %s", symbol)


async def _on_quote(quote):
    """Handle incoming quote from Alpaca WebSocket."""
    symbol = quote.symbol
    quote_dict = {
        "symbol": symbol,
        "bid": float(quote.bid_price),
        "ask": float(quote.ask_price),
        "bid_size": int(quote.bid_size),
        "ask_size": int(quote.ask_size),
        "timestamp": quote.timestamp.isoformat(),
    }
    for cb in _callbacks.get(symbol, []):
        try:
            await cb(symbol, quote_dict)
        except Exception:
            logger.exception("Error in quote callback for %s", symbol)


def _get_stream() -> StockDataStream:
    global _stream
    if _stream is None:
        _stream = StockDataStream(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    return _stream


async def start_stream():
    """Start the Alpaca data stream in the background."""
    global _stream_task
    if _stream_task is not None:
        return

    stream = _get_stream()

    async def _run():
        try:
            await stream._run_forever()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Alpaca stream error")

    _stream_task = asyncio.create_task(_run())
    logger.info("Alpaca data stream started")


async def stop_stream():
    """Stop the Alpaca data stream."""
    global _stream, _stream_task
    if _stream_task is not None:
        _stream_task.cancel()
        try:
            await _stream_task
        except asyncio.CancelledError:
            pass
        _stream_task = None
    if _stream is not None:
        try:
            await _stream.close()
        except Exception:
            pass
        _stream = None
    logger.info("Alpaca data stream stopped")


async def subscribe(symbol: str, callback):
    """Subscribe to real-time bars for a symbol."""
    symbol = symbol.upper()
    if symbol not in _callbacks:
        _callbacks[symbol] = []
        stream = _get_stream()
        stream.subscribe_bars(_on_bar, symbol)
        logger.info("Subscribed to bars for %s", symbol)
    _callbacks[symbol].append(callback)


async def unsubscribe(symbol: str, callback):
    """Unsubscribe a callback from a symbol."""
    symbol = symbol.upper()
    if symbol in _callbacks:
        try:
            _callbacks[symbol].remove(callback)
        except ValueError:
            pass
        if not _callbacks[symbol]:
            del _callbacks[symbol]
            stream = _get_stream()
            stream.unsubscribe_bars(symbol)
            logger.info("Unsubscribed from bars for %s", symbol)
