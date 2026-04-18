from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from services.research_profile import get_research_profile, market_time, session_day
from strategies.base import Signal, SignalType


@dataclass(frozen=True)
class TradeRecord:
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    quantity: int
    pnl: float
    pnl_pct: float
    reason: str
    exit_reason: str


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    timeframe: str
    period: str
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "period": self.period,
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "total_return": round(self.total_return, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "trades": self.trades,
            "equity_curve": self.equity_curve,
        }


def run_backtest(
    strategy_name: str,
    signals: list[Signal],
    bars: list[dict],
    initial_capital: float = 100000.0,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    risk_per_trade_pct: float = 2.0,
    symbol: str = "QQQ",
    timeframe: str = "1D",
    research_profile: str | None = None,
) -> BacktestResult:
    """
    Simulate trades based on signals with stop-loss and take-profit.

    For each signal:
    - BUY: enter long, stop at entry * (1 - stop_loss_pct/100), TP at entry * (1 + take_profit_pct/100)
    - SELL: enter short, stop at entry * (1 + stop_loss_pct/100), TP at entry * (1 - take_profit_pct/100)

    Position sizing: risk_per_trade_pct of capital.
    """
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    trades: list[TradeRecord] = []
    equity_curve: list[dict] = []
    profile = get_research_profile(research_profile)

    # Build a time->bar index for quick lookup
    bar_list_idx = {}
    session_bar_index = {}
    session_last_bar = set()
    session_counts = {}
    session_signal_counts = {}
    for idx, bar in enumerate(bars):
        current_time = bar["time"]
        bar_list_idx[current_time] = idx
        day = session_day(current_time)
        session_counts[day] = session_counts.get(day, 0) + 1
        session_bar_index[current_time] = session_counts[day] - 1
        is_last_bar = idx == len(bars) - 1 or session_day(bars[idx + 1]["time"]) != day
        if is_last_bar:
            session_last_bar.add(current_time)

    # Track open position
    position = None  # {side, entry_price, stop, target, qty, entry_time, reason}

    # Sort signals by time
    sorted_signals = sorted(signals, key=lambda s: s.timestamp)
    signal_by_time = {}
    for sig in sorted_signals:
        signal_time = sig.timestamp.isoformat()
        signal_by_time[signal_time] = sig
        signal_day = session_day(signal_time)
        session_signal_counts[signal_day] = session_signal_counts.get(signal_day, 0) + 1

    def close_position(exit_time: str, exit_price: float, exit_reason: str) -> None:
        nonlocal capital, position
        if position is None:
            return

        if position["side"] == "long":
            pnl = (exit_price - position["entry_price"]) * position["qty"]
        else:
            pnl = (position["entry_price"] - exit_price) * position["qty"]

        pnl_pct = pnl / (position["entry_price"] * position["qty"]) * 100

        trades.append(TradeRecord(
            entry_time=position["entry_time"],
            exit_time=exit_time,
            side=position["side"],
            entry_price=position["entry_price"],
            exit_price=exit_price,
            stop_loss=position["stop"],
            quantity=position["qty"],
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=position["reason"],
            exit_reason=exit_reason,
        ))
        capital += pnl
        position = None

    # Walk through bars in order
    for i, bar in enumerate(bars):
        current_time = bar["time"]

        # Check if position should be closed by stop/target
        if position is not None:
            hit_stop = False
            hit_target = False

            if position["side"] == "long":
                if bar["low"] <= position["stop"]:
                    hit_stop = True
                    exit_price = position["stop"]
                elif bar["high"] >= position["target"]:
                    hit_target = True
                    exit_price = position["target"]
            else:  # short
                if bar["high"] >= position["stop"]:
                    hit_stop = True
                    exit_price = position["stop"]
                elif bar["low"] <= position["target"]:
                    hit_target = True
                    exit_price = position["target"]

            if hit_stop or hit_target:
                close_position(
                    exit_time=current_time,
                    exit_price=exit_price,
                    exit_reason="stop_loss" if hit_stop else "take_profit",
                )

        if (
            position is not None
            and profile is not None
            and profile.flatten_daily
            and current_time in session_last_bar
        ):
            close_position(
                exit_time=current_time,
                exit_price=bar["close"],
                exit_reason="session_close",
            )

        # Check for new signal on this bar (only enter if no position)
        if position is None and current_time in signal_by_time:
            sig = signal_by_time[current_time]
            if sig.signal_type in (SignalType.BUY, SignalType.SELL):
                if profile is not None:
                    if profile.long_only and sig.signal_type == SignalType.SELL:
                        continue
                    if (
                        session_signal_counts.get(session_day(current_time), 0) > 1
                        and session_bar_index.get(current_time, 0) < profile.skip_opening_bars
                    ):
                        continue
                    if (
                        profile.entry_cutoff is not None
                        and market_time(current_time).time() > profile.entry_cutoff
                    ):
                        continue

                entry_price = sig.price
                if entry_price <= 0:
                    continue

                # Position sizing based on risk
                risk_amount = capital * (risk_per_trade_pct / 100.0)
                stop_distance = entry_price * (stop_loss_pct / 100.0)
                if stop_distance <= 0:
                    continue
                qty = max(1, int(risk_amount / stop_distance))

                if sig.signal_type == SignalType.BUY:
                    stop = entry_price * (1 - stop_loss_pct / 100.0)
                    target = entry_price * (1 + take_profit_pct / 100.0)
                    side = "long"
                else:
                    stop = entry_price * (1 + stop_loss_pct / 100.0)
                    target = entry_price * (1 - take_profit_pct / 100.0)
                    side = "short"

                position = {
                    "side": side,
                    "entry_price": entry_price,
                    "stop": stop,
                    "target": target,
                    "qty": qty,
                    "entry_time": current_time,
                    "reason": sig.reason,
                }

        # Track equity
        unrealized = 0.0
        if position is not None:
            if position["side"] == "long":
                unrealized = (bar["close"] - position["entry_price"]) * position["qty"]
            else:
                unrealized = (position["entry_price"] - bar["close"]) * position["qty"]

        total_equity = capital + unrealized
        peak_capital = max(peak_capital, total_equity)
        dd = peak_capital - total_equity
        max_dd = max(max_dd, dd)

        equity_curve.append({
            "time": current_time,
            "equity": round(total_equity, 2),
        })

    # Close any remaining position at last bar close
    if position is not None and len(bars) > 0:
        last_bar = bars[-1]
        close_position(
            exit_time=last_bar["time"],
            exit_price=last_bar["close"],
            exit_reason="end_of_data",
        )

    # Compute statistics
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total = len(trades)
    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.99 if gross_profit > 0 else 0
    max_dd_pct = max_dd / peak_capital * 100 if peak_capital > 0 else 0

    # Sharpe ratio (annualized, using daily returns)
    if len(equity_curve) > 1:
        returns = []
        for j in range(1, len(equity_curve)):
            prev_eq = equity_curve[j - 1]["equity"]
            curr_eq = equity_curve[j]["equity"]
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)
        if returns:
            mean_r = sum(returns) / len(returns)
            std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 0
            sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    period_str = ""
    if len(bars) >= 2:
        period_str = f"{bars[0]['time'][:10]} ~ {bars[-1]['time'][:10]}"

    return BacktestResult(
        strategy=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        period=period_str,
        initial_capital=initial_capital,
        final_capital=capital,
        total_return=capital - initial_capital,
        total_return_pct=(capital - initial_capital) / initial_capital * 100,
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        sharpe_ratio=sharpe,
        trades=[
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "side": t.side,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "stop_loss": round(t.stop_loss, 2),
                "quantity": t.quantity,
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "reason": t.reason,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ],
        equity_curve=equity_curve,
    )
