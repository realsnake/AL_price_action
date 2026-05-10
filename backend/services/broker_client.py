from __future__ import annotations

from config import BROKER
from services.alpaca_client import alpaca_client
from services.ibkr_client import ibkr_client


class BrokerClient:
    def __init__(
        self,
        *,
        selected_broker: str | None = None,
        alpaca_client=alpaca_client,
        ibkr_client=ibkr_client,
    ):
        self._selected_broker = (selected_broker or BROKER or "alpaca").lower()
        self._alpaca_client = alpaca_client
        self._ibkr_client = ibkr_client

    @property
    def name(self) -> str:
        return self._selected_broker

    @property
    def active(self):
        if self._selected_broker == "ibkr":
            return self._ibkr_client
        return self._alpaca_client

    def is_configured(self) -> bool:
        return bool(self.active.is_configured())

    def status(self) -> dict:
        active = self.active
        if hasattr(active, "status"):
            return active.status()
        return {
            "broker": self.name,
            "configured": active.is_configured(),
            "live_trading_enabled": False,
            "order_transmit": False,
        }

    def owns_order_id(self, order_id: str | None) -> bool:
        if not order_id:
            return False
        if self._selected_broker == "ibkr":
            return str(order_id).startswith("ibkr:")
        return not str(order_id).startswith("ibkr:")

    def get_account(self) -> dict:
        return self.active.get_account()

    def get_positions(self) -> list[dict]:
        return self.active.get_positions()

    def get_orders(self, status: str = "open") -> list[dict]:
        return self.active.get_orders(status)

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        *,
        order_type: str = "market",
        limit_price: float | None = None,
        confirm_live: bool = False,
    ) -> dict:
        if self._selected_broker == "ibkr":
            return self._ibkr_client.submit_order(
                symbol,
                qty,
                side,
                order_type=order_type,
                limit_price=limit_price,
                confirm_live=confirm_live,
            )
        return self._alpaca_client.submit_order(symbol, qty, side)

    def get_order_by_id(self, order_id: str) -> dict:
        return self.active.get_order_by_id(order_id)

    def cancel_order(self, order_id: str) -> None:
        self.active.cancel_order(order_id)


broker_client = BrokerClient()
