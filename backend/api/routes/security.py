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
    project_id: str | None = None
    # When true and the verdict is require_human_validation, also runs
    # the LLM advisory pass (AegisAgent.advise()) and includes its text
    # in the response. No-op (and no extra LLM call) for allow/deny —
    # opt-in since it's an extra model call, not a default cost.
    include_advisory: bool = False


class EvaluateResponse(BaseModel):
    verdict: str
    reason: str
    action_type: str
    advisory: str | None = None


@router.post("/security/evaluate")
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    registry = get_agent_registry()

    try:
        aegis: AegisAgent = registry.get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    action = ActionRequest(
        action_type=request.action_type,
        description=request.description,
        target_path=request.target_path,
        requesting_agent=request.requesting_agent,
        task_id=request.task_id,
        project_id=request.project_id,
    )
    decision = aegis.evaluate(action)
    if request.include_advisory:
        decision = await aegis.advise(action, decision)

    return EvaluateResponse(
        verdict=decision.verdict.value,
        reason=decision.reason,
        action_type=decision.action_type,
        advisory=decision.advisory,
    )

def _aegis() -> AegisAgent:
    """Same lookup /security/evaluate does, factored out for the approval
    routes below."""
    try:
        return get_agent_registry().get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/security/approvals")
async def list_approvals(status: str | None = None, project_id: str | None = None) -> list[dict]:
    """Queue of actions Aegis refused pending a human decision — the data
    behind §23's security view."""
    return _aegis().list_approvals(status=status, project_id=project_id)


class ApprovalDecision(BaseModel):
    approved: bool


@router.post("/security/approvals/{approval_id}")
async def decide_approval(approval_id: str, decision: ApprovalDecision) -> dict:
    """Relay a human yes/no. Single-use and time-limited: it authorises
    one later retry of that exact action, never a standing permission."""
    result = _aegis().decide_approval(approval_id, approved=decision.approved)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No approval {approval_id!r}")
    return result
