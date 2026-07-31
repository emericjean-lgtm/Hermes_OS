/**
 * MissionControlClient — client REST fortement typé pour l'API Hermes OS (HOS-028).
 * Point d'entrée unique pour toutes les données du dashboard.
 */
import type {
  HealthResponse,
  StatusResponse,
  DiagnosticsResponse,
  StatisticsResponse,
  RuntimeInfo,
  RuntimeHealthInfo,
  RuntimeMetrics,
  Mission,
  ExecutionStatus,
  MemoryEntry,
  MemorySearchResult,
  SkillInfo,
  SkillSelection,
  SystemEvent,
  EventStatistics,
  FreebuffProject,
  HermesAgentStatus,
} from "@/types/mission-control";

const API_URL =
  process.env.NEXT_PUBLIC_MC_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const API_PREFIX = "/api/v1";

class MissionControlClientError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "MissionControlClientError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL.replace(/\/$/, "")}${API_PREFIX}${path}`;
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new MissionControlClientError(
      response.status,
      `[${response.status}] ${path}: ${detail.slice(0, 200)}`,
    );
  }
  return response.json() as Promise<T>;
}

export const MissionControlClient = {
  // ─── Système ───────────────────────────────────────────────

  health: (): Promise<HealthResponse> => request("/health"),

  status: (): Promise<StatusResponse> => request("/status"),

  diagnostics: (): Promise<DiagnosticsResponse> => request("/diagnostics"),

  statistics: (): Promise<StatisticsResponse> => request("/statistics"),

  version: (): Promise<{ version: string; build: string }> =>
    request("/version"),

  // ─── Runtimes ──────────────────────────────────────────────

  runtimes: (): Promise<RuntimeInfo[]> => request("/runtimes"),

  runtimeHealth: (name?: string): Promise<RuntimeHealthInfo[] | RuntimeHealthInfo> =>
    request(name ? `/runtimes/${name}/health` : "/runtimes/health"),

  runtimeMetrics: (name?: string): Promise<RuntimeMetrics[] | RuntimeMetrics> =>
    request(name ? `/runtimes/${name}/metrics` : "/runtimes/metrics"),

  // ─── Missions ──────────────────────────────────────────────

  listMissions: (): Promise<Mission[]> => request("/missions"),

  getMission: (id: string): Promise<Mission> => request(`/missions/${id}`),

  createMission: (data: Partial<Mission>): Promise<Mission> =>
    request("/missions", {
      method: "POST",
      body: JSON.stringify(data),
      headers: { "Content-Type": "application/json" },
    }),

  startMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/start`, { method: "POST" }),

  pauseMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/pause`, { method: "POST" }),

  resumeMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/resume`, { method: "POST" }),

  cancelMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/cancel`, { method: "POST" }),

  // ─── Exécution ─────────────────────────────────────────────

  executionStatus: (): Promise<ExecutionStatus> => request("/execution"),

  // ─── Mémoire ───────────────────────────────────────────────

  listMemory: (scope?: string): Promise<MemoryEntry[]> =>
    request(scope ? `/memory?scope=${scope}` : "/memory"),

  searchMemory: (query: string): Promise<MemorySearchResult> =>
    request(`/memory/search?q=${encodeURIComponent(query)}`),

  // ─── Compétences ───────────────────────────────────────────

  listSkills: (): Promise<SkillInfo[]> => request("/skills"),

  recommendSkills: (mission: string): Promise<SkillSelection> =>
    request("/skills/recommend", {
      method: "POST",
      body: JSON.stringify({ mission }),
      headers: { "Content-Type": "application/json" },
    }),

  // ─── Événements ────────────────────────────────────────────

  listEvents: (
    limit?: number,
    type?: string,
    severity?: string,
  ): Promise<SystemEvent[]> => {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    if (type) params.set("type", type);
    if (severity) params.set("severity", severity);
    const qs = params.toString();
    return request(qs ? `/events?${qs}` : "/events");
  },

  eventStatistics: (): Promise<EventStatistics> =>
    request("/events/statistics"),

  // ─── Freebuff ──────────────────────────────────────────────

  listFreebuffProjects: (): Promise<FreebuffProject[]> =>
    request("/freebuff/projects"),

  // ─── Hermes Agent ──────────────────────────────────────────

  hermesStatus: (): Promise<HermesAgentStatus> => request("/hermes/status"),
};
