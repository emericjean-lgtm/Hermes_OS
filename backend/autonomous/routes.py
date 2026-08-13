"""Autonomous Routes for Hermes OS (HOS-063)."""

from __future__ import annotations


from fastapi import APIRouter, Body, HTTPException, Query

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


def handle_list_goals(limit: int = 50) -> dict:
    """GET /autonomous/goals — what is running, and what ran before.

    Without this a goal could only be reached through an id the caller had
    captured when starting it, which is why a running goal became
    unreachable the moment the Autonomous Center unmounted (HOS-102).
    """
    goals = get_engine().list_goals(limit)
    return {"success": True, "goals": goals, "total": len(goals)}


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


# Like "/status" above, this literal must precede "/{goal_id}" or FastAPI
# matches "goals" as a goal id.
@router.get("/goals")
async def list_goals(limit: int = Query(50, ge=1, le=500)) -> dict:
    return handle_list_goals(limit)


# Deliberately NOT `async def` (HOS-102). start_goal runs the whole
# pipeline synchronously — planning plus real local inference, minutes. In
# an async handler that work executes on the event loop thread, so uvicorn
# serves *nothing* else for the duration: not /autonomous/goals, not
# /missions, not /health. FastAPI runs a plain `def` path operation in its
# threadpool instead, which is what makes the goal listing below reachable
# while a goal is actually running.
#
# Narrowing the orchestrator's lock (see AutonomousOrchestrator.start_goal)
# was necessary but not sufficient: with that lock already narrow, a live
# GET /autonomous/status still timed out at 25 s, which is what showed the
# block was above the lock rather than in it.
@router.post("/start")
def start_goal(payload: dict = Body(...)) -> dict:
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
    {"path": "/autonomous/goals", "method": "GET", "handler": handle_list_goals},
]
