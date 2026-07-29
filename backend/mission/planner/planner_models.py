"""Planning models for the Intelligent Mission Planner (HOS-042)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class PlanningStage(str, Enum):
    """Stages of the planning pipeline."""
    RECEIVED = "received"
    DECOMPOSING = "decomposing"
    BUILDING_DEPENDENCIES = "building_dependencies"
    ESTIMATING_COMPLEXITY = "estimating_complexity"
    RECOMMENDING_RUNTIME = "recommending_runtime"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskCategory(str, Enum):
    ANALYSIS = "analysis"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    DEPLOYMENT = "deployment"
    REVIEW = "review"
    PLANNING = "planning"
    INTEGRATION = "integration"
    OPTIMIZATION = "optimization"
    SECURITY = "security"
    CUSTOM = "custom"


# ── Request / Result ─────────────────────────────────────────

@dataclass
class PlanningRequest:
    """User request for mission planning."""

    request_id: str = field(default_factory=lambda: uuid4().hex)
    user_request: str = ""
    objective: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    # Optional inputs
    repository: str = ""
    branch: str = ""
    github_issue: str = ""
    specification: str = ""
    documentation: str = ""
    # Constraints
    max_duration_hours: float = 0.0
    preferred_runtime: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PlanningResult:
    """Complete result of mission planning."""

    result_id: str = field(default_factory=lambda: uuid4().hex)
    request_id: str = ""
    mission_id: str = ""
    stages: list[PlanningStage] = field(default_factory=list)
    current_stage: PlanningStage = PlanningStage.RECEIVED
    # Breakdown
    task_breakdowns: list[TaskBreakdown] = field(default_factory=list)
    # Dependencies
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    parallel_groups: list[list[str]] = field(default_factory=list)
    # Estimates
    complexity_estimates: dict[str, ComplexityEstimate] = field(default_factory=dict)
    # Runtime
    runtime_recommendations: dict[str, RuntimeRecommendation] = field(default_factory=dict)
    # Validation
    validation: Optional[ValidationReport] = None
    # Summary
    total_nodes: int = 0
    estimated_total_duration_hours: float = 0.0
    overall_risk: RiskLevel = RiskLevel.LOW
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)


# ── Task Breakdown ───────────────────────────────────────────

@dataclass
class TaskBreakdown:
    """A decomposed task node ready for DAG construction."""

    task_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    description: str = ""
    category: TaskCategory = TaskCategory.CUSTOM
    parent_task_id: str = ""
    # Dependencies (task IDs)
    depends_on: list[str] = field(default_factory=list)
    # Runtime preferences
    preferred_runtime: str = ""
    preferred_agent: str = ""
    benchmark_profile: str = ""
    # Requirements
    required_skills: list[str] = field(default_factory=list)
    validation_criteria: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    # Ordering
    order: int = 0
    is_critical_path: bool = False
    can_parallelize: bool = True


# ── Complexity Estimate ──────────────────────────────────────

@dataclass
class ComplexityEstimate:
    """Estimated complexity and resource needs for a task."""

    task_id: str = ""
    # Complexity
    complexity_score: float = 0.0  # 0.0 - 10.0
    complexity_level: str = "low"  # low, medium, high, critical
    # Duration
    estimated_duration_hours: float = 0.0
    min_duration_hours: float = 0.0
    max_duration_hours: float = 0.0
    # Resources
    estimated_vram_gb: float = 0.0
    estimated_ram_gb: float = 0.0
    estimated_tokens: int = 0
    # Risk
    risk_level: RiskLevel = RiskLevel.LOW
    risk_factors: list[str] = field(default_factory=list)
    # Priority
    suggested_priority: str = "normal"  # critical, high, normal, background
    # Confidence
    confidence: float = 0.8  # 0.0 - 1.0


# ── Runtime Recommendation ───────────────────────────────────

@dataclass
class RuntimeRecommendation:
    """Recommended runtime configuration for a task node."""

    task_id: str = ""
    runtime_id: str = ""
    model_name: str = ""
    benchmark_profile: str = ""
    priority: str = "normal"
    confidence: float = 0.0
    reasoning: str = ""
    alternatives: list[str] = field(default_factory=list)
    fallback_runtime: str = ""


# ── Validation Report ────────────────────────────────────────

@dataclass
class ValidationReport:
    """Result of plan validation."""

    valid: bool = True
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    # Stats
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0


# ── Error ────────────────────────────────────────────────────

@dataclass
class PlanningError:
    """Error during planning."""

    stage: PlanningStage = PlanningStage.RECEIVED
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = False
