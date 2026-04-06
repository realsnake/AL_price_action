import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
