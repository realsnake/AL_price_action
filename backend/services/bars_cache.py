from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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
        rows = await _read_cached_rows(
            session, symbol, timeframe, start_dt, end_dt, limit
        )
        if _cache_satisfies_request(rows, end, end_dt, limit):
            return _serialize_rows(rows)

        if not alpaca_client.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

        latest_cached = await _latest_cached_timestamp(session, symbol, timeframe)
        api_start = (
            latest_cached.isoformat()
            if latest_cached is not None
            else start_dt.isoformat()
        )
        new_bars = alpaca_client.get_bars(
            symbol, timeframe, api_start, end_dt.isoformat(), limit
        )
        if new_bars:
            await _upsert_bars(session, symbol, timeframe, new_bars)
            logger.info("Cached %d new bars for %s/%s", len(new_bars), symbol, timeframe)

        refreshed_rows = await _read_cached_rows(
            session, symbol, timeframe, start_dt, end_dt, limit
        )

    return _serialize_rows(refreshed_rows)


async def _latest_cached_timestamp(session, symbol: str, timeframe: str):
    result = await session.execute(
        select(func.max(BarCache.timestamp)).where(
            BarCache.symbol == symbol,
            BarCache.timeframe == timeframe,
        )
    )
    return result.scalar_one_or_none()


async def _read_cached_rows(session, symbol: str, timeframe: str, start_dt, end_dt, limit: int):
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


def _cache_satisfies_request(rows, end: str | None, end_dt, limit: int) -> bool:
    if not rows:
        return False
    if end is not None:
        last_ts = rows[-1].timestamp
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        return last_ts >= end_dt
    return len(rows) >= limit


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


def _timeframe_delta(timeframe: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1D": timedelta(days=1),
    }
    return mapping.get(timeframe, timedelta(days=1))
