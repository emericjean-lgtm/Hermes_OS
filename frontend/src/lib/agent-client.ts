/**
 * AgentClient — client pour le Agent Center HOS-032.
 * Consomme exclusivement l'API HOS-028.
 */
import type {
  AgentInfo,
  AgentDetail,
  AgentStatisticsResponse,
  AgentGraphData,
  AgentTimelineEvent,
  AgentPerformanceData,
  HermesAgentStatus,
} from "@/types/mission-control";

const API_PREFIX = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const API_URL =
    process.env.NEXT_PUBLIC_MC_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const url = `${API_URL.replace(/\/$/, "")}${API_PREFIX}${path}`;
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`[${response.status}] ${path}: ${detail.slice(0, 200)}`);
  }
  return response.json() as Promise<T>;
}

export const AgentClient = {
  // ─── List / Overview ──────────────────────────────────────

  list: (missionId?: string): Promise<AgentInfo[]> =>
    request(missionId ? `/agents?mission_id=${missionId}` : "/agents"),

  statistics: (): Promise<AgentStatisticsResponse> => request("/agents/statistics"),

  // ─── Detail ──────────────────────────────────────────────

  get: (id: string): Promise<AgentDetail> => request(`/agents/${id}`),

  // ─── Graph ────────────────────────────────────────────────

  graph: (missionId?: string): Promise<AgentGraphData> =>
    request(missionId ? `/agents/graph?mission_id=${missionId}` : "/agents/graph"),

  // ─── Timeline ─────────────────────────────────────────────

  timeline: (agentId?: string, limit = 50): Promise<AgentTimelineEvent[]> =>
    request(agentId ? `/agents/timeline?agent_id=${agentId}&limit=${limit}` : `/agents/timeline?limit=${limit}`),

  // ─── Performance ──────────────────────────────────────────

  performance: (): Promise<AgentPerformanceData> => request("/agents/performance"),

  // ─── Control ──────────────────────────────────────────────

  pause: (id: string): Promise<AgentInfo> => request(`/agents/${id}/pause`, { method: "POST" }),
  resume: (id: string): Promise<AgentInfo> => request(`/agents/${id}/resume`, { method: "POST" }),
  cancel: (id: string): Promise<AgentInfo> => request(`/agents/${id}/cancel`, { method: "POST" }),
  retry: (id: string): Promise<AgentInfo> => request(`/agents/${id}/retry`, { method: "POST" }),
  recover: (id: string): Promise<AgentInfo> => request(`/agents/${id}/recover`, { method: "POST" }),
  duplicate: (id: string): Promise<AgentInfo> => request(`/agents/${id}/duplicate`, { method: "POST" }),

  // ─── Hermes Agent ─────────────────────────────────────────

  hermesStatus: (): Promise<HermesAgentStatus> => request("/hermes/status"),
  hermesConnect: (): Promise<HermesAgentStatus> => request("/hermes/connect", { method: "POST" }),
  hermesDisconnect: (): Promise<HermesAgentStatus> => request("/hermes/disconnect", { method: "POST" }),
  hermesCreateSubagent: (): Promise<AgentInfo> => request("/hermes/subagent", { method: "POST" }),

  // ─── Sample data ──────────────────────────────────────────

  sampleAgents: (): AgentInfo[] => [
    { id: "a1", name: "Planner", state: "COMPLETED", runtime: "ollama", priority: 1, duration_ms: 8200, retries: 0, fallback_used: false, progress: 100, created_at: new Date(Date.now() - 60000).toISOString() },
    { id: "a2", name: "Analyst", state: "RUNNING", runtime: "ollama", mission_id: "m1", task_id: "t3", priority: 2, duration_ms: 4500, retries: 0, fallback_used: false, progress: 60, created_at: new Date(Date.now() - 30000).toISOString() },
    { id: "a3", name: "Searcher", state: "COMPLETED", runtime: "ollama", mission_id: "m1", task_id: "t2", priority: 1, duration_ms: 3200, retries: 1, fallback_used: true, progress: 100, created_at: new Date(Date.now() - 45000).toISOString() },
    { id: "a4", name: "Validator", state: "READY", runtime: "stub", mission_id: "m1", task_id: "t4", priority: 3, duration_ms: 0, retries: 0, fallback_used: false, progress: 0, created_at: new Date(Date.now() - 15000).toISOString() },
    { id: "a5", name: "Executor", state: "FAILED", runtime: "ollama", mission_id: "m1", task_id: "t5", priority: 1, duration_ms: 6200, retries: 2, fallback_used: true, progress: 55, created_at: new Date(Date.now() - 20000).toISOString(), error: "Runtime timeout after 6s" },
    { id: "a6", name: "Reviewer", state: "CREATED", runtime: "ollama", mission_id: "m1", task_id: "t6", priority: 2, duration_ms: 0, retries: 0, fallback_used: false, progress: 0, created_at: new Date(Date.now() - 5000).toISOString() },
  ],

  sampleStatistics: (): AgentStatisticsResponse => ({
    total_agents: 6, active_agents: 1, completed_agents: 2, failed_agents: 1, sub_agents: 2,
    success_rate: 66.7, avg_duration_ms: 4400, total_retries: 3, total_fallbacks: 2,
    runtime_distribution: { ollama: 5, stub: 1 },
  }),

  samplePerformance: (): AgentPerformanceData => ({
    agent_durations: [
      { agent: "Planner", duration_ms: 8200 },
      { agent: "Analyst", duration_ms: 4500 },
      { agent: "Searcher", duration_ms: 3200 },
      { agent: "Validator", duration_ms: 0 },
      { agent: "Executor", duration_ms: 6200 },
      { agent: "Reviewer", duration_ms: 0 },
    ],
    success_rate: 66.7,
    runtime_distribution: [{ runtime: "ollama", count: 5 }, { runtime: "stub", count: 1 }],
    retries_by_agent: [
      { agent: "Searcher", retries: 1 },
      { agent: "Executor", retries: 2 },
    ],
    fallbacks_by_agent: [
      { agent: "Searcher", fallbacks: 1 },
      { agent: "Executor", fallbacks: 1 },
    ],
    memory_usage: [
      { agent: "Planner", memory_mb: 128 },
      { agent: "Analyst", memory_mb: 256 },
      { agent: "Searcher", memory_mb: 64 },
      { agent: "Executor", memory_mb: 192 },
    ],
    duration_histogram: [
      { bucket: "0-2s", count: 2 },
      { bucket: "2-5s", count: 2 },
      { bucket: "5-10s", count: 2 },
    ],
  }),
};
