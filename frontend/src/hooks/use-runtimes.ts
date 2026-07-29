"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RuntimeClient } from "@/lib/runtime-client";

export const runtimeKeys = {
  all: ["runtimes"] as const,
  list: () => [...runtimeKeys.all, "list"] as const,
  detail: (n: string) => [...runtimeKeys.all, "detail", n] as const,
  health: (n?: string) => [...runtimeKeys.all, "health", n] as const,
  metrics: (n?: string) => [...runtimeKeys.all, "metrics", n] as const,
  decisions: () => [...runtimeKeys.all, "decisions"] as const,
  decision: (n: string) => [...runtimeKeys.all, "decision", n] as const,
  policies: () => [...runtimeKeys.all, "policies"] as const,
  events: (r?: string) => [...runtimeKeys.all, "events", r] as const,
};

export function useRuntimeList() { return useQuery({ queryKey: runtimeKeys.list(), queryFn: RuntimeClient.list, refetchInterval: 10_000 }); }
export function useRuntime(name: string | null) { return useQuery({ queryKey: runtimeKeys.detail(name ?? ""), queryFn: () => RuntimeClient.get(name!), enabled: !!name, refetchInterval: 10_000 }); }
export function useRuntimeHealth(name?: string) { return useQuery({ queryKey: runtimeKeys.health(name), queryFn: () => RuntimeClient.health(name), refetchInterval: 5_000 }); }
export function useRuntimeMetrics(name?: string) { return useQuery({ queryKey: runtimeKeys.metrics(name), queryFn: () => RuntimeClient.metrics(name), refetchInterval: 10_000 }); }
export function useRuntimeDecisions() { return useQuery({ queryKey: runtimeKeys.decisions(), queryFn: RuntimeClient.decisions, staleTime: 15_000, refetchInterval: 15_000 }); }
export function useRuntimeDecision(name: string | null) { return useQuery({ queryKey: runtimeKeys.decision(name ?? ""), queryFn: () => RuntimeClient.decision(name!), enabled: !!name, staleTime: 15_000 }); }
export function useRuntimePolicies() { return useQuery({ queryKey: runtimeKeys.policies(), queryFn: RuntimeClient.policies, staleTime: 30_000 }); }
export function useRuntimeEvents(runtime?: string) { return useQuery({ queryKey: runtimeKeys.events(runtime), queryFn: () => RuntimeClient.events(runtime), refetchInterval: 5_000 }); }

export function useRuntimeControl() {
  const qc = useQueryClient();
  const inv = () => { qc.invalidateQueries({ queryKey: runtimeKeys.all }); };
  return {
    refresh: useMutation({ mutationFn: (n: string) => RuntimeClient.refresh(n), onSuccess: inv }),
    healthCheck: useMutation({ mutationFn: (n: string) => RuntimeClient.healthCheck(n), onSuccess: inv }),
    resetCircuit: useMutation({ mutationFn: (n: string) => RuntimeClient.resetCircuit(n), onSuccess: inv }),
    disable: useMutation({ mutationFn: (n: string) => RuntimeClient.disable(n), onSuccess: inv }),
    enable: useMutation({ mutationFn: (n: string) => RuntimeClient.enable(n), onSuccess: inv }),
  };
}
