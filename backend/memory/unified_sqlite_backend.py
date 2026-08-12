"""Durable backend for UnifiedMemory (HOS-098).

``UnifiedMemory`` was built as the single facade over every memory scope —
session, mission, agent, project, user, global, experience — with a
pluggable ``MemoryBackend`` so the store could be swapped later. "Later"
never came: ``InMemoryBackend``, a plain dict, was the only implementation,
and it is what ``mission_control``, ``hos_routes`` and the Hermes Agent
adapter have been writing to. Everything they remembered died with the
process.

That left two memory systems with opposite guarantees: ``episodic.py``
persists to SQLite and answers ``memory_remember``/``memory_search``, while
the unified facade — the one the agent integration uses — did not persist at
all. This module removes that split by giving the facade a durable backend
rather than by adding a third store.

Reuses ``memory/db.py``'s engine and session plumbing, the same SQLite file
every other table lives in. Scope, tags and metadata are stored as columns
so the existing ``MemoryQuery`` filters translate to SQL rather than being
re-implemented in Python over a full table scan.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from sqlalchemy import Float, Integer, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base
from backend.memory.unified_memory import (
    MemoryBackend,
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
)

logger = logging.getLogger("hermes_os.memory.unified_sqlite")


class UnifiedMemoryRow(Base):
    """One UnifiedMemory entry, durably.

    Deliberately a separate table from ``episodic``'s MemoryEntry: the two
    carry different shapes (scopes and importance here, type and confidence
    there) and merging them would mean losing fields from one or the other.
    Same database, same session factory, distinct concerns.
    """

    __tablename__ = "unified_memory"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    #: JSON array. Tags are queried with a LIKE over this text: the set is
    #: small and per-entry, so a join table would cost more than it saves.
    tags: Mapped[str] = mapped_column(Text, default="[]")
    importance: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


def _to_entry(row: UnifiedMemoryRow) -> MemoryEntry:
    try:
        tags = frozenset(json.loads(row.tags or "[]"))
    except (ValueError, TypeError):
        tags = frozenset()
    try:
        meta = json.loads(row.metadata_json or "{}")
    except (ValueError, TypeError):
        meta = {}
    return MemoryEntry(
        id=row.id, scope=row.scope, title=row.title or "", content=row.content or "",
        tags=tags, importance=row.importance, created_at=row.created_at,
        updated_at=row.updated_at, metadata=meta,
    )


def _scope_value(scope: MemoryScope | str) -> str:
    return scope.value if isinstance(scope, MemoryScope) else str(scope)


class SqliteMemoryBackend(MemoryBackend):
    """UnifiedMemory over the project's existing SQLite database."""

    def __init__(self, session_factory: Any = None) -> None:
        if session_factory is None:
            # Same construction EchoAgent uses (agents/echo.py) — one SQLite
            # file for the whole system, schema reconciled on the way in.
            from backend.core.config import get_settings
            from backend.memory.db import init_db, make_engine, make_session_factory

            engine = make_engine(get_settings().sqlite_path)
            init_db(engine)
            session_factory = make_session_factory(engine)
        self._session_factory = session_factory
        # SQLite tolerates concurrent readers but serialises writers; the
        # lock keeps read-modify-write sequences (store) atomic rather than
        # relying on the caller to know that.
        self._lock = threading.RLock()

    # ── writes ──────────────────────────────────────────────────────────

    def store(self, entry: MemoryEntry) -> MemoryEntry:
        with self._lock, self._session_factory() as session:
            row = session.get(UnifiedMemoryRow, entry.id)
            if row is None:
                row = UnifiedMemoryRow(id=entry.id)
                session.add(row)
            row.scope = _scope_value(entry.scope)
            row.title = entry.title
            row.content = entry.content
            row.tags = json.dumps(sorted(entry.tags))
            row.importance = entry.importance
            row.created_at = entry.created_at
            row.updated_at = entry.updated_at
            row.metadata_json = json.dumps(entry.metadata, default=str)
            session.commit()
        return entry

    def delete(self, entry_id: str) -> bool:
        with self._lock, self._session_factory() as session:
            row = session.get(UnifiedMemoryRow, entry_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def clear_scope(self, scope: MemoryScope | str) -> int:
        with self._lock, self._session_factory() as session:
            result = session.execute(
                delete(UnifiedMemoryRow).where(
                    UnifiedMemoryRow.scope == _scope_value(scope))
            )
            session.commit()
            return int(result.rowcount or 0)

    # ── reads ───────────────────────────────────────────────────────────

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        with self._session_factory() as session:
            row = session.get(UnifiedMemoryRow, entry_id)
            return _to_entry(row) if row is not None else None

    def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        stmt = select(UnifiedMemoryRow).order_by(UnifiedMemoryRow.created_at.desc())
        if query.scope is not None:
            stmt = stmt.where(UnifiedMemoryRow.scope == _scope_value(query.scope))
        if query.min_importance is not None:
            stmt = stmt.where(UnifiedMemoryRow.importance >= query.min_importance)
        if query.since is not None:
            stmt = stmt.where(UnifiedMemoryRow.created_at >= query.since)
        if query.until is not None:
            stmt = stmt.where(UnifiedMemoryRow.created_at <= query.until)
        if query.text:
            pattern = f"%{query.text}%"
            stmt = stmt.where(
                UnifiedMemoryRow.title.ilike(pattern)
                | UnifiedMemoryRow.content.ilike(pattern)
            )

        with self._session_factory() as session:
            rows = list(session.execute(stmt).scalars())

        entries = [_to_entry(r) for r in rows]
        # Tags and metadata are JSON blobs, so these two filters stay in
        # Python. Applied after the SQL narrowing above rather than instead
        # of it, so the scan is over an already-reduced set.
        if query.tags:
            wanted = set(query.tags)
            entries = [e for e in entries if wanted & set(e.tags)]
        if query.metadata_filter:
            entries = [
                e for e in entries
                if all(e.metadata.get(k) == v for k, v in query.metadata_filter.items())
            ]
        # Pagination last: applying it before the JSON filters would return
        # fewer rows than asked for whenever a filter drops one.
        if query.offset:
            entries = entries[query.offset:]
        if query.limit is not None:
            entries = entries[: query.limit]
        return entries

    def all_entries(self) -> list[MemoryEntry]:
        with self._session_factory() as session:
            rows = session.execute(
                select(UnifiedMemoryRow).order_by(UnifiedMemoryRow.created_at.desc())
            ).scalars()
            return [_to_entry(r) for r in rows]

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.execute(
                select(func.count()).select_from(UnifiedMemoryRow)).scalar() or 0)

    def count_by_scope(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(
                select(UnifiedMemoryRow.scope, func.count())
                .group_by(UnifiedMemoryRow.scope)
            ).all()
            return {scope: int(n) for scope, n in rows}
