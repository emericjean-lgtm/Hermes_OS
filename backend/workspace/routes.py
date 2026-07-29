"""FastAPI routes for the Workspace & Sandbox Manager (HOS-045)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from backend.workspace.workspace_manager import WorkspaceManager

router = APIRouter(prefix="/workspace", tags=["workspace"])

_manager: Optional[WorkspaceManager] = None


def create_workspace_routes(manager: WorkspaceManager) -> APIRouter:
    global _manager
    _manager = manager
    return router


def _ensure_manager():
    if _manager is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Workspace manager not initialized")


# ── Workspace CRUD ───────────────────────────────────────────

@router.post("")
async def create_workspace(payload: dict = Body(...)):
    _ensure_manager()
    ws = _manager.create(
        mission_id=payload["mission_id"],
        agent_id=payload["agent_id"],
        node_id=payload.get("node_id", ""),
        repository=payload.get("repository", ""),
        max_disk_mb=payload.get("max_disk_mb", 1024),
        max_duration_seconds=payload.get("max_duration_seconds", 3600.0),
    )
    return {
        "workspace_id": ws.workspace_id,
        "agent_id": ws.agent_id,
        "mission_id": ws.mission_id,
        "status": ws.status.value,
    }


@router.get("")
async def list_workspaces(agent_id: str = "", mission_id: str = ""):
    _ensure_manager()
    if agent_id:
        workspaces = _manager.get_by_agent(agent_id)
    elif mission_id:
        workspaces = _manager.get_by_mission(mission_id)
    else:
        workspaces = _manager.list_all()
    return {
        "workspaces": [
            {"id": w.workspace_id, "agent": w.agent_id, "status": w.status.value,
             "branch": w.git_branch, "disk_mb": w.disk_used_mb}
            for w in workspaces
        ],
        "total": len(workspaces),
    }


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str):
    _ensure_manager()
    ws = _manager.get(workspace_id)
    if ws is None:
        return {"error": "Not found"}
    return {
        "workspace_id": ws.workspace_id,
        "agent_id": ws.agent_id,
        "mission_id": ws.mission_id,
        "status": ws.status.value,
        "git_branch": ws.git_branch,
        "git_commit": ws.git_commit,
        "disk_used_mb": ws.disk_used_mb,
        "disk_quota_mb": ws.max_disk_mb,
        "created_at": ws.created_at.isoformat(),
    }


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str):
    _ensure_manager()
    ok = _manager.destroy(workspace_id)
    return {"ok": ok}


@router.post("/{workspace_id}/lock")
async def lock_workspace(workspace_id: str):
    _ensure_manager()
    return {"ok": _manager.lock(workspace_id)}


@router.post("/{workspace_id}/release")
async def release_workspace(workspace_id: str):
    _ensure_manager()
    return {"ok": _manager.release(workspace_id)}


@router.get("/{workspace_id}/status")
async def get_status(workspace_id: str):
    _ensure_manager()
    return _manager.get_status(workspace_id)


@router.get("/{workspace_id}/artifacts")
async def get_artifacts(workspace_id: str):
    _ensure_manager()
    artifacts = _manager.get_artifacts(workspace_id)
    return {
        "artifacts": [
            {"id": a.artifact_id, "name": a.name, "type": a.type.value,
             "version": a.version, "size_bytes": a.size_bytes}
            for a in artifacts
        ],
        "total": len(artifacts),
    }
