"""POST /vision/analyze — Hermes Eyes's image analysis loop (cahier des
charges §9.1).

Images travel as base64-encoded strings (no data URI prefix) — Ollama's
own multimodal format — so this route forwards them straight through to
the agent rather than decoding/re-encoding anything.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agents.hermes_eyes import DEFAULT_ANALYSIS_PROMPT, HermesEyesAgent
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class VisionRequest(BaseModel):
    images: list[str] = Field(min_length=1)
    prompt: str = DEFAULT_ANALYSIS_PROMPT
    context: str = ""


class VisionResponse(BaseModel):
    description: str
    model: str
    tier: str


@router.post("/vision/analyze")
async def analyze(request: VisionRequest) -> VisionResponse:
    registry = get_agent_registry()

    try:
        eyes: HermesEyesAgent = registry.get("hermes_eyes")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        decision, stream = await eyes.analyze(
            request.images, prompt=request.prompt, context=request.context
        )
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    description = "".join([chunk async for chunk in stream])

    return VisionResponse(description=description, model=decision.model, tier=decision.tier)
