"""Autonomous Core integration adapter for Model Intelligence (HOS-065B).

Connects AdaptiveRouter to AutonomousDecisionEngine for goal-driven
model selection with decision events and explanations.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .adaptive_router import AdaptiveRouter
from .model_intelligence_models import ModelDecision, TaskContext, TaskType


@dataclass
class AutonomousModelDecision:
    """Extended model decision for autonomous missions."""

    goal_id: str
    goal_phase: str
    model_decision: ModelDecision
    execution_plan: dict[str, Any] = field(default_factory=dict)
    alternative_decisions: list[ModelDecision] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mission_id: str = ""


@dataclass
class ModelExecutionFeedback:
    """Feedback from model execution in an autonomous mission."""

    goal_id: str
    model_id: str
    task_type: str
    duration_ms: float
    tokens_used: int
    success: bool
    errors: list[str] = field(default_factory=list)
    validation_score: float = 0.0
    human_approved: bool = False
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Event constants
EVENT_MODEL_DECISION_CREATED = "model.decision.created"
EVENT_MODEL_SELECTION_COMPLETED = "model.selection.completed"
EVENT_MODEL_PERFORMANCE_UPDATED = "model.performance.updated"
EVENT_MODEL_ROUTING_OPTIMIZED = "model.routing.optimized"


class ModelAutonomousAdapter:
    """Bridges Model Intelligence with Autonomous Core (HOS-063)."""

    def __init__(
        self,
        adaptive_router: AdaptiveRouter | None = None,
        on_event: callable | None = None,
    ) -> None:
        self._router = adaptive_router or AdaptiveRouter()
        self._on_event = on_event
        self._lock = threading.RLock()
        self._decision_history: list[AutonomousModelDecision] = []
        self._feedback_history: list[ModelExecutionFeedback] = []
        self._max_history = 1000

    def set_event_callback(self, callback: callable) -> None:
        """Set the event bus callback."""
        self._on_event = callback

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish event if callback is set."""
        if self._on_event:
            try:
                self._on_event(event_type, payload)
            except Exception:
                pass

    def select_model_for_goal(
        self,
        goal_id: str,
        goal_phase: str,
        task_description: str,
        task_type: str | None = None,
        constraints: dict[str, Any] | None = None,
        max_vram_mb: int | None = None,
        mission_id: str = "",
    ) -> AutonomousModelDecision:
        """Select optimal model for an autonomous mission goal."""
        # Build task context
        tt = TaskType.GENERAL
        if task_type:
            try:
                tt = TaskType(task_type)
            except ValueError:
                pass
        context = TaskContext(
            task_type=tt,
            max_vram_mb=max_vram_mb or 8192,
        )

        # Get recommendation
        if max_vram_mb:
            context.max_vram_mb = max_vram_mb
        decision = self._router.recommend(context)

        # Get alternatives with different models
        alternatives = self._get_alternatives(decision, context, max_vram_mb)

        # Build execution plan
        execution_plan = {
            "model": decision.model_id,
            "runtime": decision.runtime.value if hasattr(decision.runtime, "value") else str(decision.runtime),
            "quantization": decision.quantization.value if hasattr(decision.quantization, "value") else str(decision.quantization),
            "max_vram_mb": max_vram_mb,
            "confidence": decision.confidence,
            "task_type": context.task_type.value if hasattr(context.task_type, "value") else str(context.task_type),
        }

        auto_decision = AutonomousModelDecision(
            goal_id=goal_id,
            goal_phase=goal_phase,
            model_decision=decision,
            execution_plan=execution_plan,
            alternative_decisions=alternatives,
            mission_id=mission_id,
        )

        with self._lock:
            self._decision_history.append(auto_decision)
            if len(self._decision_history) > self._max_history:
                self._decision_history.pop(0)

        self._publish(EVENT_MODEL_DECISION_CREATED, {
            "goal_id": goal_id,
            "model_id": decision.model_id,
            "confidence": decision.confidence,
            "mission_id": mission_id,
        })

        return auto_decision

    def record_feedback(self, feedback: ModelExecutionFeedback) -> None:
        """Record execution feedback and update model performance."""
        with self._lock:
            self._feedback_history.append(feedback)
            if len(self._feedback_history) > self._max_history:
                self._feedback_history.pop(0)

        # Update model profiler with performance data
        if self._router and self._router._profiler:
            from .model_intelligence_models import ModelPerformanceRecord, TaskType
            try:
                tt = TaskType(feedback.task_type) if feedback.task_type in [t.value for t in TaskType] else TaskType.GENERAL
                record = ModelPerformanceRecord(
                    model_id=feedback.model_id,
                    task_type=tt,
                    duration_ms=feedback.duration_ms,
                    tokens_used=feedback.tokens_used,
                    success=feedback.success,
                    errors="; ".join(feedback.errors) if feedback.errors else "",
                )
                self._router._profiler.update_performance(record)
            except Exception:
                pass

        self._publish(EVENT_MODEL_PERFORMANCE_UPDATED, {
            "goal_id": feedback.goal_id,
            "model_id": feedback.model_id,
            "success": feedback.success,
            "duration_ms": feedback.duration_ms,
        })

    def record_selection_completed(self, goal_id: str, model_id: str, success: bool) -> None:
        """Record that model selection completed."""
        self._publish(EVENT_MODEL_SELECTION_COMPLETED, {
            "goal_id": goal_id,
            "model_id": model_id,
            "success": success,
        })

    def _get_alternatives(
        self,
        decision: ModelDecision,
        context: TaskContext,
        max_vram_mb: int | None = None,
    ) -> list[ModelDecision]:
        """Get alternative model decisions."""
        alternatives: list[ModelDecision] = []
        if not self._router or not self._router._profiler:
            return alternatives

        profiles = self._router._profiler.get_models_for_task(
            context.task_type, max_vram_mb=max_vram_mb or 8192
        )
        for profile in profiles[:3]:
            if profile.model_id != decision.model_id:
                alt = ModelDecision(
                    model_id=profile.model_id,
                    model_name=profile.name,
                    runtime=decision.runtime,
                    quantization=decision.quantization,
                    confidence=profile.overall_score * 0.9,
                    reason="Alternative recommendation",
                )
                alternatives.append(alt)
        return alternatives

    def get_decision_history(
        self, goal_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get decision history, optionally filtered by goal_id."""
        with self._lock:
            decisions = self._decision_history
            if goal_id:
                decisions = [d for d in decisions if d.goal_id == goal_id]
            return [
                {
                    "goal_id": d.goal_id,
                    "goal_phase": d.goal_phase,
                    "model_id": d.model_decision.model_id,
                    "model_name": d.model_decision.model_name,
                    "confidence": d.model_decision.confidence,
                    "reason": d.model_decision.reason,
                    "runtime": str(d.model_decision.runtime),
                    "quantization": str(d.model_decision.quantization),
                    "created_at": d.created_at,
                    "mission_id": d.mission_id,
                }
                for d in decisions[-limit:]
            ]

    def get_stats(self) -> dict[str, Any]:
        """Get adapter statistics."""
        with self._lock:
            total_decisions = len(self._decision_history)
            total_feedback = len(self._feedback_history)
            success_count = sum(1 for f in self._feedback_history if f.success)
            success_rate = success_count / max(total_feedback, 1)

            # Most used models
            model_counts: dict[str, int] = {}
            for d in self._decision_history:
                mid = d.model_decision.model_id
                model_counts[mid] = model_counts.get(mid, 0) + 1

            return {
                "total_decisions": total_decisions,
                "total_feedback": total_feedback,
                "success_rate": success_rate,
                "most_used_models": dict(sorted(model_counts.items(), key=lambda x: -x[1])[:5]),
            }
