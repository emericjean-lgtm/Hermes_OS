"""Task endpoints — cahier des charges §24.1 (GET /tasks, POST /tasks,
PATCH /tasks/{id}, GET /tasks/{id}). Wraps KronosAgent, never
task_manager.py directly.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.kronos import KronosAgent
from backend.core.agent_registry import get_agent_registry
from backend.tasks.task_manager import InvalidTaskPriorityError, InvalidTaskStatusError, Task

router = APIRouter()


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    objective: str = ""
    priority: str = "medium"
    agent: str | None = None
    project_id: str | None = None


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    files: list[str] | None = None
    models_used: list[str] | None = None
    test_results: dict | None = None
    note: str | None = None
    project_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    project_id: str | None
    title: str
    description: str
    objective: str
    status: str
    priority: str
    agent: str | None
    created_at: str
    updated_at: str
    models_used: list[str]
    files: list[str]
    test_results: dict | None
    history: list[dict]


def _kronos() -> KronosAgent:
    return get_agent_registry().get("kronos")


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        objective=task.objective,
        status=task.status,
        priority=task.priority,
        agent=task.agent,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        models_used=task.models_used_list,
        files=task.files_list,
        test_results=task.test_results_dict,
        history=task.history_list,
    )


@router.post("/tasks")
async def create_task(request: TaskCreateRequest) -> TaskResponse:
    try:
        task = _kronos().create_task(
            title=request.title,
            description=request.description,
            objective=request.objective,
            priority=request.priority,
            agent=request.agent,
            project_id=request.project_id,
        )
    except InvalidTaskPriorityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(task)


@router.get("/tasks")
async def list_tasks(status: str | None = None, project_id: str | None = None) -> list[TaskResponse]:
    try:
        tasks = _kronos().list_tasks(status=status, project_id=project_id)
    except InvalidTaskStatusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> TaskResponse:
    task = _kronos().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task {task_id!r}")
    return _to_response(task)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest) -> TaskResponse:
    try:
        task = _kronos().update_task(
            task_id,
            status=request.status,
            files=request.files,
            models_used=request.models_used,
            test_results=request.test_results,
            note=request.note,
            project_id=request.project_id,
        )
    except InvalidTaskStatusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task {task_id!r}")
    return _to_response(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    deleted = _kronos().delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No task {task_id!r}")
    return {"deleted": True, "id": task_id}
