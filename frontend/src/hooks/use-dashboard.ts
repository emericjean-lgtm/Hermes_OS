"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MissionControlClient } from "@/lib/mission-control";

// ─── Clés de cache ───────────────────────────────────────────

export const queryKeys = {
  health: ["mc", "health"] as const,
  status: ["mc", "status"] as const,
  statistics: ["mc", "statistics"] as const,
  diagnostics: ["mc", "diagnostics"] as const,
  runtimes: ["mc", "runtimes"] as const,
  runtimeHealth: (name?: string) => ["mc", "runtime-health", name] as const,
  runtimeMetrics: (name?: string) => ["mc", "runtime-metrics", name] as const,
  missions: ["mc", "missions"] as const,
  mission: (id: string) => ["mc", "mission", id] as const,
  execution: ["mc", "execution"] as const,
  memory: (scope?: string) => ["mc", "memory", scope] as const,
  memorySearch: (query: string) => ["mc", "memory-search", query] as const,
  skills: ["mc", "skills"] as const,
  events: (limit?: number) => ["mc", "events", limit] as const,
  eventStats: ["mc", "event-stats"] as const,
  hermes: ["mc", "hermes"] as const,
};

// ─── Durées de rafraîchissement ──────────────────────────────

const REFRESH_FAST = 5_000;   // 5s — santé, statut
const REFRESH_NORMAL = 15_000; // 15s — runtimes, missions
const REFRESH_SLOW = 30_000;   // 30s — skills, hermes
const REFRESH_STALE = 60_000;  // 1min — memory, events

// ─── Hooks ───────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: MissionControlClient.health,
    refetchInterval: REFRESH_FAST,
  });
}

export function useStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: MissionControlClient.status,
    refetchInterval: REFRESH_FAST,
  });
}

export function useStatistics() {
  return useQuery({
    queryKey: queryKeys.statistics,
    queryFn: MissionControlClient.statistics,
    refetchInterval: REFRESH_NORMAL,
  });
}

export function useDiagnostics() {
  return useQuery({
    queryKey: queryKeys.diagnostics,
    queryFn: MissionControlClient.diagnostics,
    staleTime: REFRESH_STALE,
  });
}

export function useRuntimes() {
  return useQuery({
    queryKey: queryKeys.runtimes,
    queryFn: MissionControlClient.runtimes,
    refetchInterval: REFRESH_NORMAL,
  });
}

export function useMissions() {
  return useQuery({
    queryKey: queryKeys.missions,
    queryFn: MissionControlClient.listMissions,
    refetchInterval: REFRESH_NORMAL,
  });
}

export function useExecutionStatus() {
  return useQuery({
    queryKey: queryKeys.execution,
    queryFn: MissionControlClient.executionStatus,
    refetchInterval: REFRESH_FAST,
  });
}

export function useMemory(scope?: string) {
  return useQuery({
    queryKey: queryKeys.memory(scope),
    queryFn: () => MissionControlClient.listMemory(scope),
    staleTime: REFRESH_STALE,
  });
}

export function useSkills() {
  return useQuery({
    queryKey: queryKeys.skills,
    queryFn: MissionControlClient.listSkills,
    staleTime: REFRESH_SLOW,
  });
}

export function useEvents(limit?: number) {
  return useQuery({
    queryKey: queryKeys.events(limit),
    queryFn: () => MissionControlClient.listEvents(limit),
    refetchInterval: REFRESH_NORMAL,
  });
}

export function useEventStatistics() {
  return useQuery({
    queryKey: queryKeys.eventStats,
    queryFn: MissionControlClient.eventStatistics,
    staleTime: REFRESH_NORMAL,
  });
}

export function useHermesStatus() {
  return useQuery({
    queryKey: queryKeys.hermes,
    queryFn: MissionControlClient.hermesStatus,
    staleTime: REFRESH_SLOW,
  });
}

// ─── Mutations ───────────────────────────────────────────────

export function useCreateMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: MissionControlClient.createMission,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.missions });
    },
  });
}

export function useStartMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionControlClient.startMission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.missions });
    },
  });
}

export function useCancelMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionControlClient.cancelMission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.missions });
    },
  });
}
