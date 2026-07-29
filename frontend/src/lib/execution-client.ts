/**
 * ExecutionClient — client pour le centre d'exécution HOS-031.
 * Consomme exclusivement l'API HOS-028.
 */
import type {
  ExecutionOverviewResponse,
  ExecutionTask,
  ExecutionTimelineEvent,
  ExecutionPerformanceData,
  ExecutionStatisticsResponse,
  ExecutionGraphData,
} from "@/types/mission-control";

const API_PREFIX = "/api/hermes-os";

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

export const ExecutionClient = {
  // ─── Overview ──────────────────────────────────────────────

  overview: (): Promise<ExecutionOverviewResponse> => request("/execution"),

  // ─── Control ───────────────────────────────────────────────

  tick: (): Promise<{ state: string; changes: string[] }> =>
    request("/tick", { method: "POST" }),

  pause: (): Promise<ExecutionOverviewResponse> =>
    request("/execution/pause", { method: "POST" }),

  resume: (): Promise<ExecutionOverviewResponse> =>
    request("/execution/resume", { method: "POST" }),

  cancel: (): Promise<ExecutionOverviewResponse> =>
    request("/execution/cancel", { method: "POST" }),

  recover: (): Promise<ExecutionOverviewResponse> =>
    request("/execution/recover", { method: "POST" }),

  retryFailed: (): Promise<ExecutionOverviewResponse> =>
    request("/execution/retry", { method: "POST" }),

  exportLogs: (): Promise<Blob> => {
    const API_URL =
      process.env.NEXT_PUBLIC_MC_API_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000";
    return fetch(`${API_URL.replace(/\/$/, "")}${API_PREFIX}/execution/export`).then((r) => r.blob());
  },

  // ─── Tasks ─────────────────────────────────────────────────

  tasks: (): Promise<ExecutionTask[]> => request("/execution/tasks"),

  // ─── Timeline ──────────────────────────────────────────────

  timeline: (limit?: number): Promise<ExecutionTimelineEvent[]> =>
    request(limit ? `/execution/timeline?limit=${limit}` : "/execution/timeline"),

  // ─── Performance & Statistics ──────────────────────────────

  performance: (): Promise<ExecutionPerformanceData> => request("/execution/performance"),

  statistics: (): Promise<ExecutionStatisticsResponse> => request("/events/statistics"),

  // ─── Graph ─────────────────────────────────────────────────

  graph: (): Promise<ExecutionGraphData> => request("/execution/graph"),

  // ─── Mission-specific ──────────────────────────────────────

  forMission: (missionId: string) => ({
    overview: (): Promise<ExecutionOverviewResponse> =>
      request(`/missions/${missionId}/execution`),
    tasks: (): Promise<ExecutionTask[]> =>
      request(`/missions/${missionId}/execution/tasks`),
    timeline: (limit?: number): Promise<ExecutionTimelineEvent[]> =>
      request(limit ? `/missions/${missionId}/execution/timeline?limit=${limit}` : `/missions/${missionId}/execution/timeline`),
    performance: (): Promise<ExecutionPerformanceData> =>
      request(`/missions/${missionId}/execution/performance`),
    graph: (): Promise<ExecutionGraphData> =>
      request(`/missions/${missionId}/execution/graph`),
  }),

  // ─── Utilitaires (données de démonstration) ────────────────

  samplePerformance: (): ExecutionPerformanceData => ({
    task_durations: [
      { task: "Analyze", duration_ms: 5200 },
      { task: "Search", duration_ms: 2800 },
      { task: "Plan", duration_ms: 8100 },
      { task: "Validate", duration_ms: 3900 },
      { task: "Execute", duration_ms: 14200 },
      { task: "Review", duration_ms: 4800 },
    ],
    avg_latency_ms: 3200,
    wait_time_ms: 1200,
    retries: 2,
    fallbacks: 1,
    circuit_breaker_count: 0,
    runtime_usage: [
      { runtime: "ollama", count: 5 },
      { runtime: "stub", count: 2 },
    ],
    timeline: Array.from({ length: 20 }, (_, i) => ({
      time: `T+${i * 2}s`,
      value: Math.random() * 100,
    })),
  }),

  sampleTasks: (): ExecutionTask[] => [
    { id: "t1", name: "Analyze Request", agent_id: "agent-1", runtime: "ollama", status: "completed", duration_ms: 5200, progress: 100, retries: 0 },
    { id: "t2", name: "Search Context", agent_id: "agent-2", runtime: "ollama", status: "completed", duration_ms: 2800, progress: 100, retries: 0 },
    { id: "t3", name: "Generate Plan", agent_id: "agent-1", runtime: "ollama", status: "running", duration_ms: 4100, progress: 55, retries: 0 },
    { id: "t4", name: "Validate Plan", agent_id: "agent-3", runtime: "stub", status: "pending", progress: 0, retries: 0 },
    { id: "t5", name: "Execute Tasks", agent_id: "agent-1", runtime: "ollama", status: "pending", progress: 0, retries: 1, fallback_used: true },
    { id: "t6", name: "Review Results", agent_id: "agent-2", runtime: "ollama", status: "failed", duration_ms: 3200, progress: 60, retries: 2, error: "Timeout exceeded" },
  ],

  sampleTimeline: (): ExecutionTimelineEvent[] => [
    { id: "e1", type: "execution.started", timestamp: new Date().toISOString(), message: "Mission execution started", severity: "INFO" },
    { id: "e2", type: "task.ready", timestamp: new Date(Date.now() - 30000).toISOString(), message: "Task 'Analyze Request' is ready", severity: "INFO" },
    { id: "e3", type: "task.started", timestamp: new Date(Date.now() - 25000).toISOString(), message: "Task 'Analyze Request' started on ollama", severity: "INFO" },
    { id: "e4", type: "task.completed", timestamp: new Date(Date.now() - 20000).toISOString(), message: "Task 'Analyze Request' completed (5.2s)", severity: "INFO" },
    { id: "e5", type: "task.started", timestamp: new Date(Date.now() - 18000).toISOString(), message: "Task 'Search Context' started on ollama", severity: "INFO" },
    { id: "e6", type: "task.completed", timestamp: new Date(Date.now() - 15000).toISOString(), message: "Task 'Search Context' completed (2.8s)", severity: "INFO" },
    { id: "e7", type: "task.started", timestamp: new Date(Date.now() - 12000).toISOString(), message: "Task 'Generate Plan' started on ollama", severity: "INFO" },
    { id: "e8", type: "execution.fallback", timestamp: new Date(Date.now() - 5000).toISOString(), message: "Fallback to stub runtime for 'Execute Tasks'", severity: "WARNING" },
    { id: "e9", type: "task.failed", timestamp: new Date(Date.now() - 2000).toISOString(), message: "Task 'Review Results' failed: Timeout exceeded", severity: "ERROR" },
  ],
};
