"""POST /chat — streaming chat endpoint backed by the agent registry.

This is the walking-skeleton version of the full Chat view described in
the cahier des charges §23.3: no context panel, no diff viewer, no agent
switching UI yet — just request in, streamed tokens out, with the routing
decision exposed via response headers for the frontend to display.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.router import UnknownTaskTypeError

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    agent: str = "hermes_prime"
    task_type: str | None = None


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    registry = get_agent_registry()

    try:
        agent = registry.get(request.agent)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plain_messages = [m.model_dump() for m in request.messages]

    try:
        decision, stream = await agent.respond(plain_messages, task_type=request.task_type)
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        stream,
        media_type="text/plain",
        headers={
            "X-Hermes-Model": decision.model,
            "X-Hermes-Tier": decision.tier,
            "X-Hermes-Role": decision.role,
        },
    )
