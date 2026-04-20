import { useEffect, useMemo, useState } from "react";
import {
  getPhase1PaperStrategyHistory,
  getPhase1PaperStrategyReadiness,
  getPhase1PaperStrategyStatus,
  startPhase1PaperStrategy,
  stopPhase1PaperStrategy,
} from "../services/api";
import type {
  PaperStrategyReadiness,
  PaperStrategyStatus,
  TradeHistoryEntry,
} from "../types";
import useWebSocket from "../hooks/useWebSocket";

interface PaperStrategyPanelProps {
  disabledReason?: string | null;
  onRunnerAction?: () => void;
}

export default function PaperStrategyPanel({
  disabledReason,
  onRunnerAction,
}: PaperStrategyPanelProps) {
  const [status, setStatus] = useState<PaperStrategyStatus | null>(null);
  const [readiness, setReadiness] = useState<PaperStrategyReadiness | null>(null);
  const [recentTrades, setRecentTrades] = useState<TradeHistoryEntry[]>([]);
  const [fixedQuantity, setFixedQuantity] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshStatus = async () => {
    try {
      const [next, history, readinessInfo] = await Promise.all([
        getPhase1PaperStrategyStatus(),
        getPhase1PaperStrategyHistory(8),
        getPhase1PaperStrategyReadiness(),
      ]);
      setStatus(next);
      setRecentTrades(history);
      setReadiness(readinessInfo);
      setFixedQuantity(next.fixed_quantity);
      setError("");
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to load paper strategy status";
      setError(message);
    }
  };

  useWebSocket({
    url: "/ws/trades",
    onMessage: (raw) => {
      const msg = raw as {
        type?: string;
        symbol?: string;
        strategy?: string | null;
      };
      if (
        (msg.type === "trade" || msg.type === "trade_update") &&
        msg.symbol === "QQQ" &&
        msg.strategy === "brooks_small_pb_trend"
      ) {
        void refreshStatus();
      }
    },
  });

  useEffect(() => {
    void refreshStatus();
    const id = window.setInterval(() => {
      void refreshStatus();
    }, 15000);
    return () => window.clearInterval(id);
  }, []);

  const canStart = useMemo(
    () => !loading && !status?.running && !disabledReason,
    [loading, status?.running, disabledReason],
  );

  const canStop = useMemo(
    () => !loading && Boolean(status?.running),
    [loading, status?.running],
  );

  const handleStart = async () => {
    setLoading(true);
    setError("");
    try {
      const next = await startPhase1PaperStrategy({ fixed_quantity: fixedQuantity });
      setStatus(next);
      void refreshStatus();
      onRunnerAction?.();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to start paper strategy";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError("");
    try {
      const next = await stopPhase1PaperStrategy();
      setStatus(next);
      void refreshStatus();
      onRunnerAction?.();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to stop paper strategy";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (value: string | null) =>
    value ? new Date(value).toLocaleString() : "n/a";

  return (
    <div className="rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-cyan-300/70">
            Auto Paper
          </p>
          <h3 className="mt-2 text-sm font-semibold text-cyan-50">
            QQQ 5m phase1 runner
          </h3>
          <p className="mt-1 text-xs text-slate-400">
            brooks_small_pb_trend · qqq_5m_phase1 · 结构止损 · 1R 后跌破已确认回调低点并收回 EMA20 下方动态离场
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
            status?.running
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-slate-500/15 text-slate-300"
          }`}
        >
          {status?.running ? "RUNNING" : "STOPPED"}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <label className="mb-1 block text-xs text-slate-400">
            Fixed quantity
          </label>
          <input
            type="number"
            min={1}
            value={fixedQuantity}
            onChange={(e) => setFixedQuantity(Math.max(1, Number(e.target.value) || 1))}
            disabled={Boolean(status?.running)}
            className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 font-mono text-white disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
          <p className="text-xs text-slate-500">Last completed 5m bar</p>
          <p className="mt-1 font-mono text-white">
            {formatTimestamp(status?.last_completed_bar_time ?? null)}
          </p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
          <p className="text-xs text-slate-500">Buffered bars</p>
          <p className="mt-1 font-mono text-white">{status?.bar_count ?? 0}</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
          <p className="text-xs text-slate-500">Orders submitted</p>
          <p className="mt-1 font-mono text-white">{status?.orders_submitted ?? 0}</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
          <p className="text-xs text-slate-500">Last live 1m bar</p>
          <p className="mt-1 font-mono text-white">
            {formatTimestamp(status?.last_live_bar_at ?? null)}
          </p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
          <p className="text-xs text-slate-500">Last trade update</p>
          <p className="mt-1 font-mono text-white">
            {formatTimestamp(status?.last_trade_update_at ?? null)}
          </p>
        </div>
      </div>

      {readiness && (
        <div className="mt-3 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-400">
              Phase1 preflight
            </p>
            <span
              className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                readiness.ready
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-amber-500/15 text-amber-300"
              }`}
            >
              {readiness.ready ? "READY" : "CHECK REQUIRED"}
            </span>
          </div>
          <div className="mt-2 rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-xs text-slate-300">
            Market session:{" "}
            <span className={readiness.market_session === "open" ? "text-emerald-300" : "text-slate-200"}>
              {readiness.market_session}
            </span>
            {readiness.market_session === "open" && readiness.current_session_close ? (
              <span className="text-slate-400">
                {" "}
                · closes {formatTimestamp(readiness.current_session_close)}
              </span>
            ) : readiness.next_session_open ? (
              <span className="text-slate-400">
                {" "}
                · next open {formatTimestamp(readiness.next_session_open)}
              </span>
            ) : null}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Paper mode:{" "}
              <span className={readiness.paper_trading ? "text-emerald-300" : "text-amber-300"}>
                {readiness.paper_trading ? "on" : "off"}
              </span>
            </div>
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Alpaca:{" "}
              <span className={readiness.alpaca_configured ? "text-emerald-300" : "text-amber-300"}>
                {readiness.alpaca_configured ? "configured" : "missing creds"}
              </span>
            </div>
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Account:{" "}
              <span className={readiness.account_status === "ok" ? "text-emerald-300" : "text-amber-300"}>
                {readiness.account_status}
              </span>
            </div>
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Market stream:{" "}
              <span className={readiness.market_stream_running ? "text-emerald-300" : "text-amber-300"}>
                {readiness.market_stream_running ? "running" : "stopped"}
              </span>
            </div>
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Trade updates:{" "}
              <span className={readiness.trade_updates_running ? "text-emerald-300" : "text-amber-300"}>
                {readiness.trade_updates_running ? "running" : "stopped"}
              </span>
            </div>
            <div className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2 text-slate-300">
              Runner:{" "}
              <span className={readiness.runner_running ? "text-cyan-300" : "text-slate-300"}>
                {readiness.runner_running ? "active" : "idle"}
              </span>
            </div>
          </div>
          {readiness.account_error && (
            <p className="mt-2 text-xs text-amber-300">{readiness.account_error}</p>
          )}
          {readiness.warnings.length > 0 && (
            <div className="mt-2 space-y-2">
              {readiness.warnings.map((warning) => (
                <p
                  key={warning}
                  className="rounded-lg border border-amber-300/10 bg-amber-400/[0.05] px-2.5 py-2 text-xs text-amber-100"
                >
                  {warning}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {status?.warnings && status.warnings.length > 0 && (
        <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.22em] text-amber-300/70">
            Runner warnings
          </p>
          <div className="mt-2 space-y-2">
            {status.warnings.map((warning) => (
              <p
                key={warning}
                className="rounded-lg border border-amber-300/10 bg-black/10 px-2.5 py-2 text-xs text-amber-100"
              >
                {warning}
              </p>
            ))}
          </div>
        </div>
      )}

      {status?.position && (
        <div className="mt-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.22em] text-emerald-300/70">
            Open position
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-white">
            <span>{status.position.quantity} shares</span>
            <span>Entry ${status.position.entry_price.toFixed(2)}</span>
            <span>Stop ${status.position.stop_price.toFixed(2)}</span>
            <span>
              {status.position.target_price == null
                ? "无固定止盈"
                : `目标 $${status.position.target_price.toFixed(2)}`}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-300">{status.position.reason}</p>
        </div>
      )}

      {status?.pending_order && (
        <div className="mt-3 rounded-xl border border-amber-400/15 bg-amber-400/[0.04] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.22em] text-amber-300/70">
            Pending order
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-white">
            <span>{status.pending_order.side.toUpperCase()}</span>
            <span>{status.pending_order.quantity} shares</span>
            <span className="col-span-2 break-all text-[11px] text-slate-300">
              {status.pending_order.alpaca_order_id}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-300">
            {status.pending_order.status} · {status.pending_order.reason}
          </p>
          <p className="mt-1 text-[11px] text-slate-400">
            Submitted {formatTimestamp(status.pending_order.submitted_at)}
          </p>
        </div>
      )}

      {status && status.recent_events.length > 0 && (
        <div className="mt-3 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-400">
            Recent events
          </p>
          <div className="mt-2 max-h-56 space-y-2 overflow-auto">
            {[...status.recent_events].slice().reverse().map((event) => (
              <div
                key={`${event.timestamp}-${event.type}-${event.message}`}
                className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-cyan-200">
                    {event.type.replaceAll("_", " ")}
                  </span>
                  <span className="text-[11px] font-mono text-slate-500">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-300">{event.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {recentTrades.length > 0 && (
        <div className="mt-3 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-400">
              Recent phase1 trades
            </p>
            <span className="text-[11px] text-slate-500">{recentTrades.length} shown</span>
          </div>
          <div className="mt-2 space-y-2">
            {recentTrades.map((trade) => (
              <div
                key={trade.id}
                className="rounded-lg border border-white/5 bg-black/10 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`text-[11px] font-medium uppercase tracking-[0.16em] ${
                      trade.side === "buy" ? "text-emerald-300" : "text-rose-300"
                    }`}
                  >
                    {trade.side} · {trade.status}
                  </span>
                  <span className="text-[11px] font-mono text-slate-500">
                    {formatTimestamp(trade.created_at)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-3 text-xs text-slate-300">
                  <span>{trade.quantity} shares</span>
                  <span>${trade.price.toFixed(2)}</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {trade.signal_reason || "phase1 trade"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {disabledReason && (
        <p className="mt-3 text-xs text-amber-300">{disabledReason}</p>
      )}
      {status?.last_error && (
        <p className="mt-3 text-xs text-amber-300">{status.last_error}</p>
      )}
      {error && <p className="mt-3 text-xs text-red-300">{error}</p>}

      <div className="mt-4 flex gap-2">
        <button
          onClick={() => void handleStart()}
          disabled={!canStart}
          className="flex-1 rounded-xl bg-cyan-500/90 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Start phase1
        </button>
        <button
          onClick={() => void handleStop()}
          disabled={!canStop}
          className="flex-1 rounded-xl bg-slate-700 py-2 text-sm font-medium text-white transition hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Stop runner
        </button>
      </div>
    </div>
  );
}
