from datetime import datetime
from strategies.base import BaseStrategy, Signal, SignalType
from services.strategy_engine import register_strategy


@register_strategy
class MACrossoverStrategy(BaseStrategy):
    name = "ma_crossover"
    description = "Moving Average Crossover: buy when short MA crosses above long MA, sell when below."

    def default_params(self) -> dict:
        return {"short_period": 10, "long_period": 30, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        short_p = self.params.get("short_period", 10)
        long_p = self.params.get("long_period", 30)
        qty = self.params.get("quantity", 1)

        if len(bars) < long_p + 1:
            return []

        closes = [b["close"] for b in bars]
        signals = []

        for i in range(long_p, len(bars)):
            short_ma = sum(closes[i - short_p + 1 : i + 1]) / short_p
            long_ma = sum(closes[i - long_p + 1 : i + 1]) / long_p
            prev_short_ma = sum(closes[i - short_p : i]) / short_p
            prev_long_ma = sum(closes[i - long_p : i]) / long_p

            if prev_short_ma <= prev_long_ma and short_ma > long_ma:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=closes[i],
                    quantity=qty,
                    reason=f"MA{short_p} crossed above MA{long_p}",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))
            elif prev_short_ma >= prev_long_ma and short_ma < long_ma:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=closes[i],
                    quantity=qty,
                    reason=f"MA{short_p} crossed below MA{long_p}",
                    timestamp=datetime.fromisoformat(bars[i]["time"]),
                ))

        return signals
