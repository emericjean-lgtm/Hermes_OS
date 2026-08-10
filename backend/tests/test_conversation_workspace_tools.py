"""Chat adapter for the Workspace/Filesystem tool layer
(conversation/routes.py) — tool gating on active_project_id, all without
needing a live model (respond_events' own tool-calling loop is Ollama's
concern, not this module's). Path resolution and the thin file_tools
adapter themselves live in backend/tools/workspace_chat_tools.py (shared
with Mission execution, execution/task_executor.py) — see
test_workspace_chat_tools.py for those."""
from __future__ import annotations

import pytest

from backend.conversation import routes as conv_routes
from backend.conversation.conversation_models import ConversationContext
from backend.projects.store import get_project_store
from backend.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()
    yield
    get_settings.cache_clear()
    get_project_store.cache_clear()


# ── _active_validated_project_root ──────────────────────────────


def test_no_project_id_returns_none():
    assert conv_routes._active_validated_project_root("") is None


def test_unknown_project_id_returns_none():
    assert conv_routes._active_validated_project_root("does-not-exist") is None


def test_unvalidated_project_returns_none(tmp_path):
    project = get_project_store().create(name="ws", root_path=str(tmp_path))
    assert conv_routes._active_validated_project_root(project.id) is None


def test_validated_active_project_returns_root(tmp_path):
    project = get_project_store().create(name="ws", root_path=str(tmp_path))
    get_project_store().validate(project.id)
    assert conv_routes._active_validated_project_root(project.id) == str(tmp_path.resolve())


def test_archived_validated_project_returns_none(tmp_path):
    project = get_project_store().create(name="ws", root_path=str(tmp_path))
    get_project_store().validate(project.id)
    get_project_store().update(project.id, status="archived")
    assert conv_routes._active_validated_project_root(project.id) is None


# ── _conversation_tools gating ───────────────────────────────────


def test_conversation_tools_excludes_workspace_tools_without_project():
    tools = conv_routes._conversation_tools(None)
    names = {t["function"]["name"] for t in tools}
    assert "web_search" in names
    assert not any(n.startswith("workspace_") for n in names)


def test_conversation_tools_includes_workspace_tools_with_project(tmp_path):
    tools = conv_routes._conversation_tools(str(tmp_path))
    names = {t["function"]["name"] for t in tools}
    assert {"workspace_list", "workspace_exists", "workspace_read", "workspace_write"} <= names


# ── ConversationContext / ConversationManager wiring ─────────────


def test_conversation_context_defaults_no_project():
    assert ConversationContext().active_project_id == ""


def test_set_project_binds_and_unbinds_session():
    from backend.conversation.conversation_manager import ConversationManager

    mgr = ConversationManager()
    session = mgr.create_session()
    assert session.context.active_project_id == ""

    mgr.set_project(session.session_id, "proj-123")
    assert mgr.get_session(session.session_id).context.active_project_id == "proj-123"

    mgr.set_project(session.session_id, None)
    assert mgr.get_session(session.session_id).context.active_project_id == ""


def test_set_project_unknown_session_returns_none():
    from backend.conversation.conversation_manager import ConversationManager

    mgr = ConversationManager()
    assert mgr.set_project("does-not-exist", "proj-1") is None


# ── _execute_conversation_tool: dispatch to the shared adapter ──


@pytest.mark.asyncio
async def test_execute_conversation_tool_read_denied_outside_project(tmp_path):
    """No project bound (project_root="") — the adapter must not invent
    access; it reports the real Aegis refusal, same as file_tools itself
    would raise."""
    result = await conv_routes._execute_conversation_tool(
        "workspace_read", {"path": "f.txt"}, project_id="", project_root="",
    )
    assert "Refusé par Aegis" in result or "refusée" in result.lower()


@pytest.mark.asyncio
async def test_execute_conversation_tool_unknown_name_reports_unknown():
    result = await conv_routes._execute_conversation_tool(
        "workspace_delete_everything", {}, project_id="", project_root="",
    )
    assert "Unknown tool" in result
