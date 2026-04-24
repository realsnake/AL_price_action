from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from services.alpaca_client import alpaca_client
from services.analysis_bars import get_analysis_bars
from services.research_profile import filter_bars_for_research_profile, get_research_profile
from services.backtester import run_backtest
from services.strategy_engine import get_strategy
from services.trade_replay_report import write_trade_replay_report


STRATEGY = os.getenv("REPORT_STRATEGY", "brooks_breakout_pullback")
SYMBOL = os.getenv("REPORT_SYMBOL", "QQQ")
TIMEFRAME = os.getenv("REPORT_TIMEFRAME", "5m")
START = os.getenv("REPORT_START", "2024-01-01")
END = os.getenv("REPORT_END", "2026-04-17")
RESEARCH_PROFILE = os.getenv("REPORT_RESEARCH_PROFILE", "qqq_5m_phase1")
FIXED_QUANTITY = int(os.getenv("REPORT_FIXED_QUANTITY", "100"))
STOP_LOSS_PCT = float(os.getenv("REPORT_STOP_LOSS_PCT", "2.0"))
TAKE_PROFIT_PCT = float(os.getenv("REPORT_TAKE_PROFIT_PCT", "4.0"))
RISK_PER_TRADE_PCT = float(os.getenv("REPORT_RISK_PER_TRADE_PCT", "2.0"))
SLIPPAGE_BPS = float(os.getenv("REPORT_SLIPPAGE_BPS", "1.0"))
EXIT_POLICY = os.getenv("REPORT_EXIT_POLICY", "").strip() or None
LIMIT = (
    None
    if os.getenv("REPORT_LIMIT", "").strip().lower() in {"", "none", "all"}
    else int(os.getenv("REPORT_LIMIT", "100000"))
)
MAX_TRADE_DAYS = int(os.getenv("REPORT_MAX_TRADE_DAYS", "12"))
PARAMS = json.loads(os.getenv("REPORT_PARAMS_JSON", "{}"))
OUTPUT_ROOT = os.getenv("REPORT_OUTPUT_ROOT", "reports/trade_replays")
DATA_SOURCE = os.getenv("REPORT_DATA_SOURCE", "cache").strip().lower()


async def main() -> None:
    if DATA_SOURCE == "alpaca":
        profile = get_research_profile(RESEARCH_PROFILE)
        bars = alpaca_client.get_bars(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start=START,
            end=END or None,
            limit=LIMIT or 100000,
        )
        bars = filter_bars_for_research_profile(bars, profile)
    elif DATA_SOURCE == "cache":
        bars = await get_analysis_bars(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start=START,
            end=END or None,
            limit=LIMIT or 100000,
            research_profile=RESEARCH_PROFILE,
        )
    else:
        raise ValueError(f"Unsupported REPORT_DATA_SOURCE: {DATA_SOURCE}")
    strategy = get_strategy(STRATEGY, PARAMS or None)
    signals = strategy.generate_signals(SYMBOL, bars)
    result = run_backtest(
        strategy_name=STRATEGY,
        signals=signals,
        bars=bars,
        initial_capital=100000.0,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
        risk_per_trade_pct=RISK_PER_TRADE_PCT,
        fixed_quantity=FIXED_QUANTITY,
        slippage_bps=SLIPPAGE_BPS,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        research_profile=RESEARCH_PROFILE,
        exit_policy=EXIT_POLICY,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(OUTPUT_ROOT) / STRATEGY / timestamp
    report = write_trade_replay_report(
        strategy_name=STRATEGY,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        research_profile=RESEARCH_PROFILE,
        bars=bars,
        trades=result.trades,
        output_dir=output_dir,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
        max_trade_days=MAX_TRADE_DAYS,
    )

    print(
        json.dumps(
            {
                "strategy": report.strategy,
                "symbol": report.symbol,
                "timeframe": report.timeframe,
                "period": report.period,
                "trade_count": report.trade_count,
                "trade_day_count": report.trade_day_count,
                "exit_policy": EXIT_POLICY,
                "output_dir": str(report.output_dir.resolve()),
                "report_html": str(report.report_path.resolve()),
                "summary_csv": str(report.summary_path.resolve()),
                "charts": [str(path.resolve()) for path in report.chart_paths],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
