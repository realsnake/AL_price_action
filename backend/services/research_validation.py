from __future__ import annotations

from collections import Counter
from collections import OrderedDict
from datetime import datetime
from statistics import median
from typing import Iterable

from services.backtester import BacktestResult, run_backtest
from services.research_profile import (
    canonical_timestamp,
    get_research_profile,
    market_time,
    session_day,
)
from services.strategy_engine import get_strategy


def build_strategy_validation_report(
    strategy_name: str,
    bars: list[dict],
    *,
    symbol: str = "QQQ",
    timeframe: str = "5m",
    research_profile: str | None = None,
    fixed_quantity: int | None = None,
    initial_capital: float = 100000.0,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    risk_per_trade_pct: float = 2.0,
    slippage_bps: float = 0.0,
    rolling_windows: tuple[int, ...] = (3, 6),
    exit_policy: str | None = None,
    signals: list | None = None,
    strategy=None,
) -> dict:
    bars = [{**bar, "time": canonical_timestamp(bar["time"])} for bar in bars]
    strategy_impl = strategy or get_strategy(strategy_name)
    monthly_groups = _group_bars_by_month(bars)
    all_bars = list(bars)

    combined_signals, combined_result = _run_validation_window(
        strategy_impl=strategy_impl,
        strategy_name=strategy_name,
        bars=all_bars,
        symbol=symbol,
        timeframe=timeframe,
        research_profile=research_profile,
        fixed_quantity=fixed_quantity,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        risk_per_trade_pct=risk_per_trade_pct,
        slippage_bps=slippage_bps,
        exit_policy=exit_policy,
        precomputed_signals=signals,
    )

    monthly_windows = [
        _build_window_entry(
            label=label,
            bars=month_bars,
            signal_bars=_window_signal_bars(all_bars, month_bars),
            strategy_impl=strategy_impl,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            research_profile=research_profile,
            fixed_quantity=fixed_quantity,
            initial_capital=initial_capital,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            exit_policy=exit_policy,
            precomputed_signals=signals,
        )
        for label, month_bars in monthly_groups.items()
    ]

    rolling = {}
    for window_size in rolling_windows:
        windows = []
        labels = list(monthly_groups.keys())
        for start in range(0, max(0, len(labels) - window_size + 1)):
            window_labels = labels[start:start + window_size]
            window_bars = []
            for label in window_labels:
                window_bars.extend(monthly_groups[label])
            windows.append(
                _build_window_entry(
                    label=f"{window_labels[0]}->{window_labels[-1]}",
                    bars=window_bars,
                    signal_bars=_window_signal_bars(all_bars, window_bars),
                    strategy_impl=strategy_impl,
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    research_profile=research_profile,
                    fixed_quantity=fixed_quantity,
                    initial_capital=initial_capital,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    risk_per_trade_pct=risk_per_trade_pct,
                    slippage_bps=slippage_bps,
                    exit_policy=exit_policy,
                    precomputed_signals=signals,
                )
            )
        rolling[f"{window_size}m"] = {
            "summary": _summarize_windows(windows, positive_key="positive_windows"),
            "windows": windows,
        }

    recent_trade_days = _summarize_recent_trade_days(
        combined_result.trades,
        initial_capital=initial_capital,
        day_count=12,
    )
    latest_3m = _latest_rolling_window_snapshot(rolling, "3m")

    return {
        "strategy": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "research_profile": research_profile,
        "exit_policy": exit_policy,
        "fixed_quantity": fixed_quantity,
        "slippage_bps": slippage_bps,
        "combined": _result_snapshot(len(combined_signals), combined_result),
        "benchmarks": _hold_to_close_benchmarks(combined_result.trades, all_bars, research_profile),
        "monthly": {
            "summary": _summarize_windows(monthly_windows, total_key="total_months", positive_key="positive_months"),
            "windows": monthly_windows,
        },
        "rolling": rolling,
        "recent": {
            "last_12_trade_days": recent_trade_days,
            "latest_3m": latest_3m,
            "gate_passed": recent_trade_days["positive"] and latest_3m["positive"],
        },
    }


def _group_bars_by_month(bars: list[dict]) -> OrderedDict[str, list[dict]]:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for bar in bars:
        label = market_time(bar["time"]).strftime("%Y-%m")
        grouped.setdefault(label, []).append(bar)
    return grouped


def _build_window_entry(
    *,
    label: str,
    bars: list[dict],
    signal_bars: list[dict],
    strategy_impl,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    research_profile: str | None,
    fixed_quantity: int | None,
    initial_capital: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    risk_per_trade_pct: float,
    slippage_bps: float,
    exit_policy: str | None,
    precomputed_signals: list | None,
) -> dict:
    signals, result = _run_validation_window(
        strategy_impl=strategy_impl,
        strategy_name=strategy_name,
        bars=bars,
        signal_bars=signal_bars,
        symbol=symbol,
        timeframe=timeframe,
        research_profile=research_profile,
        fixed_quantity=fixed_quantity,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        risk_per_trade_pct=risk_per_trade_pct,
        slippage_bps=slippage_bps,
        exit_policy=exit_policy,
        precomputed_signals=precomputed_signals,
    )
    return {"label": label, **_result_snapshot(len(signals), result)}


def _run_validation_window(
    *,
    strategy_impl,
    strategy_name: str,
    bars: list[dict],
    signal_bars: list[dict] | None = None,
    symbol: str,
    timeframe: str,
    research_profile: str | None,
    fixed_quantity: int | None,
    initial_capital: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    risk_per_trade_pct: float,
    slippage_bps: float,
    exit_policy: str | None,
    precomputed_signals: list | None,
) -> tuple[list, BacktestResult]:
    window_times = {bar["time"] for bar in bars}
    if precomputed_signals is None:
        source_bars = signal_bars if signal_bars is not None else bars
        signals = strategy_impl.generate_signals(symbol, source_bars)
        signals = [
            signal
            for signal in signals
            if canonical_timestamp(signal.timestamp) in window_times
        ]
    else:
        signals = [
            signal
            for signal in precomputed_signals
            if canonical_timestamp(signal.timestamp) in window_times
        ]
    result = run_backtest(
        strategy_name=strategy_name,
        signals=signals,
        bars=bars,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        risk_per_trade_pct=risk_per_trade_pct,
        fixed_quantity=fixed_quantity,
        slippage_bps=slippage_bps,
        symbol=symbol,
        timeframe=timeframe,
        research_profile=research_profile,
        exit_policy=exit_policy,
    )
    return signals, result


def _window_signal_bars(all_bars: list[dict], window_bars: list[dict]) -> list[dict]:
    if not window_bars:
        return []
    end_time = datetime.fromisoformat(window_bars[-1]["time"])
    return [
        bar
        for bar in all_bars
        if datetime.fromisoformat(bar["time"]) <= end_time
    ]


def _result_snapshot(signal_count: int, result: BacktestResult) -> dict:
    exit_reasons = Counter(trade["exit_reason"] for trade in result.trades)
    hold_minutes = [
        (datetime.fromisoformat(trade["exit_time"]) - datetime.fromisoformat(trade["entry_time"])).total_seconds() / 60.0
        for trade in result.trades
    ]
    return {
        "signals": signal_count,
        "trades": result.total_trades,
        "return_pct": round(result.total_return_pct, 2),
        "profit_factor": round(result.profit_factor, 2),
        "win_rate": round(result.win_rate, 2),
        "max_dd_pct": round(result.max_drawdown_pct, 2),
        "exit_reasons": dict(exit_reasons),
        "avg_hold_min": round(sum(hold_minutes) / len(hold_minutes), 1) if hold_minutes else 0.0,
        "median_hold_min": round(median(hold_minutes), 1) if hold_minutes else 0.0,
    }


def _hold_to_close_benchmarks(
    trades: list[dict],
    bars: list[dict],
    research_profile: str | None,
) -> dict:
    if not trades or not bars:
        return {
            "trade_count": 0,
            "eligible_bar_count": 0,
            "trade_avg_return_pct_to_close": 0.0,
            "trade_median_return_pct_to_close": 0.0,
            "eligible_avg_return_pct_to_close": 0.0,
            "eligible_median_return_pct_to_close": 0.0,
            "matched_slot_avg_return_pct_to_close": 0.0,
            "matched_slot_median_return_pct_to_close": 0.0,
        }

    profile = get_research_profile(research_profile)
    session_counts: dict[str, int] = {}
    session_index_by_time: dict[str, int] = {}
    session_close_by_day: dict[str, float] = {}
    for idx, bar in enumerate(bars):
        day = session_day(bar["time"])
        session_counts[day] = session_counts.get(day, 0) + 1
        session_index_by_time[bar["time"]] = session_counts[day] - 1
        if idx == len(bars) - 1 or session_day(bars[idx + 1]["time"]) != day:
            session_close_by_day[day] = bar["close"]

    bars_by_time = {bar["time"]: bar for bar in bars}
    eligible_returns: list[float] = []
    slot_returns: dict[tuple[str, str], list[float]] = {}

    for bar in bars:
        if profile is not None:
            if session_index_by_time.get(bar["time"], 0) < profile.skip_opening_bars:
                continue
            if profile.entry_cutoff is not None and market_time(bar["time"]).time() > profile.entry_cutoff:
                continue
        day = session_day(bar["time"])
        session_close = session_close_by_day[day]
        slot = market_time(bar["time"]).strftime("%H:%M")
        long_return = (session_close - bar["close"]) / bar["close"] * 100 if bar["close"] else 0.0
        short_return = (bar["close"] - session_close) / bar["close"] * 100 if bar["close"] else 0.0
        eligible_returns.append(long_return)
        slot_returns.setdefault(("long", slot), []).append(long_return)
        slot_returns.setdefault(("short", slot), []).append(short_return)

    trade_returns: list[float] = []
    matched_slot_returns: list[float] = []
    for trade in trades:
        entry_bar = bars_by_time.get(trade["entry_time"])
        if entry_bar is None or entry_bar["close"] == 0:
            continue
        day = session_day(trade["entry_time"])
        session_close = session_close_by_day[day]
        slot = market_time(trade["entry_time"]).strftime("%H:%M")
        if trade["side"] == "long":
            trade_return = (session_close - entry_bar["close"]) / entry_bar["close"] * 100
            slot_key = ("long", slot)
        else:
            trade_return = (entry_bar["close"] - session_close) / entry_bar["close"] * 100
            slot_key = ("short", slot)
        trade_returns.append(trade_return)
        slot_values = slot_returns.get(slot_key, [])
        if slot_values:
            matched_slot_returns.append(sum(slot_values) / len(slot_values))

    return {
        "trade_count": len(trade_returns),
        "eligible_bar_count": len(eligible_returns),
        "trade_avg_return_pct_to_close": round(sum(trade_returns) / len(trade_returns), 4) if trade_returns else 0.0,
        "trade_median_return_pct_to_close": round(median(trade_returns), 4) if trade_returns else 0.0,
        "eligible_avg_return_pct_to_close": round(sum(eligible_returns) / len(eligible_returns), 4) if eligible_returns else 0.0,
        "eligible_median_return_pct_to_close": round(median(eligible_returns), 4) if eligible_returns else 0.0,
        "matched_slot_avg_return_pct_to_close": round(sum(matched_slot_returns) / len(matched_slot_returns), 4) if matched_slot_returns else 0.0,
        "matched_slot_median_return_pct_to_close": round(median(matched_slot_returns), 4) if matched_slot_returns else 0.0,
    }


def _summarize_windows(
    windows: Iterable[dict],
    *,
    total_key: str = "count",
    positive_key: str = "positive",
) -> dict:
    entries = list(windows)
    if not entries:
        return {
            total_key: 0,
            positive_key: 0,
            "median_return_pct": 0.0,
            "median_trades": 0.0,
            "best_month" if total_key == "total_months" else "best_window": None,
            "worst_month" if total_key == "total_months" else "worst_window": None,
        }

    positive = sum(1 for entry in entries if entry["return_pct"] > 0)
    returns = [entry["return_pct"] for entry in entries]
    trades = [entry["trades"] for entry in entries]
    best = max(entries, key=lambda entry: entry["return_pct"])
    worst = min(entries, key=lambda entry: entry["return_pct"])
    best_key = "best_month" if total_key == "total_months" else "best_window"
    worst_key = "worst_month" if total_key == "total_months" else "worst_window"
    return {
        total_key: len(entries),
        positive_key: positive,
        "median_return_pct": round(median(returns), 2),
        "median_trades": round(median(trades), 1),
        best_key: {
            "label": best["label"],
            "return_pct": best["return_pct"],
            "trades": best["trades"],
        },
        worst_key: {
            "label": worst["label"],
            "return_pct": worst["return_pct"],
            "trades": worst["trades"],
        },
    }


def _summarize_recent_trade_days(
    trades: list[dict],
    *,
    initial_capital: float,
    day_count: int,
) -> dict:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for trade in trades:
        grouped.setdefault(session_day(trade["entry_time"]), []).append(trade)

    recent_days = list(grouped.keys())[-day_count:]
    recent_trades = [trade for day in recent_days for trade in grouped.get(day, [])]
    pnl = sum(float(trade["pnl"]) for trade in recent_trades)
    wins = sum(1 for trade in recent_trades if float(trade["pnl"]) > 0)
    losses = sum(1 for trade in recent_trades if float(trade["pnl"]) < 0)
    return_pct = pnl / initial_capital * 100 if initial_capital else 0.0
    period = (
        f"{recent_days[0]} ~ {recent_days[-1]}"
        if recent_days
        else ""
    )
    return {
        "days": len(recent_days),
        "trades": len(recent_trades),
        "period": period,
        "pnl": round(pnl, 2),
        "return_pct": round(return_pct, 2),
        "wins": wins,
        "losses": losses,
        "positive": pnl > 0,
    }


def _latest_rolling_window_snapshot(
    rolling: dict,
    bucket: str,
) -> dict:
    windows = rolling.get(bucket, {}).get("windows", [])
    if not windows:
        return {
            "label": "",
            "return_pct": 0.0,
            "trades": 0,
            "positive": False,
        }

    latest = windows[-1]
    return {
        "label": latest["label"],
        "return_pct": latest["return_pct"],
        "trades": latest["trades"],
        "positive": latest["return_pct"] > 0,
    }
