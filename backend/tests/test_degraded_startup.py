import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from services import alpaca_client, market_data


def _reload_main_module():
    sys.modules.pop("main", None)
    return importlib.import_module("main")


@pytest.mark.usefixtures("without_alpaca_credentials")
def test_health_reports_degraded_without_credentials(monkeypatch):
    monkeypatch.setattr(alpaca_client, "ALPACA_API_KEY", "")
    monkeypatch.setattr(alpaca_client, "ALPACA_SECRET_KEY", "")
    monkeypatch.setattr(market_data, "ALPACA_API_KEY", "")
    monkeypatch.setattr(market_data, "ALPACA_SECRET_KEY", "")

    main = _reload_main_module()

    async def fake_init_db():
        return None

    monkeypatch.setattr(main, "init_db", fake_init_db)

    with TestClient(main.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "alpaca_configured": False,
        "live_stream_enabled": False,
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("without_alpaca_credentials")
async def test_start_stream_is_noop_without_credentials(monkeypatch):
    monkeypatch.setattr(alpaca_client, "ALPACA_API_KEY", "")
    monkeypatch.setattr(alpaca_client, "ALPACA_SECRET_KEY", "")
    monkeypatch.setattr(market_data, "ALPACA_API_KEY", "")
    monkeypatch.setattr(market_data, "ALPACA_SECRET_KEY", "")

    called = {"value": False}

    def fake_get_stream():
        called["value"] = True
        raise AssertionError("stream should not be created without credentials")

    monkeypatch.setattr(market_data, "_get_stream", fake_get_stream)
    monkeypatch.setattr(market_data, "_stream_task", None)
    monkeypatch.setattr(market_data, "_stream", None)

    await market_data.start_stream()

    assert called["value"] is False
    assert market_data._stream_task is None
