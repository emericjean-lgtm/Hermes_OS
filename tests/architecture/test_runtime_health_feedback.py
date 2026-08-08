"""Tests for HOS-072 — RealTaskExecutor.on_runtime_result.

Before this, GET /api/v1/runtimes' metrics/health fields were always
absent: nothing outside backend/sds/'s own routes ever called
RuntimeHealthMonitor.record_execution(), regardless of how many real
tasks a runtime served. RealTaskExecutor now reports the runtime it
actually used (or attempted) after every real attempt, success or
failure, through a dedicated callback — separate from on_execution
(which feeds Model Intelligence) since the two track different things.

Fully hermetic: fake chat/cloud_chat callables, no real Ollama needed.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError


class _FakeTask:
    task_id = "t1"
    title = "do the thing"
    retries = 0


def _results(monitor: list[tuple[str, float, bool]]):
    def _on_runtime_result(runtime_id: str, duration_ms: float, success: bool) -> None:
        monitor.append((runtime_id, duration_ms, success))
    return _on_runtime_result


class TestOnRuntimeResultSuccess:
    def test_success_reports_the_runtime_that_actually_served_it(self):
        calls: list[tuple[str, float, bool]] = []

        async def chat(*, messages, model, num_ctx=None):
            return {"content": "ok", "metadata": {"provider": "ollama", "model": model}}

        executor = RealTaskExecutor(chat=chat, on_runtime_result=_results(calls))
        executor.execute(_FakeTask())

        assert len(calls) == 1
        runtime_id, duration_ms, success = calls[0]
        assert runtime_id == "ollama"
        assert success is True
        assert duration_ms >= 0


class TestOnRuntimeResultFailure:
    def test_runtime_unavailable_reports_failure(self):
        calls: list[tuple[str, float, bool]] = []

        async def chat(*, messages, model, num_ctx=None):
            raise RuntimeUnavailableError("ollama is down")

        executor = RealTaskExecutor(chat=chat, on_runtime_result=_results(calls))
        with pytest.raises(RuntimeUnavailableError):
            executor.execute(_FakeTask())

        assert len(calls) == 1
        runtime_id, _, success = calls[0]
        assert runtime_id == "ollama"
        assert success is False

    def test_empty_completion_reports_failure(self):
        calls: list[tuple[str, float, bool]] = []

        async def chat(*, messages, model, num_ctx=None):
            return {"content": "", "metadata": {}}

        executor = RealTaskExecutor(chat=chat, on_runtime_result=_results(calls))
        with pytest.raises(RuntimeUnavailableError):
            executor.execute(_FakeTask())

        assert len(calls) == 1
        assert calls[0][2] is False

    def test_cloud_then_local_fallback_both_fail_reports_ollama_failure(self):
        calls: list[tuple[str, float, bool]] = []

        async def cloud_chat(*, messages, model, num_ctx=None):
            raise RuntimeError("cloud unreachable")

        async def chat(*, messages, model, num_ctx=None):
            raise RuntimeUnavailableError("local also down")

        executor = RealTaskExecutor(
            chat=chat, cloud_chat=cloud_chat,
            runtime_for=lambda task: "openrouter",
            local_fallback_for=lambda task: "qwen3:4b",
            on_runtime_result=_results(calls),
        )
        with pytest.raises(RuntimeUnavailableError):
            executor.execute(_FakeTask())

        assert len(calls) == 1
        runtime_id, _, success = calls[0]
        assert runtime_id == "ollama"  # the local fallback that was actually attempted
        assert success is False


class TestOnRuntimeResultOptional:
    def test_no_callback_wired_does_not_break_execution(self):
        async def chat(*, messages, model, num_ctx=None):
            return {"content": "ok", "metadata": {}}

        executor = RealTaskExecutor(chat=chat)  # on_runtime_result not passed
        outcome = executor.execute(_FakeTask())
        assert outcome.result == "ok"

    def test_callback_exception_never_breaks_execution(self):
        async def chat(*, messages, model, num_ctx=None):
            return {"content": "ok", "metadata": {}}

        def _broken(runtime_id, duration_ms, success):
            raise ValueError("boom")

        executor = RealTaskExecutor(chat=chat, on_runtime_result=_broken)
        outcome = executor.execute(_FakeTask())
        assert outcome.result == "ok"
