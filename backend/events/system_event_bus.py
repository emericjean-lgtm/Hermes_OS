"""System Event Bus (HOS-025) — central event hub for Hermes OS.

Unifies all events produced by HOS-013 through HOS-024 into a single
publish/subscribe bus with thread safety, filtered subscriptions,
configurable history, and statistics.

No external backend is contacted. Designed to be extended with WebSocket,
Redis Streams, Kafka etc. via EventSubscriber or adapters.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ======================================================================
# Enums
# ======================================================================


class SystemEventType(str, Enum):
    """Canonical event type families across all Hermes OS subsystems.

    Each value corresponds to a family of events from a specific
    subsystem. The full event type string includes the family prefix
    (e.g. ``"runtime.started"``, ``"memory.stored"``).
    """

    RUNTIME = "runtime"
    AGENT = "agent"
    MISSION = "mission"
    EXECUTION = "execution"
    MEMORY = "memory"
    SKILL = "skill"
    SYSTEM = "system"
    OBSERVABILITY = "observability"
    INTEGRATION = "integration"


class EventSeverity(str, Enum):
    """Severity level of a system event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ======================================================================
# Exceptions
# ======================================================================


class SystemEventBusError(Exception):
    """Raised when a system event bus operation fails."""


# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class SystemEvent:
    """An immutable system-wide event.

    Attributes:
        id: Unique event identifier (UUID hex).
        type: The event type family (e.g. ``SystemEventType.RUNTIME``).
        source: Source subsystem identifier (e.g. ``"runtime.health"``,
            ``"memory.unified"``).
        timestamp: Unix timestamp in seconds.
        severity: Event severity level.
        payload: Free-form event payload.
        metadata: Free-form metadata (tags, context, etc.).
        correlation_id: Optional correlation id to group related events.
        parent_event_id: Optional id of the event that triggered this one.
    """

    id: str
    type: SystemEventType | str
    source: str
    timestamp: float = field(default_factory=time.time)
    severity: EventSeverity | str = EventSeverity.INFO
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    parent_event_id: str = ""


@dataclass(frozen=True)
class EventFilter:
    """Filter for subscriptions and queries.

    All fields are optional — an empty filter matches all events.

    Attributes:
        types: Set of event type families to match (union).
        sources: Set of source identifiers to match (union).
        severities: Set of severities to match (union).
        correlation_id: Exact correlation id match.
        since: Only events after this timestamp.
        until: Only events before this timestamp.
        text: Substring search in JSON-serialised payload + metadata.
        metadata_filter: Dict of metadata key/value requirements.
        limit: Maximum number of results.
        offset: Pagination offset.
    """

    types: Optional[frozenset[SystemEventType | str]] = None
    sources: Optional[frozenset[str]] = None
    severities: Optional[frozenset[EventSeverity | str]] = None
    correlation_id: Optional[str] = None
    since: Optional[float] = None
    until: Optional[float] = None
    text: Optional[str] = None
    metadata_filter: Optional[dict[str, Any]] = None
    limit: Optional[int] = None
    offset: int = 0


@dataclass(frozen=True)
class EventStatistics:
    """Aggregated event bus statistics.

    Attributes:
        total_published: Total events published.
        total_consumed: Total events delivered to subscribers.
        subscriber_count: Number of registered subscribers.
        avg_latency_ms: Average publish-to-deliver latency in ms.
        events_by_type: Event count per event type family.
        events_by_severity: Event count per severity level.
        history_size: Current number of events in history.
        metadata: Free-form metadata.
    """

    total_published: int = 0
    total_consumed: int = 0
    subscriber_count: int = 0
    avg_latency_ms: float = 0.0
    events_by_type: dict[str, int] = field(default_factory=dict)
    events_by_severity: dict[str, int] = field(default_factory=dict)
    history_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# EventSubscriber interface
# ======================================================================


class EventSubscriber(ABC):
    """Abstract interface for event subscribers.

    Implement this to create custom subscribers that can be registered
    with the :class:`SystemEventBus`.
    """

    @abstractmethod
    def handle_event(self, event: SystemEvent) -> None:
        """Process a single event.

        Args:
            event: The event to handle.
        """

    @property
    def name(self) -> str:
        """Human-readable subscriber name (optional override)."""
        return self.__class__.__name__


# ======================================================================
# EventHistory
# ======================================================================


class EventHistory:
    """Thread-safe, size-limited event history.

    Args:
        max_events: Maximum number of events to retain. Older events are
            discarded when exceeded.
    """

    def __init__(self, max_events: int = 5000) -> None:
        self._max_events = max_events
        self._events: list[SystemEvent] = []
        self._lock = threading.RLock()

    def append(self, event: SystemEvent) -> None:
        """Append an event to the history.

        Args:
            event: Event to store.
        """
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    def search(self, filter_: Optional[EventFilter] = None) -> list[SystemEvent]:
        """Search events matching a filter.

        Args:
            filter_: Optional filter. ``None`` returns all events.

        Returns:
            Matched events in insertion order (newest last).
        """
        with self._lock:
            events = list(self._events)

        return self._apply_filter(events, filter_)

    def clear(self) -> None:
        """Remove all events from history."""
        with self._lock:
            self._events.clear()

    def export(
        self,
        *,
        filter_: Optional[EventFilter] = None,
        indent: Optional[int] = None,
    ) -> str:
        """Export events as JSON.

        Args:
            filter_: Optional filter.
            indent: JSON indentation level.

        Returns:
            JSON string.
        """
        events = self.search(filter_)
        data = []
        for ev in events:
            data.append({
                "id": ev.id,
                "type": ev.type.value if isinstance(ev.type, Enum) else ev.type,
                "source": ev.source,
                "timestamp": ev.timestamp,
                "severity": ev.severity.value if isinstance(ev.severity, Enum) else ev.severity,
                "payload": ev.payload,
                "metadata": ev.metadata,
                "correlation_id": ev.correlation_id,
                "parent_event_id": ev.parent_event_id,
            })
        return json.dumps(data, indent=indent, ensure_ascii=False)

    @property
    def size(self) -> int:
        """Current number of events in history."""
        with self._lock:
            return len(self._events)

    # ------------------------------------------------------------------
    # Internal filter
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_filter(
        events: list[SystemEvent],
        filter_: Optional[EventFilter],
    ) -> list[SystemEvent]:
        if filter_ is None:
            return events

        result = events

        if filter_.types is not None and filter_.types:
            result = [
                e for e in result
                if e.type in filter_.types
            ]
        if filter_.sources is not None and filter_.sources:
            result = [e for e in result if e.source in filter_.sources]
        if filter_.severities is not None and filter_.severities:
            result = [
                e for e in result
                if e.severity in filter_.severities
            ]
        if filter_.correlation_id is not None:
            result = [
                e for e in result
                if e.correlation_id == filter_.correlation_id
            ]
        if filter_.since is not None:
            result = [e for e in result if e.timestamp >= filter_.since]
        if filter_.until is not None:
            result = [e for e in result if e.timestamp <= filter_.until]
        if filter_.text is not None:
            text_lower = filter_.text.lower()
            result = [
                e for e in result
                if text_lower in json.dumps(e.payload, default=str).lower()
                or text_lower in json.dumps(e.metadata, default=str).lower()
            ]
        if filter_.metadata_filter is not None:
            for key, value in filter_.metadata_filter.items():
                result = [e for e in result if e.metadata.get(key) == value]

        # Sort by timestamp descending.
        result.sort(key=lambda e: e.timestamp, reverse=True)

        total = len(result)

        # Pagination.
        start = min(filter_.offset, len(result))
        end = None
        if filter_.limit is not None:
            end = start + filter_.limit
        result = result[start:end]

        return result


# ======================================================================
# System Event Bus
# ======================================================================


SubscriberCallback = Callable[[SystemEvent], None]


class SystemEventBus:
    """Central event bus for all Hermes OS subsystem events.

    Supports:
    * Multiple subscribers (callbacks and EventSubscriber instances).
    * Filtered subscriptions (only receive events matching a filter).
    * Configurable event history.
    * Event correlation via ``correlation_id`` and ``parent_event_id``.
    * Thread-safe publish and subscribe.
    * Statistics tracking.

    Args:
        max_history: Maximum number of events to retain in history.
    """

    def __init__(self, max_history: int = 5000) -> None:
        self._history = EventHistory(max_events=max_history)
        self._callbacks: list[tuple[Optional[EventFilter], SubscriberCallback]] = []
        self._subscribers: list[tuple[Optional[EventFilter], EventSubscriber]] = []
        self._lock = threading.RLock()

        # Statistics counters
        self._published = 0
        self._consumed = 0
        self._latency_total_ms = 0.0
        self._latency_count = 0
        self._by_type: dict[str, int] = defaultdict(int)
        self._by_severity: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        event_type: SystemEventType | str,
        source: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        severity: EventSeverity | str = EventSeverity.INFO,
        correlation_id: str = "",
        parent_event_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> SystemEvent:
        """Create and publish a system event.

        Args:
            event_type: Event type family.
            source: Source subsystem identifier.
            payload: Event payload.
            severity: Event severity.
            correlation_id: Optional correlation id.
            parent_event_id: Optional parent event id.
            metadata: Optional metadata.

        Returns:
            The published event (immutable).
        """
        event = SystemEvent(
            id=uuid.uuid4().hex,
            type=event_type,
            source=source,
            timestamp=time.time(),
            severity=severity,
            payload=payload or {},
            metadata=metadata or {},
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
        )

        # Store in history.
        self._history.append(event)

        # Update statistics.
        type_key = event_type.value if isinstance(event_type, Enum) else str(event_type)
        sev_key = severity.value if isinstance(severity, Enum) else str(severity)

        with self._lock:
            self._published += 1
            self._by_type[type_key] += 1
            self._by_severity[sev_key] += 1

        # Deliver to subscribers.
        self._deliver(event)

        return event

    def _deliver(self, event: SystemEvent) -> None:
        """Deliver an event to all matching subscribers."""
        start = time.monotonic()

        # Callback subscribers.
        callbacks: list[tuple[Optional[EventFilter], SubscriberCallback]] = []
        with self._lock:
            callbacks = list(self._callbacks)

        for filter_, cb in callbacks:
            if self._matches_filter(event, filter_):
                try:
                    cb(event)
                    with self._lock:
                        self._consumed += 1
                except Exception:
                    pass

        # EventSubscriber instances.
        subscribers: list[tuple[Optional[EventFilter], EventSubscriber]] = []
        with self._lock:
            subscribers = list(self._subscribers)

        for filter_, sub in subscribers:
            if self._matches_filter(event, filter_):
                try:
                    sub.handle_event(event)
                    with self._lock:
                        self._consumed += 1
                except Exception:
                    pass

        elapsed = (time.monotonic() - start) * 1000
        if elapsed > 0:
            with self._lock:
                self._latency_total_ms += elapsed
                self._latency_count += 1

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        handler: SubscriberCallback | EventSubscriber,
        *,
        filter_: Optional[EventFilter] = None,
    ) -> None:
        """Register a subscriber.

        Args:
            handler: A callable ``(event: SystemEvent) -> None`` or an
                :class:`EventSubscriber` instance.
            filter_: Optional filter. If provided, only events matching
                the filter are delivered.

        Raises:
            SystemEventBusError: If ``handler`` is not callable and not
                an EventSubscriber.
        """
        if callable(handler):
            with self._lock:
                self._callbacks.append((filter_, handler))
        elif isinstance(handler, EventSubscriber):
            with self._lock:
                self._subscribers.append((filter_, handler))
        else:
            raise SystemEventBusError(
                "Subscriber must be a callable or an EventSubscriber instance."
            )

    def unsubscribe(
        self,
        handler: SubscriberCallback | EventSubscriber,
    ) -> bool:
        """Remove a previously registered subscriber.

        Args:
            handler: The callable or EventSubscriber to remove.

        Returns:
            ``True`` if the subscriber was found and removed.
        """
        with self._lock:
            if callable(handler):
                for i, (_, cb) in enumerate(self._callbacks):
                    if cb == handler:
                        self._callbacks.pop(i)
                        return True
            elif isinstance(handler, EventSubscriber):
                for i, (_, sub) in enumerate(self._subscribers):
                    if sub is handler:
                        self._subscribers.pop(i)
                        return True
        return False

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast(
        self,
        event_type: SystemEventType | str,
        source: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        severity: EventSeverity | str = EventSeverity.INFO,
        correlation_id: str = "",
        parent_event_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> SystemEvent:
        """Publish an event to *all* subscribers regardless of filters.

        Unlike :meth:`publish`, ``broadcast`` ignores subscriber
        filters — every registered subscriber receives the event.

        Returns:
            The published event.
        """
        event = SystemEvent(
            id=uuid.uuid4().hex,
            type=event_type,
            source=source,
            timestamp=time.time(),
            severity=severity,
            payload=payload or {},
            metadata=metadata or {},
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
        )

        self._history.append(event)

        type_key = event_type.value if isinstance(event_type, Enum) else str(event_type)
        sev_key = severity.value if isinstance(severity, Enum) else str(severity)
        with self._lock:
            self._published += 1
            self._by_type[type_key] += 1
            self._by_severity[sev_key] += 1

        # Deliver to ALL subscribers regardless of filters.
        start = time.monotonic()
        callbacks: list[SubscriberCallback] = []
        subscribers: list[EventSubscriber] = []
        with self._lock:
            callbacks = [cb for _, cb in self._callbacks]
            subscribers = [sub for _, sub in self._subscribers]

        for cb in callbacks:
            try:
                cb(event)
                with self._lock:
                    self._consumed += 1
            except Exception:
                pass

        for sub in subscribers:
            try:
                sub.handle_event(event)
                with self._lock:
                    self._consumed += 1
            except Exception:
                pass

        elapsed = (time.monotonic() - start) * 1000
        if elapsed > 0:
            with self._lock:
                self._latency_total_ms += elapsed
                self._latency_count += 1

        return event

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        filter_: Optional[EventFilter] = None,
    ) -> list[SystemEvent]:
        """Search the event history.

        Args:
            filter_: Optional filter. ``None`` returns all events.

        Returns:
            Matching events (newest first).
        """
        return self._history.search(filter_)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear the event history. Subscribers remain registered."""
        self._history.clear()

    def export(
        self,
        *,
        filter_: Optional[EventFilter] = None,
        indent: Optional[int] = None,
    ) -> str:
        """Export history as JSON.

        Args:
            filter_: Optional filter.
            indent: JSON indentation.

        Returns:
            JSON string.
        """
        return self._history.export(filter_=filter_, indent=indent)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def statistics(self) -> EventStatistics:
        """Return current aggregated statistics.

        Returns:
            Current event statistics.
        """
        with self._lock:
            avg_latency = (
                self._latency_total_ms / self._latency_count
                if self._latency_count
                else 0.0
            )
            sub_count = len(self._callbacks) + len(self._subscribers)

            return EventStatistics(
                total_published=self._published,
                total_consumed=self._consumed,
                subscriber_count=sub_count,
                avg_latency_ms=avg_latency,
                events_by_type=dict(self._by_type),
                events_by_severity=dict(self._by_severity),
                history_size=self._history.size,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filter(
        event: SystemEvent,
        filter_: Optional[EventFilter],
    ) -> bool:
        """Check if an event matches a filter.

        An event passes if it matches **all** non-None filter fields
        (AND logic within a single filter).
        """
        if filter_ is None:
            return True

        if filter_.types is not None and filter_.types:
            if event.type not in filter_.types:
                return False
        if filter_.sources is not None and filter_.sources:
            if event.source not in filter_.sources:
                return False
        if filter_.severities is not None and filter_.severities:
            if event.severity not in filter_.severities:
                return False
        if filter_.correlation_id is not None:
            if event.correlation_id != filter_.correlation_id:
                return False
        if filter_.since is not None:
            if event.timestamp < filter_.since:
                return False
        if filter_.until is not None:
            if event.timestamp > filter_.until:
                return False

        return True

    # ------------------------------------------------------------------
    # Integration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def from_runtime_event_type(rte: str) -> SystemEventType:
        """Map a HOS-013 ``RuntimeEventType`` string to a ``SystemEventType``.

        Args:
            rte: Runtime event type string (e.g. ``\"runtime.started\"``).

        Returns:
            The corresponding system event type family.
        """
        return SystemEventType.RUNTIME

    @staticmethod
    def from_memory_event(me: str) -> SystemEventType:
        """Map a HOS-021 ``MemoryEvent`` string to a ``SystemEventType``.

        Args:
            me: Memory event string (e.g. ``\"memory.stored\"``).

        Returns:
            The corresponding system event type family.
        """
        return SystemEventType.MEMORY

    @staticmethod
    def from_skill_event(se: str) -> SystemEventType:
        """Map a HOS-022 ``SkillEvent`` string to a ``SystemEventType``.

        Args:
            se: Skill event string (e.g. ``\"skill.loaded\"``).

        Returns:
            The corresponding system event type family.
        """
        return SystemEventType.SKILL

    @staticmethod
    def from_supervisor_event(sve: str) -> SystemEventType:
        """Map a HOS-020 ``SupervisorEvent`` string to a ``SystemEventType``.

        Args:
            sve: Supervisor event string.

        Returns:
            The corresponding system event type family.
        """
        if "mission" in sve:
            return SystemEventType.MISSION
        if "agent" in sve:
            return SystemEventType.AGENT
        return SystemEventType.MISSION

    @staticmethod
    def from_lifecycle_event(lce: str) -> SystemEventType:
        """Map a HOS-019 ``LifecycleEvent`` string to a ``SystemEventType``.

        Args:
            lce: Lifecycle event string.

        Returns:
            The corresponding system event type family.
        """
        return SystemEventType.AGENT

    @staticmethod
    def from_execution_event(ee: str) -> SystemEventType:
        """Map a HOS-024 ``ExecutionEvent`` string to a ``SystemEventType``.

        Args:
            ee: Execution event string.

        Returns:
            The corresponding system event type family.
        """
        return SystemEventType.EXECUTION
