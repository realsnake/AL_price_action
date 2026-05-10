from __future__ import annotations

from services.broker_client import BrokerClient


class _FakeBroker:
    def __init__(self, name: str, configured: bool = True):
        self.name = name
        self.configured = configured
        self.calls: list[tuple[str, tuple, dict]] = []

    def is_configured(self) -> bool:
        return self.configured

    def get_account(self):
        self.calls.append(("get_account", (), {}))
        return {"broker": self.name}

    def submit_order(self, *args, **kwargs):
        self.calls.append(("submit_order", args, kwargs))
        return {"id": f"{self.name}-order", "broker": self.name}

    def owns_order_id(self, order_id: str) -> bool:
        return order_id.startswith(f"{self.name}:")


def test_broker_client_defaults_to_alpaca():
    alpaca = _FakeBroker("alpaca")
    ibkr = _FakeBroker("ibkr")
    broker = BrokerClient(
        selected_broker="alpaca",
        alpaca_client=alpaca,
        ibkr_client=ibkr,
    )

    assert broker.name == "alpaca"
    assert broker.is_configured() is True
    assert broker.get_account() == {"broker": "alpaca"}
    assert alpaca.calls == [("get_account", (), {})]
    assert ibkr.calls == []


def test_broker_client_selects_ibkr_and_forwards_order_options():
    alpaca = _FakeBroker("alpaca")
    ibkr = _FakeBroker("ibkr")
    broker = BrokerClient(
        selected_broker="ibkr",
        alpaca_client=alpaca,
        ibkr_client=ibkr,
    )

    result = broker.submit_order(
        "QQQ",
        1,
        "buy",
        order_type="limit",
        limit_price=500.0,
        confirm_live=True,
    )

    assert result == {"id": "ibkr-order", "broker": "ibkr"}
    assert ibkr.calls == [
        (
            "submit_order",
            ("QQQ", 1, "buy"),
            {
                "order_type": "limit",
                "limit_price": 500.0,
                "confirm_live": True,
            },
        )
    ]
    assert broker.owns_order_id("ibkr:101") is True
    assert broker.owns_order_id("alpaca-order") is False
