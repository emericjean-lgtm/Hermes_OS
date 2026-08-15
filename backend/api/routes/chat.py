"""POST /chat — streaming chat endpoint backed by the agent registry.

This is the walking-skeleton version of the full Chat view described in
the cahier des charges §23.3: no context panel, no diff viewer, no agent
switching UI yet — just request in, streamed tokens out, with the routing
decision exposed via response headers for the frontend to display.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core import audit_log
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry
from backend.core.audit_log import AuditEntry, Timer
from backend.core.event_hub import get_event_hub
from backend.core.router import UnknownTaskTypeError

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    agent: str = "hermes_prime"
    task_type: str | None = None
    session_id: str | None = None
    # Off by default, and that default is load-bearing: without it the
    # body stays raw content, byte for byte, for every existing consumer.
    # Opting in switches the body to NDJSON — one {"kind","text"} object
    # per line — so a caller cannot start receiving reasoning text mixed
    # into the answer without having asked for it.
    include_thinking: bool = False


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    registry = get_agent_registry()

    try:
        agent = registry.get(request.agent)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plain_messages = [m.model_dump() for m in request.messages]

    try:
        decision, events = await agent.respond_events(
            plain_messages, task_type=request.task_type
        )
    except UnknownTaskTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        _audited(events, request, decision),
        media_type="application/x-ndjson" if request.include_thinking else "text/plain",
        headers={
            "X-Hermes-Model": decision.model,
            "X-Hermes-Tier": decision.tier,
            "X-Hermes-Role": decision.role,
            # The client needs to know which framing it got without
            # inferring it from the flag it sent.
            "X-Hermes-Thinking": "true" if decision.thinking else "false",
        },
    )


async def _audited(stream, request: ChatRequest, decision) -> AsyncIterator[str]:
    """Stream through, then write one audit record (§18).

    Two things are deliberate here.

    The record is written *after* the last token, never before: measured
    from the request we would be timing how long it takes to build a
    generator, not how long Hermes took to answer — and §22.1's budgets
    are the reason this instrumentation exists at all.

    And the whole logging step is swallowed on failure. Observability
    that can cost a user their answer is a downgrade; a missing log line
    is recoverable, a 500 in the middle of a response is not.
    """
    timer = Timer()
    hub = get_event_hub()
    error: str | None = None
    try:
        async for chunk in timer.measure_events(stream):
            # §24.2 chat.token — so a monitoring view can follow a
            # conversation it did not initiate. The HTTP body below is
            # still the answer's only delivery path; this is a copy for
            # observers, and a client that cannot keep up drops events
            # rather than slowing the answer down.
            hub.publish("chat.token", {
                "session_id": request.session_id,
                "agent": request.agent,
                "kind": chunk.kind,
                "text": chunk.text,
            })
            if request.include_thinking:
                yield json.dumps({"kind": chunk.kind, "text": chunk.text},
                                 ensure_ascii=False) + "\n"
            elif chunk.kind == "content":
                yield chunk.text
    except Exception as exc:  # recorded, then re-raised — never silenced
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        last = request.messages[-1].content if request.messages else ""
        # A stream that raised nothing but produced nothing is not a
        # success. Measured on real hardware: qwen3.5:9b answered a
        # trivial question in 59s with zero content tokens (a reasoning
        # model can spend the whole turn in message.thinking, which
        # chat_stream does not yield) — and the record said "success".
        # Recording that as a win is how a broken path stays invisible.
        if error:
            result, detail = "failed", error
        elif timer.tokens == 0:
            result, detail = "empty", (
                "the model produced no content token — it may have answered "
                "entirely in its reasoning channel, or been interrupted"
            )
        else:
            result, detail = "success", None
        try:
            with audit_log.open_session() as session:
                audit_log.record(session, AuditEntry(
                    agent=request.agent,
                    request=last,
                    session_id=request.session_id,
                    result=result,
                    error=detail,
                    routing_decision={
                        "task_type": decision.task_type,
                        "model_selected": decision.model,
                        "tier": decision.tier,
                        "reason": decision.reason,
                        "thinking": decision.thinking,
                        # HOS-114 : ce que ce choix a coûté en chargement.
                        # Sans lui, `first_token_ms` mélange l'attente due
                        # à une bascule et la lenteur du modèle — deux
                        # causes qui appellent des corrections opposées,
                        # exactement la distinction qui a motivé
                        # `first_thinking_ms` juste au-dessus.
                        "switch_cost_s": decision.switch_cost_s,
                    },
                    duration_ms=timer.duration_ms,
                    first_token_ms=timer.first_token_ms,
                    first_thinking_ms=timer.first_thinking_ms,
                    tokens_used=timer.tokens,
                    tokens_per_second=timer.tokens_per_second,
                ))
        except Exception:
            logger.exception("audit log write failed for agent=%s", request.agent)
