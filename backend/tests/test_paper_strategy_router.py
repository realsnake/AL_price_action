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
        strategy="brooks_pullback_count",
        fixed_quantity=50,
        stop_loss_pct=1.5,
        take_profit_pct=3.5,
        exit_policy="pullback_count_swing_ema_after_1r",
        history_days=8,
    )

    result = await paper_strategy_router.start_phase1_paper_strategy(req)

    assert result == {"running": True, "symbol": "QQQ"}
    assert captured["kwargs"] == {
        "strategy": "brooks_pullback_count",
        "fixed_quantity": 50,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.5,
        "exit_policy": "pullback_count_swing_ema_after_1r",
        "history_days": 8,
        "params": None,
    }


def test_get_phase1_paper_strategy_status(monkeypatch):
    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_status",
        lambda strategy=None: {"running": True, "strategy": "brooks_small_pb_trend"},
    )

    assert paper_strategy_router.get_phase1_paper_strategy_status() == {
        "running": True,
        "strategy": "brooks_small_pb_trend",
    }


def test_get_phase1_paper_strategy_statuses(monkeypatch):
    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_statuses",
        lambda: [
            {"running": True, "strategy": "brooks_small_pb_trend"},
            {"running": False, "strategy": "brooks_breakout_pullback"},
        ],
    )

    assert paper_strategy_router.get_phase1_paper_strategy_statuses() == [
        {"running": True, "strategy": "brooks_small_pb_trend"},
        {"running": False, "strategy": "brooks_breakout_pullback"},
    ]


@pytest.mark.asyncio
async def test_get_phase1_paper_strategy_history(monkeypatch):
    captured = {}

    async def fake_get_phase1_paper_runner_history(
        limit: int = 10,
        strategy: str | None = None,
    ):
        captured["limit"] = limit
        captured["strategy"] = strategy
        return [{"id": 1, "symbol": "QQQ"}]

    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_history",
        fake_get_phase1_paper_runner_history,
    )

    result = await paper_strategy_router.get_phase1_paper_strategy_history(limit=7)

    assert result == [{"id": 1, "symbol": "QQQ"}]
    assert captured["limit"] == 7
    assert captured["strategy"] is None


def test_get_phase1_paper_strategy_readiness(monkeypatch):
    monkeypatch.setattr(
        paper_strategy_router,
        "get_phase1_paper_runner_readiness",
        lambda: {"ready": True, "account_status": "ok"},
    )

    assert paper_strategy_router.get_phase1_paper_strategy_readiness() == {
        "ready": True,
        "account_status": "ok",
    }


@pytest.mark.asyncio
async def test_stop_phase1_paper_strategy_forwards_strategy(monkeypatch):
    captured = {}

    async def fake_stop_phase1_paper_runner(strategy=None, close_position=True):
        captured["strategy"] = strategy
        captured["close_position"] = close_position
        return {"running": False, "strategy": strategy}

    monkeypatch.setattr(
        paper_strategy_router,
        "stop_phase1_paper_runner",
        fake_stop_phase1_paper_runner,
    )

    req = paper_strategy_router.StopPhase1PaperRequest(
        strategy="brooks_breakout_pullback",
    )

    result = await paper_strategy_router.stop_phase1_paper_strategy(req)

    assert result == {"running": False, "strategy": "brooks_breakout_pullback"}
    assert captured == {
        "strategy": "brooks_breakout_pullback",
        "close_position": True,
    }
