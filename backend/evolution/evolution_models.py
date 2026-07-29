"""Self-Evolution models for Hermes OS (HOS-058)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvolutionType(str, Enum):
    RUNTIME_OPTIMIZATION = "runtime_optimization"
    SKILL_IMPROVEMENT = "skill_improvement"
    MODEL_SWITCH = "model_switch"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    AGENT_IMPROVEMENT = "agent_improvement"
    MEMORY_OPTIMIZATION = "memory_optimization"
    ARCHITECTURE_IMPROVEMENT = "architecture_improvement"


class EvolutionStatus(str, Enum):
    DETECTED = "detected"
    SIMULATED = "simulated"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EvolutionProposal:
    """A proposed evolution improvement."""
    proposal_id: str = ""
    evolution_type: EvolutionType = EvolutionType.RUNTIME_OPTIMIZATION
    target_component: str = ""
    description: str = ""
    expected_gain: float = 0.0  # percentage gain estimate
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.0  # 0-1
    status: EvolutionStatus = EvolutionStatus.DETECTED
    metrics_before: dict[str, float] = field(default_factory=dict)
    metrics_after: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "evolution_type": self.evolution_type.value,
            "target_component": self.target_component,
            "description": self.description,
            "expected_gain": self.expected_gain,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "status": self.status.value,
            "metrics_before": self.metrics_before,
            "metrics_after": self.metrics_after,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvolutionExperiment:
    """Result of simulating a proposed evolution."""
    experiment_id: str = ""
    proposal_id: str = ""
    before_metrics: dict[str, float] = field(default_factory=dict)
    after_metrics: dict[str, float] = field(default_factory=dict)
    result: str = ""  # improvement / no_change / regression
    conclusion: str = ""
    simulated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "proposal_id": self.proposal_id,
            "before_metrics": self.before_metrics,
            "after_metrics": self.after_metrics,
            "result": self.result,
            "conclusion": self.conclusion,
            "simulated_at": self.simulated_at.isoformat(),
        }


@dataclass
class OptimizationPattern:
    """A reusable optimization pattern learned from past evolutions."""
    pattern_id: str = ""
    pattern: str = ""
    source: str = ""
    frequency: int = 0
    success_rate: float = 0.0
    avg_gain: float = 0.0
    tags: list[str] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern": self.pattern,
            "source": self.source,
            "frequency": self.frequency,
            "success_rate": self.success_rate,
            "avg_gain": self.avg_gain,
            "tags": self.tags,
        }


@dataclass
class EvolutionReport:
    """Periodic evolution report."""
    report_id: str = ""
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    improvements_found: int = 0
    applied_changes: list[str] = field(default_factory=list)
    rejected_changes: list[str] = field(default_factory=list)
    total_gain_percent: float = 0.0
    proposals: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SystemMetrics:
    """Snapshot of system metrics for evolution analysis."""
    runtime_avg_latency_ms: float = 0.0
    runtime_vram_mb: float = 0.0
    runtime_error_rate: float = 0.0
    runtime_model_score: float = 0.0
    agent_success_rate: float = 0.0
    agent_avg_duration_ms: float = 0.0
    agent_failure_count: int = 0
    skill_usage_rate: float = 0.0
    skill_success_rate: float = 0.0
    skill_unused_ratio: float = 0.0
    mission_avg_duration_s: float = 0.0
    mission_blocked_count: int = 0
    mission_repeat_rate: float = 0.0
    memory_pattern_count: int = 0
    memory_hit_rate: float = 0.0
    memory_prune_rate: float = 0.0
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EVOLUTION_EVENTS = {
    "proposal_created": "evolution.proposal.created",
    "simulation_completed": "evolution.simulation.completed",
    "approved": "evolution.approved",
    "applied": "evolution.applied",
    "failed": "evolution.failed",
    "pattern_discovered": "evolution.pattern.discovered",
    "report_generated": "evolution.report.generated",
}
