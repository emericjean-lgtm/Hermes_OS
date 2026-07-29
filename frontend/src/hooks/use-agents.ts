"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AgentClient } from "@/lib/agent-client";
import type { AgentInfo, AgentDetail, HermesAgentStatus } from "@/types/mission-control";

export const agentKeys = {
  all: ["agents"] as const,
  list: (missionId?: string) => [...agentKeys.all, "list", missionId] as const,
  detail: (id: string) => [...agentKeys.all, "detail", id] as const,
  statistics: () => [...agentKeys.all, "statistics"] as const,
  graph: (missionId?: string) => [...agentKeys.all, "graph", missionId] as const,
  timeline: (agentId?: string) => [...agentKeys.all, "timeline", agentId] as const,
  performance: () => [...agentKeys.all, "performance"] as const,
  hermes: () => [...agentKeys.all, "hermes"] as const,
};

export function useAgents(missionId?: string) {
  return useQuery({
    queryKey: agentKeys.list(missionId),
    queryFn: () => AgentClient.list(missionId),
    refetchInterval: 5_000,
  });
}

export function useAgent(id: string | null) {
  return useQuery({
    queryKey: agentKeys.detail(id ?? ""),
    queryFn: () => AgentClient.get(id!),
    enabled: !!id,
    refetchInterval: 5_000,
  });
}

export function useAgentStatistics() {
  return useQuery({
    queryKey: agentKeys.statistics(),
    queryFn: AgentClient.statistics,
    refetchInterval: 15_000,
  });
}

export function useAgentGraph(missionId?: string) {
  return useQuery({
    queryKey: agentKeys.graph(missionId),
    queryFn: () => AgentClient.graph(missionId),
    refetchInterval: 10_000,
  });
}

export function useAgentTimeline(agentId?: string) {
  return useQuery({
    queryKey: agentKeys.timeline(agentId),
    queryFn: () => AgentClient.timeline(agentId),
    refetchInterval: 5_000,
  });
}

export function useAgentPerformance() {
  return useQuery({
    queryKey: agentKeys.performance(),
    queryFn: AgentClient.performance,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });
}

export function useHermesStatus() {
  return useQuery<HermesAgentStatus>({
    queryKey: agentKeys.hermes(),
    queryFn: AgentClient.hermesStatus,
    staleTime: 30_000,
  });
}

export function useAgentControl() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: agentKeys.all });
  };

  const pause = useMutation({ mutationFn: (id: string) => AgentClient.pause(id), onSuccess: invalidate });
  const resume = useMutation({ mutationFn: (id: string) => AgentClient.resume(id), onSuccess: invalidate });
  const cancel = useMutation({ mutationFn: (id: string) => AgentClient.cancel(id), onSuccess: invalidate });
  const retry = useMutation({ mutationFn: (id: string) => AgentClient.retry(id), onSuccess: invalidate });
  const recover = useMutation({ mutationFn: (id: string) => AgentClient.recover(id), onSuccess: invalidate });
  const duplicate = useMutation({ mutationFn: (id: string) => AgentClient.duplicate(id), onSuccess: invalidate });

  const hermesConnect = useMutation({ mutationFn: AgentClient.hermesConnect, onSuccess: invalidate });
  const hermesDisconnect = useMutation({ mutationFn: AgentClient.hermesDisconnect, onSuccess: invalidate });
  const hermesCreateSubagent = useMutation({ mutationFn: AgentClient.hermesCreateSubagent, onSuccess: invalidate });

  return { pause, resume, cancel, retry, recover, duplicate, hermesConnect, hermesDisconnect, hermesCreateSubagent };
}
