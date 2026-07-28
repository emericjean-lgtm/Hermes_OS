"""Runtime Abstraction Layer — runtime event bus & observability (HOS-013).

Provides an in-memory, thread-safe event bus and an observability layer
for runtime lifecycle, health, recovery and failover events.

No external backend is contacted. All data is kept in memory and is
intentionally lost on process restart.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class RuntimeEventType:
    """Canonical event types emitted by the runtime layer."""

    REGISTERED = "runtime.registered"
    SELECTED = "runtime.selected"
    STARTED = "runtime.started"
    COMPLETED = "runtime.completed"
    FAILED = "runtime.failed"
    DEGRADED = "runtime.degraded"
    UNAVAILABLE = "runtime.unavailable"
    FALLBACK = "runtime.fallback"
    RECOVERED = "runtime.recovered"
    CIRCUIT_OPENED = "runtime.circuit_opened"
    CIRCUIT_CLOSED = "runtime.circuit_closed"


class Severity(str, Enum):
    """Severity levels for runtime events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RuntimeEvent:
    """A single runtime event.

    Attributes:
        event_type: Canonical event type (see :class:`RuntimeEventType`).
        runtime_name: Identifier of the runtime concerned.
        timestamp: Unix timestamp (seconds). Defaults to ``time.time()``.
        severity: Event severity.
        message: Human-readable message.
        metadata: Free-form key-value payload.
    """

    event_type: str
    runtime_name: str
    timestamp: float = field(default_factory=time.time)
    severity: Severity | str = Severity.INFO
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


RuntimeEventHandler = Callable[[RuntimeEvent], None]


class RuntimeEventBus:
    """In-memory, thread-safe event bus for runtime events.

    Args:
        max_events: Maximum number of events to retain in history.
            Older events are discarded when the limit is exceeded.
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._max_events = max_events
        self._events: list[RuntimeEvent] = []
        self._subscribers: list[RuntimeEventHandler] = []
        self._lock = threading.Lock()

    def publish(self, event: RuntimeEvent) -> None:
        """Publish ``event`` to all subscribers and store it in history."""
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]
            subscribers = self._subscribers[:]

        for handler in subscribers:
            handler(event)

    def subscribe(self, handler: RuntimeEventHandler) -> None:
        """Register a synchronous handler that receives every published event."""
        with self._lock:
            self._subscribers.append(handler)

    def get_events(
        self,
        *,
        event_type: Optional[str] = None,
        runtime_name: Optional[str] = None,
    ) -> list[RuntimeEvent]:
        """Return stored events, optionally filtered.

        Args:
            event_type: Optional event type filter.
            runtime_name: Optional runtime name filter.

        Returns:
            A list of matching events in insertion order.
        """
        with self._lock:
            events = self._events[:]

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        if runtime_name is not None:
            events = [e for e in events if e.runtime_name == runtime_name]
        return events

    def clear(self) -> None:
        """Remove all stored events. Subscribers remain registered."""
        with self._lock:
            self._events.clear()


class RuntimeObservability:
    """Aggregate runtime events into operational metrics.

    Args:
        event_bus: The event bus to observe.
    """

    def __init__(self, event_bus: RuntimeEventBus) -> None:
        self._lock = threading.Lock()
        self._executions = 0
        self._successes = 0
        self._failures = 0
        self._fallbacks = 0
        self._latency_total_ms = 0.0
        self._latency_count = 0
        self._runtime_successes: dict[str, int] = defaultdict(int)
        self._runtime_failures: dict[str, int] = defaultdict(int)
        self._runtime_completions: dict[str, int] = defaultdict(int)
        event_bus.subscribe(self._process_event)

    def _process_event(self, event: RuntimeEvent) -> None:
        latency = event.metadata.get("latency_ms", 0)
        if not isinstance(latency, (int, float)):
            latency = 0

        with self._lock:
            if event.event_type == RuntimeEventType.COMPLETED:
                self._executions += 1
                self._successes += 1
                self._runtime_successes[event.runtime_name] += 1
                self._runtime_completions[event.runtime_name] += 1
                if latency:
                    self._latency_total_ms += latency
                    self._latency_count += 1

            elif event.event_type == RuntimeEventType.FAILED:
                self._executions += 1
                self._failures += 1
                self._runtime_failures[event.runtime_name] += 1
                if latency:
                    self._latency_total_ms += latency
                    self._latency_count += 1

            elif event.event_type == RuntimeEventType.FALLBACK:
                self._fallbacks += 1

    @property
    def metrics(self) -> dict[str, Any]:
        """Return the current aggregated metrics."""
        with self._lock:
            avg_latency = (
                self._latency_total_ms / self._latency_count
                if self._latency_count
                else 0.0
            )

            # Most used runtime = highest number of successful completions.
            most_used = None
            if self._runtime_completions:
                most_used = max(
                    self._runtime_completions,
                    key=lambda k: self._runtime_completions[k],
                )

            # Most reliable runtime = highest success ratio.
            most_reliable = None
            best_ratio = -1.0
            for name in set(self._runtime_successes) | set(self._runtime_failures):
                successes = self._runtime_successes.get(name, 0)
                failures = self._runtime_failures.get(name, 0)
                total = successes + failures
                ratio = successes / total if total else 1.0
                if ratio > best_ratio:
                    best_ratio = ratio
                    most_reliable = name

            return {
                "executions": self._executions,
                "successes": self._successes,
                "failures": self._failures,
                "fallbacks": self._fallbacks,
                "avg_latency_ms": avg_latency,
                "most_used_runtime": most_used,
                "most_reliable_runtime": most_reliable,
            }
