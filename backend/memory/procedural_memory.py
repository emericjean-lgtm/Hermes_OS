"""Procedural Memory for HOS-047 — workflows, best practices, templates, strategies."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.memory_models import ProceduralMemory


class ProceduralMemoryStore:
    """Thread-safe store of proven procedures and workflows.

    Versioned. Tracks usage count and success rate.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._procedures: dict[str, list[ProceduralMemory]] = {}  # name → versions
        self._by_category: dict[str, list[str]] = {}

    def store(self, procedure: ProceduralMemory) -> ProceduralMemory:
        with self._lock:
            self._procedures.setdefault(procedure.name, []).append(procedure)
            self._by_category.setdefault(procedure.category, []).append(procedure.procedure_id)
        if self._on_event:
            self._on_event("memory.created", {"type": "procedural", "name": procedure.name}, severity="info")
        return procedure

    def get_latest(self, name: str) -> Optional[ProceduralMemory]:
        versions = self._procedures.get(name, [])
        return versions[-1] if versions else None

    def get_versions(self, name: str) -> list[ProceduralMemory]:
        return list(self._procedures.get(name, []))

    def search(self, query: str, limit: int = 10) -> list[ProceduralMemory]:
        q = query.lower()
        results: list[ProceduralMemory] = []
        with self._lock:
            for versions in self._procedures.values():
                latest = versions[-1]
                if q in latest.name.lower() or q in latest.description.lower() or any(q in t.lower() for t in latest.tags):
                    results.append(latest)
        return sorted(results, key=lambda p: (p.success_rate, p.usage_count), reverse=True)[:limit]

    def get_by_category(self, category: str) -> list[ProceduralMemory]:
        with self._lock:
            ids = set(self._by_category.get(category, []))
            results = []
            for versions in self._procedures.values():
                if versions[-1].procedure_id in ids:
                    results.append(versions[-1])
        return results

    def record_usage(self, name: str, success: bool) -> bool:
        latest = self.get_latest(name)
        if latest is None:
            return False
        with self._lock:
            latest.usage_count += 1
            if success:
                latest.success_rate = (latest.success_rate * (latest.usage_count - 1) + 1) / latest.usage_count
            else:
                latest.success_rate = (latest.success_rate * (latest.usage_count - 1)) / latest.usage_count
        return True

    def get_all(self) -> list[ProceduralMemory]:
        with self._lock:
            return [v[-1] for v in self._procedures.values() if v]

    def stats(self) -> dict:
        with self._lock:
            return {"total_procedures": len(self._procedures),
                    "total_versions": sum(len(v) for v in self._procedures.values()),
                    "categories": {k: len(v) for k, v in self._by_category.items()}}
