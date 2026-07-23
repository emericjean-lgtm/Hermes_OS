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

from sqlalchemy import DateTime, Float, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class MemoryEntry(Base):
    __tablename__ = "memory_long"

    id: Mapped[str] = mapped_column(String, primary_key=True)
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
) -> MemoryEntry:
    """Adds an entry, or returns the existing one if the same content
    (exact match) was already stored under the same type (§11.5)."""
    content_hash = _hash(content)
    existing = session.execute(
        select(MemoryEntry).where(
            MemoryEntry.type == type_, MemoryEntry.content_hash == content_hash
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = MemoryEntry(
        id=str(uuid.uuid4()),
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


def list_memories(session: Session, *, type_: str | None = None) -> list[MemoryEntry]:
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if type_:
        stmt = stmt.where(MemoryEntry.type == type_)
    return list(session.execute(stmt).scalars())


def get_memory(session: Session, memory_id: str) -> MemoryEntry | None:
    return session.get(MemoryEntry, memory_id)


def delete_memory(session: Session, memory_id: str) -> bool:
    entry = session.get(MemoryEntry, memory_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True
