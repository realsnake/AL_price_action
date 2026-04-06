from __future__ import annotations

from services.bars_cache import get_bars_with_cache

MAX_ANALYSIS_BAR_LIMIT = 1000
DEFAULT_ANALYSIS_BAR_LIMIT = MAX_ANALYSIS_BAR_LIMIT


async def get_analysis_bars(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
) -> list[dict]:
    return await get_bars_with_cache(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )
