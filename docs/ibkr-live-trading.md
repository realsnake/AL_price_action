# IBKR Live Trading Runbook

This project supports IBKR live trading only for manual, small-size US stock limit orders. Market data, charts, strategy scans, and backtests still use the existing Alpaca-backed paths.

## Hard Gates

- `BROKER=ibkr` selects IBKR for account and order execution.
- `IBKR_LIVE_TRADING_ENABLED=true` and `IBKR_ORDER_TRANSMIT=true` are both required before any IBKR order can be sent.
- IBKR orders must be manual `limit` orders with `confirm_live=true`.
- `IBKR_ALLOWED_SYMBOLS` restricts tradable symbols.
- `IBKR_MAX_ORDER_USD` caps each order by `qty * limit_price`.
- `IBKR_DAILY_MAX_NOTIONAL_USD` caps same-day IBKR order notional recorded locally.
- Strategy-driven orders are blocked unless `IBKR_ALLOW_STRATEGY_TRADING=true`; keep this unset for the first live experiment.
- Phase 1 Brooks paper runners require `BROKER=alpaca` and remain paper-only.

## TWS / IB Gateway Setup

1. Install the official IBKR TWS API Python package from the TWS API distribution, or otherwise make `ibapi` importable in the backend virtualenv.
2. Start Trader Workstation or IB Gateway and log into the live account intended for the experiment.
3. In TWS Global Configuration -> API -> Settings:
   - enable socket clients,
   - disable read-only API,
   - confirm the socket port.
4. Use a dedicated `IBKR_CLIENT_ID`, such as `17`, so this app does not collide with another API client.

## Backend Environment

```bash
BROKER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=7496
IBKR_CLIENT_ID=17
IBKR_ACCOUNT=U1234567
IBKR_LIVE_TRADING_ENABLED=true
IBKR_ORDER_TRANSMIT=true
IBKR_ALLOWED_SYMBOLS=QQQ
IBKR_MAX_ORDER_USD=750
IBKR_DAILY_MAX_NOTIONAL_USD=1500
IBKR_ALLOW_STRATEGY_TRADING=false
```

Restart the backend after changing these values.

## Pre-Trade Checks

Run:

```bash
curl http://localhost:8000/api/trading/broker
curl http://localhost:8000/api/trading/account
curl http://localhost:8000/api/trading/positions
```

Expected:

- `/api/trading/broker` returns `"broker":"ibkr"` and `"configured":true`.
- Account and positions endpoints return IBKR snapshots without `503`.
- Frontend trade panel shows `Execution · IBKR` and `ARMED`.

## 2026-05-11 to 2026-05-15 Small-Amount Experiment

This is an operational test plan, not a recommendation to trade a specific instrument.

1. Use only symbols listed in `IBKR_ALLOWED_SYMBOLS`.
2. Submit one manual buy limit order for `qty=1`, with `qty * limit_price <= IBKR_MAX_ORDER_USD`.
3. If it does not fill within the intended observation window, cancel it from the open-orders view or TWS.
4. If it fills, submit one manual sell limit order for the same quantity before market close.
5. Keep `IBKR_ALLOW_STRATEGY_TRADING=false` for the whole experiment.
6. After the experiment, set `BROKER=alpaca` or turn off `IBKR_ORDER_TRANSMIT`.

## API Example

```bash
curl -X POST http://localhost:8000/api/trading/order \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "QQQ",
    "qty": 1,
    "side": "buy",
    "order_type": "limit",
    "limit_price": 500.00,
    "confirm_live": true
  }'
```

The backend records IBKR order IDs with an `ibkr:` prefix in the existing `alpaca_order_id` database column for backward compatibility.
