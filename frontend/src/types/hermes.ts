// ── Runtime ──────────────────────────────────────────
export interface RuntimeInfo {
  name: string;
  type: string;
  status: RuntimeStatus;
  health: RuntimeHealth;
  metrics: RuntimeMetrics;
  version?: string;
}

export type RuntimeStatus = "AVAILABLE" | "DEGRADED" | "UNAVAILABLE";

export interface RuntimeHealth {
  status: RuntimeStatus;
  last_check: string;
  latency_ms: number;
  success_rate: number;
  circuit_breaker: "CLOSED" | "OPEN" | "HALF_OPEN";
}

export interface RuntimeMetrics {
  total_executions: number;
  success_count: number;
  failure_count: number;
  avg_latency_ms: number;
  avg_tokens_per_sec: number;
  reliability: number;
  performance: number;
}

export interface RuntimeDecision {
  runtime: string;
  score: number;
  factors: Record<string, number>;
  justification: string;
}

export interface ResourceStatus {
  cpu_percent: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_percent: number;
  vram_total_gb?: number;
  vram_used_gb?: number;
  vram_percent?: number;
  gpu_temp_c?: number;
  gpu_name?: string;
}

// ── Mission ──────────────────────────────────────────
export interface Mission {
  id: string;
  title: string;
  description: string;
  status: MissionStatus;
  priority: MissionPriority;
  type: MissionType;
  progress: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  estimated_duration_s?: number;
  node_count?: number;
  completed_nodes?: number;
}

export type MissionStatus =
  | "CREATED"
  | "PLANNING"
  | "READY"
  | "RUNNING"
  | "PAUSED"
  | "WAITING_APPROVAL"
  | "VALIDATING"
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

export interface MissionGraph {
  nodes: MissionNode[];
  edges: MissionEdge[];
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
export interface Agent {
  id: string;
  name: string;
  type: string;
  status: AgentStatus;
  capabilities: string[];
  current_mission?: string;
  current_task?: string;
  runtime?: string;
  metrics: AgentMetrics;
  created_at: string;
  last_active_at?: string;
}

export type AgentStatus = "CREATED" | "STARTING" | "READY" | "BUSY" | "PAUSED" | "ERROR" | "STOPPED" | "COMPLETED";

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
export interface PolicyRule {
  id: string;
  name: string;
  category: string;
  action: "ALLOW" | "DENY" | "REVIEW_REQUIRED";
  enabled: boolean;
  description: string;
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
export interface ExecutionState {
  id: string;
  mission_id: string;
  status: MissionStatus;
  current_node?: string;
  progress: number;
  started_at?: string;
  paused_at?: string;
  completed_at?: string;
  checkpoints: Checkpoint[];
}

export interface Checkpoint {
  id: string;
  timestamp: string;
  status: MissionStatus;
  node_id?: string;
  snapshot: Record<string, unknown>;
}

// ── System ───────────────────────────────────────────
export interface SystemHealth {
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY";
  version: string;
  uptime_s: number;
  subsystems: Record<string, SubsystemHealth>;
}

export interface SubsystemHealth {
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY";
  message?: string;
  latency_ms?: number;
}

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
  skills_registered: number;
  skills_loaded: number;
  events_total: number;
  tools_available: number;
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

export interface OhMyPiCapability {
  name: string;
  description: string;
  category: string;
  requires_workspace: boolean;
  requires_sandbox: boolean;
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
