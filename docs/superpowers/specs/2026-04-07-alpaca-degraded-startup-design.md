# Alpaca Degraded Startup Design

## Goal

Allow the backend to start and expose `/api/health` even when Alpaca credentials are missing, while keeping behavior honest:

- cached historical-data flows remain usable when local cache is sufficient
- live market data, quotes, and trading endpoints return explicit `503` responses when Alpaca is not configured
- the app reports a degraded health state instead of pretending everything is healthy

## User-Approved Decisions

- Runtime behavior uses a lazy Alpaca client with capability checks instead of fail-fast import-time initialization.
- Historical bars follow `A1` semantics:
  - if the requested range can be satisfied from local cache, return cached bars normally
  - if serving the request would require an Alpaca fetch, return `503`
- `/api/health` follows `H2` semantics and reports degraded state when Alpaca is not configured.

## Current Problem

The backend currently instantiates the Alpaca SDK client during module import in [alpaca_client.py](/Users/bytedance/personalProject/AL_price_action/backend/services/alpaca_client.py). That import is pulled in by multiple routers and services during app startup. When `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are absent, the Alpaca SDK raises immediately, so the app cannot start and even `/api/health` is unavailable.

This blocks local frontend work, smoke testing, and cache-only backtest or signal flows that could otherwise run without live Alpaca access.

## Chosen Approach

Use a lightweight Alpaca service object that is always importable but only creates real Alpaca SDK clients on demand. The service exposes capability checks so callers can decide whether to use cached data, skip live-stream startup, or return `503`.

This keeps the existing repo style intact:

- routers stay thin
- most logic remains in services
- no large provider abstraction or mock framework is introduced

## Architecture

### 1. Alpaca service lifecycle

[alpaca_client.py](/Users/bytedance/personalProject/AL_price_action/backend/services/alpaca_client.py) will change from eager initialization to lazy initialization.

The service should provide:

- `is_configured()` to report whether credentials are present
- an internal method that creates SDK clients only when a real Alpaca operation is requested
- a consistent exception, such as `AlpacaNotConfiguredError`, when credentials are required but unavailable

Importing the module must never fail solely because credentials are missing.

### 2. Health reporting

[main.py](/Users/bytedance/personalProject/AL_price_action/backend/main.py) will keep `/api/health` available regardless of Alpaca configuration.

Recommended response shape:

```json
{
  "status": "degraded",
  "alpaca_configured": false,
  "live_stream_enabled": false
}
```

When credentials are present and live stream startup is enabled, the same endpoint should return:

```json
{
  "status": "ok",
  "alpaca_configured": true,
  "live_stream_enabled": true
}
```

### 3. Historical data behavior

[bars_cache.py](/Users/bytedance/personalProject/AL_price_action/backend/services/bars_cache.py) becomes the key decision point for `A1`.

Rules:

- if the requested bar range is already available in cache, return cache-only results without requiring Alpaca
- if cache is incomplete and an Alpaca fetch is needed, attempt the fetch only when Alpaca is configured
- if cache is incomplete and Alpaca is not configured, raise `AlpacaNotConfiguredError`

The implementation should be conservative. If the service cannot confidently satisfy the request from cache, it should return `503` rather than silently serving partial data that looks complete.

### 4. Live stream behavior

[market_data.py](/Users/bytedance/personalProject/AL_price_action/backend/services/market_data.py) should not fail app startup when Alpaca is unavailable.

Rules:

- `start_stream()` becomes a no-op when Alpaca is not configured
- `stop_stream()` remains safe to call even if no stream was started
- stream startup should log degraded mode for observability

For [ws.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/ws.py):

- `/ws/market/{symbol}` should not pretend to provide live updates when Alpaca is unavailable
- the server should accept the socket, send a degraded-status message, then close the socket
- `/ws/trades` can remain available because it is only a local notification channel; actual order submission will still fail with `503`

## Endpoint Behavior Matrix

### Always available

- `/api/health`
- `/api/trading/history`

### Available only when cache is sufficient

- `/api/market/bars/{symbol}`
- `/api/strategy/signals`
- `/api/backtest/run`

These endpoints should return normal responses on cache hit and `503` on cache miss when Alpaca is not configured.

### Always `503` when Alpaca is not configured

- `/api/market/quote/{symbol}`
- `/api/trading/account`
- `/api/trading/positions`
- `/api/trading/orders`
- `/api/trading/order`
- `/api/trading/order/{id}`

## Error Model

Introduce one service-level exception for missing configuration:

- `AlpacaNotConfiguredError`

Service layer:

- raises `AlpacaNotConfiguredError` only when an operation truly requires Alpaca access

Router layer:

- maps that exception to `HTTPException(status_code=503, detail="Alpaca credentials are not configured")`

This keeps error handling consistent across market, strategy, backtest, and trading paths.

## File-Level Design

### [alpaca_client.py](/Users/bytedance/personalProject/AL_price_action/backend/services/alpaca_client.py)

- remove eager SDK construction from `__init__`
- add credential capability checks
- lazily construct historical-data and trading SDK clients
- raise `AlpacaNotConfiguredError` only when a real Alpaca operation is requested

### [bars_cache.py](/Users/bytedance/personalProject/AL_price_action/backend/services/bars_cache.py)

- detect whether cache already satisfies the requested range
- only call Alpaca fetch path when cache is insufficient
- raise `AlpacaNotConfiguredError` when backfill is required but unavailable

### [market_data.py](/Users/bytedance/personalProject/AL_price_action/backend/services/market_data.py)

- gate stream creation and subscription behavior on Alpaca availability
- keep startup and shutdown idempotent in degraded mode

### [main.py](/Users/bytedance/personalProject/AL_price_action/backend/main.py)

- keep lifespan startup alive in degraded mode
- update `/api/health` response shape

### Routers

- [market.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/market.py)
- [trading.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/trading.py)
- [strategy.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/strategy.py)
- [backtest.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/backtest.py)
- [ws.py](/Users/bytedance/personalProject/AL_price_action/backend/routers/ws.py)

These routers remain thin and translate service-level degraded-mode exceptions into explicit HTTP or WebSocket behavior.

## Testing Strategy

Add focused backend tests that cover degraded startup and cache-aware routing:

1. health endpoint returns degraded status without credentials
2. app startup does not crash without credentials
3. `market_data.start_stream()` is a no-op without credentials
4. market bars route returns cached bars on cache hit without credentials
5. market bars route returns `503` on cache miss without credentials
6. strategy signals route returns `503` when analysis bars need Alpaca but Alpaca is unavailable
7. backtest route returns `503` when analysis bars need Alpaca but Alpaca is unavailable
8. quote and trading routes return `503` without credentials
9. market WebSocket sends degraded status and closes when Alpaca is unavailable

Verification for the implementation phase should include:

- backend compile check
- targeted pytest coverage for degraded-mode behavior
- frontend lint and build
- a local `/api/health` smoke check with no Alpaca credentials present

## Non-Goals

- adding mock trading or synthetic quote providers
- changing frontend UX beyond reflecting existing offline and request-failure states
- implementing fill reconciliation or other trading-flow upgrades
- redesigning the broader service architecture around a provider abstraction

## Risks And Mitigations

- Cache sufficiency is easy to misjudge.
  - Mitigation: prefer explicit `503` over returning potentially incomplete data.
- Multiple routers may drift into inconsistent degraded-mode handling.
  - Mitigation: centralize exception type and router mapping pattern.
- WebSocket clients may misread degraded mode as a transient disconnect.
  - Mitigation: send a structured degraded-status message before closing.

## Success Criteria

- Backend starts successfully with no Alpaca credentials configured.
- `/api/health` reports degraded status instead of crashing.
- Cache-backed historical flows work when data is already present locally.
- Alpaca-dependent endpoints fail explicitly with `503`.
- Frontend can be developed and smoke-tested locally without needing paper-trading credentials.
