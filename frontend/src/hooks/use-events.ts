"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TimelineEvent } from "@/types/mission-control";

type ConnectionState = "connecting" | "open" | "closed";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ??
  (process.env.NEXT_PUBLIC_MC_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000").replace(/^http/, "ws");

const RECONNECT_BASE = 500;
const RECONNECT_MAX = 10_000;
const MAX_EVENTS = 200;

interface UseEventsOptions {
  onEvent?: (event: TimelineEvent) => void;
}

export function useEvents(options?: UseEventsOptions) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const socketRef = useRef<WebSocket | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const closedRef = useRef(false);

  const connect = useCallback(() => {
    if (closedRef.current) return;
    setConnectionState("connecting");

    const url = `${WS_URL.replace(/\/$/, "")}/api/hermes-os/ws/events`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      attemptRef.current = 0;
      setConnectionState("open");
    };

    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as TimelineEvent;
        setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
        options?.onEvent?.(event);
      } catch {
        // silently ignore malformed frames
      }
    };

    socket.onclose = () => {
      setConnectionState("closed");
      if (closedRef.current) return;
      attemptRef.current += 1;
      const delay = Math.min(
        RECONNECT_BASE * 2 ** (attemptRef.current - 1),
        RECONNECT_MAX,
      );
      retryTimerRef.current = setTimeout(connect, delay);
    };

    socket.onerror = () => {
      // onclose follows; reconnection is handled there
    };
  }, [options]);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      socketRef.current?.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connectionState, clearEvents };
}
