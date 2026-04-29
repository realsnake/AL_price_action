import pytest

from services.phase1_exit import (
    BREAKOUT_EXIT_POLICIES,
    build_dynamic_exit_visualization,
    build_dynamic_exit_update,
    build_dynamic_exit_decision,
    build_exit_plan,
    compute_ema_series,
)


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


def test_phase1_dynamic_exit_requires_1r_and_confirmed_swing_low_break():
    bars = []
    price = 101.8
    hour = 14
    minute = 30
    for _ in range(18):
        ts = f"2025-01-06T{hour:02d}:{minute:02d}:00+00:00"
        bars.append(_bar(ts, price, price + 0.2, price - 0.1, price + 0.1))
        minute += 5
        if minute >= 60:
            hour += 1
            minute -= 60

    bars.extend(
        [
            _bar("2025-01-06T16:00:00+00:00", 102.0, 102.1, 101.8, 101.85),
            _bar("2025-01-06T16:05:00+00:00", 101.85, 102.4, 101.9, 102.3),
            _bar("2025-01-06T16:10:00+00:00", 102.3, 102.9, 102.2, 102.7),
            _bar("2025-01-06T16:15:00+00:00", 102.7, 102.75, 102.1, 102.25),
            _bar("2025-01-06T16:20:00+00:00", 102.25, 102.6, 102.2, 102.5),
            _bar("2025-01-06T16:25:00+00:00", 102.45, 102.5, 101.95, 102.0),
        ]
    )

    ema_values = compute_ema_series(bars, 20)
    decision = build_dynamic_exit_decision(
        strategy_name="brooks_small_pb_trend",
        research_profile="qqq_5m_phase1",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=ema_values,
        side="long",
        entry_price=102.3,
        stop_price=101.8,
        max_favorable_price=102.9,
    )

    assert decision is not None
    assert decision.reason == "phase1_confirmed_swing_low_break_after_1r"
    assert decision.exit_price == 102.0


def test_phase1_small_pb_visualizes_swing_ema_exit_after_1r():
    bars = []
    price = 101.8
    hour = 14
    minute = 30
    for _ in range(18):
        ts = f"2025-01-06T{hour:02d}:{minute:02d}:00+00:00"
        bars.append(_bar(ts, price, price + 0.2, price - 0.1, price + 0.1))
        minute += 5
        if minute >= 60:
            hour += 1
            minute -= 60

    bars.extend(
        [
            _bar("2025-01-06T16:00:00+00:00", 102.0, 102.1, 101.8, 101.85),
            _bar("2025-01-06T16:05:00+00:00", 101.85, 102.4, 101.9, 102.3),
            _bar("2025-01-06T16:10:00+00:00", 102.3, 102.9, 102.2, 102.7),
            _bar("2025-01-06T16:15:00+00:00", 102.7, 102.75, 102.1, 102.25),
            _bar("2025-01-06T16:20:00+00:00", 102.25, 102.6, 102.2, 102.5),
            _bar("2025-01-06T16:25:00+00:00", 102.45, 102.5, 101.95, 102.0),
        ]
    )

    visualization = build_dynamic_exit_visualization(
        strategy_name="brooks_small_pb_trend",
        research_profile="qqq_5m_phase1",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T16:05:00+00:00",
        entry_price=102.3,
        initial_risk=0.5,
        max_favorable_price=102.9,
    )

    assert visualization is not None
    assert visualization.policy == "small_pb_trend_swing_ema_after_1r"
    assert visualization.armed is True
    assert visualization.one_r_price == pytest.approx(102.8)
    assert visualization.swing_low == pytest.approx(102.1)
    assert visualization.swing_low_time == "2025-01-06T16:15:00+00:00"
    assert visualization.triggered is True
    assert visualization.trigger_reason == "phase1_confirmed_swing_low_break_after_1r"
    assert visualization.trigger_price == pytest.approx(102.0)


def test_phase1_dynamic_exit_ignores_swing_low_break_before_1r_profit():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 101.8, 102.0, 101.7, 101.9),
        _bar("2025-01-06T14:35:00+00:00", 101.9, 102.1, 101.8, 102.0),
        _bar("2025-01-06T14:40:00+00:00", 102.0, 102.2, 101.9, 102.1),
        _bar("2025-01-06T14:45:00+00:00", 102.1, 102.3, 102.0, 102.2),
        _bar("2025-01-06T14:50:00+00:00", 102.2, 102.4, 102.1, 102.3),
        _bar("2025-01-06T14:55:00+00:00", 102.3, 102.5, 102.2, 102.4),
        _bar("2025-01-06T15:00:00+00:00", 102.4, 102.6, 102.3, 102.5),
        _bar("2025-01-06T15:05:00+00:00", 102.5, 102.7, 102.4, 102.6),
        _bar("2025-01-06T15:10:00+00:00", 102.6, 102.8, 102.5, 102.7),
        _bar("2025-01-06T15:15:00+00:00", 102.7, 102.9, 102.6, 102.8),
        _bar("2025-01-06T15:20:00+00:00", 102.8, 103.0, 102.7, 102.9),
        _bar("2025-01-06T15:25:00+00:00", 102.9, 103.1, 102.8, 103.0),
        _bar("2025-01-06T15:30:00+00:00", 103.0, 103.2, 102.9, 103.1),
        _bar("2025-01-06T15:35:00+00:00", 103.1, 103.3, 103.0, 103.2),
        _bar("2025-01-06T15:40:00+00:00", 103.2, 103.4, 103.1, 103.3),
        _bar("2025-01-06T15:45:00+00:00", 103.3, 103.5, 103.2, 103.4),
        _bar("2025-01-06T15:50:00+00:00", 103.4, 103.6, 103.3, 103.5),
        _bar("2025-01-06T15:55:00+00:00", 103.5, 103.7, 103.4, 103.6),
        _bar("2025-01-06T16:00:00+00:00", 102.0, 102.1, 101.8, 101.85),
        _bar("2025-01-06T16:05:00+00:00", 101.85, 102.4, 101.9, 102.3),
        _bar("2025-01-06T16:10:00+00:00", 102.3, 102.7, 102.2, 102.55),
        _bar("2025-01-06T16:15:00+00:00", 102.55, 102.6, 102.1, 102.25),
        _bar("2025-01-06T16:20:00+00:00", 102.25, 102.5, 102.2, 102.45),
        _bar("2025-01-06T16:25:00+00:00", 102.45, 102.5, 101.95, 102.0),
    ]
    ema_values = compute_ema_series(bars, 20)

    decision = build_dynamic_exit_decision(
        strategy_name="brooks_small_pb_trend",
        research_profile="qqq_5m_phase1",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=ema_values,
        side="long",
        entry_price=102.3,
        stop_price=101.8,
        max_favorable_price=102.7,
    )

    assert decision is None


def test_phase1_breakout_pullback_exit_plan_uses_structural_stop_without_fixed_target():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.0, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_session_close",
    )

    assert plan.stop_price == 100.4
    assert plan.target_price is None
    assert plan.stop_reason == "phase1_structural_below_breakout_pullback_low"
    assert plan.target_reason is None


def test_phase1_breakout_pullback_exit_plan_supports_1r_target_policy():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_target_1r",
    )

    assert plan.stop_price == 100.4
    assert plan.target_price == 105.6
    assert plan.stop_reason == "phase1_structural_below_breakout_pullback_low"
    assert plan.target_reason == "breakout_target_1r"


def test_phase1_breakout_exit_policy_catalog_expands_r_target_and_trigger_variants():
    assert "breakout_target_1_25r" in BREAKOUT_EXIT_POLICIES
    assert "breakout_target_3r_break_even_after_0_5r" in BREAKOUT_EXIT_POLICIES
    assert "breakout_pullback_low_after_0_75r" in BREAKOUT_EXIT_POLICIES
    assert "breakout_swing_ema_after_1_25r" in BREAKOUT_EXIT_POLICIES


def test_phase1_breakout_pullback_exit_plan_supports_fractional_r_target_policy():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_target_1_25r",
    )

    assert plan.stop_price == 100.4
    assert plan.target_price == pytest.approx(106.25)
    assert plan.target_reason == "breakout_target_1_25r"


def test_phase1_breakout_target_3r_break_even_after_0_5r_policy():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
        _bar("2025-01-06T14:55:00+00:00", 103.0, 104.4, 102.9, 104.2),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_target_3r_break_even_after_0_5r",
    )
    update = build_dynamic_exit_update(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        exit_policy="breakout_target_3r_break_even_after_0_5r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T14:50:00+00:00",
        entry_price=103.0,
        current_stop_price=100.4,
        current_target_price=plan.target_price,
        initial_risk=2.6,
        max_favorable_price=104.4,
    )

    assert plan.target_price == pytest.approx(110.8)
    assert plan.target_reason == "breakout_target_3r_break_even_after_0_5r"
    assert update is not None
    assert update.stop_price == 103.0
    assert update.target_price == pytest.approx(110.8)
    assert update.stop_reason == "breakout_target_3r_break_even_after_0_5r"


def test_phase1_breakout_pullback_low_after_0_75r_tightens_stop_to_pullback_low():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
        _bar("2025-01-06T14:55:00+00:00", 103.0, 105.0, 102.9, 104.8),
    ]

    update = build_dynamic_exit_update(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        exit_policy="breakout_pullback_low_after_0_75r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T14:50:00+00:00",
        entry_price=103.0,
        current_stop_price=100.4,
        current_target_price=None,
        initial_risk=2.6,
        max_favorable_price=105.0,
    )

    assert update is not None
    assert update.stop_price == 101.2
    assert update.stop_reason == "breakout_pullback_low_after_0_75r"


def test_phase1_pullback_count_exit_plan_uses_recent_pullback_low_without_fixed_target():
    bars = [
        _bar("2025-01-06T14:50:00+00:00", 101.8, 102.4, 101.7, 102.2),
        _bar("2025-01-06T14:55:00+00:00", 102.2, 102.3, 101.8, 102.0),
        _bar("2025-01-06T15:00:00+00:00", 102.0, 102.9, 101.95, 102.75),
        _bar("2025-01-06T15:05:00+00:00", 102.75, 102.85, 102.45, 102.55),
        _bar("2025-01-06T15:10:00+00:00", 102.55, 103.5, 102.5, 103.45),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_pullback_count",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T15:10:00+00:00",
        side="long",
        entry_price=103.45,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="pullback_count_session_close",
    )

    assert plan.stop_price == 102.45
    assert plan.target_price is None
    assert plan.stop_reason == "phase1_structural_below_h2_pullback_low"
    assert plan.target_reason is None


def test_phase1_pullback_count_exit_plan_supports_2r_target_policy():
    bars = [
        _bar("2025-01-06T14:50:00+00:00", 101.8, 102.4, 101.7, 102.2),
        _bar("2025-01-06T14:55:00+00:00", 102.2, 102.3, 101.8, 102.0),
        _bar("2025-01-06T15:00:00+00:00", 102.0, 102.9, 101.95, 102.75),
        _bar("2025-01-06T15:05:00+00:00", 102.75, 102.85, 102.45, 102.55),
        _bar("2025-01-06T15:10:00+00:00", 102.55, 103.5, 102.5, 103.45),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_pullback_count",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T15:10:00+00:00",
        side="long",
        entry_price=103.45,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="pullback_count_target_2r",
    )

    assert plan.stop_price == 102.45
    assert plan.target_price == pytest.approx(105.45)
    assert plan.target_reason == "pullback_count_target_2r"


def test_phase1_breakout_pullback_exit_plan_supports_measured_move_target_policy():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_measured_move",
    )

    assert plan.stop_price == 100.4
    assert plan.target_price == 106.0
    assert plan.target_reason == "breakout_measured_move"


def test_phase1_breakout_pullback_exit_plan_supports_2_5r_target_with_0_75r_break_even_policy():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
    ]

    plan = build_exit_plan(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        bars=bars,
        signal_time="2025-01-06T14:50:00+00:00",
        side="long",
        entry_price=103.0,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        exit_policy="breakout_target_2_5r_break_even_after_0_75r",
    )

    assert plan.stop_price == 100.4
    assert plan.target_price == pytest.approx(109.5)
    assert plan.target_reason == "breakout_target_2_5r_break_even_after_0_75r"


def test_phase1_breakout_break_even_after_1r_tightens_stop_to_entry():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
        _bar("2025-01-06T14:55:00+00:00", 103.0, 106.0, 102.9, 105.7),
    ]

    update = build_dynamic_exit_update(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        exit_policy="breakout_break_even_after_1r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T14:50:00+00:00",
        entry_price=103.0,
        current_stop_price=100.4,
        current_target_price=None,
        initial_risk=2.6,
        max_favorable_price=106.0,
    )

    assert update is not None
    assert update.stop_price == 103.0
    assert update.stop_reason == "breakout_break_even_after_1r"
    assert update.exit_reason is None


def test_phase1_breakout_target_2_5r_break_even_after_0_75r_tightens_stop_to_entry():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
        _bar("2025-01-06T14:55:00+00:00", 103.0, 105.1, 102.9, 104.95),
    ]

    update = build_dynamic_exit_update(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        exit_policy="breakout_target_2_5r_break_even_after_0_75r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T14:50:00+00:00",
        entry_price=103.0,
        current_stop_price=100.4,
        current_target_price=109.5,
        initial_risk=2.6,
        max_favorable_price=105.1,
    )

    assert update is not None
    assert update.stop_price == 103.0
    assert update.target_price == pytest.approx(109.5)
    assert update.stop_reason == "breakout_target_2_5r_break_even_after_0_75r"


def test_phase1_breakout_pullback_low_after_1r_tightens_stop_to_pullback_low():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 103.4, 100.4, 102.6),
        _bar("2025-01-06T14:45:00+00:00", 102.6, 102.8, 101.2, 101.9),
        _bar("2025-01-06T14:50:00+00:00", 101.9, 103.1, 101.8, 103.0),
        _bar("2025-01-06T14:55:00+00:00", 103.0, 106.0, 102.9, 105.7),
    ]

    update = build_dynamic_exit_update(
        strategy_name="brooks_breakout_pullback",
        research_profile="qqq_5m_phase1",
        exit_policy="breakout_pullback_low_after_1r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T14:50:00+00:00",
        entry_price=103.0,
        current_stop_price=100.4,
        current_target_price=None,
        initial_risk=2.6,
        max_favorable_price=106.0,
    )

    assert update is not None
    assert update.stop_price == 101.2
    assert update.stop_reason == "breakout_pullback_low_after_1r"
    assert update.exit_reason is None


def test_phase1_pullback_count_break_even_after_1r_tightens_stop_to_entry():
    bars = [
        _bar("2025-01-06T14:50:00+00:00", 101.8, 102.4, 101.7, 102.2),
        _bar("2025-01-06T14:55:00+00:00", 102.2, 102.3, 101.8, 102.0),
        _bar("2025-01-06T15:00:00+00:00", 102.0, 102.9, 101.95, 102.75),
        _bar("2025-01-06T15:05:00+00:00", 102.75, 102.85, 102.45, 102.55),
        _bar("2025-01-06T15:10:00+00:00", 102.55, 103.5, 102.5, 103.45),
        _bar("2025-01-06T15:15:00+00:00", 103.45, 104.6, 103.3, 104.4),
    ]

    update = build_dynamic_exit_update(
        strategy_name="brooks_pullback_count",
        research_profile="qqq_5m_phase1",
        exit_policy="pullback_count_break_even_after_1r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T15:10:00+00:00",
        entry_price=103.45,
        current_stop_price=102.45,
        current_target_price=None,
        initial_risk=1.0,
        max_favorable_price=104.6,
    )

    assert update is not None
    assert update.stop_price == 103.45
    assert update.stop_reason == "pullback_count_break_even_after_1r"


def test_phase1_pullback_count_visualizes_swing_ema_exit_after_1r():
    bars = [
        _bar("2025-01-06T14:50:00+00:00", 101.8, 102.4, 101.7, 102.2),
        _bar("2025-01-06T14:55:00+00:00", 102.2, 102.3, 101.8, 102.0),
        _bar("2025-01-06T15:00:00+00:00", 102.0, 102.9, 101.95, 102.75),
        _bar("2025-01-06T15:05:00+00:00", 102.75, 102.85, 102.45, 102.55),
        _bar("2025-01-06T15:10:00+00:00", 102.55, 103.5, 102.5, 103.45),
        _bar("2025-01-06T15:15:00+00:00", 103.45, 104.6, 103.3, 104.4),
        _bar("2025-01-06T15:20:00+00:00", 104.4, 104.45, 103.2, 103.45),
        _bar("2025-01-06T15:25:00+00:00", 103.45, 103.9, 103.5, 103.75),
        _bar("2025-01-06T15:30:00+00:00", 103.75, 103.8, 102.6, 102.7),
    ]

    visualization = build_dynamic_exit_visualization(
        strategy_name="brooks_pullback_count",
        research_profile="qqq_5m_phase1",
        exit_policy="pullback_count_swing_ema_after_1r",
        bars=bars,
        bar_index=len(bars) - 1,
        ema_values=compute_ema_series(bars, 20),
        side="long",
        signal_time="2025-01-06T15:10:00+00:00",
        entry_price=103.45,
        initial_risk=1.0,
        max_favorable_price=104.6,
    )

    assert visualization is not None
    assert visualization.policy == "pullback_count_swing_ema_after_1r"
    assert visualization.armed is True
    assert visualization.one_r_price == pytest.approx(104.45)
    assert visualization.swing_low == pytest.approx(103.2)
    assert visualization.swing_low_time == "2025-01-06T15:20:00+00:00"
    assert visualization.triggered is True
    assert visualization.trigger_price == pytest.approx(102.7)
