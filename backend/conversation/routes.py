"""REST API routes for Hermes OS Conversation (HOS-064)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from .conversation_manager import ConversationManager

# Global manager singleton
_manager: ConversationManager | None = None


def _get_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager


def create_conversation_routes(manager: ConversationManager) -> APIRouter:
    """Bind the container-owned manager to these routes (HOS-066B)."""
    global _manager
    _manager = manager
    return router


# In-memory route handlers (no framework dependency)


def handle_start_session(user_id: str = "anonymous") -> dict[str, Any]:
    """POST /conversation/start"""
    mgr = _get_manager()
    session = mgr.create_session(user_id)
    return {
        "success": True,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "created_at": session.created_at,
        "status": session.status.value,
    }


def handle_send_message(session_id: str, message: str) -> dict[str, Any]:
    """POST /conversation/message"""
    mgr = _get_manager()
    response = mgr.handle_message(session_id, message)
    session = mgr.get_session(session_id)
    return {
        "success": True,
        "session_id": response.session_id,
        "message": {
            "role": response.message.role.value,
            "content": response.message.content,
            "timestamp": response.message.timestamp,
        },
        "intent": {
            "type": response.intent.intent.value if response.intent else "unknown",
            "confidence": response.intent.confidence if response.intent else 0.0,
            "domain": response.intent.domain if response.intent else "general",
        } if response.intent else None,
        "requires_approval": response.requires_approval,
        "approval_request": response.approval_request,
        "suggested_actions": response.suggested_actions,
        "status": session.status.value if session else "unknown",
    }


def handle_get_history(session_id: str, limit: int = 50) -> dict[str, Any]:
    """GET /conversation/{id}"""
    mgr = _get_manager()
    history = mgr.get_history(session_id, limit)
    session = mgr.get_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "messages": history,
        "total": len(history),
        "status": session.status.value if session else "unknown",
    }


def handle_approve(session_id: str) -> dict[str, Any]:
    """POST /conversation/{id}/approve"""
    mgr = _get_manager()
    try:
        response = mgr.approve_action(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "message": response.message.content,
            "status": "approved",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}


def handle_cancel(session_id: str) -> dict[str, Any]:
    """POST /conversation/{id}/cancel"""
    mgr = _get_manager()
    try:
        response = mgr.cancel_action(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "message": response.message.content,
            "status": "cancelled",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}


def handle_get_context(session_id: str) -> dict[str, Any]:
    """GET /conversation/{id}/context"""
    mgr = _get_manager()
    session = mgr.get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    ctx = session.context
    return {
        "success": True,
        "session_id": session_id,
        "context": {
            "active_goal_id": ctx.active_goal_id,
            "active_mission_id": ctx.active_mission_id,
            "active_agents": ctx.active_agents,
            "current_runtime": ctx.current_runtime,
            "current_model": ctx.current_model,
            "workspace_status": ctx.workspace_status,
            "security_level": ctx.security_level,
            "recent_events": ctx.recent_events[-5:],
        },
    }


def handle_list_sessions(limit: int = 20) -> dict[str, Any]:
    """GET /conversation/sessions"""
    mgr = _get_manager()
    sessions = mgr.list_sessions(limit)
    return {
        "success": True,
        "sessions": sessions,
        "total": len(sessions),
    }


# ── HTTP surface ─────────────────────────────────────────────
# Paths mirror get_routes() below. "/sessions" precedes "/{session_id}" so the
# literal segment wins the match.

router = APIRouter(prefix="/conversation", tags=["conversation"])


@router.post("/start")
async def start_session(payload: dict = Body(default_factory=dict)) -> dict[str, Any]:
    return handle_start_session(payload.get("user_id", "anonymous"))


@router.post("/message")
async def send_message(payload: dict = Body(...)) -> dict[str, Any]:
    return handle_send_message(payload.get("session_id", ""), payload.get("message", ""))


@router.get("/sessions")
async def list_sessions(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    return handle_list_sessions(limit)


@router.get("/{session_id}")
async def get_history(
    session_id: str, limit: int = Query(50, ge=1, le=500)
) -> dict[str, Any]:
    return handle_get_history(session_id, limit)


@router.get("/{session_id}/context")
async def get_context(session_id: str) -> dict[str, Any]:
    return handle_get_context(session_id)


@router.post("/{session_id}/approve")
async def approve(session_id: str) -> dict[str, Any]:
    return handle_approve(session_id)


@router.post("/{session_id}/cancel")
async def cancel(session_id: str) -> dict[str, Any]:
    return handle_cancel(session_id)


def get_routes() -> dict[str, Any]:
    """Return route map for framework integration."""
    return {
        "POST /conversation/start": handle_start_session,
        "POST /conversation/message": handle_send_message,
        "GET /conversation/{id}": handle_get_history,
        "POST /conversation/{id}/approve": handle_approve,
        "POST /conversation/{id}/cancel": handle_cancel,
        "GET /conversation/{id}/context": handle_get_context,
        "GET /conversation/sessions": handle_list_sessions,
    }
