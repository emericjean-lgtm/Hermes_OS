"""Mission models for the Mission Graph Engine (HOS-041)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class MissionStatus(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    BACKGROUND = "background"


class MissionType(str, Enum):
    DEVELOPMENT = "development"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    DEPLOYMENT = "deployment"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class MissionEdge:
    """Directed edge from source to target node."""

    edge_id: str = field(default_factory=lambda: uuid4().hex)
    source_id: str = ""
    target_id: str = ""
    type: str = "depends_on"  # depends_on, triggers, validates


@dataclass
class MissionNode:
    """A single task node in the mission DAG."""

    node_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    description: str = ""
    type: str = "task"
    priority: MissionPriority = MissionPriority.NORMAL
    status: NodeStatus = NodeStatus.PENDING
    # Runtime preferences
    preferred_agent: str = ""
    preferred_runtime: str = ""
    benchmark_profile: str = ""
    # Requirements
    required_skills: list[str] = field(default_factory=list)
    estimated_resources: dict[str, Any] = field(default_factory=dict)
    estimated_duration_ms: float = 0.0
    # Dependencies are tracked via edges
    depends_on: list[str] = field(default_factory=list)
    # Validation
    validation_criteria: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    # Results
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actual_duration_ms: float = 0.0
    result_summary: str = ""


@dataclass
class MissionContext:
    """Contextual information for a mission."""

    project_id: str = ""
    user_id: str = ""
    repository: str = ""
    branch: str = ""
    # Local checkout this mission operates on (HOS-068), validated against
    # Aegis's ALLOWED_PATHS whitelist before the mission may start — see
    # mission/routes.py's _check_mission_security(). Empty means "no
    # specific local project", the honest default.
    local_path: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Mission:
    """A complete mission represented as a DAG."""

    mission_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    description: str = ""
    objective: str = ""
    type: MissionType = MissionType.CUSTOM
    priority: MissionPriority = MissionPriority.NORMAL
    status: MissionStatus = MissionStatus.CREATED
    context: MissionContext = field(default_factory=MissionContext)
    nodes: list[MissionNode] = field(default_factory=list)
    edges: list[MissionEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def total_nodes(self) -> int:
        return len(self.nodes)

    def completed_nodes(self) -> int:
        return sum(1 for n in self.nodes if n.status == NodeStatus.COMPLETED)

    def failed_nodes(self) -> int:
        return sum(1 for n in self.nodes if n.status == NodeStatus.FAILED)

    def progress_pct(self) -> float:
        if not self.nodes:
            return 0.0
        return round(self.completed_nodes() / len(self.nodes) * 100, 1)


@dataclass
class MissionReport:
    """Final report for a mission (HOS-068) — derived entirely from a
    Mission's own real, already-measured state (node status, durations,
    result_summary) rather than tracked separately, so there is nothing new
    that can drift out of sync with what actually happened. Mirrors
    AutonomousReport's shape for the fields that mean the same thing, using
    Mission's own vocabulary (mission_id/title/objective) rather than
    AutonomousGoal's (goal_id/user_request/interpreted_goal)."""

    mission_id: str = ""
    title: str = ""
    objective: str = ""
    status: str = ""
    summary: str = ""
    success: bool = False
    total_duration_ms: float = 0.0
    tasks_total: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    runtimes_used: list[str] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "summary": self.summary,
            "success": self.success,
            "total_duration_ms": self.total_duration_ms,
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "runtimes_used": self.runtimes_used,
            "outputs": self.outputs,
            "errors": self.errors,
            "generated_at": self.generated_at.isoformat(),
        }


def build_mission_report(mission: "Mission") -> MissionReport:
    """Derive a MissionReport from a Mission's real, already-measured state.

    No new tracking: duration comes from started_at/completed_at (or 0 if
    the mission never started), outputs/errors come from each node's own
    result_summary, runtimes_used from the provider each completed node
    actually reported (node.preferred_runtime is overwritten with the real
    serving runtime after execution — see node_execution.py).
    """
    duration_ms = 0.0
    if mission.started_at is not None:
        end = mission.completed_at or datetime.now(timezone.utc)
        duration_ms = (end - mission.started_at).total_seconds() * 1000.0

    completed = [n for n in mission.nodes if n.status == NodeStatus.COMPLETED]
    failed = [n for n in mission.nodes if n.status == NodeStatus.FAILED]
    runtimes_used = sorted({n.preferred_runtime for n in completed if n.preferred_runtime})
    success = mission.status == MissionStatus.COMPLETED

    summary = (
        f"{len(completed)}/{len(mission.nodes)} task(s) completed"
        + (f" in {duration_ms:.0f}ms" if duration_ms else "")
        if mission.nodes else "No tasks were planned for this mission."
    )

    return MissionReport(
        mission_id=mission.mission_id,
        title=mission.title,
        objective=mission.objective,
        status=mission.status.value,
        summary=summary,
        success=success,
        total_duration_ms=round(duration_ms, 1),
        tasks_total=len(mission.nodes),
        tasks_completed=len(completed),
        tasks_failed=len(failed),
        runtimes_used=runtimes_used,
        outputs=[
            {"task": n.title, "chars": len(n.result_summary or ""), "content": n.result_summary or ""}
            for n in completed
        ],
        errors=[n.result_summary for n in failed if n.result_summary],
    )
