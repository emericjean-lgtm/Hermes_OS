"""Intelligence models for the Runtime Intelligence Layer (HOS-037)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class TaskStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    FALLBACK = "fallback"


@dataclass
class DecisionRecord:
    """Records a runtime decision and its outcome for learning."""

    record_id: str = field(default_factory=lambda: uuid4().hex)
    runtime_id: str = ""
    model_name: str = ""
    task_type: str = ""
    status: TaskStatus = TaskStatus.SUCCESS
    duration_ms: float = 0.0
    resource_cost: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RuntimeScore:
    """Computed score for a runtime."""

    runtime_id: str
    performance_score: float = 0.0   # 0-100
    reliability_score: float = 0.0   # 0-100
    resource_efficiency: float = 0.0  # 0-100
    composite_score: float = 0.0      # 0-100 weighted average
    total_executions: int = 0
    successes: int = 0
    failures: int = 0
    fallbacks: int = 0
    avg_duration_ms: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successes / self.total_executions


@dataclass
class TaskContext:
    """Context for a task to help with runtime recommendation."""

    task_type: str = ""
    priority: int = 0
    max_latency_ms: Optional[float] = None
    required_capabilities: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    prefer_local: bool = True


@dataclass
class Recommendation:
    """Runtime recommendation with reasoning."""

    runtime_id: str
    score: float
    confidence: float
    reasoning: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
