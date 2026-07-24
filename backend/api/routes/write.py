"""POST /write — Hermes Scribe's brief-to-document loop (cahier des
charges §9.1).

Non-streaming, same reasoning as /research and /verify: a document is
typically waited-for as a whole rather than watched token-by-token.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.hermes_scribe import HermesScribeAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class WriteRequest(BaseModel):
    brief: str
    format: str = "markdown"
    tone: str = "neutral"
    context: str = ""


class WriteResponse(BaseModel):
    document: str
    model: str
    tier: str


@router.post("/write")
async def write(request: WriteRequest) -> WriteResponse:
    registry = get_agent_registry()

    try:
        scribe: HermesScribeAgent = registry.get("hermes_scribe")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        decision, stream = await scribe.write(
            request.brief, format=request.format, tone=request.tone, context=request.context
        )
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = "".join([chunk async for chunk in stream])

    return WriteResponse(document=document, model=decision.model, tier=decision.tier)
