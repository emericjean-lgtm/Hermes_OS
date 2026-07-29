"""Decision Pipeline for the Adaptive Runtime Orchestrator (HOS-038).

Combines intelligence scores, health status, and resource availability
to produce a ranked list of runtime candidates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.runtime.orchestrator.decision_models import (
    CandidateRuntime,
    DecisionExplanation,
    DecisionStatus,
    OrchestratedDecision,
    PriorityLevel,
)
from backend.runtime.orchestrator.priority_manager import PriorityManager


class DecisionPipeline:
    """Multi-factor evaluation pipeline for runtime selection.

    Combines:
    1. Intelligence scores (from LearningEngine)
    2. Health status (from HealthMonitor)
    3. Resource availability (from ResourceManager)
    4. Recovery status (from RecoveryEngine)
    """

    def __init__(
        self,
        priority_manager: Optional[PriorityManager] = None,
        get_score: Optional[Callable[[str], Optional[Any]]] = None,
        get_health: Optional[Callable[[str], str]] = None,
        get_resources: Optional[Callable[[str], int]] = None,
        is_recovering: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._pm = priority_manager or PriorityManager()
        self._get_score = get_score or (lambda rid: None)
        self._get_health = get_health or (lambda rid: "unknown")
        self._get_resources = get_resources or (lambda rid: 0)
        self._is_recovering = is_recovering or (lambda rid: False)

    # ── Main Pipeline ──────────────────────────────────────

    def evaluate_candidates(
        self,
        runtime_ids: list[str],
        task_context: Optional[dict] = None,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        on_event: Optional[Callable] = None,
    ) -> OrchestratedDecision:
        """Evaluate all candidates and select the best runtime."""
        de = OrchestratedDecision(
            task_context=task_context or {},
            priority=priority,
            status=DecisionStatus.EVALUATING,
        )

        profile = self._pm.get_profile(priority)

        # Publish analysis started
        if on_event:
            on_event(
                "routing.analysis_started",
                {"candidates": runtime_ids, "priority": priority.value},
                severity="info",
            )

        # Build candidates
        candidates: list[CandidateRuntime] = []
        for rid in runtime_ids:
            c = CandidateRuntime(runtime_id=rid)

            # Intelligence score
            score = self._get_score(rid)
            if score is not None:
                c.intelligence_score = score.composite_score if hasattr(score, "composite_score") else 0.0

            # Health
            c.health_status = self._get_health(rid)

            # Resources
            free_vram = self._get_resources(rid)
            c.available_resources = free_vram

            # Resource load (inverse of free)
            if free_vram > 0:
                c.resource_load_pct = max(0.0, 1.0 - free_vram / (16 * 1024 * 1024 * 1024))
            else:
                c.resource_load_pct = 1.0

            # Recovery
            c.recovery_active = self._is_recovering(rid)

            candidates.append(c)

        # Eliminate invalid candidates
        for c in candidates:
            # Eliminate: unhealthy
            if c.health_status in ("unavailable", "critical"):
                c.eliminated = True
                c.elimination_reason = f"Health: {c.health_status}"

            # Eliminate: resource load too high
            if c.resource_load_pct > profile["max_resource_load"]:
                c.eliminated = True
                c.elimination_reason = f"Resource load {c.resource_load_pct:.0%} > {profile['max_resource_load']:.0%}"

            # Eliminate: in recovery (unless allowed)
            if c.recovery_active and not profile["allow_recovering"]:
                c.eliminated = True
                c.elimination_reason = "Runtime in recovery"

        # Score remaining candidates
        weights = self._pm.get_weights(priority)
        for c in candidates:
            if c.eliminated:
                c.final_score = -1.0
                continue

            # Health score: healthy=100, degraded=50, unavailable=0
            health_score = {"healthy": 100.0, "degraded": 50.0}.get(
                c.health_status, 0.0
            )

            # Resource score: lower load = better
            resource_score = max(0.0, 100.0 * (1.0 - c.resource_load_pct))

            # Composite
            c.final_score = round(
                weights["intelligence"] * c.intelligence_score
                + weights["health"] * health_score
                + weights["resources"] * resource_score
                + weights["reliability_boost"] * c.intelligence_score * 0.1,
                2,
            )

        de.candidates = candidates

        # Select best non-eliminated candidate
        active = [c for c in candidates if not c.eliminated]
        if active:
            active.sort(key=lambda c: c.final_score, reverse=True)
            best = active[0]
            de.selected_runtime = best.runtime_id
            de.status = DecisionStatus.SELECTED
            de.confidence = min(95.0, best.final_score * 0.95)
            de.explanation = DecisionExplanation(
                runtime_id=best.runtime_id,
                factor_scores={
                    "intelligence": best.intelligence_score,
                    "health": 100.0 if best.health_status == "healthy" else 50.0,
                    "resources": round(100.0 * (1.0 - best.resource_load_pct)),
                    "final": best.final_score,
                },
                summary=f"Selected {best.runtime_id} (score={best.final_score:.1f}, health={best.health_status})",
            )
            if on_event:
                on_event(
                    "routing.runtime_selected",
                    {"runtime_id": best.runtime_id, "score": best.final_score},
                    severity="info",
                )
        else:
            de.status = DecisionStatus.FAILED
            de.selected_runtime = None
            de.confidence = 0.0
            if on_event:
                on_event(
                    "routing.decision_failed",
                    {"reason": "No valid candidates", "candidates": len(candidates)},
                    severity="error",
                )

        de.completed_at = datetime.now(timezone.utc)

        # Publish decision
        if on_event:
            on_event(
                "routing.decision_created",
                {
                    "decision_id": de.decision_id,
                    "selected": de.selected_runtime,
                    "status": de.status.value,
                    "confidence": de.confidence,
                },
                severity="info",
            )

        return de

    def select_runtime(
        self,
        runtime_ids: list[str],
        task_context: Optional[dict] = None,
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> Optional[str]:
        """Simplified interface: return the best runtime_id or None."""
        decision = self.evaluate_candidates(runtime_ids, task_context, priority)
        return decision.selected_runtime

    def explain_decision(self, decision: OrchestratedDecision) -> dict[str, Any]:
        """Produce a human-readable explanation of a decision."""
        if decision.explanation is None:
            return {"error": "No explanation available"}

        return {
            "selected": decision.selected_runtime,
            "confidence": decision.confidence,
            "summary": decision.explanation.summary,
            "factors": decision.explanation.factor_scores,
            "candidates": [
                {
                    "id": c.runtime_id,
                    "score": c.final_score,
                    "eliminated": c.eliminated,
                    "reason": c.elimination_reason if c.eliminated else None,
                }
                for c in sorted(decision.candidates, key=lambda x: x.final_score, reverse=True)
            ],
        }
