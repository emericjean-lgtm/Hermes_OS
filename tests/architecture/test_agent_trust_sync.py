"""Tests for HOS-070 Phase C — real per-agent trust scoring.

AgentTrustEngine.record_result() existed (backend/security/agent_trust_engine.py,
HOS-057) and was never called by anything — every agent's trust score stayed
at its default (a brand-new AgentTrustScore) no matter how many real tasks it
completed or failed. MissionExecutor now feeds it a real outcome per task,
alongside AgentRegistry (HOS-070 Phase A).

Deliberately does NOT wire the full SecurityEngine.check_access() gate into
dispatch — see MissionExecutor's own docstring and the CHANGELOG for why
(no default permissions/policies exist anywhere for that engine, so it
would default-deny every real mission today).

Fully hermetic: fake task_executor, real AgentTrustEngine, no Ollama needed.
"""
from __future__ import annotations

from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RuntimeUnavailableError, TaskExecutionOutcome
from backend.security.agent_trust_engine import AgentTrustEngine
from backend.security.security_models import TrustLevel


class _FakeTaskExecutor:
    def __init__(self, *, fail: bool = False):
        self._fail = fail

    def execute(self, task, assignment):
        if self._fail:
            raise RuntimeUnavailableError("simulated failure")
        return TaskExecutionOutcome(result="ok", runtime_id="fake", model="m", duration_ms=10.0)


def _run_one_task(me: MissionExecutor, agent_name: str, max_retries: int = 3):
    me._coordinator.register_agent(agent_id=agent_name, capabilities=["chat"])
    meta = ExecutionMeta(mission_id="m1", user_goal="do a thing", max_retries_per_task=max_retries)
    task = TaskExecution(task_id="t1", node_id="n1", title="do a thing")
    sm = me.prepare(meta, [task])
    result = me.execute_task(sm, "t1")
    while task.status.value == "pending":
        result = me.execute_task(sm, "t1")
    return result, task


class TestTrustEngineSync:
    def test_successful_task_records_a_win(self):
        trust = AgentTrustEngine()
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), trust_engine=trust)

        _run_one_task(me, "atlas")

        score = trust.get_score("atlas")
        assert score.total_tasks == 1
        assert score.success_count == 1
        assert score.failure_count == 0

    def test_permanent_failure_records_a_loss(self):
        trust = AgentTrustEngine()
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=True), trust_engine=trust)

        _run_one_task(me, "atlas", max_retries=0)

        score = trust.get_score("atlas")
        assert score.total_tasks == 1
        assert score.success_count == 0
        assert score.failure_count == 1

    def test_a_fresh_agent_starts_at_unknown_and_moves_after_real_results(self):
        # get_score() returns a live reference into the engine's own dict,
        # not a snapshot — capture scalars, not the object, before running.
        trust = AgentTrustEngine()
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), trust_engine=trust)

        before_level = trust.get_score("atlas").level
        before_total = trust.get_score("atlas").total_tasks
        assert before_level == TrustLevel.UNKNOWN
        assert before_total == 0

        _run_one_task(me, "atlas")
        # A real result must have genuinely moved the engine's own state,
        # proving this ran through it and not a stub.
        after = trust.get_score("atlas")
        assert after.total_tasks == 1
        assert after.success_count == 1

    def test_no_trust_engine_is_a_no_op(self):
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False), trust_engine=None)
        result, _ = _run_one_task(me, "atlas")
        assert result["status"] == "completed"  # unaffected by the missing engine

    def test_retry_before_success_still_counts_as_one_win_not_a_loss(self):
        """Mirrors the AgentRegistry equivalent (HOS-070 Phase A): a
        transient failure followed by a real success is one logical task,
        counted once, as a success."""
        trust = AgentTrustEngine()

        class _FailsOnceThenSucceeds:
            def __init__(self):
                self.calls = 0

            def execute(self, task, assignment):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeUnavailableError("transient")
                return TaskExecutionOutcome(result="ok", runtime_id="fake", model="m", duration_ms=5.0)

        me = MissionExecutor(task_executor=_FailsOnceThenSucceeds(), trust_engine=trust)
        _run_one_task(me, "atlas", max_retries=3)

        score = trust.get_score("atlas")
        assert score.total_tasks == 1
        assert score.success_count == 1
        assert score.failure_count == 0
