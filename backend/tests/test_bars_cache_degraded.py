from datetime import datetime, timezone

import pytest

from services import bars_cache
from services.alpaca_client import AlpacaNotConfiguredError


class _DummyResult:
    def __init__(self, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DummySession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, query):
        if not self._results:
            raise AssertionError("unexpected database query")
        return self._results.pop(0)


class _DummySessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyRow:
    def __init__(self, ts, open_, high, low, close, volume):
        self.timestamp = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


@pytest.mark.asyncio
async def test_get_bars_with_cache_returns_cached_rows_without_remote_fetch(monkeypatch):
    cached_rows = [
        _DummyRow("2025-01-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-02T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    def fake_async_session():
        session = _DummySession(
            [
                _DummyResult(rows=cached_rows),
            ]
        )
        return _DummySessionContext(session)

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    monkeypatch.setattr(bars_cache, "async_session", fake_async_session)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-02",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2025-01-01T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-02T00:00:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_raises_when_cache_miss_requires_alpaca(monkeypatch):
    remote_fetch_calls = 0

    def fake_async_session():
        session = _DummySession(
            [
                _DummyResult(rows=[]),
            ]
        )
        return _DummySessionContext(session)

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    monkeypatch.setattr(bars_cache, "async_session", fake_async_session)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    with pytest.raises(
        AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        await bars_cache.get_bars_with_cache(
            symbol="qqq",
            timeframe="1D",
            start="2025-01-01",
            end="2025-01-31",
            limit=2,
        )

    assert remote_fetch_calls == 0
