from datetime import datetime

from services.backtester import run_backtest
from strategies.base import Signal, SignalType


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


def test_run_backtest_uses_exact_intraday_signal_timestamp():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.4, 499.8, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.5, 500.0, 500.3),
        _bar("2025-01-06T14:40:00+00:00", 500.3, 500.8, 500.2, 500.7),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.0, 500.6, 500.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.7,
            quantity=1,
            reason="timestamp-match",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_breakout_pullback",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"


def test_run_backtest_ignores_short_signals_for_long_only_profile():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 499.8, 500.0),
        _bar("2025-01-06T14:40:00+00:00", 500.0, 500.2, 499.7, 499.9),
        _bar("2025-01-06T20:55:00+00:00", 499.9, 500.0, 499.6, 499.8),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.SELL,
            price=499.9,
            quantity=1,
            reason="short-not-allowed",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_pullback_count",
        signals=signals,
        bars=bars,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 0


def test_run_backtest_skips_opening_bars_even_for_single_signal():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.4, 500.0, 500.3),
        _bar("2025-01-06T14:40:00+00:00", 500.3, 500.5, 500.2, 500.4),
        _bar("2025-01-06T20:55:00+00:00", 500.4, 500.6, 500.3, 500.5),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.3,
            quantity=1,
            reason="single-opening-signal",
            timestamp=datetime.fromisoformat("2025-01-06T14:35:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 0


def test_run_backtest_skips_opening_bars_enforces_cutoff_and_flattens_daily():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T14:40:00+00:00", 500.2, 500.7, 500.1, 500.6),
        _bar("2025-01-06T20:35:00+00:00", 500.6, 500.8, 500.5, 500.7),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.0, 500.6, 500.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.2,
            quantity=1,
            reason="skip-open",
            timestamp=datetime.fromisoformat("2025-01-06T14:35:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.6,
            quantity=1,
            reason="valid-entry",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.7,
            quantity=1,
            reason="after-cutoff",
            timestamp=datetime.fromisoformat("2025-01-06T20:35:00+00:00"),
        ),
    ]

    result = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"
    assert result.trades[0]["exit_time"] == "2025-01-06T20:55:00+00:00"
    assert result.trades[0]["exit_reason"] == "session_close"
