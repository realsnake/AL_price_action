from __future__ import annotations

import asyncio
import logging

from alpaca.data.live import StockDataStream

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client

logger = logging.getLogger(__name__)

# Active subscriptions: symbol -> set of callback coroutines
_callbacks: dict[str, list] = {}
_stream: StockDataStream | None = None
_stream_task: asyncio.Task | None = None


def is_live_stream_enabled() -> bool:
    return alpaca_client.is_configured()


def is_stream_running() -> bool:
    return _stream_task is not None and not _stream_task.done()


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
    if not is_live_stream_enabled():
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")
    if _stream is None:
        _stream = StockDataStream(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    return _stream


def _is_running_on_stream_loop(stream: StockDataStream) -> bool:
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return bool(getattr(stream, "_running", False)) and getattr(
        stream, "_loop", None
    ) is current_loop


def _subscribe_bars(stream: StockDataStream, symbol: str) -> None:
    if _is_running_on_stream_loop(stream):
        stream._ensure_coroutine(_on_bar)
        stream._handlers["bars"][symbol] = _on_bar
        asyncio.create_task(stream._send_subscribe_msg())
        return
    stream.subscribe_bars(_on_bar, symbol)


def _unsubscribe_bars(stream: StockDataStream, symbol: str) -> None:
    if _is_running_on_stream_loop(stream):
        stream._handlers["bars"].pop(symbol, None)
        asyncio.create_task(stream._send_unsubscribe_msg("bars", [symbol]))
        return
    stream.unsubscribe_bars(symbol)


async def start_stream():
    """Start the Alpaca data stream in the background."""
    global _stream_task
    if _stream_task is not None:
        return
    if not is_live_stream_enabled():
        logger.warning("Alpaca stream disabled: credentials are not configured")
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
    if not is_live_stream_enabled():
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")
    if symbol not in _callbacks:
        _callbacks[symbol] = []
        stream = _get_stream()
        _subscribe_bars(stream, symbol)
        logger.info("Subscribed to bars for %s", symbol)
    _callbacks[symbol].append(callback)


async def unsubscribe(symbol: str, callback):
    """Unsubscribe a callback from a symbol."""
    symbol = symbol.upper()
    if not is_live_stream_enabled():
        return
    if symbol in _callbacks:
        try:
            _callbacks[symbol].remove(callback)
        except ValueError:
            pass
        if not _callbacks[symbol]:
            del _callbacks[symbol]
            stream = _get_stream()
            _unsubscribe_bars(stream, symbol)
            logger.info("Unsubscribed from bars for %s", symbol)
