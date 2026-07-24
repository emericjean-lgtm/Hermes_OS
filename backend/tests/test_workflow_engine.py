from __future__ import annotations

import pytest

from backend.workflows.engine import WorkflowEngine
from backend.workflows.schema import WorkflowDefinition

# The engine dispatches nodes through mcp_server.server.get_tool_registry(),
# whose deterministic tools (tasks_*, security_evaluate, files_*) reach the
# *global* get_agent_registry() — same as MCP tools and Minerva (see
# conftest.py's client fixture docstring). Only deterministic tools are used
# here so no live Ollama / OllamaClient mocking is needed. asyncio_mode =
# auto (pytest.ini) means async tests below need no explicit marker; the
# sync tests (simulate() has no I/O) are plain pytest functions.


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.core.message_bus import get_message_bus

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    get_message_bus.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
        get_agent_registry.cache_clear()
        get_message_bus.cache_clear()


def _workflow(**overrides) -> WorkflowDefinition:
    data = {
        "id": "wf-1",
        "name": "Test",
        "nodes": [
            {"id": "create", "action": "tasks_create", "params": {"title": "hello"}},
            {
                "id": "update",
                "action": "tasks_update",
                "params": {"task_id": "$steps.create.id", "status": "in_progress"},
            },
        ],
        "edges": [{"from": "create", "to": "update"}],
    }
    data.update(overrides)
    return WorkflowDefinition.from_dict(data)


async def test_run_executes_linear_chain_and_resolves_placeholders(isolated_settings):
    engine = WorkflowEngine()

    run = await engine.run(_workflow())

    assert run.status == "completed"
    assert run.node_results["create"].status == "success"
    assert run.node_results["update"].status == "success"
    created_id = run.node_results["create"].result["id"]
    assert run.node_results["update"].result["id"] == created_id
    assert run.node_results["update"].result["status"] == "in_progress"


async def test_run_publishes_task_delegation_and_result_on_the_bus(isolated_settings):
    from backend.core.message_bus import MessageType, get_message_bus

    engine = WorkflowEngine()
    run = await engine.run(_workflow())

    messages = get_message_bus().list_messages(task_id=run.id)
    types = {m.type for m in messages}
    assert MessageType.TASK_DELEGATION.value in types
    assert MessageType.TASK_RESULT.value in types
    assert len(messages) == 4  # 2 nodes x (delegation + result)


async def test_run_unknown_action_fails_that_node_only(isolated_settings):
    workflow = _workflow(
        nodes=[{"id": "bad", "action": "not_a_real_tool", "params": {}}], edges=[]
    )

    run = await WorkflowEngine().run(workflow)

    assert run.status == "failed"
    assert run.node_results["bad"].status == "failed"
    assert "not_a_real_tool" in run.node_results["bad"].error


async def test_run_bad_placeholder_fails_referencing_node(isolated_settings):
    workflow = _workflow(
        nodes=[
            {"id": "create", "action": "tasks_create", "params": {"title": "x"}},
            {
                "id": "update",
                "action": "tasks_update",
                "params": {"task_id": "$steps.create.no_such_key", "status": "done"},
            },
        ],
    )

    run = await WorkflowEngine().run(workflow)

    assert run.node_results["create"].status == "success"
    assert run.node_results["update"].status == "failed"
    assert "no_such_key" in run.node_results["update"].error


async def test_run_on_failure_edge_fires_when_predecessor_raises(isolated_settings):
    workflow = _workflow(
        nodes=[
            {"id": "read", "action": "files_read", "params": {"path": "/definitely/outside"}},
            {"id": "fallback", "action": "tasks_create", "params": {"title": "recovered"}},
            {"id": "happy", "action": "tasks_create", "params": {"title": "should not run"}},
        ],
        edges=[
            {"from": "read", "to": "fallback", "condition": "on_failure"},
            {"from": "read", "to": "happy", "condition": "on_success"},
        ],
    )

    run = await WorkflowEngine().run(workflow)

    assert run.node_results["read"].status == "failed"
    assert run.node_results["fallback"].status == "success"
    assert run.node_results["happy"].status == "skipped"
    assert run.status == "partially_successful"


async def test_run_halts_at_unapproved_human_validation_node(isolated_settings):
    workflow = _workflow(
        nodes=[
            {"id": "create", "action": "tasks_create", "params": {"title": "x"}, "human_validation": True},
            {"id": "after", "action": "tasks_list", "params": {}},
        ],
        edges=[{"from": "create", "to": "after"}],
    )

    run = await WorkflowEngine().run(workflow)

    assert run.status == "awaiting_validation"
    assert run.pending_nodes == ["create"]
    assert run.node_results["create"].status == "awaiting_validation"
    assert run.node_results["after"].status == "skipped"


async def test_run_proceeds_past_gate_when_approved(isolated_settings):
    workflow = _workflow(
        nodes=[
            {"id": "create", "action": "tasks_create", "params": {"title": "x"}, "human_validation": True},
            {"id": "after", "action": "tasks_list", "params": {}},
        ],
        edges=[{"from": "create", "to": "after"}],
    )

    run = await WorkflowEngine().run(workflow, approved_nodes={"create"})

    assert run.status == "completed"
    assert run.pending_nodes == []
    assert run.node_results["create"].status == "success"
    assert run.node_results["after"].status == "success"


def test_simulate_computes_topological_order_and_gates():
    workflow = _workflow(
        nodes=[
            {"id": "a", "action": "tasks_create"},
            {"id": "b", "action": "tasks_list"},
            {"id": "c", "action": "tasks_list", "human_validation": True},
        ],
        edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
    )

    result = WorkflowEngine().simulate(workflow)

    assert result.workflow_id == "wf-1"
    assert result.execution_order == ["a", "b", "c"]
    assert result.human_validation_nodes == ["c"]


def test_simulate_handles_fan_out_fan_in():
    workflow = _workflow(
        nodes=[
            {"id": "start", "action": "tasks_create"},
            {"id": "left", "action": "tasks_list"},
            {"id": "right", "action": "tasks_list"},
            {"id": "end", "action": "tasks_list"},
        ],
        edges=[
            {"from": "start", "to": "left"},
            {"from": "start", "to": "right"},
            {"from": "left", "to": "end"},
            {"from": "right", "to": "end"},
        ],
    )

    result = WorkflowEngine().simulate(workflow)

    assert result.execution_order[0] == "start"
    assert result.execution_order[-1] == "end"
    assert set(result.execution_order) == {"start", "left", "right", "end"}


def test_simulate_does_not_touch_message_bus(isolated_settings):
    from backend.core.message_bus import get_message_bus

    workflow = _workflow()
    WorkflowEngine().simulate(workflow)

    assert get_message_bus().list_messages() == []
