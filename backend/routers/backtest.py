from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.analysis_bars import (
    DEFAULT_ANALYSIS_BAR_LIMIT,
    MAX_ANALYSIS_BAR_LIMIT,
    get_analysis_bars,
)
from services.strategy_engine import run_strategy, get_strategy
from services.backtester import run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "QQQ"
    timeframe: str = "1D"
    start: str = "2025-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=MAX_ANALYSIS_BAR_LIMIT)
    params: Optional[Dict[str, Any]] = None
    initial_capital: float = 100000.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    risk_per_trade_pct: float = 2.0


@router.post("/run")
async def run_backtest_api(req: BacktestRequest):
    try:
        symbol = req.symbol.upper()
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            limit=req.limit,
        )
        if not bars:
            raise HTTPException(400, "No bar data returned")

        strategy = get_strategy(req.strategy, req.params)
        signals = strategy.generate_signals(symbol, bars)

        result = run_backtest(
            strategy_name=req.strategy,
            signals=signals,
            bars=bars,
            initial_capital=req.initial_capital,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            risk_per_trade_pct=req.risk_per_trade_pct,
            symbol=symbol,
            timeframe=req.timeframe,
        )
        return result.to_dict()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Backtest failed: {str(e)}")
