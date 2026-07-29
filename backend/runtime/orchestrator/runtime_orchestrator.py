"""Runtime Orchestrator — Adaptive Runtime Orchestrator (HOS-038).

Final orchestration layer combining all runtime decisions.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Optional

from backend.runtime.orchestrator.decision_models import (
    DecisionStatus,
    OrchestratedDecision,
    PriorityLevel,
)
from backend.runtime.orchestrator.decision_pipeline import DecisionPipeline
from backend.runtime.orchestrator.priority_manager import PriorityManager


class RuntimeOrchestrator:
    """Central orchestrator that combines all runtime subsystems.

    Integrates:
    - RuntimeScorer (intelligence)
    - HealthMonitor
    - ResourceManager
    - RecoveryEngine

    Through configurable callbacks, keeping the architecture decoupled.
    Thread-safe.
    """

    def __init__(
        self,
        priority_manager: Optional[PriorityManager] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._pm = priority_manager or PriorityManager()
        self._on_event = on_event
        self._history: list[OrchestratedDecision] = []

        # Subsystem callbacks (set via configure)
        self._get_score: Callable[[str], Optional[Any]] = lambda rid: None
        self._get_health: Callable[[str], str] = lambda rid: "unknown"
        self._get_resources: Callable[[str], int] = lambda rid: 0
        self._is_recovering: Callable[[str], bool] = lambda rid: False

        # Known runtime IDs
        self._runtime_ids: list[str] = []

    # ── Configuration ──────────────────────────────────────

    def configure(
        self,
        runtime_ids: list[str],
        get_score: Optional[Callable] = None,
        get_health: Optional[Callable] = None,
        get_resources: Optional[Callable] = None,
        is_recovering: Optional[Callable] = None,
    ) -> None:
        """Wire in subsystem callbacks."""
        with self._lock:
            self._runtime_ids = list(runtime_ids)
            if get_score:
                self._get_score = get_score
            if get_health:
                self._get_health = get_health
            if get_resources:
                self._get_resources = get_resources
            if is_recovering:
                self._is_recovering = is_recovering

    def register_runtime(self, runtime_id: str) -> None:
        with self._lock:
            if runtime_id not in self._runtime_ids:
                self._runtime_ids.append(runtime_id)

    # ── Decision Pipeline ──────────────────────────────────

    def evaluate(
        self,
        task_context: Optional[dict] = None,
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> Optional[OrchestratedDecision]:
        """Evaluate all known runtimes and select the best one."""
        with self._lock:
            runtime_ids = list(self._runtime_ids)

        if not runtime_ids:
            return None

        pipeline = DecisionPipeline(
            priority_manager=self._pm,
            get_score=self._get_score,
            get_health=self._get_health,
            get_resources=self._get_resources,
            is_recovering=self._is_recovering,
        )

        decision = pipeline.evaluate_candidates(
            runtime_ids,
            task_context=task_context,
            priority=priority,
            on_event=self._on_event,
        )

        with self._lock:
            self._history.append(decision)
            if len(self._history) > 500:
                self._history = self._history[-500:]

        return decision

    def select(
        self,
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> Optional[str]:
        """Select the best runtime (shortcut)."""
        decision = self.evaluate(priority=priority)
        return decision.selected_runtime if decision else None

    # ── Query ───────────────────────────────────────────────

    def get_decision(self, decision_id: str) -> Optional[OrchestratedDecision]:
        """Retrieve a past decision by ID."""
        with self._lock:
            for d in self._history:
                if d.decision_id == decision_id:
                    return d
        return None

    def get_history(self, limit: int = 20) -> list[OrchestratedDecision]:
        """Return recent decisions."""
        with self._lock:
            return self._history[-limit:]

    def explain(self, decision_id: str) -> Optional[dict]:
        """Explain a decision."""
        decision = self.get_decision(decision_id)
        if decision is None:
            return None
        pipeline = DecisionPipeline(
            priority_manager=self._pm,
        )
        return pipeline.explain_decision(decision)

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return orchestrator statistics."""
        with self._lock:
            selected = sum(1 for d in self._history if d.status == DecisionStatus.SELECTED)
            failed = sum(1 for d in self._history if d.status == DecisionStatus.FAILED)
            return {
                "total_decisions": len(self._history),
                "selected": selected,
                "failed": failed,
                "known_runtimes": len(self._runtime_ids),
                "runtime_ids": list(self._runtime_ids),
                "success_rate": round(selected / max(len(self._history), 1) * 100, 1),
            }
