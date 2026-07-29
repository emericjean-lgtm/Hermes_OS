"""Simulation models for the Runtime Simulation Engine (HOS-039)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class SimulationStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ResourcePrediction:
    """Predicted resource consumption for a simulation run."""

    vram_mb: int = 0
    ram_mb: int = 0
    estimated_duration_ms: float = 0.0
    expected_load_pct: float = 0.0
    concurrent_capacity: int = 1


@dataclass
class RiskAssessment:
    """Risk analysis for a simulated decision."""

    level: RiskLevel = RiskLevel.LOW
    score: float = 0.0  # 0-100 (higher = riskier)
    failure_probability: float = 0.0
    overload_probability: float = 0.0
    instability_score: float = 0.0
    issues: list[str] = field(default_factory=list)


@dataclass
class SimulatedCandidate:
    """A runtime candidate with simulation results."""

    runtime_id: str
    predicted_score: float = 0.0
    resource_prediction: ResourcePrediction = field(default_factory=ResourcePrediction)
    risk_assessment: RiskAssessment = field(default_factory=RiskAssessment)
    is_recommended: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Complete simulation result."""

    simulation_id: str = field(default_factory=lambda: uuid4().hex)
    task_context: dict[str, Any] = field(default_factory=dict)
    status: SimulationStatus = SimulationStatus.CREATED
    candidates: list[SimulatedCandidate] = field(default_factory=list)
    recommended_runtime: Optional[str] = None
    overall_risk: RiskLevel = RiskLevel.LOW
    summary: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
