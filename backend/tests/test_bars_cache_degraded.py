from datetime import datetime, timezone

import pytest

from services import bars_cache
from services.alpaca_client import AlpacaNotConfiguredError


class _DummyRow:
    def __init__(self, ts, open_, high, low, close, volume):
        self.timestamp = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class _DummySessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _install_session(monkeypatch):
    monkeypatch.setattr(bars_cache, "async_session", lambda: _DummySessionContext())


@pytest.mark.asyncio
async def test_get_bars_with_cache_returns_short_complete_cache_without_remote_fetch(
    monkeypatch,
):
    rows = [
        _DummyRow("2025-01-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-02T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cache_bounds(session, symbol, timeframe):
        return rows[0].timestamp, rows[-1].timestamp

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    class FakeDatetime:
        @staticmethod
        def fromisoformat(value):
            return datetime.fromisoformat(value)

        @staticmethod
        def now(tz=None):
            return datetime(2025, 1, 2, tzinfo=timezone.utc)

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "datetime", FakeDatetime)
    monkeypatch.setattr(bars_cache, "_read_cache_bounds", fake_read_cache_bounds)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        limit=200,
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
async def test_get_bars_with_cache_returns_capped_range_without_remote_fetch(
    monkeypatch,
):
    rows = [
        _DummyRow("2025-01-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-02T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cache_bounds(session, symbol, timeframe):
        return rows[0].timestamp, datetime(2025, 1, 5, tzinfo=timezone.utc)

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        assert limit == 2
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cache_bounds", fake_read_cache_bounds)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-05",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert len(result) == 2
    assert result[-1]["close"] == 101.5


@pytest.mark.asyncio
async def test_get_bars_with_cache_raises_when_cache_tail_does_not_cover_start(
    monkeypatch,
):
    rows = [
        _DummyRow("2025-01-04T00:00:00", 101.0, 102.0, 100.0, 101.5, 1100),
        _DummyRow("2025-01-05T00:00:00", 101.5, 103.0, 101.0, 102.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cache_bounds(session, symbol, timeframe):
        return rows[0].timestamp, rows[-1].timestamp

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cache_bounds", fake_read_cache_bounds)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
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
            end="2025-01-05",
            limit=2,
        )

    assert remote_fetch_calls == 0


@pytest.mark.asyncio
async def test_get_bars_with_cache_backfills_from_requested_start(monkeypatch):
    rows = [
        _DummyRow("2025-01-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    captured = {}

    async def fake_read_cache_bounds(session, symbol, timeframe):
        return (
            datetime(2025, 1, 4, tzinfo=timezone.utc),
            datetime(2025, 1, 5, tzinfo=timezone.utc),
        )

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt, limit):
        return rows

    async def fake_upsert_bars(session, symbol, timeframe, bars):
        captured["upsert_bars"] = bars

    def fake_get_bars(symbol, timeframe, start, end=None, limit=1000):
        captured["fetch"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
        }
        return rows

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cache_bounds", fake_read_cache_bounds)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache, "_upsert_bars", fake_upsert_bars)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-31",
        limit=200,
    )

    assert captured["fetch"] == {
        "symbol": "QQQ",
        "timeframe": "1D",
        "start": "2025-01-01T00:00:00+00:00",
        "end": "2025-01-31T00:00:00+00:00",
        "limit": 200,
    }
    assert captured["upsert_bars"] == rows
    assert result == [
        {
            "time": "2025-01-01T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        }
    ]
