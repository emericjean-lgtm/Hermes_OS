"""Self-evolution endpoints — cahier des charges §20.

POST /evolution/process/{task_id} runs the pipeline (evaluate -> extract a
skill on success -> reflect if enabled) for one task — called explicitly
(e.g. once an agent marks a task done via PATCH /tasks/{id}), not
auto-triggered by Kronos itself (see self_evolution/pipeline.py's
docstring for why).

GET /evolution/progression aggregates stats over every task/skill currently
stored (optionally scoped to a project) — see progression_tracker.py.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.echo import EchoAgent
from backend.agents.kronos import KronosAgent
from backend.core.agent_registry import get_agent_registry
from backend.self_evolution import progression_tracker
from backend.self_evolution.pipeline import process_task

router = APIRouter()


class EvolutionProcessResponse(BaseModel):
    task_id: str
    outcome: bool | None
    skill_id: str | None
    deduplicated: bool
    reflection: str | None


def _kronos() -> KronosAgent:
    return get_agent_registry().get("kronos")


def _echo() -> EchoAgent:
    return get_agent_registry().get("echo")


@router.post("/evolution/process/{task_id}")
async def evolution_process_task(task_id: str) -> EvolutionProcessResponse:
    task = _kronos().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task {task_id!r}")
    result = process_task(task, _echo())
    return EvolutionProcessResponse(**result)


@router.get("/evolution/progression")
async def evolution_progression(project_id: str | None = None) -> dict:
    tasks = _kronos().list_tasks(project_id=project_id)
    skills = _echo().list_skills(project_id=project_id)
    return progression_tracker.compute_progression(tasks, skills)
