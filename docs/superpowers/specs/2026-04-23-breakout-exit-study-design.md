# Breakout Exit Study Design

Date: 2026-04-23

## Context

`brooks_breakout_pullback` on `QQQ 5m` under `qqq_5m_phase1` currently uses a structural stop with no fixed target and a forced session-close exit. That is internally consistent, but it is not yet the result of a systematic exit study. The repo does not currently contain reproducible research for alternative breakout exit plans such as fixed `R` targets, measured-move targets, or dynamic protective exits after the trade proves itself.

This blocks an honest claim that the strategy is fully promotion-ready for paper trading.

## Goal

Build a reproducible breakout-exit study workflow, compare a small set of interpretable exit variants on the same `QQQ 5m phase1` signal stream, choose the most paper-tradeable variant by robustness-first criteria, and wire that winning policy back into backtest, replay report, and phase1 paper-runner behavior.

## Constraints

- Keep the existing phase1 universe: `QQQ`, `5m`, RTH-only, long-only, day-flat
- Keep the existing breakout entry definition fixed during this study
- Keep the initial structural stop fixed during this study
- Compare only interpretable exit rules that can be implemented consistently in both backtest and paper trading
- Avoid broad parameter sweeps that are likely to overfit

## Robustness Criteria

The winning exit policy should be selected primarily by robustness, not raw total return alone. The comparison should emphasize:

- profit factor
- max drawdown
- positive-month ratio
- stability across rolling windows
- clarity and reproducibility of the rule in paper trading

Total return is a tie-breaker, not the primary objective.

## Candidate Exit Families

The study should compare three families of exits:

### 1. Fixed target variants

- `1.0R`
- `1.5R`
- `2.0R`
- simple measured move based on the breakout-pullback structure

These keep the initial structural stop and define a fixed profit target from entry.

### 2. No fixed target baseline

- session close only

This is the current promoted behavior and remains the control group.

### 3. Dynamic protection variants

- move stop to break-even after `1R`
- move stop to the defended pullback low after `1R` if it improves protection
- exit on confirmed swing-low / `EMA20` failure after `1R`

These variants still start from the same structural stop and only become active once the trade has demonstrated initial favorable excursion.

## Implementation Direction

The study should not fork separate backtest engines. Instead, the existing phase1 exit layer should become policy-aware so the same semantics drive:

- historical backtests
- research validation summaries
- replay reports
- phase1 paper trading

The exit layer needs to support two behaviors:

- initial plan construction at entry time
- bar-by-bar dynamic updates while a position is open

That dynamic layer should be able to:

- tighten stop prices
- set a fixed target when the policy requires one
- trigger an immediate discretionary-style exit when the policy defines one

## Research Outputs

The study should produce a reproducible artifact bundle for breakout exits, including:

- machine-readable comparison output for all candidate policies
- a human-readable summary ranking
- trade replay reports for the selected winning policy

The result should make it obvious which policy won and why.

## Promotion Rule

Do not promote a breakout exit policy into default phase1 behavior unless:

- it clearly beats or justifies itself against the session-close baseline on robustness metrics
- the rule is explainable in plain Brooks-style terms
- the same rule can be implemented in the paper runner without hidden broker-specific assumptions

## Expected Files

- `backend/services/phase1_exit.py`
- `backend/services/backtester.py`
- `backend/services/research_validation.py`
- `backend/services/paper_strategy_runner.py`
- `backend/services/trade_replay_report.py`
- `backend/run_breakout_exit_study.py`
- `backend/run_trade_replay_report.py`
- `backend/tests/test_phase1_exit.py`
- `backend/tests/test_backtester_intraday.py`
- `backend/tests/test_research_validation.py`
- `backend/tests/test_paper_strategy_runner.py`
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/components/PaperStrategyPanel.tsx`
