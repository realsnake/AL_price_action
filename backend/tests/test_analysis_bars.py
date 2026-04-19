import pytest

from services import analysis_bars


@pytest.mark.asyncio
async def test_get_analysis_bars_uppercases_symbol_and_forwards_arguments(monkeypatch):
    captured = {}
    expected = [
        {
            "time": "2025-01-02T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "volume": 123456,
        }
    ]

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        captured.update(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        return expected

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    result = await analysis_bars.get_analysis_bars(
        symbol="qqq",
        timeframe="1D",
        start="2025-01-01",
        end="2025-01-31",
        limit=250,
    )

    assert result == expected
    assert captured == {
        "symbol": "QQQ",
        "timeframe": "1D",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 250,
    }


@pytest.mark.asyncio
async def test_get_analysis_bars_uses_default_limit(monkeypatch):
    captured = {}

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    await analysis_bars.get_analysis_bars(
        symbol="spy",
        timeframe="1D",
        start="2025-01-01",
    )

    assert captured["limit"] == analysis_bars.DEFAULT_ANALYSIS_BAR_LIMIT


@pytest.mark.asyncio
async def test_get_analysis_bars_filters_to_rth_for_qqq_5m_phase1(monkeypatch):
    raw_bars = [
        {
            "time": "2025-01-06T14:25:00+00:00",
            "open": 498.0,
            "high": 499.0,
            "low": 497.5,
            "close": 498.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 498.5,
            "high": 499.5,
            "low": 498.0,
            "close": 499.0,
            "volume": 1200,
        },
        {
            "time": "2025-01-06T20:55:00+00:00",
            "open": 501.0,
            "high": 501.5,
            "low": 500.5,
            "close": 501.2,
            "volume": 1400,
        },
        {
            "time": "2025-01-06T21:00:00+00:00",
            "open": 501.2,
            "high": 501.4,
            "low": 500.8,
            "close": 501.0,
            "volume": 900,
        },
    ]

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        return raw_bars

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    result = await analysis_bars.get_analysis_bars(
        symbol="qqq",
        timeframe="5m",
        start="2025-01-06",
        research_profile="qqq_5m_phase1",
    )

    assert [bar["time"] for bar in result] == [
        "2025-01-06T14:30:00+00:00",
        "2025-01-06T20:55:00+00:00",
    ]


@pytest.mark.asyncio
async def test_get_analysis_bars_uses_direct_alpaca_fetch_for_crypto_symbols(monkeypatch):
    expected = [
        {
            "time": "2025-01-06T00:00:00+00:00",
            "open": 98000.0,
            "high": 98500.0,
            "low": 97800.0,
            "close": 98250.0,
            "volume": 42,
        }
    ]
    captured = {}

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        raise AssertionError("stock cache path should not be used for crypto")

    def fake_get_bars(symbol, timeframe, start, end=None, limit=1000):
        captured.update(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        return expected

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)
    monkeypatch.setattr(analysis_bars.alpaca_client, "get_bars", fake_get_bars)

    result = await analysis_bars.get_analysis_bars(
        symbol="btc/usd",
        timeframe="5m",
        start="2025-01-01",
        end="2025-01-31",
        limit=300,
    )

    assert result == expected
    assert captured == {
        "symbol": "BTC/USD",
        "timeframe": "5m",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 300,
    }


@pytest.mark.asyncio
async def test_get_analysis_bars_keeps_all_bars_for_btc_5m_sandbox(monkeypatch):
    raw_bars = [
        {
            "time": "2025-01-06T00:00:00+00:00",
            "open": 98000.0,
            "high": 98500.0,
            "low": 97800.0,
            "close": 98250.0,
            "volume": 42,
        },
        {
            "time": "2025-01-06T00:05:00+00:00",
            "open": 98250.0,
            "high": 98600.0,
            "low": 98150.0,
            "close": 98400.0,
            "volume": 38,
        },
    ]

    def fake_get_bars(symbol, timeframe, start, end=None, limit=1000):
        return raw_bars

    monkeypatch.setattr(
        analysis_bars,
        "get_bars_with_cache",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("stock cache path should not be used for crypto")
        ),
    )
    monkeypatch.setattr(analysis_bars.alpaca_client, "get_bars", fake_get_bars)

    result = await analysis_bars.get_analysis_bars(
        symbol="BTC/USD",
        timeframe="5m",
        start="2025-01-06",
        research_profile="btc_5m_sandbox",
    )

    assert result == raw_bars


@pytest.mark.asyncio
async def test_get_analysis_bars_treats_naive_intraday_timestamps_as_utc(monkeypatch):
    raw_bars = [
        {
            "time": "2025-01-06T14:25:00",
            "open": 498.0,
            "high": 499.0,
            "low": 497.5,
            "close": 498.5,
            "volume": 1000,
        },
        {
            "time": "2025-01-06T14:30:00",
            "open": 498.5,
            "high": 499.5,
            "low": 498.0,
            "close": 499.0,
            "volume": 1200,
        },
        {
            "time": "2025-01-06T20:55:00",
            "open": 501.0,
            "high": 501.5,
            "low": 500.5,
            "close": 501.2,
            "volume": 1400,
        },
        {
            "time": "2025-01-06T21:00:00",
            "open": 501.2,
            "high": 501.4,
            "low": 500.8,
            "close": 501.0,
            "volume": 900,
        },
    ]

    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        return raw_bars

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    result = await analysis_bars.get_analysis_bars(
        symbol="qqq",
        timeframe="5m",
        start="2025-01-06",
        research_profile="qqq_5m_phase1",
    )

    assert [bar["time"] for bar in result] == [
        "2025-01-06T14:30:00",
        "2025-01-06T20:55:00",
    ]


@pytest.mark.asyncio
async def test_get_analysis_bars_rejects_unknown_research_profile(monkeypatch):
    async def fake_get_bars_with_cache(symbol, timeframe, start, end=None, limit=1000):
        raise AssertionError("get_bars_with_cache should not be called")

    monkeypatch.setattr(analysis_bars, "get_bars_with_cache", fake_get_bars_with_cache)

    with pytest.raises(ValueError, match="Unknown research profile"):
        await analysis_bars.get_analysis_bars(
            symbol="qqq",
            timeframe="5m",
            start="2025-01-06",
            research_profile="unknown_profile",
        )
