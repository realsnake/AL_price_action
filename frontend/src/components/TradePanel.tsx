import { useState } from "react";
import PaperStrategyPanel from "./PaperStrategyPanel";
import { submitOrder } from "../services/api";
import type { Account, Position, TradingBrokerStatus } from "../types";

interface TradePanelProps {
  account: Account | null;
  positions: Position[];
  currentSymbol: string;
  brokerStatus?: TradingBrokerStatus | null;
  onOrderPlaced: () => void;
  disabledReason?: string | null;
  statusLine?: string;
}

export default function TradePanel({
  account,
  positions,
  currentSymbol,
  brokerStatus,
  onOrderPlaced,
  disabledReason,
  statusLine,
}: TradePanelProps) {
  const [qty, setQty] = useState(1);
  const [limitPrice, setLimitPrice] = useState("");
  const [confirmLive, setConfirmLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const isIBKR = brokerStatus?.broker === "ibkr";
  const ibkrReady = Boolean(
    brokerStatus?.configured &&
    brokerStatus?.live_trading_enabled &&
    brokerStatus?.order_transmit,
  );
  const brokerDisabledReason =
    isIBKR && !ibkrReady
      ? "IBKR live trading requires IBKR_LIVE_TRADING_ENABLED=true and IBKR_ORDER_TRANSMIT=true."
      : null;
  const effectiveDisabledReason = disabledReason ?? brokerDisabledReason;
  const brokerLabel = brokerStatus?.broker
    ? brokerStatus.broker.toUpperCase()
    : "BROKER";
  const parsedLimitPrice = Number.parseFloat(limitPrice);

  const handleOrder = async (side: "buy" | "sell") => {
    setLoading(true);
    setError("");
    try {
      await submitOrder(
        currentSymbol,
        qty,
        side,
        isIBKR
          ? {
              order_type: "limit",
              limit_price: Number.isFinite(parsedLimitPrice)
                ? parsedLimitPrice
                : null,
              confirm_live: confirmLive,
            }
          : { order_type: "market" },
      );
      onOrderPlaced();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Order failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-white/10 bg-[#0b1524]/90 p-4 shadow-[0_18px_60px_-28px_rgba(15,23,42,0.95)]">
      <PaperStrategyPanel
        strategyName="brooks_small_pb_trend"
        disabledReason={disabledReason}
        onRunnerAction={onOrderPlaced}
      />
      <PaperStrategyPanel
        strategyName="brooks_breakout_pullback"
        disabledReason={disabledReason}
        onRunnerAction={onOrderPlaced}
      />
      <PaperStrategyPanel
        strategyName="brooks_pullback_count"
        disabledReason={disabledReason}
        defaultFixedQuantity={50}
        onRunnerAction={onOrderPlaced}
      />

      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
            Execution · {brokerLabel}
          </p>
          <h3 className="mt-2 text-sm font-semibold text-white">
            Manual order control
          </h3>
        </div>
        {statusLine && (
          <p className="max-w-[160px] text-right text-[11px] text-slate-500">
            {statusLine}
          </p>
        )}
      </div>

      {isIBKR && (
        <div className="rounded-2xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-rose-200">
                IBKR Live
              </p>
              <p className="mt-1 text-slate-200">
                Limit orders only · max ${brokerStatus?.max_order_usd ?? "n/a"} per
                order
              </p>
            </div>
            <span
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                ibkrReady
                  ? "bg-emerald-400/15 text-emerald-200"
                  : "bg-amber-400/15 text-amber-100"
              }`}
            >
              {ibkrReady ? "ARMED" : "LOCKED"}
            </span>
          </div>
          {brokerStatus?.allowed_symbols && brokerStatus.allowed_symbols.length > 0 && (
            <p className="mt-2 text-xs text-slate-400">
              Allowed: {brokerStatus.allowed_symbols.join(", ")}
            </p>
          )}
        </div>
      )}

      {account && (
        <div className="grid grid-cols-2 gap-3 rounded-2xl border border-white/5 bg-white/[0.03] p-3 text-sm">
          <div>
            <span className="text-slate-500">Equity</span>
            <p className="font-mono text-white">
              ${account.equity.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Cash</span>
            <p className="font-mono text-white">
              ${account.cash.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-slate-500">P&L</span>
            <p
              className={`font-mono ${account.pnl >= 0 ? "text-green-400" : "text-red-400"}`}
            >
              {account.pnl >= 0 ? "+" : ""}${account.pnl.toFixed(2)} (
              {account.pnl_pct.toFixed(2)}%)
            </p>
          </div>
          <div>
            <span className="text-slate-500">Buying Power</span>
            <p className="font-mono text-white">
              ${account.buying_power.toLocaleString()}
            </p>
          </div>
        </div>
      )}

      {!account && (
        <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-slate-400">
          Account snapshot unavailable right now. If the workspace is degraded or
          disconnected, cached market data can still load while trading remains
          paused.
        </div>
      )}

      <div className="border-t border-white/10 pt-3">
        <label className="mb-1 block text-sm text-slate-400">
          Quantity for {currentSymbol}
        </label>
        <input
          type="number"
          min={1}
          value={qty}
          onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm font-mono text-white"
        />
        {isIBKR && (
          <div className="mt-3 space-y-3">
            <label className="block text-sm text-slate-400">
              Limit price
            </label>
            <input
              type="number"
              min={0.01}
              step={0.01}
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm font-mono text-white"
            />
            <label className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={confirmLive}
                onChange={(e) => setConfirmLive(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-white/20 bg-slate-950"
              />
              <span>
                Confirm this is a live IBKR order for a small-size experiment.
              </span>
            </label>
          </div>
        )}
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => handleOrder("buy")}
            disabled={loading || Boolean(effectiveDisabledReason)}
            className="flex-1 rounded-xl bg-emerald-500/90 py-2 text-sm font-medium text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            BUY
          </button>
          <button
            onClick={() => handleOrder("sell")}
            disabled={loading || Boolean(effectiveDisabledReason)}
            className="flex-1 rounded-xl bg-rose-500/90 py-2 text-sm font-medium text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            SELL
          </button>
        </div>
        {effectiveDisabledReason && (
          <p className="mt-2 text-xs text-amber-300">
            {effectiveDisabledReason}
          </p>
        )}
        {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
      </div>

      {positions.length > 0 && (
        <div className="border-t border-white/10 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm text-slate-300">Positions</h3>
            <span className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
              {positions.length} open
            </span>
          </div>
          <div className="space-y-2">
            {positions.map((p) => (
              <div
                key={p.symbol}
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium text-white">{p.symbol}</span>
                  <span className="ml-2 text-slate-500">{p.qty} shares</span>
                </div>
                <span
                  className={`font-mono ${p.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {p.unrealized_pnl >= 0 ? "+" : ""}$
                  {p.unrealized_pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
