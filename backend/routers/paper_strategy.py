from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.alpaca_client import AlpacaNotConfiguredError
from services.paper_strategy_runner import (
    get_phase1_paper_runner_status,
    start_phase1_paper_runner,
    stop_phase1_paper_runner,
)

router = APIRouter(prefix="/api/paper-strategy", tags=["paper-strategy"])


class StartPhase1PaperRequest(BaseModel):
    fixed_quantity: int = Field(100, ge=1)
    stop_loss_pct: float = Field(2.0, gt=0.0)
    take_profit_pct: float = Field(4.0, gt=0.0)
    history_days: int = Field(10, ge=3, le=12)
    params: Optional[Dict[str, Any]] = None


@router.get("/phase1/status")
def get_phase1_paper_strategy_status():
    return get_phase1_paper_runner_status()


@router.post("/phase1/start")
async def start_phase1_paper_strategy(req: StartPhase1PaperRequest):
    try:
        return await start_phase1_paper_runner(
            fixed_quantity=req.fixed_quantity,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            history_days=req.history_days,
            params=req.params,
        )
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/phase1/stop")
async def stop_phase1_paper_strategy():
    try:
        return await stop_phase1_paper_runner()
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
