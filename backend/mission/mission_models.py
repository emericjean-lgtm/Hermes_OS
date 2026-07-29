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
