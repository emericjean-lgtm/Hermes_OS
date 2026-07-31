"""Health Orchestrator for Hermes OS (HOS-056).

Aggregates health checks from all components, tracks warnings,
and provides a unified health status for the system.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from .component_registry import ComponentStatus


class HealthOrchestrator:
    """Aggregates health across all registered components."""

    def __init__(self, registry: Any) -> None:
        self._lock = threading.RLock()
        self._registry = registry
        self._health_checks: dict[str, Callable[[], ComponentStatus]] = {}
        self._warnings: list[dict[str, Any]] = []
        self._max_warnings = 500

    def register_health_check(self, component_id: str, check_fn: Callable[[], ComponentStatus]) -> None:
        with self._lock:
            self._health_checks[component_id] = check_fn

    def run_health_check(self, component_id: str) -> ComponentStatus:
        """Run a health check for a single component."""
        with self._lock:
            check = self._health_checks.get(component_id)
            if check is None:
                return ComponentStatus.UNKNOWN
        try:
            status = check()
            self._registry.update_status(component_id, status)
            return status
        except Exception:
            self._registry.update_status(component_id, ComponentStatus.UNHEALTHY)
            return ComponentStatus.UNHEALTHY

    def run_all_checks(self) -> dict[str, ComponentStatus]:
        """Run health checks for all components."""
        with self._lock:
            checks = dict(self._health_checks)
        results: dict[str, ComponentStatus] = {}
        for cid in checks:
            results[cid] = self.run_health_check(cid)
        return results

    def add_warning(self, component_id: str, message: str, severity: str = "warning") -> None:
        with self._lock:
            self._warnings.append({
                "component_id": component_id,
                "message": message,
                "severity": severity,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._warnings) > self._max_warnings:
                self._warnings = self._warnings[-self._max_warnings:]

    def get_warnings(self, component_id: str | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            warnings = list(self._warnings)
            if component_id:
                warnings = [w for w in warnings if w["component_id"] == component_id]
            return warnings[-limit:]

    def get_aggregate_health(self) -> dict[str, Any]:
        """Get comprehensive system health status."""
        summary = self._registry.get_status_summary()
        total = summary["total"] or 1
        healthy_score = round((summary["healthy"] + summary["degraded"] * 0.5) / total * 100, 1)

        overall = "healthy"
        if summary["unhealthy"] > 0:
            overall = "unhealthy"
        elif summary["degraded"] > 0:
            overall = "degraded"
        elif summary["total"] == 0:
            overall = "unknown"

        with self._lock:
            warnings = list(self._warnings)

        return {
            "overall": overall,
            "healthy_score": healthy_score,
            "total_components": summary["total"],
            "healthy_count": summary["healthy"],
            "degraded_count": summary["degraded"],
            "unhealthy_count": summary["unhealthy"],
            "unknown_count": summary["unknown"],
            "disabled_count": summary["disabled"],
            "warnings_count": len(warnings),
            "warnings": warnings[-20:],
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
