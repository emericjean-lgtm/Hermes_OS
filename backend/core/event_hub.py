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

from backend.core.event_topics import BASELINE_TOPICS

logger = logging.getLogger(__name__)

# §24.2's five and the one this module says about itself, plus every topic the
# RAL, runtime, security and subsystem layers declare — see
# backend/core/event_topics.py for why the two are kept together.
#
# A mutable set, not a frozenset, and that is deliberate: `backend.api.routes.ws`
# does `from backend.core.event_hub import EVENT_TYPES` at import time, so
# rebinding this name would leave that reference pointing at the old value.
# Mutating in place is what makes register_event_types() visible everywhere.
EVENT_TYPES: set[str] = set(BASELINE_TOPICS)


def _is_well_formed(event_type: object) -> bool:
    """A publishable topic is a non-empty dotted string, e.g. ``task.update``."""
    return (
        isinstance(event_type, str)
        and "." in event_type
        and not event_type.startswith(".")
        and not event_type.endswith(".")
        and " " not in event_type
    )


def register_event_types(*names: str) -> set[str]:
    """Declare additional publishable topics; returns the ones newly added.

    Called at startup by the bootstrap with the topics re-derived from the live
    enums, so the allow-list cannot drift behind its producers the way it did
    before HOS-066B (six entries against 44 real topics, silently dropping 26).
    """
    added = {n for n in names if n and n not in EVENT_TYPES}
    EVENT_TYPES.update(added)
    if added:
        logger.debug("registered %d additional event types", len(added))
    return added

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
        # Topics already reported as unknown, so drift is logged once rather
        # than on every publish (a hot topic would otherwise flood the log).
        self._unknown_seen: set[str] = set()

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
        if not _is_well_formed(event_type):
            # A topic that is not a dotted string is a programming error, not
            # drift. Refusing it is safe: no subscriber could match it anyway.
            logger.warning("malformed event type %r, not published", event_type)
            return

        if event_type not in EVENT_TYPES:
            # Delivered anyway, and here is why the publish side is permissive
            # while the subscribe side (see backend/api/routes/ws.py) stays
            # strict.
            #
            # An allow-list on the publish path trades "catch a producer typo"
            # against "silently destroy real events". That trade has now gone
            # wrong twice: the RC1 audit found 26 of 28 RAL topics being dropped
            # with only a log line, and the RC2 audit found 8 more afterwards —
            # emitted as `AUTONOMOUS_EVENTS["goal_received"]` and as a variable
            # holding a conditional, neither of which any scan of string
            # literals can see. Staleness is structural and recurring; a typo is
            # caught by the tests and by the topic showing up in the stream.
            #
            # So: warn once per unknown topic (drift stays visible) and deliver.
            # Subscribers filtering by type are unaffected — an unknown topic
            # matches no filter — so this can only ever reach a client that
            # asked for everything.
            if event_type not in self._unknown_seen:
                self._unknown_seen.add(event_type)
                logger.warning(
                    "event type %r is not in EVENT_TYPES; delivering anyway. "
                    "Add it to backend/core/event_topics.py so clients can "
                    "filter on it.",
                    event_type,
                )

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
