import importlib
import sys
from datetime import datetime, timedelta, timezone

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


def test_alpaca_client_quote_includes_previous_close(monkeypatch):
    from services import alpaca_client as alpaca_client_module

    class _FakeQuote:
        bid_price = 661.5
        ask_price = 661.7
        bid_size = 12
        ask_size = 14
        timestamp = datetime(2026, 4, 27, 14, 30, tzinfo=timezone.utc)

    class _FakeBar:
        def __init__(self, close: float, timestamp: datetime):
            self.close = close
            self.timestamp = timestamp

    class _FakeStockClient:
        def __init__(self):
            self.quote_request = None
            self.bars_request = None

        def get_stock_latest_quote(self, request):
            self.quote_request = request
            return {"QQQ": _FakeQuote()}

        def get_stock_bars(self, request):
            self.bars_request = request
            return {
                "QQQ": [
                    _FakeBar(646.775, datetime(2026, 4, 20, 4, 0, tzinfo=timezone.utc)),
                    _FakeBar(644.24, datetime(2026, 4, 21, 4, 0, tzinfo=timezone.utc)),
                    _FakeBar(655.085, datetime(2026, 4, 22, 4, 0, tzinfo=timezone.utc)),
                    _FakeBar(651.4, datetime(2026, 4, 23, 4, 0, tzinfo=timezone.utc)),
                    _FakeBar(663.92, datetime(2026, 4, 24, 4, 0, tzinfo=timezone.utc)),
                    _FakeBar(662.34, datetime(2026, 4, 27, 4, 0, tzinfo=timezone.utc)),
                ]
            }

    client = _FakeStockClient()

    monkeypatch.setattr(
        alpaca_client_module.alpaca_client,
        "_get_data_client",
        lambda: client,
    )
    fixed_now = datetime(2026, 4, 27, 14, 35, tzinfo=timezone.utc)
    quote_timestamp = datetime(2026, 4, 27, 14, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(alpaca_client_module, "datetime", _FixedDateTime(fixed_now))

    quote = alpaca_client_module.alpaca_client.get_quote("QQQ")

    assert quote == {
        "symbol": "QQQ",
        "bid": 661.5,
        "ask": 661.7,
        "bid_size": 12,
        "ask_size": 14,
        "timestamp": "2026-04-27T14:30:00+00:00",
        "previous_close": 663.92,
    }
    assert client.quote_request.symbol_or_symbols == "QQQ"
    assert client.bars_request.symbol_or_symbols == "QQQ"
    assert client.bars_request.limit == 10
    assert client.bars_request.start == (quote_timestamp - timedelta(days=10)).replace(tzinfo=None)


def test_alpaca_client_wraps_rest_session_with_default_timeout():
    from services import alpaca_client as alpaca_client_module

    calls = []

    class _FakeSession:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return {"ok": True}

    class _FakeRestClient:
        def __init__(self):
            self._session = _FakeSession()

    client = _FakeRestClient()

    alpaca_client_module.alpaca_client._configure_rest_client(client)
    result = client._session.request("GET", "https://example.test/v2/foo")

    assert result == {"ok": True}
    assert calls == [
        (
            "GET",
            "https://example.test/v2/foo",
            {"timeout": alpaca_client_module.DEFAULT_REQUEST_TIMEOUT_SECONDS},
        )
    ]


def test_alpaca_client_preserves_explicit_rest_timeout():
    from services import alpaca_client as alpaca_client_module

    calls = []

    class _FakeSession:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return {"ok": True}

    class _FakeRestClient:
        def __init__(self):
            self._session = _FakeSession()

    client = _FakeRestClient()

    alpaca_client_module.alpaca_client._configure_rest_client(client)
    client._session.request("GET", "https://example.test/v2/foo", timeout=2.5)

    assert calls == [
        (
            "GET",
            "https://example.test/v2/foo",
            {"timeout": 2.5},
        )
    ]


class _FixedDateTime:
    def __init__(self, fixed_now: datetime):
        self._fixed_now = fixed_now

    def now(self, tz=None):
        if tz is None:
            return self._fixed_now
        return self._fixed_now.astimezone(tz)
