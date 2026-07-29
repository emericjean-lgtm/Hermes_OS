import type {
  Mission,
  MissionGraph,
  MissionTimeline,
  Agent,
  CollaborationMessage,
  Delegation,
  RuntimeInfo,
  RuntimeDecision,
  ResourceStatus,
  MemoryEntry,
  KnowledgeGraph,
  Experience,
  SearchResult,
  Skill,
  SkillSelection,
  SkillDistribution,
  ToolDefinition,
  ToolExecution,
  ToolHealth,
  MCPServer,
  PolicyRule,
  ApprovalRequest,
  AuditEntry,
  SystemEvent,
  ExecutionState,
  SystemHealth,
  SystemStatistics,
  AlexandrieStatus,
  AlexandrieDocument,
  AlexandrieSearchResults,
  AlexandrieSyncHistory,
  AlexandrieSyncResult,
  AlexandrieGraphEdges,
  AlexandrieMissionDocs,
  OhMyPiStatus,
  OhMyPiCapability,
  OhMyPiExecutionResult,
  KlaatCodeStatus,
  KlaatCodeCapability,
  KlaatCodeExecutionResult,
} from "@/types/hermes";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

// ── System ──────────────────────────────────────────
export const systemClient = {
  health: () => fetchJSON<SystemHealth>("/health"),
  statistics: () => fetchJSON<SystemStatistics>("/statistics"),
  version: () => fetchJSON<{ version: string }>("/version"),
};

// ── Missions ─────────────────────────────────────────
export const missionsClient = {
  list: () => fetchJSON<Mission[]>("/missions"),
  get: (id: string) => fetchJSON<Mission>(`/missions/${id}`),
  create: (data: Partial<Mission>) =>
    fetchJSON<Mission>("/missions", { method: "POST", body: JSON.stringify(data) }),
  graph: (id: string) => fetchJSON<MissionGraph>(`/missions/${id}/graph`),
  timeline: (id: string) => fetchJSON<MissionTimeline>(`/missions/${id}/timeline`),
  progress: (id: string) => fetchJSON<{ progress: number; completed: number; total: number }>(
    `/missions/${id}/progress`
  ),
  start: (id: string) => fetchJSON<Mission>(`/missions/${id}/start`, { method: "POST" }),
  pause: (id: string) => fetchJSON<Mission>(`/missions/${id}/pause`, { method: "POST" }),
  resume: (id: string) => fetchJSON<Mission>(`/missions/${id}/resume`, { method: "POST" }),
  cancel: (id: string) => fetchJSON<Mission>(`/missions/${id}/cancel`, { method: "POST" }),
};

// ── Agents ───────────────────────────────────────────
export const agentsClient = {
  list: () => fetchJSON<Agent[]>("/agents"),
  get: (id: string) => fetchJSON<Agent>(`/agents/${id}`),
  create: (data: Partial<Agent>) =>
    fetchJSON<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),
  start: (id: string) => fetchJSON<Agent>(`/agents/${id}/start`, { method: "POST" }),
  stop: (id: string) => fetchJSON<Agent>(`/agents/${id}/stop`, { method: "POST" }),
  pause: (id: string) => fetchJSON<Agent>(`/agents/${id}/pause`, { method: "POST" }),
  metrics: () => fetchJSON<Record<string, number>>("/agents/metrics"),
};

// ── Collaboration ────────────────────────────────────
export const collaborationClient = {
  messages: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    return fetchJSON<CollaborationMessage[]>(`/collaboration/messages${qs}`);
  },
  sendMessage: (data: Partial<CollaborationMessage>) =>
    fetchJSON<CollaborationMessage>("/collaboration/messages", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delegate: (data: Partial<Delegation>) =>
    fetchJSON<Delegation>("/collaboration/delegate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  review: (data: { task_id: string; reviewer_agent: string }) =>
    fetchJSON<{ status: string }>("/collaboration/review", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  history: (mission_id?: string) => {
    const qs = mission_id ? "?mission_id=" + mission_id : "";
    return fetchJSON<CollaborationMessage[]>(`/collaboration/history${qs}`);
  },
};

// ── Runtime ──────────────────────────────────────────
export const runtimeClient = {
  list: () => fetchJSON<RuntimeInfo[]>("/runtimes"),
  get: (name: string) => fetchJSON<RuntimeInfo>(`/runtimes/${name}`),
  health: () => fetchJSON<Record<string, { status: string; latency_ms: number }>>("/runtimes/health"),
  metrics: () => fetchJSON<Record<string, unknown>>("/runtimes/metrics"),
  resources: () => fetchJSON<ResourceStatus>("/runtime/resources/status"),
  allocations: () => fetchJSON<Record<string, unknown>[]>("/runtime/resources/allocations"),
  release: (data: { resource_id: string }) =>
    fetchJSON<{ status: string }>("/runtime/resources/release", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  select: (data: { task: Record<string, unknown> }) =>
    fetchJSON<RuntimeDecision>("/runtime/select", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Memory ───────────────────────────────────────────
export const memoryClient = {
  search: (q: string, mode: "hybrid" | "graph" | "keyword" = "hybrid") =>
    fetchJSON<SearchResult[]>(`/memory/search?q=${encodeURIComponent(q)}&mode=${mode}`),
  searchAdvanced: (data: Record<string, unknown>) =>
    fetchJSON<SearchResult[]>("/memory/search", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  graph: (node_id?: string, depth?: number) => {
    const qs = new URLSearchParams();
    if (node_id) qs.set("node_id", node_id);
    if (depth) qs.set("depth", String(depth));
    return fetchJSON<KnowledgeGraph>(`/memory/graph?${qs}`);
  },
  experiences: () => fetchJSON<Experience[]>("/memory/experiences"),
  index: (data: Record<string, unknown>) =>
    fetchJSON<MemoryEntry>("/memory/index", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  statistics: () => fetchJSON<Record<string, number>>("/memory/statistics"),
};

// ── Skills ───────────────────────────────────────────
export const skillsClient = {
  list: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    return fetchJSON<Skill[]>(`/skills${qs}`);
  },
  get: (id: string) => fetchJSON<Skill>(`/skills/${id}`),
  select: (data: { task_description: string; domain?: string }) =>
    fetchJSON<SkillSelection[]>("/skills/select", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  load: (data: { skill_id: string; agent_id: string }) =>
    fetchJSON<Skill>("/skills/load", { method: "POST", body: JSON.stringify(data) }),
  unload: (data: { skill_id: string; agent_id: string }) =>
    fetchJSON<{ status: string }>("/skills/unload", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cache: () => fetchJSON<Record<string, unknown>>("/skills/cache"),
  statistics: () => fetchJSON<Record<string, number>>("/skills/statistics"),
};

// ── Tools ────────────────────────────────────────────
export const toolsClient = {
  list: () => fetchJSON<ToolDefinition[]>("/tools"),
  get: (id: string) => fetchJSON<ToolDefinition>(`/tools/${id}`),
  register: (data: Partial<ToolDefinition>) =>
    fetchJSON<ToolDefinition>("/tools/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  execute: (data: { tool_id: string; params: Record<string, unknown>; agent_id?: string }) =>
    fetchJSON<ToolExecution>("/tools/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  select: (data: { task: Record<string, unknown>; agent_id?: string }) =>
    fetchJSON<{ tool_id: string; score: number; justification: string }>("/tools/select", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  health: () => fetchJSON<ToolHealth[]>("/tools/health"),
  metrics: () => fetchJSON<Record<string, number>>("/tools/metrics"),
  mcpServers: () => fetchJSON<MCPServer[]>("/mcp/servers"),
  mcpConnect: (data: { server_name: string; transport: string; endpoint: string }) =>
    fetchJSON<MCPServer>("/mcp/connect", { method: "POST", body: JSON.stringify(data) }),
  mcpDisconnect: (data: { server_name: string }) =>
    fetchJSON<{ status: string }>("/mcp/disconnect", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Governance ───────────────────────────────────────
export const governanceClient = {
  rules: () => fetchJSON<PolicyRule[]>("/policy/rules"),
  evaluate: (data: { operation: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<{ verdict: string; reason: string; rule_id?: string }>("/policy/evaluate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  approvals: () => fetchJSON<ApprovalRequest[]>("/approval"),
  approve: (id: string, comment?: string) =>
    fetchJSON<ApprovalRequest>(`/approval/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),
  reject: (id: string, comment?: string) =>
    fetchJSON<ApprovalRequest>(`/approval/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),
  audit: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    return fetchJSON<AuditEntry[]>(`/audit${qs}`);
  },
};

// ── Execution ────────────────────────────────────────
export const executionClient = {
  start: (data: { goal: string; mission_type?: string; priority?: string }) =>
    fetchJSON<ExecutionState>("/execution/start", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: string) => fetchJSON<ExecutionState>(`/execution/${id}`),
  list: () => fetchJSON<ExecutionState[]>("/execution"),
  pause: (id: string) =>
    fetchJSON<ExecutionState>(`/execution/${id}/pause`, { method: "POST" }),
  resume: (id: string) =>
    fetchJSON<ExecutionState>(`/execution/${id}/resume`, { method: "POST" }),
  cancel: (id: string) =>
    fetchJSON<ExecutionState>(`/execution/${id}/cancel`, { method: "POST" }),
  timeline: (id: string) => fetchJSON<MissionTimeline>(`/execution/${id}/timeline`),
  statistics: () => fetchJSON<SystemStatistics>("/execution/statistics"),
};

// ── Events ───────────────────────────────────────────
export const eventsClient = {
  list: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    return fetchJSON<SystemEvent[]>(`/events${qs}`);
  },
};

// ── Alexandrie ───────────────────────────────────────
export const alexandrieClient = {
  health: () => fetchJSON<{ healthy: boolean; error?: string }>("/alexandrie/health"),
  status: () => fetchJSON<AlexandrieStatus>("/alexandrie/status"),
  documents: () =>
    fetchJSON<{ total: number; documents: AlexandrieDocument[] }>("/alexandrie/documents"),
  getDocument: (id: string) => fetchJSON<AlexandrieDocument>(`/alexandrie/documents/${id}`),
  createDocument: (data: { title: string; content: string; user_id?: string; is_public?: boolean }) =>
    fetchJSON<AlexandrieDocument>("/alexandrie/documents", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteDocument: (id: string) =>
    fetchJSON<{ status: string }>(`/alexandrie/documents/${id}`, { method: "DELETE" }),
  search: (q: string, mode: "hybrid" | "fulltext" | "semantic" = "hybrid", limit = 20) =>
    fetchJSON<AlexandrieSearchResults>(
      `/alexandrie/search?q=${encodeURIComponent(q)}&mode=${mode}&limit=${limit}`
    ),
  sync: (data: { user_id?: string; incremental?: boolean }) =>
    fetchJSON<AlexandrieSyncResult>("/alexandrie/sync", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  syncStatus: () =>
    fetchJSON<{ last_sync_at: string | null; documents_synced: number }>("/alexandrie/sync/status"),
  syncHistory: (limit = 50) =>
    fetchJSON<AlexandrieSyncHistory>(`/alexandrie/sync/history?limit=${limit}`),
  graph: (node_id?: string) => {
    const qs = node_id ? `?node_id=${node_id}` : "";
    return fetchJSON<AlexandrieGraphEdges>(`/alexandrie/graph${qs}`);
  },
  cacheStats: () =>
    fetchJSON<{ entries: number; hits: number; misses: number; hit_rate: number }>(
      "/alexandrie/cache/stats"
    ),
  cachePrune: () =>
    fetchJSON<{ removed: number }>("/alexandrie/cache/prune", { method: "POST" }),
  linkToMission: (data: { document_id: string; mission_id: string }) =>
    fetchJSON<{ linked: boolean }>("/alexandrie/missions/link", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  missionDocuments: (mission_id: string) =>
    fetchJSON<AlexandrieMissionDocs>(`/alexandrie/missions/${mission_id}/documents`),
  relevantDocuments: (data: { tags: string[]; limit?: number }) =>
    fetchJSON<{ documents: { id: string; title: string; relevance: number }[] }>(
      "/alexandrie/missions/relevant",
      { method: "POST", body: JSON.stringify(data) }
    ),
  events: (limit = 50) =>
    fetchJSON<{ total: number; events: Record<string, unknown>[] }>(
      `/alexandrie/events?limit=${limit}`
    ),
};

// ── Oh My Pi ──────────────────────────────────────────
export const ohmypiClient = {
  status: () => fetchJSON<OhMyPiStatus>("/ohmypi/status"),
  capabilities: () =>
    fetchJSON<{ capabilities: OhMyPiCapability[]; count: number }>(
      "/ohmypi/capabilities"
    ),
  execute: (data: {
    action: string;
    parameters?: Record<string, unknown>;
    agent_id?: string;
    mission_id?: string;
  }) =>
    fetchJSON<OhMyPiExecutionResult>("/ohmypi/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── KlaatCode ─────────────────────────────────────────
export const klaatcodeClient = {
  status: () => fetchJSON<KlaatCodeStatus>("/klaatcode/status"),
  capabilities: () =>
    fetchJSON<{ capabilities: KlaatCodeCapability[]; count: number }>(
      "/klaatcode/capabilities"
    ),
  analyze: (data: { path: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  execute: (data: {
    action: string;
    parameters?: Record<string, unknown>;
    agent_id?: string;
    mission_id?: string;
  }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  diagnostics: (data: { file: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/diagnostics", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
