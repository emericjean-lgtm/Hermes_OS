"""File endpoints — cahier des charges §24.1 (GET /files, GET
/files/content, POST /files/diff, POST /files/apply). Every operation is
gated by Aegis; nothing here bypasses backend/tools/file_tools.py.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import get_agent_registry
from backend.tools import file_tools

router = APIRouter()


class DiffRequest(BaseModel):
    path: str
    new_content: str
    project_id: str | None = None


class DiffResponse(BaseModel):
    diff: str


class ApplyResponse(BaseModel):
    applied: bool
    verdict: str
    reason: str
    diff: str
    backup_path: str | None = None
    verified: bool = False


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


@router.get("/files")
async def list_files(path: str, project_id: str | None = None) -> list[str]:
    try:
        return file_tools.list_directory(_aegis(), path, project_id=project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/files/content")
async def get_file_content(path: str, project_id: str | None = None) -> dict:
    try:
        return {"path": path, "content": file_tools.read_file(_aegis(), path, project_id=project_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/files/diff")
async def diff_file(request: DiffRequest) -> DiffResponse:
    try:
        before = file_tools.read_existing_or_empty(
            _aegis(), request.path, project_id=request.project_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return DiffResponse(diff=file_tools.compute_diff(before, request.new_content, request.path))


@router.post("/files/apply")
async def apply_file(request: DiffRequest) -> ApplyResponse:
    result = file_tools.propose_write(
        _aegis(), request.path, request.new_content, project_id=request.project_id
    )
    return ApplyResponse(
        applied=result.applied,
        verdict=result.verdict,
        reason=result.reason,
        diff=result.diff,
        backup_path=result.backup_path,
        verified=result.verified,
    )
