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

/** Pull the array out of a `{ key: [...] , total: n }` envelope.
 *
 *  Most Hermes list endpoints wrap their payload — `/agents` returns
 *  `{agents, total}`, `/tools` returns `{tools, count, stats}` and so on — but
 *  these client methods were typed as returning a bare array. Nothing caught it
 *  because the Cockpit could not reach the backend at all (the shipped
 *  `.env.local.example` omitted the `/api/v1` prefix and CORS only allowed port
 *  3000), so every call failed and the components fell back to `[]`. With
 *  connectivity restored the Dashboard crashed outright on
 *  `missions.filter is not a function`.
 *
 *  Tolerates a bare array too, so an endpoint that is already unwrapped — or is
 *  changed to be — keeps working.
 */
function unwrap<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const inner = (payload as Record<string, unknown>)[key];
    if (Array.isArray(inner)) return inner as T[];
  }
  return [];
}

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

/** Réponse réelle de GET /api/v1/system/health (ServiceHealthProbe).
 *  Documentée ici parce qu'elle ne ressemble pas au type SystemHealth que
 *  le Cockpit manipule : statuts en minuscules, sous-systèmes sous `detail`,
 *  ni version ni uptime. La normalisation est faite ci-dessous. */
interface SubsystemHealthWire {
  status?: string;
  detail?: string;
}
interface SystemHealthWire {
  status?: string;
  services?: number;
  by_status?: Record<string, number>;
  unhealthy?: string[];
  silent?: string[];
  detail?: Record<string, SubsystemHealthWire>;
}
interface RootHealthWire {
  status?: string;
  uptime_seconds?: number;
}

const normaliseStatus = (s: string | undefined): SystemHealth["status"] => {
  const v = (s ?? "").toLowerCase();
  if (v === "healthy" || v === "ok") return "HEALTHY";
  if (v === "degraded") return "DEGRADED";
  if (v === "unhealthy" || v === "error" || v === "failed") return "UNHEALTHY";
  // "unknown" et tout statut non prévu : ne pas mentir en annonçant HEALTHY.
  return "DEGRADED";
};

// ── System ──────────────────────────────────────────
export const systemClient = {
  /** Le Cockpit interrogeait GET /health, qui est la sonde de vivacité
   *  héritée : elle renvoie `{"status": "ok", "uptime_seconds": …}` et rien
   *  d'autre. Le bandeau affichait donc « UNKNOWN » en permanence (le
   *  Cockpit compare à "HEALTHY") et n'avait aucun sous-système à lister.
   *  La vraie sonde agrégée est /system/health (34 services). Les deux sont
   *  interrogées : l'une pour le détail par sous-système, l'autre parce
   *  qu'elle seule expose l'uptime du processus. */
  health: async (): Promise<SystemHealth> => {
    const [agg, root] = await Promise.all([
      fetchJSON<SystemHealthWire>("/system/health"),
      fetchJSON<RootHealthWire>("/health").catch(() => ({} as RootHealthWire)),
    ]);
    const subsystems: SystemHealth["subsystems"] = {};
    for (const [name, info] of Object.entries(agg.detail ?? {})) {
      subsystems[name] = {
        status: normaliseStatus(info?.status),
        message: info?.detail,
      };
    }
    return {
      status: normaliseStatus(agg.status),
      version: "",
      uptime_seconds: root.uptime_seconds ?? 0,
      subsystems,
    };
  },
  /** /system/statistics renvoie `{services: {<clé>: {…}}}`, pas les champs
   *  plats (`missions_total`, `agents_active`…) que le type SystemStatistics
   *  déclare. Toutes ces lectures valaient donc `undefined`, et la barre
   *  d'état affichait « 0/0 » partout en permanence. On projette ici la
   *  charge utile réelle sur le type attendu ; `raw` reste exposé pour les
   *  Centers qui ont besoin du détail par service. */
  statistics: async (): Promise<SystemStatistics> => {
    const raw = await fetchJSON<Record<string, any>>("/system/statistics");
    const svc = (raw?.services ?? {}) as Record<string, any>;
    const sched = svc.execution_engine?.scheduler ?? {};
    const coord = svc.execution_engine?.coordinator ?? {};
    const sup = svc.agent_supervisor ?? {};
    const mem = svc.memory_manager ?? {};
    const num = (v: unknown) => (typeof v === "number" ? v : 0);

    return {
      missions_total: num(sched.total),
      missions_active: num(sched.running) + num(sched.pending),
      missions_completed: num(sched.completed),
      missions_failed: num(sched.failed),
      agents_total: num(sup.total_agents) || num(coord.agents_registered),
      agents_active: num(sup.busy),
      runtimes_total: num(svc.runtime_orchestrator?.known_runtimes),
      runtimes_healthy: num(coord.runtimes_available),
      memory_entries:
        num(mem.episodic?.total) +
        num(mem.semantic?.total) +
        num(mem.procedural?.total_procedures),
      raw,
    } as SystemStatistics;
  },
  // GET /version n'existe pas (404) : méthode retirée (P-002 §7).
};

// ── Missions ─────────────────────────────────────────
/** GET /api/v1/missions returns `mission_id` and a bare `progress` number
 *  (0-100); GET /api/v1/missions/{id} returns the same `mission_id` but a
 *  `progress` *object* (`{total, completed, progress_pct, ...}` — see
 *  backend/mission/dependency_resolver.py) plus `description`/`created_at`,
 *  which the list endpoint omits entirely. Every mission therefore had
 *  `id === undefined` (MissionCenter read `.id`, never `.mission_id`) —
 *  every row shared the same React key, and `.find(m => m.id === selected)`
 *  always matched the first mission regardless of which one was clicked.
 *  This normalises both shapes onto the one `Mission` type. */
function toMission(raw: Record<string, any>): Mission {
  const progress = raw.progress;
  const progressIsDetail = progress && typeof progress === "object";
  return {
    ...raw,
    id: raw.id ?? raw.mission_id,
    progress: progressIsDetail ? progress.progress_pct ?? 0 : progress ?? 0,
    node_count: progressIsDetail ? progress.total : raw.nodes,
    completed_nodes: progressIsDetail ? progress.completed : undefined,
  } as Mission;
}

export const missionsClient = {
  list: () =>
    fetchJSON<unknown>("/missions")
      .then((d) => unwrap<Record<string, any>>(d, "missions"))
      .then((rows) => rows.map(toMission)),
  get: (id: string) => fetchJSON<Record<string, any>>(`/missions/${id}`).then(toMission),
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
/** GET /api/v1/agents renvoie `agent_id`, `preferred_runtime` et
 *  `preferred_model` — pas `id`, `type` ni `runtime`. Chaque agent avait donc
 *  `id === undefined`, ce qui donnait dix clés React identiques (« Each child
 *  in a list should have a unique key ») et un `type` vide sous chaque nom
 *  dans le Dashboard. On projette ici la charge utile réelle sur le type
 *  Agent, en gardant les champs d'origine. */
function toAgent(raw: Record<string, any>): Agent {
  return {
    ...raw,
    id: raw.id ?? raw.agent_id ?? raw.name,
    name: raw.name ?? raw.agent_id ?? "(inconnu)",
    type: raw.type ?? raw.preferred_model ?? "",
    runtime: raw.runtime ?? raw.preferred_runtime ?? "",
    capabilities: Array.isArray(raw.capabilities) ? raw.capabilities : [],
  } as Agent;
}

export const agentsClient = {
  list: () =>
    fetchJSON<unknown>("/agents")
      .then((d) => unwrap<Record<string, any>>(d, "agents"))
      .then((rows) => rows.map(toAgent)),
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
    // {messages, total} envelope. Typed as a bare array, this crashed the Agent
    // Center on `messages.slice is not a function` — and because the crash
    // escaped the Center, it took the whole Cockpit shell down with it (R-004).
    return fetchJSON<unknown>(`/collaboration/messages${qs}`)
      .then((d) => unwrap<CollaborationMessage>(d, "messages"));
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
    return fetchJSON<unknown>(`/collaboration/history${qs}`)
      .then((d) => unwrap<CollaborationMessage>(d, "messages"));
  },
};

// ── Runtime ──────────────────────────────────────────
export const runtimeClient = {
  list: () => fetchJSON<unknown>("/runtimes").then((d) => unwrap<RuntimeInfo>(d, "runtimes")),
  get: (name: string) => fetchJSON<RuntimeInfo>(`/runtimes/${name}`),
  health: () => fetchJSON<Record<string, { status: string; latency_ms: number }>>("/runtimes/health"),
  metrics: () => fetchJSON<Record<string, unknown>>("/runtimes/metrics"),
  // `/runtime/resources/status` n'existe pas (404) : la route est
  // `/runtime/resources`. Le Runtime Center n'a donc jamais affiché la
  // moindre jauge de ressources — la requête échouait à chaque fois et le
  // garde `resources && …` masquait l'erreur en n'affichant rien.
  resources: () => fetchJSON<ResourceStatus>("/runtime/resources"),
  allocations: () => fetchJSON<Record<string, unknown>[]>("/runtime/resources/allocations"),
  release: (data: { resource_id: string }) =>
    fetchJSON<{ status: string }>("/runtime/resources/release", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // POST /runtime/select n'existe pas côté backend (404). La méthode a été
  // retirée plutôt que laissée à pointer dans le vide (P-002 §7).
};

// ── Memory ───────────────────────────────────────────
export const memoryClient = {
  search: (q: string, mode: "hybrid" | "graph" | "keyword" = "hybrid") =>
    fetchJSON<SearchResult[]>(`/memory/search?q=${encodeURIComponent(q)}&mode=${mode}`),
  searchAdvanced: (data: Record<string, unknown>) =>
    fetchJSON<unknown>("/memory/search", {
      method: "POST",
      body: JSON.stringify(data),
    }).then((d) => unwrap<SearchResult>(d, "results")),
  graph: (node_id?: string, depth?: number) => {
    const qs = new URLSearchParams();
    if (node_id) qs.set("node_id", node_id);
    if (depth) qs.set("depth", String(depth));
    return fetchJSON<KnowledgeGraph>(`/memory/graph?${qs}`);
  },
  experiences: () => fetchJSON<unknown>("/memory/experiences").then((d) => unwrap<Experience>(d, "recommendations")),
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
    // {skills, count, stats} envelope — the last of the query-string list
    // methods that a literal-path contract check could not reach (R-004).
    return fetchJSON<unknown>(`/skills${qs}`).then((d) => unwrap<Skill>(d, "skills"));
  },
  get: (id: string) => fetchJSON<Skill>(`/skills/${id}`),
  select: (data: { task_description: string; domain?: string }) =>
    fetchJSON<unknown>("/skills/select", {
      method: "POST",
      body: JSON.stringify(data),
    }).then((d) => unwrap<SkillSelection>(d, "selections")),
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
export interface ToolHealthSummary {
  total: number;
  healthy: number;
  degraded_or_unhealthy: number;
  avg_latency_ms: number;
}

export const toolsClient = {
  list: () => fetchJSON<unknown>("/tools").then((d) => unwrap<ToolDefinition>(d, "tools")),
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
  // An aggregate, not a per-tool list: the endpoint returns
  // {total, healthy, degraded_or_unhealthy, avg_latency_ms}. Typing it as
  // ToolHealth[] made tools-center call .map() on an object (R-003).
  health: () => fetchJSON<ToolHealthSummary>("/tools/health"),
  metrics: () => fetchJSON<Record<string, number>>("/tools/metrics"),
  mcpServers: () => fetchJSON<unknown>("/mcp/servers").then((d) => unwrap<MCPServer>(d, "servers")),
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
  rules: () => fetchJSON<unknown>("/policy/rules").then((d) => unwrap<PolicyRule>(d, "rules")),
  evaluate: (data: { operation: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<{ verdict: string; reason: string; rule_id?: string }>("/policy/evaluate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  approvals: () => fetchJSON<unknown>("/approval").then((d) => unwrap<ApprovalRequest>(d, "approvals")),
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
    // {entries, total} envelope. Typed as a bare array, `auditLog.slice(0, 30)`
    // in the Governance Center threw and took the whole shell down (R-004).
    return fetchJSON<unknown>(`/audit${qs}`)
      .then((d) => unwrap<AuditEntry>(d, "entries"));
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
    // /api/v1/events does not exist — it 404s. The event log lives at
    // /api/v1/runtime/events and answers {events, total, runtime_id} (R-004).
    return fetchJSON<unknown>(`/runtime/events${qs}`)
      .then((d) => unwrap<SystemEvent>(d, "events"));
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
  // The endpoint wraps the payload in a "status" envelope, exactly like
  // /klaatcode/status does. This was typed as the bare inner object, so
  // every field read off it was undefined at runtime (R-002 P3).
  status: () => fetchJSON<{ status: OhMyPiStatus }>("/ohmypi/status"),
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

// ── Evolution (R-001: real endpoints, no client-side mocks) ─────────
//
// The Evolution Center used to render module-level MOCK_PROPOSALS /
// MOCK_REPORTS constants, so its counters were fabricated in the browser no
// matter what the backend said. These call the real /api/v1/evolution routes.

export interface EvolutionProposalDTO {
  proposal_id: string;
  evolution_type: string;
  target_component: string;
  description: string;
  expected_gain: number;
  risk_level: string;
  confidence: number;
  status: string;
}

export interface EvolutionReportDTO {
  report_id: string;
  improvements_found: number;
  applied_changes: string[];
  rejected_changes: string[];
  total_gain_percent: number;
}

export const evolutionClient = {
  status: () => fetchJSON<Record<string, unknown>>("/evolution/status"),
  proposals: (status?: string) =>
    fetchJSON<EvolutionProposalDTO[]>(
      status ? `/evolution/proposals?status=${encodeURIComponent(status)}` : "/evolution/proposals",
    ),
  reports: (limit = 10) => fetchJSON<EvolutionReportDTO[]>(`/evolution/reports?limit=${limit}`),
  approve: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/approve/${id}`, { method: "POST" }),
  apply: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/apply/${id}`, { method: "POST" }),
  // POST /evolution/simulate/{id} existe côté backend et n'avait aucun appelant.
  simulate: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/simulate/${id}`, { method: "POST" }),
  analyze: () =>
    fetchJSON<Record<string, unknown>>("/evolution/analyze", { method: "POST" }),
};

// ── Security & System (RC3: these Centers had no data source at all) ──
//
// security-center.tsx imported only useState and rendered MOCK_STATUS /
// MOCK_TRUST_SCORES — 42 permissions, trust scores of 94.2/88.5/82.1 — all
// invented in the browser while /api/v1/security/status returned real values.
// system-center.tsx was the same.

export interface SecurityStatusDTO {
  permissions: { total_permissions: number; total_policies: number; history_entries?: number };
  trust: {
    total_agents: number;
    average_score: number;
    by_level: Record<string, number>;
    total_violations?: number;
    total_approvals?: number;
  };
  threats?: Record<string, unknown>;
  isolation?: Record<string, unknown>;
}

export const securityClient = {
  status: () => fetchJSON<SecurityStatusDTO>("/security/status"),
  policies: () => fetchJSON<Record<string, unknown>[]>("/security/policies"),
  threats: (limit = 50) => fetchJSON<Record<string, unknown>[]>(`/security/threats?limit=${limit}`),
  events: (limit = 100) => fetchJSON<Record<string, unknown>[]>(`/security/events?limit=${limit}`),
  trust: (agentId: string) => fetchJSON<Record<string, unknown>>(`/security/trust/${agentId}`),
};

export interface SubsystemHealthDTO {
  status: string;
  services: number;
  by_status: Record<string, number>;
  unhealthy: string[];
  silent: string[];
  detail: Record<string, { status: string; detail?: string }>;
}

export const subsystemClient = {
  health: () => fetchJSON<SubsystemHealthDTO>("/system/health"),
  ready: () => fetchJSON<Record<string, unknown>>("/system/ready"),
  statistics: () => fetchJSON<Record<string, unknown>>("/system/statistics"),
  assembly: () => fetchJSON<Record<string, unknown>>("/system/assembly"),
  dependencies: () => fetchJSON<Record<string, unknown>>("/system/dependencies"),
};

// ── Autonomous (HOS-063) ──────────────────────────────────
// The Autonomous Center rendered module-level MOCK_GOAL / MOCK_SESSION /
// MOCK_DECISIONS / MOCK_TIMELINE constants — a fabricated goal, a fabricated
// session on a "ktransformers" runtime and four invented decisions — while this
// API was fully working and doing real inference. There was no client at all
// for the most capable surface Hermes has (R-002 P3).

export interface AutonomousGoalDTO {
  goal_id: string;
  user_request: string;
  interpreted_goal: string;
  status: string;
  domain: string;
  language: string;
  complexity: number;
  priority: string;
  estimated_duration_s: number;
  // Project binding (HOS-067) — empty strings when the goal isn't bound to
  // a specific local checkout or GitHub repository.
  local_path: string;
  repository: string;
  branch: string;
  // Real prior-experience summary gathered before planning (HOS-067) —
  // empty on a fresh deployment with no mission history yet.
  knowledge_context: string;
  created_at: string;
}

export interface AutonomousDecisionDTO {
  decision_id: string;
  decision_type: string;
  reason: string;
  confidence: number;
  alternatives_count: number;
  selected: string;
  context: Record<string, unknown>;
  timestamp: string;
}

export interface AutonomousReportDTO {
  goal_id: string;
  user_request: string;
  interpreted_goal: string;
  execution_summary: string;
  results: Record<string, unknown>;
  improvements: string[];
  lessons: string[];
  decisions: AutonomousDecisionDTO[];
  total_duration_ms: number;
  agents_used: string[];
  runtimes_used: string[];
  tools_used: string[];
  success: boolean;
}

export interface AutonomousTimelineDTO {
  goal_id: string;
  status: string;
  timeline: { event: string; timestamp: number; decisions: string[] }[];
}

export interface AutonomousStatusDTO {
  total_goals: number;
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
  total_executions: number;
  active_sessions: number;
  interpreter: { history: number };
  decisions: {
    total_decisions: number;
    by_type: Record<string, number>;
    avg_confidence: number;
  };
  guard: {
    total_blocked: number;
    security_connected: boolean;
    policy_connected: boolean;
  };
  memory_loop: { missions: number; success_rate: number; total_lessons: number };
}

export const autonomousClient = {
  status: () => fetchJSON<AutonomousStatusDTO>("/autonomous/status"),
  start: (userRequest: string, context?: Record<string, unknown>) =>
    fetchJSON<AutonomousGoalDTO>("/autonomous/start", {
      method: "POST",
      body: JSON.stringify({ user_request: userRequest, context: context ?? {} }),
    }),
  goal: (goalId: string) =>
    fetchJSON<AutonomousGoalDTO>(`/autonomous/${goalId}`),
  report: (goalId: string) =>
    fetchJSON<AutonomousReportDTO>(`/autonomous/${goalId}/report`),
  timeline: (goalId: string) =>
    fetchJSON<AutonomousTimelineDTO>(`/autonomous/${goalId}/timeline`),
  pause: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/pause`, {
      method: "POST",
    }),
  resume: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/resume`, {
      method: "POST",
    }),
  cancel: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/cancel`, {
      method: "POST",
    }),
};

// ── Model Intelligence (HOS-060) ──────────────────────────
// model-intelligence-center.tsx rendered MOCK_MODELS and MOCK_DECISIONS while
// these endpoints served six real models and real routing decisions.

export interface ModelIntelligenceDTO {
  success: boolean;
  data: {
    total_models: number;
    total_runs: number;
    average_success_rate: number;
    models: Record<string, unknown>[];
  };
}

export interface ModelRankingEntryDTO {
  model_id: string;
  name: string;
  score: number;
  parameters_b: number;
  vram_mb: number;
  tps: number;
  success_rate: number;
  tags: string[];
}

export interface ModelDecisionDTO {
  model_id: string;
  model_name: string;
  runtime: string;
  quantization: string;
  confidence: number;
  reason: string;
  estimated_latency_ms: number;
  estimated_tps: number;
  estimated_vram_mb: number;
  alternatives: { model_id: string; name: string; score: number; reason: string }[];
}

// OpenRouter free-model cloud escalation (HOS-066C) — read-only status:
// whether a key is configured, whether Aegis authorizes it *right now* at
// the current autonomy level, and the real cached catalogue/quota state.
export interface CloudStatusDTO {
  success: boolean;
  configured: boolean;
  authorized: boolean;
  message: string;
  catalog_size?: number;
  catalog_age_s?: number | null;
  quota_remaining?: number | null;
  quota_checked_age_s?: number | null;
  reserve_daily_requests?: number;
}

export const modelIntelligenceClient = {
  models: () => fetchJSON<ModelIntelligenceDTO>("/models"),
  ranking: () =>
    fetchJSON<{ success: boolean; models: ModelRankingEntryDTO[] }>("/models/ranking"),
  performance: () => fetchJSON<ModelIntelligenceDTO>("/models/performance"),
  history: (limit = 50) =>
    fetchJSON<Record<string, unknown>>(`/models/history?limit=${limit}`),
  benchmarks: () => fetchJSON<Record<string, unknown>>("/models/benchmarks"),
  recommend: (payload: { task_type: string; description: string }) =>
    fetchJSON<{ success: boolean; decision: ModelDecisionDTO }>("/models/recommend", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cloudStatus: () => fetchJSON<CloudStatusDTO>("/models/cloud/status"),
};

// ── Conversation (HOS-062) ────────────────────────────────
// conversation-center.tsx held a module-level `mockSessionId` built from
// Math.random(), a generateMockResponse() that keyword-matched the user's text
// to canned French replies with invented confidence scores, and fake 800–1400 ms
// delays to look like thinking. /api/v1/conversation performs real intent
// classification and real approval gating (R-002 P3).

export interface ConversationIntentDTO {
  type: string;
  confidence: number;
  domain: string;
}

export interface ConversationReplyDTO {
  success: boolean;
  session_id: string;
  message: { role: string; content: string; timestamp: string };
  intent: ConversationIntentDTO | null;
  requires_approval: boolean;
  approval_request: { action: string; risk: string; description: string } | null;
  suggested_actions?: { label: string; action: string }[];
  status: string;
}

export interface ConversationSessionDTO {
  success: boolean;
  session_id: string;
  messages: {
    role: string;
    content: string;
    timestamp: string;
    agent_id?: string;
    mission_id?: string;
  }[];
}

export const conversationClient = {
  start: (userRequest?: string) =>
    fetchJSON<{ success: boolean; session_id: string; status: string }>(
      "/conversation/start",
      { method: "POST", body: JSON.stringify({ user_request: userRequest ?? "" }) },
    ),
  sessions: () =>
    fetchJSON<{ success: boolean; sessions: unknown[]; total: number }>(
      "/conversation/sessions",
    ),
  session: (sessionId: string) =>
    fetchJSON<ConversationSessionDTO>(`/conversation/${sessionId}`),
  message: (sessionId: string, message: string) =>
    fetchJSON<ConversationReplyDTO>("/conversation/message", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),
  approve: (sessionId: string) =>
    fetchJSON<ConversationReplyDTO>(`/conversation/${sessionId}/approve`, {
      method: "POST",
    }),
  cancel: (sessionId: string) =>
    fetchJSON<ConversationReplyDTO>(`/conversation/${sessionId}/cancel`, {
      method: "POST",
    }),
};

// ── Workspace (P-001) ─────────────────────────────────────
// Le backend expose la création, le verrouillage, la libération et la
// suppression d'espaces de travail depuis HOS-047 ; aucun écran ne les
// atteignait.

export interface WorkspaceDTO {
  workspace_id: string;
  mission_id?: string;
  agent_id?: string;
  status?: string;
  path?: string;
  locked?: boolean;
  created_at?: string;
}

export const workspaceClient = {
  list: () =>
    fetchJSON<unknown>("/workspace").then((d) => unwrap<WorkspaceDTO>(d, "workspaces")),
  get: (id: string) => fetchJSON<WorkspaceDTO>(`/workspace/${id}`),
  status: (id: string) => fetchJSON<Record<string, unknown>>(`/workspace/${id}/status`),
  artifacts: (id: string) =>
    fetchJSON<unknown>(`/workspace/${id}/artifacts`).then((d) =>
      unwrap<Record<string, unknown>>(d, "artifacts")),
  create: (data: Record<string, unknown>) =>
    fetchJSON<WorkspaceDTO>("/workspace", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  lock: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}/lock`, { method: "POST" }),
  release: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}/release`, { method: "POST" }),
  remove: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}`, { method: "DELETE" }),
};

// ── Verification ──────────────────────────────────────────
// Ces routes vivaient hors de /api/v1 et exigeaient une base secondaire.
// P-002 les republie sous le namespace canonique : le client n'a plus qu'une
// seule racine, comme tous les autres.

export interface VerificationRunnerDTO {
  name: string;
  kind: string;
  description: string;
}

export interface VerificationRunRequest {
  repo_path: string;
  runner: string;
  timeout?: number;
  project_id?: string;
}

export interface VerificationRunResult {
  ran: boolean;
  runner: string;
  kind: string;
  passed: boolean;
  exit_code: number | null;
  timed_out: boolean;
  verdict: string;
  reason: string;
  duration_seconds: number;
  output: string;
}

export const verificationClient = {
  runners: () =>
    fetchJSON<unknown>("/verification/runners").then((d) =>
      Array.isArray(d) ? (d as VerificationRunnerDTO[]) : []),
  // POST /verification/run — its payload *is* documented (VerificationRunRequest
  // in backend/api/routes/verification.py, visible at GET /openapi.json), unlike
  // what ValidationCenter used to claim. At the shipped autonomy_level of "low"
  // Aegis will refuse most calls (verdict != "allow", ran=false) — that refusal
  // is the real, honest answer, not a reason to hide the trigger.
  run: (data: VerificationRunRequest) =>
    fetchJSON<VerificationRunResult>("/verification/run", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Monitoring (P-001) ────────────────────────────────────

export const monitoringClient = {
  resources: () => fetchJSON<ResourceStatus>("/runtime/resources"),
  allocations: () =>
    fetchJSON<unknown>("/runtime/resources/allocations").then((d) =>
      unwrap<Record<string, unknown>>(d, "allocations")),
  runtimeEvents: (limit = 50) =>
    fetchJSON<unknown>(`/runtime/events?limit=${limit}`).then((d) =>
      unwrap<Record<string, unknown>>(d, "events")),
  intelligenceScores: () => fetchJSON<Record<string, unknown>>("/runtime/intelligence/scores"),
  recommendations: () =>
    fetchJSON<Record<string, unknown>>("/runtime/intelligence/recommendations"),
  executionStatistics: () => fetchJSON<Record<string, unknown>>("/execution/statistics"),
};
