"""Fetch QQQ & SPY daily bars from 2024-01-01 to now, cache to DB, and run all strategy backtests."""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import init_db
from services.bars_cache import get_bars_with_cache
from services.strategy_engine import get_strategy, list_strategies
from services.backtester import run_backtest


SYMBOLS = ["QQQ", "SPY"]
TIMEFRAME = "1D"
START = "2024-01-01"
STRATEGIES = ["ma_crossover", "rsi", "macd"]


async def main():
    await init_db()

    for symbol in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"  Fetching {symbol} daily bars from {START} ...")
        print(f"{'='*60}")

        bars = await get_bars_with_cache(symbol, TIMEFRAME, START, limit=2000)
        print(f"  Loaded {len(bars)} bars  ({bars[0]['time'][:10]} ~ {bars[-1]['time'][:10]})")

        for strat_name in STRATEGIES:
            print(f"\n  --- Strategy: {strat_name} ---")
            strategy = get_strategy(strat_name)
            signals = strategy.generate_signals(symbol, bars)
            print(f"  Signals generated: {len(signals)}")

            result = run_backtest(
                strategy_name=strat_name,
                signals=signals,
                bars=bars,
                initial_capital=100000.0,
                stop_loss_pct=2.0,
                take_profit_pct=4.0,
                risk_per_trade_pct=2.0,
                symbol=symbol,
                timeframe=TIMEFRAME,
            )

            r = result.to_dict()
            print(f"  Period:         {r['period']}")
            print(f"  Initial:        ${r['initial_capital']:,.2f}")
            print(f"  Final:          ${r['final_capital']:,.2f}")
            print(f"  Total Return:   ${r['total_return']:,.2f} ({r['total_return_pct']:.2f}%)")
            print(f"  Total Trades:   {r['total_trades']}")
            print(f"  Win Rate:       {r['win_rate']:.1f}%")
            print(f"  Avg Win:        ${r['avg_win']:,.2f}")
            print(f"  Avg Loss:       ${r['avg_loss']:,.2f}")
            print(f"  Profit Factor:  {r['profit_factor']:.2f}")
            print(f"  Max Drawdown:   ${r['max_drawdown']:,.2f} ({r['max_drawdown_pct']:.2f}%)")
            print(f"  Sharpe Ratio:   {r['sharpe_ratio']:.2f}")

            if r['trades']:
                print(f"\n  Last 5 trades:")
                for t in r['trades'][-5:]:
                    pnl_sign = "+" if t['pnl'] >= 0 else ""
                    print(f"    {t['side']:5s} {t['entry_time'][:10]} -> {t['exit_time'][:10]}  "
                          f"${t['entry_price']:.2f} -> ${t['exit_price']:.2f}  "
                          f"{pnl_sign}${t['pnl']:.2f} ({t['exit_reason']})")

    print(f"\n{'='*60}")
    print("  All backtests complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
