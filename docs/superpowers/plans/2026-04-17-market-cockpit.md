# Market Cockpit Implementation Plan

Date: 2026-04-17

## Goal

Implement a polished reliability-first frontend upgrade that makes live, degraded, cached, and offline modes legible throughout the workspace.

## Tasks

### Task 1: Add central status hook

- create a hook that polls `/api/health`
- combine browser online state and market WebSocket state
- expose normalized mode and derived booleans
- include last successful sync timestamp

### Task 2: Make cache freshness visible

- extend offline DB records with `cached_at`
- add snapshot helpers in `api.ts` or cache utilities so the app can read both data and metadata
- keep existing simple API helpers compatible where possible

### Task 3: Rebuild the top-of-app experience

- strengthen the visual shell in `App.tsx`
- add operational metric cards and mode badges
- replace the simplistic live/offline dot with richer status presentation
- preserve the chart-left / sidebar-right structure

### Task 4: Improve control-state semantics

- pass clear disabled reasons into Trade, Strategy, and Backtest panels
- keep trading disabled in offline, backend-down, and degraded-without-Alpaca states
- keep analysis available in degraded mode when backend is alive

### Task 5: Replace banner and polish panels

- upgrade the offline banner into a contextual status banner
- align Trade and analysis panels with the new cockpit visual hierarchy
- keep changes compatible with current local state model

### Task 6: Verify

- run frontend lint
- run frontend build
- verify local dev proxy path:
  - `http://127.0.0.1:5173/api/health`
  - `ws://127.0.0.1:5173/ws/market/AAPL`

## Execution Notes

- prefer additive changes over churn
- do not disturb unrelated in-progress frontend work
- keep backend unchanged unless a blocker appears
