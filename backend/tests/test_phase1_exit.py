from services.phase1_exit import build_dynamic_exit_decision, compute_ema_series


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
