from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone

from services.bars_cache import MARKET_TZ, SESSION_OPEN, _is_trading_day, _session_close_for


@dataclass(frozen=True)
class ResearchProfile:
    name: str
    session: str
    long_only: bool
    skip_opening_bars: int
    entry_cutoff: time | None
    flatten_daily: bool


def get_research_profile(name: str | None) -> ResearchProfile | None:
    if name is None:
        return None
    if name == "qqq_5m_phase1":
        return ResearchProfile(
            name=name,
            session="rth",
            long_only=True,
            skip_opening_bars=2,
            entry_cutoff=time(14, 0),
            flatten_daily=True,
        )
    raise ValueError(f"Unknown research profile: {name}")


def filter_bars_for_research_profile(
    bars: list[dict], profile: ResearchProfile | None
) -> list[dict]:
    if profile is None or profile.session != "rth":
        return bars
    return [bar for bar in bars if _is_rth_bar(bar["time"])]


def market_time(timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MARKET_TZ)


def session_day(timestamp: str) -> str:
    return market_time(timestamp).date().isoformat()


def _is_rth_bar(timestamp: str) -> bool:
    local = market_time(timestamp)
    return (
        local.weekday() < 5
        and _is_trading_day(local.date())
        and SESSION_OPEN <= local.time() < _session_close_for(local.date()).time()
    )


def is_rth_bar_timestamp(timestamp: str) -> bool:
    return _is_rth_bar(timestamp)


def is_session_final_bar_timestamp(timestamp: str, timeframe_minutes: int = 5) -> bool:
    local = market_time(timestamp)
    if not _is_trading_day(local.date()):
        return False
    session_close = _session_close_for(local.date())
    bar_end = local + timedelta(minutes=timeframe_minutes)
    return local < session_close <= bar_end
