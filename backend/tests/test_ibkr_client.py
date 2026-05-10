from __future__ import annotations

import concurrent.futures
import time

import pytest

from services.ibkr_client import IBKRClient
from services.ibkr_client import IBKRNotConfiguredError
from services.ibkr_client import IBKRSafetyError
from services.ibkr_client import IBKRSettings


def test_ibkr_order_submission_requires_live_trading_enabled():
    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=False,
            order_transmit=False,
            allowed_symbols=("QQQ",),
            max_order_usd=750.0,
        )
    )

    with pytest.raises(IBKRNotConfiguredError, match="IBKR live trading is not enabled"):
        client.submit_order(
            "QQQ",
            1,
            "buy",
            order_type="limit",
            limit_price=500.0,
            confirm_live=True,
        )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {"order_type": "market", "limit_price": None, "confirm_live": True},
            "IBKR live orders require order_type='limit'",
        ),
        (
            {"order_type": "limit", "limit_price": None, "confirm_live": True},
            "IBKR live orders require a positive limit_price",
        ),
        (
            {"order_type": "limit", "limit_price": 500.0, "confirm_live": False},
            "IBKR live orders require confirm_live=true",
        ),
    ],
)
def test_ibkr_live_orders_require_limit_price_and_confirmation(kwargs, match):
    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=True,
            order_transmit=True,
            allowed_symbols=("QQQ",),
            max_order_usd=750.0,
        )
    )

    with pytest.raises(IBKRSafetyError, match=match):
        client.submit_order("QQQ", 1, "buy", **kwargs)


def test_ibkr_live_orders_enforce_allowed_symbols_and_notional_cap():
    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=True,
            order_transmit=True,
            allowed_symbols=("SPY",),
            max_order_usd=400.0,
        )
    )

    with pytest.raises(IBKRSafetyError, match="not in IBKR_ALLOWED_SYMBOLS"):
        client.submit_order(
            "QQQ",
            1,
            "buy",
            order_type="limit",
            limit_price=350.0,
            confirm_live=True,
        )

    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=True,
            order_transmit=True,
            allowed_symbols=("QQQ",),
            max_order_usd=400.0,
        )
    )

    with pytest.raises(IBKRSafetyError, match="exceeds IBKR_MAX_ORDER_USD"):
        client.submit_order(
            "QQQ",
            1,
            "buy",
            order_type="limit",
            limit_price=500.0,
            confirm_live=True,
        )


def test_ibkr_limit_order_uses_tws_gateway_and_prefixes_order_id(monkeypatch):
    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=True,
            order_transmit=True,
            account="DU12345",
            allowed_symbols=("QQQ",),
            max_order_usd=750.0,
        )
    )
    captured = {}

    def fake_submit_to_tws(symbol, qty, side, limit_price):
        captured.update(
            {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "limit_price": limit_price,
            }
        )
        return {
            "id": "101",
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "filled_qty": "0",
            "filled_avg_price": None,
            "status": "submitted",
            "created_at": "2026-05-10T12:00:00+00:00",
        }

    monkeypatch.setattr(client, "_submit_limit_order_to_tws", fake_submit_to_tws)

    result = client.submit_order(
        "qqq",
        1,
        "buy",
        order_type="limit",
        limit_price=500.0,
        confirm_live=True,
    )

    assert captured == {
        "symbol": "QQQ",
        "qty": 1,
        "side": "buy",
        "limit_price": 500.0,
    }
    assert result["id"] == "ibkr:101"
    assert result["broker"] == "ibkr"
    assert result["order_type"] == "limit"


def test_ibkr_client_serializes_tws_requests(monkeypatch):
    client = IBKRClient(
        settings=IBKRSettings(
            live_trading_enabled=True,
            order_transmit=True,
            allowed_symbols=("QQQ",),
            max_order_usd=750.0,
        )
    )
    active = 0
    max_active = 0

    def fake_submit_to_tws(symbol, qty, side, limit_price):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.05)
        active -= 1
        return {
            "id": f"{side}-{qty}",
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "filled_qty": "0",
            "filled_avg_price": None,
            "status": "submitted",
            "created_at": "2026-05-10T12:00:00+00:00",
        }

    monkeypatch.setattr(client, "_submit_limit_order_to_tws", fake_submit_to_tws)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                client.submit_order,
                "QQQ",
                1,
                "buy",
                order_type="limit",
                limit_price=500.0,
                confirm_live=True,
            ),
            executor.submit(
                client.submit_order,
                "QQQ",
                1,
                "sell",
                order_type="limit",
                limit_price=500.0,
                confirm_live=True,
            ),
        ]
        for future in futures:
            future.result()

    assert max_active == 1
