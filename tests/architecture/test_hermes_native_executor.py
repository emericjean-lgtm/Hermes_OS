"""Tests for HermesNativeExecutor (R-006 Phase 3).

Hermetic: a fake OllamaClient (no real HTTP) paired with a real ModelRouter
built from a small in-memory config — the routing decision is genuine, only
the network call is faked.
"""
from __future__ import annotations

import pytest

from backend.agents.agent_models import TaskOutcome
from backend.agents.specialized.code_intelligence.hermes_native_executor import (
    HermesNativeExecutor,
)
from backend.core.router import ModelRouter

_CONFIG = {
    "roles": {
        "coder": {"model": "coder:7b", "tier": "standard", "vram_gb": 6.0},
        "swift": {"model": "swift:1b", "tier": "turbo", "vram_gb": 1.0},
    },
    "routing": {
        "code_analysis": ["coder"],
        "code_generation": ["coder"],
        "code_refactor": ["coder"],
    },
    "thinking": {"default": False, "by_task_type": {}},
}


class _FakeChatResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeOllamaClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.chat_calls: list[tuple[list[dict], str]] = []

    async def list_running_models(self) -> list[dict]:
        return [{"name": "coder:7b"}]

    async def chat(self, messages, *, model=None):
        self.chat_calls.append((messages, model))
        if self.fail:
            raise RuntimeError("Ollama connection refused")
        return _FakeChatResponse(f"real completion from {model}")


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(_CONFIG)


@pytest.fixture
def ollama() -> _FakeOllamaClient:
    return _FakeOllamaClient()


@pytest.fixture
def executor(ollama, router) -> HermesNativeExecutor:
    ex = HermesNativeExecutor(ollama_client=ollama, model_router=router)
    yield ex
    ex.close()


class TestExecution:
    def test_code_generation_reaches_ollama_with_the_routed_model(self, executor, ollama):
        result = executor.execute_task("code_generation", {"instruction": "write a fibonacci function"})
        assert result.outcome == TaskOutcome.SUCCESS
        assert result.details["data"]["model"] == "coder:7b"
        assert "real completion" in result.details["data"]["content"]
        assert ollama.chat_calls[0][1] == "coder:7b"

    def test_prompt_carries_the_real_code_and_instruction(self, executor, ollama):
        executor.execute_task(
            "code_analysis",
            {"code": "def f(): return 1", "instruction": "what does this do?", "language": "python"},
        )
        messages, _ = ollama.chat_calls[0]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "def f(): return 1" in user_msg
        assert "what does this do?" in user_msg

    def test_ineligible_task_type_fails_honestly_without_calling_ollama(self, executor, ollama):
        """debugging has no HERMES_NATIVE_TASK_TYPES mapping — must fail
        clearly, never silently substitute a different task type."""
        result = executor.execute_task("debugging", {})
        assert result.outcome == TaskOutcome.FAILURE
        assert "no Hermes-native routing mapping" in result.error_message
        assert ollama.chat_calls == []

    def test_ollama_failure_is_reported_not_hidden(self, router):
        failing_ollama = _FakeOllamaClient(fail=True)
        executor = HermesNativeExecutor(ollama_client=failing_ollama, model_router=router)
        try:
            result = executor.execute_task("code_generation", {})
            assert result.outcome == TaskOutcome.FAILURE
            assert "connection refused" in result.error_message
        finally:
            executor.close()

    def test_duration_is_measured_not_hardcoded(self, executor):
        result = executor.execute_task("code_generation", {})
        assert result.duration_ms >= 0
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at

    def test_list_running_models_failure_degrades_to_empty_not_a_crash(self, router):
        class _BrokenListOllama(_FakeOllamaClient):
            async def list_running_models(self):
                raise RuntimeError("Ollama unreachable")

        executor = HermesNativeExecutor(ollama_client=_BrokenListOllama(), model_router=router)
        try:
            result = executor.execute_task("code_generation", {})
            # Routing still succeeds via the "no VRAM constraint" default path.
            assert result.outcome == TaskOutcome.SUCCESS
        finally:
            executor.close()


class TestIdentity:
    def test_agent_id_is_stable_and_real(self, executor):
        assert executor.agent_id
        assert executor.execute_task("code_generation", {}, node_id="n1").agent_id == executor.agent_id

    def test_is_available(self, executor):
        assert executor.is_available is True
