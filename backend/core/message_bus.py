"""Inter-agent message bus (cahier des charges §9.2, §24.4).

Every typed exchange between agents — right now just Aegis's validation
request/verdict pair, see agents/aegis.py — goes through publish() so
there is one place these are traced (persisted to SQLite, the same file
as tasks/memory, see backend/memory/db.py) and one place a future
consumer (a WebSocket layer pushing `agent.message` events to the Agents
view, per §24.2) can subscribe without coupling to whichever agent
happens to emit them.

Deliberately synchronous, matching Echo/Kronos: message persistence is a
handful of SQLite writes, not I/O worth making async, and it keeps the
bus callable from both async agent code and sync code like
security/aegis_engine.py's callers.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.config import get_settings
from backend.memory.db import Base, init_db, make_engine, make_session_factory


class MessageType(StrEnum):
    """§9.2's minimal set of message types."""

    TASK_DELEGATION = "TASK_DELEGATION"  # Prime -> agent
    TASK_RESULT = "TASK_RESULT"  # agent -> Prime
    VALIDATION_REQUEST = "VALIDATION_REQUEST"  # agent -> Aegis
    VALIDATION_GRANTED = "VALIDATION_GRANTED"  # Aegis -> agent
    VALIDATION_DENIED = "VALIDATION_DENIED"  # Aegis -> agent
    MEMORY_WRITE = "MEMORY_WRITE"  # agent -> Echo
    MEMORY_QUERY = "MEMORY_QUERY"  # agent -> Echo
    ESCALATION = "ESCALATION"  # agent -> user, human validation needed


class BusMessage(Base):
    """SQLite-backed record of one bus message — the persisted half of
    §24.4's { id, from, to, type, payload, timestamp, task_id } contract.
    `from`/`to` are Python keywords, hence from_agent/to_agent as column
    names; to_dict() below restores the spec's exact field names."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_agent: Mapped[str] = mapped_column(String, index=True)
    to_agent: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
        }


Subscriber = Callable[[BusMessage], None]


class MessageBus:
    def __init__(self, sqlite_path: str) -> None:
        engine = make_engine(sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)
        self._subscribers: list[Subscriber] = []

    def publish(
        self,
        *,
        from_agent: str,
        to_agent: str,
        type_: MessageType | str,
        payload: dict | None = None,
        task_id: str | None = None,
    ) -> BusMessage:
        """Persist a message and notify subscribers, in that order — a
        subscriber only ever sees a message that's already durably
        traced. Raises ValueError if type_ isn't one of MessageType's
        values."""
        message = BusMessage(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent=to_agent,
            type=MessageType(type_).value,
            payload_json=json.dumps(payload or {}),
            timestamp=datetime.now(UTC),
            task_id=task_id,
        )
        with self._session_factory() as session:
            session.add(message)
            session.commit()
            session.refresh(message)

        for handler in list(self._subscribers):
            handler(message)

        return message

    def subscribe(self, handler: Subscriber) -> Callable[[], None]:
        """Register a handler invoked synchronously, in-process, right
        after every publish(). Returns an unsubscribe callable."""
        self._subscribers.append(handler)

        def unsubscribe() -> None:
            self._subscribers.remove(handler)

        return unsubscribe

    def list_messages(
        self, *, task_id: str | None = None, agent: str | None = None, limit: int = 100
    ) -> list[BusMessage]:
        """Most recent messages first, optionally filtered by task_id or
        by agent (matches either side of the exchange — from or to)."""
        with self._session_factory() as session:
            stmt = select(BusMessage).order_by(BusMessage.timestamp.desc()).limit(limit)
            if task_id is not None:
                stmt = stmt.where(BusMessage.task_id == task_id)
            if agent is not None:
                stmt = stmt.where(
                    (BusMessage.from_agent == agent) | (BusMessage.to_agent == agent)
                )
            return list(session.execute(stmt).scalars())


@lru_cache
def get_message_bus() -> MessageBus:
    return MessageBus(get_settings().sqlite_path)
