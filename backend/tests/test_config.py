import importlib
import sys
from pathlib import Path


def test_database_url_defaults_to_backend_trader_db(monkeypatch):
    original_module = sys.modules.get("config")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("config", None)

    try:
        config = importlib.import_module("config")
    finally:
        if original_module is not None:
            sys.modules["config"] = original_module
        else:
            sys.modules.pop("config", None)

    expected = Path(__file__).resolve().parents[1] / "trader.db"
    assert config.DATABASE_URL == f"sqlite+aiosqlite:///{expected}"


def test_ibkr_config_parses_live_trading_controls(monkeypatch):
    original_module = sys.modules.get("config")
    monkeypatch.setenv("BROKER", "ibkr")
    monkeypatch.setenv("IBKR_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("IBKR_ORDER_TRANSMIT", "1")
    monkeypatch.setenv("IBKR_ALLOWED_SYMBOLS", "qqq, spy")
    monkeypatch.setenv("IBKR_MAX_ORDER_USD", "750.50")
    monkeypatch.setenv("IBKR_DAILY_MAX_NOTIONAL_USD", "1500")
    sys.modules.pop("config", None)

    try:
        config = importlib.import_module("config")
    finally:
        if original_module is not None:
            sys.modules["config"] = original_module
        else:
            sys.modules.pop("config", None)

    assert config.BROKER == "ibkr"
    assert config.IBKR_LIVE_TRADING_ENABLED is True
    assert config.IBKR_ORDER_TRANSMIT is True
    assert config.IBKR_ALLOWED_SYMBOLS == ("QQQ", "SPY")
    assert config.IBKR_MAX_ORDER_USD == 750.50
    assert config.IBKR_DAILY_MAX_NOTIONAL_USD == 1500.0
