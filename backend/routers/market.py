from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client
from services.analysis_bars import get_analysis_bars

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    timeframe: str = Query("1D", regex="^(1m|5m|15m|1h|1D)$"),
    start: str = Query(..., description="Start date ISO format, e.g. 2024-01-01"),
    end: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    research_profile: Optional[str] = Query(None),
):
    try:
        bars = await get_analysis_bars(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
            research_profile=research_profile,
        )
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"symbol": symbol, "timeframe": timeframe, "bars": bars}


@router.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        return alpaca_client.get_quote(symbol)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
