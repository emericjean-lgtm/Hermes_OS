"""Semantic Memory for HOS-047 — concepts, technologies, frameworks, patterns."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.memory_models import SemanticMemory


class SemanticMemoryStore:
    """Thread-safe store of concepts and technologies.

    Fast retrieval by name, category, tags. Supports fuzzy matching.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._concepts: dict[str, SemanticMemory] = {}
        self._by_name: dict[str, str] = {}
        self._by_category: dict[str, list[str]] = {}

    def store(self, concept: SemanticMemory) -> SemanticMemory:
        with self._lock:
            self._concepts[concept.concept_id] = concept
            self._by_name[concept.name.lower()] = concept.concept_id
            self._by_category.setdefault(concept.category, []).append(concept.concept_id)

        if self._on_event:
            self._on_event("memory.created", {"type": "semantic", "name": concept.name}, severity="info")
        return concept

    def get_by_name(self, name: str) -> Optional[SemanticMemory]:
        with self._lock:
            cid = self._by_name.get(name.lower())
            return self._concepts.get(cid) if cid else None

    def search(self, query: str, limit: int = 10) -> list[SemanticMemory]:
        """Fuzzy search by name and tags."""
        q = query.lower()
        results: list[SemanticMemory] = []
        with self._lock:
            for c in self._concepts.values():
                if q in c.name.lower() or q in c.description.lower() or any(q in t.lower() for t in c.tags):
                    results.append(c)
        return results[:limit]

    def get_by_category(self, category: str) -> list[SemanticMemory]:
        with self._lock:
            ids = self._by_category.get(category, [])
            return [self._concepts[cid] for cid in ids if cid in self._concepts]

    def get_all(self) -> list[SemanticMemory]:
        with self._lock:
            return list(self._concepts.values())

    def stats(self) -> dict:
        with self._lock:
            return {"total": len(self._concepts),
                    "categories": {k: len(v) for k, v in self._by_category.items()}}
