from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


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
            entry_cutoff=time(15, 30),
            flatten_daily=True,
        )
    raise ValueError(f"Unknown research profile: {name}")


def filter_bars_for_research_profile(
    bars: list[dict], research_profile: str | None
) -> list[dict]:
    profile = get_research_profile(research_profile)
    if profile is None or profile.session != "rth":
        return bars
    return [bar for bar in bars if _is_rth_bar(bar["time"])]


def market_time(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(MARKET_TZ)


def session_day(timestamp: str) -> str:
    return market_time(timestamp).date().isoformat()


def _is_rth_bar(timestamp: str) -> bool:
    local = market_time(timestamp)
    local_time = local.time()
    return local.weekday() < 5 and RTH_OPEN <= local_time < RTH_CLOSE
