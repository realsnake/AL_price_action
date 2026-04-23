import { useState, useEffect } from "react";
import { getStrategies, getSignals } from "../services/api";
import type { StrategyInfo, Signal, Timeframe } from "../types";

interface StrategyPanelProps {
  symbol: string;
  timeframe: Timeframe;
  startDate: string;
  onSignals: (signals: Signal[]) => void;
  disabledReason?: string | null;
}

export default function StrategyPanel({
  symbol,
  timeframe,
  startDate,
  onSignals,
  disabledReason,
}: StrategyPanelProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [signalCount, setSignalCount] = useState(0);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (disabledReason) return;

    getStrategies()
      .then((list) => {
        setStrategies(list);
        setLoadError("");
        if (list.length > 0) {
          setSelected((prev) => prev || list[0].name);
          setParams((prev) =>
            Object.keys(prev).length > 0 ? prev : list[0].default_params,
          );
        }
      })
      .catch(() => {
        setLoadError("Strategy catalog unavailable right now.");
      });
  }, [disabledReason]);

  const handleStrategyChange = (name: string) => {
    setSelected(name);
    const s = strategies.find((s) => s.name === name);
    if (s) setParams({ ...s.default_params });
    onSignals([]);
    setSignalCount(0);
  };

  const handleParamChange = (key: string, value: string) => {
    setParams((prev) => ({ ...prev, [key]: Number(value) || value }));
  };

  const runStrategy = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      const signals = await getSignals(selected, symbol, timeframe, startDate, params);
      onSignals(signals);
      setSignalCount(signals.length);
    } catch {
      onSignals([]);
      setSignalCount(0);
    } finally {
      setLoading(false);
    }
  };

  const currentStrategy = strategies.find((s) => s.name === selected);

  return (
    <div className="space-y-3 rounded-2xl border border-white/10 bg-[#0b1524]/90 p-4 shadow-[0_18px_60px_-28px_rgba(15,23,42,0.95)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
            Scan
          </p>
          <h3 className="mt-2 text-sm font-semibold text-white">
            Strategy explorer
          </h3>
        </div>
        <p className="max-w-[150px] text-right text-[11px] text-slate-500">
          {symbol} · {timeframe}
        </p>
      </div>

      <select
        value={selected}
        onChange={(e) => handleStrategyChange(e.target.value)}
        className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white"
      >
        {strategies.map((s) => (
          <option key={s.name} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>

      {currentStrategy && (
        <p className="text-xs text-slate-400">{currentStrategy.description}</p>
      )}

      <div className="space-y-2">
        {Object.entries(params).map(([key, val]) => (
          <div key={key} className="flex items-center gap-2">
            <label className="w-24 shrink-0 text-xs text-slate-400">{key}</label>
            <input
              type="number"
              value={String(val)}
              onChange={(e) => handleParamChange(key, e.target.value)}
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
        ))}
      </div>

      <button
        onClick={runStrategy}
        disabled={loading || Boolean(disabledReason) || strategies.length === 0}
        className="w-full rounded-xl bg-cyan-500/90 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Running..." : "Run Strategy"}
      </button>

      {disabledReason && (
        <p className="text-xs text-amber-300">{disabledReason}</p>
      )}
      {!disabledReason && loadError && (
        <p className="text-xs text-red-300">{loadError}</p>
      )}
      {signalCount > 0 && (
        <p className="text-xs text-slate-400">
          Found {signalCount} signal{signalCount > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
