"""Decision models for the Adaptive Runtime Orchestrator (HOS-038)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class PriorityLevel(str, Enum):
    """Task priority levels for orchestration."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    BACKGROUND = "background"


class DecisionStatus(str, Enum):
    CREATED = "created"
    EVALUATING = "evaluating"
    SELECTED = "selected"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class CandidateRuntime:
    """A runtime candidate in the decision pipeline."""

    runtime_id: str
    intelligence_score: float = 0.0     # From RuntimeScorer
    health_status: str = "unknown"       # From HealthMonitor
    available_resources: int = 0         # Free VRAM bytes from ResourceManager
    resource_load_pct: float = 0.0       # Current utilisation
    recovery_active: bool = False        # In recovery?
    final_score: float = 0.0
    eliminated: bool = False
    elimination_reason: str = ""


@dataclass
class DecisionExplanation:
    """Explains why a runtime was selected or rejected."""

    runtime_id: str
    factor_scores: dict[str, float] = field(default_factory=dict)
    eliminations: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class OrchestratedDecision:
    """Complete decision from the orchestration pipeline."""

    decision_id: str = field(default_factory=lambda: uuid4().hex)
    task_context: dict[str, Any] = field(default_factory=dict)
    priority: PriorityLevel = PriorityLevel.NORMAL
    candidates: list[CandidateRuntime] = field(default_factory=list)
    selected_runtime: Optional[str] = None
    confidence: float = 0.0
    status: DecisionStatus = DecisionStatus.CREATED
    explanation: Optional[DecisionExplanation] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
