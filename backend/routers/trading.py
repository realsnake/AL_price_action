from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.alpaca_client import alpaca_client
from services.trade_executor import execute_order, get_trade_history

router = APIRouter(prefix="/api/trading", tags=["trading"])


class OrderRequest(BaseModel):
    symbol: str
    qty: int
    side: str  # "buy" or "sell"


@router.get("/account")
def get_account():
    return alpaca_client.get_account()


@router.get("/positions")
def get_positions():
    return alpaca_client.get_positions()


@router.get("/orders")
def get_orders(status: str = "open"):
    return alpaca_client.get_orders(status)


@router.post("/order")
async def submit_order(req: OrderRequest):
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if req.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    return await execute_order(req.symbol, req.qty, req.side)


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    try:
        alpaca_client.cancel_order(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/history")
async def trade_history(limit: int = 50):
    return await get_trade_history(limit)
