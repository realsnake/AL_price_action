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


def test_run_backtest_uses_first_tradable_signal_when_multiple_share_timestamp():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T14:40:00+00:00", 500.2, 500.9, 500.1, 500.7),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.0, 500.6, 500.9),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.SELL,
            price=500.2,
            quantity=1,
            reason="short-not-allowed",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.6,
            quantity=1,
            reason="first-tradable-buy",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        ),
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.8,
            quantity=1,
            reason="later-buy",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        ),
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

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"
    assert result.trades[0]["entry_price"] == 500.6
    assert result.trades[0]["reason"] == "first-tradable-buy"


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


def test_run_backtest_rejects_new_entries_after_1400_et_for_phase1_profile():
    bars = [
        _bar("2025-01-06T18:55:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T19:00:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T19:05:00+00:00", 500.2, 500.5, 500.1, 500.4),
        _bar("2025-01-06T20:55:00+00:00", 500.4, 500.6, 500.3, 500.5),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.4,
            quantity=1,
            reason="after-1400-cutoff",
            timestamp=datetime.fromisoformat("2025-01-06T19:05:00+00:00"),
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


def test_run_backtest_uses_fixed_quantity_when_requested():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T14:40:00+00:00", 500.2, 500.8, 500.1, 500.7),
        _bar("2025-01-06T20:55:00+00:00", 500.7, 501.2, 500.6, 501.0),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.7,
            quantity=1,
            reason="fixed-qty-entry",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_breakout_pullback",
        signals=signals,
        bars=bars,
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        risk_per_trade_pct=2.0,
        fixed_quantity=3,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 1
    assert result.trades[0]["quantity"] == 3
    assert result.trades[0]["pnl"] == 0.9


def test_run_backtest_flattens_position_opened_on_session_final_bar():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 500.0, 500.2, 499.9, 500.1),
        _bar("2025-01-06T14:35:00+00:00", 500.1, 500.3, 500.0, 500.2),
        _bar("2025-01-06T14:40:00+00:00", 500.2, 500.4, 500.1, 500.3),
        _bar("2025-01-06T19:00:00+00:00", 500.3, 500.4, 500.2, 500.35),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.35,
            quantity=1,
            reason="enter-last-bar",
            timestamp=datetime.fromisoformat("2025-01-06T19:00:00+00:00"),
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

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T19:00:00+00:00"
    assert result.trades[0]["exit_time"] == "2025-01-06T19:00:00+00:00"
    assert result.trades[0]["exit_reason"] == "session_close"


def test_run_backtest_applies_unfavorable_slippage_to_entry_and_exit():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 100.0, 100.2, 99.9, 100.0),
        _bar("2025-01-06T14:35:00+00:00", 100.0, 100.2, 99.9, 100.0),
        _bar("2025-01-06T14:40:00+00:00", 101.0, 101.2, 100.8, 101.0),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=100.0,
            quantity=1,
            reason="slippage-entry",
            timestamp=datetime.fromisoformat("2025-01-06T14:35:00+00:00"),
        )
    ]

    baseline = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=50.0,
        take_profit_pct=50.0,
        fixed_quantity=10,
        symbol="QQQ",
        timeframe="5m",
    )
    slipped = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=50.0,
        take_profit_pct=50.0,
        fixed_quantity=10,
        slippage_bps=10.0,
        symbol="QQQ",
        timeframe="5m",
    )

    assert baseline.trades[0]["entry_price"] == 100.0
    assert baseline.trades[0]["exit_price"] == 101.0
    assert baseline.trades[0]["pnl"] == 10.0
    assert slipped.trades[0]["entry_price"] == 100.1
    assert slipped.trades[0]["exit_price"] == 100.9
    assert slipped.trades[0]["pnl"] == 7.99
