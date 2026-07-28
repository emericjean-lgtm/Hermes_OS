"""Runtime Abstraction Layer — runtime recovery & failover engine (HOS-012).

Provides :class:`RuntimeRecoveryManager` and :class:`CircuitBreaker`, a
backend-agnostic resilience layer for Hermes OS runtimes. No concrete
backend (Ollama, cloud, etc.) is contacted directly by this module.

Recovery decisions are driven by in-memory circuit breakers, the runtime
registry, and the existing :class:`~backend.ral.runtime_selector.RuntimeSelector`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_events import RuntimeEvent, RuntimeEventBus, RuntimeEventType, Severity
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector


class CircuitState(str, Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple thread-safe circuit breaker with automatic recovery.

    The breaker starts ``CLOSED``. After ``failure_threshold`` consecutive
    failures it transitions to ``OPEN`` and refuses executions for
    ``recovery_timeout`` seconds. Once the timeout elapses, it transitions
    to ``HALF_OPEN`` and allows a single probe execution. A successful probe
    closes the circuit; a failed one re-opens it.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before attempting a probe.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            return self._state

    def is_allowed(self) -> bool:
        """Return ``True`` if the circuit allows an execution attempt."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                return True
            # OPEN: check if recovery timeout has elapsed.
            if self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
            return False

    def record_success(self) -> None:
        """Record a successful execution."""
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None

    def record_failure(self, error: Optional[BaseException] = None) -> None:
        """Record a failed execution.

        After ``failure_threshold`` consecutive failures the circuit opens.
        """
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        """Manually reset the circuit to ``CLOSED``."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None


@dataclass(frozen=True)
class ExecutionTrace:
    """Trace of an execution routed through recovery/failover logic.

    Attributes:
        runtime_initial: Name of the runtime first selected for the request.
        runtime_final: Name of the runtime that ultimately executed the
            request.
        retries: Number of retries / fallback attempts.
        fallback_reason: Human-readable reason for the final fallback, if any.
    """

    runtime_initial: str
    runtime_final: str
    retries: int = 0
    fallback_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict representation suitable for metadata."""
        return {
            "runtime_initial": self.runtime_initial,
            "runtime_final": self.runtime_final,
            "retries": self.retries,
            "fallback_reason": self.fallback_reason,
        }


class RuntimeRecoveryError(Exception):
    """Raised when recovery/failover cannot be completed."""


class RuntimeRecoveryManager:
    """Coordinate runtime failover and circuit-breaker-based recovery.

    The manager owns a circuit breaker per runtime and uses the
    :class:`~backend.ral.runtime_selector.RuntimeSelector` to pick a
    compatible fallback when the initially selected runtime fails.

    Args:
        registry: Registry of available runtimes.
        selector: Capability-aware runtime selector.
        failure_threshold: Consecutive failures before a circuit opens.
        recovery_timeout: Seconds before a half-open probe is allowed.
    """

    def __init__(
        self,
        registry: RuntimeRegistry,
        selector: RuntimeSelector,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        self._registry = registry
        self._selector = selector
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._event_bus = event_bus
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Circuit breaker access
    # ------------------------------------------------------------------

    def _publish(
        self,
        event_type: str,
        runtime_name: str,
        *,
        severity: Severity | str = Severity.INFO,
        message: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Publish a runtime event if an event bus is configured."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            RuntimeEvent(
                event_type=event_type,
                runtime_name=runtime_name,
                severity=severity,
                message=message,
                metadata=metadata or {},
            )
        )

    def _get_breaker(self, runtime_name: str) -> CircuitBreaker:
        """Return (or create) the circuit breaker for ``runtime_name``."""
        with self._lock:
            if runtime_name not in self._breakers:
                self._breakers[runtime_name] = CircuitBreaker(
                    failure_threshold=self._failure_threshold,
                    recovery_timeout=self._recovery_timeout,
                )
            return self._breakers[runtime_name]

    def should_retry(self, runtime_name: str) -> bool:
        """Return ``True`` if ``runtime_name`` is allowed to execute.

        A runtime is allowed unless its circuit breaker is currently OPEN
        and the recovery timeout has not elapsed.
        """
        return self._get_breaker(runtime_name).is_allowed()

    def record_failure(self, runtime_name: str, error: Optional[BaseException] = None) -> None:
        """Record a failure on ``runtime_name`` and open its circuit if needed."""
        breaker = self._get_breaker(runtime_name)
        previous_state = breaker.state
        breaker.record_failure(error)
        if breaker.state == CircuitState.OPEN and previous_state != CircuitState.OPEN:
            self._publish(
                RuntimeEventType.CIRCUIT_OPENED,
                runtime_name,
                severity=Severity.WARNING,
                message="Circuit breaker opened after consecutive failures.",
            )

    def record_success(self, runtime_name: str) -> None:
        """Record a success on ``runtime_name`` and close its circuit."""
        breaker = self._get_breaker(runtime_name)
        previous_state = breaker.state
        breaker.record_success()
        if previous_state != CircuitState.CLOSED:
            self._publish(
                RuntimeEventType.CIRCUIT_CLOSED,
                runtime_name,
                severity=Severity.INFO,
                message="Circuit breaker closed after successful execution.",
            )

    def reset(self, runtime_name: str) -> None:
        """Reset the circuit breaker for ``runtime_name``."""
        self._get_breaker(runtime_name).reset()

    # ------------------------------------------------------------------
    # Recovery actions
    # ------------------------------------------------------------------

    def recover(self, runtime_name: str, error: Optional[BaseException] = None) -> str:
        """Update state after a failure and return a fallback reason.

        This method is called by the router after an execution error. It
        records the failure and produces a short reason string that can
        be included in the execution trace.
        """
        self.record_failure(runtime_name, error)
        breaker = self._get_breaker(runtime_name)
        if breaker.state == CircuitState.OPEN:
            return "circuit_open"
        return "runtime_failure"

    def select_fallback(
        self,
        failed_runtime_name: str,
        capability: str,
        *,
        preference: Optional[str] = None,
        exclude: Optional[set[str]] = None,
    ) -> RuntimeInterface:
        """Select an alternative runtime for ``capability``.

        The failed runtime is excluded, and any runtime whose circuit is
        currently OPEN is also skipped.

        Args:
            failed_runtime_name: Name of the runtime that just failed.
            capability: Required capability.
            preference: Optional deployment hint.
            exclude: Optional set of additional runtime names to exclude.

        Returns:
            A compatible runtime that is not excluded and not circuit-open.

        Raises:
            RuntimeRecoveryError: If no suitable fallback can be found.
        """
        exclude = exclude or set()
        exclude.add(failed_runtime_name)

        candidates = self._selector.list_compatible(capability, preference=preference)
        for candidate in candidates:
            name = self._registry.find_name(candidate)
            if name is None or name in exclude:
                continue
            if not self.should_retry(name):
                continue
            if not RuntimeLifecycle.health_check(candidate):
                continue
            return candidate

        raise RuntimeRecoveryError(
            f"No fallback runtime available for capability '{capability}' "
            f"after '{failed_runtime_name}' failed."
        )
