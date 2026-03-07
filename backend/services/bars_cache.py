from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session
from models import BarCache
from services.alpaca_client import alpaca_client

logger = logging.getLogger(__name__)


async def get_bars_with_cache(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Fetch bars with DB caching and incremental updates.

    1. Query the latest cached timestamp for this symbol+timeframe.
    2. If cache exists, only fetch new bars from API after the latest cached time.
    3. Upsert new bars into the cache.
    4. Return the requested range from the cache.
    """
    symbol = symbol.upper()
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        if end
        else datetime.now(timezone.utc)
    )

    async with async_session() as session:
        # Find the latest cached bar for this symbol+timeframe
        result = await session.execute(
            select(func.max(BarCache.timestamp)).where(
                BarCache.symbol == symbol,
                BarCache.timeframe == timeframe,
            )
        )
        latest_cached = result.scalar_one_or_none()

        # Determine the API fetch start time
        if latest_cached is not None:
            # Ensure timezone-aware
            if latest_cached.tzinfo is None:
                latest_cached = latest_cached.replace(tzinfo=timezone.utc)
            # Re-fetch from the latest cached bar to update the potentially
            # incomplete (still-open) bar, then fetch anything newer.
            api_start = latest_cached.isoformat()
        else:
            # No cache at all — fetch from user-requested start
            api_start = start_dt.isoformat()

        # Fetch new bars from Alpaca API if needed
        if api_start is not None:
            try:
                new_bars = alpaca_client.get_bars(
                    symbol, timeframe, api_start, end_dt.isoformat(), limit
                )
                if new_bars:
                    await _upsert_bars(session, symbol, timeframe, new_bars)
                    logger.info(
                        "Cached %d new bars for %s/%s", len(new_bars), symbol, timeframe
                    )
            except Exception:
                logger.exception("Failed to fetch bars from API for %s", symbol)

        # Read from cache for the requested range
        result = await session.execute(
            select(BarCache)
            .where(
                BarCache.symbol == symbol,
                BarCache.timeframe == timeframe,
                BarCache.timestamp >= start_dt,
                BarCache.timestamp <= end_dt,
            )
            .order_by(BarCache.timestamp)
            .limit(limit)
        )
        rows = result.scalars().all()

    return [
        {
            "time": row.timestamp.isoformat(),
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in rows
    ]


async def _upsert_bars(
    session, symbol: str, timeframe: str, bars: list[dict]
) -> None:
    """Insert bars into cache, updating on conflict (upsert)."""
    for bar in bars:
        ts = datetime.fromisoformat(bar["time"])
        stmt = sqlite_insert(BarCache).values(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        await session.execute(stmt)
    await session.commit()


def _timeframe_delta(timeframe: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1D": timedelta(days=1),
    }
    return mapping.get(timeframe, timedelta(days=1))
