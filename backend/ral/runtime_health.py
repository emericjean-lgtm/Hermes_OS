"""Runtime Abstraction Layer — runtime health monitor (HOS-011).

Provides :class:`RuntimeHealthMonitor`, a generic, backend-agnostic
observability layer for Hermes OS runtimes. It derives a runtime’s
health from its :class:`~backend.ral.runtime.RuntimeStatus` and from
execution metrics recorded in memory.

No concrete backend (Ollama, OpenAI, Claude, vLLM, etc.) is contacted
directly by this module. All checks go through the existing RAL
abstractions.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from backend.ral.runtime import RuntimeStatus
from backend.ral.runtime_registry import RuntimeRegistry


class RuntimeHealthStatus(str, Enum):
    """High-level health status of a runtime adapter."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RuntimeMetrics:
    """In-memory performance metrics for a single runtime.

    Attributes:
        runtime: Name of the observed runtime.
        executions: Total number of recorded executions.
        failures: Number of failed executions.
        total_latency_ms: Sum of all recorded latencies (milliseconds).
        last_error: String representation of the last error, if any.
        last_check: UTC timestamp of the last health check.
    """

    runtime: str
    executions: int = 0
    failures: int = 0
    total_latency_ms: int = 0
    last_error: Optional[str] = None
    last_check: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        """Average latency across all recorded executions."""
        if self.executions == 0:
            return 0.0
        return self.total_latency_ms / self.executions

    @property
    def failure_rate(self) -> float:
        """Failure rate in the range ``[0.0, 1.0]``."""
        if self.executions == 0:
            return 0.0
        return self.failures / self.executions


class RuntimeHealthError(Exception):
    """Raised when a health check or metrics lookup cannot be completed."""


class RuntimeHealthMonitor:
    """Monitor the health and execution metrics of registered runtimes.

    The monitor is intentionally generic: it knows runtimes only through
    a :class:`~backend.ral.runtime_registry.RuntimeRegistry`. It derives
    health from the runtime lifecycle status and from execution counters
    kept in memory.

    Args:
        registry: Registry containing the runtimes to observe.
    """

    # Thresholds
    FAILURE_THRESHOLD = 3
    FAILURE_RATE_THRESHOLD = 0.5

    def __init__(self, registry: RuntimeRegistry) -> None:
        self._registry = registry
        self._metrics: dict[str, RuntimeMetrics] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def check_runtime(self, runtime_name: str) -> RuntimeHealthStatus:
        """Return the current health status of ``runtime_name``.

        The check verifies that:

        * the runtime is registered,
        * the runtime exposes at least one capability,
        * the runtime lifecycle status is usable.

        No backend network call is performed.

        Args:
            runtime_name: Identifier of the runtime to check.

        Returns:
            The current :class:`RuntimeHealthStatus`.

        Raises:
            RuntimeHealthError: If the runtime is not registered.
        """
        try:
            runtime = self._registry.get(runtime_name)
        except KeyError as exc:
            raise RuntimeHealthError(
                f"Runtime '{runtime_name}' is not registered."
            ) from exc

        # Update the last_check timestamp for this runtime.
        self._touch(runtime_name)

        # A runtime without advertised capabilities is considered degraded
        # rather than unavailable: it is present but not useful as-is.
        if runtime.capabilities is None or not runtime.capabilities.available:
            return RuntimeHealthStatus.DEGRADED

        status = runtime.status
        if status == RuntimeStatus.STARTED:
            health = RuntimeHealthStatus.AVAILABLE
        elif status == RuntimeStatus.STARTING:
            health = RuntimeHealthStatus.DEGRADED
        elif status in {RuntimeStatus.STOPPED, RuntimeStatus.STOPPING, RuntimeStatus.ERROR}:
            health = RuntimeHealthStatus.UNAVAILABLE
        else:
            health = RuntimeHealthStatus.UNKNOWN

        return health

    def is_available(self, runtime_name: str) -> bool:
        """Return ``True`` if ``runtime_name`` is currently available."""
        return self.check_runtime(runtime_name) == RuntimeHealthStatus.AVAILABLE

    def is_degraded(self, runtime_name: str) -> bool:
        """Return ``True`` if ``runtime_name`` is degraded."""
        return self.check_runtime(runtime_name) == RuntimeHealthStatus.DEGRADED

    def is_unavailable(self, runtime_name: str) -> bool:
        """Return ``True`` if ``runtime_name`` is unavailable."""
        return self.check_runtime(runtime_name) == RuntimeHealthStatus.UNAVAILABLE

    def is_error_prone(self, runtime_name: str) -> bool:
        """Return ``True`` if the runtime has failed too often.

        A runtime is considered error-prone when it has recorded more
        than :attr:`FAILURE_THRESHOLD` failures **or** when its failure
        rate exceeds :attr:`FAILURE_RATE_THRESHOLD`.
        """
        metrics = self.get_metrics(runtime_name)
        return (
            metrics.failures > self.FAILURE_THRESHOLD
            or metrics.failure_rate > self.FAILURE_RATE_THRESHOLD
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_execution(
        self,
        runtime_name: str,
        *,
        latency_ms: int = 0,
        success: bool = True,
        error: Optional[BaseException] = None,
    ) -> None:
        """Record an execution result for ``runtime_name``.

        Args:
            runtime_name: Identifier of the runtime that executed the
                request.
            latency_ms: Duration of the execution in milliseconds.
            success: ``True`` if the execution succeeded.
            error: Optional exception raised during the execution.
        """
        with self._lock:
            existing = self._metrics.get(runtime_name)
            if existing is None:
                existing = RuntimeMetrics(runtime=runtime_name)

            executions = existing.executions + 1
            failures = existing.failures + (0 if success else 1)
            total_latency = existing.total_latency_ms + latency_ms
            last_error = existing.last_error
            if not success and error is not None:
                last_error = f"{type(error).__name__}: {error}"

            updated = RuntimeMetrics(
                runtime=runtime_name,
                executions=executions,
                failures=failures,
                total_latency_ms=total_latency,
                last_error=last_error,
                last_check=existing.last_check,
            )
            self._metrics[runtime_name] = updated

    def get_metrics(self, runtime_name: str) -> RuntimeMetrics:
        """Return the metrics for ``runtime_name``.

        Args:
            runtime_name: Identifier of the runtime.

        Returns:
            The current :class:`RuntimeMetrics`, or an empty metrics
            object if no execution has been recorded yet.

        Raises:
            RuntimeHealthError: If the runtime is not registered.
        """
        # Ensure the runtime exists before returning metrics, without
        # mutating ``last_check`` (this is a read-only metrics getter).
        try:
            self._registry.get(runtime_name)
        except KeyError as exc:
            raise RuntimeHealthError(
                f"Runtime '{runtime_name}' is not registered."
            ) from exc

        with self._lock:
            return self._metrics.get(
                runtime_name,
                RuntimeMetrics(runtime=runtime_name),
            )

    def list_metrics(self) -> list[RuntimeMetrics]:
        """Return metrics for every runtime that has been touched."""
        with self._lock:
            return list(self._metrics.values())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _touch(self, runtime_name: str) -> None:
        """Ensure a metrics entry exists and update ``last_check``."""
        with self._lock:
            existing = self._metrics.get(runtime_name)
            if existing is None:
                self._metrics[runtime_name] = RuntimeMetrics(
                    runtime=runtime_name,
                    last_check=datetime.now(timezone.utc),
                )
            else:
                self._metrics[runtime_name] = RuntimeMetrics(
                    runtime=existing.runtime,
                    executions=existing.executions,
                    failures=existing.failures,
                    total_latency_ms=existing.total_latency_ms,
                    last_error=existing.last_error,
                    last_check=datetime.now(timezone.utc),
                )
