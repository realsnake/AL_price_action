from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from services.phase1_exit import (
    build_dynamic_exit_update,
    build_exit_plan,
    compute_ema_series,
)
from services.research_profile import (
    canonical_timestamp,
    get_research_profile,
    market_time,
    session_day,
)
from strategies.base import Signal, SignalType


def _apply_slippage(price: float, side: str, slippage_bps: float) -> float:
    if slippage_bps <= 0:
        return price
    if side == "buy":
        return price * (1 + slippage_bps / 10000.0)
    if side == "sell":
        return price * (1 - slippage_bps / 10000.0)
    raise ValueError(f"Unknown slippage side: {side}")


@dataclass(frozen=True)
class TradeRecord:
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    target_price: float | None
    quantity: int
    pnl: float
    pnl_pct: float
    reason: str
    exit_reason: str
    stop_reason: str
    target_reason: str | None


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
    fixed_quantity: int | None = None,
    slippage_bps: float = 0.0,
    symbol: str = "QQQ",
    timeframe: str = "1D",
    research_profile: str | None = None,
    exit_policy: str | None = None,
) -> BacktestResult:
    """
    Simulate trades based on signals with stop-loss and take-profit.

    For each signal:
    - BUY: enter long, stop at entry * (1 - stop_loss_pct/100), TP at entry * (1 + take_profit_pct/100)
    - SELL: enter short, stop at entry * (1 + stop_loss_pct/100), TP at entry * (1 - take_profit_pct/100)

    Position sizing: risk_per_trade_pct of capital.
    """
    bars = [{**bar, "time": canonical_timestamp(bar["time"])} for bar in bars]
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    trades: list[TradeRecord] = []
    equity_curve: list[dict] = []
    profile = get_research_profile(research_profile)

    # Build a time->bar index for quick lookup
    session_bar_index = {}
    session_last_bar = set()
    session_counts = {}
    for idx, bar in enumerate(bars):
        current_time = bar["time"]
        day = session_day(current_time)
        session_counts[day] = session_counts.get(day, 0) + 1
        session_bar_index[current_time] = session_counts[day] - 1
        is_last_bar = idx == len(bars) - 1 or session_day(bars[idx + 1]["time"]) != day
        if is_last_bar:
            session_last_bar.add(current_time)

    # Track open position
    position = None  # {side, entry_price, stop, target, qty, entry_time, reason}
    ema_values = compute_ema_series(bars, 20)

    # Sort signals by time
    sorted_signals = sorted(signals, key=lambda s: s.timestamp)
    signal_by_time: dict[str, list[Signal]] = {}
    for sig in sorted_signals:
        signal_time = canonical_timestamp(sig.timestamp)
        signal_by_time.setdefault(signal_time, []).append(sig)

    def close_position(exit_time: str, exit_price: float, exit_reason: str) -> None:
        nonlocal capital, position
        if position is None:
            return

        exit_side = "sell" if position["side"] == "long" else "buy"
        filled_exit_price = _apply_slippage(exit_price, exit_side, slippage_bps)

        if position["side"] == "long":
            pnl = (filled_exit_price - position["entry_price"]) * position["qty"]
        else:
            pnl = (position["entry_price"] - filled_exit_price) * position["qty"]

        pnl_pct = pnl / (position["entry_price"] * position["qty"]) * 100

        trades.append(TradeRecord(
            entry_time=position["entry_time"],
            exit_time=exit_time,
            side=position["side"],
            entry_price=position["entry_price"],
            exit_price=filled_exit_price,
            stop_loss=position["stop"],
            target_price=position["target"],
            quantity=position["qty"],
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=position["reason"],
            exit_reason=exit_reason,
            stop_reason=position["stop_reason"],
            target_reason=position["target_reason"],
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
            dynamic_update = None
            candidate_max_favorable_price = position["max_favorable_price"]

            if position["side"] == "long":
                if bar["low"] <= position["stop"]:
                    hit_stop = True
                    exit_price = position["stop"]
                elif position["target"] is not None and bar["high"] >= position["target"]:
                    hit_target = True
                    exit_price = position["target"]
                else:
                    candidate_max_favorable_price = max(
                        position["max_favorable_price"],
                        float(bar["high"]),
                    )
                    dynamic_update = build_dynamic_exit_update(
                        strategy_name=strategy_name,
                        research_profile=research_profile,
                        exit_policy=exit_policy,
                        bars=bars,
                        bar_index=i,
                        ema_values=ema_values,
                        side=position["side"],
                        signal_time=position["signal_time"],
                        entry_price=position["entry_price"],
                        current_stop_price=position["stop"],
                        current_target_price=position["target"],
                        initial_risk=position["initial_risk"],
                        max_favorable_price=candidate_max_favorable_price,
                    )
            else:  # short
                if bar["high"] >= position["stop"]:
                    hit_stop = True
                    exit_price = position["stop"]
                elif position["target"] is not None and bar["low"] <= position["target"]:
                    hit_target = True
                    exit_price = position["target"]

            if hit_stop or hit_target:
                close_position(
                    exit_time=current_time,
                    exit_price=exit_price,
                    exit_reason="stop_loss" if hit_stop else "take_profit",
                )
            elif dynamic_update is not None and dynamic_update.exit_reason is not None:
                close_position(
                    exit_time=current_time,
                    exit_price=dynamic_update.exit_price,
                    exit_reason=dynamic_update.exit_reason,
                )
            elif position is not None and position["side"] == "long":
                if (
                    dynamic_update is not None
                    and dynamic_update.stop_price is not None
                    and dynamic_update.stop_price > position["stop"]
                ):
                    position["stop"] = dynamic_update.stop_price
                    position["stop_reason"] = (
                        dynamic_update.stop_reason or position["stop_reason"]
                    )
                if (
                    dynamic_update is not None
                    and dynamic_update.target_price is not None
                ):
                    position["target"] = dynamic_update.target_price
                    position["target_reason"] = dynamic_update.target_reason
                position["max_favorable_price"] = candidate_max_favorable_price

        # Check for new signal on this bar (only enter if no position)
        if position is None and current_time in signal_by_time:
            for sig in signal_by_time[current_time]:
                if sig.signal_type not in (SignalType.BUY, SignalType.SELL):
                    continue
                if profile is not None:
                    if profile.long_only and sig.signal_type == SignalType.SELL:
                        continue
                    if session_bar_index.get(current_time, 0) < profile.skip_opening_bars:
                        continue
                    if (
                        profile.entry_cutoff is not None
                        and market_time(current_time).time() > profile.entry_cutoff
                    ):
                        continue

                signal_price = sig.price
                if signal_price <= 0:
                    continue

                entry_side = "buy" if sig.signal_type == SignalType.BUY else "sell"
                entry_price = _apply_slippage(signal_price, entry_side, slippage_bps)
                side = "long" if sig.signal_type == SignalType.BUY else "short"
                exit_plan = build_exit_plan(
                    strategy_name=strategy_name,
                    research_profile=research_profile,
                    bars=bars,
                    signal_time=current_time,
                    side=side,
                    entry_price=entry_price,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    exit_policy=exit_policy,
                )

                if fixed_quantity is not None:
                    qty = fixed_quantity
                else:
                    # Position sizing based on risk
                    risk_amount = capital * (risk_per_trade_pct / 100.0)
                    stop_distance = abs(entry_price - exit_plan.stop_price)
                    if stop_distance <= 0:
                        continue
                    qty = max(1, int(risk_amount / stop_distance))

                position = {
                    "side": side,
                    "entry_price": entry_price,
                    "stop": exit_plan.stop_price,
                    "target": exit_plan.target_price,
                    "qty": qty,
                    "entry_time": current_time,
                    "reason": sig.reason,
                    "stop_reason": exit_plan.stop_reason,
                    "target_reason": exit_plan.target_reason,
                    "initial_risk": abs(entry_price - exit_plan.stop_price),
                    "max_favorable_price": entry_price,
                    "signal_time": current_time,
                }
                break

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
                "target_price": round(t.target_price, 2) if t.target_price is not None else None,
                "quantity": t.quantity,
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "reason": t.reason,
                "exit_reason": t.exit_reason,
                "stop_reason": t.stop_reason,
                "target_reason": t.target_reason,
            }
            for t in trades
        ],
        equity_curve=equity_curve,
    )
