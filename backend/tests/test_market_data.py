import asyncio

import pytest

from services import market_data


class _FakeStream:
    def __init__(self, loop):
        self._running = True
        self._loop = loop
        self._handlers = {"bars": {}}
        self.subscribe_sent = 0
        self.unsubscribe_calls = []

    def _ensure_coroutine(self, handler):
        assert asyncio.iscoroutinefunction(handler)

    async def _send_subscribe_msg(self):
        self.subscribe_sent += 1

    async def _send_unsubscribe_msg(self, channel, symbols):
        self.unsubscribe_calls.append((channel, list(symbols)))

    def subscribe_bars(self, handler, symbol):
        raise AssertionError("blocking subscribe_bars path should not be used")

    def unsubscribe_bars(self, symbol):
        raise AssertionError("blocking unsubscribe_bars path should not be used")


@pytest.mark.asyncio
async def test_subscribe_uses_nonblocking_path_on_stream_loop(monkeypatch):
    market_data._callbacks.clear()
    loop = asyncio.get_running_loop()
    stream = _FakeStream(loop)

    monkeypatch.setattr(market_data, "is_live_stream_enabled", lambda: True)
    monkeypatch.setattr(market_data, "_get_stream", lambda: stream)

    async def cb(symbol, payload):
        return None

    await market_data.subscribe("aapl", cb)
    await asyncio.sleep(0)

    assert "AAPL" in market_data._callbacks
    assert market_data._callbacks["AAPL"] == [cb]
    assert stream._handlers["bars"]["AAPL"] == market_data._on_bar
    assert stream.subscribe_sent == 1


@pytest.mark.asyncio
async def test_unsubscribe_uses_nonblocking_path_on_stream_loop(monkeypatch):
    loop = asyncio.get_running_loop()
    stream = _FakeStream(loop)
    stream._handlers["bars"]["AAPL"] = market_data._on_bar

    async def cb(symbol, payload):
        return None

    market_data._callbacks.clear()
    market_data._callbacks["AAPL"] = [cb]

    monkeypatch.setattr(market_data, "is_live_stream_enabled", lambda: True)
    monkeypatch.setattr(market_data, "_get_stream", lambda: stream)

    await market_data.unsubscribe("aapl", cb)
    await asyncio.sleep(0)

    assert "AAPL" not in market_data._callbacks
    assert "AAPL" not in stream._handlers["bars"]
    assert stream.unsubscribe_calls == [("bars", ["AAPL"])]
