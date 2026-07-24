"""POST /research — Minerva's full RAG loop (cahier des charges §10.5).

Non-streaming on purpose, unlike /chat: the response bundles the
synthesized answer together with structured source passages, which
doesn't fit /chat's plain-text streaming body without either overloading
headers or building a custom streaming envelope. A research query is
also typically waited-for rather than watched token-by-token.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.minerva import MinervaAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str
    n_results: int = 5


class Passage(BaseModel):
    id: str
    content: str
    metadata: dict
    distance: float | None = None


class ResearchResponse(BaseModel):
    answer: str
    passages: list[Passage]
    model: str
    tier: str


@router.post("/research")
async def research(request: ResearchRequest) -> ResearchResponse:
    registry = get_agent_registry()

    try:
        minerva: MinervaAgent = registry.get("minerva")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        decision, stream, passages = await minerva.research(
            request.query, n_results=request.n_results
        )
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    answer = "".join([chunk async for chunk in stream])

    return ResearchResponse(
        answer=answer,
        passages=[Passage(**p) for p in passages],
        model=decision.model,
        tier=decision.tier,
    )
