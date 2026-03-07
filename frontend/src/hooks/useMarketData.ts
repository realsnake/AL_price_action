import { useState, useCallback } from "react";
import useWebSocket from "./useWebSocket";
import type { Bar } from "../types";

interface MarketMessage {
  type: string;
  symbol: string;
  data: Bar;
}

export default function useMarketData(symbol: string) {
  const [lastBar, setLastBar] = useState<Bar | null>(null);

  const onMessage = useCallback(
    (raw: unknown) => {
      const msg = raw as MarketMessage;
      if (msg.type === "bar" && msg.symbol === symbol) {
        setLastBar(msg.data);
      }
    },
    [symbol]
  );

  const { connected } = useWebSocket({
    url: `/ws/market/${symbol}`,
    onMessage,
  });

  return { lastBar, connected };
}
