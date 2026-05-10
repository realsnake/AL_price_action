from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.alpaca_client import AlpacaNotConfiguredError
from services.broker_client import broker_client
from services.ibkr_client import IBKRNotConfiguredError, IBKRSafetyError
from services.trade_executor import execute_order, get_trade_history

router = APIRouter(prefix="/api/trading", tags=["trading"])


class OrderRequest(BaseModel):
    symbol: str
    qty: int
    side: str  # "buy" or "sell"
    order_type: str = "market"
    limit_price: float | None = Field(None, gt=0)
    confirm_live: bool = False


def _broker_unavailable_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Broker unavailable: {exc}")


@router.get("/account")
def get_account():
    try:
        return broker_client.get_account()
    except (AlpacaNotConfiguredError, IBKRNotConfiguredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise _broker_unavailable_http_error(exc) from exc


@router.get("/positions")
def get_positions():
    try:
        return broker_client.get_positions()
    except (AlpacaNotConfiguredError, IBKRNotConfiguredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise _broker_unavailable_http_error(exc) from exc


@router.get("/orders")
def get_orders(status: str = "open"):
    try:
        return broker_client.get_orders(status)
    except (AlpacaNotConfiguredError, IBKRNotConfiguredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise _broker_unavailable_http_error(exc) from exc


@router.get("/broker")
def get_broker_status():
    return broker_client.status()


@router.post("/order")
async def submit_order(req: OrderRequest):
    side = req.side.lower()
    order_type = req.order_type.lower()
    if side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if order_type not in ("market", "limit"):
        raise HTTPException(400, "order_type must be 'market' or 'limit'")
    if req.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    try:
        return await execute_order(
            symbol=req.symbol.upper(),
            qty=req.qty,
            side=side,
            order_type=order_type,
            limit_price=req.limit_price,
            confirm_live=req.confirm_live,
        )
    except (AlpacaNotConfiguredError, IBKRNotConfiguredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IBKRSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    try:
        broker_client.cancel_order(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except (AlpacaNotConfiguredError, IBKRNotConfiguredError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as e:
        raise _broker_unavailable_http_error(e) from e


@router.get("/history")
async def trade_history(limit: int = 50):
    return await get_trade_history(limit)
