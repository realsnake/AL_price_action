# Pullback Count Phase1 Design

## Goal

Bring `brooks_pullback_count` to the same `QQQ 5m qqq_5m_phase1` quality bar as the completed phase1 strategies: reproducible backtest research, a selected exit policy that passes the recent-window gate, an annotated Chinese replay report, and a paper-trading path only if the study result is strong enough.

## Current State

The strategy exists, but it is still a broad H1/H2/L1/L2 signal generator. A baseline `QQQ 5m qqq_5m_phase1` study on cached bars produced 4162 signals, 448 trades, `-0.61%` total return, `PF 0.99`, and a negative last-12-trade-day window. That means the work must start with signal quality, not exit optimization alone.

## Design

The phase1 version remains long-only. It should emit H1/H2 continuation buys only when the market is already in a credible bull trend: EMA20 rising, price above EMA, close above session open, and close above session VWAP with a small buffer. The signal should use the previous pullback state correctly, so a reversal bar is recognized after the pullback rather than after state has already been overwritten.

The exit study should use strategy-specific policy identifiers for pullback count, not breakout-specific names. The candidate set should include session close, fixed R targets, break-even protection, and pullback/swing-low dynamic protection. Ranking must keep the same hard recent gate used by breakout: last 12 tradedays PnL above zero and latest 3-month return above zero.

## Reporting And Paper Trade

The replay report must stay in the offline annotated format: `report.html`, `summary.csv`, and one SVG per trade day. Chinese reason text should explain H1/H2 pullback-count entries, structural stops, explicit targets, and dynamic stop updates. Paper-trading support should be added only after the selected policy passes the research gate.

## Verification

Required checks are targeted pytest for strategy, exit, backtester, study/report, and runner paths; full backend pytest after integration; frontend lint and build if frontend strategy selection or copy changes; and a real generated replay report for the selected policy.
