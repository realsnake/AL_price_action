import { useState, useEffect, useCallback } from "react";
import Chart from "./components/Chart";
import TradePanel from "./components/TradePanel";
import StrategyPanel from "./components/StrategyPanel";
import BacktestPanel from "./components/BacktestPanel";
import { useOffline } from "./hooks/useOffline";
import useMarketData from "./hooks/useMarketData";
import useSystemStatus from "./hooks/useSystemStatus";
import useWebSocket from "./hooks/useWebSocket";
import {
  formatBeijingDate,
  formatBeijingDateTime,
  formatBeijingTime,
} from "./utils/time";
import {
  getBars,
  getAccount,
  getQuote,
  getPhase1PaperStrategyStatuses,
  getPositions,
} from "./services/api";
import type {
  Bar,
  Signal,
  Account,
  Position,
  Timeframe,
  PaperStrategyStatus,
  MarketQuote,
} from "./types";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "1D"];
const BROOKS_COMBO_LABEL = "QQQ 5m Brooks 组合";
const MARKET_DAY_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function getDefaultStart(tf: Timeframe): string {
  const d = new Date();
  switch (tf) {
    case "1m":
    case "5m":
      d.setDate(d.getDate() - 2);
      break;
    case "15m":
      d.setDate(d.getDate() - 7);
      break;
    case "1h":
      d.setDate(d.getDate() - 30);
      break;
    case "1D":
      d.setFullYear(d.getFullYear() - 1);
      break;
  }
  return d.toISOString().split("T")[0];
}

function marketDayLabel(iso: string): string {
  return MARKET_DAY_FORMATTER.format(new Date(iso));
}

function getPreviousSessionClose(bars: Bar[]): number | null {
  if (bars.length < 2) {
    return null;
  }

  const latestDay = marketDayLabel(bars[bars.length - 1].time);
  for (let index = bars.length - 2; index >= 0; index -= 1) {
    if (marketDayLabel(bars[index].time) !== latestDay) {
      return bars[index].close;
    }
  }

  return null;
}

type SidebarTab = "trade" | "backtest";
type ChartRequest = {
  start: string;
  limit: number;
  researchProfile?: "qqq_5m_phase1";
};

export default function App() {
  const [symbol, setSymbol] = useState("QQQ");
  const [symbolInput, setSymbolInput] = useState("QQQ");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [chartRequest, setChartRequest] = useState<ChartRequest | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [quote, setQuote] = useState<MarketQuote | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notifications, setNotifications] = useState<string[]>([]);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("trade");
  const [equityCurve, setEquityCurve] = useState<{ time: string; equity: number }[]>([]);
  const [paperRunnerStatuses, setPaperRunnerStatuses] = useState<PaperStrategyStatus[]>([]);

  const startDate = chartRequest?.start ?? getDefaultStart(timeframe);
  const barLimit = chartRequest?.limit ?? 500;

  const { lastBar, connected: marketConnected } = useMarketData(symbol);
  const browserOffline = useOffline();
  const systemStatus = useSystemStatus({
    browserOnline: !browserOffline,
    marketConnected,
  });

  const onTradeMessage = useCallback(
    (raw: unknown) => {
      const msg = raw as { type: string; symbol: string; side: string; qty: number; status: string };
      if (msg.type === "trade") {
        const note = `${msg.side.toUpperCase()} ${msg.qty} ${msg.symbol} - ${msg.status}`;
        setNotifications((prev) => [note, ...prev].slice(0, 10));
        fetchAccountData();
        fetchPaperRunnerStatuses();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useWebSocket({ url: "/ws/trades", onMessage: onTradeMessage });

  useEffect(() => {
    if (!lastBar) return;
    setBars((prev) => {
      if (prev.length === 0) return prev;
      const lastExisting = prev[prev.length - 1];
      if (chartRequest !== null) {
        return prev;
      }
      if (lastExisting.time === lastBar.time) {
        return [...prev.slice(0, -1), lastBar];
      }
      return [...prev, lastBar];
    });
  }, [chartRequest, lastBar]);

  const fetchBars = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getBars(symbol, timeframe, startDate, barLimit, {
        researchProfile: chartRequest?.researchProfile,
      });
      setBars(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load bars";
      setError(msg);
      setBars([]);
    } finally {
      setLoading(false);
    }
  }, [barLimit, chartRequest?.researchProfile, symbol, timeframe, startDate]);

  const fetchAccountData = useCallback(async () => {
    try {
      const [acc, pos] = await Promise.all([getAccount(), getPositions()]);
      setAccount(acc);
      setPositions(pos);
    } catch {
      // secondary
    }
  }, []);

  const fetchPaperRunnerStatuses = useCallback(async () => {
    try {
      const next = await getPhase1PaperStrategyStatuses();
      setPaperRunnerStatuses(next);
    } catch {
      // secondary
    }
  }, []);

  useEffect(() => {
    fetchBars();
  }, [fetchBars]);

  useEffect(() => {
    let cancelled = false;

    const fetchQuote = async () => {
      try {
        const next = await getQuote(symbol);
        if (!cancelled) {
          setQuote(next);
        }
      } catch {
        if (!cancelled) {
          setQuote(null);
        }
      }
    };

    void fetchQuote();
    const id = window.setInterval(() => {
      void fetchQuote();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [symbol]);

  useEffect(() => {
    fetchAccountData();
    const id = window.setInterval(() => {
      void fetchAccountData();
    }, 15000);
    return () => window.clearInterval(id);
  }, [fetchAccountData]);

  useEffect(() => {
    fetchPaperRunnerStatuses();
    const id = window.setInterval(() => {
      void fetchPaperRunnerStatuses();
    }, 15000);
    return () => window.clearInterval(id);
  }, [fetchPaperRunnerStatuses]);

  const handleSymbolSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const s = symbolInput.trim().toUpperCase();
    if (s && s !== symbol) {
      setSymbol(s);
      setChartRequest(null);
      setSignals([]);
      setEquityCurve([]);
    }
  };

  const dismissNotification = (index: number) => {
    setNotifications((prev) => prev.filter((_, i) => i !== index));
  };

  const activeRunners = paperRunnerStatuses.filter((runnerStatus) => runnerStatus.running);
  const healthyActiveRunners = activeRunners.filter(
    (runnerStatus) =>
      !runnerStatus.warnings.some((warning) =>
        warning.includes("No live 1m bars observed"),
      ),
  );
  const spotlightRunner =
    healthyActiveRunners.find((runnerStatus) => runnerStatus.position != null)
    ?? healthyActiveRunners[0]
    ?? activeRunners.find((runnerStatus) => runnerStatus.position != null)
    ?? paperRunnerStatuses[0]
    ?? null;
  const activeRunnerPosition = spotlightRunner?.symbol
    ? positions.find((position) => position.symbol === spotlightRunner.symbol)
    : undefined;
  const runnerStatusPosition = spotlightRunner?.position ?? null;
  const hasRunnerPosition = activeRunnerPosition != null || runnerStatusPosition != null;
  const latestRunnerEvent = spotlightRunner?.recent_events.at(-1);
  const runnerPnLText = activeRunnerPosition
    ? `${activeRunnerPosition.unrealized_pnl >= 0 ? "+" : ""}$${activeRunnerPosition.unrealized_pnl.toFixed(2)} (${activeRunnerPosition.unrealized_pnl_pct.toFixed(2)}%)`
    : runnerStatusPosition
      ? `${runnerStatusPosition.quantity} shares open`
    : `No open ${BROOKS_COMBO_LABEL} position`;
  const runnerPnLClass = activeRunnerPosition
    ? activeRunnerPosition.unrealized_pnl >= 0
      ? "text-emerald-300"
      : "text-rose-300"
    : runnerStatusPosition
      ? "text-emerald-300"
    : "text-slate-300";
  const runnerPositionDetail = activeRunnerPosition
    ? `${activeRunnerPosition.qty} shares @ $${activeRunnerPosition.avg_entry.toFixed(2)}`
    : runnerStatusPosition
      ? `${spotlightRunner?.strategy ?? "runner"} @ $${runnerStatusPosition.entry_price.toFixed(2)} · stop $${runnerStatusPosition.stop_price.toFixed(2)}`
      : `No active ${BROOKS_COMBO_LABEL} position yet`;
  const openRunnerPositions = activeRunners.filter(
    (runnerStatus) => runnerStatus.position != null,
  );
  const executionPulseMessage = spotlightRunner?.pending_order
    ? `${spotlightRunner.pending_order.side.toUpperCase()} ${spotlightRunner.pending_order.quantity} pending`
    : spotlightRunner?.last_live_bar_at
      ? `Last live bar ${formatBeijingTime(spotlightRunner.last_live_bar_at)} · ${healthyActiveRunners.map((runnerStatus) => runnerStatus.strategy).join(" + ")}`
      : activeRunners.length > 0
        ? "Runners are started, but live bar feed is degraded"
        : "Live bar feed still warming up";
  const dayPnLClass =
    account == null
      ? "text-slate-300"
      : account.pnl >= 0
        ? "text-emerald-300"
        : "text-rose-300";
  const latestBar = bars.length > 0 ? bars[bars.length - 1] : null;
  const previousSessionCloseFromBars =
    latestBar != null ? getPreviousSessionClose(bars) : null;
  const previousSessionClose = previousSessionCloseFromBars ?? quote?.previous_close ?? null;
  const displayPrice =
    quote != null
      ? (quote.bid + quote.ask) / 2
      : latestBar?.close ?? null;
  const priceDelta =
    displayPrice != null && previousSessionClose != null
      ? displayPrice - previousSessionClose
      : null;
  const priceDeltaPct =
    priceDelta != null && previousSessionClose != null && previousSessionClose !== 0
      ? (priceDelta / previousSessionClose) * 100
      : null;
  const priceToneClass =
    displayPrice == null
      ? "text-slate-300"
      : priceDelta == null
        ? latestBar != null
          ? latestBar.close >= latestBar.open
            ? "text-green-400"
            : "text-red-400"
          : "text-slate-300"
        : priceDelta >= 0
          ? "text-green-400"
          : "text-red-400"
      ;
  const spotlightTone = spotlightRunner?.running
    ? hasRunnerPosition
      ? activeRunnerPosition == null || activeRunnerPosition.unrealized_pnl >= 0
        ? "border-emerald-400/25 bg-emerald-400/[0.08]"
        : "border-rose-400/25 bg-rose-400/[0.08]"
      : "border-cyan-400/25 bg-cyan-400/[0.08]"
    : "border-white/10 bg-white/[0.03]";

  const activateResearchContext = useCallback((request?: ChartRequest) => {
    const switchingChart = symbol !== "QQQ" || timeframe !== "5m";
    setSymbol("QQQ");
    setSymbolInput("QQQ");
    setTimeframe("5m");
    setChartRequest(request ?? null);
    setSignals([]);
    setEquityCurve([]);
    if (switchingChart || request !== undefined) {
      setBars([]);
      setError("");
      setLoading(true);
    }
  }, [symbol, timeframe]);

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-200">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-white">Stock Trader</h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${
                systemStatus.mode === "live"
                  ? "bg-green-400"
                  : systemStatus.mode === "syncing" || systemStatus.mode === "standby"
                    ? "bg-amber-400"
                    : "bg-red-400"
              }`}
            />
            <span className="text-xs text-gray-500">
              {systemStatus.mode === "live"
                ? "Live"
                : systemStatus.mode === "syncing"
                  ? "Syncing"
                  : systemStatus.mode === "standby"
                    ? "Standby"
                    : "Offline"}
            </span>
          </div>

          <form onSubmit={handleSymbolSubmit} className="flex gap-2">
            <input
              type="text"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
              placeholder="Symbol"
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm font-mono w-28"
            />
            <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm">Go</button>
          </form>

          <div className="flex gap-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => {
                  setTimeframe(tf);
                  setChartRequest(null);
                  setSignals([]);
                  setEquityCurve([]);
                }}
                className={`px-3 py-1.5 rounded text-sm ${tf === timeframe ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}
              >{tf}</button>
            ))}
          </div>
        </div>
      </header>

      {/* Notifications */}
      {notifications.length > 0 && (
        <div className="fixed top-16 right-4 z-50 space-y-2 w-72">
          {notifications.map((note, i) => (
            <div key={i} className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white shadow-lg flex justify-between items-start">
              <span>{note}</span>
              <button onClick={() => dismissNotification(i)} className="text-gray-500 hover:text-white ml-2 text-xs">x</button>
            </div>
          ))}
        </div>
      )}

      {/* Main Content */}
      <div className="flex h-[calc(100vh-57px)]">
        {/* Chart Area */}
        <main className="flex-1 p-4 flex flex-col gap-4 overflow-auto">
          <section className={`rounded-2xl border p-4 ${spotlightTone}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">
                  {BROOKS_COMBO_LABEL}
                </p>
                <h2 className="mt-2 text-base font-semibold text-white">
                  {spotlightRunner?.running
                    ? `${activeRunners.length} Brooks strategies live on ${spotlightRunner.symbol} 5m`
                    : `${BROOKS_COMBO_LABEL} is idle`}
                </h2>
                <p className="mt-1 text-sm text-slate-300">
                  {latestRunnerEvent?.message ?? "Waiting for the next 5m Brooks decision bar."}
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  spotlightRunner?.running
                    ? "bg-cyan-400/15 text-cyan-200"
                    : "bg-slate-500/15 text-slate-300"
                }`}
              >
                {spotlightRunner?.running ? "RUNNING" : "STOPPED"}
              </span>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Account Day P&L
                </p>
                <p className={`mt-2 text-2xl font-semibold ${dayPnLClass}`}>
                  {account == null
                    ? "n/a"
                    : `${account.pnl >= 0 ? "+" : ""}$${account.pnl.toFixed(2)}`}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {account == null ? "Account snapshot pending" : `${account.pnl_pct.toFixed(2)}% vs prior equity`}
                </p>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Brooks Combo Position P&L
                </p>
                <p className={`mt-2 text-2xl font-semibold ${runnerPnLClass}`}>
                  {runnerPnLText}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {runnerPositionDetail}
                </p>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Execution Pulse
                </p>
                <p className="mt-2 text-base font-semibold text-white">
                  {activeRunners.reduce((sum, runnerStatus) => sum + runnerStatus.orders_submitted, 0)} orders submitted
                  {openRunnerPositions.length > 0
                    ? ` · ${openRunnerPositions.length} open Brooks position${openRunnerPositions.length > 1 ? "s" : ""}`
                    : ""}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {executionPulseMessage}
                </p>
              </div>
            </div>
          </section>

          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white">{symbol}</h2>
            {displayPrice != null && (
              <>
                <span className={`text-lg font-mono ${priceToneClass}`}>
                  ${displayPrice.toFixed(2)}
                </span>
                {priceDelta != null && priceDeltaPct != null && (
                  <span className={`text-sm font-mono ${priceToneClass}`}>
                    {priceDelta >= 0 ? "+" : ""}{priceDelta.toFixed(2)} ({priceDeltaPct >= 0 ? "+" : ""}{priceDeltaPct.toFixed(2)}%)
                  </span>
                )}
              </>
            )}
            {loading && <span className="text-sm text-gray-500">Loading...</span>}
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded p-3 text-red-400 text-sm">{error}</div>
          )}

          <Chart
            bars={bars}
            signals={signals}
            paperRunnerStatuses={paperRunnerStatuses}
            viewKey={`${symbol}:${timeframe}:${startDate}:${barLimit}:${chartRequest?.researchProfile ?? "default"}`}
            height={480}
          />

          {/* Equity Curve (shown during backtest) */}
          {equityCurve.length > 0 && (
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h3 className="text-sm text-gray-400 mb-2">Equity Curve</h3>
              <div className="flex items-end gap-px h-24">
                {(() => {
                  const values = equityCurve.map((e) => e.equity);
                  const min = Math.min(...values);
                  const max = Math.max(...values);
                  const range = max - min || 1;
                  // Sample to max 200 bars for display
                  const step = Math.max(1, Math.floor(values.length / 200));
                  const sampled = values.filter((_, i) => i % step === 0);
                  return sampled.map((v, i) => {
                    const h = ((v - min) / range) * 100;
                    const initial = equityCurve[0].equity;
                    return (
                      <div
                        key={i}
                        className={`flex-1 min-w-[1px] rounded-t ${v >= initial ? "bg-green-500/60" : "bg-red-500/60"}`}
                        style={{ height: `${Math.max(2, h)}%` }}
                      />
                    );
                  });
                })()}
              </div>
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>{formatBeijingDate(equityCurve[0].time)}</span>
                <span>${equityCurve[equityCurve.length - 1].equity.toLocaleString()}</span>
                <span>{formatBeijingDate(equityCurve[equityCurve.length - 1].time)}</span>
              </div>
            </div>
          )}

          {/* Signals Table */}
          {signals.length > 0 && (
            <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="text-left px-4 py-2">Time</th>
                    <th className="text-left px-4 py-2">Signal</th>
                    <th className="text-right px-4 py-2">Price</th>
                    <th className="text-right px-4 py-2">Qty</th>
                    <th className="text-left px-4 py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.slice(-20).reverse().map((s, i) => (
                    <tr key={i} className="border-b border-gray-800/50">
                      <td className="px-4 py-2 font-mono text-gray-400">{formatBeijingDateTime(s.timestamp)}</td>
                      <td className="px-4 py-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${s.signal_type === "buy" ? "bg-green-900/50 text-green-400" : "bg-red-900/50 text-red-400"}`}>
                          {s.signal_type.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-white">${s.price.toFixed(2)}</td>
                      <td className="px-4 py-2 text-right font-mono">{s.quantity}</td>
                      <td className="px-4 py-2 text-gray-400">{s.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>

        {/* Right Sidebar */}
        <aside className="w-96 border-l border-gray-800 flex flex-col overflow-hidden">
          {/* Tab Switcher */}
          <div className="flex border-b border-gray-800">
            <button
              onClick={() => setSidebarTab("trade")}
              className={`flex-1 px-4 py-2 text-sm ${sidebarTab === "trade" ? "text-white border-b-2 border-blue-500" : "text-gray-500 hover:text-gray-300"}`}
            >Trade</button>
            <button
              onClick={() => setSidebarTab("backtest")}
              className={`flex-1 px-4 py-2 text-sm ${sidebarTab === "backtest" ? "text-white border-b-2 border-purple-500" : "text-gray-500 hover:text-gray-300"}`}
            >Backtest</button>
          </div>

          <div className="flex-1 overflow-auto p-4 space-y-4">
            {sidebarTab === "trade" ? (
              <>
                <StrategyPanel
                  symbol={symbol}
                  timeframe={timeframe}
                  startDate={startDate}
                  onSignals={setSignals}
                />
                <TradePanel
                  account={account}
                  positions={positions}
                  currentSymbol={symbol}
                  onOrderPlaced={fetchAccountData}
                />
              </>
            ) : (
              <BacktestPanel
                onSignals={(sigs) => { setSignals(sigs); }}
                onEquityCurve={setEquityCurve}
                onActivateResearchContext={activateResearchContext}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
