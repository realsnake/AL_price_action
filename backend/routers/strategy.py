from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.analysis_bars import DEFAULT_ANALYSIS_BAR_LIMIT, get_analysis_bars
from services.strategy_engine import list_strategies, run_strategy

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class RunStrategyRequest(BaseModel):
    name: str
    symbol: str
    timeframe: str = "1D"
    start: str = "2024-01-01"
    end: Optional[str] = None
    limit: int = Field(DEFAULT_ANALYSIS_BAR_LIMIT, ge=1, le=1000)
    params: Optional[Dict[str, Any]] = None


@router.get("/list")
def get_strategies():
    return list_strategies()


@router.post("/signals")
async def get_signals(req: RunStrategyRequest):
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

        signals = run_strategy(req.name, symbol, bars, req.params)
        return {"strategy": req.name, "symbol": symbol, "signals": signals}
    except ValueError as e:
        raise HTTPException(400, str(e))
