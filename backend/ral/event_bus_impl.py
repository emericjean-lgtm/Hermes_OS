"""Concrete SQLite-backed EventBus implementation (HOS-002).

Satisfies the :class:`backend.ral.event_bus.EventBusInterface` protocol.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import threading
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from backend.ral.event_bus import (
    Event,
    EventBusInterface,
    EventId,
    SubscriptionId,
    Topic,
    TopicPattern,
)

logger = logging.getLogger(__name__)


def _topic_to_string(pattern: Topic | TopicPattern) -> str:
    """Return the canonical string form of a topic subscription target."""
    if isinstance(pattern, Topic):
        return pattern.value
    return pattern.pattern


class _AsyncGuard:
    """Wraps an async callable so it can be safely invoked from sync code.

    Stores the event loop captured during ``start()`` and uses
    ``call_soon_threadsafe``/``create_task`` to dispatch the handler.
    """

    __slots__ = ("_loop",)

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @staticmethod
    def _is_coroutine_fn(fn: Callable[..., object]) -> bool:
        return asyncio.iscoroutinefunction(fn)

    def invoke(self, fn: Callable[[Event], object], event: Event) -> None:
        """Schedule *fn(event)* and never raise."""
        try:
            if self._is_coroutine_fn(fn):
                self._loop.call_soon_threadsafe(
                    self._loop.create_task, fn(event)
                )
            else:
                self._loop.call_soon_threadsafe(fn, event)
        except RuntimeError:
            # Loop already closed — subscriber was not removed in time.
            pass
        except Exception:  # pragma: no cover
            logger.exception("async dispatch of event %r failed", event.id)


class EventBusImpl:
    """SQLite-backed event bus with synchronous *publish()*.

    Lifecycle
    ---------
        *await bus.start()*  — opens the database, creates tables,
        captures the running async loop.
        *bus.publish(...)*   — sync; persists then notifies subscribers.
        *await bus.stop()*   — closes the database, clears subscribers.

    Thread safety
    -------------
    *publish()* and *subscribe()* / *unsubscribe()* hold a
    :class:`threading.Lock` briefly during SQLite writes and subscriber
    list mutations. Handlers scheduled via *call_soon_threadsafe* are
    dispatched on the loop captured by *start()*.
    """

    def __init__(
        self,
        sqlite_path: str,
        *,
        retention_days: int = 7,
    ) -> None:
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")

        self._db_path: str = sqlite_path
        self._retention_days: int = retention_days
        self._conn: sqlite3.Connection | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_guard: _AsyncGuard | None = None
        self._subscribers: dict[SubscriptionId, tuple[str | None, Callable[[Event], object]]] = {}
        self._lock: threading.Lock = threading.Lock()
        self._started: bool = False
        self._stopped: bool = False
        self._cleanup_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API — Protocol methods
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the database and start the bus lifecycle."""
        if self._started:
            return

        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                occurred_at TEXT NOT NULL,
                publisher TEXT,
                causation_id TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic)"
        )
        conn.commit()

        self._conn = conn
        self._loop = asyncio.get_running_loop()
        self._async_guard = _AsyncGuard(self._loop)
        self._started = True
        self._stopped = False

        # Schedule periodic retention cleanup.
        self._cleanup_task = asyncio.ensure_future(
            self._retention_loop(),
            loop=self._loop,
        )

        logger.info("EventBusImpl started at %s", self._db_path)

    async def stop(self) -> None:
        """Stop the bus, close the database, clear state."""
        if self._stopped or not self._started:
            return
        self._stopped = True
        self._started = False

        # Cancel background cleanup task.
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        # Clear subscribers under lock.
        with self._lock:
            self._subscribers.clear()

        # Close database.
        conn = self._conn
        if conn is not None:
            self._conn = None
            conn.close()

        self._loop = None
        self._async_guard = None
        logger.info("EventBusImpl stopped")

    def publish(
        self,
        topic: Topic,
        payload: dict,
        *,
        publisher: str | None = None,
        causation_id: str | None = None,
    ) -> None:
        """Persist the event and notify matching subscribers.

        Never raises (logs and swallows subscriber errors; persists
        silently if persistence fails due to a closed connection).
        """
        # Build event.
        event_id: EventId = uuid.uuid4().hex
        occurred_at = datetime.now(timezone.utc)
        event = Event(
            id=event_id,
            topic=topic,
            payload=payload,
            occurred_at=occurred_at,
            publisher=publisher,
            causation_id=causation_id,
        )

        # Persist and notify under a single lock.
        with self._lock:
            try:
                self._persist(event)
            except Exception:
                logger.exception("failed to persist event %s", event_id)
                return

            for _sid, (_pattern, handler) in list(self._subscribers.items()):
                if _pattern is None or _topic_matches(_pattern, topic.value):
                    self._dispatch(handler, event)

    def subscribe(
        self,
        topic_pattern: Topic | TopicPattern,
        handler: Callable[[Event], object],
    ) -> SubscriptionId:
        """Register *handler* to receive events matching *topic_pattern*."""
        subscription_id: SubscriptionId = uuid.uuid4().hex
        pattern_str: str | None = _topic_to_string(topic_pattern)
        with self._lock:
            self._subscribers[subscription_id] = (pattern_str, handler)
        return subscription_id

    def unsubscribe(self, subscription_id: SubscriptionId) -> None:
        """Remove a previously registered subscription."""
        with self._lock:
            self._subscribers.pop(subscription_id, None)

    async def replay(
        self,
        since: datetime,
        until: datetime | None = None,
        topic_pattern: Topic | TopicPattern | None = None,
    ) -> AsyncIterator[Event]:
        """Yield historical events within *since* .. *until* (or now)."""
        clause = "WHERE occurred_at >= ?"
        params: list[str] = [since.isoformat()]

        if until is not None:
            clause += " AND occurred_at <= ?"
            params.append(until.isoformat())

        clause += " ORDER BY occurred_at ASC"

        topic_filter_str: str | None = None
        if topic_pattern is not None:
            topic_filter_str = _topic_to_string(topic_pattern)

        with self._lock:
            if self._conn is None:
                return
            cursor = self._conn.execute(
                f"SELECT id, topic, payload, occurred_at, publisher, causation_id "
                f"FROM events {clause}",
                params,
            )
            rows = cursor.fetchall()

        for row in rows:
            event_topic_value = str(row[1])
            if topic_filter_str is not None and not _topic_matches(topic_filter_str, event_topic_value):
                continue
            yield Event(
                id=str(row[0]),
                topic=Topic(event_topic_value),
                payload=json.loads(row[2]),
                occurred_at=datetime.fromisoformat(row[3]),
                publisher=row[4],
                causation_id=row[5],
            )

    # ------------------------------------------------------------------
    # Observability (not part of the Protocol — used via cast in HOS-003)
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return diagnostic counters.

        .. note::
            ``stats()`` is *not* part of ``EventBusInterface`` (the
            Protocol). Consumers requiring it downcast via
            ``cast(EventBusImpl, bus).stats()`` per architecture decree
            D-23.
        """
        with self._lock:
            subscriber_count = len(self._subscribers)
            conn = self._conn
            persisted = 0
            if conn is not None:
                try:
                    persisted = conn.execute(
                        "SELECT COUNT(*) FROM events"
                    ).fetchone()[0]
                except Exception:
                    pass

        return {
            "persisted": persisted,
            "subscribers": subscriber_count,
            "started": self._started,
            "stopped": self._stopped,
            "uptime_seconds": self._uptime(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _uptime(self) -> float:
        """Return seconds since *start()* or 0.0 if not started."""
        # Not stored; HOS-003 holder tracks this.
        return 0.0

    def _persist(self, event: Event) -> None:
        """Insert *event* into the SQLite table (caller must hold lock)."""
        if self._conn is None:
            raise RuntimeError("EventBusImpl not started")
        self._conn.execute(
            "INSERT INTO events (id, topic, payload, occurred_at, publisher, causation_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.topic.value,
                json.dumps(event.payload),
                event.occurred_at.isoformat(),
                event.publisher,
                event.causation_id,
            ),
        )
        self._conn.commit()

    def _dispatch(self, handler: Callable[[Event], object], event: Event) -> None:
        """Invoke *handler(event)* without raising."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                # Should not happen — handler should have been a coroutine
                # function already handled via _AsyncGuard — but be safe.
                if self._async_guard is not None:
                    self._async_guard.invoke(handler, event)
        except Exception:
            logger.warning("handler failed for event %s", event.id, exc_info=True)

    async def _retention_loop(self) -> None:
        """Periodically delete expired events."""
        if self._retention_days <= 0:
            return
        while not self._stopped:
            try:
                await asyncio.sleep(3600)  # every hour
                if self._stopped:
                    break
                cutoff = (datetime.now(timezone.utc) - timedelta(days=self._retention_days)).isoformat()
                with self._lock:
                    if self._conn is None:
                        continue
                    cursor = self._conn.execute(
                        "DELETE FROM events WHERE occurred_at < ?", (cutoff,)
                    )
                    self._conn.commit()
                    deleted = cursor.rowcount
                    if deleted:
                        logger.info("retention deleted %d events older than %s", deleted, cutoff)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("retention loop error")


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


@lru_cache(maxsize=128)
def _compile_pattern(pattern_str: str) -> re.Pattern[str]:
    """Convert a Hermes OS wildcard pattern to a compiled regex.

    Supported syntax:

    * ``*`` — matches any topic.
    * ``task.*`` — matches any one-level topic under ``task``
      (e.g. ``task.created`` but *not* ``task.sub.created``).
    * ``task.**`` — matches any recursive topic under ``task``
      (e.g. both ``task.created`` and ``task.sub.created``).
    """
    if pattern_str == "*":
        return re.compile(".*")

    # Escape regex meta-characters except * and **
    parts: list[str] = []
    i = 0
    while i < len(pattern_str):
        ch = pattern_str[i]
        if ch == "*":
            if i + 1 < len(pattern_str) and pattern_str[i + 1] == "*":
                # ** — recursive wildcard
                parts.append(".*")
                i += 2
            else:
                # * — single-level wildcard
                parts.append("[^.]*")
                i += 1
        elif ch in ".^$+?{}()[]|\\":
            parts.append("\\" + ch)
            i += 1
        else:
            parts.append(ch)
            i += 1

    return re.compile(f"^{''.join(parts)}$")


def _topic_matches(pattern_str: str, topic_value: str) -> bool:
    """Return True if *topic_value* matches *pattern_str*."""
    return bool(_compile_pattern(pattern_str).match(topic_value))
