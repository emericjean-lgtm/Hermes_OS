"""FastAPI routes for the Runtime Intelligence Layer (HOS-037)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.intelligence.learning_engine import LearningEngine

router = APIRouter(prefix="/runtime/intelligence", tags=["runtime-intelligence"])

_engine: Optional[LearningEngine] = None


def create_intelligence_routes(engine: LearningEngine) -> APIRouter:
    """Factory: bind a LearningEngine to the routes."""
    global _engine
    _engine = engine
    return router


@router.get("/scores")
async def get_scores():
    """Get scores for all runtimes, sorted by composite score."""
    if _engine is None:
        return {"scores": [], "total": 0}

    scores = _engine.get_all_scores()
    return {
        "scores": [
            {
                "runtime_id": s.runtime_id,
                "composite_score": s.composite_score,
                "performance_score": s.performance_score,
                "reliability_score": s.reliability_score,
                "resource_efficiency": s.resource_efficiency,
                "total_executions": s.total_executions,
                "successes": s.successes,
                "failures": s.failures,
                "fallbacks": s.fallbacks,
                "avg_duration_ms": s.avg_duration_ms,
                "success_rate": round(s.success_rate * 100, 1),
            }
            for s in scores
        ],
        "total": len(scores),
    }


@router.get("/{runtime_id}")
async def get_runtime_detail(runtime_id: str):
    """Get detailed score and stats for a specific runtime."""
    if _engine is None:
        return {"error": "LearningEngine not initialised"}

    score = _engine.get_score(runtime_id)
    if score is None:
        return {"error": f"No data for runtime {runtime_id}"}

    stats = _engine.get_stats(runtime_id)
    return {
        "runtime_id": score.runtime_id,
        "composite_score": score.composite_score,
        "performance_score": score.performance_score,
        "reliability_score": score.reliability_score,
        "resource_efficiency": score.resource_efficiency,
        "success_rate": round(score.success_rate * 100, 1),
        "avg_duration_ms": score.avg_duration_ms,
        "totals": {
            "executions": stats["total"],
            "successes": stats["successes"],
            "failures": stats["failures"],
            "fallbacks": stats["fallbacks"],
        },
        "last_updated": score.last_updated.isoformat(),
    }


@router.get("/recommendations")
async def get_recommendations(
    task_type: str = Query("", description="Task type for recommendation"),
    max_latency_ms: Optional[float] = Query(None, description="Max acceptable latency in ms"),
    priority: int = Query(0, description="Task priority (0-10)"),
):
    """Get a runtime recommendation for the given task context."""
    if _engine is None:
        return {"error": "LearningEngine not initialised"}

    rec = _engine.recommend(
        task_type=task_type,
        max_latency_ms=max_latency_ms,
        priority=priority,
    )
    if rec is None:
        return {"recommendation": None, "reason": "No runtime data available"}

    return {
        "recommendation": {
            "runtime_id": rec.runtime_id,
            "score": rec.score,
            "confidence": rec.confidence,
            "reasoning": rec.reasoning,
            "alternatives": [
                {"runtime_id": alt[0], "score": alt[1]} for alt in rec.alternatives
            ],
        }
    }
