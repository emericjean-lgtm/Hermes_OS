"""POST /verify — Veritas's QA review loop (cahier des charges §9.1, §16).

Non-streaming, same reasoning as /research: the response is a parsed
verdict (structured), not a token stream a user would watch live.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.veritas import VeritasAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class VerifyRequest(BaseModel):
    output: str
    context: str = ""
    criteria: list[str] | None = None


class VerifyResponse(BaseModel):
    verdict: str
    issues: list[str]
    corrections: str
    raw: str
    model: str
    tier: str


@router.post("/verify")
async def verify(request: VerifyRequest) -> VerifyResponse:
    registry = get_agent_registry()

    try:
        veritas: VeritasAgent = registry.get("veritas")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        decision, stream = await veritas.review(
            request.output, context=request.context, criteria=request.criteria
        )
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reply = "".join([chunk async for chunk in stream])
    parsed = VeritasAgent.parse_verdict(reply)

    return VerifyResponse(
        verdict=parsed["verdict"],
        issues=parsed["issues"],
        corrections=parsed["corrections"],
        raw=parsed["raw"],
        model=decision.model,
        tier=decision.tier,
    )
