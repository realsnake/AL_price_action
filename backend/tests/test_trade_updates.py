import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from services import trade_updates


class _FakeTradingStream:
    def __init__(self, loop):
        self._running = True
        self._loop = loop
        self.handler = None

    def subscribe_trade_updates(self, handler):
        self.handler = handler


@pytest.mark.asyncio
async def test_start_stream_registers_trade_updates_handler(monkeypatch):
    trade_updates._trade_stream = None
    trade_updates._trade_stream_task = None
    loop = asyncio.get_running_loop()
    stream = _FakeTradingStream(loop)
    started = {"called": False}

    monkeypatch.setattr(trade_updates.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(trade_updates, "_get_trade_stream", lambda: stream)

    async def fake_run(stream_obj):
        started["called"] = True
        await asyncio.sleep(0)

    monkeypatch.setattr(trade_updates, "_run_trade_stream", fake_run)

    await trade_updates.start_trade_updates_stream()
    await asyncio.sleep(0)

    assert stream.handler == trade_updates._on_trade_update
    assert started["called"] is True

    trade_updates._trade_stream_task = None
    trade_updates._trade_stream = None


@pytest.mark.asyncio
async def test_on_trade_update_forwards_to_trade_executor(monkeypatch):
    captured = {}

    async def fake_apply_trade_update(update):
        captured["update"] = update

    monkeypatch.setattr(trade_updates, "apply_trade_update", fake_apply_trade_update)

    update = SimpleNamespace(event="fill", order=SimpleNamespace(id="ord-1"))
    await trade_updates._on_trade_update(update)

    assert captured["update"] is update
