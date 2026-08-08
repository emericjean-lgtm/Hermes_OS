"""Tests for HOS-070 Phase A — real agent activity reflected in AgentRegistry.

Before this, AgentRegistry.update_status()/update_metrics() were only ever
called from TaskDispatcher.dispatch() (backend/agents/task_dispatcher.py),
itself only reachable from AgentSupervisor.dispatch_node()/
execute_mission_step()/execute_full_mission() — and nothing in the whole
codebase calls any of those three outside agent_supervisor.py itself. The
real execution path (MissionExecutor, backend/execution/) never touched the
real AgentRegistry at all, so every agent showed its initial "READY, 0
tasks" state forever regardless of real mission activity.

Fully hermetic: a fake task_executor stands in for RealTaskExecutor, no real
Ollama needed. Uses the real AgentRegistry/AgentModels classes (not fakes)
since the whole point is verifying the real sync logic against them.
"""
from __future__ import annotations

from backend.agents.agent_models import Agent, AgentCapability, AgentStatus
from backend.agents.agent_registry import AgentRegistry
from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RuntimeUnavailableError, TaskExecutionOutcome


class _FakeTaskExecutor:
    def __init__(self, *, fail: bool = False):
        self._fail = fail

    def execute(self, task, assignment):
        if self._fail:
            raise RuntimeUnavailableError("simulated failure")
        return TaskExecutionOutcome(
            result="ok", runtime_id="fake", model="fake-model", duration_ms=42.0,
        )


def _registry_with_agent(name: str = "atlas") -> tuple[AgentRegistry, Agent]:
    registry = AgentRegistry()
    agent = Agent(name=name, capabilities=[AgentCapability.CODE_GENERATION])
    registry.register(agent)
    return registry, agent


def _run_one_task(me: MissionExecutor, agent_name: str, max_retries: int = 3):
    """Drive one task to a terminal outcome, mirroring node_execution.py's
    own retry loop. AgentCoordinator picks whichever agent scores best from
    its own internal (separate) registry — for these tests that registry is
    empty, so it falls back to "default"; we monkeypatch the assignment
    result instead by registering the same name into the coordinator."""
    me._coordinator.register_agent(agent_id=agent_name, capabilities=["code_generation"])
    meta = ExecutionMeta(mission_id="m1", user_goal="do a thing", max_retries_per_task=max_retries)
    task = TaskExecution(task_id="t1", node_id="n1", title="do a thing")
    sm = me.prepare(meta, [task])
    result = me.execute_task(sm, "t1")
    while task.status.value == "pending":
        result = me.execute_task(sm, "t1")
    return result, task


class TestAgentRegistrySyncSuccess:
    def test_successful_task_updates_metrics_and_frees_agent(self):
        registry, agent = _registry_with_agent("atlas")
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), agent_registry=registry)

        result, task = _run_one_task(me, "atlas")

        assert result["status"] == "completed"
        refreshed = registry.get(agent.agent_id)
        assert refreshed.status == AgentStatus.READY
        assert refreshed.total_tasks == 1
        assert refreshed.successful_tasks == 1
        assert refreshed.failed_tasks == 0
        assert refreshed.total_duration_ms == 42.0
        assert refreshed.current_task_id == ""
        assert refreshed.current_mission_id == ""

    def test_agent_is_marked_busy_during_execution(self):
        """The registry reflects BUSY the moment assignment happens, before
        the (synchronous, in this test) execution call returns — verified
        via a task_executor that inspects the registry mid-call."""
        registry, agent = _registry_with_agent("atlas")
        seen = {}

        class _InspectingExecutor:
            def execute(self, task, assignment):
                mid_flight = registry.get(agent.agent_id)
                seen["status"] = mid_flight.status
                seen["task_id"] = mid_flight.current_task_id
                seen["mission_id"] = mid_flight.current_mission_id
                return TaskExecutionOutcome(
                    result="ok", runtime_id="fake", model="m", duration_ms=1.0)

        me = MissionExecutor(task_executor=_InspectingExecutor(), agent_registry=registry)
        _run_one_task(me, "atlas")

        assert seen["status"] == AgentStatus.BUSY
        assert seen["task_id"] == "t1"
        assert seen["mission_id"] == "m1"


class TestAgentRegistrySyncFailure:
    def test_permanent_failure_updates_metrics_as_failed(self):
        registry, agent = _registry_with_agent("atlas")
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=True), agent_registry=registry)

        result, task = _run_one_task(me, "atlas", max_retries=0)

        assert result["status"] == "failed"
        refreshed = registry.get(agent.agent_id)
        assert refreshed.status == AgentStatus.READY
        assert refreshed.total_tasks == 1
        assert refreshed.successful_tasks == 0
        assert refreshed.failed_tasks == 1

    def test_retry_in_flight_does_not_double_count_before_final_outcome(self):
        """A task that fails, retries, then succeeds must count as exactly
        one success — not a failure followed by a success — since the
        retries are transparent re-attempts at the same logical task, not
        distinct dispatches from the Cockpit's point of view."""
        registry, agent = _registry_with_agent("atlas")

        class _FailsOnceThenSucceeds:
            def __init__(self):
                self.calls = 0

            def execute(self, task, assignment):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeUnavailableError("transient")
                return TaskExecutionOutcome(
                    result="ok", runtime_id="fake", model="m", duration_ms=5.0)

        me = MissionExecutor(task_executor=_FailsOnceThenSucceeds(), agent_registry=registry)
        result, task = _run_one_task(me, "atlas", max_retries=3)

        assert result["status"] == "completed"
        refreshed = registry.get(agent.agent_id)
        assert refreshed.total_tasks == 1
        assert refreshed.successful_tasks == 1
        assert refreshed.failed_tasks == 0


class TestAgentRegistrySyncIsOptionalAndSafe:
    def test_no_registry_is_a_no_op(self):
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), agent_registry=None)
        result, _ = _run_one_task(me, "atlas")
        assert result["status"] == "completed"  # unaffected by the missing registry

    def test_unknown_agent_name_is_a_no_op_not_an_error(self):
        registry, _agent = _registry_with_agent("someone-else")
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), agent_registry=registry)
        result, _ = _run_one_task(me, "atlas")  # "atlas" was never registered here
        assert result["status"] == "completed"  # no crash, no fabricated match
