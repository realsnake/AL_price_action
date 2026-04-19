from services.strategy_engine import get_strategy


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
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

    signals = strategy.generate_signals("QQQ", _bars_with_pullback_low(101.0))

    assert len(signals) == 1
    assert signals[0].timestamp.isoformat() == "2025-01-06T15:00:00+00:00"


def test_breakout_pullback_skips_signal_when_pullback_breaks_breakout_level():
    strategy = get_strategy(
        "brooks_breakout_pullback",
        {"range_lookback": 3, "ema_period": 3, "quantity": 1},
    )

    signals = strategy.generate_signals("QQQ", _bars_with_pullback_low(100.9))

    assert signals == []
