import importlib
import sys

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
