from __future__ import annotations

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, PAPER_TRADING


def _timeframe_from_str(tf: str) -> TimeFrame:
    mapping = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "1D": TimeFrame(1, TimeFrameUnit.Day),
    }
    return mapping.get(tf, TimeFrame(1, TimeFrameUnit.Day))


class AlpacaNotConfiguredError(RuntimeError):
    pass


class AlpacaClient:
    def __init__(self):
        self._data_client: StockHistoricalDataClient | None = None
        self._trading_client: TradingClient | None = None

    def is_configured(self) -> bool:
        return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise AlpacaNotConfiguredError("Alpaca credentials are not configured")

    def _get_data_client(self) -> StockHistoricalDataClient:
        self._ensure_configured()
        if self._data_client is None:
            self._data_client = StockHistoricalDataClient(
                ALPACA_API_KEY, ALPACA_SECRET_KEY
            )
        return self._data_client

    def _get_trading_client(self) -> TradingClient:
        self._ensure_configured()
        if self._trading_client is None:
            self._trading_client = TradingClient(
                ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING
            )
        return self._trading_client

    def get_bars(self, symbol: str, timeframe: str, start: str, end: str | None = None, limit: int = 200) -> list[dict]:
        tf = _timeframe_from_str(timeframe)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
            feed=DataFeed.IEX,
        )
        bars = self._get_data_client().get_stock_bars(request)
        result = []
        for bar in bars[symbol]:
            result.append({
                "time": bar.timestamp.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
            })
        return result

    def get_quote(self, symbol: str) -> dict:
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        quote = self._get_data_client().get_stock_latest_quote(request)
        q = quote[symbol]
        return {
            "symbol": symbol,
            "bid": float(q.bid_price),
            "ask": float(q.ask_price),
            "bid_size": int(q.bid_size),
            "ask_size": int(q.ask_size),
            "timestamp": q.timestamp.isoformat(),
        }

    def get_account(self) -> dict:
        account = self._get_trading_client().get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "pnl": float(account.equity) - float(account.last_equity),
            "pnl_pct": (float(account.equity) - float(account.last_equity)) / float(account.last_equity) * 100 if float(account.last_equity) > 0 else 0,
        }

    def get_positions(self) -> list[dict]:
        positions = self._get_trading_client().get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": int(p.qty),
                "avg_entry": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
            }
            for p in positions
        ]

    def submit_order(self, symbol: str, qty: int, side: str) -> dict:
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._get_trading_client().submit_order(request)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": str(order.qty),
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
        }

    def get_order_by_id(self, order_id: str) -> dict:
        order = self._get_trading_client().get_order_by_id(order_id)
        return {
            "id": str(order.id),
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": str(order.qty) if order.qty is not None else None,
            "filled_qty": str(order.filled_qty) if order.filled_qty is not None else None,
            "filled_avg_price": (
                str(order.filled_avg_price)
                if order.filled_avg_price is not None
                else None
            ),
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        }

    def cancel_order(self, order_id: str):
        self._get_trading_client().cancel_order_by_id(order_id)

    def get_orders(self, status: str = "open") -> list[dict]:
        query_status = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
        request = GetOrdersRequest(status=query_status, limit=50)
        orders = self._get_trading_client().get_orders(request)
        return [
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value,
                "qty": str(o.qty),
                "filled_qty": str(o.filled_qty) if o.filled_qty else "0",
                "status": o.status.value,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ]


alpaca_client = AlpacaClient()
