import { useState, useEffect } from "react";
import { getStrategies, runBacktest } from "../services/api";
import type {
  StrategyInfo,
  BacktestResult,
  ResearchProfile,
  Signal,
  Timeframe,
} from "../types";

const RESEARCH_SYMBOL = "QQQ";
const RESEARCH_TIMEFRAME: Timeframe = "5m";
const RESEARCH_PROFILE: ResearchProfile = "qqq_5m_phase1";

interface BacktestPanelProps {
  onSignals: (signals: Signal[]) => void;
  onEquityCurve: (curve: { time: string; equity: number }[]) => void;
  onActivateResearchContext: () => void;
  disabledReason?: string | null;
}

export default function BacktestPanel({
  onSignals,
  onEquityCurve,
  onActivateResearchContext,
  disabledReason,
}: BacktestPanelProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loadError, setLoadError] = useState("");
  const [config, setConfig] = useState({
    start: "2025-01-01",
    initial_capital: 100000,
    stop_loss_pct: 2,
    take_profit_pct: 4,
    risk_per_trade_pct: 2,
  });

  useEffect(() => {
    if (disabledReason) return;

    getStrategies()
      .then((list) => {
        const brooks = list.filter((s) => s.name.startsWith("brooks_"));
        setStrategies(brooks);
        setLoadError("");
        if (brooks.length > 0) {
          setSelected((prev) => prev || brooks[0].name);
          setParams((prev) =>
            Object.keys(prev).length > 0 ? prev : { ...brooks[0].default_params },
          );
        }
      })
      .catch(() => {
        setLoadError("Backtest catalog unavailable right now.");
      });
  }, [disabledReason]);

  const handleStrategyChange = (name: string) => {
    setSelected(name);
    const s = strategies.find((s) => s.name === name);
    if (s) setParams({ ...s.default_params });
    setResult(null);
  };

  const handleRun = async () => {
    if (!selected) return;
    onActivateResearchContext();
    setLoading(true);
    setResult(null);
    setAllResults(null);
    try {
      const res = await runBacktest({
        strategy: selected,
        symbol: RESEARCH_SYMBOL,
        timeframe: RESEARCH_TIMEFRAME,
        start: config.start,
        params,
        initial_capital: config.initial_capital,
        stop_loss_pct: config.stop_loss_pct,
        take_profit_pct: config.take_profit_pct,
        risk_per_trade_pct: config.risk_per_trade_pct,
        researchProfile: RESEARCH_PROFILE,
      });
      setResult(res);
      onEquityCurve(res.equity_curve);

      // Convert trades to signals for chart markers
      const signals: Signal[] = res.trades.flatMap((t) => {
        const entry: Signal = {
          symbol: RESEARCH_SYMBOL,
          signal_type: t.side === "long" ? "buy" : "sell",
          price: t.entry_price,
          quantity: t.quantity,
          reason: t.reason,
          timestamp: t.entry_time,
        };
        const exit: Signal = {
          symbol: RESEARCH_SYMBOL,
          signal_type: t.side === "long" ? "sell" : "buy",
          price: t.exit_price,
          quantity: t.quantity,
          reason: `Exit: ${t.exit_reason} (${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(0)})`,
          timestamp: t.exit_time,
        };
        return [entry, exit];
      });
      onSignals(signals);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleRunAll = async () => {
    onActivateResearchContext();
    setLoading(true);
    setResult(null);
    setAllResults(null);

    const results: BacktestResult[] = [];
    for (const s of strategies) {
      try {
        const res = await runBacktest({
          strategy: s.name,
          symbol: RESEARCH_SYMBOL,
          timeframe: RESEARCH_TIMEFRAME,
          start: config.start,
          params: s.default_params,
          initial_capital: config.initial_capital,
          stop_loss_pct: config.stop_loss_pct,
          take_profit_pct: config.take_profit_pct,
          risk_per_trade_pct: config.risk_per_trade_pct,
          researchProfile: RESEARCH_PROFILE,
        });
        results.push(res);
      } catch {
        // skip failed
      }
    }

    setAllResults(results);
    setLoading(false);
  };

  const [allResults, setAllResults] = useState<BacktestResult[] | null>(null);

  const currentStrategy = strategies.find((s) => s.name === selected);
  const usesStructuralPhase1Exits = selected === "brooks_small_pb_trend";

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-2xl border border-white/10 bg-[#0b1524]/90 p-4 shadow-[0_18px_60px_-28px_rgba(15,23,42,0.95)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
              Research
            </p>
            <h3 className="mt-2 text-sm font-semibold text-violet-200">
              Brooks backtest lab
            </h3>
          </div>
          <p className="max-w-[150px] text-right text-[11px] text-slate-500">
            QQQ · 5m · RTH · long-only
          </p>
        </div>

        <select
          value={selected}
          onChange={(e) => handleStrategyChange(e.target.value)}
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white"
        >
          {strategies.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name.replace("brooks_", "").replace(/_/g, " ")}
            </option>
          ))}
        </select>

        {currentStrategy && (
          <p className="text-xs text-slate-400">{currentStrategy.description}</p>
        )}

        <div className="space-y-1">
          {Object.entries(params).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="w-28 shrink-0 text-xs text-slate-400">{key}</label>
              <input
                type="number"
                value={String(val)}
                onChange={(e) =>
                  setParams((p) => ({
                    ...p,
                    [key]: Number(e.target.value) || e.target.value,
                  }))
                }
                className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
              />
            </div>
          ))}
        </div>

        <div className="space-y-1 border-t border-white/10 pt-2">
          <p className="rounded-lg border border-cyan-400/10 bg-cyan-400/5 px-3 py-2 text-xs text-cyan-100">
            Fixed research path: {RESEARCH_SYMBOL} on {RESEARCH_TIMEFRAME} bars
            with the {RESEARCH_PROFILE} profile.
          </p>
          {usesStructuralPhase1Exits && (
            <p className="rounded-lg border border-amber-400/10 bg-amber-400/5 px-3 py-2 text-xs text-amber-100">
              `brooks_small_pb_trend` 在 `qqq_5m_phase1` 下会使用结构止损 + `1R` 后跌破已确认回调低点并收回 `EMA20` 下方的动态离场，仍保留收盘强平。
            </p>
          )}
          <div className="flex items-center gap-2">
            <label className="w-28 shrink-0 text-xs text-slate-400">
              Start Date
            </label>
            <input
              value={config.start}
              onChange={(e) => setConfig((c) => ({ ...c, start: e.target.value }))}
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="w-28 shrink-0 text-xs text-slate-400">
              Capital ($)
            </label>
            <input
              type="number"
              value={config.initial_capital}
              onChange={(e) =>
                setConfig((c) => ({ ...c, initial_capital: Number(e.target.value) }))
              }
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="w-28 shrink-0 text-xs text-slate-400">
              Stop Loss %
            </label>
            <input
              type="number"
              step="0.5"
              value={config.stop_loss_pct}
              onChange={(e) =>
                setConfig((c) => ({ ...c, stop_loss_pct: Number(e.target.value) }))
              }
              disabled={usesStructuralPhase1Exits}
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="w-28 shrink-0 text-xs text-slate-400">
              Take Profit %
            </label>
            <input
              type="number"
              step="0.5"
              value={config.take_profit_pct}
              onChange={(e) =>
                setConfig((c) => ({ ...c, take_profit_pct: Number(e.target.value) }))
              }
              disabled={usesStructuralPhase1Exits}
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="w-28 shrink-0 text-xs text-slate-400">
              Risk/Trade %
            </label>
            <input
              type="number"
              step="0.5"
              value={config.risk_per_trade_pct}
              onChange={(e) =>
                setConfig((c) => ({
                  ...c,
                  risk_per_trade_pct: Number(e.target.value),
                }))
              }
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm font-mono text-white"
            />
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleRun}
            disabled={loading || Boolean(disabledReason) || !selected}
            className="flex-1 rounded-xl bg-cyan-500/90 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Running..." : "Run Backtest"}
          </button>
          <button
            onClick={handleRunAll}
            disabled={loading || Boolean(disabledReason) || strategies.length === 0}
            className="flex-1 rounded-xl bg-violet-500/90 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Run All
          </button>
        </div>
        {disabledReason && (
          <p className="text-xs text-amber-300">{disabledReason}</p>
        )}
        {!disabledReason && loadError && (
          <p className="text-xs text-red-300">{loadError}</p>
        )}
      </div>

      {/* Single Result */}
      {result && <BacktestResultCard result={result} />}

      {/* All Results Comparison */}
      {allResults && allResults.length > 0 && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-800">
            <h3 className="text-sm font-medium text-purple-400">All Strategies Comparison</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="text-left px-3 py-2">Strategy</th>
                  <th className="text-right px-3 py-2">Trades</th>
                  <th className="text-right px-3 py-2">Win%</th>
                  <th className="text-right px-3 py-2">PF</th>
                  <th className="text-right px-3 py-2">Return</th>
                  <th className="text-right px-3 py-2">MaxDD</th>
                  <th className="text-right px-3 py-2">Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {allResults.sort((a, b) => b.total_return_pct - a.total_return_pct).map((r) => (
                  <tr key={r.strategy} className="border-b border-gray-800/50 hover:bg-gray-800/50">
                    <td className="px-3 py-2 text-gray-300">{r.strategy.replace("brooks_", "")}</td>
                    <td className="px-3 py-2 text-right font-mono">{r.total_trades}</td>
                    <td className="px-3 py-2 text-right font-mono">{r.win_rate}%</td>
                    <td className="px-3 py-2 text-right font-mono">{r.profit_factor}</td>
                    <td className={`px-3 py-2 text-right font-mono ${r.total_return >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {r.total_return >= 0 ? "+" : ""}{r.total_return_pct}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-red-400">{r.max_drawdown_pct}%</td>
                    <td className={`px-3 py-2 text-right font-mono ${r.sharpe_ratio >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {r.sharpe_ratio}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function BacktestResultCard({ result: r }: { result: BacktestResult }) {
  const [showTrades, setShowTrades] = useState(false);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      {/* Summary */}
      <div className="px-4 py-3 border-b border-gray-800">
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-300">{r.strategy.replace("brooks_", "").replace(/_/g, " ")}</span>
          <span className="text-xs text-gray-500">{r.period}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-px bg-gray-800">
        <StatCell label="Return" value={`${r.total_return >= 0 ? "+" : ""}$${r.total_return.toLocaleString()}`}
          sub={`${r.total_return_pct}%`} positive={r.total_return >= 0} />
        <StatCell label="Win Rate" value={`${r.win_rate}%`}
          sub={`${r.winning_trades}W / ${r.losing_trades}L`} positive={r.win_rate > 50} />
        <StatCell label="Profit Factor" value={String(r.profit_factor)}
          sub={`${r.total_trades} trades`} positive={r.profit_factor > 1} />
        <StatCell label="Avg Win" value={`$${r.avg_win.toLocaleString()}`} positive={true} />
        <StatCell label="Avg Loss" value={`$${r.avg_loss.toLocaleString()}`} positive={false} />
        <StatCell label="Max Drawdown" value={`${r.max_drawdown_pct}%`}
          sub={`$${r.max_drawdown.toLocaleString()}`} positive={false} />
        <StatCell label="Sharpe" value={String(r.sharpe_ratio)} positive={r.sharpe_ratio > 0} />
        <StatCell label="Initial" value={`$${r.initial_capital.toLocaleString()}`} />
        <StatCell label="Final" value={`$${r.final_capital.toLocaleString()}`} positive={r.final_capital > r.initial_capital} />
      </div>

      {/* Trades Toggle */}
      {r.trades.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-800">
          <button onClick={() => setShowTrades(!showTrades)}
            className="text-xs text-blue-400 hover:text-blue-300">
            {showTrades ? "Hide" : "Show"} {r.trades.length} trades
          </button>
        </div>
      )}

      {showTrades && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500">
                <th className="text-left px-3 py-1">Entry</th>
                <th className="text-left px-3 py-1">Side</th>
                <th className="text-right px-3 py-1">Entry$</th>
                <th className="text-right px-3 py-1">Exit$</th>
                <th className="text-right px-3 py-1">P&L</th>
                <th className="text-left px-3 py-1">Exit</th>
                <th className="text-left px-3 py-1">Reason</th>
              </tr>
            </thead>
            <tbody>
              {r.trades.map((t, i) => (
                <tr key={i} className="border-b border-gray-800/50">
                  <td className="px-3 py-1 font-mono text-gray-400">{t.entry_time.slice(0, 10)}</td>
                  <td className="px-3 py-1">
                    <span className={t.side === "long" ? "text-green-400" : "text-red-400"}>
                      {t.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-1 text-right font-mono">${t.entry_price}</td>
                  <td className="px-3 py-1 text-right font-mono">${t.exit_price}</td>
                  <td className={`px-3 py-1 text-right font-mono ${t.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {t.pnl >= 0 ? "+" : ""}${t.pnl}
                  </td>
                  <td className="px-3 py-1 text-gray-400">{t.exit_reason}</td>
                  <td className="px-3 py-1 text-gray-500 truncate max-w-[150px]">{t.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCell({ label, value, sub, positive }: {
  label: string; value: string; sub?: string; positive?: boolean;
}) {
  return (
    <div className="bg-gray-900 px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-sm font-mono font-medium ${
        positive === undefined ? "text-white" : positive ? "text-green-400" : "text-red-400"
      }`}>{value}</div>
      {sub && <div className="text-xs text-gray-600">{sub}</div>}
    </div>
  );
}
