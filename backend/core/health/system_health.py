"""System Health service for Hermes OS (HOS-056).

Orchestrates all health checks, aggregates results, and produces
a unified system health report.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from .health_checks import SYSTEM_HEALTH_CHECKS
from .health_models import ComponentHealth, HealthStatus, SystemHealthReport


class SystemHealth:
    """Central health monitoring service for Hermes OS.

    Aggregates checks across EventBus, Memory, Runtime, Agents,
    Tools, MCP, and External Integrations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._checks: dict[str, Callable[[], ComponentHealth]] = dict(SYSTEM_HEALTH_CHECKS)
        self._custom_checks: dict[str, Callable[[], ComponentHealth]] = {}

    def register_check(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        with self._lock:
            self._custom_checks[name] = check_fn

    def run_all(self) -> SystemHealthReport:
        """Run all health checks and produce a report."""
        with self._lock:
            all_checks = dict(self._checks)
            all_checks.update(self._custom_checks)

        components: list[ComponentHealth] = []
        warnings: list[dict] = []
        degraded: list[str] = []
        unhealthy: list[str] = []
        passed = 0
        failed = 0

        for cid, check_fn in all_checks.items():
            try:
                result = check_fn()
                components.append(result)
                if result.status == HealthStatus.HEALTHY:
                    passed += 1
                elif result.status == HealthStatus.DEGRADED:
                    degraded.append(cid)
                    passed += 1
                elif result.status == HealthStatus.UNHEALTHY:
                    unhealthy.append(cid)
                    failed += 1
                    warnings.append({
                        "component": cid,
                        "message": result.message,
                        "severity": "error",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                else:
                    warnings.append({
                        "component": cid,
                        "message": "Status unknown",
                        "severity": "warning",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except Exception as e:
                components.append(ComponentHealth(
                    component_id=cid, name=cid,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                ))
                unhealthy.append(cid)
                failed += 1
                warnings.append({
                    "component": cid,
                    "message": f"Check failed: {e}",
                    "severity": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        total = len(components) or 1
        healthy_score = round((passed / total) * 100, 1)

        overall = HealthStatus.HEALTHY
        if failed > 0:
            overall = HealthStatus.UNHEALTHY
        elif degraded:
            overall = HealthStatus.DEGRADED
        elif total == 0:
            overall = HealthStatus.UNKNOWN

        return SystemHealthReport(
            overall=overall,
            healthy_score=healthy_score,
            components=components,
            warnings=warnings,
            degraded=degraded,
            unhealthy=unhealthy,
            checks_passed=passed,
            checks_failed=failed,
        )

    def check_component(self, component_id: str) -> ComponentHealth | None:
        """Run a single component health check."""
        with self._lock:
            fn = self._checks.get(component_id) or self._custom_checks.get(component_id)
        if fn is None:
            return None
        try:
            return fn()
        except Exception as e:
            return ComponentHealth(
                component_id=component_id, name=component_id,
                status=HealthStatus.UNHEALTHY, message=str(e),
            )

    def get_check_names(self) -> list[str]:
        with self._lock:
            return list(self._checks.keys()) + list(self._custom_checks.keys())
