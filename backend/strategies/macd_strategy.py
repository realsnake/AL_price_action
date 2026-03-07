from datetime import datetime
from strategies.base import BaseStrategy, Signal, SignalType
from services.strategy_engine import register_strategy


def _compute_ema(values: list[float], period: int) -> list[float]:
    """Compute EMA. Returns list same length as input."""
    ema = [0.0] * len(values)
    if len(values) < period:
        return ema
    multiplier = 2 / (period + 1)
    ema[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


@register_strategy
class MACDStrategy(BaseStrategy):
    name = "macd"
    description = "MACD Strategy: buy on bullish crossover (MACD crosses above signal), sell on bearish crossover."

    def default_params(self) -> dict:
        return {"fast": 12, "slow": 26, "signal": 9, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        fast_p = self.params.get("fast", 12)
        slow_p = self.params.get("slow", 26)
        signal_p = self.params.get("signal", 9)
        qty = self.params.get("quantity", 1)

        closes = [b["close"] for b in bars]
        if len(closes) < slow_p + signal_p:
            return []

        fast_ema = _compute_ema(closes, fast_p)
        slow_ema = _compute_ema(closes, slow_p)

        macd_line = [fast_ema[i] - slow_ema[i] for i in range(len(closes))]
        signal_line = _compute_ema(macd_line[slow_p - 1:], signal_p)
        # Pad signal_line to align with macd_line
        signal_line = [0.0] * (slow_p - 1) + signal_line

        start = slow_p + signal_p - 1
        signals = []

        for i in range(start, len(bars)):
            prev_macd = macd_line[i - 1]
            prev_signal = signal_line[i - 1]
            curr_macd = macd_line[i]
            curr_signal = signal_line[i]

            if prev_macd <= prev_signal and curr_macd > curr_signal:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=closes[i],
                    quantity=qty,
                    reason=f"MACD bullish crossover (MACD={curr_macd:.2f}, Signal={curr_signal:.2f})",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=closes[i],
                    quantity=qty,
                    reason=f"MACD bearish crossover (MACD={curr_macd:.2f}, Signal={curr_signal:.2f})",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))

        return signals
