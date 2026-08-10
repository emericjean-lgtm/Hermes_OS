"""node_execution.py's execute_node() -> TaskExecution.mission_id — the real
bug found while doing a live end-to-end verification of the Workspace/
Filesystem tool layer's Mission integration (HOS-084): RealTaskExecutor's
workspace_project_for(task) reads task.mission_id, but the TaskExecution
built here never carried it (the field did not even exist on the dataclass
before this fix), so a real Mission run through /api/v1/missions could
never resolve its bound Project no matter how correctly everything else
was wired — only the hand-built fakes in test_real_task_executor.py had
mission_id set, which is exactly why that suite stayed green while the
live path silently fell back to plain chat with no tool calls at all.
"""
from __future__ import annotations

from backend.execution.execution_controller import ExecutionController
from backend.execution.mission_executor import MissionExecutor
from backend.mission.mission_models import MissionNode
from backend.mission.node_execution import make_node_executor


def test_execute_node_propagates_node_mission_id_onto_task_execution():
    # A real controller exercises the real prepare/execute path end to
    # end, rather than re-deriving MissionExecutor's contract in a mock.
    controller = ExecutionController(MissionExecutor())
    node = MissionNode(node_id="n1", title="Do a thing", mission_id="mission-real-123")

    execute_node = make_node_executor(controller)
    execute_node(node)

    execution = controller._executor  # noqa: SLF001 - reach the scheduler to inspect the registered task
    task = execution._scheduler.get_task("n1-task")  # noqa: SLF001
    assert task is not None
    assert task.mission_id == "mission-real-123"


def test_execute_node_leaves_mission_id_empty_when_node_has_none():
    controller = ExecutionController(MissionExecutor())
    node = MissionNode(node_id="n2", title="Standalone node")  # mission_id defaults to ""

    execute_node = make_node_executor(controller)
    execute_node(node)

    task = controller._executor._scheduler.get_task("n2-task")  # noqa: SLF001
    assert task is not None
    assert task.mission_id == ""


def test_start_execution_route_propagates_mission_id_to_tasks(monkeypatch):
    """execution/routes.py's standalone /execution/start API — same fix,
    same reasoning: without this a real Mission id passed here could never
    let RealTaskExecutor resolve a bound Project either.

    ``_executor``/``_controller`` are process-wide singletons shared by
    every test that touches this route (the module's own comment: "in the
    real app, these would be injected") — asserting against them directly
    is order-dependent on whatever else ran in the same session (retention
    eviction, task_id collisions). Swap in fresh, test-local instances so
    this test observes only its own registration.
    """
    import backend.execution.routes as execution_routes

    fresh_executor = MissionExecutor()
    monkeypatch.setattr(execution_routes, "_executor", fresh_executor)
    monkeypatch.setattr(execution_routes, "_controller", ExecutionController(fresh_executor))

    result = execution_routes.start_execution(
        goal="test goal",
        tasks=[{"id": "t1", "node_id": "t1", "title": "Task one"}],
        mission_id="mission-abc",
    )
    assert result["tasks_registered"] == 1

    task = fresh_executor._scheduler.get_task("t1")  # noqa: SLF001
    assert task is not None
    assert task.mission_id == "mission-abc"
