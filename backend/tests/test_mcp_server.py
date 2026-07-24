from __future__ import annotations

import json

import pytest

from backend.tests.conftest import open_mcp_session

# These go through the real MCP wire protocol (initialize, list_tools,
# call_tool) over an in-process ASGI transport — not a mocked shortcut.
# memory_index/memory_search aren't covered here for the same reason as
# elsewhere: they need a live Ollama server for embeddings.
#
# open_mcp_session is a plain async context manager (not a fixture) —
# see its docstring in conftest.py for why: fixture teardown runs in a
# different asyncio Task than setup, which breaks the anyio cancel scope
# inside FastMCP's session manager. Called directly here, setup and
# teardown share the test's own Task.

pytestmark = pytest.mark.asyncio


def _result(call_tool_result):
    """Tools that return a bare dict (security_evaluate, files_apply,
    memory_remember, tasks_create) have no output_schema, so FastMCP
    puts their JSON straight in content[0].text. Anything else — list,
    bool, str, dict | None — gets an auto-generated output_schema and
    wrapped as structuredContent={"result": ...} instead; unwrap that."""
    structured = call_tool_result.structuredContent
    if structured is not None:
        return structured["result"] if set(structured) == {"result"} else structured
    return json.loads(call_tool_result.content[0].text)


async def test_list_tools_exposes_all_expected_tools(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert names == {
        "security_evaluate",
        "files_list",
        "files_read",
        "files_diff",
        "files_apply",
        "memory_remember",
        "memory_list",
        "memory_forget",
        "memory_index",
        "memory_search",
        "research_query",
        "verify_output",
        "write_document",
        "analyze_image",
        "classify_request",
        "tasks_create",
        "tasks_get",
        "tasks_list",
        "tasks_update",
        "tasks_delete",
        "messages_list",
        "workflows_list",
        "workflows_get",
        "workflows_create",
        "workflows_delete",
        "workflows_simulate",
        "workflows_run",
        "projects_create",
        "projects_get",
        "projects_list",
        "projects_update",
        "projects_delete",
    }


async def test_security_evaluate_mandatory_category(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "security_evaluate",
            {"action_type": "git_critical", "description": "force push to main"},
        )
    body = _result(result)
    assert body["verdict"] == "require_human_validation"


async def test_files_apply_denied_outside_whitelist(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "files_apply", {"path": "/definitely/not/allowed.txt", "new_content": "hi"}
        )
    body = _result(result)
    assert body["applied"] is False
    assert body["verdict"] == "deny"


async def test_tasks_create_list_update_delete_roundtrip(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        created = _result(await session.call_tool("tasks_create", {"title": "MCP task"}))
        assert created["status"] == "todo"

        listed = _result(await session.call_tool("tasks_list", {}))
        assert [t["title"] for t in listed] == ["MCP task"]

        updated = _result(
            await session.call_tool(
                "tasks_update", {"task_id": created["id"], "status": "in_progress"}
            )
        )
        assert updated["status"] == "in_progress"

        deleted = _result(await session.call_tool("tasks_delete", {"task_id": created["id"]}))
        assert deleted is True

        listed_after = _result(await session.call_tool("tasks_list", {}))
        assert listed_after == []


async def test_research_query_returns_answer_and_passages(monkeypatch, tmp_path):
    from backend.agents.echo import EchoAgent
    from backend.connectors.ollama_client import OllamaClient

    # research_query needs both retrieval (Echo, embeddings) and
    # synthesis (a chat completion) — unlike the deterministic tools
    # above, the MCP session here uses the *real* OllamaClient (no fake
    # client injection point on this path), so both are stubbed at the
    # class level to avoid needing a live Ollama server.
    fake_passages = [{"id": "doc-0", "content": "RX 6800.", "metadata": {"source": "readme.md"}, "distance": 0.1}]
    monkeypatch.setattr(EchoAgent, "recall", lambda self, query, n_results=5: fake_passages)

    async def fake_list_running_models(self):
        return []

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None):
        for chunk in ["Answer", " from", " Minerva"]:
            yield chunk

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)
    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("research_query", {"query": "What GPU?"})

    body = _result(result)
    assert body["answer"] == "Answer from Minerva"
    assert body["passages"] == fake_passages
    assert body["model"]


async def test_verify_output_returns_parsed_verdict(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient

    async def fake_list_running_models(self):
        return []

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None):
        for chunk in ["VERDICT: approved\n", "ISSUES:\n- none\n", "CORRECTIONS:\nnone"]:
            yield chunk

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)
    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "verify_output", {"output": "def add(a, b): return a + b", "context": "addition function"}
        )

    body = _result(result)
    assert body["verdict"] == "approved"
    assert body["issues"] == []
    assert body["corrections"] == ""
    assert body["model"]


async def test_write_document_returns_document(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient

    async def fake_list_running_models(self):
        return []

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None):
        for chunk in ["# Title\n", "Some content."]:
            yield chunk

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)
    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("write_document", {"brief": "Write a README title and one line."})

    body = _result(result)
    assert body["document"] == "# Title\nSome content."
    assert body["model"]


async def test_analyze_image_returns_description(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient

    async def fake_list_running_models(self):
        return []

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None):
        for chunk in ["An ", "RX 6800 ", "graphics card."]:
            yield chunk

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)
    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("analyze_image", {"images": ["aGVsbG8="]})

    body = _result(result)
    assert body["description"] == "An RX 6800 graphics card."
    assert body["model"]


async def test_classify_request_returns_known_task_type(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient

    async def fake_list_running_models(self):
        return []

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None):
        yield "code_generation"

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)
    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("classify_request", {"request": "Write a sort function."})

    body = _result(result)
    assert body["task_type"] == "code_generation"
    assert body["model"]


async def test_messages_list_reflects_security_evaluate(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        await session.call_tool(
            "security_evaluate",
            {
                "action_type": "network_call",
                "description": "ping",
                "requesting_agent": "atlas",
                "task_id": "t1",
            },
        )
        result = await session.call_tool("messages_list", {"task_id": "t1"})

    body = _result(result)
    assert len(body) == 2
    types = {m["type"] for m in body}
    assert "VALIDATION_REQUEST" in types
    assert types & {"VALIDATION_GRANTED", "VALIDATION_DENIED", "ESCALATION"}


async def test_workflows_create_simulate_and_run_roundtrip(monkeypatch, tmp_path):
    # Uses deterministic tools (tasks_*) as node actions -> no live Ollama
    # needed, same reasoning as test_workflow_engine.py.
    workflow = {
        "id": "wf-1",
        "name": "Test",
        "nodes": [
            {"id": "create", "action": "tasks_create", "params": {"title": "hi"}},
            {"id": "list", "action": "tasks_list", "params": {}},
        ],
        "edges": [{"from": "create", "to": "list"}],
    }

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        created = _result(await session.call_tool("workflows_create", workflow))
        assert created["id"] == "wf-1"

        listed = _result(await session.call_tool("workflows_list", {}))
        assert [w["id"] for w in listed] == ["wf-1"]

        simulated = _result(await session.call_tool("workflows_simulate", {"workflow_id": "wf-1"}))
        assert simulated["execution_order"] == ["create", "list"]

        run = _result(await session.call_tool("workflows_run", {"workflow_id": "wf-1"}))
        assert run["status"] == "completed"
        assert run["node_results"]["create"]["status"] == "success"

        fetched = _result(await session.call_tool("workflows_get", {"workflow_id": "wf-1"}))
        assert fetched["id"] == "wf-1"

        deleted = _result(await session.call_tool("workflows_delete", {"workflow_id": "wf-1"}))
        assert deleted is True

        missing = _result(await session.call_tool("workflows_get", {"workflow_id": "wf-1"}))
        assert missing is None


async def test_projects_create_list_update_delete_roundtrip(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        created = _result(
            await session.call_tool("projects_create", {"name": "MCP project", "tags": ["pro"]})
        )
        assert created["status"] == "active"
        assert created["tags"] == ["pro"]

        listed = _result(await session.call_tool("projects_list", {}))
        assert [p["name"] for p in listed] == ["MCP project"]

        updated = _result(
            await session.call_tool(
                "projects_update", {"project_id": created["id"], "status": "archived"}
            )
        )
        assert updated["status"] == "archived"

        deleted = _result(await session.call_tool("projects_delete", {"project_id": created["id"]}))
        assert deleted is True

        listed_after = _result(await session.call_tool("projects_list", {}))
        assert listed_after == []


async def test_project_id_filters_tasks_memory_and_messages(monkeypatch, tmp_path):
    # One wiring test covering project_id across the deterministic tools
    # (no live Ollama needed) touched by the project_id rollout.
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        await session.call_tool("tasks_create", {"title": "a", "project_id": "proj-1"})
        await session.call_tool("tasks_create", {"title": "b", "project_id": "proj-2"})
        tasks = _result(await session.call_tool("tasks_list", {"project_id": "proj-1"}))
        assert [t["title"] for t in tasks] == ["a"]

        await session.call_tool(
            "memory_remember", {"type": "preference", "content": "x", "project_id": "proj-1"}
        )
        await session.call_tool(
            "memory_remember", {"type": "preference", "content": "y", "project_id": "proj-2"}
        )
        memories = _result(await session.call_tool("memory_list", {"project_id": "proj-1"}))
        assert [m["content"] for m in memories] == ["x"]

        await session.call_tool(
            "security_evaluate",
            {"action_type": "network_call", "description": "ping", "project_id": "proj-1"},
        )
        messages = _result(await session.call_tool("messages_list", {"project_id": "proj-1"}))
        assert messages
        assert all(m["project_id"] == "proj-1" for m in messages)


async def test_memory_remember_list_forget_roundtrip(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        created = _result(
            await session.call_tool(
                "memory_remember", {"type": "preference", "content": "reply in French"}
            )
        )
        assert created["content"] == "reply in French"

        listed = _result(await session.call_tool("memory_list", {"type": "preference"}))
        assert [m["content"] for m in listed] == ["reply in French"]

        forgotten = _result(
            await session.call_tool("memory_forget", {"memory_id": created["id"]})
        )
        assert forgotten is True
