"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { SystemEvent, EventSeverity } from "@/types/hermes";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/events";

interface UseWebSocketOptions {
  sources?: string[];
  enabled?: boolean;
  onEvent?: (event: SystemEvent) => void;
  maxEvents?: number;
}

interface UseWebSocketReturn {
  events: SystemEvent[];
  connected: boolean;
  error: string | null;
  clearEvents: () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { sources, enabled = true, onEvent, maxEvents = 200 } = options;
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (!enabled) return;
    try {
      const url = sources?.length
        ? `${WS_URL}?sources=${sources.join(",")}`
        : WS_URL;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setError(null);
      };

      ws.onmessage = (msg) => {
        try {
          const event: SystemEvent = JSON.parse(msg.data);
          setEvents((prev) => {
            const next = [event, ...prev];
            return next.length > maxEvents ? next.slice(0, maxEvents) : next;
          });
          onEvent?.(event);
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection error");
      };

      ws.onclose = () => {
        setConnected(false);
        if (enabled) {
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        }
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    }
  }, [enabled, sources, maxEvents, onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, error, clearEvents };
}

export function severityColor(severity: EventSeverity): string {
  switch (severity) {
    case "CRITICAL": return "text-red-500";
    case "ERROR": return "text-red-400";
    case "WARNING": return "text-amber-400";
    case "INFO": return "text-blue-400";
    default: return "text-gray-400";
  }
}

export function severityBg(severity: EventSeverity): string {
  switch (severity) {
    case "CRITICAL": return "bg-red-500/20 border-red-500/40";
    case "ERROR": return "bg-red-400/15 border-red-400/30";
    case "WARNING": return "bg-amber-400/15 border-amber-400/30";
    case "INFO": return "bg-blue-400/15 border-blue-400/30";
    default: return "bg-gray-400/15 border-gray-400/30";
  }
}
