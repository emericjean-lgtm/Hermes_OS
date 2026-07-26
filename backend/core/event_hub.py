"""Real-time event fan-out — cahier des charges §24.2.

Five event types are specified: `system.metrics` (every 2 s), `chat.token`,
`agent.message`, `task.update`, `validation.request`. None of them is new
information — the message bus, Kronos, the approval queue and the GPU
monitor already produce all of it. This module only carries it to
connected clients.

**Publishing is synchronous and never fails.** Four of the five sources
are plain sync functions (`message_bus.publish`, `kronos.update_task`,
`approvals.record_pending`) with no event loop in sight, so `publish()`
must be callable from anywhere. It is also wrapped so that a broken
subscriber cannot break the action being reported: a task status change
that fails because nobody was listening properly would be a far worse bug
than a missing notification. Same rule as the audit log.

**A slow client is isolated, and dropped events are announced.** Each
subscriber owns a bounded queue. When a client cannot keep up, its
*oldest* events are discarded and it is told how many — a stream that
silently skips events is worse than one that admits a gap, because the
reader has no way to know the picture is incomplete.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# §24.2's five, plus one this module has to be able to say about itself.
EVENT_TYPES = frozenset({
    "system.metrics",
    "chat.token",
    "agent.message",
    "task.update",
    "validation.request",
    "stream.dropped",
})

# Roughly ten seconds of metrics at the §24.2 cadence, plus room for a
# burst of agent traffic. Large enough that a brief hiccup costs nothing,
# small enough that a client that walked away cannot pin memory.
DEFAULT_QUEUE_SIZE = 256


@dataclass
class Event:
    type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload, "timestamp": self.timestamp}


@dataclass(eq=False)  # identity hashing: two clients are never "equal"
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    types: frozenset[str] | None  # None = everything
    dropped: int = 0


class EventHub:
    """Fan-out to every connected client. One queue per subscriber."""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._queue_size = queue_size

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Broadcast one event. Safe to call from sync code, from any
        thread, and from code that has no event loop of its own.

        **Never raises**, and the guarantee is structural rather than a
        promise: the whole body is wrapped here, once, so no producer has
        to remember to defend itself. Kronos persisting a task and Aegis
        queueing an approval are real work; a dashboard notification is
        not, and must never be able to cost them.
        """
        try:
            self._publish(event_type, payload)
        except Exception:  # pragma: no cover - the guarantee, not a path
            logger.exception("event fan-out failed for %r", event_type)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in EVENT_TYPES:
            # Loud, because an unknown type means a producer and this list
            # have drifted — but still not fatal to the caller.
            logger.warning("unknown event type %r, not published", event_type)
            return

        event = Event(event_type, payload)
        for subscriber in list(self._subscribers):
            if subscriber.types is not None and event_type not in subscriber.types:
                continue
            self._offer(subscriber, event)

    def _offer(self, subscriber: _Subscriber, event: Event) -> None:
        try:
            subscriber.loop.call_soon_threadsafe(self._enqueue, subscriber, event)
        except RuntimeError:
            # Loop already closed: the client is gone but has not been
            # unsubscribed yet. Not an error worth surfacing.
            self._subscribers.discard(subscriber)
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to offer event %s", event.type)

    @staticmethod
    def _enqueue(subscriber: _Subscriber, event: Event) -> None:
        try:
            subscriber.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest, keep the newest: for a live view, recent
            # state matters more than history. The count is reported.
            with suppress(asyncio.QueueEmpty):
                subscriber.queue.get_nowait()
            subscriber.dropped += 1
            with suppress(asyncio.QueueFull):
                subscriber.queue.put_nowait(event)

    async def subscribe(
        self, types: frozenset[str] | None = None
    ) -> AsyncIterator[Event]:
        """Yield events until the consumer stops iterating."""
        subscriber = _Subscriber(
            queue=asyncio.Queue(maxsize=self._queue_size),
            loop=asyncio.get_running_loop(),
            types=types,
        )
        self._subscribers.add(subscriber)
        try:
            while True:
                event = await subscriber.queue.get()
                if subscriber.dropped:
                    # Announced before the event that follows it, so the
                    # gap is visible at the point where it happened.
                    missed, subscriber.dropped = subscriber.dropped, 0
                    yield Event("stream.dropped", {"count": missed})
                yield event
        finally:
            self._subscribers.discard(subscriber)


@lru_cache(maxsize=1)
def get_event_hub() -> EventHub:
    return EventHub()
