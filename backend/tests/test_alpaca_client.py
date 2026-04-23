import importlib
import sys
from datetime import datetime, timezone

import pytest


def _reload_alpaca_client_module(monkeypatch):
    config = importlib.import_module("config")
    original_module = sys.modules.get("services.alpaca_client")
    monkeypatch.setattr(config, "ALPACA_API_KEY", "")
    monkeypatch.setattr(config, "ALPACA_SECRET_KEY", "")
    sys.modules.pop("services.alpaca_client", None)
    try:
        return importlib.import_module("services.alpaca_client")
    finally:
        if original_module is not None:
            sys.modules["services.alpaca_client"] = original_module
        else:
            sys.modules.pop("services.alpaca_client", None)


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_alpaca_client_imports_without_credentials(monkeypatch):
    module = _reload_alpaca_client_module(monkeypatch)

    assert module.alpaca_client.is_configured() is False


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_alpaca_client_raises_only_on_real_usage(monkeypatch):
    module = _reload_alpaca_client_module(monkeypatch)

    with pytest.raises(
        module.AlpacaNotConfiguredError,
        match="Alpaca credentials are not configured",
    ):
        module.alpaca_client.get_quote("AAPL")


def test_alpaca_client_uses_crypto_historical_client_for_crypto_symbols(monkeypatch):
    from services import alpaca_client as alpaca_client_module

    class _FakeBar:
        def __init__(self):
            self.timestamp = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)
            self.open = 98000.0
            self.high = 98500.0
            self.low = 97800.0
            self.close = 98250.0
            self.volume = 42

    class _FakeCryptoClient:
        def __init__(self):
            self.request = None

        def get_crypto_bars(self, request):
            self.request = request
            return {"BTC/USD": [_FakeBar()]}

    client = _FakeCryptoClient()

    monkeypatch.setattr(
        alpaca_client_module.alpaca_client,
        "_get_crypto_data_client",
        lambda: client,
    )

    bars = alpaca_client_module.alpaca_client.get_bars(
        "BTC/USD",
        "5m",
        "2025-01-01T00:00:00+00:00",
        "2025-01-02T00:00:00+00:00",
        None,
    )

    assert bars == [
        {
            "time": "2025-01-06T00:00:00+00:00",
            "open": 98000.0,
            "high": 98500.0,
            "low": 97800.0,
            "close": 98250.0,
            "volume": 42,
        }
    ]
    assert client.request.symbol_or_symbols == "BTC/USD"
    assert client.request.limit is None
