export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Signal {
  symbol: string;
  signal_type: "buy" | "sell" | "hold";
  price: number;
  quantity: number;
  reason: string;
  timestamp: string;
}

export interface Position {
  symbol: string;
  qty: number;
  avg_entry: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface Account {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: string;
  qty: string;
  filled_qty: string;
  status: string;
  created_at: string;
}

export interface StrategyInfo {
  name: string;
  description: string;
  params: Record<string, unknown>;
  default_params: Record<string, unknown>;
}

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "1D";

export type ResearchProfile = "qqq_5m_phase1";
export type Phase1StrategyName =
  | "brooks_breakout_pullback"
  | "brooks_small_pb_trend";

export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  side: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  target_price: number | null;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  reason: string;
  exit_reason: string;
  stop_reason: string;
  target_reason: string | null;
}

export interface BacktestResult {
  strategy: string;
  symbol: string;
  timeframe: string;
  period: string;
  initial_capital: number;
  final_capital: number;
  total_return: number;
  total_return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  trades: BacktestTrade[];
  equity_curve: { time: string; equity: number }[];
}

export interface PaperStrategyPosition {
  quantity: number;
  entry_price: number;
  stop_price: number;
  target_price: number | null;
  entry_time: string;
  reason: string;
  stop_reason: string;
  target_reason: string | null;
}

export interface PaperStrategyPendingOrder {
  alpaca_order_id: string;
  side: string;
  quantity: number;
  status: string;
  reason: string;
  submitted_at: string;
  signal_time: string;
}

export interface PaperStrategyEvent {
  timestamp: string;
  type: string;
  message: string;
}

export interface TradeHistoryEntry {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  strategy: string | null;
  signal_reason: string | null;
  status: string;
  alpaca_order_id: string | null;
  created_at: string | null;
}

export interface PaperStrategyReadiness {
  ready: boolean;
  paper_trading: boolean;
  alpaca_configured: boolean;
  account_status: "ok" | "error" | "unavailable";
  account_error: string | null;
  market_stream_running: boolean;
  trade_updates_running: boolean;
  runner_running: boolean;
  market_session: "open" | "closed";
  current_session_open: string | null;
  current_session_close: string | null;
  next_session_open: string | null;
  warnings: string[];
}

export interface PaperStrategyStatus {
  running: boolean;
  strategy: Phase1StrategyName;
  symbol: string;
  timeframe: Timeframe;
  research_profile: ResearchProfile;
  fixed_quantity: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  history_days: number;
  params: Record<string, unknown> | null;
  bar_count: number;
  started_at: string | null;
  last_completed_bar_time: string | null;
  last_live_bar_at: string | null;
  last_trade_update_at: string | null;
  orders_submitted: number;
  position: PaperStrategyPosition | null;
  pending_order: PaperStrategyPendingOrder | null;
  last_error: string | null;
  warnings: string[];
  recent_events: PaperStrategyEvent[];
}

export type DataSource = "network" | "cache";

export type WorkspaceMode =
  | "live"
  | "syncing"
  | "standby"
  | "degraded"
  | "api_down"
  | "offline";

export interface HealthStatus {
  status: "ok" | "degraded";
  alpacaConfigured: boolean;
  liveStreamEnabled: boolean;
}

export interface DataSnapshot<T> {
  data: T;
  source: DataSource;
  cachedAt: string | null;
}
