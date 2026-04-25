from __future__ import annotations

from dataclasses import dataclass


BREAKOUT_EXIT_POLICY_SESSION_CLOSE = "breakout_session_close"
BREAKOUT_EXIT_POLICY_TARGET_1R = "breakout_target_1r"
BREAKOUT_EXIT_POLICY_TARGET_1_5R = "breakout_target_1_5r"
BREAKOUT_EXIT_POLICY_TARGET_2R = "breakout_target_2r"
BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R = "breakout_target_2_5r_break_even_after_0_75r"
BREAKOUT_EXIT_POLICY_MEASURED_MOVE = "breakout_measured_move"
BREAKOUT_EXIT_POLICY_BREAK_EVEN_AFTER_1R = "breakout_break_even_after_1r"
BREAKOUT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R = "breakout_pullback_low_after_1r"
BREAKOUT_EXIT_POLICY_SWING_EMA_AFTER_1R = "breakout_swing_ema_after_1r"

BREAKOUT_EXIT_POLICIES = (
    BREAKOUT_EXIT_POLICY_SESSION_CLOSE,
    BREAKOUT_EXIT_POLICY_TARGET_1R,
    BREAKOUT_EXIT_POLICY_TARGET_1_5R,
    BREAKOUT_EXIT_POLICY_TARGET_2R,
    BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R,
    BREAKOUT_EXIT_POLICY_MEASURED_MOVE,
    BREAKOUT_EXIT_POLICY_BREAK_EVEN_AFTER_1R,
    BREAKOUT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R,
    BREAKOUT_EXIT_POLICY_SWING_EMA_AFTER_1R,
)

DEFAULT_BREAKOUT_EXIT_POLICY = BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R

PULLBACK_COUNT_EXIT_POLICY_SESSION_CLOSE = "pullback_count_session_close"
PULLBACK_COUNT_EXIT_POLICY_TARGET_1R = "pullback_count_target_1r"
PULLBACK_COUNT_EXIT_POLICY_TARGET_1_5R = "pullback_count_target_1_5r"
PULLBACK_COUNT_EXIT_POLICY_TARGET_2R = "pullback_count_target_2r"
PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R = "pullback_count_target_2r_break_even_after_0_75r"
PULLBACK_COUNT_EXIT_POLICY_BREAK_EVEN_AFTER_1R = "pullback_count_break_even_after_1r"
PULLBACK_COUNT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R = "pullback_count_pullback_low_after_1r"
PULLBACK_COUNT_EXIT_POLICY_SWING_EMA_AFTER_1R = "pullback_count_swing_ema_after_1r"

PULLBACK_COUNT_EXIT_POLICIES = (
    PULLBACK_COUNT_EXIT_POLICY_SESSION_CLOSE,
    PULLBACK_COUNT_EXIT_POLICY_TARGET_1R,
    PULLBACK_COUNT_EXIT_POLICY_TARGET_1_5R,
    PULLBACK_COUNT_EXIT_POLICY_TARGET_2R,
    PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R,
    PULLBACK_COUNT_EXIT_POLICY_BREAK_EVEN_AFTER_1R,
    PULLBACK_COUNT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R,
    PULLBACK_COUNT_EXIT_POLICY_SWING_EMA_AFTER_1R,
)

DEFAULT_PULLBACK_COUNT_EXIT_POLICY = PULLBACK_COUNT_EXIT_POLICY_SWING_EMA_AFTER_1R

SMALL_PB_EXIT_POLICY_SWING_EMA_AFTER_1R = "small_pb_trend_swing_ema_after_1r"


@dataclass(frozen=True)
class ExitPlan:
    stop_price: float
    target_price: float | None
    stop_reason: str
    target_reason: str | None


@dataclass(frozen=True)
class DynamicExitDecision:
    reason: str
    exit_price: float


@dataclass(frozen=True)
class DynamicExitUpdate:
    stop_price: float | None = None
    target_price: float | None = None
    stop_reason: str | None = None
    target_reason: str | None = None
    exit_reason: str | None = None
    exit_price: float | None = None


@dataclass(frozen=True)
class DynamicExitVisualization:
    policy: str
    armed: bool
    one_r_price: float
    bar_time: str
    ema20: float | None
    swing_low: float | None
    swing_low_time: str | None
    triggered: bool
    trigger_reason: str | None
    trigger_price: float | None


@dataclass(frozen=True)
class BreakoutContext:
    breakout_low: float
    breakout_high: float
    pullback_low: float
    signal_low: float
    structural_stop: float


@dataclass(frozen=True)
class PullbackCountContext:
    pullback_low: float
    signal_low: float
    structural_stop: float


def resolve_exit_policy(
    *,
    strategy_name: str,
    research_profile: str | None,
    exit_policy: str | None,
) -> str | None:
    if (
        research_profile == "qqq_5m_phase1"
        and strategy_name == "brooks_breakout_pullback"
    ):
        return exit_policy or DEFAULT_BREAKOUT_EXIT_POLICY
    if (
        research_profile == "qqq_5m_phase1"
        and strategy_name == "brooks_pullback_count"
    ):
        return exit_policy or DEFAULT_PULLBACK_COUNT_EXIT_POLICY
    return exit_policy


def build_exit_plan(
    *,
    strategy_name: str,
    research_profile: str | None,
    bars: list[dict],
    signal_time: str,
    side: str,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    exit_policy: str | None = None,
) -> ExitPlan:
    if (
        research_profile == "qqq_5m_phase1"
        and strategy_name == "brooks_small_pb_trend"
        and side == "long"
    ):
        signal_index = next(
            (idx for idx, bar in enumerate(bars) if bar["time"] == signal_time),
            None,
        )
        if signal_index is not None:
            signal_bar = bars[signal_index]
            prev_bar = bars[signal_index - 1] if signal_index > 0 else signal_bar
            stop_price = min(float(prev_bar["low"]), float(signal_bar["low"]))
            if stop_price < entry_price:
                return ExitPlan(
                    stop_price=stop_price,
                    target_price=None,
                    stop_reason="phase1_structural_below_signal_pullback_low",
                    target_reason=None,
                )

    if (
        research_profile == "qqq_5m_phase1"
        and strategy_name == "brooks_breakout_pullback"
        and side == "long"
    ):
        breakout_context = _breakout_context(bars, signal_time)
        policy = resolve_exit_policy(
            strategy_name=strategy_name,
            research_profile=research_profile,
            exit_policy=exit_policy,
        )
        if breakout_context is not None and breakout_context.structural_stop < entry_price:
            target_price, target_reason = _breakout_target_for_policy(
                policy=policy,
                breakout_context=breakout_context,
                entry_price=entry_price,
            )
            return ExitPlan(
                stop_price=breakout_context.structural_stop,
                target_price=target_price,
                stop_reason="phase1_structural_below_breakout_pullback_low",
                target_reason=target_reason,
            )

    if (
        research_profile == "qqq_5m_phase1"
        and strategy_name == "brooks_pullback_count"
        and side == "long"
    ):
        pullback_context = _pullback_count_context(bars, signal_time)
        policy = resolve_exit_policy(
            strategy_name=strategy_name,
            research_profile=research_profile,
            exit_policy=exit_policy,
        )
        if pullback_context is not None and pullback_context.structural_stop < entry_price:
            target_price, target_reason = _pullback_count_target_for_policy(
                policy=policy,
                pullback_context=pullback_context,
                entry_price=entry_price,
            )
            return ExitPlan(
                stop_price=pullback_context.structural_stop,
                target_price=target_price,
                stop_reason="phase1_structural_below_h2_pullback_low",
                target_reason=target_reason,
            )

    if side == "long":
        return ExitPlan(
            stop_price=entry_price * (1 - stop_loss_pct / 100.0),
            target_price=entry_price * (1 + take_profit_pct / 100.0),
            stop_reason="fixed_pct_stop_loss",
            target_reason="fixed_pct_take_profit",
        )

    return ExitPlan(
        stop_price=entry_price * (1 + stop_loss_pct / 100.0),
        target_price=entry_price * (1 - take_profit_pct / 100.0),
        stop_reason="fixed_pct_stop_loss",
        target_reason="fixed_pct_take_profit",
    )


def compute_ema_series(bars: list[dict], period: int = 20) -> list[float]:
    if not bars:
        return []

    multiplier = 2 / (period + 1)
    values: list[float] = []
    ema_value: float | None = None
    for bar in bars:
        close = float(bar["close"])
        ema_value = close if ema_value is None else close * multiplier + ema_value * (1 - multiplier)
        values.append(ema_value)
    return values


def build_dynamic_exit_decision(
    *,
    strategy_name: str,
    research_profile: str | None,
    exit_policy: str | None = None,
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    side: str,
    entry_price: float,
    stop_price: float,
    max_favorable_price: float,
    signal_time: str | None = None,
    initial_risk: float | None = None,
) -> DynamicExitDecision | None:
    update = build_dynamic_exit_update(
        strategy_name=strategy_name,
        research_profile=research_profile,
        exit_policy=exit_policy,
        bars=bars,
        bar_index=bar_index,
        ema_values=ema_values,
        side=side,
        signal_time=signal_time,
        entry_price=entry_price,
        current_stop_price=stop_price,
        current_target_price=None,
        initial_risk=initial_risk if initial_risk is not None else abs(entry_price - stop_price),
        max_favorable_price=max_favorable_price,
    )
    if update is not None and update.exit_reason and update.exit_price is not None:
        return DynamicExitDecision(
            reason=update.exit_reason,
            exit_price=update.exit_price,
        )
    return None


def build_dynamic_exit_update(
    *,
    strategy_name: str,
    research_profile: str | None,
    exit_policy: str | None = None,
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    side: str,
    signal_time: str | None,
    entry_price: float,
    current_stop_price: float,
    current_target_price: float | None,
    initial_risk: float,
    max_favorable_price: float,
) -> DynamicExitUpdate | None:
    if side != "long" or bar_index <= 0 or bar_index >= len(bars):
        return None

    if research_profile != "qqq_5m_phase1":
        return None

    if strategy_name == "brooks_small_pb_trend":
        return _small_pb_dynamic_update(
            bars=bars,
            bar_index=bar_index,
            ema_values=ema_values,
            entry_price=entry_price,
            stop_price=current_stop_price,
            max_favorable_price=max_favorable_price,
        )

    if strategy_name == "brooks_pullback_count":
        return _pullback_count_dynamic_update(
            policy=resolve_exit_policy(
                strategy_name=strategy_name,
                research_profile=research_profile,
                exit_policy=exit_policy,
            ),
            bars=bars,
            bar_index=bar_index,
            ema_values=ema_values,
            signal_time=signal_time,
            entry_price=entry_price,
            current_stop_price=current_stop_price,
            current_target_price=current_target_price,
            initial_risk=initial_risk,
            max_favorable_price=max_favorable_price,
        )

    if strategy_name != "brooks_breakout_pullback":
        return None

    policy = resolve_exit_policy(
        strategy_name=strategy_name,
        research_profile=research_profile,
        exit_policy=exit_policy,
    )
    if policy not in BREAKOUT_EXIT_POLICIES:
        return None

    if initial_risk <= 0:
        return None

    if policy in {
        BREAKOUT_EXIT_POLICY_BREAK_EVEN_AFTER_1R,
        BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R,
    }:
        trigger_r = (
            0.75
            if policy == BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R
            else 1.0
        )
        if max_favorable_price < entry_price + initial_risk * trigger_r:
            return None
        if current_stop_price < entry_price:
            return DynamicExitUpdate(
                stop_price=entry_price,
                target_price=current_target_price,
                stop_reason=policy,
                target_reason=policy if current_target_price is not None else None,
            )
        return None
    if policy == BREAKOUT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R:
        if max_favorable_price < entry_price + initial_risk:
            return None
        breakout_context = _breakout_context(bars, signal_time)
        if breakout_context is None:
            return None
        tightened_stop = max(current_stop_price, breakout_context.pullback_low)
        if tightened_stop > current_stop_price:
            return DynamicExitUpdate(
                stop_price=tightened_stop,
                target_price=current_target_price,
                stop_reason=BREAKOUT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R,
                target_reason=None,
            )
        return None

    if policy == BREAKOUT_EXIT_POLICY_SWING_EMA_AFTER_1R:
        if max_favorable_price < entry_price + initial_risk:
            return None
        if len(ema_values) <= bar_index:
            return None

        curr = bars[bar_index]
        ema_value = float(ema_values[bar_index])
        if ema_value <= 0:
            return None

        confirmed_swing_low = _latest_confirmed_swing_low(bars, bar_index, lookback=1)
        if (
            confirmed_swing_low is not None
            and float(curr["close"]) < confirmed_swing_low
            and float(curr["close"]) < ema_value
        ):
            return DynamicExitUpdate(
                exit_reason="phase1_breakout_confirmed_swing_low_break_after_1r",
                exit_price=float(curr["close"]),
            )

    return None


def build_dynamic_exit_visualization(
    *,
    strategy_name: str,
    research_profile: str | None,
    exit_policy: str | None = None,
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    side: str,
    signal_time: str | None,
    entry_price: float,
    initial_risk: float,
    max_favorable_price: float,
) -> DynamicExitVisualization | None:
    if side != "long" or bar_index <= 0 or bar_index >= len(bars):
        return None
    if research_profile != "qqq_5m_phase1" or initial_risk <= 0:
        return None

    if strategy_name == "brooks_small_pb_trend":
        policy = SMALL_PB_EXIT_POLICY_SWING_EMA_AFTER_1R
        trigger_reason = "phase1_confirmed_swing_low_break_after_1r"
        supported_policy = SMALL_PB_EXIT_POLICY_SWING_EMA_AFTER_1R
    elif strategy_name == "brooks_breakout_pullback":
        policy = resolve_exit_policy(
            strategy_name=strategy_name,
            research_profile=research_profile,
            exit_policy=exit_policy,
        )
        trigger_reason = "phase1_breakout_confirmed_swing_low_break_after_1r"
        supported_policy = BREAKOUT_EXIT_POLICY_SWING_EMA_AFTER_1R
    elif strategy_name == "brooks_pullback_count":
        policy = resolve_exit_policy(
            strategy_name=strategy_name,
            research_profile=research_profile,
            exit_policy=exit_policy,
        )
        trigger_reason = "phase1_pullback_count_confirmed_swing_low_break_after_1r"
        supported_policy = PULLBACK_COUNT_EXIT_POLICY_SWING_EMA_AFTER_1R
    else:
        return None
    if policy != supported_policy:
        return None

    curr = bars[bar_index]
    one_r_price = entry_price + initial_risk
    armed = max_favorable_price >= one_r_price
    ema20 = float(ema_values[bar_index]) if len(ema_values) > bar_index else None
    swing_low_info = _latest_confirmed_swing_low_info(bars, bar_index, lookback=1)
    swing_low = swing_low_info[0] if swing_low_info is not None else None
    swing_low_time = swing_low_info[1] if swing_low_info is not None else None
    trigger_price = float(curr["close"])
    triggered = (
        armed
        and swing_low is not None
        and ema20 is not None
        and ema20 > 0
        and trigger_price < swing_low
        and trigger_price < ema20
    )

    return DynamicExitVisualization(
        policy=policy,
        armed=armed,
        one_r_price=one_r_price,
        bar_time=str(curr["time"]),
        ema20=ema20,
        swing_low=swing_low,
        swing_low_time=swing_low_time,
        triggered=triggered,
        trigger_reason=trigger_reason if triggered else None,
        trigger_price=trigger_price if triggered else None,
    )


def _pullback_count_dynamic_update(
    *,
    policy: str | None,
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    signal_time: str | None,
    entry_price: float,
    current_stop_price: float,
    current_target_price: float | None,
    initial_risk: float,
    max_favorable_price: float,
) -> DynamicExitUpdate | None:
    if policy not in PULLBACK_COUNT_EXIT_POLICIES:
        return None
    if initial_risk <= 0:
        return None

    if policy in {
        PULLBACK_COUNT_EXIT_POLICY_BREAK_EVEN_AFTER_1R,
        PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R,
    }:
        trigger_r = (
            0.75
            if policy == PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R
            else 1.0
        )
        if max_favorable_price < entry_price + initial_risk * trigger_r:
            return None
        if current_stop_price < entry_price:
            return DynamicExitUpdate(
                stop_price=entry_price,
                target_price=current_target_price,
                stop_reason=policy,
                target_reason=policy if current_target_price is not None else None,
            )
        return None

    if policy == PULLBACK_COUNT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R:
        if max_favorable_price < entry_price + initial_risk:
            return None
        pullback_context = _pullback_count_context(bars, signal_time)
        if pullback_context is None:
            return None
        tightened_stop = max(current_stop_price, pullback_context.pullback_low)
        if tightened_stop > current_stop_price:
            return DynamicExitUpdate(
                stop_price=tightened_stop,
                target_price=current_target_price,
                stop_reason=PULLBACK_COUNT_EXIT_POLICY_PULLBACK_LOW_AFTER_1R,
                target_reason=None,
            )
        return None

    if policy == PULLBACK_COUNT_EXIT_POLICY_SWING_EMA_AFTER_1R:
        if max_favorable_price < entry_price + initial_risk:
            return None
        if len(ema_values) <= bar_index:
            return None
        curr = bars[bar_index]
        ema_value = float(ema_values[bar_index])
        confirmed_swing_low = _latest_confirmed_swing_low(bars, bar_index, lookback=1)
        if (
            confirmed_swing_low is not None
            and ema_value > 0
            and float(curr["close"]) < confirmed_swing_low
            and float(curr["close"]) < ema_value
        ):
            return DynamicExitUpdate(
                exit_reason="phase1_pullback_count_confirmed_swing_low_break_after_1r",
                exit_price=float(curr["close"]),
            )

    return None


def _small_pb_dynamic_update(
    *,
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    entry_price: float,
    stop_price: float,
    max_favorable_price: float,
) -> DynamicExitUpdate | None:
    if len(ema_values) <= bar_index:
        return None

    initial_risk = entry_price - stop_price
    if initial_risk <= 0:
        return None
    if max_favorable_price < entry_price + initial_risk:
        return None

    curr = bars[bar_index]
    ema_value = float(ema_values[bar_index])
    if ema_value <= 0:
        return None

    confirmed_swing_low = _latest_confirmed_swing_low(bars, bar_index, lookback=1)
    if (
        confirmed_swing_low is not None
        and float(curr["close"]) < confirmed_swing_low
        and float(curr["close"]) < ema_value
    ):
        return DynamicExitUpdate(
            exit_reason="phase1_confirmed_swing_low_break_after_1r",
            exit_price=float(curr["close"]),
        )

    return None


def _breakout_context(
    bars: list[dict],
    signal_time: str | None,
) -> BreakoutContext | None:
    if not signal_time:
        return None

    signal_index = next(
        (idx for idx, bar in enumerate(bars) if bar["time"] == signal_time),
        None,
    )
    if signal_index is None:
        return None

    breakout_bar = (
        bars[signal_index - 2]
        if signal_index >= 2
        else bars[max(signal_index - 1, 0)]
    )
    pullback_bar = (
        bars[signal_index - 1]
        if signal_index >= 1
        else bars[signal_index]
    )
    signal_bar = bars[signal_index]
    structural_stop = min(float(breakout_bar["low"]), float(pullback_bar["low"]))
    return BreakoutContext(
        breakout_low=float(breakout_bar["low"]),
        breakout_high=float(breakout_bar["high"]),
        pullback_low=float(pullback_bar["low"]),
        signal_low=float(signal_bar["low"]),
        structural_stop=structural_stop,
    )


def _pullback_count_context(
    bars: list[dict],
    signal_time: str | None,
) -> PullbackCountContext | None:
    if not signal_time:
        return None

    signal_index = next(
        (idx for idx, bar in enumerate(bars) if bar["time"] == signal_time),
        None,
    )
    if signal_index is None or signal_index <= 0:
        return None

    pullback_bar = bars[signal_index - 1]
    signal_bar = bars[signal_index]
    structural_stop = min(float(pullback_bar["low"]), float(signal_bar["low"]))
    return PullbackCountContext(
        pullback_low=float(pullback_bar["low"]),
        signal_low=float(signal_bar["low"]),
        structural_stop=structural_stop,
    )


def _breakout_target_for_policy(
    *,
    policy: str | None,
    breakout_context: BreakoutContext,
    entry_price: float,
) -> tuple[float | None, str | None]:
    if policy == BREAKOUT_EXIT_POLICY_TARGET_1R:
        risk = entry_price - breakout_context.structural_stop
        return entry_price + risk, BREAKOUT_EXIT_POLICY_TARGET_1R
    if policy == BREAKOUT_EXIT_POLICY_TARGET_1_5R:
        risk = entry_price - breakout_context.structural_stop
        return entry_price + risk * 1.5, BREAKOUT_EXIT_POLICY_TARGET_1_5R
    if policy == BREAKOUT_EXIT_POLICY_TARGET_2R:
        risk = entry_price - breakout_context.structural_stop
        return entry_price + risk * 2.0, BREAKOUT_EXIT_POLICY_TARGET_2R
    if policy == BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R:
        risk = entry_price - breakout_context.structural_stop
        return (
            entry_price + risk * 2.5,
            BREAKOUT_EXIT_POLICY_TARGET_2_5R_BREAK_EVEN_AFTER_0_75R,
        )
    if policy == BREAKOUT_EXIT_POLICY_MEASURED_MOVE:
        measured_move = breakout_context.breakout_high - breakout_context.breakout_low
        return entry_price + measured_move, BREAKOUT_EXIT_POLICY_MEASURED_MOVE
    return None, None


def _pullback_count_target_for_policy(
    *,
    policy: str | None,
    pullback_context: PullbackCountContext,
    entry_price: float,
) -> tuple[float | None, str | None]:
    risk = entry_price - pullback_context.structural_stop
    if policy == PULLBACK_COUNT_EXIT_POLICY_TARGET_1R:
        return entry_price + risk, PULLBACK_COUNT_EXIT_POLICY_TARGET_1R
    if policy == PULLBACK_COUNT_EXIT_POLICY_TARGET_1_5R:
        return entry_price + risk * 1.5, PULLBACK_COUNT_EXIT_POLICY_TARGET_1_5R
    if policy == PULLBACK_COUNT_EXIT_POLICY_TARGET_2R:
        return entry_price + risk * 2.0, PULLBACK_COUNT_EXIT_POLICY_TARGET_2R
    if policy == PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R:
        return (
            entry_price + risk * 2.0,
            PULLBACK_COUNT_EXIT_POLICY_TARGET_2R_BREAK_EVEN_AFTER_0_75R,
        )
    return None, None


def _latest_confirmed_swing_low(
    bars: list[dict],
    current_index: int,
    lookback: int,
) -> float | None:
    latest = _latest_confirmed_swing_low_info(bars, current_index, lookback)
    return latest[0] if latest is not None else None


def _latest_confirmed_swing_low_info(
    bars: list[dict],
    current_index: int,
    lookback: int,
) -> tuple[float, str] | None:
    latest: float | None = None
    latest_time: str | None = None
    end_center = current_index - lookback
    for center in range(lookback, end_center + 1):
        low = float(bars[center]["low"])
        is_swing_low = True
        for idx in range(center - lookback, center + lookback + 1):
            if idx == center:
                continue
            if low > float(bars[idx]["low"]):
                is_swing_low = False
                break
        if is_swing_low:
            latest = low
            latest_time = str(bars[center]["time"])
    if latest is None or latest_time is None:
        return None
    return latest, latest_time


def _is_strong_bear(bar: dict, threshold: float) -> bool:
    return float(bar["close"]) < float(bar["open"]) and _body_ratio(bar) >= threshold


def _body_ratio(bar: dict) -> float:
    total_range = max(float(bar["high"]) - float(bar["low"]), 1e-9)
    return abs(float(bar["close"]) - float(bar["open"])) / total_range
