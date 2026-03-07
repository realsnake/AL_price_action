from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    symbol: str
    signal_type: SignalType
    price: float
    quantity: int
    reason: str
    timestamp: datetime


class BaseStrategy(ABC):
    name: str = "base"
    description: str = ""

    def __init__(self, params: dict | None = None):
        self.params = params or self.default_params()

    @abstractmethod
    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        """Input K-line bars, output trading signals."""
        pass

    @abstractmethod
    def default_params(self) -> dict:
        """Return default parameters for this strategy."""
        pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "params": self.params,
            "default_params": self.default_params(),
        }
