import { useState, useEffect } from "react";
import { getStrategies, getSignals } from "../services/api";
import type { StrategyInfo, Signal, Timeframe } from "../types";

interface StrategyPanelProps {
  symbol: string;
  timeframe: Timeframe;
  startDate: string;
  onSignals: (signals: Signal[]) => void;
}

export default function StrategyPanel({
  symbol,
  timeframe,
  startDate,
  onSignals,
}: StrategyPanelProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [signalCount, setSignalCount] = useState(0);

  useEffect(() => {
    getStrategies().then((list) => {
      setStrategies(list);
      if (list.length > 0) {
        setSelected(list[0].name);
        setParams(list[0].default_params);
      }
    });
  }, []);

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
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 space-y-3">
      <h3 className="text-sm font-medium text-gray-300">Strategy</h3>

      {/* Strategy Select */}
      <select
        value={selected}
        onChange={(e) => handleStrategyChange(e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
      >
        {strategies.map((s) => (
          <option key={s.name} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>

      {currentStrategy && (
        <p className="text-xs text-gray-500">{currentStrategy.description}</p>
      )}

      {/* Params */}
      <div className="space-y-2">
        {Object.entries(params).map(([key, val]) => (
          <div key={key} className="flex items-center gap-2">
            <label className="text-xs text-gray-400 w-24 shrink-0">{key}</label>
            <input
              type="number"
              value={String(val)}
              onChange={(e) => handleParamChange(key, e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm font-mono"
            />
          </div>
        ))}
      </div>

      <button
        onClick={runStrategy}
        disabled={loading}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2 rounded text-sm font-medium"
      >
        {loading ? "Running..." : "Run Strategy"}
      </button>

      {signalCount > 0 && (
        <p className="text-xs text-gray-400">
          Found {signalCount} signal{signalCount > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
