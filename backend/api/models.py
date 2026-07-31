"""Pydantic models for the Hermes OS Mission Control API (HOS-028)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ======================================================================
# Generic response wrappers
# ======================================================================


class APIError(BaseModel):
    """Standard error response body."""

    detail: str
    error_code: str = "internal_error"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Response for GET /api/v1/health."""

    status: str
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    kernel_status: str = "operational"
    runtime_available: int = 0
    runtime_degraded: int = 0
    runtime_unavailable: int = 0
    hermes_agent: str = "unavailable"


class StatusResponse(BaseModel):
    """Response for GET /api/v1/status."""

    status: str
    uptime_seconds: float


class VersionResponse(BaseModel):
    """Response for GET /api/v1/version."""

    version: str = "0.1.0"
    build: str = "HOS-028"
    modules: list[str] = Field(default_factory=lambda: [
        "HOS-009", "HOS-010", "HOS-011", "HOS-012", "HOS-013",
        "HOS-014", "HOS-015", "HOS-016", "HOS-017", "HOS-018",
        "HOS-019", "HOS-020", "HOS-021", "HOS-022", "HOS-023",
        "HOS-024", "HOS-025", "HOS-026", "HOS-027", "HOS-028",
    ])


# ======================================================================
# Mission models
# ======================================================================


class MissionCreateRequest(BaseModel):
    """Request body for POST /api/v1/missions."""

    title: str = Field(..., min_length=1, max_length=200)
    objective: str = Field(..., min_length=1)
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="List of task dicts with id, title, runtime_capability, dependencies")
    mission_id: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=10)


class MissionResponse(BaseModel):
    """Response body for a mission."""

    mission_id: str
    title: str
    objective: str
    state: str
    priority: int
    task_count: int
    agent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionListResponse(BaseModel):
    """Response body for GET /api/v1/missions."""

    missions: list[MissionResponse]
    total: int


# ======================================================================
# Runtime models
# ======================================================================


class RuntimeInfoResponse(BaseModel):
    """Runtime information."""

    name: str
    status: str
    health: str
    capabilities: list[str] = Field(default_factory=list)
    circuit_allowed: bool = True
    metrics: dict[str, Any] = Field(default_factory=dict)


class RuntimeListResponse(BaseModel):
    """Response for GET /api/v1/runtimes."""

    runtimes: list[RuntimeInfoResponse]
    total: int


class RuntimeDecisionResponse(BaseModel):
    """Response for runtime selection."""

    selected_runtime: str
    confidence: float
    decision_score: float
    decision_reason: str
    timestamp: float


# ======================================================================
# Execution models
# ======================================================================


class ExecutionStartRequest(BaseModel):
    """Request body for POST /api/v1/execution/start."""

    mission_id: str
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionStatusResponse(BaseModel):
    """Response for GET /api/v1/execution."""

    state: str
    execution_id: Optional[str] = None
    mission_id: Optional[str] = None
    task_progress: dict[str, int] = Field(default_factory=lambda: {"total": 0, "completed": 0, "failed": 0, "running": 0, "pending": 0})
    elapsed_ms: float = 0.0


# ======================================================================
# Memory models
# ======================================================================


class MemoryStoreRequest(BaseModel):
    """Request body for POST /api/v1/memory."""

    content: str = Field(..., min_length=1)
    title: str = ""
    scope: str = "session"
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=1, ge=1, le=10)


class MemoryEntryResponse(BaseModel):
    """Memory entry response."""

    id: str
    scope: str
    title: str
    content: str
    tags: list[str]
    importance: int
    created_at: float
    updated_at: float


class MemorySearchResponse(BaseModel):
    """Search results."""

    entries: list[MemoryEntryResponse]
    total: int
    execution_time_ms: float


# ======================================================================
# Skills models
# ======================================================================


class SkillSelectRequest(BaseModel):
    """Request body for POST /api/v1/skills/select."""

    required_capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    preferred_ids: list[str] = Field(default_factory=list)


class SkillResponse(BaseModel):
    """Skill descriptor response."""

    id: str
    name: str
    description: str
    capabilities: list[str]
    tags: list[str]
    priority: int
    estimated_tokens: int


class SkillSelectionResponse(BaseModel):
    """Skill selection response."""

    selected_skills: list[str]
    rejected_skills: list[str] = Field(default_factory=list)
    total_tokens: int
    explanation: str
    strategy: str


# ======================================================================
# Events models
# ======================================================================


class EventQueryRequest(BaseModel):
    """Query parameters for GET /api/v1/events."""

    types: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    severities: Optional[list[str]] = None
    limit: Optional[int] = None
    offset: int = 0


class EventResponse(BaseModel):
    """System event response."""

    id: str
    type: str
    source: str
    timestamp: float
    severity: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""


class EventStatisticsResponse(BaseModel):
    """Event bus statistics."""

    total_published: int
    total_consumed: int
    subscriber_count: int
    avg_latency_ms: float
    events_by_type: dict[str, int] = Field(default_factory=dict)
    history_size: int


# ======================================================================
# Integrations models
# ======================================================================


class HermesConnectRequest(BaseModel):
    """Request body for POST /api/v1/hermes/connect."""

    base_url: str = "http://localhost:11434"
    timeout: float = 120.0


class HermesTaskRequest(BaseModel):
    """Request body for POST /api/v1/hermes/task."""

    task_type: str = "chat"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    session_id: Optional[str] = None


# ======================================================================
# System models
# ======================================================================


class DiagnosticsResponse(BaseModel):
    """Full system diagnostics."""

    uptime_seconds: float
    missions: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, Any] = Field(default_factory=dict)
    runtimes: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    skills: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    integrations: dict[str, str] = Field(default_factory=dict)


class StatisticsResponse(BaseModel):
    """Aggregated system statistics."""

    missions: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, Any] = Field(default_factory=dict)
    runtimes: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    uptime_seconds: float


class WebSocketEventMessage(BaseModel):
    """Message sent over the /ws/events WebSocket."""

    id: str
    type: str
    source: str
    timestamp: float
    severity: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""
