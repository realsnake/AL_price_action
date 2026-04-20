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


def test_run_backtest_phase1_small_pb_uses_structural_stop_instead_of_fixed_pct():
    bars = [
        _bar("2025-01-06T14:30:00+00:00", 499.8, 500.2, 499.4, 500.0),
        _bar("2025-01-06T14:35:00+00:00", 500.0, 500.3, 498.0, 499.1),
        _bar("2025-01-06T14:40:00+00:00", 499.1, 500.8, 498.6, 500.7),
        _bar("2025-01-06T14:45:00+00:00", 500.7, 500.9, 497.9, 498.4),
        _bar("2025-01-06T20:55:00+00:00", 498.4, 498.8, 498.3, 498.5),
    ]
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=500.7,
            quantity=1,
            reason="phase1-structural-stop",
            timestamp=datetime.fromisoformat("2025-01-06T14:40:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=50.0,
        take_profit_pct=50.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T14:40:00+00:00"
    assert result.trades[0]["exit_time"] == "2025-01-06T14:45:00+00:00"
    assert result.trades[0]["exit_reason"] == "stop_loss"
    assert result.trades[0]["stop_loss"] == 498.0
    assert result.trades[0]["target_price"] is None
    assert result.trades[0]["target_reason"] is None


def test_run_backtest_phase1_small_pb_exits_on_strong_bear_below_ema_after_1r():
    bars = []
    price = 101.8
    hour = 14
    minute = 30
    for idx in range(18):
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
            _bar("2025-01-06T20:55:00+00:00", 102.0, 102.1, 101.9, 102.05),
        ]
    )
    signals = [
        Signal(
            symbol="QQQ",
            signal_type=SignalType.BUY,
            price=102.3,
            quantity=1,
            reason="phase1-dynamic-exit",
            timestamp=datetime.fromisoformat("2025-01-06T16:05:00+00:00"),
        )
    ]

    result = run_backtest(
        strategy_name="brooks_small_pb_trend",
        signals=signals,
        bars=bars,
        stop_loss_pct=50.0,
        take_profit_pct=50.0,
        fixed_quantity=100,
        slippage_bps=0.0,
        symbol="QQQ",
        timeframe="5m",
        research_profile="qqq_5m_phase1",
    )

    assert result.total_trades == 1
    assert result.trades[0]["entry_time"] == "2025-01-06T16:05:00+00:00"
    assert result.trades[0]["exit_time"] == "2025-01-06T16:25:00+00:00"
    assert (
        result.trades[0]["exit_reason"]
        == "phase1_confirmed_swing_low_break_after_1r"
    )
    assert result.trades[0]["exit_price"] == 102.0
