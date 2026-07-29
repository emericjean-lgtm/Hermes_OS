"""Document Memory for HOS-047 — indexed documentation, code, specs, architecture."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.memory_models import DocumentMemory


class DocumentMemoryStore:
    """Thread-safe document indexer.

    Supports markdown, code, README, specs, architecture docs.
    Chunked for RAG preparation.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._documents: dict[str, list[DocumentMemory]] = {}  # title → chunks

    def index(self, doc: DocumentMemory) -> DocumentMemory:
        with self._lock:
            self._documents.setdefault(doc.title, []).append(doc)
        if self._on_event:
            self._on_event("memory.indexed", {"type": "document", "title": doc.title}, severity="info")
        return doc

    def search(self, query: str, limit: int = 10) -> list[DocumentMemory]:
        q = query.lower()
        results: list[DocumentMemory] = []
        with self._lock:
            for chunks in self._documents.values():
                for doc in chunks:
                    if q in doc.title.lower() or q in doc.content.lower() or q in doc.summary.lower() or any(q in t.lower() for t in doc.tags):
                        results.append(doc)
        return results[:limit]

    def get_by_title(self, title: str) -> list[DocumentMemory]:
        return list(self._documents.get(title, []))

    def get_by_mission(self, mission_id: str) -> list[DocumentMemory]:
        with self._lock:
            results = []
            for chunks in self._documents.values():
                for doc in chunks:
                    if doc.mission_id == mission_id:
                        results.append(doc)
        return results

    def get_all(self) -> list[DocumentMemory]:
        with self._lock:
            return [doc for chunks in self._documents.values() for doc in chunks]

    def stats(self) -> dict:
        with self._lock:
            total_chunks = sum(len(c) for c in self._documents.values())
            return {"total_documents": len(self._documents), "total_chunks": total_chunks}
