"""Learning Engine for the Runtime Intelligence Layer (HOS-037).

Ties together DecisionMemory, PerformanceAnalyzer, and RuntimeScorer.
Provides incremental learning: after each task, record the outcome and adjust weights.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.runtime.intelligence.decision_memory import DecisionMemory
from backend.runtime.intelligence.intelligence_models import (
    DecisionRecord,
    Recommendation,
    RuntimeScore,
    TaskContext,
    TaskStatus,
)
from backend.runtime.intelligence.performance_analyzer import PerformanceAnalyzer
from backend.runtime.intelligence.runtime_scorer import RuntimeScorer


class LearningEngine:
    """Incremental learning engine for runtime intelligence.

    Hooks into runtime events to learn from outcomes and improve future decisions.
    Thread-safe.
    """

    def __init__(
        self,
        memory: Optional[DecisionMemory] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._memory = memory or DecisionMemory()
        self._analyzer = PerformanceAnalyzer(self._memory)
        self._scorer = RuntimeScorer(self._memory, self._analyzer)
        self._on_event = on_event

    # ── Record Outcomes ────────────────────────────────────

    def on_runtime_completed(
        self,
        runtime_id: str,
        model_name: str,
        task_type: str,
        duration_ms: float,
        resource_cost: Optional[dict] = None,
        success: bool = True,
    ) -> None:
        """Handle a completed runtime execution."""
        record = DecisionRecord(
            runtime_id=runtime_id,
            model_name=model_name,
            task_type=task_type,
            status=TaskStatus.SUCCESS if success else TaskStatus.FAILURE,
            duration_ms=duration_ms,
            resource_cost=resource_cost or {},
        )
        with self._lock:
            self._memory.record(record)

        # Update score
        score = self._scorer.get_runtime_score(runtime_id)

        # Publish intelligence.score_updated
        if self._on_event:
            self._on_event(
                "intelligence.score_updated",
                {
                    "runtime_id": runtime_id,
                    "composite_score": score.composite_score,
                    "total_executions": score.total_executions,
                },
                severity="info",
            )

    def on_runtime_failed(
        self,
        runtime_id: str,
        model_name: str,
        task_type: str,
        duration_ms: float,
        error: str = "",
    ) -> None:
        """Handle a failed runtime execution."""
        self.on_runtime_completed(
            runtime_id=runtime_id,
            model_name=model_name,
            task_type=task_type,
            duration_ms=duration_ms,
            success=False,
        )

    def on_routine_decision(
        self,
        runtime_id: str,
        model_name: str,
        task_type: str,
        decision_data: Optional[dict] = None,
    ) -> None:
        """Record a routing decision (before execution)."""
        record = DecisionRecord(
            runtime_id=runtime_id,
            model_name=model_name,
            task_type=task_type,
            status=TaskStatus.SUCCESS,  # Optimistic; updated on completion
            params=decision_data or {},
        )
        with self._lock:
            self._memory.record(record)

    def on_recovery_completed(
        self,
        runtime_id: str,
        attempt_data: Optional[dict] = None,
    ) -> None:
        """Record a successful recovery."""
        record = DecisionRecord(
            runtime_id=runtime_id,
            model_name="recovery",
            task_type="recovery",
            status=TaskStatus.FALLBACK,
            params=attempt_data or {},
        )
        with self._lock:
            self._memory.record(record)

    # ── Scoring & Recommendations ──────────────────────────

    def get_score(self, runtime_id: str) -> Optional[RuntimeScore]:
        """Get the current score for a runtime."""
        records = self._memory.get_by_runtime(runtime_id)
        if not records:
            return None
        return self._scorer.get_runtime_score(runtime_id)

    def get_all_scores(self) -> list[RuntimeScore]:
        """Get scores for all known runtimes."""
        return self._scorer.get_all_scores()

    def recommend(
        self,
        task_type: str = "",
        max_latency_ms: Optional[float] = None,
        priority: int = 0,
    ) -> Optional[Recommendation]:
        """Recommend the best runtime for a task."""
        context = TaskContext(
            task_type=task_type,
            priority=priority,
            max_latency_ms=max_latency_ms,
        )
        rec = self._scorer.recommend_runtime(context)
        if rec and self._on_event:
            self._on_event(
                "intelligence.recommendation_created",
                {
                    "runtime_id": rec.runtime_id,
                    "score": rec.score,
                    "confidence": rec.confidence,
                    "alternatives": [a[0] for a in rec.alternatives],
                },
                severity="info",
            )
        return rec

    def compare(self, runtime_a: str, runtime_b: str) -> dict:
        """Compare two runtimes."""
        return self._scorer.compare_runtimes(runtime_a, runtime_b)

    # ── Config ─────────────────────────────────────────────

    def set_weights(
        self,
        performance: float = 0.35,
        reliability: float = 0.40,
        efficiency: float = 0.25,
    ) -> None:
        """Adjust scoring weights."""
        self._scorer.set_weights(performance, reliability, efficiency)

    def get_stats(self, runtime_id: str) -> dict:
        """Get raw stats for a runtime."""
        return self._memory.get_stats(runtime_id)

    @property
    def total_decisions(self) -> int:
        return self._memory.count()
