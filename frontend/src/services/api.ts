import axios from "axios";
import type {
  Account,
  BacktestResult,
  Bar,
  DataSnapshot,
  Order,
  Position,
  ResearchProfile,
  Signal,
  StrategyInfo,
} from "../types";
import {
  getAccountSnapshot as loadCachedAccountSnapshot,
  getBarsSnapshot as loadCachedBarsSnapshot,
  getPositionsSnapshot as loadCachedPositionsSnapshot,
  saveAccount as cacheAccount,
  saveBars as cacheBars,
  savePositions as cachePositions,
} from "./offlineDb";

const api = axios.create({ baseURL: "/api" });

function isOffline(): boolean {
  return !navigator.onLine;
}

function nowIso(): string {
  return new Date().toISOString();
}

export async function loadBarsSnapshot(
  symbol: string,
  timeframe: string,
  start: string,
  limit = 200,
): Promise<DataSnapshot<Bar[]>> {
  if (isOffline()) {
    const cached = await loadCachedBarsSnapshot(symbol, timeframe);
    if (cached?.data.length) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Offline - no cached data available");
  }

  try {
    const { data } = await api.get(`/market/bars/${symbol}`, {
      params: { timeframe, start, limit },
    });
    const cachedAt = nowIso();
    cacheBars(symbol, timeframe, data.bars).catch(() => {});
    return { data: data.bars, source: "network", cachedAt };
  } catch {
    const cached = await loadCachedBarsSnapshot(symbol, timeframe);
    if (cached?.data.length) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Failed to load bars - offline with no cache");
  }
}

export async function getBars(
  symbol: string,
  timeframe: string,
  start: string,
  limit = 200,
): Promise<Bar[]> {
  const snapshot = await loadBarsSnapshot(symbol, timeframe, start, limit);
  return snapshot.data;
}

export async function getQuote(symbol: string) {
  const { data } = await api.get(`/market/quote/${symbol}`);
  return data;
}

export async function loadAccountSnapshot(): Promise<DataSnapshot<Account>> {
  if (isOffline()) {
    const cached = await loadCachedAccountSnapshot();
    if (cached) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Offline - no cached account data");
  }

  try {
    const { data } = await api.get("/trading/account");
    const cachedAt = nowIso();
    cacheAccount(data).catch(() => {});
    return { data, source: "network", cachedAt };
  } catch {
    const cached = await loadCachedAccountSnapshot();
    if (cached) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Failed to load account - offline with no cache");
  }
}

export async function getAccount(): Promise<Account> {
  const snapshot = await loadAccountSnapshot();
  return snapshot.data;
}

export async function loadPositionsSnapshot(): Promise<DataSnapshot<Position[]>> {
  if (isOffline()) {
    const cached = await loadCachedPositionsSnapshot();
    if (cached) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Offline - no cached positions");
  }

  try {
    const { data } = await api.get("/trading/positions");
    const cachedAt = nowIso();
    cachePositions(data).catch(() => {});
    return { data, source: "network", cachedAt };
  } catch {
    const cached = await loadCachedPositionsSnapshot();
    if (cached) {
      return { data: cached.data, source: "cache", cachedAt: cached.cachedAt };
    }
    throw new Error("Failed to load positions - offline with no cache");
  }
}

export async function getPositions(): Promise<Position[]> {
  const snapshot = await loadPositionsSnapshot();
  return snapshot.data;
}

export async function getOrders(status = "open"): Promise<Order[]> {
  const { data } = await api.get("/trading/orders", { params: { status } });
  return data;
}

export async function submitOrder(symbol: string, qty: number, side: string) {
  if (isOffline()) {
    throw new Error("Cannot submit orders while offline");
  }
  const { data } = await api.post("/trading/order", { symbol, qty, side });
  return data;
}

export async function cancelOrder(orderId: string) {
  const { data } = await api.delete(`/trading/order/${orderId}`);
  return data;
}

export async function getStrategies(): Promise<StrategyInfo[]> {
  const { data } = await api.get("/strategy/list");
  return data;
}

export async function getSignals(
  name: string,
  symbol: string,
  timeframe: string,
  start: string,
  params?: Record<string, unknown>,
  options?: {
    researchProfile?: ResearchProfile;
    research_profile?: ResearchProfile;
  },
): Promise<Signal[]> {
  const researchProfile =
    options?.researchProfile ?? options?.research_profile;
  const { data } = await api.post("/strategy/signals", {
    name,
    symbol,
    timeframe,
    start,
    params,
    research_profile: researchProfile,
  });
  return data.signals;
}

export async function runBacktest(req: {
  strategy: string;
  symbol: string;
  timeframe: string;
  start: string;
  end?: string;
  params?: Record<string, unknown>;
  initial_capital: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  risk_per_trade_pct: number;
  researchProfile?: ResearchProfile;
  research_profile?: ResearchProfile;
}): Promise<BacktestResult> {
  const { researchProfile, research_profile, ...rest } = req;
  const { data } = await api.post("/backtest/run", {
    ...rest,
    research_profile: researchProfile ?? research_profile,
  });
  return data;
}
