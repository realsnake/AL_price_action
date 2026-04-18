from __future__ import annotations

from services.bars_cache import get_bars_with_cache
from services.research_profile import (
    filter_bars_for_research_profile,
    get_research_profile,
)

MAX_ANALYSIS_BAR_LIMIT = 1000
DEFAULT_ANALYSIS_BAR_LIMIT = MAX_ANALYSIS_BAR_LIMIT


async def get_analysis_bars(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
    research_profile: str | None = None,
) -> list[dict]:
    profile = get_research_profile(research_profile)
    bars = await get_bars_with_cache(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )
    return filter_bars_for_research_profile(bars, profile)
