"""HOS-020 sentinel tests — Multi-Agent Supervisor.

Tests mission creation, planning, state transitions, agent orchestration,
tick cycle and statistics without any concrete agent or network call.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

import pytest

from backend.agent.lifecycle import AgentInstance, AgentLifecycleManager, AgentState
from backend.agent.supervisor import (
    MissionContext,
    MissionInstance,
    MissionState,
    MultiAgentSupervisor,
    SupervisorError,
    SupervisorEvent,
    SupervisorStatistics,
)
from backend.agent.task_planner import PlannedTask, TaskPlanner


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def planner() -> TaskPlanner:
    return TaskPlanner()


@pytest.fixture
def lifecycle() -> AgentLifecycleManager:
    return AgentLifecycleManager()


@pytest.fixture
def supervisor(planner: TaskPlanner, lifecycle: AgentLifecycleManager) -> MultiAgentSupervisor:
    return MultiAgentSupervisor(planner, lifecycle)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_mission_context_defaults() -> None:
    ctx = MissionContext(mission_id="m1")
    assert ctx.mission_id == "m1"
    assert ctx.priority == 5


def test_mission_context_frozen() -> None:
    ctx = MissionContext(mission_id="m1")
    with pytest.raises(AttributeError):
        ctx.mission_id = "m2"  # type: ignore[misc]


def test_supervisor_statistics_defaults() -> None:
    s = SupervisorStatistics()
    assert s.missions_started == 0
    assert s.missions_completed == 0
    assert s.agents_created == 0


def test_mission_state_values() -> None:
    assert MissionState.CREATED.value == "created"
    assert MissionState.PLANNING.value == "planning"
    assert MissionState.READY.value == "ready"
    assert MissionState.RUNNING.value == "running"
    assert MissionState.COMPLETED.value == "completed"
    assert MissionState.FAILED.value == "failed"
    assert MissionState.CANCELLED.value == "cancelled"


def test_supervisor_event_values() -> None:
    assert SupervisorEvent.MISSION_CREATED.value == "supervisor.mission_created"
    assert SupervisorEvent.MISSION_STARTED.value == "supervisor.mission_started"
    assert SupervisorEvent.AGENT_CREATED.value == "supervisor.agent_created"


# ============================================================================
# Mission creation and planning
# ============================================================================


def test_create_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1", title="Test")
    tasks = [PlannedTask(id="t1", title="Task 1")]
    mission = supervisor.create_mission(ctx, tasks)
    assert mission.state == MissionState.READY
    assert mission.task_plan is not None
    assert mission.task_plan.execution_graph is not None


def test_create_mission_duplicate_raises(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    with pytest.raises(SupervisorError, match="already exists"):
        supervisor.create_mission(ctx, [PlannedTask(id="t2", title="T")])


def test_create_mission_with_dependencies(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1", title="Deps")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
        PlannedTask(id="c", title="C", dependencies=frozenset({"b"})),
    ]
    mission = supervisor.create_mission(ctx, tasks)
    assert mission.state == MissionState.READY
    graph = mission.task_plan.execution_graph
    assert graph is not None
    assert len(graph.list_nodes()) == 3
    assert len(graph.list_edges()) == 2


# ============================================================================
# Mission state transitions
# ============================================================================


def test_start_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    mission = supervisor.start_mission("m1")
    assert mission.state == MissionState.RUNNING


def test_start_nonexistent_mission_raises(supervisor: MultiAgentSupervisor) -> None:
    with pytest.raises(SupervisorError, match="not found"):
        supervisor.start_mission("nonexistent")


def test_pause_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    mission = supervisor.pause_mission("m1")
    assert mission.state == MissionState.PAUSED


def test_resume_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    supervisor.pause_mission("m1")
    mission = supervisor.resume_mission("m1")
    assert mission.state == MissionState.RUNNING


def test_cancel_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    mission = supervisor.cancel_mission("m1")
    assert mission.state == MissionState.CANCELLED


def test_cancel_mission_twice_raises(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.cancel_mission("m1")
    with pytest.raises(SupervisorError, match="Invalid mission transition"):
        supervisor.cancel_mission("m1")


# ============================================================================
# Invalid mission transitions
# ============================================================================


def test_start_ready_twice_raises(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    with pytest.raises(SupervisorError, match="Invalid mission transition"):
        supervisor.start_mission("m1")


# ============================================================================
# Tick — agent creation and execution
# ============================================================================


def test_tick_creates_agents_for_root_tasks(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    changed = supervisor.tick()
    assert len(changed) > 0
    # An agent should have been created for the root task
    agents = supervisor._lifecycle.list_agents()
    assert len(agents) >= 1


def test_tick_respects_dependencies(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    supervisor.create_mission(ctx, tasks)
    supervisor.start_mission("m1")
    supervisor.tick()  # should create agent for 'a' only
    agents = supervisor._lifecycle.list_agents()
    agent_ids = [a.id for a in agents]
    # Only 'a' should have an agent since 'b' depends on 'a'
    agent_for_a = [a for a in agents if "a" in a.context.task_id]
    agent_for_b = [a for a in agents if "b" in a.context.task_id]
    assert len(agent_for_a) >= 1
    assert len(agent_for_b) == 0  # 'b' not ready yet


def test_tick_advances_after_dependency_completes(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    supervisor.create_mission(ctx, tasks)
    supervisor.start_mission("m1")
    supervisor.tick()  # creates agent for 'a'

    # Complete the agent for 'a'
    agents = supervisor._lifecycle.list_agents()
    for agent in agents:
        if "a" in agent.context.task_id:
            supervisor._lifecycle.complete_agent(agent.id)

    supervisor.tick()  # should now create agent for 'b'
    agents_after = supervisor._lifecycle.list_agents()
    agent_for_b = [a for a in agents_after if "b" in a.context.task_id]
    assert len(agent_for_b) >= 1


# ============================================================================
# Mission completion after graph completes
# ============================================================================


def test_mission_completes_when_graph_done(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    supervisor.tick()  # creates agent

    # Complete the agent
    agents = supervisor._lifecycle.list_agents()
    for agent in agents:
        supervisor._lifecycle.complete_agent(agent.id)

    changed = supervisor.tick()
    mission = supervisor.get_mission("m1")
    assert mission.state == MissionState.COMPLETED


# ============================================================================
# Runtime selector callback
# ============================================================================


def test_runtime_selector_callback() -> None:
    planner = TaskPlanner()
    lifecycle = AgentLifecycleManager()

    def selector(capability: str) -> Optional[str]:
        if capability == "chat":
            return "stub-runtime"
        return None

    sup = MultiAgentSupervisor(planner, lifecycle, runtime_selector_callback=selector)
    ctx = MissionContext(mission_id="m1")
    sup.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    sup.start_mission("m1")
    sup.tick()

    agents = lifecycle.list_agents()
    if agents:
        assert agents[0].context.assigned_runtime == "stub-runtime"


# ============================================================================
# Events
# ============================================================================


def test_event_handler_called(supervisor: MultiAgentSupervisor) -> None:
    events: list[tuple[SupervisorEvent, str]] = []
    supervisor.on_event(lambda evt, mid: events.append((evt, mid)))

    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])

    assert any(e == SupervisorEvent.MISSION_CREATED for e, _ in events)


# ============================================================================
# Query operations
# ============================================================================


def test_get_mission(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    mission = supervisor.get_mission("m1")
    assert mission.context.mission_id == "m1"


def test_get_mission_not_found_raises(supervisor: MultiAgentSupervisor) -> None:
    with pytest.raises(SupervisorError, match="not found"):
        supervisor.get_mission("nonexistent")


def test_list_missions(supervisor: MultiAgentSupervisor) -> None:
    ctx1 = MissionContext(mission_id="m1")
    ctx2 = MissionContext(mission_id="m2")
    supervisor.create_mission(ctx1, [PlannedTask(id="t1", title="T")])
    supervisor.create_mission(ctx2, [PlannedTask(id="t2", title="T")])
    assert len(supervisor.list_missions()) == 2


def test_list_missions_filter_by_state(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    ready = supervisor.list_missions(state=MissionState.READY)
    running = supervisor.list_missions(state=MissionState.RUNNING)
    assert len(ready) == 1
    assert len(running) == 0


# ============================================================================
# Statistics
# ============================================================================


def test_statistics(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")
    supervisor.tick()

    stats = supervisor.get_statistics()
    assert stats.missions_started >= 1
    assert stats.agents_created >= 1


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_mission_creation(supervisor: MultiAgentSupervisor) -> None:
    errors: list[Exception] = []

    def create_worker(n: int) -> None:
        for i in range(20):
            mid = f"conc_m{n}_t{i}"
            try:
                ctx = MissionContext(mission_id=mid, title=f"Mission{mid}")
                supervisor.create_mission(ctx, [PlannedTask(id=f"{mid}_t1", title="T")])
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=create_worker, args=(t,)) for t in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(supervisor.list_missions()) == 60


def test_concurrent_tick_and_cancel(supervisor: MultiAgentSupervisor) -> None:
    ctx = MissionContext(mission_id="m1")
    supervisor.create_mission(ctx, [PlannedTask(id="t1", title="T")])
    supervisor.start_mission("m1")

    errors: list[Exception] = []

    def tick_loop() -> None:
        for _ in range(50):
            try:
                supervisor.tick()
            except Exception as e:
                errors.append(e)

    def cancel_loop() -> None:
        for _ in range(50):
            try:
                supervisor.cancel_mission("m1")
            except (SupervisorError, Exception):
                pass

    t1 = threading.Thread(target=tick_loop)
    t2 = threading.Thread(target=cancel_loop)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
