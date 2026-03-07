from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.strategy_engine import list_strategies, run_strategy
from services.alpaca_client import alpaca_client

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class RunStrategyRequest(BaseModel):
    name: str
    symbol: str
    timeframe: str = "1D"
    start: str = "2024-01-01"
    params: Optional[Dict[str, Any]] = None


@router.get("/list")
def get_strategies():
    return list_strategies()


@router.post("/signals")
def get_signals(req: RunStrategyRequest):
    try:
        bars = alpaca_client.get_bars(req.symbol, req.timeframe, req.start)
        signals = run_strategy(req.name, req.symbol, bars, req.params)
        return {"strategy": req.name, "symbol": req.symbol, "signals": signals}
    except ValueError as e:
        raise HTTPException(400, str(e))
