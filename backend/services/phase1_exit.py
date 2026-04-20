from __future__ import annotations

from dataclasses import dataclass


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
    bars: list[dict],
    bar_index: int,
    ema_values: list[float],
    side: str,
    entry_price: float,
    stop_price: float,
    max_favorable_price: float,
) -> DynamicExitDecision | None:
    if (
        research_profile != "qqq_5m_phase1"
        or strategy_name != "brooks_small_pb_trend"
        or side != "long"
        or bar_index <= 0
        or bar_index >= len(bars)
        or len(ema_values) <= bar_index
    ):
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
        return DynamicExitDecision(
            reason="phase1_confirmed_swing_low_break_after_1r",
            exit_price=float(curr["close"]),
        )

    return None


def _latest_confirmed_swing_low(
    bars: list[dict],
    current_index: int,
    lookback: int,
) -> float | None:
    latest: float | None = None
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
    return latest


def _is_strong_bear(bar: dict, threshold: float) -> bool:
    return float(bar["close"]) < float(bar["open"]) and _body_ratio(bar) >= threshold


def _body_ratio(bar: dict) -> float:
    total_range = max(float(bar["high"]) - float(bar["low"]), 1e-9)
    return abs(float(bar["close"]) - float(bar["open"])) / total_range
