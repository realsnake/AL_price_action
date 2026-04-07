from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session
from models import BarCache
from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client

logger = logging.getLogger(__name__)
MARKET_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
HALF_DAY_CLOSE = time(13, 0)


class _NyseHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        USMartinLutherKingJr,
        USPresidentsDay,
        USMemorialDay,
        GoodFriday,
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]


async def get_bars_with_cache(
    symbol: str,
    timeframe: str,
    start: str,
    end: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    symbol = symbol.upper()
    start_dt = _parse_request_timestamp(start)
    end_dt = (
        _parse_request_timestamp(end)
        if end
        else datetime.now(timezone.utc)
    )

    if end is not None and _first_expected_timestamp(start_dt, timeframe) > end_dt:
        return []

    async with async_session() as session:
        rows = await _read_cached_rows(session, symbol, timeframe, start_dt, end_dt)
        cache_hit, fetch_start = _cache_satisfies_request(
            rows, timeframe, start_dt, end_dt, limit, end is not None
        )
        if cache_hit:
            return _serialize_rows(rows[:limit])

        if not alpaca_client.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

        fetch_start = _normalize_timestamp(fetch_start or start_dt)
        new_bars = alpaca_client.get_bars(
            symbol, timeframe, fetch_start.isoformat(), end_dt.isoformat(), limit
        )
        if new_bars:
            await _upsert_bars(session, symbol, timeframe, new_bars)
            logger.info("Cached %d new bars for %s/%s", len(new_bars), symbol, timeframe)

        refreshed_rows = await _read_cached_rows(
            session, symbol, timeframe, start_dt, end_dt
        )
        refreshed_hit, _ = _cache_satisfies_request(
            refreshed_rows, timeframe, start_dt, end_dt, limit, end is not None
        )
        if not refreshed_hit:
            raise RuntimeError("Historical bars are still incomplete after Alpaca backfill")

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
        return False, _first_expected_timestamp(start_dt, timeframe)

    expected_timestamp = _first_expected_timestamp(start_dt, timeframe)
    contiguous_count = 0

    for row in rows:
        row_timestamp = _normalize_timestamp(row.timestamp)
        if row_timestamp < expected_timestamp:
            continue
        if row_timestamp > expected_timestamp:
            return False, expected_timestamp

        contiguous_count += 1
        expected_timestamp = _next_expected_timestamp(expected_timestamp, timeframe)

        if explicit_end and expected_timestamp > end_dt:
            return True, None
        if not explicit_end and contiguous_count >= limit:
            return True, None

    if explicit_end:
        return False, expected_timestamp

    return (contiguous_count >= limit), (None if contiguous_count >= limit else expected_timestamp)


def _parse_request_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _normalize_timestamp(parsed)


def _normalize_timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _first_expected_timestamp(start_dt: datetime, timeframe: str) -> datetime:
    if timeframe == "1D":
        return _first_expected_daily_timestamp(start_dt)
    return _first_expected_intraday_timestamp(start_dt, timeframe)


def _next_expected_timestamp(current: datetime, timeframe: str) -> datetime:
    if timeframe == "1D":
        return _next_daily_timestamp(current)
    return _next_intraday_timestamp(current, timeframe)


def _first_expected_daily_timestamp(start_dt: datetime) -> datetime:
    expected = _normalize_timestamp(start_dt)
    while not _is_trading_day(expected.date()):
        expected = expected + timedelta(days=1)
    return expected


def _next_daily_timestamp(current: datetime) -> datetime:
    expected = _normalize_timestamp(current) + timedelta(days=1)
    while not _is_trading_day(expected.date()):
        expected = expected + timedelta(days=1)
    return expected


def _first_expected_intraday_timestamp(start_dt: datetime, timeframe: str) -> datetime:
    minutes = _timeframe_minutes(timeframe)
    local = _normalize_timestamp(start_dt).astimezone(MARKET_TZ)
    if not _is_trading_day(local.date()):
        return _session_open_for(_next_trading_day(local.date()))

    session_open = _session_open_for(local.date())
    session_close = _session_close_for(local.date())

    if local < session_open:
        return session_open
    if local >= session_close:
        return _session_open_for(_next_trading_day(local.date()))

    offset_minutes = int((local - session_open).total_seconds() // 60)
    aligned_minutes = ((offset_minutes + minutes - 1) // minutes) * minutes
    candidate = session_open + timedelta(minutes=aligned_minutes)
    if candidate < session_close:
        return candidate
    return _session_open_for(_next_trading_day(local.date()))


def _next_intraday_timestamp(current: datetime, timeframe: str) -> datetime:
    minutes = _timeframe_minutes(timeframe)
    local = _normalize_timestamp(current).astimezone(MARKET_TZ)
    candidate = local + timedelta(minutes=minutes)
    if candidate.date() == local.date() and candidate < _session_close_for(local.date()):
        return candidate
    return _session_open_for(_next_trading_day(local.date()))


def _timeframe_minutes(timeframe: str) -> int:
    mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
    return mapping.get(timeframe, 60)


def _session_open_for(day: date) -> datetime:
    return datetime.combine(day, SESSION_OPEN, tzinfo=MARKET_TZ)


def _session_close_for(day: date) -> datetime:
    return datetime.combine(day, _session_close_time_for(day), tzinfo=MARKET_TZ)


def _is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in _market_holiday_dates(day.year - 1, day.year + 1)


def _next_trading_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while not _is_trading_day(candidate):
        candidate = candidate + timedelta(days=1)
    return candidate


@lru_cache(maxsize=64)
def _market_holiday_dates(start_year: int, end_year: int) -> frozenset[date]:
    calendar = _NyseHolidayCalendar()
    holidays = calendar.holidays(
        start=f"{start_year}-01-01",
        end=f"{end_year}-12-31",
    )
    holiday_dates = {ts.date() for ts in holidays}
    for year in range(start_year, end_year + 1):
        holiday_dates.add(_observed_new_years_day(year))
        observed_juneteenth = _observed_juneteenth(year)
        if observed_juneteenth is not None:
            holiday_dates.add(observed_juneteenth)
    return frozenset(holiday_dates)


def _session_close_time_for(day: date) -> time:
    if _is_half_day(day):
        return HALF_DAY_CLOSE
    return SESSION_CLOSE


def _is_half_day(day: date) -> bool:
    return (
        _is_day_after_thanksgiving(day)
        or _is_christmas_eve_half_day(day)
        or _is_independence_day_eve_half_day(day)
    )


def _is_day_after_thanksgiving(day: date) -> bool:
    thanksgiving = _nth_weekday_of_month(day.year, 11, 3, 4)
    return day == thanksgiving + timedelta(days=1)


def _is_christmas_eve_half_day(day: date) -> bool:
    return day.month == 12 and day.day == 24 and _is_trading_day(day)


def _is_independence_day_eve_half_day(day: date) -> bool:
    observed = _observed_independence_day(day.year)
    if day >= observed:
        return False

    candidate = observed - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return day == candidate


def _observed_new_years_day(year: int) -> date:
    actual = date(year, 1, 1)
    if actual.weekday() == 5:
        return actual
    if actual.weekday() == 6:
        return date(year, 1, 2)
    return actual


def _observed_juneteenth(year: int) -> date | None:
    if year < 2021:
        return None

    actual = date(year, 6, 19)
    if year == 2021:
        return date(2021, 6, 18)
    if actual.weekday() == 5:
        return date(year, 6, 18)
    if actual.weekday() == 6:
        return date(year, 6, 20)
    return actual


def _observed_independence_day(year: int) -> date:
    actual = date(year, 7, 4)
    if actual.weekday() == 5:
        return date(year, 7, 3)
    if actual.weekday() == 6:
        return date(year, 7, 5)
    return actual


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=offset + 7 * (n - 1))


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
