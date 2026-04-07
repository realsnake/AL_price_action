from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.alpaca_client import AlpacaNotConfiguredError, alpaca_client
from services.trade_executor import execute_order, get_trade_history

router = APIRouter(prefix="/api/trading", tags=["trading"])


class OrderRequest(BaseModel):
    symbol: str
    qty: int
    side: str  # "buy" or "sell"


@router.get("/account")
def get_account():
    try:
        return alpaca_client.get_account()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/positions")
def get_positions():
    try:
        return alpaca_client.get_positions()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders")
def get_orders(status: str = "open"):
    try:
        return alpaca_client.get_orders(status)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/order")
async def submit_order(req: OrderRequest):
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if req.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    try:
        return await execute_order(req.symbol, req.qty, req.side)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    try:
        alpaca_client.cancel_order(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/history")
async def trade_history(limit: int = 50):
    return await get_trade_history(limit)
