import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")

DEFAULT_DB_PATH = Path(__file__).resolve().with_name("trader.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# Paper trading by default
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# Trading broker selection. Market data remains Alpaca-backed unless changed
# elsewhere; this controls account/order execution paths only.
BROKER = os.getenv("BROKER", "alpaca").strip().lower()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


# IBKR live-trading controls. These defaults are intentionally conservative:
# selecting BROKER=ibkr is not enough to transmit real orders.
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = _env_int("IBKR_PORT", 7496)
IBKR_CLIENT_ID = _env_int("IBKR_CLIENT_ID", 17)
IBKR_ACCOUNT = os.getenv("IBKR_ACCOUNT", "").strip()
IBKR_LIVE_TRADING_ENABLED = _env_bool("IBKR_LIVE_TRADING_ENABLED", False)
IBKR_ORDER_TRANSMIT = _env_bool("IBKR_ORDER_TRANSMIT", False)
IBKR_ALLOWED_SYMBOLS = _env_csv("IBKR_ALLOWED_SYMBOLS", "QQQ")
IBKR_MAX_ORDER_USD = _env_float("IBKR_MAX_ORDER_USD", 750.0)
IBKR_DAILY_MAX_NOTIONAL_USD = _env_float("IBKR_DAILY_MAX_NOTIONAL_USD", 1500.0)
IBKR_ALLOW_STRATEGY_TRADING = _env_bool("IBKR_ALLOW_STRATEGY_TRADING", False)
IBKR_REQUEST_TIMEOUT_SECONDS = _env_float("IBKR_REQUEST_TIMEOUT_SECONDS", 8.0)
