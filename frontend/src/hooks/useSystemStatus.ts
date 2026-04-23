import { useEffect, useEffectEvent, useState } from "react";
import type { HealthStatus, WorkspaceMode } from "../types";

interface UseSystemStatusOptions {
  browserOnline: boolean;
  marketConnected: boolean;
}

interface SystemStatus {
  mode: WorkspaceMode;
  browserOnline: boolean;
  backendReachable: boolean;
  marketConnected: boolean;
  alpacaConfigured: boolean;
  liveStreamEnabled: boolean;
  healthChecked: boolean;
  lastSuccessfulSyncAt: string | null;
}

const HEALTH_POLL_MS = 15_000;
const STREAM_SYNC_GRACE_MS = 5_000;

export default function useSystemStatus({
  browserOnline,
  marketConnected,
}: UseSystemStatusOptions): SystemStatus {
  const [backendReachable, setBackendReachable] = useState(browserOnline);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthChecked, setHealthChecked] = useState(false);
  const [lastSuccessfulSyncAt, setLastSuccessfulSyncAt] = useState<
    string | null
  >(null);
  const [streamUnavailableSince, setStreamUnavailableSince] = useState<
    string | null
  >(null);

  const refreshHealth = useEffectEvent(async () => {
    if (!browserOnline) {
      setBackendReachable(false);
      setHealthChecked(true);
      return;
    }

    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Health check failed with ${response.status}`);
      }

      const data = (await response.json()) as {
        status: "ok" | "degraded";
        alpaca_configured: boolean;
        live_stream_enabled: boolean;
      };

      setHealth({
        status: data.status,
        alpacaConfigured: data.alpaca_configured,
        liveStreamEnabled: data.live_stream_enabled,
      });
      setBackendReachable(true);
      setHealthChecked(true);
      setLastSuccessfulSyncAt(new Date().toISOString());
    } catch {
      setBackendReachable(false);
      setHealthChecked(true);
    }
  });

  useEffect(() => {
    void refreshHealth();
  }, [browserOnline]);

  useEffect(() => {
    void refreshHealth();

    const intervalId = window.setInterval(() => {
      void refreshHealth();
    }, HEALTH_POLL_MS);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshHealth();
      }
    };

    const handleFocus = () => {
      void refreshHealth();
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (
      !browserOnline ||
      !backendReachable ||
      !health?.alpacaConfigured ||
      marketConnected
    ) {
      setStreamUnavailableSince(null);
      return;
    }

    if (health.liveStreamEnabled) {
      setStreamUnavailableSince((prev) => prev ?? new Date().toISOString());
      return;
    }

    setStreamUnavailableSince(null);
  }, [
    browserOnline,
    backendReachable,
    health?.alpacaConfigured,
    health?.liveStreamEnabled,
    marketConnected,
  ]);

  const streamUnavailableMs = streamUnavailableSince
    ? Date.now() - new Date(streamUnavailableSince).getTime()
    : 0;

  let mode: WorkspaceMode;
  if (!browserOnline) {
    mode = "offline";
  } else if (!backendReachable && healthChecked) {
    mode = "api_down";
  } else if (!healthChecked) {
    mode = "syncing";
  } else if (!health?.alpacaConfigured) {
    mode = "degraded";
  } else if (marketConnected && health.liveStreamEnabled) {
    mode = "live";
  } else if (
    health.liveStreamEnabled &&
    streamUnavailableSince &&
    streamUnavailableMs >= STREAM_SYNC_GRACE_MS
  ) {
    mode = "standby";
  } else {
    mode = "syncing";
  }

  return {
    mode,
    browserOnline,
    backendReachable,
    marketConnected,
    alpacaConfigured: health?.alpacaConfigured ?? false,
    liveStreamEnabled: health?.liveStreamEnabled ?? false,
    healthChecked,
    lastSuccessfulSyncAt,
  };
}
