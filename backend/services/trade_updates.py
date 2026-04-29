from __future__ import annotations

import asyncio
import logging

from alpaca.trading.stream import TradingStream

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, PAPER_TRADING
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client
from services.trade_executor import apply_trade_update

logger = logging.getLogger(__name__)

_trade_stream: TradingStream | None = None
_trade_stream_task: asyncio.Task | None = None
_trade_updates_heartbeat_task: asyncio.Task | None = None


def is_trade_updates_enabled() -> bool:
    return alpaca_client.is_configured()


def is_trade_updates_running() -> bool:
    stream_running = _trade_stream_task is not None and not _trade_stream_task.done()
    heartbeat_running = (
        _trade_updates_heartbeat_task is not None
        and not _trade_updates_heartbeat_task.done()
    )
    return stream_running or heartbeat_running


def _get_trade_stream() -> TradingStream:
    global _trade_stream
    if not is_trade_updates_enabled():
        raise AlpacaNotConfiguredError("Alpaca credentials are not configured")
    if _trade_stream is None:
        _trade_stream = TradingStream(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            paper=PAPER_TRADING,
        )
    return _trade_stream


async def _on_trade_update(update) -> None:
    await apply_trade_update(update)


async def _run_trade_stream(stream: TradingStream) -> None:
    try:
        await stream._run_forever()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Trading stream error")


async def start_trade_updates_stream():
    global _trade_stream_task, _trade_updates_heartbeat_task
    if is_trade_updates_running():
        return
    if not is_trade_updates_enabled():
        logger.warning("Trade updates stream disabled: credentials are not configured")
        return

    stream = _get_trade_stream()
    stream.subscribe_trade_updates(_on_trade_update)
    _trade_stream_task = asyncio.create_task(_run_trade_stream(stream))

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(60)

    _trade_updates_heartbeat_task = asyncio.create_task(_heartbeat())
    logger.info("Trade updates stream started")


async def stop_trade_updates_stream():
    global _trade_stream, _trade_stream_task, _trade_updates_heartbeat_task
    if _trade_updates_heartbeat_task is not None:
        _trade_updates_heartbeat_task.cancel()
        try:
            await _trade_updates_heartbeat_task
        except asyncio.CancelledError:
            pass
        _trade_updates_heartbeat_task = None

    if _trade_stream_task is not None:
        _trade_stream_task.cancel()
        try:
            await _trade_stream_task
        except asyncio.CancelledError:
            pass
        _trade_stream_task = None

    if _trade_stream is not None:
        try:
            await _trade_stream.stop_ws()
        except Exception:
            logger.exception("Failed to stop trade updates stream cleanly")
        try:
            await _trade_stream.close()
        except Exception:
            logger.exception("Failed to close trade updates stream")
        _trade_stream = None
