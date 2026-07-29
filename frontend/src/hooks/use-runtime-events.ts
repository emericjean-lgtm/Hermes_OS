"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ─── Types ─────────────────────────────────────────────────

export interface RuntimeEvent {
  id: string;
  runtime_id: string;
  event_type: string;
  severity: "debug" | "info" | "warning" | "error" | "critical";
  timestamp: string;
  source: string;
  payload: Record<string, unknown>;
  correlation_id: string | null;
}

export interface UseRuntimeEventsOptions {
  runtimeId?: string | null;
  severity?: string | null;
  maxEvents?: number;
  reconnectDelay?: number;
}

export interface UseRuntimeEventsReturn {
  events: RuntimeEvent[];
  isConnected: boolean;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  clear: () => void;
  setFilter: (runtimeId?: string | null, severity?: string | null) => void;
  recentByRuntime: (runtimeId: string) => RuntimeEvent[];
}

// ─── Hook ──────────────────────────────────────────────────

export function useRuntimeEvents(
  options: UseRuntimeEventsOptions = {},
): UseRuntimeEventsReturn {
  const {
    runtimeId = null,
    severity = null,
    maxEvents = 200,
    reconnectDelay = 3000,
  } = options;

  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runtimeIdRef = useRef(runtimeId);
  const severityRef = useRef(severity);

  // Keep refs in sync
  useEffect(() => {
    runtimeIdRef.current = runtimeId;
  }, [runtimeId]);

  useEffect(() => {
    severityRef.current = severity;
  }, [severity]);

  const clear = useCallback(() => {
    setEvents([]);
  }, []);

  const connect = useCallback(() => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Clear any pending reconnect
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    // Build WebSocket URL
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${window.location.host}`;
    const wsUrl = `${host}/api/v1/runtime/events/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);

        // Send filter
        const filter: Record<string, string> = {};
        if (runtimeIdRef.current) {
          filter.runtime_id = runtimeIdRef.current;
        }
        if (severityRef.current) {
          filter.severity = severityRef.current;
        }
        ws.send(JSON.stringify(filter));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.type === "connected") {
            return; // Ignore connection confirmation
          }
          const runtimeEvent = data as RuntimeEvent;
          setEvents((prev) => {
            const next = [runtimeEvent, ...prev];
            return next.slice(0, maxEvents);
          });
        } catch {
          // Ignore parse errors
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        // Auto-reconnect
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, reconnectDelay);
      };

      ws.onerror = () => {
        setError("WebSocket connection error");
        ws.close();
      };
    } catch (err) {
      setError(`Failed to connect: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [reconnectDelay, maxEvents]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const setFilter = useCallback(
    (newRuntimeId?: string | null, newSeverity?: string | null) => {
      runtimeIdRef.current = newRuntimeId ?? null;
      severityRef.current = newSeverity ?? null;

      // Send filter update if connected
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        const filter: Record<string, string> = {};
        if (runtimeIdRef.current) {
          filter.runtime_id = runtimeIdRef.current;
        }
        if (severityRef.current) {
          filter.severity = severityRef.current;
        }
        wsRef.current.send(JSON.stringify(filter));
      }
    },
    [],
  );

  const recentByRuntime = useCallback(
    (targetRuntimeId: string): RuntimeEvent[] => {
      return events.filter((e) => e.runtime_id === targetRuntimeId);
    },
    [events],
  );

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    events,
    isConnected,
    error,
    connect,
    disconnect,
    clear,
    setFilter,
    recentByRuntime,
  };
}
