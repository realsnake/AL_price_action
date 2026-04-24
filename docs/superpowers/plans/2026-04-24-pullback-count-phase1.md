# Pullback Count Phase1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `brooks_pullback_count` research-complete for `QQQ 5m qqq_5m_phase1`, with a gate-passing exit policy, annotated replay report, and paper runner support.

**Architecture:** Keep the existing strategy/backtester/replay architecture. Add pullback-count-specific signal filters and exit policies in the same places that already support breakout and small-pullback phase1 behavior.

**Tech Stack:** FastAPI backend services, Brooks strategy registry, SQLite cached bars, pytest, React/Vite frontend.

---

### Task 1: Signal Quality

**Files:**
- Modify: `backend/strategies/brooks_price_action.py`
- Test: `backend/tests/test_brooks_pullback_count.py`

- [x] Add failing tests showing H2 buy detection after a pullback, and rejecting entries below session open or below VWAP buffer.
- [x] Run `cd backend && .venv/bin/python -m pytest tests/test_brooks_pullback_count.py -q` and confirm the tests fail.
- [x] Fix `PullbackCountStrategy.generate_signals()` so it uses the previous pullback state before overwriting it, and add phase1-compatible quality filters.
- [x] Re-run the targeted tests and confirm they pass.

### Task 2: Pullback Count Exit Policies

**Files:**
- Modify: `backend/services/phase1_exit.py`
- Modify: `backend/services/backtester.py` only if the existing dynamic update API is insufficient
- Test: `backend/tests/test_phase1_exit.py`
- Test: `backend/tests/test_backtester_intraday.py`

- [x] Add failing tests for structural pullback-count stops and selected candidate targets.
- [x] Add failing tests for dynamic break-even and pullback-low stop tightening.
- [x] Implement pullback-count policy constants, default resolution, structural stop calculation, fixed R targets, and dynamic stop updates.
- [x] Run targeted exit/backtester tests and confirm they pass.

### Task 3: Study And Replay

**Files:**
- Modify: `backend/run_breakout_exit_study.py`
- Modify: `backend/run_trade_replay_report.py`
- Modify: `backend/services/trade_replay_report.py`
- Test: `backend/tests/test_trade_replay_report.py`

- [x] Make the exit-study runner choose policy sets and labels by strategy.
- [x] Add Chinese replay reason text for pullback-count entries, stops, targets, and dynamic updates.
- [x] Run the study for `brooks_pullback_count` and select only a recent-gate-passing winner.
- [x] Generate a replay report for the selected winner under `reports/trade_replays/brooks_pullback_count`.

### Task 4: Paper Runner And Frontend

**Files:**
- Modify: `backend/services/paper_strategy_runner.py`
- Modify: `backend/routers/paper_strategy.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/PaperStrategyPanel.tsx`
- Test: `backend/tests/test_paper_strategy_runner.py`
- Test: `backend/tests/test_paper_strategy_router.py`

- [x] Add `brooks_pullback_count` to supported phase1 strategies only after the study has a winner.
- [x] Verify the runner passes the selected exit policy through `build_exit_plan()` and `build_dynamic_exit_update()`.
- [x] Add frontend selection/copy for pullback count.
- [x] Run backend runner/router tests, frontend lint, and frontend build.

### Task 5: Final Verification

**Files:**
- No production file changes expected.

- [x] Run `cd backend && .venv/bin/python -m pytest -q`.
- [x] Run `PYTHONPYCACHEPREFIX=/tmp/codex_pycache python3 -m compileall -q backend/main.py backend/config.py backend/database.py backend/models.py backend/routers backend/services backend/strategies backend/tests`.
- [x] Run `cd frontend && PATH=/Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH ./node_modules/.bin/eslint .`.
- [x] Run `cd frontend && PATH=/Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH ./node_modules/.bin/vite build`.
- [x] Commit and push the completed branch.
