"""FastAPI routes for the Intelligent Mission Planner (HOS-042)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from backend.mission.planner.mission_planner import MissionPlanner
from backend.mission.planner.planner_models import PlanningRequest

router = APIRouter(prefix="/planner", tags=["planner"])

_planner: Optional[MissionPlanner] = None


def create_planner_routes(planner: MissionPlanner) -> APIRouter:
    global _planner
    _planner = planner
    return router


def _ensure_planner():
    if _planner is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Planner not initialized")


@router.post("/plan")
async def plan_mission(payload: dict = Body(...)):
    """Plan a new mission from a user request."""
    _ensure_planner()
    request = PlanningRequest(
        user_request=payload.get("user_request", ""),
        objective=payload.get("objective", ""),
        context=payload.get("context", {}),
        repository=payload.get("repository", ""),
        branch=payload.get("branch", ""),
        github_issue=payload.get("github_issue", ""),
        specification=payload.get("specification", ""),
        documentation=payload.get("documentation", ""),
        max_duration_hours=payload.get("max_duration_hours", 0.0),
        tags=payload.get("tags", []),
    )
    result = _planner.plan(request)
    return _planning_result_to_dict(result)


@router.post("/plan/template/{template_id}")
async def plan_from_template(template_id: str, payload: dict = Body(...)):
    """Plan a mission using a predefined template."""
    _ensure_planner()
    request = PlanningRequest(
        user_request=payload.get("user_request", ""),
        objective=payload.get("objective", ""),
        context=payload.get("context", {}),
        tags=payload.get("tags", []),
    )
    result = _planner.plan_from_template(template_id, request)
    return _planning_result_to_dict(result)


@router.get("/results")
async def list_results():
    """List all planning results."""
    _ensure_planner()
    return {"results": _planner.list_results(), "total": len(_planner.list_results())}


@router.get("/results/{result_id}")
async def get_result(result_id: str):
    """Get a specific planning result."""
    _ensure_planner()
    result = _planner.get_result(result_id)
    if result is None:
        return {"error": "Result not found"}
    return _planning_result_to_dict(result)


@router.post("/results/{result_id}/build")
async def build_mission(result_id: str, payload: dict = Body({})):
    """Build an executable Mission from a planning result."""
    _ensure_planner()
    result = _planner.get_result(result_id)
    if result is None:
        return {"error": "Result not found"}
    if not result.validation or not result.validation.valid:
        return {"error": "Cannot build mission from invalid plan", "issues": result.errors}

    mission = _planner.build_mission(
        result,
        title=payload.get("title", "Planned Mission"),
        objective=payload.get("objective", ""),
    )
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
    }


@router.get("/templates")
async def list_templates():
    """List available mission templates."""
    _ensure_planner()
    return {"templates": _planner.list_templates(), "total": len(_planner.list_templates())}


def _planning_result_to_dict(result):
    return {
        "result_id": result.result_id,
        "request_id": result.request_id,
        "mission_id": result.mission_id,
        "current_stage": result.current_stage.value,
        "stages": [s.value for s in result.stages],
        "total_nodes": result.total_nodes,
        "estimated_total_duration_hours": result.estimated_total_duration_hours,
        "overall_risk": result.overall_risk.value,
        "task_breakdowns": [
            {
                "task_id": bd.task_id,
                "title": bd.title,
                "description": bd.description,
                "category": bd.category.value,
                "depends_on": bd.depends_on,
                "order": bd.order,
                "is_critical_path": bd.is_critical_path,
            }
            for bd in result.task_breakdowns
        ],
        "dependency_graph": result.dependency_graph,
        "parallel_groups": result.parallel_groups,
        "complexity_estimates": {
            tid: {
                "complexity_score": est.complexity_score,
                "complexity_level": est.complexity_level,
                "estimated_duration_hours": est.estimated_duration_hours,
                "estimated_vram_gb": est.estimated_vram_gb,
                "estimated_ram_gb": est.estimated_ram_gb,
                "risk_level": est.risk_level.value,
                "suggested_priority": est.suggested_priority,
                "confidence": est.confidence,
            }
            for tid, est in result.complexity_estimates.items()
        },
        "runtime_recommendations": {
            tid: {
                "model_name": rec.model_name,
                "benchmark_profile": rec.benchmark_profile,
                "priority": rec.priority,
                "confidence": rec.confidence,
                "reasoning": rec.reasoning,
                "alternatives": rec.alternatives,
            }
            for tid, rec in result.runtime_recommendations.items()
        },
        "validation": {
            "valid": result.validation.valid,
            "issues": result.validation.issues,
            "warnings": result.validation.warnings,
        } if result.validation else None,
        "errors": result.errors,
        "created_at": result.created_at.isoformat(),
    }
