"""Snapshot endpoints — cahier des charges §19.3, acceptance criterion T8.

Creating is read-only with respect to application state and needs no
gate. Restoring overwrites it, so it is classified `data_migration`
(mandatory human validation at every autonomy level, §17.3) and gets a
preview endpoint alongside — the same "show the diff before asking"
contract §14.1 imposes on file writes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core import snapshot_manager
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.snapshot_manager import SnapshotError

router = APIRouter()


def _aegis() -> AegisAgent:
    try:
        return get_agent_registry().get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class CreateSnapshotRequest(BaseModel):
    reason: str = ""
    context: dict = {}


class RestoreRequest(BaseModel):
    project_id: str | None = None


@router.post("/snapshots")
async def create_snapshot(request: CreateSnapshotRequest) -> dict:
    info = snapshot_manager.create_snapshot(reason=request.reason, context=request.context)
    return {
        "id": info.id,
        "created_at": info.created_at,
        "reason": info.reason,
        "task_count": info.task_count,
        "run_count": info.run_count,
    }


@router.get("/snapshots")
async def list_snapshots() -> list[dict]:
    return [
        {
            "id": s.id,
            "created_at": s.created_at,
            "reason": s.reason,
            "task_count": s.task_count,
            "run_count": s.run_count,
            "context": s.context,
        }
        for s in snapshot_manager.list_snapshots()
    ]


@router.get("/snapshots/{snapshot_id}/preview")
async def preview_restore(snapshot_id: str) -> dict:
    try:
        preview = snapshot_manager.preview_restore(snapshot_id)
    except SnapshotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "snapshot_id": preview.snapshot_id,
        "tasks_restored": preview.tasks_restored,
        "tasks_overwritten": preview.tasks_overwritten,
        "tasks_created": preview.tasks_created,
        "tasks_absent_from_snapshot": preview.tasks_absent_from_snapshot,
        "runs_restored": preview.runs_restored,
    }


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str, request: RestoreRequest) -> dict:
    """A refusal comes back as 200 with restored=false and a verdict: at
    the shipped autonomy level that is the expected outcome, not a fault.
    """
    try:
        result = snapshot_manager.restore_snapshot(
            _aegis(), snapshot_id, project_id=request.project_id
        )
    except SnapshotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "restored": result.restored,
        "snapshot_id": result.snapshot_id,
        "verdict": result.verdict,
        "reason": result.reason,
        "tasks_restored": result.tasks_restored,
        "runs_restored": result.runs_restored,
    }
