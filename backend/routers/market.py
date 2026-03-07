from typing import Optional

from fastapi import APIRouter, Query

from services.alpaca_client import alpaca_client
from services.bars_cache import get_bars_with_cache

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    timeframe: str = Query("1D", regex="^(1m|5m|15m|1h|1D)$"),
    start: str = Query(..., description="Start date ISO format, e.g. 2024-01-01"),
    end: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    bars = await get_bars_with_cache(symbol, timeframe, start, end, limit)
    return {"symbol": symbol, "timeframe": timeframe, "bars": bars}


@router.get("/quote/{symbol}")
def get_quote(symbol: str):
    return alpaca_client.get_quote(symbol)
