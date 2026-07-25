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
        "documents_index",
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
        "system_status",
        "workflows_list",
        "workflows_get",
        "workflows_create",
        "workflows_delete",
        "workflows_simulate",
        "workflows_run",
        "workflows_get_run",
        "projects_create",
        "projects_get",
        "projects_list",
        "projects_update",
        "projects_delete",
        "skills_list",
        "skills_get",
        "skills_use",
        "skills_delete",
        "skills_index",
        "skills_search",
        "evolution_process_task",
        "evolution_progression",
    }


async def test_security_evaluate_mandatory_category(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "security_evaluate",
            {"action_type": "git_critical", "description": "force push to main"},
        )
    body = _result(result)
    assert body["verdict"] == "require_human_validation"
    assert body["advisory"] is None


async def test_security_evaluate_include_advisory(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient

    async def fake_chat_stream(self, model, messages, *, temperature=None, top_p=None, num_ctx=None, think=None):
        yield "This force-pushes to main, which rewrites shared history."

    monkeypatch.setattr(OllamaClient, "chat_stream", fake_chat_stream)

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "security_evaluate",
            {
                "action_type": "git_critical",
                "description": "force push to main",
                "include_advisory": True,
            },
        )
    body = _result(result)
    assert body["verdict"] == "require_human_validation"
    assert "force-pushes" in body["advisory"]


async def test_files_apply_denied_outside_whitelist(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool(
            "files_apply", {"path": "/definitely/not/allowed.txt", "new_content": "hi"}
        )
    body = _result(result)
    assert body["applied"] is False
    assert body["verdict"] == "deny"


async def test_files_apply_narrowed_to_project_root(monkeypatch, tmp_path, security_config):
    # open_mcp_session (unlike the `client` fixture) sets ALLOWED_PATHS to
    # tmp_path/allowed, so this can exercise the ALLOW path too, not just
    # deny — see test_files_endpoint.py's comment for why the REST-level
    # tests stick to deny-only. autonomy_level is bumped to "medium" (the
    # real config/security.yaml default is "low", which would gate every
    # file_write behind require_human_validation regardless of whitelist,
    # masking whether project-root narrowing itself worked).
    monkeypatch.setattr(
        "backend.agents.aegis.load_security_config",
        lambda: dict(security_config, autonomy_level="medium"),
    )
    allowed_dir = tmp_path / "allowed"
    project_dir = allowed_dir / "project-a"
    other_dir = allowed_dir / "project-b"

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        # open_mcp_session already created "allowed" (and set it as
        # ALLOWED_PATHS) by this point — create the project subdirs now.
        project_dir.mkdir()
        other_dir.mkdir()

        project = _result(
            await session.call_tool("projects_create", {"name": "A", "root_path": str(project_dir)})
        )

        inside = _result(
            await session.call_tool(
                "files_apply",
                {
                    "path": str(project_dir / "f.txt"),
                    "new_content": "hi",
                    "project_id": project["id"],
                },
            )
        )
        assert inside["applied"] is True

        outside = _result(
            await session.call_tool(
                "files_apply",
                {
                    "path": str(other_dir / "f.txt"),
                    "new_content": "hi",
                    "project_id": project["id"],
                },
            )
        )
        assert outside["applied"] is False
        assert outside["verdict"] == "deny"


async def test_tasks_update_run_evolution_extracts_skill(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        created = _result(await session.call_tool("tasks_create", {"title": "Ship it"}))

        updated = _result(
            await session.call_tool(
                "tasks_update", {"task_id": created["id"], "status": "done", "run_evolution": True}
            )
        )
        assert updated["evolution"]["outcome"] is True
        assert updated["evolution"]["skill_id"] is not None

        skill = _result(await session.call_tool("skills_get", {"skill_id": updated["evolution"]["skill_id"]}))
        assert skill["name"] == "Ship it"


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


async def test_workflows_run_resumes_via_run_id(monkeypatch, tmp_path):
    # "create" runs on the first call (not itself gated); "gate" blocks
    # "list" until approved — so "create" already has a real result by
    # the time we resume, proving it wasn't re-executed rather than just
    # not-yet-executed.
    workflow = {
        "id": "wf-gated",
        "name": "Test",
        "nodes": [
            {"id": "create", "action": "tasks_create", "params": {"title": "hi"}},
            {"id": "gate", "action": "tasks_list", "params": {}, "human_validation": True},
            {"id": "list", "action": "tasks_list", "params": {}},
        ],
        "edges": [{"from": "create", "to": "gate"}, {"from": "gate", "to": "list"}],
    }

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        await session.call_tool("workflows_create", workflow)

        first = _result(await session.call_tool("workflows_run", {"workflow_id": "wf-gated"}))
        assert first["status"] == "awaiting_validation"
        assert first["pending_nodes"] == ["gate"]
        created_id = first["node_results"]["create"]["result"]["id"]

        resumed = _result(
            await session.call_tool(
                "workflows_run",
                {"workflow_id": "wf-gated", "run_id": first["id"], "approved_nodes": ["gate"]},
            )
        )
        assert resumed["id"] == first["id"]
        assert resumed["status"] == "completed"
        assert resumed["node_results"]["create"]["result"]["id"] == created_id

        fetched = _result(await session.call_tool("workflows_get_run", {"run_id": first["id"]}))
        assert fetched["status"] == "completed"

        tasks = _result(await session.call_tool("tasks_list", {}))
        assert len(tasks) == 1  # "create" wasn't re-executed on resume


async def test_workflows_get_run_returns_none_for_unknown_id(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("workflows_get_run", {"run_id": "does-not-exist"})
    assert _result(result) is None


async def test_workflows_run_with_unknown_run_id_errors(monkeypatch, tmp_path):
    workflow = {
        "id": "wf-1",
        "name": "Test",
        "nodes": [{"id": "create", "action": "tasks_create", "params": {"title": "hi"}}],
        "edges": [],
    }
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        await session.call_tool("workflows_create", workflow)
        result = await session.call_tool(
            "workflows_run", {"workflow_id": "wf-1", "run_id": "does-not-exist"}
        )
    assert result.isError is True


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


async def test_system_status_reports_agents_and_gpu_null_without_rocm(monkeypatch, tmp_path):
    from backend.connectors.ollama_client import OllamaClient
    from backend.core.config import get_settings
    from backend.monitoring.gpu_monitor import GpuMonitor
    from backend.tests.conftest import FakeOllamaClient

    async def fake_list_running_models(self):
        return [{"name": "qwen3.5:9b"}]

    monkeypatch.setattr(OllamaClient, "list_running_models", fake_list_running_models)

    # Injected fake rather than relying on the sandbox's own ambient
    # absence of rocm-smi: a real machine (e.g. the actual RX 6800 dev
    # box) genuinely finds GPU data via rocm-smi/PowerShell, which would
    # make `gpu is None` false there even though nothing about this test
    # is platform-specific — it's testing the degrade path itself.
    monkeypatch.setattr(
        "backend.mcp_server.server.get_gpu_monitor",
        lambda: GpuMonitor(
            FakeOllamaClient(running_models=["qwen3.5:9b"]),
            get_settings(),
            run_command=lambda args: None,
            disk_path=str(tmp_path),
            platform_name="Linux",
        ),
    )

    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("system_status", {})

    body = _result(result)
    assert "hermes_prime" in body["enabled_agents"]
    assert "standard" in body["configured_roles"]
    assert body["gpu"] is None
    assert body["loaded_models"] == [{"name": "qwen3.5:9b"}]
    assert "disk_free_gb" in body


async def test_evolution_process_task_and_skills_roundtrip(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        task = _result(await session.call_tool("tasks_create", {"title": "Ship it"}))
        await session.call_tool("tasks_update", {"task_id": task["id"], "status": "done"})

        processed = _result(await session.call_tool("evolution_process_task", {"task_id": task["id"]}))
        assert processed["outcome"] is True
        assert processed["skill_id"] is not None

        skill = _result(await session.call_tool("skills_get", {"skill_id": processed["skill_id"]}))
        assert skill["name"] == "Ship it"
        assert skill["status"] == "in_review"

        listed = _result(await session.call_tool("skills_list", {}))
        assert [s["name"] for s in listed] == ["Ship it"]

        used = _result(
            await session.call_tool("skills_use", {"skill_id": skill["id"], "success": True})
        )
        assert used["uses"] == 1
        assert used["confidence"] > skill["confidence"]

        progression = _result(await session.call_tool("evolution_progression", {}))
        assert progression["tasks_succeeded"] == 1
        assert progression["skills_total"] == 1

        deleted = _result(await session.call_tool("skills_delete", {"skill_id": skill["id"]}))
        assert deleted is True


async def test_skills_index_returns_false_for_unknown_id(monkeypatch, tmp_path):
    # skills_index/skills_search need a live Ollama server for real
    # embeddings this sandbox doesn't have — only the unknown-id short
    # circuit (before any embedding call) is exercised here.
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = _result(await session.call_tool("skills_index", {"skill_id": "does-not-exist"}))
    assert result is False


async def test_evolution_process_task_raises_for_unknown_task(monkeypatch, tmp_path):
    async with open_mcp_session(monkeypatch, tmp_path) as session:
        result = await session.call_tool("evolution_process_task", {"task_id": "does-not-exist"})
    assert result.isError is True
