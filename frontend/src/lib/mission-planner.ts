/**
 * MissionPlanner — client pour le planning et la visualisation des missions HOS-030.
 * Utilise MissionControlClient comme base et ajoute les opérations de planification.
 */
import { MissionControlClient } from "./mission-control";
import type {
  Mission,
  CreateMissionRequest,
  MissionPlan,
  MissionActionResponse,
  ExecutionGraphData,
  GraphNode,
  GraphEdge,
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

export const MissionPlanner = {
  // ─── Création & Planification ─────────────────────────────

  createAndPlan: async (data: CreateMissionRequest): Promise<{ mission: Mission; plan: MissionPlan }> => {
    return request("/missions/plan", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  createMission: (data: CreateMissionRequest): Promise<Mission> =>
    request("/missions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  planMission: (missionId: string): Promise<MissionPlan> =>
    request(`/missions/${missionId}/plan`, { method: "POST" }),

  // ─── Cycle de vie ─────────────────────────────────────────

  startMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/start`, { method: "POST" }),

  pauseMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/pause`, { method: "POST" }),

  resumeMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/resume`, { method: "POST" }),

  cancelMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/cancel`, { method: "POST" }),

  deleteMission: (id: string): Promise<void> =>
    request(`/missions/${id}`, { method: "DELETE" }),

  duplicateMission: (id: string): Promise<Mission> =>
    request(`/missions/${id}/duplicate`, { method: "POST" }),

  exportMission: (id: string): Promise<Blob> => {
    const API_URL =
      process.env.NEXT_PUBLIC_MC_API_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000";
    return fetch(`${API_URL.replace(/\/$/, "")}${API_PREFIX}/missions/${id}/export`).then((r) => r.blob());
  },

  // ─── Graph / ExecutionGraph ───────────────────────────────

  getMissionGraph: (id: string): Promise<ExecutionGraphData> =>
    request(`/missions/${id}/graph`),

  // ─── Utilitaires ──────────────────────────────────────────

  generateSampleGraph: (): ExecutionGraphData => ({
    nodes: [
      { id: "start", label: "Start", type: "start", status: "completed", capability: "system" },
      { id: "analyze", label: "Analyze Request", type: "task", status: "completed", capability: "reasoning", complexity: "medium", estimated_ms: 5000 },
      { id: "search", label: "Search Context", type: "task", status: "completed", capability: "retrieval", complexity: "low", estimated_ms: 3000 },
      { id: "plan", label: "Generate Plan", type: "task", status: "running", capability: "planning", complexity: "high", estimated_ms: 8000 },
      { id: "validate", label: "Validate Plan", type: "condition", status: "pending", capability: "validation", complexity: "medium", estimated_ms: 4000 },
      { id: "execute", label: "Execute Tasks", type: "task", status: "pending", capability: "execution", complexity: "high", estimated_ms: 15000 },
      { id: "review", label: "Review Results", type: "task", status: "pending", capability: "reasoning", complexity: "medium", estimated_ms: 5000 },
      { id: "end", label: "Complete", type: "end", status: "pending", capability: "system" },
    ],
    edges: [
      { id: "e1", source: "start", target: "analyze" },
      { id: "e2", source: "start", target: "search" },
      { id: "e3", source: "analyze", target: "plan" },
      { id: "e4", source: "search", target: "plan" },
      { id: "e5", source: "plan", target: "validate" },
      { id: "e6", source: "validate", target: "execute", label: "valid" },
      { id: "e7", source: "execute", target: "review" },
      { id: "e8", source: "review", target: "end" },
    ],
  }),
};
