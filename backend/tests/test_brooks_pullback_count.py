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


def _h2_bull_pullback_bars(entry_close: float = 103.45) -> list[dict]:
    return [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.5, 99.9, 100.4, 12000),
        _bar("2025-01-06T14:35:00+00:00", 100.4, 101.0, 100.3, 100.8, 11000),
        _bar("2025-01-06T14:40:00+00:00", 100.8, 101.5, 100.7, 101.3, 10000),
        _bar("2025-01-06T14:45:00+00:00", 101.3, 102.0, 101.2, 101.8, 10000),
        _bar("2025-01-06T14:50:00+00:00", 101.8, 102.4, 101.7, 102.2, 9000),
        _bar("2025-01-06T14:55:00+00:00", 102.2, 102.3, 101.8, 102.0, 8000),
        _bar("2025-01-06T15:00:00+00:00", 102.0, 102.9, 101.95, 102.75, 11000),
        _bar("2025-01-06T15:05:00+00:00", 102.75, 102.85, 102.45, 102.55, 7000),
        _bar("2025-01-06T15:10:00+00:00", 102.55, 103.5, 102.5, entry_close, 12000),
        _bar("2025-01-06T15:15:00+00:00", entry_close, 103.7, 103.2, 103.5, 9000),
    ]


def test_pullback_count_emits_h2_buy_after_second_pullback_reversal():
    strategy = get_strategy(
        "brooks_pullback_count",
        {"ema_period": 3, "quantity": 1},
    )

    signals = strategy.generate_signals("QQQ", _h2_bull_pullback_bars())

    assert len(signals) == 1
    assert signals[0].timestamp.isoformat() == "2025-01-06T15:10:00+00:00"
    assert signals[0].reason.startswith("H2 buy")


def test_pullback_count_skips_buy_signal_below_session_open():
    strategy = get_strategy(
        "brooks_pullback_count",
        {"ema_period": 3, "quantity": 1},
    )
    bars = _h2_bull_pullback_bars(entry_close=103.45)
    bars[0] = _bar("2025-01-06T14:30:00+00:00", 104.0, 104.1, 103.8, 103.9, 12000)

    signals = strategy.generate_signals("QQQ", bars)

    assert signals == []


def test_pullback_count_skips_buy_signal_below_session_vwap_buffer():
    strategy = get_strategy(
        "brooks_pullback_count",
            {
                "ema_period": 3,
                "quantity": 1,
                "session_vwap_buffer_bps": 300.0,
            },
        )

    signals = strategy.generate_signals("QQQ", _h2_bull_pullback_bars())

    assert signals == []
