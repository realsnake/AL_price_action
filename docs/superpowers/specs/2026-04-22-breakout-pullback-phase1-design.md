# Breakout Pullback Phase1 Design

Date: 2026-04-22

## Context

`brooks_breakout_pullback` is the first intended `QQQ 5m` phase1 validation target, but the live code has two gaps that block honest promotion into paper trading:

- cached-bar timestamps and strategy signal timestamps do not currently line up reliably in real research flows, so backtests and validation summaries can silently drop valid signals
- the current breakout-pullback definition is still generic and does not yet express a `QQQ 5m phase1` continuation-quality filter or a breakout-specific execution model

At the same time, the existing phase1 paper runner is hard-wired to `brooks_small_pb_trend`, so even a validated breakout-pullback variant cannot currently graduate into the paper-trading path.

## Goal

Take `brooks_breakout_pullback` all the way from trustworthy `QQQ 5m phase1` research to a paper-trade-ready phase1 runner path in one continuous rollout.

## Constraints

- Keep the existing phase1 universe: `QQQ`, `5m`, RTH only, long-only, intraday flat
- Fix timestamp alignment at the shared plumbing level rather than by patching one UI path
- Treat signal definition and exit definition as separate levers, but do not stop before both are good enough for paper trading
- Prefer strategy rules that are explainable in Brooks terms over opaque score blends

## Approach

### 1. Repair the research and backtest substrate

Normalize cached timestamps into one canonical UTC string format and make both backtest execution and research validation compare canonical timestamps rather than raw strings. This makes cached historical bars, Alpaca bars, generated signals, and validation windows behave consistently.

### 2. Re-express breakout pullback for phase1

Keep the core pattern recognizable:

- strong bull breakout above a recent range high
- a pullback that proves the breakout is holding, not collapsing
- a bull resumption bar that confirms buyers are defending the breakout

Then add only interpretable quality filters where research justifies them:

- trend context via rising EMA
- continuation quality via session-open and VWAP relationship
- tighter pullback structure relative to the breakout bar
- breakout-specific structural stop logic rather than the current generic percentage stop

### 3. Make paper-trade promotion a real gate

Use the same validated breakout-pullback rules in:

- strategy scan behavior
- backtest execution
- research validation summaries
- phase1 paper runner entry and exit planning

The paper runner should become strategy-selectable within the validated phase1 set rather than remaining permanently bound to `brooks_small_pb_trend`.

## Exit Design Direction

Breakout-pullback trades should not keep the current generic `2% / 4%` phase1 defaults once promoted. For intraday `QQQ 5m`, a breakout setup is better represented by:

- initial stop below the defended pullback low or breakout support shelf
- optional target as a simple measured move or no fixed target when a better session-management rule wins in research
- explicit day-flat behavior preserved

The exact breakout exit should be chosen from research evidence, not mirrored mechanically from `small_pb_trend`.

## Paper-Trade Readiness Criteria

The breakout-pullback variant is paper-trade ready only when all of the following are true:

- timestamp alignment bugs are covered by regression tests
- real `QQQ 5m phase1` research reports show non-zero, correctly attributed signals and trades
- the selected breakout definition and exit plan meet the repo's promotion intent closely enough to justify paper exposure
- the paper runner can trade this strategy without introducing strategy-specific contract drift between backtest and live-paper logic

## Expected Files

- `backend/services/bars_cache.py`
- `backend/services/backtester.py`
- `backend/services/research_validation.py`
- `backend/services/phase1_exit.py`
- `backend/services/paper_strategy_runner.py`
- `backend/routers/paper_strategy.py`
- `backend/tests/test_backtester_intraday.py`
- `backend/tests/test_research_validation.py`
- `backend/tests/test_brooks_breakout_pullback.py`
- `backend/tests/test_phase1_exit.py`
- `backend/tests/test_paper_strategy_runner.py`
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/components/PaperStrategyPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`
