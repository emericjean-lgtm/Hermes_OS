"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  systemClient,
  missionsClient,
  agentsClient,
  collaborationClient,
  runtimeClient,
  memoryClient,
  skillsClient,
  toolsClient,
  governanceClient,
  executionClient,
  eventsClient,
  alexandrieClient,
} from "@/services/client";
import type {
  Mission,
  Agent,
  CollaborationMessage,
  Delegation,
  RuntimeInfo,
  MemoryEntry,
  SearchResult,
  Skill,
  SkillSelection,
  ToolDefinition,
  ToolExecution,
  PolicyRule,
  ApprovalRequest,
  AuditEntry,
  ExecutionState,
  SystemHealth,
  SystemStatistics,
  SystemEvent,
  KnowledgeGraph,
  Experience,
  ResourceStatus,
  MCPServer,
  ToolHealth,
  AlexandrieStatus,
  AlexandrieSearchResults,
  AlexandrieSyncResult,
} from "@/types/hermes";

// ── System ──────────────────────────────────────────
export function useSystemHealth() {
  return useQuery<SystemHealth>({ queryKey: ["system", "health"], queryFn: systemClient.health });
}
export function useSystemStatistics() {
  return useQuery<SystemStatistics>({ queryKey: ["system", "statistics"], queryFn: systemClient.statistics });
}

// ── Missions ─────────────────────────────────────────
export function useMissions() {
  return useQuery<Mission[]>({ queryKey: ["missions"], queryFn: missionsClient.list });
}
export function useMission(id: string | null) {
  return useQuery<Mission | null>({
    queryKey: ["missions", id],
    queryFn: () => (id ? missionsClient.get(id) : null),
    enabled: !!id,
  });
}
export function useMissionGraph(id: string | null) {
  return useQuery({
    queryKey: ["missions", id, "graph"],
    queryFn: () => (id ? missionsClient.graph(id) : null),
    enabled: !!id,
  });
}
export function useMissionTimeline(id: string | null) {
  return useQuery({
    queryKey: ["missions", id, "timeline"],
    queryFn: () => (id ? missionsClient.timeline(id) : null),
    enabled: !!id,
  });
}
export function useCreateMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: missionsClient.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["missions"] }),
  });
}
export function useMissionAction(id: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["missions"] });
    qc.invalidateQueries({ queryKey: ["missions", id] });
  };
  return {
    start: useMutation({ mutationFn: () => missionsClient.start(id), onSuccess: invalidate }),
    pause: useMutation({ mutationFn: () => missionsClient.pause(id), onSuccess: invalidate }),
    resume: useMutation({ mutationFn: () => missionsClient.resume(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: () => missionsClient.cancel(id), onSuccess: invalidate }),
  };
}

// ── Agents ───────────────────────────────────────────
export function useAgents() {
  return useQuery<Agent[]>({ queryKey: ["agents"], queryFn: agentsClient.list });
}
export function useAgent(id: string | null) {
  return useQuery<Agent | null>({
    queryKey: ["agents", id],
    queryFn: () => (id ? agentsClient.get(id) : null),
    enabled: !!id,
  });
}
export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: agentsClient.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

// ── Collaboration ────────────────────────────────────
export function useCollaborationMessages(mission_id?: string) {
  return useQuery<CollaborationMessage[]>({
    queryKey: ["collaboration", "messages", mission_id],
    queryFn: () => collaborationClient.messages(mission_id ? { mission_id } : undefined),
  });
}
export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: collaborationClient.sendMessage,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collaboration"] }),
  });
}

// ── Runtime ──────────────────────────────────────────
export function useRuntimes() {
  return useQuery<RuntimeInfo[]>({ queryKey: ["runtimes"], queryFn: runtimeClient.list });
}
export function useRuntimeHealth() {
  return useQuery({ queryKey: ["runtimes", "health"], queryFn: runtimeClient.health });
}
export function useResourceStatus() {
  return useQuery<ResourceStatus>({ queryKey: ["runtime", "resources"], queryFn: runtimeClient.resources });
}

// ── Memory ───────────────────────────────────────────
export function useMemorySearch(q: string, mode: "hybrid" | "graph" | "keyword" = "hybrid") {
  return useQuery<SearchResult[]>({
    queryKey: ["memory", "search", q, mode],
    queryFn: () => memoryClient.search(q, mode),
    enabled: q.length > 0,
  });
}
export function useKnowledgeGraph(node_id?: string) {
  return useQuery<KnowledgeGraph>({
    queryKey: ["memory", "graph", node_id],
    queryFn: () => memoryClient.graph(node_id, 3),
  });
}
export function useExperiences() {
  return useQuery<Experience[]>({ queryKey: ["memory", "experiences"], queryFn: memoryClient.experiences });
}
export function useMemoryStatistics() {
  return useQuery({ queryKey: ["memory", "statistics"], queryFn: memoryClient.statistics });
}

// ── Skills ───────────────────────────────────────────
export function useSkills() {
  return useQuery<Skill[]>({ queryKey: ["skills"], queryFn: () => skillsClient.list() });
}
export function useSelectSkills(taskDescription: string) {
  return useQuery<SkillSelection[]>({
    queryKey: ["skills", "select", taskDescription],
    queryFn: () => skillsClient.select({ task_description: taskDescription }),
    enabled: taskDescription.length > 3,
  });
}
export function useSkillCache() {
  return useQuery({ queryKey: ["skills", "cache"], queryFn: skillsClient.cache });
}

// ── Tools ────────────────────────────────────────────
export function useTools() {
  return useQuery<ToolDefinition[]>({ queryKey: ["tools"], queryFn: toolsClient.list });
}
export function useToolsHealth() {
  return useQuery<ToolHealth[]>({ queryKey: ["tools", "health"], queryFn: toolsClient.health });
}
export function useMCPServers() {
  return useQuery<MCPServer[]>({ queryKey: ["tools", "mcp"], queryFn: toolsClient.mcpServers });
}
export function useExecuteTool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: toolsClient.execute,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tools"] }),
  });
}

// ── Governance ───────────────────────────────────────
export function usePolicyRules() {
  return useQuery<PolicyRule[]>({ queryKey: ["policy", "rules"], queryFn: governanceClient.rules });
}
export function useApprovals() {
  return useQuery<ApprovalRequest[]>({ queryKey: ["approvals"], queryFn: governanceClient.approvals });
}
export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => governanceClient.approve(id, comment),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
}
export function useRejectAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => governanceClient.reject(id, comment),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
}
export function useAuditLog(params?: Record<string, string>) {
  return useQuery<AuditEntry[]>({
    queryKey: ["audit", params],
    queryFn: () => governanceClient.audit(params),
  });
}

// ── Execution ────────────────────────────────────────
export function useExecutions() {
  return useQuery<ExecutionState[]>({ queryKey: ["executions"], queryFn: executionClient.list });
}
export function useExecution(id: string | null) {
  return useQuery<ExecutionState | null>({
    queryKey: ["executions", id],
    queryFn: () => (id ? executionClient.get(id) : null),
    enabled: !!id,
  });
}
export function useStartExecution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: executionClient.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["executions"] }),
  });
}
export function useExecutionAction(id: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["executions"] });
    qc.invalidateQueries({ queryKey: ["executions", id] });
  };
  return {
    pause: useMutation({ mutationFn: () => executionClient.pause(id), onSuccess: invalidate }),
    resume: useMutation({ mutationFn: () => executionClient.resume(id), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: () => executionClient.cancel(id), onSuccess: invalidate }),
  };
}

// ── Events ───────────────────────────────────────────
export function useEvents(params?: Record<string, string>) {
  return useQuery<SystemEvent[]>({
    queryKey: ["events", params],
    queryFn: () => eventsClient.list(params),
  });
}

// ── Alexandrie ───────────────────────────────────────
export function useAlexandrieStatus() {
  return useQuery<AlexandrieStatus>({ queryKey: ["alexandrie", "status"], queryFn: alexandrieClient.status, refetchInterval: 15000 });
}
export function useAlexandrieHealth() {
  return useQuery({ queryKey: ["alexandrie", "health"], queryFn: alexandrieClient.health, refetchInterval: 30000 });
}
export function useAlexandrieSearch(q: string, mode: "hybrid" | "fulltext" | "semantic" = "hybrid") {
  return useQuery<AlexandrieSearchResults>({
    queryKey: ["alexandrie", "search", q, mode],
    queryFn: () => alexandrieClient.search(q, mode),
    enabled: q.length > 1,
  });
}
export function useAlexandrieSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data?: { user_id?: string; incremental?: boolean }) => alexandrieClient.sync(data || {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alexandrie"] });
      qc.invalidateQueries({ queryKey: ["memory"] });
    },
  });
}
export function useAlexandrieSyncHistory() {
  return useQuery({ queryKey: ["alexandrie", "sync", "history"], queryFn: () => alexandrieClient.syncHistory() });
}
export function useAlexandrieDocuments() {
  return useQuery({ queryKey: ["alexandrie", "documents"], queryFn: () => alexandrieClient.documents() });
}
export function useAlexandrieGraph(node_id?: string) {
  return useQuery({
    queryKey: ["alexandrie", "graph", node_id],
    queryFn: () => alexandrieClient.graph(node_id),
    enabled: true,
  });
}
