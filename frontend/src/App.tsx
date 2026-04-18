import { useCallback, useEffect, useRef, useState } from "react";
import Chart from "./components/Chart";
import TradePanel from "./components/TradePanel";
import StrategyPanel from "./components/StrategyPanel";
import BacktestPanel from "./components/BacktestPanel";
import MetricCard from "./components/MetricCard";
import StatusPill from "./components/StatusPill";
import useMarketData from "./hooks/useMarketData";
import useWebSocket from "./hooks/useWebSocket";
import { useOffline } from "./hooks/useOffline";
import useSystemStatus from "./hooks/useSystemStatus";
import OfflineBanner from "./components/OfflineBanner";
import {
  loadAccountSnapshot,
  loadBarsSnapshot,
  loadPositionsSnapshot,
} from "./services/api";
import type {
  Account,
  Bar,
  DataSource,
  Position,
  Signal,
  Timeframe,
  WorkspaceMode,
} from "./types";

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

interface SnapshotMeta {
  source: DataSource;
  cachedAt: string | null;
}

function formatCurrency(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return "no snapshot yet";

  const diffMs = Date.now() - new Date(timestamp).getTime();
  if (!Number.isFinite(diffMs)) return "unknown";

  const diffMinutes = Math.round(diffMs / 60_000);
  if (diffMinutes <= 0) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function modeTone(mode: WorkspaceMode): "green" | "amber" | "red" | "blue" | "slate" {
  switch (mode) {
    case "live":
      return "green";
    case "degraded":
      return "blue";
    case "standby":
      return "slate";
    case "offline":
      return "amber";
    case "api_down":
      return "red";
    default:
      return "slate";
  }
}

function modeLabel(mode: WorkspaceMode): string {
  switch (mode) {
    case "live":
      return "Live";
    case "degraded":
      return "Degraded";
    case "standby":
      return "Standby";
    case "api_down":
      return "API Down";
    case "offline":
      return "Offline";
    default:
      return "Syncing";
  }
}

function sourceLabel(meta: SnapshotMeta | null, fallback = "No snapshot"): string {
  if (!meta) return fallback;
  return meta.source === "network"
    ? `Network sync · ${formatRelativeTime(meta.cachedAt)}`
    : `Cached snapshot · ${formatRelativeTime(meta.cachedAt)}`;
}

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
  const [equityCurve, setEquityCurve] = useState<
    { time: string; equity: number }[]
  >([]);
  const [barsMeta, setBarsMeta] = useState<SnapshotMeta | null>(null);
  const [accountMeta, setAccountMeta] = useState<SnapshotMeta | null>(null);
  const [positionsMeta, setPositionsMeta] = useState<SnapshotMeta | null>(null);
  const previousBackendReachable = useRef<boolean | null>(null);

  const startDate = getDefaultStart(timeframe);

  const { lastBar, connected: marketConnected } = useMarketData(symbol);
  const isOffline = useOffline();
  const browserOnline = !isOffline;
  const systemStatus = useSystemStatus({ browserOnline, marketConnected });

  const onTradeMessage = useCallback(
    (raw: unknown) => {
      const msg = raw as {
        type: string;
        symbol: string;
        side: string;
        qty: number;
        status: string;
      };
      if (msg.type === "trade") {
        const note = `${msg.side.toUpperCase()} ${msg.qty} ${msg.symbol} - ${msg.status}`;
        setNotifications((prev) => [note, ...prev].slice(0, 10));
        fetchAccountData();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
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
      const snapshot = await loadBarsSnapshot(symbol, timeframe, startDate, 500);
      setBars(snapshot.data);
      setBarsMeta({
        source: snapshot.source,
        cachedAt: snapshot.cachedAt,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load bars";
      setError(msg);
      setBars([]);
      setBarsMeta(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, startDate]);

  const fetchAccountData = useCallback(async () => {
    const [accountResult, positionsResult] = await Promise.allSettled([
      loadAccountSnapshot(),
      loadPositionsSnapshot(),
    ]);

    if (accountResult.status === "fulfilled") {
      setAccount(accountResult.value.data);
      setAccountMeta({
        source: accountResult.value.source,
        cachedAt: accountResult.value.cachedAt,
      });
    } else {
      setAccount(null);
      setAccountMeta(null);
    }

    if (positionsResult.status === "fulfilled") {
      setPositions(positionsResult.value.data);
      setPositionsMeta({
        source: positionsResult.value.source,
        cachedAt: positionsResult.value.cachedAt,
      });
    } else {
      setPositions([]);
      setPositionsMeta(null);
    }
  }, []);

  useEffect(() => {
    fetchBars();
  }, [fetchBars]);

  useEffect(() => {
    fetchAccountData();
  }, [fetchAccountData]);

  useEffect(() => {
    const wasReachable = previousBackendReachable.current;
    if (wasReachable === false && systemStatus.backendReachable) {
      void fetchBars();
      void fetchAccountData();
    }
    previousBackendReachable.current = systemStatus.backendReachable;
  }, [systemStatus.backendReachable, fetchBars, fetchAccountData]);

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
    setSymbol("QQQ");
    setSymbolInput("QQQ");
    setTimeframe("5m");
    setSignals([]);
    setEquityCurve([]);
  }, []);

  const latestBar = bars[bars.length - 1] ?? null;
  const previousBar = bars.length > 1 ? bars[bars.length - 2] : null;
  const barDelta =
    latestBar && previousBar ? latestBar.close - previousBar.close : 0;
  const barDeltaPct =
    previousBar && previousBar.close !== 0
      ? (barDelta / previousBar.close) * 100
      : 0;

  const tradingDisabledReason = !browserOnline
    ? "Browser offline. Trading stays paused until the network returns."
    : !systemStatus.backendReachable
      ? "Backend unavailable. Start the API before sending paper orders."
      : !systemStatus.alpacaConfigured
        ? "Alpaca paper credentials are not configured. Trading is disabled in degraded mode."
        : null;

  const analysisDisabledReason = !browserOnline
    ? "Reconnect to run strategy scans and backtests."
    : !systemStatus.backendReachable
      ? "Backend unavailable. Analysis actions need the local API."
      : null;

  const bannerTitle =
    systemStatus.mode === "offline"
      ? "Browser offline. Workspace switched to cached mode."
      : systemStatus.mode === "api_down"
        ? "Backend unreachable. Live API features are paused."
        : systemStatus.mode === "degraded"
          ? "Running in degraded mode. Cache-backed flows stay available."
          : systemStatus.mode === "standby"
            ? "Market stream in standby. Research tools remain ready."
          : "Market stream is reconnecting.";

  const bannerDetail =
    systemStatus.mode === "offline"
      ? "Historical bars and any saved snapshots can still render, but analysis and trading actions are paused until connectivity returns."
      : systemStatus.mode === "api_down"
        ? "The app shell is loaded, but requests to the local FastAPI service are not completing. Cached data may still be visible."
        : systemStatus.mode === "degraded"
          ? "Alpaca account and quote endpoints are unavailable, but cache-aware historical flows and backtests can still run."
          : systemStatus.mode === "standby"
            ? "The backend health check is green, but the live market bar socket is not attached yet. The workspace will keep retrying in the background."
          : "The API is alive and the workspace is syncing. Market bars will resume once the stream handshake is back.";

  const workspaceDetail =
    systemStatus.mode === "live"
      ? "Streaming bars, paper account ready, and cache updates happening in the background."
      : systemStatus.mode === "degraded"
        ? "Historical research stays online while account and quote features remain intentionally disabled."
        : systemStatus.mode === "standby"
          ? "The workstation is healthy and interactive, but live bar streaming is paused while the market socket retries in the background."
        : systemStatus.mode === "api_down"
          ? "UI shell is up, but the backend needs attention before live features come back."
          : systemStatus.mode === "offline"
            ? "The browser is offline, so the workstation is serving only what it has already cached."
            : "Local API is up and the workspace is synchronizing live market context.";

  const sidebarSummary =
    sidebarTab === "trade"
      ? signals.length > 0
        ? `${signals.length} strategy markers staged on the chart`
        : "Run a strategy to stage fresh entry and exit markers."
      : equityCurve.length > 0
        ? `${equityCurve.length} equity points ready for review`
        : "Backtest metrics and equity curves will land here.";

  return (
    <div className="min-h-screen bg-[#050b14] text-slate-100">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.14),_transparent_36%),radial-gradient(circle_at_top_right,_rgba(139,92,246,0.12),_transparent_28%),linear-gradient(180deg,#050b14_0%,#07101d_50%,#050b14_100%)]" />
        <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgba(148,163,184,0.16)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.16)_1px,transparent_1px)] [background-size:28px_28px]" />
      </div>

      {notifications.length > 0 && (
        <div className="fixed right-4 top-24 z-50 w-80 space-y-2">
          {notifications.map((note, i) => (
            <div
              key={i}
              className="flex items-start justify-between rounded-2xl border border-white/10 bg-[#0c1627]/95 px-4 py-3 text-sm text-white shadow-[0_20px_60px_-28px_rgba(15,23,42,0.95)] backdrop-blur"
            >
              <span>{note}</span>
              <button
                onClick={() => dismissNotification(i)}
                className="ml-2 text-xs text-slate-500 hover:text-white"
              >
                x
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="relative">
        <header className="border-b border-white/10 bg-[#07111f]/80 backdrop-blur-xl">
          <div className="px-6 py-5">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] uppercase tracking-[0.34em] text-cyan-300/70">
                    AL Price Action
                  </span>
                  <StatusPill
                    label={`Mode · ${modeLabel(systemStatus.mode)}`}
                    tone={modeTone(systemStatus.mode)}
                  />
                </div>
                <div>
                  <h1 className="text-3xl font-semibold tracking-tight text-white">
                    Market Cockpit
                  </h1>
                  <p className="mt-2 max-w-3xl text-sm text-slate-400">
                    {workspaceDetail}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusPill
                    label={
                      systemStatus.backendReachable ? "API ready" : "API unavailable"
                    }
                    tone={systemStatus.backendReachable ? "green" : "red"}
                  />
                  <StatusPill
                    label={
                      systemStatus.alpacaConfigured
                        ? "Paper account ready"
                        : "Alpaca degraded"
                    }
                    tone={systemStatus.alpacaConfigured ? "blue" : "amber"}
                  />
                  <StatusPill
                    label={
                      marketConnected
                        ? "Market stream linked"
                        : systemStatus.mode === "standby"
                          ? "Stream standby"
                          : "Stream syncing"
                    }
                    tone={marketConnected ? "green" : "slate"}
                  />
                  <StatusPill label={sourceLabel(barsMeta, "Waiting for bars")} />
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 shadow-[0_18px_60px_-30px_rgba(15,23,42,0.95)]">
                <div className="flex flex-col gap-3">
                  <form
                    onSubmit={handleSymbolSubmit}
                    className="flex items-center gap-2"
                  >
                    <input
                      type="text"
                      value={symbolInput}
                      onChange={(e) =>
                        setSymbolInput(e.target.value.toUpperCase())
                      }
                      placeholder="Symbol"
                      className="w-28 rounded-xl border border-white/10 bg-[#091423] px-3 py-2 text-sm font-mono text-white"
                    />
                    <button
                      type="submit"
                      className="rounded-xl bg-cyan-400 px-3 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-300"
                    >
                      Load
                    </button>
                  </form>
                  <div className="flex flex-wrap gap-1 rounded-2xl bg-[#091423] p-1">
                    {TIMEFRAMES.map((tf) => (
                      <button
                        key={tf}
                        onClick={() => {
                          setTimeframe(tf);
                          setSignals([]);
                          setEquityCurve([]);
                        }}
                        className={`rounded-xl px-3 py-1.5 text-sm transition ${tf === timeframe ? "bg-cyan-400 text-slate-950" : "text-slate-400 hover:bg-white/[0.06] hover:text-white"}`}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="px-6 py-5">
          {systemStatus.mode !== "live" && (
            <OfflineBanner
              mode={systemStatus.mode}
              title={bannerTitle}
              detail={bannerDetail}
              lastSyncedAt={formatRelativeTime(systemStatus.lastSuccessfulSyncAt)}
            />
          )}

          <section className="mt-5 grid gap-4 xl:grid-cols-4">
            <MetricCard
              eyebrow="Workspace"
              value={modeLabel(systemStatus.mode)}
              detail={workspaceDetail}
              footer={`Health sync ${formatRelativeTime(systemStatus.lastSuccessfulSyncAt)}`}
              accent="cyan"
              aside={
                <StatusPill
                  label={systemStatus.marketConnected ? "WS Live" : "WS Standby"}
                  tone={systemStatus.marketConnected ? "green" : "slate"}
                />
              }
            />
            <MetricCard
              eyebrow={`${symbol} · ${timeframe}`}
              value={
                latestBar ? formatCurrency(latestBar.close, 2) : "Waiting for bars"
              }
              detail={
                latestBar && previousBar
                  ? `${barDelta >= 0 ? "+" : ""}${barDelta.toFixed(2)} (${barDeltaPct.toFixed(2)}%) vs previous bar`
                  : `Loaded ${bars.length} bars`
              }
              footer={sourceLabel(barsMeta, "No cached market data yet")}
              accent={barDelta >= 0 ? "emerald" : "amber"}
            />
            <MetricCard
              eyebrow="Account"
              value={account ? formatCurrency(account.equity, 0) : "Unavailable"}
              detail={
                account
                  ? `Cash ${formatCurrency(account.cash)} · P&L ${account.pnl >= 0 ? "+" : ""}${account.pnl.toFixed(2)}`
                  : tradingDisabledReason ?? "Account snapshot will appear once available."
              }
              footer={sourceLabel(accountMeta, "No account snapshot cached")}
              accent="emerald"
            />
            <MetricCard
              eyebrow={sidebarTab === "trade" ? "Trade tab" : "Backtest tab"}
              value={
                sidebarTab === "trade"
                  ? signals.length > 0
                    ? `${signals.length} signals`
                    : "Ready"
                  : equityCurve.length > 0
                    ? `${equityCurve.length} curve points`
                    : "Ready"
              }
              detail={sidebarSummary}
              footer={sourceLabel(positionsMeta, "No positions snapshot cached")}
              accent="violet"
            />
          </section>

          <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
            <main className="min-w-0 space-y-4">
              <section className="overflow-hidden rounded-[28px] border border-white/10 bg-[#08111f]/90 shadow-[0_30px_90px_-36px_rgba(15,23,42,0.95)]">
                <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.32em] text-slate-500">
                      Chart deck
                    </p>
                    <div className="mt-2 flex items-center gap-3">
                      <h2 className="text-2xl font-semibold text-white">
                        {symbol}
                      </h2>
                      {latestBar && (
                        <span
                          className={`text-lg font-mono ${latestBar.close >= latestBar.open ? "text-emerald-300" : "text-rose-300"}`}
                        >
                          {formatCurrency(latestBar.close, 2)}
                        </span>
                      )}
                      {loading && (
                        <span className="text-sm text-slate-500">Loading…</span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <StatusPill label={`Bars · ${bars.length}`} />
                    <StatusPill
                      label={
                        barsMeta?.source === "cache"
                          ? "Using cache"
                          : "Fresh network"
                      }
                      tone={barsMeta?.source === "cache" ? "amber" : "blue"}
                    />
                    <StatusPill
                      label={
                        marketConnected
                          ? "Streaming active"
                          : systemStatus.mode === "standby"
                            ? "Waiting on live stream"
                            : "Polling and cache"
                      }
                      tone={marketConnected ? "green" : "slate"}
                    />
                  </div>
                </div>

                {error && (
                  <div className="border-b border-rose-400/20 bg-rose-400/10 px-5 py-3 text-sm text-rose-200">
                    {error}
                  </div>
                )}

                <div className="p-4">
                  <Chart bars={bars} signals={signals} height={520} />
                </div>
              </section>

              {equityCurve.length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-[#08111f]/90 p-4 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.95)]">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-medium text-slate-300">
                      Equity Curve
                    </h3>
                    <p className="text-xs text-slate-500">
                      {equityCurve[0].time.slice(0, 10)} to{" "}
                      {equityCurve[equityCurve.length - 1].time.slice(0, 10)}
                    </p>
                  </div>
                  <div className="mt-3 flex h-24 items-end gap-px">
                    {(() => {
                      const values = equityCurve.map((entry) => entry.equity);
                      const min = Math.min(...values);
                      const max = Math.max(...values);
                      const range = max - min || 1;
                      const step = Math.max(1, Math.floor(values.length / 200));
                      const sampled = values.filter((_, index) => index % step === 0);
                      return sampled.map((value, index) => {
                        const heightPct = ((value - min) / range) * 100;
                        const initial = equityCurve[0].equity;
                        return (
                          <div
                            key={index}
                            className={`min-w-[1px] flex-1 rounded-t ${value >= initial ? "bg-emerald-400/60" : "bg-rose-400/60"}`}
                            style={{ height: `${Math.max(2, heightPct)}%` }}
                          />
                        );
                      });
                    })()}
                  </div>
                  <div className="mt-2 flex justify-between text-xs text-slate-500">
                    <span>{formatCurrency(equityCurve[0].equity)}</span>
                    <span>
                      {formatCurrency(equityCurve[equityCurve.length - 1].equity)}
                    </span>
                  </div>
                </div>
              )}

              {signals.length > 0 && (
                <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#08111f]/90 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.95)]">
                  <div className="border-b border-white/10 px-4 py-3">
                    <h3 className="text-sm font-medium text-slate-300">
                      Signal Tape
                    </h3>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-slate-500">
                        <th className="px-4 py-2 text-left">Time</th>
                        <th className="px-4 py-2 text-left">Signal</th>
                        <th className="px-4 py-2 text-right">Price</th>
                        <th className="px-4 py-2 text-right">Qty</th>
                        <th className="px-4 py-2 text-left">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {signals
                        .slice(-20)
                        .reverse()
                        .map((entry, index) => (
                          <tr
                            key={index}
                            className="border-b border-white/5 text-slate-300"
                          >
                            <td className="px-4 py-2 font-mono text-slate-500">
                              {new Date(entry.timestamp).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-2">
                              <span
                                className={`rounded-full px-2 py-0.5 text-xs font-medium ${entry.signal_type === "buy" ? "bg-emerald-400/10 text-emerald-300" : "bg-rose-400/10 text-rose-300"}`}
                              >
                                {entry.signal_type.toUpperCase()}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-right font-mono text-white">
                              {formatCurrency(entry.price, 2)}
                            </td>
                            <td className="px-4 py-2 text-right font-mono">
                              {entry.quantity}
                            </td>
                            <td className="px-4 py-2 text-slate-400">
                              {entry.reason}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </main>

            <aside className="space-y-4">
              <div className="overflow-hidden rounded-[28px] border border-white/10 bg-[#08111f]/90 shadow-[0_30px_90px_-36px_rgba(15,23,42,0.95)]">
                <div className="flex gap-1 border-b border-white/10 bg-white/[0.03] p-2">
                  <button
                    onClick={() => setSidebarTab("trade")}
                    className={`flex-1 rounded-2xl px-4 py-2 text-sm transition ${sidebarTab === "trade" ? "bg-cyan-400 text-slate-950" : "text-slate-400 hover:bg-white/[0.06] hover:text-white"}`}
                  >
                    Trade
                  </button>
                  <button
                    onClick={() => setSidebarTab("backtest")}
                    className={`flex-1 rounded-2xl px-4 py-2 text-sm transition ${sidebarTab === "backtest" ? "bg-violet-400 text-slate-950" : "text-slate-400 hover:bg-white/[0.06] hover:text-white"}`}
                  >
                    Backtest
                  </button>
                </div>

                <div className="space-y-4 p-4">
                  {sidebarTab === "trade" ? (
                    <>
                      <StrategyPanel
                        symbol={symbol}
                        timeframe={timeframe}
                        startDate={startDate}
                        onSignals={setSignals}
                        disabledReason={analysisDisabledReason}
                      />
                      <TradePanel
                        account={account}
                        positions={positions}
                        currentSymbol={symbol}
                        onOrderPlaced={fetchAccountData}
                        disabledReason={tradingDisabledReason}
                        statusLine={sourceLabel(accountMeta, "No account sync yet")}
                      />
                    </>
                  ) : (
                    <BacktestPanel
                      onSignals={(sigs) => {
                        setSignals(sigs);
                      }}
                      onEquityCurve={setEquityCurve}
                      onActivateResearchContext={activateResearchContext}
                      disabledReason={analysisDisabledReason}
                    />
                  )}
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
