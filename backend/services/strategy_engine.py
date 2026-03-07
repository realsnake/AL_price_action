from __future__ import annotations

import importlib
import json
from strategies.base import BaseStrategy, Signal

# Registry of available strategies
_registry: dict[str, type[BaseStrategy]] = {}


def register_strategy(cls: type[BaseStrategy]):
    _registry[cls.name] = cls
    return cls


def get_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    if name not in _registry:
        raise ValueError(f"Unknown strategy: {name}")
    return _registry[name](params)


def list_strategies() -> list[dict]:
    return [cls(None).to_dict() for cls in _registry.values()]


def run_strategy(name: str, symbol: str, bars: list[dict], params: dict | None = None) -> list[dict]:
    strategy = get_strategy(name, params)
    signals = strategy.generate_signals(symbol, bars)
    return [
        {
            "symbol": s.symbol,
            "signal_type": s.signal_type.value,
            "price": s.price,
            "quantity": s.quantity,
            "reason": s.reason,
            "timestamp": s.timestamp.isoformat(),
        }
        for s in signals
    ]


def _load_builtin_strategies():
    """Import all strategy modules in the strategies/ directory to trigger registration."""
    import pathlib
    import logging

    logger = logging.getLogger(__name__)
    strategies_dir = pathlib.Path(__file__).resolve().parent.parent / "strategies"

    for path in strategies_dir.glob("*.py"):
        if path.name.startswith("_") or path.name == "base.py":
            continue
        module_name = path.stem
        try:
            importlib.import_module(f"strategies.{module_name}")
        except Exception as e:
            logger.warning(f"Failed to load strategy module '{module_name}': {e}")


_load_builtin_strategies()
