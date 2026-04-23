# Breakout Pullback Phase1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair phase1 timestamp alignment, make `brooks_breakout_pullback` research-valid on `QQQ 5m`, and promote the validated strategy into the phase1 paper-trading path.

**Architecture:** First fix canonical timestamp handling at the shared historical-bar and validation layers so cached and live-like flows agree. Then tighten breakout-pullback signal and exit logic under test, verify the chosen rule set against real `QQQ 5m` research output, and finally make the phase1 paper runner strategy-selectable so the same breakout logic can execute in paper trading.

**Tech Stack:** FastAPI, Python services, SQLAlchemy/SQLite cache, React + TypeScript frontend, pytest

---

### Task 1: Timestamp Alignment Floor

**Files:**
- Modify: `backend/services/bars_cache.py`
- Modify: `backend/services/backtester.py`
- Modify: `backend/services/research_validation.py`
- Test: `backend/tests/test_backtester_intraday.py`
- Test: `backend/tests/test_research_validation.py`

- [ ] Add failing tests that use cached-style timestamps with `.000000+00:00` and prove that both backtest execution and research validation currently drop otherwise valid signals.
- [ ] Run the targeted pytest cases and confirm they fail for timestamp-mismatch reasons instead of unrelated errors.
- [ ] Add one canonical timestamp helper path and use it consistently in cached-bar serialization plus backtest/validation comparisons.
- [ ] Re-run the targeted pytest cases until they pass.

### Task 2: Breakout Signal Definition

**Files:**
- Modify: `backend/strategies/brooks_price_action.py`
- Test: `backend/tests/test_brooks_breakout_pullback.py`

- [ ] Add failing tests for the intended phase1 breakout behavior: accept defended bull breakouts in trend context and reject weak or broken pullbacks.
- [ ] Run those strategy tests and verify they fail against the current generic implementation.
- [ ] Tighten `brooks_breakout_pullback` with the minimum explainable `QQQ 5m` quality filters needed by the tests.
- [ ] Re-run the strategy tests until they pass.

### Task 3: Breakout Exit Model

**Files:**
- Modify: `backend/services/phase1_exit.py`
- Modify: `backend/services/backtester.py`
- Test: `backend/tests/test_backtester_intraday.py`
- Test: `backend/tests/test_phase1_exit.py`

- [ ] Add failing tests for breakout-specific exit planning and backtest behavior.
- [ ] Run the new exit-focused tests and confirm the current generic percentage-based behavior fails them.
- [ ] Implement the minimal breakout-specific exit plan that the tests describe.
- [ ] Re-run the exit tests until they pass.

### Task 4: Research Validation Evidence

**Files:**
- Modify: `backend/services/research_validation.py`
- Modify: `backend/run_research_validation.py` only if the reporting surface needs small truth-preserving adjustments
- Test: `backend/tests/test_research_validation.py`

- [ ] Add or extend tests so validation summaries keep breakout trades, exit reasons, and time-slice accounting after the timestamp fix.
- [ ] Run the validation tests and confirm they fail before the code change if the behavior is not already covered.
- [ ] Implement the smallest reporting updates needed for breakout promotion evidence.
- [ ] Re-run the validation tests until they pass.

### Task 5: Phase1 Paper Runner Promotion

**Files:**
- Modify: `backend/services/paper_strategy_runner.py`
- Modify: `backend/routers/paper_strategy.py`
- Modify: `backend/tests/test_paper_strategy_runner.py`
- Modify: `backend/tests/test_paper_strategy_router.py`
- Modify: `frontend/src/components/PaperStrategyPanel.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] Add failing backend tests that prove the current phase1 runner is incorrectly fixed to `brooks_small_pb_trend`.
- [ ] Run those runner tests and confirm they fail for strategy-selection reasons.
- [ ] Generalize the phase1 runner so it can run the validated breakout-pullback strategy without breaking the existing runner contract.
- [ ] Update the router and frontend contract only as much as needed to expose the selected phase1 strategy cleanly.
- [ ] Re-run the backend runner/router tests and any touched frontend type checks until they pass.

### Task 6: Promotion Verification

**Files:**
- No new production files required unless research output reveals a final small correction

- [ ] Run focused pytest coverage for breakout strategy, backtester intraday semantics, validation, phase1 exits, and paper runner behavior.
- [ ] Run real `QQQ 5m phase1` research output for the chosen breakout variant and inspect promotion metrics honestly.
- [ ] Run backend compile verification plus frontend lint/build if any frontend contract or panel changed.
- [ ] Summarize what is now paper-trade ready, what real-data evidence supports that claim, and any remaining environment-dependent checks.
