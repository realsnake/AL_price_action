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
