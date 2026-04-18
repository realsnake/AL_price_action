# Market Cockpit Design

Date: 2026-04-17

## Context

The frontend already has the beginnings of offline support and PWA work:

- `frontend/src/hooks/useOffline.ts`
- `frontend/src/services/offlineDb.ts`
- offline-aware fallback logic in `frontend/src/services/api.ts`
- a simple offline banner in `frontend/src/components/OfflineBanner.tsx`

At the same time, the app still communicates system health in a coarse way:

- the header status only reflects the market WebSocket
- "Offline" can mean browser offline, backend unreachable, or a transient proxy issue
- degraded backend mode is not surfaced clearly in the UI
- trading and analysis actions do not consistently explain why they are unavailable

The result is a workstation that can function in more modes than it can explain.

## Goal

Turn the current UI into a more polished "market cockpit" experience that makes reliability visible:

- distinguish browser offline vs backend down vs degraded Alpaca mode vs live streaming
- show when the workspace is using cached data
- improve the visual hierarchy without replacing the left-chart/right-sidebar layout
- make trade and analysis controls explain availability instead of just failing or silently degrading

## Options Considered

### Option 1: Minimal status patch

Add a better banner and keep the rest of the app mostly unchanged.

Pros:

- small change set
- low risk

Cons:

- does not improve the overall information hierarchy
- keeps status fragmented and easy to miss
- wastes the existing offline cache work

### Option 2: Market cockpit upgrade

Introduce a central system-status model, surface it in a richer header + status strip, and restyle the main workspace around that model.

Pros:

- visibly upgrades product quality
- improves trust and operational clarity
- fits the existing app structure
- reuses current offline/PWA work instead of fighting it

Cons:

- touches several frontend files together
- needs careful contract handling for cached metadata

### Option 3: Full shell rewrite

Redesign navigation, panels, and layout architecture together.

Pros:

- maximum visual change

Cons:

- too much surface area for one iteration
- high risk of regressions in a working workstation
- not aligned with the user's instruction to move fast without churn

## Decision

Choose Option 2.

This keeps the project recognizably the same app, but upgrades it from a functional demo feel to a more intentional workstation feel.

## Design

### 1. Central system status

Add a frontend status hook that combines:

- browser online state
- backend `/api/health`
- live-stream availability
- market WebSocket connection state

The hook will expose a normalized workspace mode:

- `live`
- `syncing`
- `degraded`
- `api_down`
- `offline`

It will also track:

- whether Alpaca is configured
- whether live streaming is enabled
- the last successful health sync timestamp

### 2. Cache-aware data presentation

Extend the IndexedDB cache layer to store `cached_at` metadata for:

- bars
- account snapshot
- positions snapshot

The app will use that metadata to show cache freshness in the UI instead of presenting stale snapshots as if they were live.

### 3. Cockpit header and status strip

Reshape the top area into:

- a stronger workspace header
- explicit mode badges
- compact operational cards for symbol, price, data source, and account state

The visual language should feel like a trading console:

- stronger contrast
- subtle gradient and glow treatment
- denser metrics
- clearer text hierarchy

The layout should stay compatible with the current app skeleton.

### 4. Contextual availability rules

Make controls explain why they are unavailable.

Trading:

- disabled when browser is offline
- disabled when backend is unreachable
- disabled when Alpaca is not configured

Strategy scan and backtest:

- disabled when browser is offline or backend is unreachable
- still available in degraded Alpaca mode if backend is up

### 5. Better degraded and offline messaging

Replace the current one-line offline banner with a contextual system banner that adapts copy by mode:

- offline browser
- backend unavailable
- degraded Alpaca mode
- reconnecting market stream

### 6. Keep scope tight

This iteration will not include:

- order history UI
- fill reconciliation
- multi-page navigation
- backend contract changes beyond existing `/api/health`

## Files Expected To Change

- `frontend/src/App.tsx`
- `frontend/src/components/TradePanel.tsx`
- `frontend/src/components/StrategyPanel.tsx`
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/components/OfflineBanner.tsx`
- `frontend/src/hooks/useOffline.ts`
- `frontend/src/services/api.ts`
- `frontend/src/services/offlineDb.ts`
- `frontend/src/types/index.ts`
- new status and metric components/hooks as needed

## Verification

Minimum verification for this iteration:

- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- local smoke of:
  - app load
  - `/api/health` through Vite proxy
  - market WebSocket through Vite proxy
  - visible status transitions in normal online mode

## Notes

The user explicitly asked for autonomous decision-making in this thread, so this design is approved by default and can proceed directly into implementation planning.
