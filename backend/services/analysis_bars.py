from __future__ import annotations

import asyncio

from services.alpaca_client import alpaca_client
from services.bars_cache import get_bars_with_cache
from services.research_profile import (
    filter_bars_for_research_profile,
    get_research_profile,
)

MAX_ANALYSIS_BAR_LIMIT = 1000
DEFAULT_ANALYSIS_BAR_LIMIT = MAX_ANALYSIS_BAR_LIMIT
INCOMPLETE_BACKFILL_ERROR = "Historical bars are still incomplete after Alpaca backfill"


async def get_analysis_bars(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
    research_profile: str | None = None,
) -> list[dict]:
    profile = get_research_profile(research_profile)
    normalized_symbol = symbol.upper()
    if alpaca_client.is_crypto_symbol(normalized_symbol):
        bars = await asyncio.to_thread(
            alpaca_client.get_bars,
            normalized_symbol,
            timeframe,
            start,
            end,
            limit,
        )
    else:
        try:
            bars = await get_bars_with_cache(
                symbol=normalized_symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )
        except RuntimeError as exc:
            if str(exc) != INCOMPLETE_BACKFILL_ERROR:
                raise
            bars = await asyncio.to_thread(
                alpaca_client.get_bars,
                normalized_symbol,
                timeframe,
                start,
                end,
                limit,
            )
    return filter_bars_for_research_profile(bars, profile)
