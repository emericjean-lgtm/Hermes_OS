"""Autonomous Routes for Hermes OS (HOS-063)."""

from __future__ import annotations


from fastapi import APIRouter, Body, HTTPException

from .autonomous_engine import AutonomousEngine

_engine: AutonomousEngine | None = None


def get_engine() -> AutonomousEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousEngine()
    return _engine


def create_autonomous_routes(engine: AutonomousEngine) -> APIRouter:
    """Bind the container-owned engine to these routes (HOS-066B)."""
    global _engine
    _engine = engine
    return router


def handle_start_goal(data: dict) -> dict:
    engine = get_engine()
    return engine.start_goal(
        user_request=data["user_request"],
        context=data.get("context"),
    )


def handle_get_goal(goal_id: str) -> dict | None:
    engine = get_engine()
    return engine.get_goal(goal_id)


def handle_pause_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.pause_goal(goal_id)


def handle_resume_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.resume_goal(goal_id)


def handle_cancel_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.cancel_goal(goal_id)


def handle_get_timeline(goal_id: str) -> dict:
    engine = get_engine()
    return engine.get_timeline(goal_id)


def handle_get_report(goal_id: str) -> dict | None:
    engine = get_engine()
    return engine.get_report(goal_id)


def handle_get_status() -> dict:
    engine = get_engine()
    return engine.get_status()


# ── HTTP surface ─────────────────────────────────────────────
#
# Paths mirror AUTONOMOUS_ROUTES below. Note the ordering: "/status" is
# declared before "/{goal_id}" so the literal wins — registered the other way
# round, FastAPI would match "status" as a goal id.

router = APIRouter(prefix="/autonomous", tags=["autonomous"])


@router.get("/status")
async def get_status() -> dict:
    return handle_get_status()


@router.post("/start")
async def start_goal(payload: dict = Body(...)) -> dict:
    return handle_start_goal(payload)


@router.get("/{goal_id}")
async def get_goal(goal_id: str) -> dict:
    result = handle_get_goal(goal_id)
    if result is None:
        raise HTTPException(404, f"goal {goal_id!r} not found")
    return result


@router.post("/{goal_id}/pause")
async def pause_goal(goal_id: str) -> dict:
    return handle_pause_goal(goal_id)


@router.post("/{goal_id}/resume")
async def resume_goal(goal_id: str) -> dict:
    return handle_resume_goal(goal_id)


@router.post("/{goal_id}/cancel")
async def cancel_goal(goal_id: str) -> dict:
    return handle_cancel_goal(goal_id)


@router.get("/{goal_id}/timeline")
async def get_timeline(goal_id: str) -> dict:
    return handle_get_timeline(goal_id)


@router.get("/{goal_id}/report")
async def get_report(goal_id: str) -> dict:
    result = handle_get_report(goal_id)
    if result is None:
        raise HTTPException(404, f"no report for goal {goal_id!r}")
    return result


AUTONOMOUS_ROUTES = [
    {"path": "/autonomous/start", "method": "POST", "handler": handle_start_goal},
    {"path": "/autonomous/{id}", "method": "GET", "handler": handle_get_goal},
    {"path": "/autonomous/{id}/pause", "method": "POST", "handler": handle_pause_goal},
    {"path": "/autonomous/{id}/resume", "method": "POST", "handler": handle_resume_goal},
    {"path": "/autonomous/{id}/cancel", "method": "POST", "handler": handle_cancel_goal},
    {"path": "/autonomous/{id}/timeline", "method": "GET", "handler": handle_get_timeline},
    {"path": "/autonomous/{id}/report", "method": "GET", "handler": handle_get_report},
    {"path": "/autonomous/status", "method": "GET", "handler": handle_get_status},
]
