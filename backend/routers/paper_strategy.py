from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.alpaca_client import AlpacaNotConfiguredError
from services.paper_strategy_runner import (
    get_phase1_paper_runner_history,
    get_phase1_paper_runner_readiness,
    get_phase1_paper_runner_status,
    get_phase1_paper_runner_statuses,
    start_phase1_paper_runner,
    stop_phase1_paper_runner,
)

router = APIRouter(prefix="/api/paper-strategy", tags=["paper-strategy"])

Phase1Strategy = Literal[
    "brooks_small_pb_trend",
    "brooks_breakout_pullback",
    "brooks_pullback_count",
]


class StartPhase1PaperRequest(BaseModel):
    strategy: Phase1Strategy = "brooks_small_pb_trend"
    fixed_quantity: int = Field(100, ge=1)
    stop_loss_pct: float = Field(2.0, gt=0.0)
    take_profit_pct: float = Field(4.0, gt=0.0)
    exit_policy: Optional[str] = None
    history_days: int = Field(10, ge=3, le=12)
    params: Optional[Dict[str, Any]] = None


class StopPhase1PaperRequest(BaseModel):
    strategy: Optional[Phase1Strategy] = None


@router.get("/phase1/status")
def get_phase1_paper_strategy_status(
    strategy: Optional[Phase1Strategy] = None,
):
    return get_phase1_paper_runner_status(strategy=strategy)


@router.get("/phase1/statuses")
def get_phase1_paper_strategy_statuses():
    return get_phase1_paper_runner_statuses()


@router.get("/phase1/history")
async def get_phase1_paper_strategy_history(
    limit: int = 10,
    strategy: Optional[Phase1Strategy] = None,
):
    return await get_phase1_paper_runner_history(limit=limit, strategy=strategy)


@router.get("/phase1/readiness")
def get_phase1_paper_strategy_readiness():
    return get_phase1_paper_runner_readiness()


@router.post("/phase1/start")
async def start_phase1_paper_strategy(req: StartPhase1PaperRequest):
    try:
        return await start_phase1_paper_runner(
            strategy=req.strategy,
            fixed_quantity=req.fixed_quantity,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            exit_policy=req.exit_policy,
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
async def stop_phase1_paper_strategy(req: StopPhase1PaperRequest | None = None):
    try:
        return await stop_phase1_paper_runner(strategy=None if req is None else req.strategy)
    except AlpacaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
