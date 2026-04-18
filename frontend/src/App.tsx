import { useState, useEffect, useCallback } from "react";
import Chart from "./components/Chart";
import TradePanel from "./components/TradePanel";
import StrategyPanel from "./components/StrategyPanel";
import BacktestPanel from "./components/BacktestPanel";
import useMarketData from "./hooks/useMarketData";
import useWebSocket from "./hooks/useWebSocket";
import { getBars, getAccount, getPositions } from "./services/api";
import type { Bar, Signal, Account, Position, Timeframe } from "./types";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "1D"];

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

type SidebarTab = "trade" | "backtest";

export default function App() {
  const [symbol, setSymbol] = useState("QQQ");
  const [symbolInput, setSymbolInput] = useState("QQQ");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [bars, setBars] = useState<Bar[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notifications, setNotifications] = useState<string[]>([]);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("backtest");
  const [equityCurve, setEquityCurve] = useState<{ time: string; equity: number }[]>([]);

  const startDate = getDefaultStart(timeframe);

  const { lastBar, connected: marketConnected } = useMarketData(symbol);

  const onTradeMessage = useCallback(
    (raw: unknown) => {
      const msg = raw as { type: string; symbol: string; side: string; qty: number; status: string };
      if (msg.type === "trade") {
        const note = `${msg.side.toUpperCase()} ${msg.qty} ${msg.symbol} - ${msg.status}`;
        setNotifications((prev) => [note, ...prev].slice(0, 10));
        fetchAccountData();
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
      if (lastExisting.time === lastBar.time) {
        return [...prev.slice(0, -1), lastBar];
      }
      return [...prev, lastBar];
    });
  }, [lastBar]);

  const fetchBars = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getBars(symbol, timeframe, startDate, 500);
      setBars(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load bars";
      setError(msg);
      setBars([]);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, startDate]);

  const fetchAccountData = useCallback(async () => {
    try {
      const [acc, pos] = await Promise.all([getAccount(), getPositions()]);
      setAccount(acc);
      setPositions(pos);
    } catch {
      // secondary
    }
  }, []);

  useEffect(() => {
    fetchBars();
  }, [fetchBars]);

  useEffect(() => {
    fetchAccountData();
  }, [fetchAccountData]);

  const handleSymbolSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const s = symbolInput.trim().toUpperCase();
    if (s && s !== symbol) {
      setSymbol(s);
      setSignals([]);
      setEquityCurve([]);
    }
  };

  const dismissNotification = (index: number) => {
    setNotifications((prev) => prev.filter((_, i) => i !== index));
  };

  const activateResearchContext = useCallback(() => {
    const switchingChart = symbol !== "QQQ" || timeframe !== "5m";
    setSymbol("QQQ");
    setSymbolInput("QQQ");
    setTimeframe("5m");
    setSignals([]);
    setEquityCurve([]);
    if (switchingChart) {
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
            <div className={`w-2 h-2 rounded-full ${marketConnected ? "bg-green-400" : "bg-red-400"}`} />
            <span className="text-xs text-gray-500">{marketConnected ? "Live" : "Offline"}</span>
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
                onClick={() => { setTimeframe(tf); setSignals([]); setEquityCurve([]); }}
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
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white">{symbol}</h2>
            {bars.length > 0 && (
              <span className={`text-lg font-mono ${bars[bars.length - 1].close >= bars[bars.length - 1].open ? "text-green-400" : "text-red-400"}`}>
                ${bars[bars.length - 1].close.toFixed(2)}
              </span>
            )}
            {loading && <span className="text-sm text-gray-500">Loading...</span>}
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded p-3 text-red-400 text-sm">{error}</div>
          )}

          <Chart bars={bars} signals={signals} height={480} />

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
                <span>{equityCurve[0].time.slice(0, 10)}</span>
                <span>${equityCurve[equityCurve.length - 1].equity.toLocaleString()}</span>
                <span>{equityCurve[equityCurve.length - 1].time.slice(0, 10)}</span>
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
                      <td className="px-4 py-2 font-mono text-gray-400">{new Date(s.timestamp).toLocaleDateString()}</td>
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
