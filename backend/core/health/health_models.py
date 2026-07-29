"""Health models for Hermes OS system health monitoring (HOS-056)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single system component."""
    component_id: str
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    latency_ms: float = 0.0
    error_rate: float = 0.0
    last_check: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "last_check": self.last_check,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass
class SystemHealthReport:
    """Complete system health report."""
    overall: HealthStatus = HealthStatus.UNKNOWN
    healthy_score: float = 0.0
    components: list[ComponentHealth] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    unhealthy: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checks_passed: int = 0
    checks_failed: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.overall.value,
            "healthy_score": self.healthy_score,
            "version": self.version,
            "timestamp": self.timestamp,
            "total_components": len(self.components),
            "components": [c.to_dict() for c in self.components],
            "warnings": self.warnings[-20:],
            "degraded": self.degraded,
            "unhealthy": self.unhealthy,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
        }
