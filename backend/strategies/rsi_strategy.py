from __future__ import annotations

from datetime import datetime
from strategies.base import BaseStrategy, Signal, SignalType
from services.strategy_engine import register_strategy


def _compute_rsi(closes: list[float], period: int) -> list[float | None]:
    """Compute RSI values. Returns list same length as closes, with None for insufficient data."""
    rsi_values: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return rsi_values

    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100 - (100 / (1 + rs))

    return rsi_values


@register_strategy
class RSIStrategy(BaseStrategy):
    name = "rsi"
    description = "RSI Strategy: buy when RSI drops below oversold, sell when RSI rises above overbought."

    def default_params(self) -> dict:
        return {"period": 14, "oversold": 30, "overbought": 70, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)
        qty = self.params.get("quantity", 1)

        closes = [b["close"] for b in bars]
        rsi_values = _compute_rsi(closes, period)
        signals = []

        for i in range(period + 1, len(bars)):
            prev_rsi = rsi_values[i - 1]
            curr_rsi = rsi_values[i]
            if prev_rsi is None or curr_rsi is None:
                continue

            if prev_rsi <= oversold and curr_rsi > oversold:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=closes[i],
                    quantity=qty,
                    reason=f"RSI crossed above {oversold} (RSI={curr_rsi:.1f})",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))
            elif prev_rsi >= overbought and curr_rsi < overbought:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=closes[i],
                    quantity=qty,
                    reason=f"RSI crossed below {overbought} (RSI={curr_rsi:.1f})",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))

        return signals
