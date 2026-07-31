"""Health Monitor for Hermes OS (HOS-062).

Runs health checks on all registered components and provides
unified health status. Integrates with HOS-056 HealthOrchestrator.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class HealthCheckResult:
    component: str
    status: str = "unknown"  # healthy / degraded / unhealthy / unknown
    message: str = ""
    latency_ms: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0


class HealthMonitor:
    """Unified health monitoring for all Hermes OS services."""

    def __init__(self, check_interval_s: int = 30):
        self._interval_s = check_interval_s
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._checks: dict[str, tuple[Callable[[], bool], int]] = {}
        self._results: dict[str, HealthCheckResult] = {}
        self._history: list[dict[str, Any]] = []
        self._max_history = 1000
        self._callbacks: list[Callable] = []

    # ── Public API ──

    def register_check(self, name: str, check_fn: Callable[[], bool],
                       interval_s: int = 30) -> None:
        with self._lock:
            self._checks[name] = (check_fn, interval_s)
            self._results[name] = HealthCheckResult(
                component=name, status="unknown"
            )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._results)
            healthy = sum(1 for r in self._results.values() if r.status == "healthy")
            degraded = sum(1 for r in self._results.values() if r.status == "degraded")
            unhealthy = sum(1 for r in self._results.values() if r.status == "unhealthy")
            return {
                "overall": "healthy" if healthy == total and total > 0
                          else "degraded" if unhealthy == 0
                          else "unhealthy",
                "total_components": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "components": {k: {"status": v.status, "message": v.message,
                                   "latency_ms": v.latency_ms}
                              for k, v in self._results.items()},
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def get_component_status(self, name: str) -> HealthCheckResult | None:
        with self._lock:
            return self._results.get(name)

    def on_unhealthy(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def check_once(self, name: str) -> bool:
        """Run a single health check by name."""
        with self._lock:
            if name not in self._checks:
                return False
            check_fn, _ = self._checks[name]
            return self._run_check(name, check_fn)

    # ── Private ──

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                for name, (check_fn, interval) in self._checks.items():
                    result = self._results.get(name)
                    if result and (time.time() - result.last_success < interval):
                        continue
                    self._run_check(name, check_fn)
            time.sleep(5)

    def _run_check(self, name: str, check_fn: Callable[[], bool]) -> bool:
        start = time.time()
        try:
            ok = check_fn()
            latency = (time.time() - start) * 1000
            result = self._results.get(name, HealthCheckResult(component=name))
            if ok:
                result.status = "healthy"
                result.message = ""
                result.consecutive_failures = 0
            else:
                result.status = "degraded"
                result.message = "Check returned unhealthy"
                result.consecutive_failures += 1
                if result.consecutive_failures >= 3:
                    result.status = "unhealthy"
            result.latency_ms = round(latency, 2)
            result.last_success = time.time()
            self._results[name] = result
            self._log_event(name, result.status, result.message)
            if result.status == "unhealthy":
                for cb in self._callbacks:
                    try:
                        cb({"component": name, "status": "unhealthy", "message": result.message})
                    except Exception:
                        pass
            return ok
        except Exception as e:
            result = self._results.get(name, HealthCheckResult(component=name))
            result.status = "unhealthy"
            result.message = str(e)
            result.consecutive_failures = (result.consecutive_failures + 1)
            result.last_success = time.time()
            self._results[name] = result
            self._log_event(name, "unhealthy", str(e))
            return False

    def _log_event(self, component: str, status: str, message: str) -> None:
        event = {
            "component": component,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
