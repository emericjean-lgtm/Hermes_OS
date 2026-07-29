"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MissionControlClient } from "@/lib/mission-control";
import { MissionPlanner } from "@/lib/mission-planner";
import type { CreateMissionRequest, ExecutionGraphData } from "@/types/mission-control";

// ─── Clés de cache ───────────────────────────────────────────

export const missionKeys = {
  all: ["missions"] as const,
  list: () => [...missionKeys.all, "list"] as const,
  detail: (id: string) => [...missionKeys.all, "detail", id] as const,
  plan: (id: string) => [...missionKeys.all, "plan", id] as const,
  graph: (id: string) => [...missionKeys.all, "graph", id] as const,
};

// ─── Hooks ───────────────────────────────────────────────────

export function useMissionList() {
  return useQuery({
    queryKey: missionKeys.list(),
    queryFn: MissionControlClient.listMissions,
    refetchInterval: 10_000,
  });
}

export function useMission(id: string | null) {
  return useQuery({
    queryKey: missionKeys.detail(id ?? ""),
    queryFn: () => MissionControlClient.getMission(id!),
    enabled: !!id,
  });
}

export function useMissionPlan(id: string | null) {
  return useQuery({
    queryKey: missionKeys.plan(id ?? ""),
    queryFn: () => MissionPlanner.getMissionGraph(id!),
    enabled: !!id,
  });
}

export function useMissionGraph(id: string | null) {
  return useQuery({
    queryKey: missionKeys.graph(id ?? ""),
    queryFn: () => MissionPlanner.getMissionGraph(id!),
    enabled: !!id,
    staleTime: 30_000,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasRunning = data.nodes.some((n) => n.status === "running" || n.status === "ready");
      return hasRunning ? 5_000 : false;
    },
  });
}

// ─── Mutations ───────────────────────────────────────────────

export function useCreateMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateMissionRequest) => MissionPlanner.createAndPlan(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useStartMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.startMission(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: missionKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function usePauseMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.pauseMission(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: missionKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useResumeMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.resumeMission(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: missionKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useCancelMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.cancelMission(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: missionKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useDeleteMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.deleteMission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useDuplicateMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => MissionPlanner.duplicateMission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: missionKeys.list() });
    },
  });
}

export function useSyncFreebuff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (missionId: string) => MissionPlanner.syncWithFreebuff(missionId),
    onSuccess: (_, missionId) => {
      queryClient.invalidateQueries({ queryKey: missionKeys.detail(missionId) });
    },
  });
}
