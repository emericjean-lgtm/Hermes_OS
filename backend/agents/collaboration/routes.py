"""FastAPI routes for the Collaboration Engine (HOS-044)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from backend.agents.collaboration.collaboration_engine import CollaborationEngine
from backend.agents.collaboration.collaboration_models import (
    ConflictType,
    ConsensusMode,
)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])

_engine: Optional[CollaborationEngine] = None


def create_collaboration_routes(engine: CollaborationEngine) -> APIRouter:
    global _engine
    _engine = engine
    return router


def _ensure_engine():
    if _engine is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Collaboration engine not initialized")


# ── Messages ─────────────────────────────────────────────────

@router.get("/messages")
async def get_inbox(agent_id: str = ""):
    _ensure_engine()
    if agent_id:
        messages = _engine.get_inbox(agent_id)
    else:
        messages = []
    return {
        "messages": [
            {
                "message_id": m.message_id,
                "sender_id": m.sender_id,
                "recipient_id": m.recipient_id,
                "type": m.type.value,
                "subject": m.subject,
                "body": m.body,
                "read": m.read,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.post("/messages")
async def send_message(payload: dict = Body(...)):
    _ensure_engine()
    msg = _engine.send_message(
        sender_id=payload["sender_id"],
        recipient_id=payload["recipient_id"],
        subject=payload.get("subject", ""),
        body=payload.get("body", ""),
        mission_id=payload.get("mission_id", ""),
        node_id=payload.get("node_id", ""),
    )
    return {
        "message_id": msg.message_id,
        "sender_id": msg.sender_id,
        "recipient_id": msg.recipient_id,
        "type": msg.type.value,
    }


@router.post("/messages/broadcast")
async def broadcast(payload: dict = Body(...)):
    _ensure_engine()
    msg = _engine.broadcast_message(
        sender_id=payload["sender_id"],
        subject=payload.get("subject", ""),
        body=payload.get("body", ""),
        mission_id=payload.get("mission_id", ""),
    )
    return {"message_id": msg.message_id, "type": "broadcast"}


@router.get("/messages/unread")
async def get_unread(agent_id: str):
    _ensure_engine()
    messages = _engine.get_unread(agent_id)
    return {"messages": [m.message_id for m in messages], "total": len(messages)}


@router.get("/messages/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    _ensure_engine()
    messages = _engine.get_conversation(conversation_id)
    return {
        "conversation_id": conversation_id,
        "messages": [
            {"message_id": m.message_id, "sender": m.sender_id,
             "subject": m.subject, "created_at": m.created_at.isoformat()}
            for m in messages
        ],
    }


# ── Delegation ───────────────────────────────────────────────

@router.post("/delegate")
async def delegate(payload: dict = Body(...)):
    _ensure_engine()
    d = _engine.delegate_task(
        from_id=payload["from_agent_id"],
        to_id=payload["to_agent_id"],
        mission_id=payload.get("mission_id", ""),
        node_id=payload.get("node_id", ""),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        reason=payload.get("reason", ""),
        required_capabilities=payload.get("required_capabilities"),
    )
    return {
        "delegation_id": d.delegation_id,
        "from": d.from_agent_id,
        "to": d.to_agent_id,
        "status": d.status.value,
    }


@router.get("/delegations")
async def get_delegations(agent_id: str = "", pending: bool = False):
    _ensure_engine()
    if agent_id and pending:
        delegations = _engine.get_pending_delegations(agent_id)
    else:
        delegations = []
    return {
        "delegations": [
            {"id": d.delegation_id, "from": d.from_agent_id, "to": d.to_agent_id,
             "status": d.status.value, "title": d.title}
            for d in delegations
        ],
    }


@router.post("/delegations/{delegation_id}/accept")
async def accept_delegation(delegation_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.accept_delegation(delegation_id, payload["agent_id"])
    return {"ok": ok}


@router.post("/delegations/{delegation_id}/complete")
async def complete_delegation(delegation_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.complete_delegation(
        delegation_id, payload["agent_id"],
        payload.get("summary", ""),
    )
    return {"ok": ok}


# ── Reviews ──────────────────────────────────────────────────

@router.post("/review")
async def request_review(payload: dict = Body(...)):
    _ensure_engine()
    r = _engine.request_review(
        requester_id=payload["requester_id"],
        reviewer_id=payload["reviewer_id"],
        mission_id=payload.get("mission_id", ""),
        node_id=payload.get("node_id", ""),
        title=payload.get("title", ""),
        content=payload.get("content", {}),
        description=payload.get("description", ""),
    )
    return {"review_id": r.review_id, "status": r.status.value}


@router.post("/review/{review_id}")
async def submit_review(review_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.submit_review(
        review_id,
        verdict=payload.get("verdict", "approved"),
        comments=payload.get("comments", ""),
        suggestions=payload.get("suggestions"),
    )
    return {"ok": ok}


# ── Consensus ────────────────────────────────────────────────

@router.post("/consensus")
async def propose_consensus(payload: dict = Body(...)):
    _ensure_engine()
    mode = ConsensusMode(payload.get("mode", "majority"))
    p = _engine.propose_consensus(
        proposer_id=payload["proposer_id"],
        mission_id=payload.get("mission_id", ""),
        node_id=payload.get("node_id", ""),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        options=payload.get("options", []),
        mode=mode,
        minimum_voters=payload.get("minimum_voters", 2),
    )
    return {
        "proposal_id": p.proposal_id,
        "status": p.status.value,
        "mode": p.mode.value,
        "options": p.options,
    }


@router.post("/consensus/{proposal_id}/vote")
async def vote(proposal_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.vote(proposal_id, payload["agent_id"], payload["option"])
    proposal = _engine.get_consensus(proposal_id)
    return {
        "ok": ok,
        "status": proposal.status.value if proposal else "unknown",
        "winner": proposal.winner if proposal else None,
    }


# ── History ──────────────────────────────────────────────────

@router.get("/history")
async def get_history(mission_id: str = ""):
    _ensure_engine()
    if mission_id:
        return _engine.get_mission_history(mission_id)
    return _engine.stats()
