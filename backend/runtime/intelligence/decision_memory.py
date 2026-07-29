"""Decision Memory for the Runtime Intelligence Layer (HOS-037).

Stores past decisions for analysis and learning.
Thread-safe, in-memory with configurable capacity.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.runtime.intelligence.intelligence_models import (
    DecisionRecord,
    TaskStatus,
)


class DecisionMemory:
    """Thread-safe store of past runtime decisions.

    Used by the LearningEngine to compute scores and make recommendations.
    """

    def __init__(self, max_records: int = 10000) -> None:
        self._lock = threading.Lock()
        self._records: list[DecisionRecord] = []
        self._max_records = max_records
        # Indexes for fast query
        self._by_runtime: dict[str, list[DecisionRecord]] = defaultdict(list)
        self._by_task_type: dict[str, list[DecisionRecord]] = defaultdict(list)

    def record(self, decision: DecisionRecord) -> None:
        """Store a decision. Thread-safe."""
        with self._lock:
            self._records.append(decision)
            self._by_runtime[decision.runtime_id].append(decision)
            self._by_task_type[decision.task_type].append(decision)

            # Trim
            if len(self._records) > self._max_records:
                overflow = len(self._records) - self._max_records
                removed = self._records[:overflow]
                self._records = self._records[overflow:]
                for r in removed:
                    self._by_runtime[r.runtime_id].remove(r)
                    self._by_task_type[r.task_type].remove(r)

    def get_by_runtime(self, runtime_id: str, limit: int = 500) -> list[DecisionRecord]:
        """Return recent decisions for a runtime."""
        with self._lock:
            records = self._by_runtime.get(runtime_id, [])
            return records[-limit:]

    def get_by_task_type(self, task_type: str, limit: int = 500) -> list[DecisionRecord]:
        """Return recent decisions for a task type."""
        with self._lock:
            records = self._by_task_type.get(task_type, [])
            return records[-limit:]

    def get_stats(self, runtime_id: str) -> dict:
        """Return summary stats for a runtime."""
        records = self.get_by_runtime(runtime_id)
        if not records:
            return {
                "total": 0, "successes": 0, "failures": 0, "fallbacks": 0,
                "avg_duration_ms": 0.0, "success_rate": 0.0,
            }

        total = len(records)
        successes = sum(1 for r in records if r.status == TaskStatus.SUCCESS)
        failures = sum(1 for r in records if r.status == TaskStatus.FAILURE)
        fallbacks = sum(1 for r in records if r.status == TaskStatus.FALLBACK)
        avg_dur = sum(r.duration_ms for r in records) / total if total > 0 else 0.0

        return {
            "total": total,
            "successes": successes,
            "failures": failures,
            "fallbacks": fallbacks,
            "avg_duration_ms": round(avg_dur, 2),
            "success_rate": round(successes / total, 4) if total > 0 else 0.0,
        }

    def get_all_runtime_ids(self) -> list[str]:
        """Return all known runtime IDs."""
        with self._lock:
            return list(self._by_runtime.keys())

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._by_runtime.clear()
            self._by_task_type.clear()
