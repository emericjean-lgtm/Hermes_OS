"""Tests for HOS-069 Phase C — intelligent bounded retry:

* RuntimeUnavailableError now retries (bounded), instead of failing a task
  on the very first Ollama timeout / VRAM denial / connection error with no
  second chance at all.
* The retry ceiling actually reads ExecutionMeta.max_retries_per_task
  instead of a hardcoded 3 (in two separate places).
* On a retry attempt, RealTaskExecutor prefers a real alternative model
  (local_fallback_for) over blindly re-resolving the same primary model.

Fully hermetic: fake task_executor/callables, no real Ollama needed.
"""
from __future__ import annotations

import pytest

from backend.execution.execution_models import ExecutionMeta, TaskExecution, TaskExecutionStatus
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError, TaskExecutionOutcome


class _AlwaysUnavailable:
    def __init__(self):
        self.calls = 0

    def execute(self, task, assignment):
        self.calls += 1
        raise RuntimeUnavailableError("ollama timed out")


class TestRuntimeUnavailableRetries:
    def test_retries_up_to_configured_ceiling_then_fails(self):
        fake = _AlwaysUnavailable()
        me = MissionExecutor(task_executor=fake)
        meta = ExecutionMeta(user_goal="flaky", max_retries_per_task=2)
        task = TaskExecution(task_id="t1", node_id="n1", title="t1")
        sm = me.prepare(meta, [task])

        # Drive it exactly like node_execution.py's retry loop does.
        result = me.execute_task(sm, "t1")
        attempts = 1
        while task.status == TaskExecutionStatus.PENDING:
            result = me.execute_task(sm, "t1")
            attempts += 1

        assert result["status"] == "failed"
        assert fake.calls == attempts == 3  # 1 initial + 2 retries
        assert task.retries == 2

    def test_respects_a_different_configured_ceiling(self):
        fake = _AlwaysUnavailable()
        me = MissionExecutor(task_executor=fake)
        meta = ExecutionMeta(user_goal="flaky", max_retries_per_task=0)
        task = TaskExecution(task_id="t1", node_id="n1", title="t1")
        sm = me.prepare(meta, [task])

        result = me.execute_task(sm, "t1")

        assert result["status"] == "failed"
        assert fake.calls == 1  # no retries at all when the ceiling is 0

    def test_recovers_if_the_runtime_comes_back(self):
        """Matches the user's own description: timeout, retry, then a real
        success — not an immediate, permanent failure."""
        class _RecoversOnSecondAttempt:
            def __init__(self):
                self.calls = 0

            def execute(self, task, assignment):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeUnavailableError("ollama timed out")
                return TaskExecutionOutcome(
                    result="ok", runtime_id="ollama", model="qwen3:4b", duration_ms=5.0,
                )

        fake = _RecoversOnSecondAttempt()
        me = MissionExecutor(task_executor=fake)
        meta = ExecutionMeta(user_goal="recovers", max_retries_per_task=3)
        task = TaskExecution(task_id="t1", node_id="n1", title="t1")
        sm = me.prepare(meta, [task])

        result = me.execute_task(sm, "t1")
        while task.status == TaskExecutionStatus.PENDING:
            result = me.execute_task(sm, "t1")

        assert result["status"] == "completed"
        assert fake.calls == 2


class TestRetryPrefersAlternativeModel:
    def test_first_attempt_uses_primary_model(self):
        seen = {}

        async def _chat(**kwargs):
            seen["model"] = kwargs["model"]
            raise RuntimeUnavailableError("boom")

        ex = RealTaskExecutor(
            chat=_chat,
            model_for=lambda t: "primary-model",
            local_fallback_for=lambda t: "fallback-model",
        )
        task = TaskExecution(task_id="t1", node_id="n1", title="t1", retries=0)
        with pytest.raises(RuntimeUnavailableError):
            ex.execute(task)
        assert seen["model"] == "primary-model"

    def test_retry_attempt_prefers_fallback_model(self):
        seen = {}

        async def _chat(**kwargs):
            seen["model"] = kwargs["model"]
            raise RuntimeUnavailableError("boom")

        ex = RealTaskExecutor(
            chat=_chat,
            model_for=lambda t: "primary-model",
            local_fallback_for=lambda t: "fallback-model",
        )
        task = TaskExecution(task_id="t1", node_id="n1", title="t1", retries=1)
        with pytest.raises(RuntimeUnavailableError):
            ex.execute(task)
        assert seen["model"] == "fallback-model"

    def test_retry_falls_back_to_primary_when_no_alternative_available(self):
        seen = {}

        async def _chat(**kwargs):
            seen["model"] = kwargs["model"]
            raise RuntimeUnavailableError("boom")

        ex = RealTaskExecutor(
            chat=_chat,
            model_for=lambda t: "primary-model",
            local_fallback_for=lambda t: None,  # no real alternative exists
        )
        task = TaskExecution(task_id="t1", node_id="n1", title="t1", retries=1)
        with pytest.raises(RuntimeUnavailableError):
            ex.execute(task)
        assert seen["model"] == "primary-model"
