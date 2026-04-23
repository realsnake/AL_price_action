import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

interface UseWebSocketOptions {
  url: string;
  onMessage: (data: unknown) => void;
  reconnectInterval?: number;
  heartbeatInterval?: number;
}

export default function useWebSocket({
  url,
  onMessage,
  reconnectInterval = 3000,
  heartbeatInterval = 15000,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const handleMessage = useEffectEvent((data: unknown) => {
    onMessage(data);
  });

  useEffect(() => {
    let shouldReconnect = true;

    const connect = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}${url}`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnected(true);
        if (heartbeatTimer.current) {
          clearInterval(heartbeatTimer.current);
        }
        heartbeatTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, heartbeatInterval);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (
            typeof data === "object" &&
            data !== null &&
            "type" in data &&
            data.type === "pong"
          ) {
            return;
          }
          handleMessage(data);
        } catch {
          // Ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (heartbeatTimer.current) {
          clearInterval(heartbeatTimer.current);
          heartbeatTimer.current = null;
        }
        if (shouldReconnect) {
          reconnectTimer.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    };

    connect();
    return () => {
      shouldReconnect = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (heartbeatTimer.current) {
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [url, reconnectInterval, heartbeatInterval]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { connected, send };
}
