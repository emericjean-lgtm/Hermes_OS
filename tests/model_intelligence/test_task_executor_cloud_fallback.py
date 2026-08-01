"""Tests for RealTaskExecutor's cloud-to-local fallback (HOS-066C).

Fully hermetic: chat/cloud_chat are injected fakes (constructor params
RealTaskExecutor already supports), no real Ollama or OpenRouter needed.
Real-runtime coverage lives in tests/integration/test_real_execution.py.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError


class _Task:
    def __init__(self, title: str = "write a function") -> None:
        self.task_id = "t1"
        self.node_id = "n1"
        self.title = title
        self.assigned_agent = "coder"
        self.assigned_runtime = "ollama"
        self.assigned_skills: list[str] = []
        self.assigned_tools: list[str] = []


class _FakeResponse:
    def __init__(self, content: str, provider: str, **extra_meta) -> None:
        self.content = content
        self.metadata = {"provider": provider, **extra_meta}


async def _local_chat(*, messages, model, num_ctx=None):
    return _FakeResponse("local completion", "ollama", model=model)


def _executor(**kwargs) -> RealTaskExecutor:
    return RealTaskExecutor(chat=_local_chat, **kwargs)


class TestNoCloudWired:
    def test_behaves_exactly_as_before_this_feature(self):
        """cloud_chat=None (the default) — every task runs local, regardless
        of what runtime_for says."""
        executor = _executor(runtime_for=lambda t: "openrouter")
        outcome = executor.execute(_Task())
        assert outcome.runtime_id == "ollama"
        assert outcome.result == "local completion"


class TestCloudSucceeds:
    def test_uses_cloud_when_runtime_for_says_openrouter(self):
        calls = []

        async def cloud_chat(*, messages, model, num_ctx=None):
            calls.append(model)
            return _FakeResponse("cloud completion", "openrouter", model=model,
                                 prompt_tokens=10, completion_tokens=3)

        executor = _executor(
            cloud_chat=cloud_chat,
            runtime_for=lambda t: "openrouter",
            model_for=lambda t: "deepseek/deepseek-chat-v3.1:free",
        )
        outcome = executor.execute(_Task())
        assert outcome.runtime_id == "openrouter"
        assert outcome.result == "cloud completion"
        assert outcome.prompt_tokens == 10
        assert outcome.completion_tokens == 3
        assert calls == ["deepseek/deepseek-chat-v3.1:free"]

    def test_local_chat_never_called_when_cloud_succeeds(self):
        calls = {"local": 0}

        async def counting_local_chat(*, messages, model, num_ctx=None):
            calls["local"] += 1
            return _FakeResponse("local completion", "ollama")

        async def cloud_chat(*, messages, model, num_ctx=None):
            return _FakeResponse("cloud completion", "openrouter")

        executor = RealTaskExecutor(
            chat=counting_local_chat, cloud_chat=cloud_chat,
            runtime_for=lambda t: "openrouter",
        )
        executor.execute(_Task())
        assert calls["local"] == 0

    def test_runtime_for_returning_ollama_never_touches_cloud_chat(self):
        calls = {"cloud": 0}

        async def counting_cloud_chat(*, messages, model, num_ctx=None):
            calls["cloud"] += 1
            return _FakeResponse("cloud completion", "openrouter")

        executor = _executor(cloud_chat=counting_cloud_chat, runtime_for=lambda t: "ollama")
        outcome = executor.execute(_Task())
        assert calls["cloud"] == 0
        assert outcome.runtime_id == "ollama"


class TestCloudFailsAutomaticLocalFallback:
    def test_falls_back_to_local_model_on_cloud_failure(self):
        async def failing_cloud_chat(*, messages, model, num_ctx=None):
            raise RuntimeError("OpenRouter rate limit exceeded (HTTP 429)")

        executor = _executor(
            cloud_chat=failing_cloud_chat,
            runtime_for=lambda t: "openrouter",
            local_fallback_for=lambda t: "qwen3:4b",
        )
        outcome = executor.execute(_Task())
        assert outcome.runtime_id == "ollama"
        assert outcome.result == "local completion"
        assert outcome.model == "qwen3:4b"
        # The original intent is preserved even though local actually served it —
        # never silently rewritten to look as if cloud had never been tried.
        assert outcome.metadata["runtime_requested"] == "openrouter"

    def test_falls_back_to_default_model_when_no_local_fallback_resolves(self):
        async def failing_cloud_chat(*, messages, model, num_ctx=None):
            raise RuntimeError("network error")

        executor = _executor(
            cloud_chat=failing_cloud_chat,
            runtime_for=lambda t: "openrouter",
            default_model="qwen3:1.7b",
        )
        outcome = executor.execute(_Task())
        assert outcome.runtime_id == "ollama"
        assert outcome.model == "qwen3:1.7b"

    def test_raises_when_both_cloud_and_local_fallback_fail(self):
        async def failing_cloud_chat(*, messages, model, num_ctx=None):
            raise RuntimeError("quota exhausted")

        async def failing_local_chat(*, messages, model, num_ctx=None):
            raise RuntimeError("Ollama unreachable")

        executor = RealTaskExecutor(
            chat=failing_local_chat, cloud_chat=failing_cloud_chat,
            runtime_for=lambda t: "openrouter",
        )
        with pytest.raises(RuntimeUnavailableError) as excinfo:
            executor.execute(_Task())
        assert "quota exhausted" in str(excinfo.value)
        assert "Ollama unreachable" in str(excinfo.value)

    def test_a_quiet_task_never_fails_solely_because_cloud_was_down(self):
        """The point of the feature: a cloud hiccup must not turn into a
        failed task when a real local alternative exists."""
        async def failing_cloud_chat(*, messages, model, num_ctx=None):
            raise TimeoutError("cloud request timed out")

        executor = _executor(
            cloud_chat=failing_cloud_chat,
            runtime_for=lambda t: "openrouter",
            local_fallback_for=lambda t: "qwen3:4b",
        )
        outcome = executor.execute(_Task())  # must not raise
        assert outcome.result
