from datetime import datetime

from services.research_validation import build_strategy_validation_report
from strategies.base import Signal
from strategies.base import SignalType


def _bar(ts: str, close: float) -> dict:
    return {
        "time": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1000,
    }


class FirstBarStrategy:
    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        if len(bars) < 2:
            return []
        first = bars[0]
        return [
            Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=first["close"],
                quantity=1,
                reason="first-bar",
                timestamp=datetime.fromisoformat(first["time"]),
            )
        ]


class MonthBoundaryStrategy:
    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        signals = []
        for idx in range(1, len(bars)):
            prev = datetime.fromisoformat(bars[idx - 1]["time"])
            curr = datetime.fromisoformat(bars[idx]["time"])
            if prev.month == curr.month:
                continue
            signals.append(
                Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=bars[idx]["close"],
                    quantity=1,
                    reason="month-boundary",
                    timestamp=curr,
                )
            )
        return signals


class DailyFirstBarStrategy:
    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        signals = []
        seen_days = set()
        for bar in bars:
            day = bar["time"][:10]
            if day in seen_days:
                continue
            seen_days.add(day)
            signals.append(
                Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=bar["close"],
                    quantity=1,
                    reason="daily-first-bar",
                    timestamp=datetime.fromisoformat(bar["time"]),
                )
            )
        return signals


def test_build_strategy_validation_report_summarizes_monthly_and_rolling_windows():
    bars = [
        _bar("2025-01-02T15:00:00+00:00", 100.0),
        _bar("2025-01-31T15:00:00+00:00", 110.0),
        _bar("2025-02-03T15:00:00+00:00", 110.0),
        _bar("2025-02-28T15:00:00+00:00", 100.0),
        _bar("2025-03-03T15:00:00+00:00", 100.0),
        _bar("2025-03-31T15:00:00+00:00", 120.0),
        _bar("2025-04-01T15:00:00+00:00", 120.0),
        _bar("2025-04-30T15:00:00+00:00", 90.0),
    ]

    report = build_strategy_validation_report(
        strategy_name="dummy",
        bars=bars,
        symbol="QQQ",
        timeframe="1D",
        strategy=MonthBoundaryStrategy(),
        fixed_quantity=1,
        initial_capital=100.0,
        stop_loss_pct=50.0,
        take_profit_pct=200.0,
        rolling_windows=(2,),
    )

    assert report["monthly"]["summary"] == {
        "total_months": 4,
        "positive_months": 1,
        "median_return_pct": -5.0,
        "median_trades": 1.0,
        "best_month": {"label": "2025-03", "return_pct": 20.0, "trades": 1},
        "worst_month": {"label": "2025-04", "return_pct": -30.0, "trades": 1},
    }
    assert [window["label"] for window in report["monthly"]["windows"]] == [
        "2025-01",
        "2025-02",
        "2025-03",
        "2025-04",
    ]
    assert report["rolling"]["2m"]["summary"] == {
        "count": 3,
        "positive_windows": 1,
        "median_return_pct": -10.0,
        "median_trades": 1,
        "best_window": {"label": "2025-02->2025-03", "return_pct": 10.0, "trades": 1},
        "worst_window": {"label": "2025-01->2025-02", "return_pct": -10.0, "trades": 1},
    }
    assert [window["label"] for window in report["rolling"]["2m"]["windows"]] == [
        "2025-01->2025-02",
        "2025-02->2025-03",
        "2025-03->2025-04",
    ]


def test_build_strategy_validation_report_handles_empty_input():
    report = build_strategy_validation_report(
        strategy_name="dummy",
        bars=[],
        symbol="QQQ",
        timeframe="1D",
        strategy=FirstBarStrategy(),
    )

    assert report["combined"]["signals"] == 0
    assert report["combined"]["trades"] == 0
    assert report["monthly"]["summary"]["total_months"] == 0
    assert report["rolling"]["3m"]["summary"]["count"] == 0
    assert report["rolling"]["6m"]["summary"]["count"] == 0


def test_build_strategy_validation_report_includes_exit_reason_and_hold_stats():
    bars = [
        _bar("2025-01-02T15:00:00+00:00", 100.0),
        _bar("2025-01-03T15:05:00+00:00", 110.0),
    ]

    report = build_strategy_validation_report(
        strategy_name="dummy",
        bars=bars,
        symbol="QQQ",
        timeframe="1D",
        strategy=FirstBarStrategy(),
        fixed_quantity=1,
        initial_capital=100.0,
        stop_loss_pct=50.0,
        take_profit_pct=200.0,
        rolling_windows=(),
    )

    assert report["combined"]["exit_reasons"] == {"end_of_data": 1}
    assert report["combined"]["avg_hold_min"] == 1445.0
    assert report["combined"]["median_hold_min"] == 1445.0


def test_build_strategy_validation_report_includes_hold_to_close_benchmarks():
    bars = [
        _bar("2025-01-02T15:00:00+00:00", 100.0),
        _bar("2025-01-02T16:00:00+00:00", 110.0),
        _bar("2025-01-03T15:00:00+00:00", 200.0),
        _bar("2025-01-03T16:00:00+00:00", 220.0),
    ]

    report = build_strategy_validation_report(
        strategy_name="dummy",
        bars=bars,
        symbol="QQQ",
        timeframe="1D",
        strategy=DailyFirstBarStrategy(),
        fixed_quantity=1,
        initial_capital=100.0,
        stop_loss_pct=50.0,
        take_profit_pct=5.0,
        rolling_windows=(),
    )

    assert report["benchmarks"] == {
        "trade_count": 2,
        "eligible_bar_count": 4,
        "trade_avg_return_pct_to_close": 10.0,
        "trade_median_return_pct_to_close": 10.0,
        "eligible_avg_return_pct_to_close": 5.0,
        "eligible_median_return_pct_to_close": 5.0,
        "matched_slot_avg_return_pct_to_close": 10.0,
        "matched_slot_median_return_pct_to_close": 10.0,
    }
