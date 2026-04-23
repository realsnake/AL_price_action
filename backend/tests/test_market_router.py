from typing import Optional

import pytest

from routers import market as market_router


@pytest.mark.asyncio
async def test_market_bars_route_uses_analysis_bars_service(monkeypatch):
    captured = {}
    expected_bars = [
        {
            "time": "2025-01-06T14:30:00+00:00",
            "open": 498.5,
            "high": 499.5,
            "low": 498.0,
            "close": 499.0,
            "volume": 1200,
        }
    ]

    async def fake_get_analysis_bars(
        symbol: str,
        timeframe: str,
        start: str,
        end: Optional[str] = None,
        limit: int = 1000,
        research_profile: Optional[str] = None,
    ) -> list[dict]:
        captured.update(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
                "research_profile": research_profile,
            }
        )
        return expected_bars

    monkeypatch.setattr(market_router, "get_analysis_bars", fake_get_analysis_bars)

    result = await market_router.get_bars(
        symbol="qqq",
        timeframe="5m",
        start="2025-01-01",
        end="2025-01-31",
        limit=300,
        research_profile="qqq_5m_phase1",
    )

    assert result == {
        "symbol": "qqq",
        "timeframe": "5m",
        "bars": expected_bars,
    }
    assert captured == {
        "symbol": "qqq",
        "timeframe": "5m",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "limit": 300,
        "research_profile": "qqq_5m_phase1",
    }
