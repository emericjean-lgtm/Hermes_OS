"""REST API routes for the Autonomous Execution Engine (HOS-050)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .execution_controller import ExecutionController
from .mission_executor import MissionExecutor
from .execution_models import (
    ExecutionMeta,
    ExecutionPriority,
    ExecutionState,
    ExecutionTimeline,
    TaskExecution,
    TaskExecutionStatus,
)

# Singleton instances (in real app, these would be injected)
_executor = MissionExecutor()
_controller = ExecutionController(_executor)


def get_routes() -> dict[str, Any]:
    """Return route definitions for the execution API."""
    return {
        "POST /execution/start": start_execution,
        "GET /execution/{id}": get_execution,
        "GET /execution": list_executions,
        "POST /execution/{id}/pause": pause_execution,
        "POST /execution/{id}/resume": resume_execution,
        "POST /execution/{id}/cancel": cancel_execution,
        "GET /execution/{id}/timeline": get_timeline,
        "GET /execution/statistics": statistics,
    }


def start_execution(goal: str, tasks: list[dict[str, str]],
                    mission_id: str = "",
                    dependencies: dict[str, list[str]] | None = None,
                    priority: str = "normal") -> dict[str, Any]:
    """POST /execution/start — Start a new autonomous mission execution.

    Creates a mission from user goal, tasks, and optional dependencies.
    """
    meta = ExecutionMeta(
        mission_id=mission_id or "mission-auto",
        user_goal=goal,
        priority=ExecutionPriority(priority.lower()),
    )

    exec_tasks = [
        TaskExecution(
            task_id=t.get("id", f"task-{i}"),
            node_id=t.get("node_id", f"node-{i}"),
            title=t.get("title", t.get("id", f"task-{i}")),
            status=TaskExecutionStatus.PENDING,
        )
        for i, t in enumerate(tasks)
    ]

    sm = _controller.start(meta, exec_tasks, dependencies)
    return {
        "execution_id": meta.execution_id,
        "state": sm.state.value,
        "tasks_registered": len(exec_tasks),
        "user_goal": goal,
    }


def get_execution(execution_id: str) -> dict[str, Any]:
    """GET /execution/{id} — Get execution state and progress."""
    info = _controller.get(execution_id)
    if info is None:
        return {"error": f"Execution {execution_id} not found"}
    return info


def list_executions() -> list[dict[str, Any]]:
    """GET /execution — List all executions."""
    return _controller.list_executions()


def pause_execution(execution_id: str) -> dict[str, Any]:
    """POST /execution/{id}/pause — Pause a running execution."""
    ok = _controller.pause(execution_id)
    return {"execution_id": execution_id, "paused": ok}


def resume_execution(execution_id: str) -> dict[str, Any]:
    """POST /execution/{id}/resume — Resume a paused execution."""
    ok = _controller.resume(execution_id)
    return {"execution_id": execution_id, "resumed": ok}


def cancel_execution(execution_id: str) -> dict[str, Any]:
    """POST /execution/{id}/cancel — Cancel an execution."""
    ok = _controller.cancel(execution_id)
    return {"execution_id": execution_id, "cancelled": ok}


def get_timeline(execution_id: str) -> dict[str, Any]:
    """GET /execution/{id}/timeline — Get full execution timeline."""
    timeline = _controller.get_timeline(execution_id)
    if timeline is None:
        return {"error": f"Execution {execution_id} not found"}
    return timeline


def statistics() -> dict[str, Any]:
    """GET /execution/statistics — Get global execution statistics."""
    return _controller.stats()


# For test usage — reset controller
def _reset_controller() -> None:
    global _executor, _controller
    _executor = MissionExecutor()
    _controller = ExecutionController(_executor)


# ── HTTP surface ─────────────────────────────────────────────
# Thin delegation to the handlers above (HOS-066B). Paths mirror get_routes().
# "/statistics" is declared before "/{execution_id}" so the literal wins.

router = APIRouter(prefix="/execution", tags=["execution"])


def create_execution_routes(controller: ExecutionController) -> APIRouter:
    """Bind the container-owned controller to these routes."""
    global _controller
    _controller = controller
    return router


@router.get("")
async def list_all() -> list[dict[str, Any]]:
    return list_executions()


@router.get("/statistics")
async def get_statistics() -> dict[str, Any]:
    return statistics()


@router.post("/start")
async def start(payload: dict = Body(...)) -> dict[str, Any]:
    # `tasks` is walked with `t.get(...)` downstream, so a string or a list of
    # scalars raised AttributeError and surfaced as 500 — a client-input error
    # reported as a server fault. Validated here rather than by widening the
    # app-level exception handlers to AttributeError, which would also swallow
    # genuine server bugs.
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise HTTPException(
            status_code=422,
            detail=[{"type": "list_type", "loc": ["body", "tasks"],
                     "msg": "Input should be a list of task objects"}],
        )
    bad = [i for i, t in enumerate(tasks) if not isinstance(t, dict)]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=[{"type": "dict_type", "loc": ["body", "tasks", i],
                     "msg": "Each task must be an object"} for i in bad],
        )

    dependencies = payload.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, dict):
        raise HTTPException(
            status_code=422,
            detail=[{"type": "dict_type", "loc": ["body", "dependencies"],
                     "msg": "Input should be an object mapping task id -> list of ids"}],
        )

    return start_execution(
        goal=payload.get("goal", ""),
        tasks=tasks,
        mission_id=payload.get("mission_id", ""),
        dependencies=dependencies,
        priority=payload.get("priority", "normal"),
    )


@router.get("/{execution_id}")
async def get_one(execution_id: str) -> dict[str, Any]:
    return get_execution(execution_id)


@router.get("/{execution_id}/timeline")
async def timeline(execution_id: str) -> dict[str, Any]:
    return get_timeline(execution_id)


@router.post("/{execution_id}/pause")
async def pause(execution_id: str) -> dict[str, Any]:
    return pause_execution(execution_id)


@router.post("/{execution_id}/resume")
async def resume(execution_id: str) -> dict[str, Any]:
    return resume_execution(execution_id)


@router.post("/{execution_id}/cancel")
async def cancel(execution_id: str) -> dict[str, Any]:
    return cancel_execution(execution_id)
