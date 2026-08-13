"""Durable storage for Assistant conversations (HOS-101).

``ConversationManager`` kept every session in ``self._sessions``, a plain
dict, with a 100-session LRU on top. Two consequences followed, and both
were visible from the UI: restarting the backend erased every transcript,
and the 101st conversation silently deleted the first — permanently, since
nothing else held a copy.

This is the same gap ``UnifiedMemory`` had before HOS-098, and it gets the
same remedy: a durable backend under the existing facade, in the SQLite
file every other table already lives in, rather than a parallel store the
rest of the system would have to learn about.

Two design points are worth stating, because they are what make this cheap
enough to run on every turn:

*Messages are appended, never rewritten.* ``sync`` asks how many rows a
session already has and inserts only what came after. Re-serialising a
whole transcript on each turn would be quadratic over a long conversation,
which is precisely the conversation worth keeping.

*``sync`` is idempotent and self-healing.* It derives the delta from the
database rather than from a counter held in memory, so a call site that
forgets to persist merely defers the write to the next turn instead of
losing the message. Given the choice between an optimisation that can lose
data when someone edits a call site in a year and a ``SELECT COUNT`` that
cannot, this takes the count.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from sqlalchemy import Integer, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from backend.conversation.conversation_models import (
    ConversationContext,
    ConversationSession,
    ConversationStatus,
    Message,
    MessageRole,
)
from backend.memory.db import Base

logger = logging.getLogger("hermes_os.conversation.store")

#: How much of the first user message becomes the session's title. Long
#: enough to tell two conversations apart in a list, short enough not to
#: wrap in the sidebar.
TITLE_MAX_CHARS = 80


class ConversationRow(Base):
    """One Assistant conversation, minus its messages."""

    __tablename__ = "conversation_session"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), default="anonymous", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    #: Derived from the first user message. Stored rather than computed on
    #: read so listing conversations never has to load their transcripts.
    title: Mapped[str] = mapped_column(String(256), default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="", index=True)


class ConversationMessageRow(Base):
    """One line of one transcript.

    ``seq`` is the message's position in its conversation, assigned by the
    writer rather than by the database. Ordering by timestamp would be
    wrong: a user message and the reply it triggered can share a
    millisecond, and ISO strings from different clock readings do not break
    that tie in any meaningful way.
    """

    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str] = mapped_column(String(40), default="")
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    mission_id: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        value = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def derive_title(messages: list[Message]) -> str:
    """The first thing the user actually asked, trimmed to fit a list.

    Falls back to empty rather than to a placeholder like "New conversation":
    an empty title lets the caller decide what to show, whereas a baked-in
    English placeholder would leak into a French UI.
    """
    for message in messages:
        if message.role != MessageRole.USER:
            continue
        text = " ".join((message.content or "").split())
        if not text:
            continue
        return text if len(text) <= TITLE_MAX_CHARS else text[: TITLE_MAX_CHARS - 1] + "…"
    return ""


class SqliteConversationStore:
    """Conversations in the project's existing SQLite database."""

    def __init__(self, session_factory: Any = None) -> None:
        if session_factory is None:
            from backend.core.config import get_settings
            from backend.memory.db import init_db, make_engine, make_session_factory

            engine = make_engine(get_settings().sqlite_path)
            init_db(engine)
            session_factory = make_session_factory(engine)
        self._session_factory = session_factory
        # SQLite serialises writers; the lock keeps sync's count-then-insert
        # sequence atomic rather than hoping two turns never overlap.
        self._lock = threading.RLock()

    # ── writes ──────────────────────────────────────────────────────────

    def sync(self, session: ConversationSession) -> int:
        """Persist the session and any messages not yet stored.

        Returns the number of messages written, so a caller (or a test) can
        assert on what happened instead of inferring it.
        """
        with self._lock, self._session_factory() as db:
            row = db.get(ConversationRow, session.session_id)
            if row is None:
                row = ConversationRow(session_id=session.session_id)
                db.add(row)
            row.user_id = session.user_id
            row.status = getattr(session.status, "value", str(session.status))
            row.title = derive_title(session.messages)
            row.context_json = json.dumps(vars(session.context), default=str)
            row.metadata_json = json.dumps(session.metadata, default=str)
            row.created_at = session.created_at
            row.updated_at = session.updated_at

            stored = int(db.execute(
                select(func.count()).select_from(ConversationMessageRow).where(
                    ConversationMessageRow.session_id == session.session_id)
            ).scalar() or 0)

            written = 0
            for index in range(stored, len(session.messages)):
                message = session.messages[index]
                db.add(ConversationMessageRow(
                    session_id=session.session_id,
                    seq=index,
                    role=getattr(message.role, "value", str(message.role)),
                    content=message.content or "",
                    timestamp=message.timestamp,
                    agent_id=message.agent_id or "",
                    mission_id=message.mission_id or "",
                    metadata_json=json.dumps(message.metadata or {}, default=str),
                ))
                written += 1

            db.commit()
            return written

    def delete(self, session_id: str) -> bool:
        with self._lock, self._session_factory() as db:
            row = db.get(ConversationRow, session_id)
            db.execute(delete(ConversationMessageRow).where(
                ConversationMessageRow.session_id == session_id))
            if row is not None:
                db.delete(row)
            db.commit()
            return row is not None

    # ── reads ───────────────────────────────────────────────────────────

    def load(self, session_id: str) -> Optional[ConversationSession]:
        with self._session_factory() as db:
            row = db.get(ConversationRow, session_id)
            if row is None:
                return None
            message_rows = list(db.execute(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.session_id == session_id)
                .order_by(ConversationMessageRow.seq)
            ).scalars())

        context = ConversationContext()
        for key, value in _loads(row.context_json, {}).items():
            if hasattr(context, key):
                setattr(context, key, value)

        try:
            status = ConversationStatus(row.status)
        except ValueError:
            status = ConversationStatus.ACTIVE

        return ConversationSession(
            session_id=row.session_id,
            user_id=row.user_id or "anonymous",
            status=status,
            messages=[
                Message(
                    role=_role(m.role),
                    content=m.content or "",
                    timestamp=m.timestamp or "",
                    metadata=_loads(m.metadata_json, {}),
                    agent_id=m.agent_id or "",
                    mission_id=m.mission_id or "",
                )
                for m in message_rows
            ],
            context=context,
            created_at=row.created_at or "",
            updated_at=row.updated_at or "",
            metadata=_loads(row.metadata_json, {}),
        )

    def list_recent(self, limit: int = 20, user_id: str | None = None) -> list[dict[str, Any]]:
        """Most recently active conversations, newest first.

        Message counts come from a grouped count rather than from loading
        each transcript: the sidebar asks for this on every render, and it
        has no use for the content.
        """
        stmt = select(ConversationRow).order_by(ConversationRow.updated_at.desc())
        if user_id:
            stmt = stmt.where(ConversationRow.user_id == user_id)
        stmt = stmt.limit(limit)

        with self._session_factory() as db:
            rows = list(db.execute(stmt).scalars())
            counts = dict(db.execute(
                select(ConversationMessageRow.session_id, func.count())
                .group_by(ConversationMessageRow.session_id)
            ).all())

        return [
            {
                "session_id": r.session_id,
                "user_id": r.user_id or "anonymous",
                "status": r.status,
                "title": r.title or "",
                "message_count": int(counts.get(r.session_id, 0)),
                "created_at": r.created_at or "",
                "updated_at": r.updated_at or "",
            }
            for r in rows
        ]

    def count(self) -> int:
        with self._session_factory() as db:
            return int(db.execute(
                select(func.count()).select_from(ConversationRow)).scalar() or 0)


def _role(value: str) -> MessageRole:
    try:
        return MessageRole(value)
    except ValueError:
        return MessageRole.SYSTEM
