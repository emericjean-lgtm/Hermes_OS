"""Recovery models for the Runtime Recovery Engine (HOS-036)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class IncidentType(str, Enum):
    """Types of incidents that can trigger recovery."""

    RUNTIME_FAILED = "runtime.failed"
    RUNTIME_UNAVAILABLE = "runtime.unavailable"
    RUNTIME_OVERLOADED = "runtime.overloaded"
    HEALTH_DEGRADED = "health.degraded"
    RESOURCE_LIMIT_REACHED = "resource.limit_reached"
    MODEL_LOAD_FAILED = "model.load_failed"


class RecoveryStatus(str, Enum):
    """Status of a recovery process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(str, Enum):
    """Types of recovery actions."""

    RESTART_RUNTIME = "restart_runtime"
    RELOAD_MODEL = "reload_model"
    SWITCH_RUNTIME = "switch_runtime"
    UNLOAD_RESOURCE = "unload_resource"
    NOTIFY = "notify"


class ActionCost(str, Enum):
    """Relative cost of a recovery action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RecoveryIncident:
    """Represents a detected incident that needs recovery."""

    incident_id: str = field(default_factory=lambda: uuid4().hex)
    incident_type: str = ""
    runtime_id: str = ""
    severity: str = "warning"
    payload: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RecoveryAction:
    """Base class for a recovery action."""

    action_id: str = field(default_factory=lambda: uuid4().hex)
    action_type: ActionType = ActionType.NOTIFY
    runtime_id: str = ""
    cost: ActionCost = ActionCost.LOW
    priority: int = 0
    parameters: dict[str, Any] = field(default_factory=dict)

    def execute(self) -> ActionResult:
        """Execute the action. Override in subclasses."""
        return ActionResult(
            action_id=self.action_id,
            action_type=self.action_type,
            success=False,
            message=f"No implementation for {self.action_type}",
        )


@dataclass
class ActionResult:
    """Result of executing a recovery action."""

    action_id: str
    action_type: ActionType
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RecoveryAttempt:
    """Tracks one recovery attempt for an incident."""

    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    incident_id: str = ""
    status: RecoveryStatus = RecoveryStatus.PENDING
    actions: list[RecoveryAction] = field(default_factory=list)
    results: list[ActionResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)


@dataclass
class RecoveryPolicy:
    """A policy rule: when incident_type X, execute actions Y."""

    policy_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    incident_types: list[str] = field(default_factory=list)
    actions: list[RecoveryAction] = field(default_factory=list)
    max_attempts: int = 3
    cooldown_seconds: float = 30.0
    enabled: bool = True
    priority: int = 0
