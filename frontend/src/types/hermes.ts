// ── Runtime ──────────────────────────────────────────
/** GET /api/v1/runtimes renvoie :
 *  `{name, runtime_name, version, capabilities[], healthy, status, is_active,
 *    is_fallback, metrics, health}` — `status` vaut `"started"`/`"stopped"`
 *  (cycle de vie du runtime), pas `"AVAILABLE"`. `metrics`/`health` (HOS-072)
 *  sont `null` tant qu'aucune tâche réelle n'est passée par ce runtime — un
 *  runtime jamais utilisé est non mesuré, pas mesuré à zéro. Champs alignés
 *  sur ce que RuntimeHealthMonitor (backend/ral/runtime_health.py) sait
 *  réellement calculer — pas de avg_tokens_per_sec/circuit_breaker
 *  fabriqués, ces concepts n'existent pas côté backend. */
export interface RuntimeInfo {
  name: string;
  status: RuntimeStatus;
  type?: string;
  runtime_name?: string;
  version?: string;
  capabilities?: string[];
  healthy?: boolean;
  is_active?: boolean;
  is_fallback?: boolean;
  health?: RuntimeHealth | null;
  metrics?: RuntimeMetrics | null;
}

export type RuntimeStatus =
  | "AVAILABLE" | "DEGRADED" | "UNAVAILABLE"
  | "started" | "stopped" | "starting" | "error";

export interface RuntimeHealth {
  status: RuntimeStatus;
  last_check: string | null;
  latency_ms: number;
}

export interface RuntimeMetrics {
  total_executions: number;
  success_count: number;
  failure_count: number;
  avg_latency_ms: number;
  reliability: number;
}

export interface RuntimeDecision {
  runtime: string;
  score: number;
  factors: Record<string, number>;
  justification: string;
}

// Mirrors what GET /api/v1/runtime/resources actually returns. The previous
// shape (cpu_percent, ram_total_gb, vram_total_gb, gpu_name...) matched none of
// the response fields, so every consumer silently read `undefined` and fell back
// to zero rather than failing (R-002 P3).
export interface ResourceStatus {
  gpu: {
    name: string;
    vendor: string;
    vram_total_bytes: number;
    vram_used_bytes: number;
    vram_free_bytes: number;
    temperature_celsius: number | null;
    utilization_pct: number | null;
    available: boolean;
  };
  ram: {
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
    usage_pct: number;
    status: string;
  };
  allocations: number;
  allocated_bytes: number;
}

// ── Mission ──────────────────────────────────────────
export interface Mission {
  id: string;
  title: string;
  // GET /missions (list) sends neither — only GET /missions/{id} does.
  description?: string;
  objective?: string;
  status: MissionStatus;
  priority?: MissionPriority;
  type?: MissionType;
  progress: number;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  estimated_duration_s?: number;
  node_count?: number;
  completed_nodes?: number;
  // Project binding (HOS-068) — only GET /missions/{id} sends these, like
  // description above.
  local_path?: string;
  repository?: string;
  branch?: string;
  // Workspace/Filesystem tool layer (HOS-084) — binds the mission to a
  // validated Project so RealTaskExecutor's tool-calling loop can offer
  // workspace_list/read/write to its tasks. Independent of local_path
  // above (HOS-068's older Aegis pre-flight binding); a mission can carry
  // either, both, or neither.
  project_id?: string;
  // True when the real (LLM) task decomposition failed and this mission
  // ran a generic, request-independent template instead — see
  // TaskDecomposer.decompose_with_method. Sent by both the list and detail
  // endpoints.
  plan_is_generic?: boolean;
  decomposition_method?: string;
}

// Mirrors backend/mission/mission_models.py's MissionReport.to_dict().
export interface MissionReport {
  mission_id: string;
  title: string;
  objective: string;
  status: string;
  summary: string;
  success: boolean;
  total_duration_ms: number;
  tasks_total: number;
  tasks_completed: number;
  tasks_failed: number;
  runtimes_used: string[];
  outputs: Array<{ task: string; chars: number; content: string }>;
  errors: string[];
  generated_at: string;
  decomposition_method?: string;
  plan_is_generic?: boolean;
  /** Ce que le disque dit, par opposition à ce que la mission rapporte.
   *
   * `null` signifie « pas de vérification » — une mission sans workspace
   * lié n'a rien à comparer — et jamais « vérification réussie ». Les
   * confondre à l'affichage recréerait le faux positif que HOS-092 existe
   * pour détecter. */
  verification?: {
    contradicted?: boolean;
    files_changed?: number;
    workspace?: string;
    [k: string]: unknown;
  } | null;
}

// Mirrors backend/mission/mission_models.py's MissionStatus values
// (uppercased — see toMission() in services/client.ts, which is the only
// place the lowercase wire value ever gets normalized).
export type MissionStatus =
  | "CREATED"
  | "PLANNING"
  | "READY"
  | "RUNNING"
  | "PAUSED"
  | "WAITING_APPROVAL"
  | "VALIDATED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type MissionPriority = "CRITICAL" | "HIGH" | "NORMAL" | "LOW";

export type MissionType = "CODE_GENERATION" | "BUG_FIX" | "REFACTORING" | "DOCUMENTATION" | "TESTING" | "DEPLOYMENT" | "CUSTOM";

export interface MissionNode {
  id: string;
  mission_id: string;
  title: string;
  description: string;
  type: string;
  status: MissionStatus;
  priority: MissionPriority;
  dependencies: string[];
  dependents: string[];
  agent_id?: string;
  runtime_id?: string;
  estimated_duration_s?: number;
  actual_duration_s?: number;
}

export interface MissionEdge {
  from: string;
  to: string;
}

/** Ce que `GET /missions/{id}/graph` renvoie **réellement**.
 *
 * `MissionGraph` déclarait `MissionNode[]` et `MissionEdge[]`, qui
 * décrivent une autre forme : le nœud du graphe n'a ni `priority`, ni
 * `dependencies`, ni `actual_duration_s`, et les arêtes sont
 * `{source, target}` et non `{from, to}`. Un type qui ment sur sa charge
 * utile est pire qu'un type absent — il donne à celui qui s'y fie
 * l'assurance de champs qui n'arriveront jamais, ce qui explique
 * vraisemblablement pourquoi cette vue n'avait jamais été construite
 * (HOS-116).
 *
 * Vérifié contre `GraphExecutor.get_graph_data`. */
export interface MissionGraphNode {
  id: string;
  title: string;
  status: string;
  type: string;
  /** Mesuré par l'exécuteur, pas estimé — 0 quand le nœud n'a pas tourné. */
  duration_ms: number;
  /** Le runtime qui a réellement servi le nœud, écrit après exécution. */
  runtime?: string;
  result_summary?: string;
  depends_on: string[];
}

export interface MissionGraphEdge {
  source: string;
  target: string;
}

export interface MissionGraph {
  mission_id?: string;
  nodes: MissionGraphNode[];
  edges: MissionGraphEdge[];
  topological_order?: string[];
  /** Les nœuds qui peuvent tourner en parallèle, par vague. */
  parallel_groups?: string[][];
  progress?: Record<string, number>;
}

export interface MissionTimeline {
  id: string;
  mission_id: string;
  events: TimelineEvent[];
}

export interface TimelineEvent {
  timestamp: string;
  type: string;
  node_id?: string;
  agent_id?: string;
  description: string;
  duration_ms?: number;
}

// ── Agent ────────────────────────────────────────────
/** Forme normalisée par agentsClient (voir `toAgent`) : le backend expose
 *  `agent_id` / `preferred_runtime` / `preferred_model`. `metrics` et
 *  `created_at` ne figurent pas dans la réponse de liste — déclarés
 *  facultatifs plutôt que requis, pour que le compilateur cesse de garantir
 *  des champs absents à l'exécution. */
export interface Agent {
  id: string;
  name: string;
  type: string;
  status: AgentStatus;
  capabilities: string[];
  current_mission?: string;
  current_task?: string;
  current_task_id?: string;
  current_mission_id?: string;
  runtime?: string;
  preferred_runtime?: string;
  preferred_model?: string;
  success_rate?: number;
  total_tasks?: number;
  successful_tasks?: number;
  failed_tasks?: number;
  // Real per-agent trust score (HOS-070) — AgentTrustEngine, fed by real
  // task outcomes. null when no trust engine is wired (never fabricated).
  trust_score?: number | null;
  trust_level?: string | null;
  metrics?: AgentMetrics;
  created_at?: string;
  last_active_at?: string;
}

// Mirrors backend/agents/agent_models.py's AgentStatus values (uppercased
// — see toAgent() in services/client.ts, the only place the lowercase wire
// value is normalized). "ERROR" never existed on the backend; real values
// are CREATED/STARTING/READY/BUSY/PAUSED/COMPLETED/FAILED/STOPPING/
// STOPPED/RECOVERING — every status-keyed lookup against the old "ERROR"
// silently missed for every agent that ever actually failed.
export type AgentStatus =
  | "CREATED"
  | "STARTING"
  | "READY"
  | "BUSY"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "STOPPING"
  | "STOPPED"
  | "RECOVERING";

export interface AgentMetrics {
  tasks_completed: number;
  tasks_failed: number;
  total_duration_s: number;
  avg_duration_s: number;
  success_rate: number;
  tokens_consumed: number;
}

export interface AgentCapability {
  name: string;
  category: string;
  proficiency: number;
}

export interface CollaborationMessage {
  id: string;
  from_agent: string;
  to_agent?: string;
  mission_id?: string;
  type: "DIRECT" | "BROADCAST" | "HELP_REQUEST" | "DELEGATION" | "REVIEW" | "CONSENSUS";
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface Delegation {
  id: string;
  from_agent: string;
  to_agent: string;
  task_title: string;
  status: "PENDING" | "ACCEPTED" | "REJECTED" | "COMPLETED";
  created_at: string;
  completed_at?: string;
}

// ── Memory ───────────────────────────────────────────
export interface MemoryEntry {
  id: string;
  type: MemoryType;
  scope: MemoryScope;
  content: string;
  tags: string[];
  created_at: string;
  last_accessed_at?: string;
  ttl?: number;
  metadata?: Record<string, unknown>;
}

export type MemoryType = "EPISODIC" | "SEMANTIC" | "PROCEDURAL" | "DOCUMENT" | "WORKING";

export type MemoryScope = "SESSION" | "MISSION" | "AGENT" | "PROJECT" | "USER" | "GLOBAL" | "EXPERIENCE";

export interface KnowledgeNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface KnowledgeEdge {
  from: string;
  to: string;
  type: string;
  weight?: number;
}

export interface KnowledgeGraph {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

export interface Experience {
  id: string;
  mission_id: string;
  pattern: string;
  success: boolean;
  confidence: number;
  learnings: string[];
  created_at: string;
}

export interface SearchResult {
  entry: MemoryEntry;
  score: number;
  justification: string;
}

// ── Skills ───────────────────────────────────────────
export interface Skill {
  id: string;
  name: string;
  version: string;
  category: string;
  domain: string;
  description: string;
  tags: string[];
  dependencies: string[];
  status: SkillStatus;
  metrics: SkillMetrics;
}

export type SkillStatus = "REGISTERED" | "LOADED" | "ACTIVE" | "DEPRECATED";

export interface SkillMetrics {
  load_count: number;
  success_rate: number;
  avg_load_time_ms: number;
  memory_mb: number;
  tokens_consumed: number;
  failure_rate: number;
}

export interface SkillSelection {
  skill_id: string;
  skill_name: string;
  score: number;
  justification: string;
}

export interface SkillDistribution {
  agent_id: string;
  skills: SkillSelection[];
  mission_id: string;
}

// ── Tools ────────────────────────────────────────────
export interface ToolDefinition {
  id: string;
  name: string;
  type: ToolType;
  version: string;
  description: string;
  permissions: string[];
  category: string;
  status: ToolStatus;
}

export type ToolType = "GITHUB" | "GITLAB" | "DOCKER" | "DATABASE" | "FILESYSTEM" | "REST_API" | "BROWSER" | "MCP";

export type ToolStatus = "AVAILABLE" | "IN_USE" | "ERROR" | "DISABLED";

export interface ToolExecution {
  id: string;
  tool_id: string;
  tool_name: string;
  agent_id: string;
  mission_id: string;
  status: "SUCCESS" | "FAILURE" | "TIMEOUT" | "CANCELLED" | "PERMISSION_DENIED";
  duration_ms: number;
  created_at: string;
  error?: string;
}

export interface ToolHealth {
  tool_id: string;
  status: ToolStatus;
  last_check: string;
  latency_ms: number;
  error_count: number;
  success_rate: number;
}

export interface MCPServer {
  id: string;
  name: string;
  transport: "STDIO" | "SSE" | "HTTP";
  status: "CONNECTED" | "DISCONNECTED" | "ERROR";
  tool_count: number;
  connected_at?: string;
}

// ── Governance ───────────────────────────────────────
// Aligné sur ce que /api/v1/policy/rules renvoie réellement :
// {id, name, category, decision, enabled, priority}. Le type déclarait `action`
// et `description`, deux champs que l'endpoint n'a jamais envoyés (P-001).
export interface PolicyRule {
  id: string;
  name: string;
  category: string;
  decision: string;
  enabled: boolean;
  priority: number;
  description?: string;
}

export interface ApprovalRequest {
  id: string;
  operation: string;
  requested_by: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  priority: "CRITICAL" | "HIGH" | "NORMAL" | "LOW";
  created_at: string;
  expires_at?: string;
  resolved_at?: string;
  resolved_by?: string;
  comment?: string;
  metadata?: Record<string, unknown>;
}

export interface AuditEntry {
  id: string;
  operation: string;
  principal: string;
  result: "ALLOWED" | "DENIED" | "APPROVED" | "REJECTED";
  duration_ms: number;
  created_at: string;
  metadata?: Record<string, unknown>;
}

// ── Events ───────────────────────────────────────────
export interface SystemEvent {
  id: string;
  type: string;
  source: string;
  severity: EventSeverity;
  payload: Record<string, unknown>;
  timestamp: string;
  correlation_id?: string;
}

export type EventSeverity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";

// ── Execution ────────────────────────────────────────
// Mirrors backend/execution/execution_controller.py's ExecutionController.get()
// (HOS-069) — one row per real task execution (a mission node, or a legacy
// /execution/start call), not per mission. The previous shape here
// (id/status/current_node/progress/checkpoints) never matched what the
// backend actually returns and was never exercised against it.
export interface ExecutionSummary {
  execution_id: string;
  state: string; // created|planning|ready|running|waiting_approval|paused|validating|completed|failed|cancelled
  mission_id: string;
  user_goal: string;
  is_terminal: boolean;
  is_active: boolean;
  report?: {
    total_tasks: number;
    completed_tasks: number;
    failed_tasks: number;
    duration_ms: number;
    agents_used: string[];
    runtimes_used: string[];
    errors: string[];
  };
}

export interface ExecutionStatistics {
  active_executions: number;
  completed_executions: number;
  total_executions: number;
  executor_stats: {
    scheduler?: { total: number; completed: number; failed: number; running: number; pending: number; percent: number };
    coordinator?: { agents_registered: number; runtimes_available: number; active_assignments: number };
    validator?: { total_validated: number; outcomes: Record<string, number> };
    events_published?: number;
  };
}

export interface Checkpoint {
  id: string;
  timestamp: string;
  status: MissionStatus;
  node_id?: string;
  snapshot: Record<string, unknown>;
}

// ── System ───────────────────────────────────────────
/** Forme *normalisée* par systemClient.health(), pas la charge utile brute :
 *  /api/v1/system/health renvoie des statuts en minuscules sous `detail`, et
 *  ni version ni uptime. Voir la normalisation dans services/client.ts. */
export interface SystemHealth {
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY";
  version: string;
  uptime_seconds: number;
  subsystems: Record<string, SubsystemHealth>;
}

// NOT_INSTRUMENTED is real, distinct backend information (the `silent` array
// in GET /system/health) — a subsystem with no telemetry accessor wired yet,
// not one reporting a bad state. Collapsing it into DEGRADED (as this type
// used to) makes an architectural gap look like an incident; see
// services/client.ts's health() and dashboard-view.tsx's subsystem census.
export interface SubsystemHealth {
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "NOT_INSTRUMENTED";
  message?: string;
  latency_ms?: number;
}

/** Projection à plat produite par systemClient.statistics(). Le backend
 *  renvoie `{services: {…}}` par sous-système ; `raw` conserve cette charge
 *  utile intacte pour les Centers (Validation, Monitoring, Deployment…) qui
 *  lisent un service précis plutôt que les agrégats. */
export interface SystemStatistics {
  missions_total: number;
  missions_active: number;
  missions_completed: number;
  missions_failed: number;
  agents_total: number;
  agents_active: number;
  runtimes_total: number;
  runtimes_healthy: number;
  memory_entries: number;
  skills_registered?: number;
  skills_loaded?: number;
  events_total?: number;
  tools_available?: number;
  raw?: Record<string, unknown>;
}

export interface WebSocketEvent {
  type: string;
  source: string;
  severity: EventSeverity;
  payload: Record<string, unknown>;
  timestamp: string;
  correlation_id?: string;
}

// ── Alexandrie ───────────────────────────────────────
export interface AlexandrieStatus {
  alexandrie_health: { healthy: boolean; error?: string; latency_ms?: number };
  documents_synced: number;
  documents_indexed: number;
  graph_edges: number;
  cache: { entries: number; hit_rate: number };
  circuit_breaker: { open: boolean; failures: number };
  last_sync_at: string | null;
  events_count: number;
}

export interface AlexandrieDocument {
  id: string;
  title: string;
  content: string;
  node_type: string;
  parent_id: string | null;
  owner_id: string;
  is_public: boolean;
  version: number;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface AlexandrieSearchResults {
  query: string;
  mode: string;
  total: number;
  took_ms?: number;
  results: AlexandrieMergeResult[];
}

export interface AlexandrieMergeResult {
  source: "alexandrie" | "hermes";
  id: string;
  title: string;
  content: string;
  score: number;
  match_type: "full_text" | "semantic";
}

export interface AlexandrieSyncHistory {
  events: { type: string; doc_id: string; status: string; timestamp: string }[];
}

export interface AlexandrieSyncResult {
  synced: number;
  failed: number;
  error?: string;
}

export interface AlexandrieGraphEdges {
  total: number;
  edges: { source: string; target: string; relation: string; weight?: number }[];
}

export interface AlexandrieMissionDocs {
  mission_id: string;
  documents: { id: string; title: string; status: string }[];
}

// ── Oh My Pi (HOS-055B/C) ────────────────────────────
export interface OhMyPiStatus {
  installed: boolean;
  version: string | null;
  server_bound: boolean;
  lsp_available: boolean;
  dap_available: boolean;
  tools_count: number;
  capabilities: string[];
  client_stats: {
    total_executions: number;
    success_count: number;
    failure_count: number;
    timeout_count: number;
    success_rate: number;
    avg_duration_ms: number;
    installed: boolean;
    version: string | null;
  };
}

// Mirrors what /api/v1/ohmypi/capabilities actually returns. This used to
// declare category / requires_workspace / requires_sandbox — three fields the
// endpoint has never sent — and omit requires_lsp, which it does send. The
// panel's fabricated MOCK_CAPABILITIES satisfied the wrong shape, so nothing
// ever surfaced the drift (RC3 P8).
export interface OhMyPiCapability {
  name: string;
  description: string;
  inputs: string[];
  requires_lsp: boolean;
}

export interface OhMyPiExecutionResult {
  id: string;
  action: string;
  status: string;
  data: unknown;
  error: string;
  duration_ms: number;
  success: boolean;
  timestamp: string;
}

export interface LSPDiagnostic {
  file_path: string;
  severity: string;
  line: number;
  column: number;
  message: string;
  source: string;
}

export interface LSPSymbol {
  name: string;
  kind: string;
  file_path: string;
  line: number;
  column: number;
  signature: string;
}

export interface DebugSession {
  session_id: string;
  file: string;
  status: string;
  breakpoints: { file: string; line: number; condition?: string }[];
  created_at: string;
  completed_at: string | null;
  incidents: number;
}

// ── KlaatCode (HOS-054B) ────────────────────────────
export interface KlaatCodeStatus {
  status: {
    installed: boolean;
    version: string | null;
    tools_count: number;
    capabilities: string[];
    client_stats: {
      total_executions: number;
      success_count: number;
      failure_count: number;
      timeout_count: number;
      success_rate: number;
      avg_duration_ms: number;
      installed: boolean;
      version: string | null;
    };
    server_bound: boolean;
  };
  tools: number;
  capabilities: number;
}

export interface KlaatCodeCapability {
  name: string;
  description: string;
  inputs: string[];
  outputs: string[];
  requires_git: boolean;
  requires_project: boolean;
}

export interface KlaatCodeExecutionResult {
  id: string;
  request_id: string;
  status: string;
  data: unknown;
  error: string;
  duration_ms: number;
  timestamp: string;
  success: boolean;
}

// ── Code Intelligence (R-006) ─────────────────────────
// /api/v1/code-intelligence/* — CodeIntelligenceAgent/Router really wired
// in, replacing the fabricated client-side routing decision the Center used
// to compute (R-002). See backend/api/routes/code_intelligence.py.

export interface CodeIntelligenceProviderStatsDTO {
  total_executions: number;
  success_count: number;
  failure_count: number;
  timeout_count: number;
  success_rate: number;
  avg_duration_ms: number;
  installed: boolean;
  version: string | null;
}

export interface CodeIntelligenceStatusDTO {
  agent_id: string;
  name: string;
  status: string;
  op_status: string;
  is_available: boolean;
  capabilities: string[];
  providers: string[];
  total_tasks: number;
  successful_tasks: number;
  failed_tasks: number;
  klaatcode_tasks: number;
  ohmypi_tasks: number;
  hermes_native_tasks: number;
  hybrid_tasks: number;
  /** Already 0-100 — CodeIntelligenceAgent.success_rate, unlike the raw
   *  0-1 fraction klaatcode/ohmypi client_stats.success_rate carry. */
  success_rate: number;
  router_stats: {
    klaatcode: { total: number; success_count: number; success_rate: number };
    ohmypi: { total: number; success_count: number; success_rate: number };
    hermes_native: { total: number; success_count: number; success_rate: number };
    total_executions: number;
  };
  current_task_id: string;
}

export interface CodeIntelligenceCapabilitiesDTO {
  capabilities: string[];
  providers: string[];
  task_types: string[];
}

export type MCPStatusValue = "connected" | "disconnected" | "unbound" | "unavailable" | "not_configured";

export interface CodeIntelligenceExternalProviderStatusDTO {
  installed: boolean;
  version: string | null;
  tools_count: number;
  capabilities: string[];
  client_stats: CodeIntelligenceProviderStatsDTO;
  server_bound: boolean;
  mcp_status: MCPStatusValue;
}

export interface CodeIntelligenceProvidersDTO {
  klaatcode: { available: boolean; status: CodeIntelligenceExternalProviderStatusDTO | null };
  ohmypi: { available: boolean; status: CodeIntelligenceExternalProviderStatusDTO | null };
  hermes_native: { available: boolean; status: { agent_id: string } | null };
}

export interface CodeIntelligenceProviderScoreDTO {
  provider: string;
  score: number;
  factors: Record<string, number>;
  reasoning: string[];
}

export interface CodeIntelligenceDecisionDTO {
  task_type: string;
  selected_provider: string;
  strategy: string;
  primary_reason: string;
  scores: CodeIntelligenceProviderScoreDTO[];
  hybrid_order: string[];
  metadata: Record<string, unknown>;
  decided_at: string;
}

export interface CodeIntelligenceTaskResultDTO {
  success: boolean;
  summary: string;
  duration_ms: number;
  data: unknown;
  provider: string | null;
  strategy: string | null;
  decision: CodeIntelligenceDecisionDTO | null;
  error: string | null;
}

export interface CodeIntelligenceHistoryEntryDTO {
  task_id: string;
  task_type: string;
  selected_provider: string;
  strategy: string;
  success: boolean;
  duration_ms: number;
  kc_score: number;
  omp_score: number;
  primary_reason: string;
  timestamp: string;
}

export interface CodeIntelligenceHistoryDTO {
  history: CodeIntelligenceHistoryEntryDTO[];
  total: number;
}
