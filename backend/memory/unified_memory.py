"""Unified Memory Intelligence Layer (HOS-021).

Centralises all memory stores in Hermes OS — session, mission, agent,
project, user, global and experience scopes — behind a single facade.

The layer exposes an abstract :class:`MemoryBackend` interface so that
future PRs can swap the in-memory store for SQLite, Vector DB,
Alexandrie, etc., without changing the callers.

No concrete RAG or vector-store engine is imported here.
"""
from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class MemoryScope(str, Enum):
    """Canonical memory scopes in Hermes OS.

    Scopes define the visibility and lifetime of a memory entry.
    """

    SESSION = "session"
    MISSION = "mission"
    AGENT = "agent"
    PROJECT = "project"
    USER = "user"
    GLOBAL = "global"
    EXPERIENCE = "experience"


class MemoryEvent(str, Enum):
    """Events emitted by the unified memory on write operations."""

    STORED = "memory.stored"
    UPDATED = "memory.updated"
    DELETED = "memory.deleted"
    IMPORTED = "memory.imported"
    EXPORTED = "memory.exported"


class UnifiedMemoryError(Exception):
    """Raised when a memory operation cannot be completed."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryEntry:
    """An immutable memory entry.

    Attributes:
        id: Unique entry identifier.
        scope: Memory scope.
        title: Short title.
        content: Full content.
        tags: Set of tags for filtering.
        importance: Importance level 1-10.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        metadata: Free-form payload.
    """

    id: str
    scope: MemoryScope | str
    title: str = ""
    content: str = ""
    tags: frozenset[str] = frozenset()
    importance: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryQuery:
    """Parameters for searching memory entries.

    All fields are optional — an empty query returns all entries.

    Attributes:
        scope: Filter by scope.
        tags: Filter by tags (any match).
        text: Substring search in title and content (case-insensitive).
        min_importance: Minimum importance (1-10).
        since: Only entries created after this timestamp.
        until: Only entries created before this timestamp.
        metadata_filter: Dict of metadata key/value requirements.
        limit: Maximum number of results.
        offset: Pagination offset.
    """

    scope: Optional[MemoryScope | str] = None
    tags: Optional[frozenset[str]] = None
    text: Optional[str] = None
    min_importance: Optional[int] = None
    since: Optional[float] = None
    until: Optional[float] = None
    metadata_filter: Optional[dict[str, Any]] = None
    limit: Optional[int] = None
    offset: int = 0


@dataclass(frozen=True)
class MemoryResult:
    """The result of a search query.

    Attributes:
        entries: Matching entries.
        total: Total number of matching entries (before pagination).
        execution_time_ms: Query execution time in milliseconds.
    """

    entries: tuple[MemoryEntry, ...] = ()
    total: int = 0
    execution_time_ms: float = 0.0


@dataclass(frozen=True)
class MemoryStatistics:
    """Aggregated memory statistics.

    Attributes:
        total_entries: Total entries across all scopes.
        per_scope: Mapping of scope → entry count.
        total_searches: Number of search queries executed.
        avg_search_time_ms: Average search duration.
        total_imports: Number of import operations.
        total_exports: Number of export operations.
        metadata: Free-form metadata.
    """

    total_entries: int = 0
    per_scope: dict[str, int] = field(default_factory=dict)
    total_searches: int = 0
    avg_search_time_ms: float = 0.0
    total_imports: int = 0
    total_exports: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


class MemoryBackend(ABC):
    """Abstract interface for memory storage backends.

    Implement this interface to add support for SQLite, vector stores,
    Alexandrie, etc.
    """

    @abstractmethod
    def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Persist an entry. Overwrites if ``entry.id`` already exists."""

    @abstractmethod
    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Return an entry by id, or ``None``."""

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """Delete an entry. Returns ``True`` if it existed."""

    @abstractmethod
    def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Return entries matching the query."""

    @abstractmethod
    def clear_scope(self, scope: MemoryScope | str) -> int:
        """Delete all entries of a scope. Returns the count removed."""

    @abstractmethod
    def all_entries(self) -> list[MemoryEntry]:
        """Return every stored entry (for export / statistics)."""

    @abstractmethod
    def count(self) -> int:
        """Total number of entries."""

    @abstractmethod
    def count_by_scope(self) -> dict[str, int]:
        """Entries per scope."""


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryBackend(MemoryBackend):
    """Thread-safe in-memory implementation of :class:`MemoryBackend`.

    All data is held in a dict keyed by entry id. Lost on process restart.
    """

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()

    def store(self, entry: MemoryEntry) -> MemoryEntry:
        with self._lock:
            self._entries[entry.id] = entry
            return entry

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        with self._lock:
            return copy.deepcopy(self._entries.get(entry_id))

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            if entry_id in self._entries:
                del self._entries[entry_id]
                return True
            return False

    def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        with self._lock:
            results = list(self._entries.values())

        # Apply filters.
        if query.scope is not None:
            results = [e for e in results if e.scope == query.scope]
        if query.tags is not None and query.tags:
            results = [e for e in results if query.tags & e.tags]
        if query.text is not None:
            text_lower = query.text.lower()
            results = [
                e for e in results
                if text_lower in e.title.lower() or text_lower in e.content.lower()
            ]
        if query.min_importance is not None:
            results = [e for e in results if e.importance >= query.min_importance]
        if query.since is not None:
            results = [e for e in results if e.created_at >= query.since]
        if query.until is not None:
            results = [e for e in results if e.created_at <= query.until]
        if query.metadata_filter is not None:
            for key, value in query.metadata_filter.items():
                results = [
                    e for e in results
                    if e.metadata.get(key) == value
                ]

        # Sort by created_at descending.
        results.sort(key=lambda e: e.created_at, reverse=True)

        total = len(results)

        # Pagination.
        start = min(query.offset, len(results))
        end = None
        if query.limit is not None:
            end = start + query.limit
        results = results[start:end]

        return results

    def clear_scope(self, scope: MemoryScope | str) -> int:
        with self._lock:
            before = len(self._entries)
            self._entries = {
                eid: entry
                for eid, entry in self._entries.items()
                if entry.scope != scope
            }
            return before - len(self._entries)

    def all_entries(self) -> list[MemoryEntry]:
        with self._lock:
            return copy.deepcopy(list(self._entries.values()))

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def count_by_scope(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = defaultdict(int)
            for entry in self._entries.values():
                scope = entry.scope if isinstance(entry.scope, str) else entry.scope.value
                counts[scope] += 1
            return dict(counts)


# ---------------------------------------------------------------------------
# Unified Memory (facade)
# ---------------------------------------------------------------------------


Handler = Callable[[MemoryEvent, MemoryEntry], None]


class UnifiedMemory:
    """Thread-safe facade over a :class:`MemoryBackend`.

    Provides the public Hermes OS memory API with event emission,
    statistics tracking, and serialisation helpers.

    Args:
        backend: Storage backend. Defaults to :class:`InMemoryBackend`.
    """

    def __init__(self, backend: Optional[MemoryBackend] = None) -> None:
        self._backend = backend or InMemoryBackend()
        self._lock = threading.RLock()
        self._handlers: list[Handler] = []
        self._search_count = 0
        self._search_time_total = 0.0
        self._import_count = 0
        self._export_count = 0

    def on_event(self, handler: Handler) -> None:
        """Register a callback ``(event: MemoryEvent, entry: MemoryEntry)``."""
        with self._lock:
            self._handlers.append(handler)

    def store(
        self,
        content: str,
        *,
        scope: MemoryScope | str = MemoryScope.SESSION,
        title: str = "",
        tags: Optional[frozenset[str]] = None,
        importance: int = 1,
        entry_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store a new entry.

        Args:
            content: The content to store.
            scope: Memory scope.
            title: Optional title.
            tags: Optional tags.
            importance: Importance 1-10.
            entry_id: Optional explicit id. Auto-generated if not given.
            metadata: Optional metadata.

        Returns:
            The stored entry.
        """
        now = time.time()
        entry = MemoryEntry(
            id=entry_id or uuid.uuid4().hex,
            scope=scope,
            title=title,
            content=content,
            tags=tags or frozenset(),
            importance=importance,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._backend.store(entry)
        self._emit(MemoryEvent.STORED, entry)
        return entry

    def update(
        self,
        entry_id: str,
        *,
        content: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[frozenset[str]] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Update an existing entry.

        Args:
            entry_id: Entry to update.
            content: New content (if changed).
            title: New title (if changed).
            tags: New tags (if changed).
            importance: New importance (if changed).
            metadata: Merged into existing metadata.

        Returns:
            The updated entry.

        Raises:
            UnifiedMemoryError: If the entry does not exist.
        """
        existing = self._backend.get(entry_id)
        if existing is None:
            raise UnifiedMemoryError(f"Entry '{entry_id}' not found.")

        merged_meta = dict(existing.metadata)
        if metadata is not None:
            merged_meta.update(metadata)

        updated = MemoryEntry(
            id=existing.id,
            scope=existing.scope,
            title=title if title is not None else existing.title,
            content=content if content is not None else existing.content,
            tags=tags if tags is not None else existing.tags,
            importance=importance if importance is not None else existing.importance,
            created_at=existing.created_at,
            updated_at=time.time(),
            metadata=merged_meta,
        )
        self._backend.store(updated)
        self._emit(MemoryEvent.UPDATED, updated)
        return updated

    def delete(self, entry_id: str) -> bool:
        """Delete an entry by id.

        Args:
            entry_id: Entry to delete.

        Returns:
            ``True`` if the entry existed.
        """
        removed = self._backend.delete(entry_id)
        if removed:
            # Emit a pseudo-entry for the event.
            self._emit(
                MemoryEvent.DELETED,
                MemoryEntry(id=entry_id, scope=MemoryScope.SESSION),
            )
        return removed

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve an entry by id.

        Args:
            entry_id: Entry identifier.

        Returns:
            The entry, or ``None``.
        """
        return self._backend.get(entry_id)

    def search(
        self,
        query: MemoryQuery,
    ) -> MemoryResult:
        """Search entries.

        Args:
            query: Search parameters.

        Returns:
            A :class:`MemoryResult` with matching entries.
        """
        start = time.monotonic()
        entries = self._backend.search(query)
        elapsed = (time.monotonic() - start) * 1000

        with self._lock:
            self._search_count += 1
            self._search_time_total += elapsed

        total = len(entries)
        # We need the full count before pagination. For InMemoryBackend,
        # search already handles pagination internally. Re-run without
        # pagination for accurate count.
        full_query = MemoryQuery(
            scope=query.scope,
            tags=query.tags,
            text=query.text,
            min_importance=query.min_importance,
            since=query.since,
            until=query.until,
            metadata_filter=query.metadata_filter,
        )
        all_matching = self._backend.search(full_query)

        return MemoryResult(
            entries=tuple(entries),
            total=len(all_matching),
            execution_time_ms=elapsed,
        )

    def clear_scope(self, scope: MemoryScope | str) -> int:
        """Delete all entries of a given scope.

        Args:
            scope: The scope to clear.

        Returns:
            Number of entries removed.
        """
        return self._backend.clear_scope(scope)

    def export(
        self,
        *,
        scope: Optional[MemoryScope | str] = None,
        indent: Optional[int] = None,
    ) -> str:
        """Export entries as a JSON string.

        Args:
            scope: Optional scope filter.
            indent: JSON indentation.

        Returns:
            JSON string.
        """
        entries = self._backend.all_entries()
        if scope is not None:
            entries = [e for e in entries if e.scope == scope]

        data = []
        for e in entries:
            data.append({
                "id": e.id,
                "scope": e.scope.value if isinstance(e.scope, Enum) else e.scope,
                "title": e.title,
                "content": e.content,
                "tags": sorted(e.tags),
                "importance": e.importance,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
                "metadata": e.metadata,
            })

        with self._lock:
            self._export_count += 1
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def import_json(
        self,
        json_str: str,
    ) -> int:
        """Import entries from a JSON string produced by :meth:`export`.

        Existing entries with the same id are overwritten.

        Args:
            json_str: JSON string.

        Returns:
            Number of imported entries.
        """
        data = json.loads(json_str)
        count = 0
        for item in data:
            scope_raw = item.get("scope", "session")
            try:
                scope = MemoryScope(scope_raw)
            except ValueError:
                scope = scope_raw
            entry = MemoryEntry(
                id=item.get("id", uuid.uuid4().hex),
                scope=scope,
                title=item.get("title", ""),
                content=item.get("content", ""),
                tags=frozenset(item.get("tags", [])),
                importance=item.get("importance", 1),
                created_at=item.get("created_at", time.time()),
                updated_at=item.get("updated_at", time.time()),
                metadata=item.get("metadata", {}),
            )
            self._backend.store(entry)
            count += 1

        with self._lock:
            self._import_count += count
        return count

    def get_statistics(self) -> MemoryStatistics:
        """Return aggregated statistics.

        Returns:
            Current statistics.
        """
        total = self._backend.count()
        per_scope = self._backend.count_by_scope()
        avg_search = (
            self._search_time_total / self._search_count
            if self._search_count
            else 0.0
        )
        return MemoryStatistics(
            total_entries=total,
            per_scope=per_scope,
            total_searches=self._search_count,
            avg_search_time_ms=avg_search,
            total_imports=self._import_count,
            total_exports=self._export_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, event: MemoryEvent, entry: MemoryEntry) -> None:
        for handler in self._handlers:
            try:
                handler(event, entry)
            except Exception:
                pass
