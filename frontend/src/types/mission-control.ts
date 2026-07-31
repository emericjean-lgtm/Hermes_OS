/**
 * Types Hermes OS — correspondance exacte avec les modèles Pydantic HOS-028.
 * Source de vérité unique pour tout le frontend.
 */

// ─── Énumérations ─────────────────────────────────────────────

export type MissionStatus =
  | "CREATED" | "PLANNING" | "READY" | "RUNNING"
  | "PAUSED" | "COMPLETED" | "FAILED" | "CANCELLED";

export type AgentState =
  | "CREATED" | "READY" | "SCHEDULED" | "RUNNING"
  | "PAUSED" | "WAITING" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMEOUT";

export type ExecutionState =
  | "IDLE" | "INITIALIZING" | "RUNNING" | "WAITING"
  | "PAUSED" | "RECOVERING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type MissionControlStatusValue =
  | "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "STARTING" | "STOPPING";

export type EventSeverity = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";

export type SystemEventTypeValue =
  | "RUNTIME" | "AGENT" | "MISSION" | "EXECUTION"
  | "MEMORY" | "SKILL" | "SYSTEM" | "OBSERVABILITY" | "INTEGRATION";

export type FreebuffConnectionMode = "API" | "TERMINAL" | "CLI" | "MCP";

export type IntegrationStatus =
  | "DISCONNECTED" | "CONNECTING" | "CONNECTED" | "ERROR";

// ─── Santé & Statut ───────────────────────────────────────────

export interface SubsystemHealth {
  name: string;
  status: "healthy" | "degraded" | "unhealthy";
  message?: string;
  metrics?: Record<string, number>;
}

export interface HealthResponse {
  status: MissionControlStatusValue;
  version: string;
  uptime: number;
  kernel_status: SubsystemHealth[];
  runtime_status: SubsystemHealth[];
  memory_status: SubsystemHealth[];
  integrations_status: SubsystemHealth[];
  event_bus_status: SubsystemHealth[];
}

export interface StatusResponse {
  status: MissionControlStatusValue;
  mission_status: string;
  runtime_status: string;
  memory_status: string;
  integrations: Record<string, string>;
  event_bus_status: string;
  uptime: number;
  version: string;
}

export interface DiagnosticsResponse {
  kernel: Record<string, unknown>;
  runtimes: Record<string, unknown>;
  memory: Record<string, unknown>;
  events: Record<string, unknown>;
  integrations: Record<string, unknown>;
  suggestions: string[];
}

// ─── Statistiques ─────────────────────────────────────────────

export interface StatisticsResponse {
  missions: {
    total: number;
    active: number;
    completed: number;
    failed: number;
  };
  agents: {
    total: number;
    running: number;
  };
  runtimes: {
    total: number;
    healthy: number;
    degraded: number;
  };
  events: {
    total: number;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
  };
  memory: {
    entries: number;
    scopes: Record<string, number>;
  };
  skills: {
    registered: number;
    loaded: number;
  };
  integrations: {
    hermes_agent: boolean;
    freebuff: boolean;
  };
}

// ─── Runtime ──────────────────────────────────────────────────

export interface RuntimeInfo {
  name: string;
  version?: string;
  healthy: boolean;
  status: string;
  capabilities: string[];
  reliability_score: number;
  performance_score: number;
  success_rate: number;
  executions: number;
  failures: number;
  avg_latency_ms: number;
  last_execution?: string;
}

export interface RuntimeHealthInfo {
  name: string;
  healthy: boolean;
  status: string;
  last_check?: string;
  latency_ms?: number;
  error?: string;
}

export interface RuntimeMetrics {
  name: string;
  success_rate: number;
  avg_latency_ms: number;
  reliability_score: number;
  performance_score: number;
  executions: number;
  rank?: number;
}

// ─── Mission ──────────────────────────────────────────────────

export interface Mission {
  id: string;
  title: string;
  description?: string;
  status: MissionStatus;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  progress: number;
  runtime?: string;
  duration_ms?: number;
  created_at: string;
  updated_at?: string;
  error?: string;
}

// ─── Exécution ────────────────────────────────────────────────

export interface ExecutionStatus {
  state: ExecutionState;
  mission_id: string;
  graph_id?: string;
  completed_tasks: number;
  failed_tasks: number;
  total_tasks: number;
  execution_time_ms: number;
  current_task?: string;
}

// ─── Mémoire ──────────────────────────────────────────────────

export interface MemoryEntry {
  id: string;
  scope: string;
  key: string;
  value: unknown;
  timestamp: string;
  ttl?: number;
  metadata?: Record<string, unknown>;
}

export interface MemorySearchResult {
  entries: MemoryEntry[];
  total: number;
}

// ─── Compétences ──────────────────────────────────────────────

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  tags: string[];
  loaded: boolean;
  priority: number;
  estimated_tokens?: number;
}

export interface SkillSelection {
  skills: SkillInfo[];
  reason: string;
}

// ─── Événements ───────────────────────────────────────────────

export interface SystemEvent {
  id: string;
  type: SystemEventTypeValue;
  source: string;
  timestamp: string;
  severity: EventSeverity;
  message: string;
  metadata?: Record<string, unknown>;
  correlation_id?: string;
}

export interface EventStatistics {
  total: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  avg_latency_ms: number;
}

// ─── Freebuff ─────────────────────────────────────────────────

export interface FreebuffProject {
  id: string;
  name: string;
  description?: string;
  status: string;
  last_sync?: string;
  mission_ids?: string[];
}

// ─── Hermes Agent ─────────────────────────────────────────────

export interface HermesAgentStatus {
  status: IntegrationStatus;
  sessions: number;
  capabilities: string[];
  version?: string;
}

// ─── WebSocket Event (timeline temps réel) ────────────────────

export interface TimelineEvent {
  id: string;
  type: string;
  source: string;
  severity: EventSeverity;
  message: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

// ─── Mission Planner (HOS-030) ──────────────────────────────

export type PlanningStrategy = "SEQUENTIAL" | "BALANCED" | "PARALLEL" | "CONSERVATIVE";

export type PlannerType = "LOCAL" | "FREEBUFF";

export interface CreateMissionRequest {
  title: string;
  description?: string;
  objective?: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  strategy: PlanningStrategy;
  planner: PlannerType;
  runtime?: string;
  tags?: string[];
}

export interface MissionPlan {
  mission_id: string;
  graph: ExecutionGraphData;
  strategy: PlanningStrategy;
  planner: PlannerType;
  total_tasks: number;
  estimated_duration_ms: number;
  parallel_groups: number;
  critical_path: string[];
}

export interface ExecutionGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: "task" | "start" | "end" | "condition";
  status: "pending" | "ready" | "running" | "completed" | "failed" | "skipped";
  capability?: string;
  complexity?: "low" | "medium" | "high";
  estimated_ms?: number;
  runtime?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  condition?: string;
}

export interface MissionActionResponse {
  success: boolean;
  mission: Mission;
  message?: string;
}

export interface FreebuffSyncResult {
  project_id: string;
  prompt: string;
  response: string;
  plan: MissionPlan;
  synced_at: string;
}

export const MISSION_STATUS_COLORS: Record<string, string> = {
  CREATED: "var(--color-text-muted)",
  PLANNING: "var(--color-warning)",
  READY: "var(--color-accent)",
  RUNNING: "var(--color-accent)",
  PAUSED: "var(--color-warning)",
  COMPLETED: "var(--color-success)",
  FAILED: "var(--color-danger)",
  CANCELLED: "var(--color-text-muted)",
};

export const PRIORITY_ORDER: Record<string, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
};

// ─── Execution (HOS-031) ────────────────────────────────────

export interface ExecutionOverviewResponse {
  state: ExecutionState;
  mission_id: string;
  mission_title?: string;
  progress: number;
  duration_ms: number;
  runtime?: string;
  active_agents: number;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  remaining_tasks: number;
  started_at?: string;
  estimated_completion?: string;
}

export interface ExecutionTask {
  id: string;
  name: string;
  agent_id?: string;
  runtime?: string;
  status: "pending" | "ready" | "running" | "completed" | "failed" | "skipped" | "cancelled" | "retry";
  started_at?: string;
  duration_ms?: number;
  progress: number;
  retries: number;
  fallback_used?: boolean;
  error?: string;
}

export interface ExecutionTimelineEvent {
  id: string;
  type: string;
  timestamp: string;
  message: string;
  source?: string;
  severity?: string;
}

export interface ExecutionPerformanceData {
  task_durations: { task: string; duration_ms: number }[];
  avg_latency_ms: number;
  wait_time_ms: number;
  retries: number;
  fallbacks: number;
  circuit_breaker_count: number;
  runtime_usage: { runtime: string; count: number }[];
  timeline: { time: string; value: number }[];
}

export interface ExecutionStatisticsResponse {
  missions_executed: number;
  tasks_executed: number;
  success_rate: number;
  avg_execution_time_ms: number;
  avg_wait_time_ms: number;
  total_retries: number;
  total_fallbacks: number;
  circuit_breaker_openings: number;
}

// ─── Agent (HOS-032) ────────────────────────────────────────

export interface AgentInfo {
  id: string;
  name: string;
  state: AgentState;
  runtime: string;
  model?: string;
  mission_id?: string;
  task_id?: string;
  priority: number;
  duration_ms?: number;
  retries: number;
  fallback_used: boolean;
  progress: number;
  created_at: string;
  updated_at?: string;
  error?: string;
  parent_agent_id?: string;
  sub_agent_ids?: string[];
}

export interface AgentDetail extends AgentInfo {
  state_history: { from: AgentState; to: AgentState; timestamp: string; reason?: string }[];
  reliability_score: number;
  performance_score: number;
  memory_ids?: string[];
  skill_ids?: string[];
  dependencies: string[];
  circuit_breaker_count: number;
  fallback_count: number;
}

export interface AgentStatisticsResponse {
  total_agents: number;
  active_agents: number;
  completed_agents: number;
  failed_agents: number;
  sub_agents: number;
  success_rate: number;
  avg_duration_ms: number;
  total_retries: number;
  total_fallbacks: number;
  runtime_distribution: Record<string, number>;
}

export interface AgentGraphEdge {
  source: string;
  target: string;
  label?: string;
}

export interface AgentGraphData {
  nodes: { id: string; label: string; state: AgentState; runtime: string; progress: number; children?: string[] }[];
  edges: AgentGraphEdge[];
}

export interface AgentTimelineEvent {
  id: string;
  agent_id: string;
  agent_name: string;
  type: string;
  timestamp: string;
  message: string;
  severity: "INFO" | "WARNING" | "ERROR";
}

export interface AgentPerformanceData {
  agent_durations: { agent: string; duration_ms: number }[];
  success_rate: number;
  runtime_distribution: { runtime: string; count: number }[];
  retries_by_agent: { agent: string; retries: number }[];
  fallbacks_by_agent: { agent: string; fallbacks: number }[];
  memory_usage: { agent: string; memory_mb: number }[];
  duration_histogram: { bucket: string; count: number }[];
}

// ─── Runtime (HOS-033) ──────────────────────────────────────

export interface RuntimeDetail extends RuntimeInfo {
  provider: string;
  model?: string;
  type: "local" | "cloud";
  policies: string[];
  config: Record<string, unknown>;
  health_history: { time: string; status: string; latency_ms: number }[];
  last_decision?: RuntimeDecisionInfo;
}

export interface RuntimeDecisionInfo {
  runtime: string;
  health_score: number;
  reliability_score: number;
  performance_score: number;
  capability_score: number;
  policy_score: number;
  circuit_penalty: number;
  final_score: number;
  confidence: number;
  reason: string;
  candidate_scores: Record<string, number>;
  timestamp: string;
}

export interface RuntimePolicyInfo {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  description: string;
  rules: RuntimePolicyRuleInfo[];
  runtimes_allowed: string[];
  runtimes_denied: string[];
  preference: "local" | "cloud" | "any";
}

export interface RuntimePolicyRuleInfo {
  field: string;
  operator: string;
  value: string | number | boolean;
}

export interface RuntimeEvent {
  id: string;
  type: string;
  runtime: string;
  timestamp: string;
  /** Mirrors backend RuntimeEventSeverity (backend/runtime/events/event_models.py),
   *  which also emits DEBUG and CRITICAL — both were missing here. */
  severity: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  message: string;
}

export interface RuntimeControlAction {
  action: string;
  runtime: string;
  success: boolean;
  message?: string;
}
