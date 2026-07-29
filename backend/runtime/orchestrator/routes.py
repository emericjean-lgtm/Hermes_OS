"""FastAPI routes for the Adaptive Runtime Orchestrator (HOS-038)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.orchestrator.decision_models import PriorityLevel
from backend.runtime.orchestrator.runtime_orchestrator import RuntimeOrchestrator

router = APIRouter(prefix="/runtime/orchestrator", tags=["runtime-orchestrator"])

_orchestrator: Optional[RuntimeOrchestrator] = None


def create_orchestrator_routes(orch: RuntimeOrchestrator) -> APIRouter:
    global _orchestrator
    _orchestrator = orch
    return router


@router.get("/history")
async def get_history(limit: int = Query(20, ge=1, le=200)):
    if _orchestrator is None:
        return {"decisions": [], "total": 0}

    decisions = _orchestrator.get_history(limit)
    return {
        "decisions": [
            {
                "decision_id": d.decision_id,
                "selected_runtime": d.selected_runtime,
                "status": d.status.value,
                "priority": d.priority.value,
                "confidence": d.confidence,
                "candidates_count": len(d.candidates),
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions
        ],
        "total": len(decisions),
    }


@router.get("/decision/{decision_id}")
async def get_decision(decision_id: str):
    if _orchestrator is None:
        return {"error": "RuntimeOrchestrator not initialised"}

    decision = _orchestrator.get_decision(decision_id)
    if decision is None:
        return {"error": "Decision not found"}

    return {
        "decision_id": decision.decision_id,
        "selected_runtime": decision.selected_runtime,
        "priority": decision.priority.value,
        "status": decision.status.value,
        "confidence": decision.confidence,
        "candidates": [
            {
                "runtime_id": c.runtime_id,
                "final_score": c.final_score,
                "intelligence_score": c.intelligence_score,
                "health_status": c.health_status,
                "resource_load_pct": c.resource_load_pct,
                "eliminated": c.eliminated,
                "elimination_reason": c.elimination_reason,
            }
            for c in sorted(decision.candidates, key=lambda x: x.final_score, reverse=True)
        ],
        "explanation": _orchestrator.explain(decision_id),
        "created_at": decision.created_at.isoformat(),
    }


@router.post("/evaluate")
async def evaluate(
    priority: str = Query("normal", description="critical|high|normal|background"),
    task_type: str = Query("", description="Task type for context"),
):
    if _orchestrator is None:
        return {"error": "RuntimeOrchestrator not initialised"}

    try:
        prio = PriorityLevel(priority)
    except ValueError:
        prio = PriorityLevel.NORMAL

    decision = _orchestrator.evaluate(
        task_context={"task_type": task_type},
        priority=prio,
    )

    if decision is None:
        return {"error": "No runtimes registered"}

    return {
        "decision_id": decision.decision_id,
        "selected_runtime": decision.selected_runtime,
        "status": decision.status.value,
        "confidence": decision.confidence,
        "candidates_count": len(decision.candidates),
    }
