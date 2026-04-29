from services.strategy_engine import get_strategy


def _bar(
    ts: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1000,
) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bars_with_pullback_low(pullback_low: float) -> list[dict]:
    return [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.7, 100.1, 100.5),
        _bar("2025-01-06T14:40:00+00:00", 100.5, 101.0, 100.4, 100.9),
        _bar("2025-01-06T14:45:00+00:00", 100.9, 101.2, 100.8, 101.0),
        _bar("2025-01-06T14:50:00+00:00", 101.0, 102.3, 100.95, 102.0),
        _bar("2025-01-06T14:55:00+00:00", 102.0, 102.15, pullback_low, 101.95),
        _bar("2025-01-06T15:00:00+00:00", 101.95, 102.4, 101.9, 102.25),
        _bar("2025-01-06T15:05:00+00:00", 102.25, 102.5, 102.1, 102.3),
    ]


def test_breakout_pullback_emits_signal_when_pullback_holds_breakout_level():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {"range_lookback": 3, "ema_period": 3, "quantity": 1},
    )

    signals = strategy.generate_signals("QQQ", _bars_with_pullback_low(101.25))

    assert len(signals) == 1
    assert signals[0].timestamp.isoformat() == "2025-01-06T15:00:00+00:00"


def test_breakout_pullback_skips_signal_when_pullback_breaks_breakout_level():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {"range_lookback": 3, "ema_period": 3, "quantity": 1},
    )

    signals = strategy.generate_signals("QQQ", _bars_with_pullback_low(100.9))

    assert signals == []


def test_breakout_pullback_skips_signal_when_pullback_retraces_too_deep():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {"range_lookback": 3, "ema_period": 3, "quantity": 1},
    )
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 101.1, 100.5, 100.9),
        _bar("2025-01-06T14:45:00+00:00", 100.9, 101.2, 100.8, 101.0),
        _bar("2025-01-06T14:50:00+00:00", 101.0, 103.2, 100.95, 102.9),
        _bar("2025-01-06T14:55:00+00:00", 102.9, 103.0, 101.15, 101.4),
        _bar("2025-01-06T15:00:00+00:00", 101.4, 103.3, 101.35, 103.1),
        _bar("2025-01-06T15:05:00+00:00", 103.1, 103.2, 102.9, 103.0),
    ]

    signals = strategy.generate_signals("QQQ", bars)

    assert signals == []


def test_breakout_pullback_default_skips_pullback_deeper_than_065_breakout_range():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {
            "range_lookback": 3,
            "ema_period": 3,
            "quantity": 1,
            "require_above_session_open": False,
            "require_above_session_vwap": False,
        },
    )
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.8, 100.1, 100.6),
        _bar("2025-01-06T14:40:00+00:00", 100.6, 101.1, 100.5, 100.9),
        _bar("2025-01-06T14:45:00+00:00", 100.9, 101.2, 100.8, 101.0),
        _bar("2025-01-06T14:50:00+00:00", 101.0, 103.2, 100.95, 102.9),
        _bar("2025-01-06T14:55:00+00:00", 102.9, 103.0, 101.35, 101.4),
        _bar("2025-01-06T15:00:00+00:00", 101.4, 103.3, 101.35, 103.1),
        _bar("2025-01-06T15:05:00+00:00", 103.1, 103.2, 102.9, 103.0),
    ]

    signals = strategy.generate_signals("QQQ", bars)

    assert signals == []


def test_breakout_pullback_default_vwap_buffer_allows_entry_at_session_vwap():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {
            "range_lookback": 3,
            "ema_period": 3,
            "quantity": 1,
            "max_pullback_depth_ratio": 0.75,
            "require_above_session_open": False,
            "require_above_session_vwap": True,
        },
    )
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.4, 99.9, 100.2, volume=1),
        _bar("2025-01-06T14:35:00+00:00", 100.2, 100.7, 100.1, 100.5, volume=1),
        _bar("2025-01-06T14:40:00+00:00", 100.5, 101.0, 100.4, 100.9, volume=1),
        _bar("2025-01-06T14:45:00+00:00", 100.9, 101.2, 100.8, 101.0, volume=1),
        _bar("2025-01-06T14:50:00+00:00", 101.0, 102.3, 100.95, 102.0, volume=1),
        _bar("2025-01-06T14:55:00+00:00", 102.0, 102.15, 101.0, 101.95, volume=1),
        _bar("2025-01-06T15:00:00+00:00", 101.95, 102.3, 102.17, 102.25, volume=1_000_000),
        _bar("2025-01-06T15:05:00+00:00", 102.25, 102.5, 102.1, 102.3, volume=1),
    ]

    signals = strategy.generate_signals("QQQ", bars)

    assert len(signals) == 1
    assert signals[0].timestamp.isoformat() == "2025-01-06T15:00:00+00:00"


def test_breakout_pullback_skips_signal_when_resumption_is_below_session_open():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {"range_lookback": 2, "ema_period": 3, "quantity": 1},
    )
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 104.0, 104.05, 103.2, 103.25, volume=30000),
        _bar("2025-01-06T14:35:00+00:00", 103.25, 103.4, 102.9, 103.0, volume=16000),
        _bar("2025-01-06T14:40:00+00:00", 103.0, 103.3, 102.6, 102.8, volume=12000),
        _bar("2025-01-06T14:45:00+00:00", 102.8, 102.95, 102.7, 102.85, volume=9000),
        _bar("2025-01-06T14:50:00+00:00", 102.85, 103.65, 102.8, 103.62, volume=11000),
        _bar("2025-01-06T14:55:00+00:00", 103.62, 103.63, 103.42, 103.5, volume=6000),
        _bar("2025-01-06T15:00:00+00:00", 103.5, 103.8, 103.48, 103.7, volume=8000),
        _bar("2025-01-06T15:05:00+00:00", 103.7, 103.72, 103.55, 103.62, volume=5000),
    ]

    signals = strategy.generate_signals("QQQ", bars)

    assert signals == []
