"""The retry actually runs (HOS-100).

HOS-099 produced the decision and the brief but stopped short of acting on
them, which left the loop open: the system knew a mission had reported
success over an untouched workspace, knew what to say about it, and did
nothing. These tests drive the real route helper and assert that a mission
whose first attempt changes nothing is genuinely run a second time — with
the evidence attached, and not indefinitely.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from backend.mission.mission_models import Mission, MissionNode, MissionStatus


@pytest.fixture
def project(monkeypatch, tmp_path):
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "retry.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    created = get_project_store().create(name="ws", root_path=str(workspace))
    yield created, workspace
    get_settings.cache_clear()
    get_project_store.cache_clear()


def _mission(project_id: str, objective: str = "Create REPORT.md.") -> Mission:
    mission = Mission(title="t", description=objective, objective=objective)
    mission.context.project_id = project_id
    mission.nodes = [MissionNode(node_id="n1", title="do the work")]
    return mission


def _drive(mission: Mission, executor) -> int:
    """Run the real route helper against a patched module-level executor."""
    from backend.mission import routes

    routes._executor = executor  # noqa: SLF001
    executor.build_graph(mission, mission.nodes, [])
    mission.status = MissionStatus.READY
    executor.start_mission(mission)
    return asyncio.run(routes._run_mission_steps(mission))  # noqa: SLF001


def test_a_mission_that_changed_nothing_is_run_again(project):
    """The first attempt reports success and writes nothing; the second
    writes for real. Without the retry the mission would end 'successful'
    over an empty workspace — the exact false positive being removed."""
    _created, workspace = project
    from backend.mission.graph_executor import GraphExecutor

    attempts: list[str] = []

    def execute_node(node):
        attempts.append(node.node_id)
        if len(attempts) > 1:            # second attempt does real work
            (workspace / "REPORT.md").write_text("done", encoding="utf-8")
        return True

    mission = _mission(_created.id)
    _drive(mission, GraphExecutor(execute_node=execute_node))

    assert len(attempts) == 2, "the mission was not retried"
    assert (workspace / "REPORT.md").is_file()


def test_the_retry_carries_the_evidence(project):
    """The retry must not re-send the identical prompt — the objective the
    second attempt sees has to contain what the filesystem showed."""
    _created, workspace = project
    from backend.mission.graph_executor import GraphExecutor

    seen_objectives: list[str] = []

    def execute_node(node):
        seen_objectives.append(node.mission_id and "" or "")
        return True

    mission = _mission(_created.id)
    _drive(mission, GraphExecutor(execute_node=execute_node))

    assert "unchanged" in mission.objective.lower()
    assert "Create REPORT.md." in mission.objective
    assert mission.metadata["original_objective"] == "Create REPORT.md."


def test_a_successful_mission_is_not_retried(project):
    _created, workspace = project
    from backend.mission.graph_executor import GraphExecutor

    attempts: list[str] = []

    def execute_node(node):
        attempts.append(node.node_id)
        (workspace / "REPORT.md").write_text("done", encoding="utf-8")
        return True

    mission = _mission(_created.id)
    _drive(mission, GraphExecutor(execute_node=execute_node))

    assert len(attempts) == 1


def test_the_retry_does_not_loop_forever(project):
    """A node that never writes anything must stop after the budget, not
    burn the machine. This is the test that would catch an infinite loop."""
    _created, _workspace = project
    from backend.mission.graph_executor import GraphExecutor

    attempts: list[str] = []

    def execute_node(node):
        attempts.append(node.node_id)
        return True

    mission = _mission(_created.id)
    _drive(mission, GraphExecutor(execute_node=execute_node))

    assert len(attempts) == 2, f"expected one retry, got {len(attempts)} attempts"
    assert int(mission.metadata["attempts"]) == 2


def test_a_mission_without_a_workspace_is_not_retried():
    """Nothing was measured, so there is no contradiction to act on."""
    from backend.mission.graph_executor import GraphExecutor

    attempts: list[str] = []

    def execute_node(node):
        attempts.append(node.node_id)
        return True

    mission = Mission(title="t", objective="do something")
    mission.nodes = [MissionNode(node_id="n1", title="do")]
    _drive(mission, GraphExecutor(execute_node=execute_node))

    assert len(attempts) == 1
