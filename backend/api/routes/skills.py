"""Skill library endpoints — cahier des charges §20 (HSE), §24.3
(GET /skills). Every operation goes through EchoAgent, never
skill_library.py directly, same discipline as memory.py.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.echo import EchoAgent
from backend.core.agent_registry import get_agent_registry
from backend.core.config import get_settings
from backend.memory.skill_library import Skill, status_for

router = APIRouter()


class SkillUseRequest(BaseModel):
    success: bool


class SkillResponse(BaseModel):
    id: str
    project_id: str | None
    name: str
    description: str
    procedure: str
    confidence: float
    status: str
    decay: float
    uses: int
    successes: int
    tags: list[str]
    source_task_id: str | None
    created_at: str
    updated_at: str


def _echo() -> EchoAgent:
    return get_agent_registry().get("echo")


def _to_response(skill: Skill) -> SkillResponse:
    settings = get_settings()
    return SkillResponse(
        id=skill.id,
        project_id=skill.project_id,
        name=skill.name,
        description=skill.description,
        procedure=skill.procedure,
        confidence=skill.confidence,
        status=status_for(
            skill.confidence,
            min_confidence=settings.skill_min_confidence,
            auto_validate_threshold=settings.skill_auto_validate_threshold,
        ),
        decay=skill.decay,
        uses=skill.uses,
        successes=skill.successes,
        tags=skill.tags_list,
        source_task_id=skill.source_task_id,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat(),
    )


@router.get("/skills")
async def list_skills(project_id: str | None = None, tag: str | None = None) -> list[SkillResponse]:
    skills = _echo().list_skills(project_id=project_id, tag=tag)
    return [_to_response(s) for s in skills]


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> SkillResponse:
    skill = _echo().get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No skill {skill_id!r}")
    return _to_response(skill)


@router.post("/skills/{skill_id}/use")
async def use_skill(skill_id: str, request: SkillUseRequest) -> SkillResponse:
    skill = _echo().use_skill(skill_id, success=request.success)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No skill {skill_id!r}")
    return _to_response(skill)


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str) -> dict:
    deleted = _echo().forget_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No skill {skill_id!r}")
    return {"deleted": True, "id": skill_id}
