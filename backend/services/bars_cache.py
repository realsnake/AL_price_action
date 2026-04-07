from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session
from models import BarCache
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client

logger = logging.getLogger(__name__)


async def get_bars_with_cache(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    symbol = symbol.upper()
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        if end
        else datetime.now(timezone.utc)
    )

    async with async_session() as session:
        cache_bounds = await _read_cache_bounds(session, symbol, timeframe)
        if _cache_satisfies_request(cache_bounds, start_dt, end_dt):
            rows = await _read_cached_rows(
                session, symbol, timeframe, start_dt, end_dt, limit
            )
            return _serialize_rows(rows)

        if not alpaca_client.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

        new_bars = alpaca_client.get_bars(
            symbol, timeframe, start_dt.isoformat(), end_dt.isoformat(), limit
        )
        if new_bars:
            await _upsert_bars(session, symbol, timeframe, new_bars)
            logger.info("Cached %d new bars for %s/%s", len(new_bars), symbol, timeframe)

        refreshed_rows = await _read_cached_rows(
            session, symbol, timeframe, start_dt, end_dt, limit
        )

    return _serialize_rows(refreshed_rows)


async def _read_cache_bounds(session, symbol: str, timeframe: str):
    result = await session.execute(
        select(
            func.min(BarCache.timestamp),
            func.max(BarCache.timestamp),
        ).where(
            BarCache.symbol == symbol,
            BarCache.timeframe == timeframe,
        )
    )
    row = result.first()
    if row is None:
        return None, None
    earliest, latest = row
    return _normalize_timestamp(earliest), _normalize_timestamp(latest)


async def _read_cached_rows(
    session, symbol: str, timeframe: str, start_dt, end_dt, limit: int
):
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
    return result.scalars().all()


def _cache_satisfies_request(cache_bounds, start_dt, end_dt) -> bool:
    earliest, latest = cache_bounds
    if earliest is None or latest is None:
        return False
    return earliest <= start_dt and latest >= end_dt


def _normalize_timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_rows(rows) -> list[dict]:
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
