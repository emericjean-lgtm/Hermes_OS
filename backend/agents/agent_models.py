"""Agent models for the Agent Supervisor (HOS-043)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RECOVERING = "recovering"


class AgentCapability(str, Enum):
    """Agent capabilities for task matching."""
    CHAT = "chat"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    DESIGN = "design"
    DEPLOYMENT = "deployment"
    DATA_PROCESSING = "data_processing"
    SECURITY_AUDIT = "security_audit"
    OPTIMIZATION = "optimization"
    RESEARCH = "research"
    CUSTOM = "custom"


class TaskOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ── Agent ────────────────────────────────────────────────────

@dataclass
class Agent:
    """A specialized agent that executes mission tasks."""

    agent_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    status: AgentStatus = AgentStatus.CREATED
    # Capabilities
    capabilities: list[AgentCapability] = field(default_factory=list)
    profile: AgentProfile = field(default_factory=lambda: AgentProfile())
    # Runtime
    preferred_runtime: str = ""
    preferred_model: str = ""
    benchmark_profile: str = ""
    # State
    current_task_id: str = ""
    current_mission_id: str = ""
    # Metrics
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_duration_ms: float = 0.0
    # Tracking
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.status == AgentStatus.READY

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 100.0
        return round(self.successful_tasks / self.total_tasks * 100, 1)

    @property
    def load(self) -> float:
        return 1.0 if self.status == AgentStatus.BUSY else 0.0


@dataclass
class AgentProfile:
    """Detailed agent profile for capability matching."""

    max_concurrent_tasks: int = 1
    max_retries: int = 3
    timeout_seconds: float = 300.0
    # Skill levels (0.0 - 1.0)
    skill_levels: dict[str, float] = field(default_factory=dict)
    # Preferences
    preferred_task_types: list[str] = field(default_factory=list)
    excluded_task_types: list[str] = field(default_factory=list)
    # Reliability
    reliability_score: float = 0.8
    performance_score: float = 0.7
    # Constraints
    max_tokens_per_task: int = 0
    requires_gpu: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class AgentMetrics:
    """Aggregated agent metrics."""

    agent_id: str = ""
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    success_rate: float = 100.0
    last_active: Optional[datetime] = None
    uptime_seconds: float = 0.0
    current_load: float = 0.0


# ── Execution Context ────────────────────────────────────────

@dataclass
class ExecutionContext:
    """Context for a task execution."""

    context_id: str = field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    mission_id: str = ""
    node_id: str = ""
    task_title: str = ""
    task_description: str = ""
    task_type: str = ""
    # Environment
    preferred_runtime: str = ""
    preferred_model: str = ""
    benchmark_profile: str = ""
    # Resources
    estimated_vram_gb: float = 0.0
    estimated_ram_gb: float = 0.0
    estimated_tokens: int = 0
    # Constraints
    max_retries: int = 3
    timeout_seconds: float = 300.0
    priority: str = "normal"
    # State
    retry_count: int = 0
    started_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of a task execution."""

    context_id: str = ""
    agent_id: str = ""
    node_id: str = ""
    outcome: TaskOutcome = TaskOutcome.SUCCESS
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    # Output
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    # Errors
    error_message: str = ""
    retry_count: int = 0


# ── Task ─────────────────────────────────────────────────────

@dataclass
class AgentTask:
    """A task assigned to an agent."""

    task_id: str = field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    mission_id: str = ""
    node_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "pending"  # pending, running, completed, failed
    priority: str = "normal"
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[ExecutionResult] = None
