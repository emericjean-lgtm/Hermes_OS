"""Evolution Routes for Hermes OS (HOS-058)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from .evolution_engine import EvolutionEngine
from .evolution_models import EvolutionStatus

_engine: EvolutionEngine | None = None


def get_engine() -> EvolutionEngine:
    global _engine
    if _engine is None:
        _engine = EvolutionEngine()
    return _engine


def create_evolution_routes(engine: EvolutionEngine) -> APIRouter:
    """Bind the container-owned engine to these routes (HOS-066B)."""
    global _engine
    _engine = engine
    return router


def handle_get_status() -> dict[str, Any]:
    engine = get_engine()
    return engine.stats()


def handle_get_proposals(status: str | None = None) -> list[dict]:
    engine = get_engine()
    es = EvolutionStatus(status) if status else None
    return [p.to_dict() for p in engine.get_proposals(status=es)]


def handle_analyze(data: dict) -> list[dict]:
    engine = get_engine()
    from .evolution_models import SystemMetrics
    metrics = SystemMetrics(
        runtime_avg_latency_ms=data.get("runtime_avg_latency_ms", 500.0),
        runtime_error_rate=data.get("runtime_error_rate", 0.05),
        runtime_model_score=data.get("runtime_model_score", 0.7),
        agent_success_rate=data.get("agent_success_rate", 0.8),
        agent_avg_duration_ms=data.get("agent_avg_duration_ms", 5000.0),
        skill_usage_rate=data.get("skill_usage_rate", 0.6),
        skill_unused_ratio=data.get("skill_unused_ratio", 0.3),
        mission_avg_duration_s=data.get("mission_avg_duration_s", 120.0),
        mission_blocked_count=data.get("mission_blocked_count", 0),
        memory_hit_rate=data.get("memory_hit_rate", 0.65),
    )
    results = engine.run_full_pipeline(metrics)
    return results


def handle_simulate(proposal_id: str) -> dict:
    engine = get_engine()
    proposals = engine.get_proposals()
    proposal = next((p for p in proposals if p.proposal_id == proposal_id), None)
    if proposal is None:
        return {"error": "Proposal not found"}
    experiment = engine.simulator.simulate(proposal)
    return experiment.to_dict()


def handle_approve(proposal_id: str) -> dict:
    engine = get_engine()
    ok = engine.approve(proposal_id)
    return {"success": ok, "proposal_id": proposal_id}


def handle_apply(proposal_id: str) -> dict:
    engine = get_engine()
    ok = engine.approve(proposal_id)
    return {"success": ok, "proposal_id": proposal_id}


def handle_get_reports(limit: int = 10) -> list[dict]:
    engine = get_engine()
    return [
        {
            "report_id": r.report_id,
            "improvements_found": r.improvements_found,
            "applied_changes": r.applied_changes,
            "rejected_changes": r.rejected_changes,
            "total_gain_percent": r.total_gain_percent,
        }
        for r in engine.get_reports(limit=limit)
    ]


# ── HTTP surface ─────────────────────────────────────────────
# Paths mirror EVOLUTION_ROUTES below.

router = APIRouter(prefix="/evolution", tags=["evolution"])


@router.get("/status")
async def get_status() -> dict[str, Any]:
    return handle_get_status()


@router.get("/proposals")
async def get_proposals(status: Optional[str] = Query(None)) -> list[dict]:
    return handle_get_proposals(status)


@router.post("/analyze")
async def analyze(payload: dict = Body(default_factory=dict)) -> list[dict]:
    return handle_analyze(payload)


@router.post("/simulate/{proposal_id}")
async def simulate(proposal_id: str) -> dict:
    return handle_simulate(proposal_id)


@router.post("/approve/{proposal_id}")
async def approve(proposal_id: str) -> dict:
    return handle_approve(proposal_id)


@router.post("/apply/{proposal_id}")
async def apply_proposal(proposal_id: str) -> dict:
    return handle_apply(proposal_id)


@router.get("/reports")
async def get_reports(limit: int = Query(10, ge=1, le=200)) -> list[dict]:
    return handle_get_reports(limit)


EVOLUTION_ROUTES = [
    {"path": "/evolution/status", "method": "GET", "handler": handle_get_status},
    {"path": "/evolution/proposals", "method": "GET", "handler": handle_get_proposals},
    {"path": "/evolution/analyze", "method": "POST", "handler": handle_analyze},
    {"path": "/evolution/simulate/{id}", "method": "POST", "handler": handle_simulate},
    {"path": "/evolution/approve/{id}", "method": "POST", "handler": handle_approve},
    {"path": "/evolution/apply/{id}", "method": "POST", "handler": handle_apply},
    {"path": "/evolution/reports", "method": "GET", "handler": handle_get_reports},
]
