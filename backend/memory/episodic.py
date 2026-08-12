"""Long-term memory store — cahier des charges §11.2, §24.3 (memory_long).

Rules from §11.5 applied here: every entry is dated automatically
(created_at), duplicates are rejected by content hash (not full semantic
dedup — that needs the ChromaDB side, see semantic.py), and deletion is
explicit (delete_memory), never implicit.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String, Text, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class MemoryEntry(Base):
    __tablename__ = "memory_long"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime)


def _hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def add_memory(
    session: Session,
    *,
    type_: str,
    content: str,
    tags: list[str] | None = None,
    confidence: float = 1.0,
    project_id: str | None = None,
) -> MemoryEntry:
    """Adds an entry, or returns the existing one if the same content
    (exact match) was already stored under the same type *and project*
    (§11.5) — the same fact remembered for two different projects is two
    entries, not a dedup hit across them."""
    content_hash = _hash(content)
    existing = session.execute(
        select(MemoryEntry).where(
            MemoryEntry.type == type_,
            MemoryEntry.content_hash == content_hash,
            MemoryEntry.project_id == project_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = MemoryEntry(
        id=str(uuid.uuid4()),
        project_id=project_id,
        type=type_,
        content=content,
        content_hash=content_hash,
        tags=",".join(tags or []),
        confidence=confidence,
        created_at=datetime.now(UTC),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def list_memories(
    session: Session, *, type_: str | None = None, project_id: str | None = None
) -> list[MemoryEntry]:
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if type_:
        stmt = stmt.where(MemoryEntry.type == type_)
    if project_id is not None:
        stmt = stmt.where(MemoryEntry.project_id == project_id)
    return list(session.execute(stmt).scalars())


def search_memories(
    session: Session,
    query: str,
    *,
    limit: int = 5,
    type_: str | None = None,
    project_id: str | None = None,
) -> list[MemoryEntry]:
    """Text search over what ``add_memory`` actually stored (HOS-086).

    ``memory_remember``/``memory_search`` looked like one round trip and were
    two unrelated stores: remember wrote a MemoryEntry row here, while search
    queried the *document* vector index, so a freshly remembered fact was
    never findable — the failure the user reported as
    ``memory_remember → OK, memory_search → []``.

    Deliberately a LIKE scan over content and tags rather than an embedding
    lookup: these rows are short, explicitly-written facts, they are not
    embedded anywhere today, and inventing a second vector index for them is
    exactly the parallel-memory duplication this system is trying to shed.
    Semantic retrieval over *documents* stays where it already is.
    """
    terms = [t for t in (query or "").split() if t]
    if not terms:
        return []
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if type_:
        stmt = stmt.where(MemoryEntry.type == type_)
    if project_id is not None:
        stmt = stmt.where(MemoryEntry.project_id == project_id)
    # Any term may match (OR): a caller searching "hermes deployment port"
    # should still find a memory that only mentions the port.
    stmt = stmt.where(
        or_(*[MemoryEntry.content.ilike(f"%{t}%") for t in terms]
            + [MemoryEntry.tags.ilike(f"%{t}%") for t in terms])
    )
    rows = list(session.execute(stmt).scalars())
    # Rank by how many distinct terms a row actually matches, so an exact hit
    # outranks an incidental one-word overlap; recency breaks ties via the
    # ORDER BY above (Python's sort is stable).
    lowered = [t.lower() for t in terms]

    def _score(entry: MemoryEntry) -> int:
        haystack = f"{entry.content or ''} {entry.tags or ''}".lower()
        return sum(1 for t in lowered if t in haystack)

    rows.sort(key=_score, reverse=True)
    return rows[:limit]


def get_memory(session: Session, memory_id: str) -> MemoryEntry | None:
    return session.get(MemoryEntry, memory_id)


def delete_memory(session: Session, memory_id: str) -> bool:
    entry = session.get(MemoryEntry, memory_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True
