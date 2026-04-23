# Breakout Exit Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible exit-policy study for `brooks_breakout_pullback`, select a robustness-first winner, and promote that winner into the shared backtest and paper-trading path.

**Architecture:** Extend the shared phase1 exit layer so breakout exits are policy-aware at both entry-time and bar-by-bar management time, then reuse that same interface from backtests, research validation, replay reports, and the paper runner. Add a dedicated research script that runs a bounded set of interpretable exit variants against the same `QQQ 5m phase1` signal stream and writes a ranked study output.

**Tech Stack:** Python, FastAPI service layer, pytest, existing AL_price_action research/backtest services, local HTML/CSV replay reports.

---

### Task 1: Define Shared Breakout Exit Policy Semantics

**Files:**
- Modify: `backend/services/phase1_exit.py`
- Test: `backend/tests/test_phase1_exit.py`

- [ ] Add tests for breakout fixed-target and dynamic-protection policy behavior.
- [ ] Implement a shared breakout exit policy enum/string surface plus helper functions for initial exit plans and in-trade updates.
- [ ] Keep existing `brooks_small_pb_trend` behavior unchanged.

### Task 2: Route Exit Policies Through Backtester And Validation

**Files:**
- Modify: `backend/services/backtester.py`
- Modify: `backend/services/research_validation.py`
- Test: `backend/tests/test_backtester_intraday.py`
- Test: `backend/tests/test_research_validation.py`

- [ ] Add failing tests showing that breakout backtests can select different exit policies while keeping the same entry stream.
- [ ] Teach the backtester to apply dynamic stop tightening and discretionary exits from the shared phase1 exit layer.
- [ ] Thread the exit-policy parameter through research validation reporting.

### Task 3: Add Breakout Exit Study Runner

**Files:**
- Create: `backend/run_breakout_exit_study.py`

- [ ] Add a script that loads `QQQ 5m phase1` bars once, generates breakout signals once, runs the bounded exit-policy matrix, and writes ranked comparison output.
- [ ] Include metrics that support robustness-first selection, not just total return.

### Task 4: Promote The Winning Policy Into Paper-Trade Paths

**Files:**
- Modify: `backend/services/paper_strategy_runner.py`
- Modify: `frontend/src/components/BacktestPanel.tsx`
- Modify: `frontend/src/components/PaperStrategyPanel.tsx`
- Test: `backend/tests/test_paper_strategy_runner.py`

- [ ] Add failing tests for the selected breakout exit policy in the paper-runner path.
- [ ] Apply the same exit-policy semantics in live paper management.
- [ ] Update user-facing copy so the selected breakout exit plan is described honestly.

### Task 5: Keep Replay Reports Honest

**Files:**
- Modify: `backend/services/trade_replay_report.py`
- Modify: `backend/run_trade_replay_report.py`

- [ ] Add support for new breakout stop/target/exit reason labels in the report generator.
- [ ] Ensure the report only draws target lines when the selected policy actually has a fixed target.

### Task 6: Run The Study, Pick A Winner, And Generate Final Evidence

**Files:**
- Output under: `reports/`

- [ ] Run targeted pytest for the changed backend behavior.
- [ ] Run the breakout exit study script on the intended `QQQ 5m phase1` range.
- [ ] Inspect the ranked results and choose the winning policy by the robustness criteria from the spec.
- [ ] Generate a fresh annotated replay report for the promoted policy.
- [ ] Run the smallest honest verification set and summarize what was and was not validated.
