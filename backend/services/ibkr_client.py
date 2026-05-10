from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any

from config import IBKR_ACCOUNT
from config import IBKR_ALLOWED_SYMBOLS
from config import IBKR_CLIENT_ID
from config import IBKR_HOST
from config import IBKR_LIVE_TRADING_ENABLED
from config import IBKR_MAX_ORDER_USD
from config import IBKR_ORDER_TRANSMIT
from config import IBKR_PORT
from config import IBKR_REQUEST_TIMEOUT_SECONDS

IBKR_ORDER_PREFIX = "ibkr:"
OPEN_ORDER_STATUSES = {
    "ApiPending",
    "PendingSubmit",
    "PendingCancel",
    "PreSubmitted",
    "Submitted",
    "Inactive",
}


class IBKRNotConfiguredError(RuntimeError):
    pass


class IBKRSafetyError(ValueError):
    pass


@dataclass(frozen=True)
class IBKRSettings:
    host: str = IBKR_HOST
    port: int = IBKR_PORT
    client_id: int = IBKR_CLIENT_ID
    account: str = IBKR_ACCOUNT
    live_trading_enabled: bool = IBKR_LIVE_TRADING_ENABLED
    order_transmit: bool = IBKR_ORDER_TRANSMIT
    allowed_symbols: tuple[str, ...] = IBKR_ALLOWED_SYMBOLS
    max_order_usd: float = IBKR_MAX_ORDER_USD
    request_timeout_seconds: float = IBKR_REQUEST_TIMEOUT_SECONDS


def prefixed_ibkr_order_id(order_id: str | int) -> str:
    value = str(order_id)
    return value if value.startswith(IBKR_ORDER_PREFIX) else f"{IBKR_ORDER_PREFIX}{value}"


def raw_ibkr_order_id(order_id: str | int) -> int:
    value = str(order_id)
    if value.startswith(IBKR_ORDER_PREFIX):
        value = value[len(IBKR_ORDER_PREFIX):]
    return int(value)


class IBKRClient:
    def __init__(self, settings: IBKRSettings | None = None):
        self.settings = settings or IBKRSettings()
        self._request_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "ibkr"

    def is_configured(self) -> bool:
        return bool(
            self.settings.live_trading_enabled
            and self.settings.order_transmit
            and self.settings.host
            and self.settings.port
            and self.settings.client_id >= 0
        )

    def owns_order_id(self, order_id: str) -> bool:
        return str(order_id).startswith(IBKR_ORDER_PREFIX)

    def status(self) -> dict:
        return {
            "broker": self.name,
            "configured": self.is_configured(),
            "live_trading_enabled": self.settings.live_trading_enabled,
            "order_transmit": self.settings.order_transmit,
            "host": self.settings.host,
            "port": self.settings.port,
            "client_id": self.settings.client_id,
            "account": self.settings.account or None,
            "allowed_symbols": list(self.settings.allowed_symbols),
            "max_order_usd": self.settings.max_order_usd,
        }

    def _ensure_configured(self) -> None:
        if not self.settings.live_trading_enabled:
            raise IBKRNotConfiguredError("IBKR live trading is not enabled")
        if not self.settings.order_transmit:
            raise IBKRNotConfiguredError("IBKR_ORDER_TRANSMIT is not enabled")
        if not self.settings.host or not self.settings.port:
            raise IBKRNotConfiguredError("IBKR host/port are not configured")

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
        self._ensure_configured()
        normalized_symbol = symbol.upper()
        normalized_side = side.lower()
        normalized_order_type = order_type.lower()
        self._validate_live_order(
            normalized_symbol,
            qty,
            normalized_side,
            normalized_order_type,
            limit_price,
            confirm_live,
        )

        with self._request_lock:
            result = self._submit_limit_order_to_tws(
                normalized_symbol,
                qty,
                normalized_side,
                float(limit_price or 0.0),
            )
        result["id"] = prefixed_ibkr_order_id(result["id"])
        result["broker"] = self.name
        result["order_type"] = "limit"
        result.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return result

    def _validate_live_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        limit_price: float | None,
        confirm_live: bool,
    ) -> None:
        if qty <= 0:
            raise IBKRSafetyError("qty must be positive")
        if side not in {"buy", "sell"}:
            raise IBKRSafetyError("side must be 'buy' or 'sell'")
        if order_type != "limit":
            raise IBKRSafetyError("IBKR live orders require order_type='limit'")
        if limit_price is None or limit_price <= 0:
            raise IBKRSafetyError("IBKR live orders require a positive limit_price")
        if not confirm_live:
            raise IBKRSafetyError("IBKR live orders require confirm_live=true")

        allowed_symbols = set(self.settings.allowed_symbols)
        if allowed_symbols and symbol not in allowed_symbols:
            raise IBKRSafetyError(f"{symbol} is not in IBKR_ALLOWED_SYMBOLS")

        notional = qty * float(limit_price)
        if notional > self.settings.max_order_usd:
            raise IBKRSafetyError(
                f"order notional ${notional:.2f} exceeds IBKR_MAX_ORDER_USD "
                f"${self.settings.max_order_usd:.2f}"
            )

    def _submit_limit_order_to_tws(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
    ) -> dict:
        gateway = _IBKRTWSGateway(self.settings)
        return gateway.submit_limit_order(symbol, qty, side, limit_price)

    def get_account(self) -> dict:
        self._ensure_configured()
        with self._request_lock:
            return _IBKRTWSGateway(self.settings).get_account()

    def get_positions(self) -> list[dict]:
        self._ensure_configured()
        with self._request_lock:
            return _IBKRTWSGateway(self.settings).get_positions()

    def get_orders(self, status: str = "open") -> list[dict]:
        self._ensure_configured()
        with self._request_lock:
            orders = _IBKRTWSGateway(self.settings).get_orders()
        if status == "open":
            return [
                order
                for order in orders
                if _ibkr_status_is_open(str(order.get("status") or ""))
            ]
        return orders

    def get_order_by_id(self, order_id: str) -> dict:
        self._ensure_configured()
        with self._request_lock:
            return _IBKRTWSGateway(self.settings).get_order_by_id(
                raw_ibkr_order_id(order_id)
            )

    def cancel_order(self, order_id: str) -> None:
        self._ensure_configured()
        with self._request_lock:
            _IBKRTWSGateway(self.settings).cancel_order(raw_ibkr_order_id(order_id))


class _IBKRTWSGateway:
    def __init__(self, settings: IBKRSettings):
        self.settings = settings

    def submit_limit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
    ) -> dict:
        app = _IBKRTWSApp()
        try:
            _connect_app(app, self.settings)
            order_id = app.next_order_id()
            contract = _stock_contract(symbol)
            order = _limit_order(side, qty, limit_price, self.settings)
            app.placeOrder(order_id, contract, order)
            snapshot = app.wait_for_order(order_id, self.settings.request_timeout_seconds)
            return _order_snapshot(order_id, symbol, side, qty, snapshot)
        finally:
            _disconnect_app(app)

    def get_account(self) -> dict:
        app = _IBKRTWSApp()
        try:
            _connect_app(app, self.settings)
            request_id = app.next_request_id()
            app.reqAccountSummary(
                request_id,
                "All",
                "NetLiquidation,CashBalance,BuyingPower,AvailableFunds,RealizedPnL,UnrealizedPnL",
            )
            values = app.wait_for_account_summary(
                request_id,
                self.settings.request_timeout_seconds,
            )
            try:
                app.cancelAccountSummary(request_id)
            except Exception:
                pass
            return _account_snapshot(values, self.settings.account)
        finally:
            _disconnect_app(app)

    def get_positions(self) -> list[dict]:
        app = _IBKRTWSApp()
        try:
            _connect_app(app, self.settings)
            app.reqPositions()
            positions = app.wait_for_positions(self.settings.request_timeout_seconds)
            return _position_snapshots(positions, self.settings.account)
        finally:
            _disconnect_app(app)

    def get_orders(self) -> list[dict]:
        app = _IBKRTWSApp()
        try:
            _connect_app(app, self.settings)
            app.reqOpenOrders()
            open_orders = app.wait_for_open_orders(self.settings.request_timeout_seconds)
            try:
                app.reqCompletedOrders(True)
                completed = app.wait_for_completed_orders(
                    self.settings.request_timeout_seconds
                )
            except Exception:
                completed = []
            snapshots = open_orders + completed
            return [_normalize_order_snapshot(snapshot) for snapshot in snapshots]
        finally:
            _disconnect_app(app)

    def get_order_by_id(self, order_id: int) -> dict:
        orders = self.get_orders()
        expected_id = prefixed_ibkr_order_id(order_id)
        for order in orders:
            if order.get("id") == expected_id:
                return order
        return {
            "id": expected_id,
            "symbol": "",
            "side": "",
            "qty": None,
            "filled_qty": None,
            "filled_avg_price": None,
            "status": "unknown",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def cancel_order(self, order_id: int) -> None:
        app = _IBKRTWSApp()
        try:
            _connect_app(app, self.settings)
            try:
                from ibapi.order_cancel import OrderCancel

                app.cancelOrder(order_id, OrderCancel())
            except ImportError:
                app.cancelOrder(order_id)
            except TypeError:
                app.cancelOrder(order_id)
        finally:
            _disconnect_app(app)


class _IBKRTWSApp:
    def __init__(self):
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
        except ImportError as exc:
            raise IBKRNotConfiguredError(
                "IBKR TWS API package is not installed; install the official ibapi package"
            ) from exc

        class _App(EWrapper, EClient):
            def __init__(self):
                EClient.__init__(self, self)
                self._next_order_id: int | None = None
                self._request_id = 9000
                self._ready = threading.Event()
                self._account_events: dict[int, threading.Event] = {}
                self._account_values: dict[int, dict[str, dict[str, float]]] = {}
                self._positions: list[tuple[str, Any, Decimal, float]] = []
                self._positions_done = threading.Event()
                self._orders: dict[int, dict] = {}
                self._open_orders_done = threading.Event()
                self._completed_orders: list[dict] = []
                self._completed_orders_done = threading.Event()
                self._errors: list[str] = []

            def nextValidId(self, orderId):  # noqa: N802
                self._next_order_id = int(orderId)
                self._ready.set()

            def next_order_id(self) -> int:
                if self._next_order_id is None:
                    raise RuntimeError("IBKR next order id is unavailable")
                value = self._next_order_id
                self._next_order_id += 1
                return value

            def next_request_id(self) -> int:
                self._request_id += 1
                return self._request_id

            def wait_until_ready(self, timeout: float) -> None:
                if not self._ready.wait(timeout):
                    raise TimeoutError("Timed out waiting for IBKR nextValidId")

            def error(self, reqId, errorCode, errorString, *args):  # noqa: N802
                if int(errorCode) not in {2104, 2106, 2158}:
                    self._errors.append(f"{errorCode}: {errorString}")

            def accountSummary(self, reqId, account, tag, value, currency):  # noqa: N802
                request_id = int(reqId)
                by_account = self._account_values.setdefault(request_id, {})
                account_values = by_account.setdefault(str(account), {})
                try:
                    account_values[str(tag)] = float(value)
                except (TypeError, ValueError):
                    account_values[str(tag)] = 0.0

            def accountSummaryEnd(self, reqId):  # noqa: N802
                request_id = int(reqId)
                self._account_events.setdefault(request_id, threading.Event()).set()

            def wait_for_account_summary(self, req_id: int, timeout: float):
                event = self._account_events.setdefault(req_id, threading.Event())
                if not event.wait(timeout):
                    raise TimeoutError("Timed out waiting for IBKR account summary")
                return self._account_values.get(req_id, {})

            def position(self, account, contract, position, avgCost):  # noqa: N802
                self._positions.append((str(account), contract, Decimal(str(position)), float(avgCost or 0.0)))

            def positionEnd(self):  # noqa: N802
                self._positions_done.set()

            def wait_for_positions(self, timeout: float):
                if not self._positions_done.wait(timeout):
                    raise TimeoutError("Timed out waiting for IBKR positions")
                return list(self._positions)

            def openOrder(self, orderId, contract, order, orderState):  # noqa: N802
                snapshot = _snapshot_from_ib_order(orderId, contract, order, orderState)
                self._orders[int(orderId)] = snapshot

            def openOrderEnd(self):  # noqa: N802
                self._open_orders_done.set()

            def completedOrder(self, contract, order, orderState):  # noqa: N802
                order_id = getattr(order, "orderId", None) or getattr(order, "permId", None)
                self._completed_orders.append(
                    _snapshot_from_ib_order(order_id, contract, order, orderState)
                )

            def completedOrdersEnd(self):  # noqa: N802
                self._completed_orders_done.set()

            def orderStatus(  # noqa: N802
                self,
                orderId,
                status,
                filled,
                remaining,
                avgFillPrice,
                *args,
            ):
                snapshot = self._orders.setdefault(int(orderId), {"id": int(orderId)})
                snapshot.update(
                    {
                        "status": str(status).lower(),
                        "filled_qty": str(filled),
                        "remaining": str(remaining),
                        "filled_avg_price": (
                            None if float(avgFillPrice or 0.0) <= 0 else str(avgFillPrice)
                        ),
                    }
                )

            def wait_for_order(self, order_id: int, timeout: float) -> dict:
                deadline = threading.Event()
                if deadline.wait(0):
                    return {}
                end_at = datetime.now(timezone.utc).timestamp() + timeout
                while datetime.now(timezone.utc).timestamp() < end_at:
                    snapshot = self._orders.get(order_id)
                    if snapshot is not None:
                        return snapshot
                    threading.Event().wait(0.05)
                if self._errors:
                    raise RuntimeError("; ".join(self._errors))
                return {"id": order_id, "status": "submitted"}

            def wait_for_open_orders(self, timeout: float):
                if not self._open_orders_done.wait(timeout):
                    raise TimeoutError("Timed out waiting for IBKR open orders")
                return list(self._orders.values())

            def wait_for_completed_orders(self, timeout: float):
                if not self._completed_orders_done.wait(timeout):
                    raise TimeoutError("Timed out waiting for IBKR completed orders")
                return list(self._completed_orders)

        self._app = _App()

    def __getattr__(self, name):
        return getattr(self._app, name)


def _connect_app(app: _IBKRTWSApp, settings: IBKRSettings) -> None:
    app.connect(settings.host, settings.port, settings.client_id)
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    app._thread = thread
    app.wait_until_ready(settings.request_timeout_seconds)


def _disconnect_app(app: _IBKRTWSApp) -> None:
    try:
        app.disconnect()
    except Exception:
        pass


def _stock_contract(symbol: str):
    try:
        from ibapi.contract import Contract
    except ImportError as exc:
        raise IBKRNotConfiguredError(
            "IBKR TWS API package is not installed; install the official ibapi package"
        ) from exc

    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    return contract


def _limit_order(side: str, qty: int, limit_price: float, settings: IBKRSettings):
    try:
        from ibapi.order import Order
    except ImportError as exc:
        raise IBKRNotConfiguredError(
            "IBKR TWS API package is not installed; install the official ibapi package"
        ) from exc

    order = Order()
    order.action = "BUY" if side.lower() == "buy" else "SELL"
    order.orderType = "LMT"
    order.totalQuantity = qty
    order.lmtPrice = float(limit_price)
    order.tif = "DAY"
    order.transmit = settings.order_transmit
    if settings.account:
        order.account = settings.account
    return order


def _snapshot_from_ib_order(order_id, contract, order, order_state) -> dict:
    status = getattr(order_state, "status", None) or getattr(order, "status", None)
    return {
        "id": prefixed_ibkr_order_id(order_id),
        "symbol": getattr(contract, "symbol", ""),
        "side": str(getattr(order, "action", "")).lower(),
        "qty": str(getattr(order, "totalQuantity", "") or ""),
        "filled_qty": None,
        "filled_avg_price": None,
        "status": str(status or "submitted").lower(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "broker": "ibkr",
    }


def _order_snapshot(order_id: int, symbol: str, side: str, qty: int, snapshot: dict) -> dict:
    normalized = dict(snapshot)
    normalized.setdefault("id", prefixed_ibkr_order_id(order_id))
    normalized.setdefault("symbol", symbol)
    normalized.setdefault("side", side)
    normalized.setdefault("qty", str(qty))
    normalized.setdefault("filled_qty", "0")
    normalized.setdefault("filled_avg_price", None)
    normalized.setdefault("status", "submitted")
    normalized.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    normalized["id"] = prefixed_ibkr_order_id(normalized["id"])
    normalized["broker"] = "ibkr"
    return normalized


def _normalize_order_snapshot(snapshot: dict) -> dict:
    normalized = dict(snapshot)
    normalized["id"] = prefixed_ibkr_order_id(normalized.get("id", ""))
    normalized.setdefault("broker", "ibkr")
    return normalized


def _account_snapshot(
    values_by_account: dict[str, dict[str, float]],
    configured_account: str,
) -> dict:
    if configured_account and configured_account in values_by_account:
        values = values_by_account[configured_account]
    elif values_by_account:
        values = next(iter(values_by_account.values()))
    else:
        values = {}

    equity = float(values.get("NetLiquidation", 0.0))
    cash = float(values.get("CashBalance", values.get("AvailableFunds", 0.0)))
    buying_power = float(values.get("BuyingPower", values.get("AvailableFunds", 0.0)))
    realized = float(values.get("RealizedPnL", 0.0))
    unrealized = float(values.get("UnrealizedPnL", 0.0))
    pnl = realized + unrealized
    return {
        "equity": equity,
        "cash": cash,
        "buying_power": buying_power,
        "portfolio_value": equity,
        "pnl": pnl,
        "pnl_pct": (pnl / equity * 100) if equity else 0.0,
        "broker": "ibkr",
    }


def _position_snapshots(
    positions: list[tuple[str, Any, Decimal, float]],
    configured_account: str,
) -> list[dict]:
    snapshots = []
    for account, contract, quantity, avg_cost in positions:
        if configured_account and account != configured_account:
            continue
        if getattr(contract, "secType", "") != "STK":
            continue
        symbol = getattr(contract, "symbol", "")
        qty = int(quantity)
        current_price = float(avg_cost)
        market_value = qty * current_price
        snapshots.append(
            {
                "symbol": symbol,
                "qty": qty,
                "avg_entry": current_price,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "broker": "ibkr",
            }
        )
    return snapshots


def _ibkr_status_is_open(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized in {value.lower() for value in OPEN_ORDER_STATUSES}


ibkr_client = IBKRClient()
