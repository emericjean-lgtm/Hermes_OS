"""POST /security/evaluate — ask Aegis whether an action is allowed.

This is the integration point future tools (Atlas's file/git tools, etc.)
will call before doing anything mutating. Exposed as its own endpoint now
so the engine is independently testable and usable ahead of those tools
existing (cahier des charges §17).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.security.aegis_engine import ActionRequest

router = APIRouter()


class EvaluateRequest(BaseModel):
    action_type: str
    description: str
    target_path: str | None = None
    requesting_agent: str = "user"
    task_id: str | None = None


class EvaluateResponse(BaseModel):
    verdict: str
    reason: str
    action_type: str


@router.post("/security/evaluate")
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    registry = get_agent_registry()

    try:
        aegis: AegisAgent = registry.get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    decision = aegis.evaluate(
        ActionRequest(
            action_type=request.action_type,
            description=request.description,
            target_path=request.target_path,
            requesting_agent=request.requesting_agent,
            task_id=request.task_id,
        )
    )
    return EvaluateResponse(
        verdict=decision.verdict.value,
        reason=decision.reason,
        action_type=decision.action_type,
    )
