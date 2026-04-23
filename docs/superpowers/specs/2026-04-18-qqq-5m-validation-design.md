# QQQ 5-Minute Validation Design

Date: 2026-04-18

## Context

The current repository can already fetch and cache stock bars, run Brooks strategies, and display backtest results, but the active workflow is still biased toward daily-bar research:

- [backtester.py](/Users/bytedance/personalProject/AL_price_action/backend/services/backtester.py) matches signals to bars by date instead of exact intraday timestamp, which is not acceptable for `5m` research.
- [BacktestPanel.tsx](/Users/bytedance/personalProject/AL_price_action/frontend/src/components/BacktestPanel.tsx) currently hardcodes `timeframe: "1D"` in both single-run and run-all flows.
- The Brooks catalog contains many setups, but several are heavily tied to open-gap context or symmetric long/short assumptions, which would make the first research pass harder to interpret.

The user wants a narrower, more honest research program:

- only `QQQ`
- only `5m`
- only regular trading hours
- only `long-only`
- only day trades with no overnight risk
- a workflow where every optimization is explained and reviewed rather than silently curve-fit

## Goal

Create a disciplined first-stage validation framework for `QQQ 5m` Brooks-style trading so the project can answer three questions in order:

1. Is the backtest engine trustworthy enough for intraday research?
2. Do the first selected strategy expressions show any edge after realistic constraints?
3. If they do, which changes are justified by evidence rather than hindsight fitting?

This design is for validation workflow, not yet for autonomous live trading.

## User-Approved Decisions

- Trade only `QQQ`.
- Trade only `5m`.
- Restrict research to regular trading hours, defined as `9:30 a.m. - 4:00 p.m. ET`.
- Use `long-only` for the first stage.
- Close all positions intraday and carry no overnight exposure.
- Review every optimization step together with explicit reasons.

## Options Considered

### Option 1: Validate many Brooks setups at once

Run a broad cross-section of trend, range, reversal, and opening-pattern strategies in parallel.

Pros:

- fast coverage of the full catalog
- more immediate leaderboard output

Cons:

- makes failures hard to diagnose
- encourages post-hoc picking of the best curve
- mixes strategy quality with engine quality and regime mismatch

### Option 2: Trend-first validation ladder

Start with a small set of the most mechanical long-side trend-continuation setups, then expand only if the engine and baseline results justify it.

Pros:

- easiest to reason about on `QQQ 5m`
- best fit for `long-only`
- failures are easier to attribute

Cons:

- fewer trades in the first pass
- may miss some range-day opportunities

### Option 3: Reversal-first validation

Start with second-entry, failed-breakout, and two-bar reversal setups because they can produce more signals quickly.

Pros:

- larger sample counts early
- may find tactical edges faster

Cons:

- more subjective pattern expression
- easier to confuse dip-buying noise with durable edge
- worse fit for a first `long-only` pass

## Decision

Choose Option 2.

The first-stage program should optimize for interpretability, not coverage. On `QQQ 5m`, a trend-first ladder is the cleanest way to test whether the repo can express Brooks-style continuation setups without immediately drowning in ambiguity.

## Phase 1 Scope

### Trading universe

- Symbol: `QQQ`
- Timeframe: `5m`
- Session: regular trading hours only
- Direction: `long-only`
- Positioning: one position at a time
- Carry: no overnight positions

### Baseline session rules

- Bars outside `9:30 a.m. - 4:00 p.m. ET` are excluded from signal generation and execution.
- New entries are not allowed on the first two `5m` bars of the session.
- New entries are not allowed after `3:30 p.m. ET`.
- Any open position is force-closed on the `3:55 p.m. - 4:00 p.m. ET` bar of the same session.

These rules intentionally remove the noisiest opening bars and the end-of-day carry problem without yet introducing a midday filter.

### Baseline execution rules

- Long entries only
- No pyramiding
- No immediate reversal into a new trade on the same bar
- Position sizing remains risk-based, but must respect the long-only day-trade constraint
- Initial research uses simple, explicit exits so engine correctness can be judged before exit optimization

## Strategy Validation Order

### 1. `brooks_breakout_pullback`

This is the first validation target.

Reason:

- most mechanically expressible of the chosen set
- strong fit for `QQQ` intraday continuation behavior
- easiest starting point for separating trend-following signal quality from engine defects

### 2. `brooks_pullback_count`

This is the second validation target.

Reason:

- closer to Brooks language, especially H1/H2 continuation logic
- still compatible with `long-only`
- slightly more sensitive to implementation interpretation, so it belongs after the first strategy

### 3. `brooks_small_pb_trend`

This is the third validation target.

Reason:

- high-quality continuation concept when momentum is unusually strong
- fewer signals, so it is better used after the first two strategies establish whether the research loop is behaving sensibly

## Explicitly Deferred From Phase 1

The following are intentionally not part of the first pass:

- `brooks_trend_from_open`
- `brooks_gap_bar`
- `brooks_second_entry`
- `brooks_failed_breakout`
- `brooks_two_bar_reversal`

Reasons:

- open-gap setups add opening-session complexity too early
- reversal and range setups are harder to encode and easier to overfit
- the first stage should prove that the engine and continuation logic are sound before expanding the surface area

## Engine Fixes Required Before Strategy Judgement

Before any strategy result is treated as meaningful, the following issues must be fixed or explicitly ruled out:

### 1. Exact intraday signal-to-bar alignment

Current code in [backtester.py](/Users/bytedance/personalProject/AL_price_action/backend/services/backtester.py) maps signals to the first bar with the same date. That is acceptable for daily bars but invalid for `5m` research.

Requirement:

- signals must align to exact intraday timestamps, not calendar date only

### 2. Long-only and day-flat enforcement

Current backtest logic supports both long and short entries and only flattens at the end of the entire dataset.

Requirements:

- reject or ignore short signals in phase 1
- force-close any open trade on the final valid bar of each regular-hours session

### 3. Session filtering

The research program needs a consistent regular-hours boundary.

Requirements:

- execution bars must be filtered to regular hours
- the strategy engine must see the same filtered bars that the backtester executes on

### 4. UI and API contract alignment

The current backtest UI is daily-oriented.

Requirements:

- backtest requests must support `QQQ 5m` as the explicit first-class path
- the frontend should not keep sending `1D` when the program has switched to intraday validation

### 5. Conservative bar-based execution semantics

Intraday bar backtests cannot know full intra-bar path ordering.

Requirement:

- use explicit, documented assumptions for entry, stop, target, and forced close behavior, and keep those assumptions stable until deliberately changed

## Failure Triage Model

Every weak or unstable result must first be classified before anything is optimized.

### A. Engine problem

Examples:

- impossible entry or exit timestamps
- same-bar behavior that violates the defined execution model
- overnight carry despite day-flat rules
- signal alignment mismatch

Action:

- fix engine behavior before touching strategy logic

### B. Strategy expression problem

Examples:

- coded setup does not match intended Brooks concept
- signal density is obviously too high for a supposedly selective setup
- visually strong trend cases are being missed or inverted

Action:

- refine the coded pattern definition while keeping the engine fixed

### C. Market-fit problem

Examples:

- the setup remains unstable across months after engine and expression are cleaned up
- results disappear when simple costs are applied
- returns depend on a tiny handful of sessions

Action:

- document the mismatch and either defer the setup or narrow the allowed context later

## Optimization Rules

Optimization is allowed, but it must be constrained.

### One change at a time

Each iteration may change only one class of behavior:

- engine logic
- setup definition
- context filter
- risk rule
- exit rule

### Every iteration must record

- observed problem
- diagnosis category
- single intended change
- reason for the change
- expected effect
- measured result after the change
- keep/revert/defer decision

### Optimization order

1. engine correctness
2. baseline strategy expression
3. minimal context filters
4. exit refinement

This order is meant to prevent curve-fitting under the label of "cleanup."

## Allowed Context Filters In Early Iterations

The first implementation should stay sparse. If baseline continuation logic is noisy, add filters in this order:

1. 20 EMA slope or directional bias
2. require price above intraday VWAP for long entries
3. time-of-day filter, especially midday exclusion

No broader filter stack should be introduced until each earlier filter has been tested and justified on its own.

## Evaluation Metrics

The first stage should not optimize for win rate.

Primary metrics:

- trade count
- expectancy per trade
- profit factor
- max drawdown
- return stability across time slices
- time-of-day distribution of results

Secondary metrics:

- win rate
- Sharpe ratio
- average hold time

## Baseline Cost Model

The first phase should apply one fixed research cost model and keep it stable across iterations:

- `2` basis points at entry
- `2` basis points at exit

This is a simple `4` basis-point round-trip haircut, not a claim about exact live fills. Its job is to stop obviously fragile backtests from graduating just because gross results look attractive.

## Promotion Criteria For Paper Trading

The strategy does not move to paper trading just because one backtest looks attractive.

Minimum gate:

- engine constraints above are implemented and verified
- at least `100` in-sample trades across the baseline research window
- positive expectancy after applying the fixed `4` basis-point round-trip cost model above
- profit factor of at least `1.20` before paper
- no single calendar month contributes more than `40%` of cumulative net profit
- at least `2` out of `3` chronological out-of-sample slices remain profitable

If these conditions are not met, the result stays in research and does not move forward.

## Price Action Learning Scope

Additional Brooks study is useful, but it should stay tightly tied to the first three setups.

Priority study topics:

1. breakout pullback quality and failure cases
2. H1/H2 continuation context in trends
3. what qualifies as a true small-pullback trend versus ordinary drift

The goal of study is not to collect more terminology. It is to make the coded rules more faithful and more falsifiable.

## Files Expected To Change

- `backend/services/backtester.py`
- `backend/services/analysis_bars.py`
- `backend/routers/backtest.py`
- `backend/routers/strategy.py`
- `backend/tests/test_backtest_router.py`
- new targeted backtester tests for `5m`, long-only, and day-flat behavior
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`

Additional frontend files may change if the chart and controls need clearer intraday research handling, but scope should stay tight.

## Verification

Minimum verification for implementation that follows this spec:

- `PYTHONPYCACHEPREFIX=/tmp/codex_pycache python3 -m compileall -q backend`
- targeted backend tests for intraday backtest semantics
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- manual smoke of `QQQ 5m` backtest from the UI

## Non-Goals

- live automation or unattended execution
- crypto support
- multi-symbol portfolio optimization
- short-selling in phase 1
- opening-gap specialist strategies in phase 1
- broad parameter sweep tooling before the baseline loop proves useful

## Success Criteria

This design is successful when the repo can support a clean first-stage research loop for `QQQ 5m` such that:

- intraday backtests are technically trustworthy enough to compare iterations
- the first three strategies can be tested in a fixed order under consistent constraints
- every optimization step has a written reason and result
- the project can clearly distinguish engine flaws from strategy flaws from market-fit flaws
- moving to paper trading becomes a gated decision rather than a hunch
