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
async def test_get_bars_with_cache_returns_empty_for_explicit_end_window_without_market_bars(
    monkeypatch,
):
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return []

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-04",
        end="2025-01-05",
        limit=10,
    )

    assert remote_fetch_calls == 0
    assert result == []


@pytest.mark.asyncio
async def test_get_bars_with_cache_returns_cache_only_for_friday_to_monday_daily_gap(
    monkeypatch,
):
    rows = [
        _DummyRow("2025-01-03T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-06T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-03",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2025-01-03T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T00:00:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_keeps_2020_juneteenth_as_trading_day(monkeypatch):
    rows = [
        _DummyRow("2020-06-18T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2020-06-19T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2020-06-18",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2020-06-18T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2020-06-19T00:00:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_keeps_2021_12_31_as_trading_day(monkeypatch):
    rows = [
        _DummyRow("2021-12-30T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2021-12-31T00:00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1D",
        start="2021-12-30",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2021-12-30T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2021-12-31T00:00:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_returns_intraday_overnight_session_gap_cache_only(
    monkeypatch,
):
    rows = [
        _DummyRow("2025-01-03T20:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-06T14:30:00+00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1h",
        start="2025-01-03T15:30:00-05:00",
        end="2025-01-06T09:30:00-05:00",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2025-01-03T20:30:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_respects_half_day_early_close(monkeypatch):
    rows = [
        _DummyRow("2024-11-29T17:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2024-12-02T14:30:00+00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1h",
        start="2024-11-29T12:30:00-05:00",
        end="2024-12-02T09:30:00-05:00",
        limit=2,
    )

    assert remote_fetch_calls == 0
    assert result == [
        {
            "time": "2024-11-29T17:30:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2024-12-02T14:30:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_does_not_treat_2026_07_02_as_independence_half_day(
    monkeypatch,
):
    rows = [
        _DummyRow("2026-07-02T16:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    with pytest.raises(
        AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        await bars_cache.get_bars_with_cache(
            symbol="qqq",
            timeframe="1h",
            start="2026-07-02T12:30:00-04:00",
            end="2026-07-02T13:30:00-04:00",
            limit=10,
        )

    assert remote_fetch_calls == 0


@pytest.mark.asyncio
async def test_get_bars_with_cache_does_not_treat_2022_07_01_as_independence_half_day(
    monkeypatch,
):
    rows = [
        _DummyRow("2022-07-01T16:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: False)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    with pytest.raises(
        AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        await bars_cache.get_bars_with_cache(
            symbol="qqq",
            timeframe="1h",
            start="2022-07-01T12:30:00-04:00",
            end="2022-07-01T13:30:00-04:00",
            limit=10,
        )

    assert remote_fetch_calls == 0


@pytest.mark.asyncio
async def test_get_bars_with_cache_raises_for_sparse_cache_gap(monkeypatch):
    rows = [
        _DummyRow("2025-01-06T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000),
        _DummyRow("2025-01-08T00:00:00", 101.0, 102.0, 100.0, 101.5, 1300),
    ]
    remote_fetch_calls = 0

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return rows

    def fake_get_bars(*args, **kwargs):
        nonlocal remote_fetch_calls
        remote_fetch_calls += 1
        return []

    _install_session(monkeypatch)
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
            start="2025-01-06",
            end="2025-01-08",
            limit=10,
        )

    assert remote_fetch_calls == 0


@pytest.mark.asyncio
async def test_get_bars_with_cache_normalizes_offset_aware_bounds_before_fetching(
    monkeypatch,
):
    initial_rows = [
        _DummyRow("2025-01-03T20:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    fetched_rows = [
        _DummyRow("2025-01-06T14:30:00+00:00", 100.5, 102.0, 100.0, 101.5, 1200),
    ]
    captured = {}

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return fake_read_cached_rows.results.pop(0)

    fake_read_cached_rows.results = [initial_rows, initial_rows + fetched_rows]

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
        return fetched_rows

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache, "_upsert_bars", fake_upsert_bars)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    result = await bars_cache.get_bars_with_cache(
        symbol="qqq",
        timeframe="1h",
        start="2025-01-03T15:30:00-05:00",
        end="2025-01-06T09:30:00-05:00",
        limit=10,
    )

    assert captured["fetch"] == {
        "symbol": "QQQ",
        "timeframe": "1h",
        "start": "2025-01-06T14:30:00+00:00",
        "end": "2025-01-06T14:30:00+00:00",
        "limit": 10,
    }
    assert captured["upsert_bars"] == fetched_rows
    assert result == [
        {
            "time": "2025-01-03T20:30:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
        },
    ]


@pytest.mark.asyncio
async def test_get_bars_with_cache_raises_when_backfill_still_leaves_gap(monkeypatch):
    rows = [
        _DummyRow("2025-01-03T20:30:00+00:00", 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    captured = {}

    async def fake_read_cached_rows(session, symbol, timeframe, start_dt, end_dt):
        return fake_read_cached_rows.results.pop(0)

    fake_read_cached_rows.results = [rows, rows]

    def fake_get_bars(symbol, timeframe, start, end=None, limit=1000):
        captured["fetch"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
        }
        return []

    _install_session(monkeypatch)
    monkeypatch.setattr(bars_cache, "_read_cached_rows", fake_read_cached_rows)
    monkeypatch.setattr(bars_cache.alpaca_client, "is_configured", lambda: True)
    monkeypatch.setattr(bars_cache.alpaca_client, "get_bars", fake_get_bars)

    with pytest.raises(
        RuntimeError,
        match="Historical bars are still incomplete after Alpaca backfill",
    ):
        await bars_cache.get_bars_with_cache(
            symbol="qqq",
            timeframe="1h",
            start="2025-01-03T15:30:00-05:00",
            end="2025-01-06T09:30:00-05:00",
            limit=10,
        )

    assert captured["fetch"] == {
        "symbol": "QQQ",
        "timeframe": "1h",
        "start": "2025-01-06T14:30:00+00:00",
        "end": "2025-01-06T14:30:00+00:00",
        "limit": 10,
    }
