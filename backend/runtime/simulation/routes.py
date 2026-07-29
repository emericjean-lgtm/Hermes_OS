"""FastAPI routes for the Runtime Simulation Engine (HOS-039)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.simulation.simulation_engine import SimulationEngine

router = APIRouter(prefix="/runtime/simulation", tags=["runtime-simulation"])

_engine: Optional[SimulationEngine] = None


def create_simulation_routes(engine: SimulationEngine) -> APIRouter:
    global _engine
    _engine = engine
    return router


@router.post("/run")
async def run_simulation(
    task_type: str = Query("default", description="chat|code|vision|reasoning|embedding"),
    task_name: str = Query("", description="Descriptive task name"),
):
    if _engine is None:
        return {"error": "SimulationEngine not initialised"}

    result = _engine.simulate_task(
        task_context={"task_type": task_type, "task_name": task_name},
        task_type=task_type,
    )
    return {
        "simulation_id": result.simulation_id,
        "status": result.status.value,
        "recommended_runtime": result.recommended_runtime,
        "overall_risk": result.overall_risk.value,
        "summary": result.summary,
        "candidates": [
            {
                "runtime_id": c.runtime_id,
                "predicted_score": c.predicted_score,
                "resource_prediction": {
                    "vram_mb": c.resource_prediction.vram_mb,
                    "ram_mb": c.resource_prediction.ram_mb,
                    "estimated_duration_ms": c.resource_prediction.estimated_duration_ms,
                    "expected_load_pct": c.resource_prediction.expected_load_pct,
                },
                "risk_level": c.risk_assessment.level.value,
                "risk_score": c.risk_assessment.score,
                "is_recommended": c.is_recommended,
                "warnings": c.warnings,
            }
            for c in result.candidates
        ],
    }


@router.get("/{simulation_id}")
async def get_simulation(simulation_id: str):
    if _engine is None:
        return {"error": "SimulationEngine not initialised"}

    result = _engine.get_simulation(simulation_id)
    if result is None:
        return {"error": "Simulation not found"}

    return {
        "simulation_id": result.simulation_id,
        "status": result.status.value,
        "recommended_runtime": result.recommended_runtime,
        "overall_risk": result.overall_risk.value,
        "summary": result.summary,
        "candidates_count": len(result.candidates),
        "created_at": result.created_at.isoformat(),
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
    }


@router.get("/history")
async def get_history(limit: int = Query(20, ge=1, le=200)):
    if _engine is None:
        return {"simulations": [], "total": 0}

    history = _engine.get_history(limit)
    return {
        "simulations": [
            {
                "simulation_id": s.simulation_id,
                "status": s.status.value,
                "recommended_runtime": s.recommended_runtime,
                "overall_risk": s.overall_risk.value,
                "summary": s.summary,
                "candidates_count": len(s.candidates),
                "created_at": s.created_at.isoformat(),
            }
            for s in history
        ],
        "total": len(history),
    }
