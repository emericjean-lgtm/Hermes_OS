"""Tool health monitor (HOS-049)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .tool_models import HealthStatus, ToolDefinition, ToolInstance


class ToolHealth:
    """Monitors tool availability, latency, and errors."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instances: dict[str, ToolInstance] = {}
        self._health_checks: dict[str, Callable[[], bool]] = {}

    def register(self, tool: ToolDefinition, health_check_fn: Optional[Callable[[], bool]] = None) -> ToolInstance:
        with self._lock:
            instance = ToolInstance(tool_id=tool.id)
            self._instances[tool.id] = instance
            if health_check_fn:
                self._health_checks[tool.id] = health_check_fn
            return instance

    def check(self, tool_id: str) -> HealthStatus:
        with self._lock:
            instance = self._instances.get(tool_id)
            if instance is None:
                return HealthStatus.UNHEALTHY

            check_fn = self._health_checks.get(tool_id)
            if check_fn is None:
                # No health check defined → assume healthy
                instance.health = HealthStatus.HEALTHY
                instance.last_health_check = datetime.now(timezone.utc)
                return HealthStatus.HEALTHY

            try:
                start = time.monotonic()
                healthy = check_fn()
                latency = (time.monotonic() - start) * 1000

                instance.latency_ms = latency
                instance.last_health_check = datetime.now(timezone.utc)

                if healthy:
                    instance.health = HealthStatus.HEALTHY
                    return HealthStatus.HEALTHY
                else:
                    instance.health = HealthStatus.UNHEALTHY
                    return HealthStatus.UNHEALTHY
            except Exception:
                instance.health = HealthStatus.UNHEALTHY
                return HealthStatus.UNHEALTHY

    def check_all(self) -> dict[str, HealthStatus]:
        results: dict[str, HealthStatus] = {}
        with self._lock:
            for tool_id in list(self._instances.keys()):
                results[tool_id] = self.check(tool_id)
        return results

    def record_execution(self, tool_id: str, success: bool, latency_ms: float = 0.0) -> None:
        with self._lock:
            instance = self._instances.get(tool_id)
            if instance:
                instance.total_executions += 1
                if not success:
                    instance.error_count += 1
                instance.latency_ms = (instance.latency_ms * (instance.total_executions - 1) + latency_ms) / max(instance.total_executions, 1)

    def get(self, tool_id: str) -> Optional[ToolInstance]:
        with self._lock:
            return self._instances.get(tool_id)

    def get_all(self) -> list[ToolInstance]:
        with self._lock:
            return list(self._instances.values())

    def remove(self, tool_id: str) -> bool:
        with self._lock:
            self._health_checks.pop(tool_id, None)
            return self._instances.pop(tool_id, None) is not None

    def stats(self) -> dict:
        with self._lock:
            healthy = sum(1 for i in self._instances.values() if i.health == HealthStatus.HEALTHY)
            return {
                "total": len(self._instances),
                "healthy": healthy,
                "degraded_or_unhealthy": len(self._instances) - healthy,
                "avg_latency_ms": round(
                    sum(i.latency_ms for i in self._instances.values()) / max(len(self._instances), 1), 2
                ),
            }
