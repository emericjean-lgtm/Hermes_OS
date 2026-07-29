"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ExecutionClient } from "@/lib/execution-client";
import { useEvents } from "@/hooks/use-events";
import type {
  ExecutionOverviewResponse,
  ExecutionTask,
  ExecutionTimelineEvent,
  ExecutionPerformanceData,
  ExecutionGraphData,
  TimelineEvent,
} from "@/types/mission-control";

// ─── Cache keys ──────────────────────────────────────────────

export const executionKeys = {
  all: ["execution"] as const,
  overview: () => [...executionKeys.all, "overview"] as const,
  tasks: () => [...executionKeys.all, "tasks"] as const,
  timeline: () => [...executionKeys.all, "timeline"] as const,
  performance: () => [...executionKeys.all, "performance"] as const,
  graph: () => [...executionKeys.all, "graph"] as const,
  statistics: () => [...executionKeys.all, "statistics"] as const,
};

// ─── Hooks ───────────────────────────────────────────────────

export function useExecutionOverview() {
  return useQuery({
    queryKey: executionKeys.overview(),
    queryFn: ExecutionClient.overview,
    refetchInterval: 5_000,
  });
}

export function useExecutionTasks() {
  return useQuery({
    queryKey: executionKeys.tasks(),
    queryFn: ExecutionClient.tasks,
    refetchInterval: 3_000,
  });
}

export function useExecutionPerformance() {
  return useQuery({
    queryKey: executionKeys.performance(),
    queryFn: ExecutionClient.performance,
    staleTime: 10_000,
    refetchInterval: 10_000,
  });
}

export function useExecutionGraph() {
  return useQuery({
    queryKey: executionKeys.graph(),
    queryFn: ExecutionClient.graph,
    refetchInterval: 5_000,
  });
}

export function useExecutionStatistics() {
  return useQuery({
    queryKey: executionKeys.statistics(),
    queryFn: ExecutionClient.statistics,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });
}

// ─── Timeline with WebSocket + REST hybrid ───────────────────

export function useExecutionTimeline(limit = 50) {
  const [events, setEvents] = useState<ExecutionTimelineEvent[]>([]);
  const loaded = useRef(false);

  // Initial load from REST
  const { data: initialEvents } = useQuery({
    queryKey: executionKeys.timeline(),
    queryFn: () => ExecutionClient.timeline(limit),
    staleTime: 30_000,
    enabled: !loaded.current,
  });

  useEffect(() => {
    if (initialEvents && !loaded.current) {
      setEvents(initialEvents);
      loaded.current = true;
    }
  }, [initialEvents]);

  // Real-time updates from WebSocket
  const { events: wsEvents } = useEvents({
    onEvent: useCallback((event: TimelineEvent) => {
      setEvents((prev) => [
        {
          id: event.id,
          type: event.type,
          timestamp: event.timestamp,
          message: event.message,
          source: event.source,
          severity: event.severity,
        },
        ...prev,
      ].slice(0, limit));
    }, [limit]),
  });

  const clearTimeline = useCallback(() => setEvents([]), []);

  return { events, clearTimeline };
}

// ─── Execution Controls (mutations) ──────────────────────────

export function useExecutionControl() {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: executionKeys.overview() });
    queryClient.invalidateQueries({ queryKey: executionKeys.tasks() });
    queryClient.invalidateQueries({ queryKey: executionKeys.graph() });
    queryClient.invalidateQueries({ queryKey: executionKeys.performance() });
  };

  const pause = useMutation({
    mutationFn: ExecutionClient.pause,
    onSuccess: invalidate,
  });

  const resume = useMutation({
    mutationFn: ExecutionClient.resume,
    onSuccess: invalidate,
  });

  const cancel = useMutation({
    mutationFn: ExecutionClient.cancel,
    onSuccess: invalidate,
  });

  const recover = useMutation({
    mutationFn: ExecutionClient.recover,
    onSuccess: invalidate,
  });

  const retryFailed = useMutation({
    mutationFn: ExecutionClient.retryFailed,
    onSuccess: invalidate,
  });

  const tick = useMutation({
    mutationFn: ExecutionClient.tick,
    onSuccess: invalidate,
  });

  return { pause, resume, cancel, recover, retryFailed, tick };
}
