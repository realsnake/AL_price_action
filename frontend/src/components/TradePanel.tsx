import { useState } from "react";
import { submitOrder } from "../services/api";
import type { Account, Position } from "../types";

interface TradePanelProps {
  account: Account | null;
  positions: Position[];
  currentSymbol: string;
  onOrderPlaced: () => void;
}

export default function TradePanel({
  account,
  positions,
  currentSymbol,
  onOrderPlaced,
}: TradePanelProps) {
  const [qty, setQty] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleOrder = async (side: "buy" | "sell") => {
    setLoading(true);
    setError("");
    try {
      await submitOrder(currentSymbol, qty, side);
      onOrderPlaced();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Order failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 space-y-4">
      {/* Account Summary */}
      {account && (
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-gray-500">Equity</span>
            <p className="text-white font-mono">${account.equity.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-gray-500">Cash</span>
            <p className="text-white font-mono">${account.cash.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-gray-500">P&L</span>
            <p className={`font-mono ${account.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
              {account.pnl >= 0 ? "+" : ""}${account.pnl.toFixed(2)} ({account.pnl_pct.toFixed(2)}%)
            </p>
          </div>
          <div>
            <span className="text-gray-500">Buying Power</span>
            <p className="text-white font-mono">${account.buying_power.toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Order Form */}
      <div className="border-t border-gray-800 pt-3">
        <label className="text-sm text-gray-400 block mb-1">
          Quantity for {currentSymbol}
        </label>
        <input
          type="number"
          min={1}
          value={qty}
          onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm font-mono"
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => handleOrder("buy")}
            disabled={loading}
            className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white py-2 rounded text-sm font-medium"
          >
            BUY
          </button>
          <button
            onClick={() => handleOrder("sell")}
            disabled={loading}
            className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white py-2 rounded text-sm font-medium"
          >
            SELL
          </button>
        </div>
        {error && <p className="text-red-400 text-xs mt-1">{error}</p>}
      </div>

      {/* Positions */}
      {positions.length > 0 && (
        <div className="border-t border-gray-800 pt-3">
          <h3 className="text-sm text-gray-400 mb-2">Positions</h3>
          <div className="space-y-2">
            {positions.map((p) => (
              <div
                key={p.symbol}
                className="flex justify-between items-center text-sm bg-gray-800 rounded px-3 py-2"
              >
                <div>
                  <span className="text-white font-medium">{p.symbol}</span>
                  <span className="text-gray-500 ml-2">{p.qty} shares</span>
                </div>
                <span
                  className={`font-mono ${p.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
