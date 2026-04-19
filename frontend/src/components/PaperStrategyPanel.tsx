import { useEffect, useMemo, useState } from "react";
import {
  getPhase1PaperStrategyStatus,
  startPhase1PaperStrategy,
  stopPhase1PaperStrategy,
} from "../services/api";
import type { PaperStrategyStatus } from "../types";

interface PaperStrategyPanelProps {
  disabledReason?: string | null;
  onRunnerAction?: () => void;
}

export default function PaperStrategyPanel({
  disabledReason,
  onRunnerAction,
}: PaperStrategyPanelProps) {
  const [status, setStatus] = useState<PaperStrategyStatus | null>(null);
  const [fixedQuantity, setFixedQuantity] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshStatus = async () => {
    try {
      const next = await getPhase1PaperStrategyStatus();
      setStatus(next);
      setFixedQuantity(next.fixed_quantity);
      setError("");
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to load paper strategy status";
      setError(message);
    }
  };

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
      onRunnerAction?.();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to stop paper strategy";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

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
            brooks_small_pb_trend · qqq_5m_phase1 · 2% stop · 4% target
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
            {status?.last_completed_bar_time
              ? new Date(status.last_completed_bar_time).toLocaleString()
              : "n/a"}
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
      </div>

      {status?.position && (
        <div className="mt-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.22em] text-emerald-300/70">
            Open position
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-white">
            <span>{status.position.quantity} shares</span>
            <span>Entry ${status.position.entry_price.toFixed(2)}</span>
            <span>Stop ${status.position.stop_price.toFixed(2)}</span>
            <span>Target ${status.position.target_price.toFixed(2)}</span>
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
