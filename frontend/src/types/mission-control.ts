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
