from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from services.alpaca_client import alpaca_client
from services.research_profile import filter_bars_for_research_profile, get_research_profile
from services.research_validation import build_strategy_validation_report


DEFAULT_STRATEGIES = [
    "brooks_small_pb_trend",
    "brooks_pullback_count",
    "brooks_breakout_pullback",
]
SYMBOL = os.getenv("RESEARCH_SYMBOL", "QQQ")
TIMEFRAME = os.getenv("RESEARCH_TIMEFRAME", "5m")
START = os.getenv("RESEARCH_START", "2024-01-01T00:00:00+00:00")
END = os.getenv("RESEARCH_END", "2026-04-17T23:59:00+00:00")
RESEARCH_PROFILE = os.getenv("RESEARCH_PROFILE", "qqq_5m_phase1")
FIXED_QUANTITY = int(os.getenv("RESEARCH_FIXED_QUANTITY", "100"))
RESEARCH_LIMIT = (
    None
    if os.getenv("RESEARCH_LIMIT", "").strip().lower() in {"", "none", "all"}
    else int(os.getenv("RESEARCH_LIMIT", "10000"))
)
SLIPPAGE_BPS = float(os.getenv("BACKTEST_SLIPPAGE_BPS", "1.0"))
STRATEGIES = [
    name.strip()
    for name in os.getenv("RESEARCH_STRATEGIES", ",".join(DEFAULT_STRATEGIES)).split(",")
    if name.strip()
]


def main() -> None:
    profile = get_research_profile(RESEARCH_PROFILE)
    bars = alpaca_client.get_bars(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=START,
        end=END,
        limit=RESEARCH_LIMIT,
    )
    bars = [dict(v) for _, v in sorted({bar["time"]: bar for bar in bars}.items())]
    bars = filter_bars_for_research_profile(bars, profile)

    reports = [
        build_strategy_validation_report(
            strategy_name=name,
            bars=bars,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            research_profile=RESEARCH_PROFILE,
            fixed_quantity=FIXED_QUANTITY,
            slippage_bps=SLIPPAGE_BPS,
        )
        for name in STRATEGIES
    ]
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
