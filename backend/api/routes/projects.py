"""Project endpoints — foundation for multi-project support (not part
of the original cahier des charges; see backend/projects/project_manager.py
for why). Wraps ProjectStore, mirroring /tasks's shape.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.projects.project_manager import InvalidProjectStatusError, Project
from backend.projects.store import get_project_store

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    root_path: str | None = None
    # Independent of root_path — both can be set together (a local
    # checkout AND its remote), never one-or-the-other. Mirrors Mission's
    # existing local_path/repository/branch binding (HOS-068).
    repository: str | None = None
    branch: str | None = None
    tags: list[str] = []


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    root_path: str | None = None
    repository: str | None = None
    branch: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    root_path: str | None
    repository: str | None
    branch: str | None
    status: str
    validation_status: str | None
    validated_accessible: bool | None
    validated_readable: bool | None
    validated_writable: bool | None
    validation_detail: str | None
    validated_at: str | None
    tags: list[str]
    created_at: str
    updated_at: str


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        repository=project.repository,
        branch=project.branch,
        status=project.status,
        validation_status=project.validation_status,
        validated_accessible=project.validated_accessible,
        validated_readable=project.validated_readable,
        validated_writable=project.validated_writable,
        validation_detail=project.validation_detail,
        validated_at=project.validated_at.isoformat() if project.validated_at else None,
        tags=project.tags_list,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.post("/projects")
async def create_project(request: ProjectCreateRequest) -> ProjectResponse:
    project = get_project_store().create(
        name=request.name,
        description=request.description,
        root_path=request.root_path,
        repository=request.repository,
        branch=request.branch,
        tags=request.tags,
    )
    return _to_response(project)


@router.get("/projects")
async def list_projects(status: str | None = None, tag: str | None = None) -> list[ProjectResponse]:
    try:
        projects = get_project_store().list(status=status, tag=tag)
    except InvalidProjectStatusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_to_response(p) for p in projects]


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> ProjectResponse:
    project = get_project_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")
    return _to_response(project)


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest) -> ProjectResponse:
    try:
        project = get_project_store().update(
            project_id,
            name=request.name,
            description=request.description,
            root_path=request.root_path,
            repository=request.repository,
            branch=request.branch,
            status=request.status,
            tags=request.tags,
        )
    except InvalidProjectStatusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")
    return _to_response(project)


@router.post("/projects/{project_id}/validate")
async def validate_project(project_id: str) -> ProjectResponse:
    """Really probe root_path on disk (exists, is a directory, is
    readable, is writable — see project_manager.validate_project_path)
    and persist the result. Nothing here is a frontend or model claim:
    this is the only endpoint allowed to set validation_status, and
    Aegis's dynamic whitelist (agents/aegis.py) only ever trusts a
    project whose validation_status this endpoint set to "valid"."""
    project = get_project_store().validate(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")
    return _to_response(project)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    deleted = get_project_store().delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")
    return {"deleted": True, "id": project_id}
