"""Runtime Abstraction Layer — event bus contract.

This module defines the central event bus protocol and the topic
vocabulary used by Hermes OS. Concrete implementations (e.g.
:class:`backend.ral.event_bus_impl.EventBusImpl`) are introduced by
HOS-002.
"""
from __future__ import annotations

import typing
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

if typing.TYPE_CHECKING:
    from typing import TypeAlias
else:
    try:
        from typing import TypeAlias
    except ImportError:
        TypeAlias = str  # type: ignore[assignment,misc]


EventId: TypeAlias = str
SubscriptionId: TypeAlias = str


class Topic(str, Enum):
    """Canonical event topics used throughout Hermes OS.

    Topics follow the ``domain.action`` convention. They are emitted by
    runtimes, the SDS, the model router, and the rest of the system. New
    topics must be added here rather than using raw strings.
    """

    RUNTIME_STARTED = "runtime.started"
    RUNTIME_STOPPED = "runtime.stopped"
    RUNTIME_HEALTH = "runtime.health"
    CAPABILITY_REGISTERED = "capability.registered"
    CAPABILITY_UNREGISTERED = "capability.unregistered"
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_DELETED = "memory.deleted"
    KNOWLEDGE_INDEXED = "knowledge.indexed"
    SKILL_GENERATED = "skill.generated"
    SKILL_COMPILATION_COMPLETED = "skill.compilation.completed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    EVOLUTION_TRIGGERED = "evolution.triggered"
    EVOLUTION_COMPLETED = "evolution.completed"
    DELEGATION_REQUESTED = "delegation.requested"
    DELEGATION_COMPLETED = "delegation.completed"
    SECURITY_VALIDATION_REQUESTED = "security.validation.requested"
    SECURITY_VALIDATION_GRANTED = "security.validation.granted"
    SECURITY_VALIDATION_DENIED = "security.validation.denied"
    SYSTEM_METRICS = "system.metrics"
    SDSL_MESSAGE = "sdsl.message"
    AGENT_MESSAGE = "agent.message"


@dataclass(frozen=True)
class TopicPattern:
    """Wildcard pattern for event subscriptions.

    Supported wildcards (implementation-defined in HOS-002):
        * ``task.*`` — any direct action under ``task``.
        * ``task.**`` — any action recursively under ``task``.
        * ``*`` — all topics.
    """

    pattern: str


@dataclass(frozen=True)
class Event:
    """Immutable domain event envelope.

    Attributes:
        id: Unique event identifier.
        topic: Canonical topic of the event.
        payload: Free-form event payload.
        occurred_at: UTC timestamp of the event.
        publisher: Optional identifier of the publisher.
        causation_id: Optional identifier of the causing event.
    """

    id: EventId
    topic: Topic
    payload: dict[str, typing.Any]
    occurred_at: datetime
    publisher: str | None
    causation_id: EventId | None


@typing.runtime_checkable
class EventBusInterface(typing.Protocol):
    """Central event bus contract for Hermes OS.

    Implementations must support:
        * synchronous publishers (``publish`` is sync by design so it can
          be called from both sync and async code paths),
        * wildcard topic subscriptions,
        * durable event replay within an optional time range,
        * idempotent event IDs.

    The concrete implementation is provided by HOS-002.
    
    """

    async def start(self) -> None:
        """Start the event bus lifecycle.

        Must be called before any ``publish()`` or ``subscribe()`` call.
        """
        ...

    async def stop(self) -> None:
        """Stop the event bus lifecycle.

        Releases all resources (SQLite connections, background tasks,
        subscriber references). After ``stop()`` the bus must not be used
        until ``start()`` is called again.
        """
        ...

    def publish(
        self,
        topic: Topic,
        payload: dict[str, typing.Any],
        *,
        publisher: str | None = None,
        causation_id: str | None = None,
    ) -> None:
        """Publish an event.

        This method is intentionally **synchronous** so it can be called
        from sync callback code (Aegis, Kronos, MessageBus legacy bridge)
        as well as async code without requiring an event loop. The method
        persists the event to durable storage before notifying
        subscribers; it never raises (implementations must guarantee this).

        Args:
            topic: Canonical event topic.
            payload: Free-form event payload.
            publisher: Optional identifier of the publishing
                component/runtime.
            causation_id: Optional identifier of the event that caused
                this one (for causality tracing).
        """
        ...

    def subscribe(
        self,
        topic_pattern: Topic | TopicPattern,
        handler: Callable[[Event], typing.Any],
    ) -> SubscriptionId:
        """Register a handler for events matching ``topic_pattern``.

        Handlers may be sync or async callables.
        """
        ...

    def unsubscribe(self, subscription_id: SubscriptionId) -> None:
        """Revoke a previously created subscription."""
        ...

    async def replay(
        self,
        since: datetime,
        until: datetime | None = None,
        topic_pattern: Topic | TopicPattern | None = None,
    ) -> AsyncIterator[Event]:
        """Replay historical events within the optional time range.

        Args:
            since: Earliest timestamp (inclusive).
            until: Optional latest timestamp (inclusive). If ``None``,
                replays all events from ``since`` up to now.
            topic_pattern: If provided, only events matching this
                pattern are yielded.
        """
        ...
