import axios from "axios";
import type { Bar, Signal, Account, Position, Order, StrategyInfo, BacktestResult } from "../types";

const api = axios.create({ baseURL: "/api" });

export async function getBars(
  symbol: string,
  timeframe: string,
  start: string,
  limit = 200
): Promise<Bar[]> {
  const { data } = await api.get(`/market/bars/${symbol}`, {
    params: { timeframe, start, limit },
  });
  return data.bars;
}

export async function getQuote(symbol: string) {
  const { data } = await api.get(`/market/quote/${symbol}`);
  return data;
}

export async function getAccount(): Promise<Account> {
  const { data } = await api.get("/trading/account");
  return data;
}

export async function getPositions(): Promise<Position[]> {
  const { data } = await api.get("/trading/positions");
  return data;
}

export async function getOrders(status = "open"): Promise<Order[]> {
  const { data } = await api.get("/trading/orders", { params: { status } });
  return data;
}

export async function submitOrder(symbol: string, qty: number, side: string) {
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
  params?: Record<string, unknown>
): Promise<Signal[]> {
  const { data } = await api.post("/strategy/signals", {
    name,
    symbol,
    timeframe,
    start,
    params,
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
}): Promise<BacktestResult> {
  const { data } = await api.post("/backtest/run", req);
  return data;
}
