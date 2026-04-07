from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
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
        rows = await _read_cached_rows(session, symbol, timeframe, start_dt, end_dt)
        cache_hit, fetch_start = _cache_satisfies_request(
            rows, timeframe, start_dt, end_dt, limit, end is not None
        )
        if cache_hit:
            return _serialize_rows(rows[:limit])

        if not alpaca_client.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

        fetch_start = fetch_start or start_dt
        new_bars = alpaca_client.get_bars(
            symbol, timeframe, fetch_start.isoformat(), end_dt.isoformat(), limit
        )
        if new_bars:
            await _upsert_bars(session, symbol, timeframe, new_bars)
            logger.info("Cached %d new bars for %s/%s", len(new_bars), symbol, timeframe)

        refreshed_rows = await _read_cached_rows(
            session, symbol, timeframe, start_dt, end_dt
        )

    return _serialize_rows(refreshed_rows[:limit])


async def _read_cached_rows(session, symbol: str, timeframe: str, start_dt, end_dt):
    result = await session.execute(
        select(BarCache)
        .where(
            BarCache.symbol == symbol,
            BarCache.timeframe == timeframe,
            BarCache.timestamp >= start_dt,
            BarCache.timestamp <= end_dt,
        )
        .order_by(BarCache.timestamp)
    )
    return result.scalars().all()


def _cache_satisfies_request(rows, timeframe, start_dt, end_dt, limit, explicit_end):
    if not rows:
        return False, None

    expected_timestamp = start_dt
    contiguous_count = 0
    delta = _timeframe_delta(timeframe)

    for row in rows:
        row_timestamp = _normalize_timestamp(row.timestamp)
        if row_timestamp < expected_timestamp:
            continue
        if row_timestamp > expected_timestamp:
            return False, expected_timestamp

        contiguous_count += 1
        expected_timestamp = _advance_timestamp(expected_timestamp, delta)

        if explicit_end and expected_timestamp > end_dt:
            return True, None
        if not explicit_end and contiguous_count >= limit:
            return True, None

    if explicit_end:
        return False, expected_timestamp

    return (contiguous_count >= limit), (None if contiguous_count >= limit else expected_timestamp)


def _normalize_timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _advance_timestamp(value, delta):
    return value + delta


def _timeframe_delta(timeframe: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1D": timedelta(days=1),
    }
    return mapping.get(timeframe, timedelta(days=1))


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
