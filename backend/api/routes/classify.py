"""POST /classify — Hermes Swift's request-classification loop (cahier
des charges §9.1).

Non-streaming: the response is a single validated task_type label, not
prose a user would watch stream in.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.hermes_swift import HermesSwiftAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class ClassifyRequest(BaseModel):
    request: str
    default: str = "conversation"


class ClassifyResponse(BaseModel):
    task_type: str
    model: str
    tier: str


@router.post("/classify")
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    registry = get_agent_registry()

    try:
        swift: HermesSwiftAgent = registry.get("hermes_swift")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        decision, stream = await swift.classify(request.request)
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reply = "".join([chunk async for chunk in stream])
    task_type = swift.parse_task_type(reply, default=request.default)

    return ClassifyResponse(task_type=task_type, model=decision.model, tier=decision.tier)
