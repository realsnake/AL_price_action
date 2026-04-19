from __future__ import annotations

import pytest

from routers import paper_strategy as paper_strategy_router


@pytest.mark.asyncio
async def test_start_phase1_paper_strategy_forwards_request(monkeypatch):
    captured = {}

    async def fake_start_phase1_paper_runner(**kwargs):
        captured["kwargs"] = kwargs
        return {"running": True, "symbol": "QQQ"}

    monkeypatch.setattr(
        paper_strategy_router,
        "start_phase1_paper_runner",
        fake_start_phase1_paper_runner,
    )

    req = paper_strategy_router.StartPhase1PaperRequest(
        fixed_quantity=50,
        stop_loss_pct=1.5,
        take_profit_pct=3.5,
        history_days=8,
    )

    result = await paper_strategy_router.start_phase1_paper_strategy(req)

    assert result == {"running": True, "symbol": "QQQ"}
    assert captured["kwargs"] == {
        "fixed_quantity": 50,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.5,
        "history_days": 8,
        "params": None,
    }


def test_get_phase1_paper_strategy_status(monkeypatch):
    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_status",
        lambda: {"running": True, "strategy": "brooks_small_pb_trend"},
    )

    assert paper_strategy_router.get_phase1_paper_strategy_status() == {
        "running": True,
        "strategy": "brooks_small_pb_trend",
    }


@pytest.mark.asyncio
async def test_get_phase1_paper_strategy_history(monkeypatch):
    captured = {}

    async def fake_get_phase1_paper_runner_history(limit: int = 10):
        captured["limit"] = limit
        return [{"id": 1, "symbol": "QQQ"}]

    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_history",
        fake_get_phase1_paper_runner_history,
    )

    result = await paper_strategy_router.get_phase1_paper_strategy_history(limit=7)

    assert result == [{"id": 1, "symbol": "QQQ"}]
    assert captured["limit"] == 7
