"""REST API routes for Hermes OS Conversation (HOS-064)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse

from .conversation_manager import ConversationManager

logger = logging.getLogger("hermes_os.conversation.routes")

# Global manager singleton
_manager: ConversationManager | None = None


def _get_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager


_web_search_connector = None


def _get_web_search_connector():
    global _web_search_connector
    if _web_search_connector is None:
        from backend.tools.connectors.web_search import WebSearchConnector

        _web_search_connector = WebSearchConnector()
    return _web_search_connector


def _web_search_authorized() -> bool:
    """Aegis's ``web_search`` category (config/security.yaml), evaluated
    fresh each turn — same real, local, no-network rules check as
    ``_cloud_authorized()`` in backend/model_intelligence/routes.py. A
    live chat stream has no approval UI to pause into (unlike Missions'
    pause/resume), so below the configured autonomy threshold the tool is
    refused outright and the model is told so, rather than left hanging."""
    from backend.core.config import get_settings, load_security_config
    from backend.security.aegis_engine import ActionRequest, AegisEngine, Verdict
    from backend.security.permission_matrix import PermissionMatrix

    settings = get_settings()
    matrix = PermissionMatrix(load_security_config())
    engine = AegisEngine(matrix, settings.allowed_paths_list)
    decision = engine.evaluate(ActionRequest(
        action_type="web_search",
        description="Real internet search requested by a chat turn",
        requesting_agent="conversation",
    ))
    return decision.verdict == Verdict.ALLOW


async def _execute_conversation_tool(
    name: str, arguments: dict[str, Any], *, project_id: str, project_root: str
) -> str:
    """Dispatches to the right adapter by tool name — the single
    tool_executor passed to agent.respond_events, since that call takes
    exactly one. Both branches are thin adapters (web search's own
    connector; workspace/chat_tools' file_tools wrapper, shared with
    Mission execution — execution/task_executor.py) — no tool logic
    lives here."""
    if name == "web_search":
        return await _execute_web_search(name, arguments)
    if name.startswith("workspace_"):
        from backend.tools.workspace_chat_tools import execute_workspace_tool
        return await execute_workspace_tool(
            name, arguments, project_id=project_id, project_root=project_root
        )
    return f"Unknown tool {name!r} — nothing executed."


async def _execute_web_search(name: str, arguments: dict[str, Any]) -> str:
    if name != "web_search":
        return f"Unknown tool {name!r} — nothing executed."
    if not _web_search_authorized():
        return (
            "Recherche refusée : validation humaine requise au niveau "
            "d'autonomie actuel (Aegis, catégorie web_search)."
        )
    query = str(arguments.get("query", "")).strip()
    if not query:
        return "No search query was provided."
    raw_max = arguments.get("max_results")
    max_results = int(raw_max) if isinstance(raw_max, (int, float)) else None

    connector = _get_web_search_connector()
    try:
        results = await connector.search(query, max_results=max_results)
    except Exception as exc:
        return f"Search for {query!r} failed: {type(exc).__name__}: {exc}"
    if not results:
        return f"No results found for {query!r}."
    return "\n\n".join(
        f"{i}. {r.title}\n   {r.url}\n   {r.snippet}"
        for i, r in enumerate(results, start=1)
    )


def _active_validated_project_root(project_id: str) -> str | None:
    """The project's root_path, but only if it exists, is ACTIVE and its
    validation_status is "valid" — the same three-way check
    AegisAgent._dynamic_allowed_paths applies, repeated here so the chat
    doesn't offer a tool it knows Aegis would just refuse (a UX
    improvement, not a security boundary — Aegis re-checks independently
    regardless of what this returns)."""
    if not project_id:
        return None
    try:
        from backend.projects.project_manager import ProjectStatus, ValidationStatus
        from backend.projects.store import get_project_store
        project = get_project_store().get(project_id)
    except Exception:
        return None
    if project is None or not project.root_path:
        return None
    if project.status != ProjectStatus.ACTIVE.value:
        return None
    if project.validation_status != ValidationStatus.VALID.value:
        return None
    return project.root_path


#: Offered to every conversation turn — the model decides whether a given
#: question actually needs it (config/models.yaml's `orchestrator` role,
#: hermes_prime's default model, was upgraded specifically for reliable
#: tool-calling; see that file's own comment). A model that never calls it
#: costs nothing extra beyond the tool schema in the prompt. Workspace
#: tools are additionally gated on project_root being non-None — no
#: active, validated workspace means no filesystem tools offered at all
#: (Workspace/Filesystem tool layer, Phase 9).
def _conversation_tools(project_root: str | None) -> list[dict[str, Any]]:
    from backend.tools.connectors.web_search import web_search_tool_schema
    from backend.tools.workspace_chat_tools import workspace_tool_schemas

    tools = [web_search_tool_schema()]
    if project_root is not None:
        tools.extend(workspace_tool_schemas())
    return tools


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
            "active_project_id": ctx.active_project_id,
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


def handle_delete_session(session_id: str) -> dict[str, Any]:
    """DELETE /conversation/{session_id}

    Now that transcripts outlive the process (HOS-101), erasing one has to
    be possible from the same surface that keeps it.
    """
    deleted = _get_manager().delete_session(session_id)
    return {"success": True, "deleted": deleted, "session_id": session_id}


# ── HTTP surface ─────────────────────────────────────────────
# Paths mirror get_routes() below. "/sessions" precedes "/{session_id}" so the
# literal segment wins the match.

router = APIRouter(prefix="/conversation", tags=["conversation"])


@router.post("/start")
async def start_session(payload: dict = Body(default_factory=dict)) -> dict[str, Any]:
    return handle_start_session(payload.get("user_id", "anonymous"))


@router.post("/{session_id}/project")
async def bind_project(session_id: str, payload: dict = Body(default_factory=dict)) -> dict[str, Any]:
    """Bind (project_id set) or unbind (project_id omitted/null) this
    session's active workspace. The real mutation ConversationContext's
    own update_context() placeholder never provided — see
    ConversationManager.set_project(). Filesystem tools only start
    appearing in the next /stream call once this has been called with a
    project_id that resolves to an ACTIVE, validation_status="valid"
    Project (see _active_validated_project_root)."""
    mgr = _get_manager()
    project_id = payload.get("project_id") or None
    session = mgr.set_project(session_id, project_id)
    if session is None:
        return {"success": False, "error": f"Session {session_id} not found"}
    return {
        "success": True,
        "session_id": session_id,
        "active_project_id": session.context.active_project_id,
    }


@router.post("/message")
async def send_message(payload: dict = Body(...)) -> dict[str, Any]:
    return handle_send_message(payload.get("session_id", ""), payload.get("message", ""))


@router.post("/stream")
async def stream_message(payload: dict = Body(...)) -> StreamingResponse:
    """Streamed reply, token by token (HOS-074).

    The Assistant used to POST to ``/conversation/message``, which blocks
    until the whole answer exists: on a local 30B model at ~13 tok/s, a
    400-token reply is 30 s of a bouncing-dots animation with nothing to
    read. A real streaming pipeline already existed (``POST /chat``) but
    nothing in the Cockpit called it, and it carries no session, no
    history and no intent gating.

    So this route keeps the conversation module's own semantics (session,
    history, intent, approval) and delegates the actual inference to the
    *same* agent machinery ``/chat`` uses — ``BaseAgent.respond_events``,
    with its real ModelRouter decision, reasoning channel and cloud
    fallback — rather than adding a third inference path that could drift
    from both.

    Body is NDJSON, one object per line, so the client can distinguish
    reasoning from answer without inferring anything from framing:
    ``{"kind": "thinking"|"content"|"done"|"error", ...}``.
    """
    session_id = str(payload.get("session_id") or "")
    message = str(payload.get("message") or "")
    if not message.strip():
        return StreamingResponse(
            iter([json.dumps({"kind": "error", "error": "message is required"}) + "\n"]),
            media_type="application/x-ndjson",
        )

    mgr = _get_manager()
    session_id, model_messages, intent = mgr.begin_stream(session_id, message)

    # HOS-075: manual model choice / reasoning-effort presets. `role` names
    # a real config/models.yaml role (validated below, never a raw model
    # string a client could invent) — None keeps automatic routing exactly
    # as before this existed.
    forced_role = payload.get("role") or None
    forced_thinking_raw = payload.get("thinking")
    forced_thinking = bool(forced_thinking_raw) if forced_thinking_raw is not None else None

    # Workspace/Filesystem tool layer (Phase 9): filesystem tools are only
    # offered when this session is bound to an ACTIVE, validated Project —
    # re-checked fresh every turn, never cached, so unbinding or
    # invalidating the workspace mid-conversation takes effect immediately.
    active_session = mgr.get_session(session_id)
    project_id = active_session.context.active_project_id if active_session else ""
    project_root = _active_validated_project_root(project_id)

    async def _tool_executor(name: str, arguments: dict[str, Any]) -> str:
        return await _execute_conversation_tool(
            name, arguments, project_id=project_id, project_root=project_root or "",
        )

    decision = None
    events: AsyncIterator[Any] | None = None
    try:
        from backend.core.agent_registry import get_agent_registry

        agent = get_agent_registry().get(str(payload.get("agent") or "hermes_prime"))
        decision, events = await agent.respond_events(
            model_messages, task_type=payload.get("task_type") or None,
            forced_role=forced_role, forced_thinking=forced_thinking,
            tools=_conversation_tools(project_root), tool_executor=_tool_executor,
        )
    except KeyError as exc:
        mgr.finish_stream(session_id, "")
        return StreamingResponse(
            iter([json.dumps({"kind": "error", "session_id": session_id,
                              "error": f"unknown role {forced_role!r}: {exc}"},
                             ensure_ascii=False) + "\n"]),
            media_type="application/x-ndjson",
        )
    except Exception as exc:
        # The model could not even be reached — say so as a real error
        # rather than streaming an empty, successful-looking answer.
        logger.warning("conversation stream could not start", exc_info=True)
        detail = f"{type(exc).__name__}: {exc}"
        mgr.finish_stream(session_id, "")
        return StreamingResponse(
            iter([json.dumps({"kind": "error", "session_id": session_id,
                              "error": detail}, ensure_ascii=False) + "\n"]),
            media_type="application/x-ndjson",
        )

    async def _body() -> AsyncIterator[str]:
        collected: list[str] = []
        try:
            async for chunk in events:
                if chunk.kind == "content":
                    collected.append(chunk.text)
                payload_out: dict[str, Any] = {"kind": chunk.kind, "text": chunk.text}
                # tool_calls/tool_result (real web search) carry structured
                # data no client can reconstruct from `text` alone — the
                # search query, or the result a client would otherwise have
                # no way to show as anything but blank.
                tool_calls = getattr(chunk, "tool_calls", None)
                if tool_calls:
                    payload_out["tool_calls"] = tool_calls
                yield json.dumps(payload_out, ensure_ascii=False) + "\n"
        except Exception as exc:  # mid-stream drop: keep what arrived
            logger.warning("conversation stream interrupted", exc_info=True)
            yield json.dumps({"kind": "error", "error": f"{type(exc).__name__}: {exc}"},
                             ensure_ascii=False) + "\n"
        finally:
            # Runs on client disconnect too (the user pressing stop), so a
            # partial answer still becomes real history rather than
            # vanishing and desynchronising the next turn.
            answer = "".join(collected)
            mgr.finish_stream(session_id, answer, metadata={
                "model": decision.model, "intent": intent.intent.value,
            })
        # Context-window usage (HOS-075): an honest estimate (~4 chars/token,
        # the same approximation RealTaskExecutor already uses when a
        # runtime doesn't report real counts — see _estimate_tokens in
        # backend/execution/task_executor.py) over what was actually sent —
        # the prompt this turn plus the answer just generated — against the
        # role's real, benchmarked num_ctx (HOS-065C). Not a token-exact
        # count: Ollama's own tokenizer isn't exposed without a real call
        # per message, and an honest estimate beats a silent omission.
        prompt_chars = sum(len(m.get("content", "")) for m in model_messages)
        used_tokens = max(1, (prompt_chars + len(answer)) // 4)
        yield json.dumps({
            "kind": "done", "session_id": session_id,
            "intent": {"type": intent.intent.value, "confidence": intent.confidence,
                       "domain": intent.domain},
            "context": {"used_tokens_estimate": used_tokens, "window": decision.num_ctx},
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(
        _body(),
        media_type="application/x-ndjson",
        headers={
            "X-Hermes-Session": session_id,
            "X-Hermes-Model": decision.model,
            "X-Hermes-Tier": decision.tier,
            "X-Hermes-Role": decision.role,
            "X-Hermes-Reason": decision.reason,
            "X-Hermes-Thinking": "true" if decision.thinking else "false",
            "X-Hermes-Intent": intent.intent.value,
            # Proxies that buffer would defeat the point of streaming.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    return handle_delete_session(session_id)


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
        "DELETE /conversation/{id}": handle_delete_session,
    }
