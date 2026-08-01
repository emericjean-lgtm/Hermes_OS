"""Tests for BaseAgent's cloud fallback (HOS-066C) — local is always the
first attempt; cloud is retried only when the local stream fails *before*
yielding a single chunk, so a partially-delivered answer is never risked.
"""
from __future__ import annotations

import pytest

from backend.agents.base_agent import BaseAgent
from backend.connectors.ollama_client import StreamChunk
from backend.core.router import ModelRouter

CONFIG = {
    "roles": {"small": {"model": "small:1b", "tier": "turbo", "vram_gb": 1.0}},
    "routing": {"conversation": ["small"]},
    "thinking": {"default": False, "by_task_type": {}},
}

_GEN_DEFAULTS = {"generation_defaults": {"standard": {"temperature": 0.6, "top_p": 0.95}}}


class _Agent(BaseAgent):
    name = "test-agent"

    @property
    def default_task_type(self):
        return "conversation"


class _RaisingOllama:
    """Fails before yielding anything."""

    async def list_running_models(self):
        return []

    def chat_events(self, model, messages, **kwargs):
        async def gen():
            raise RuntimeError("Ollama unreachable")
            yield  # pragma: no cover - unreachable, satisfies generator syntax

        return gen()


class _PartialThenRaisingOllama:
    """Yields one real chunk, then the connection drops."""

    async def list_running_models(self):
        return []

    def chat_events(self, model, messages, **kwargs):
        async def gen():
            yield StreamChunk("content", "partial answer")
            raise RuntimeError("dropped mid-stream")

        return gen()


class _WorkingOllama:
    async def list_running_models(self):
        return []

    def chat_events(self, model, messages, **kwargs):
        async def gen():
            yield StreamChunk("content", "local completion")

        return gen()


class _FakeCloud:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def chat_events(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))

        async def gen():
            yield StreamChunk("content", "cloud completion")

        return gen()


class TestNoCloudFailurePath:
    async def test_local_success_never_touches_cloud(self):
        cloud = _FakeCloud()
        agent = _Agent(_WorkingOllama(), ModelRouter(CONFIG), _GEN_DEFAULTS, cloud)
        _, stream = await agent.respond_events([{"role": "user", "content": "hi"}])
        chunks = [c async for c in stream]
        assert [c.text for c in chunks] == ["local completion"]
        assert cloud.calls == []


class TestCloudFallback:
    async def test_falls_back_to_cloud_when_local_fails_before_yielding(self, monkeypatch):
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: "cloud/model:free")
        cloud = _FakeCloud()
        agent = _Agent(_RaisingOllama(), ModelRouter(CONFIG), _GEN_DEFAULTS, cloud)
        _, stream = await agent.respond_events([{"role": "user", "content": "hi"}])
        chunks = [c async for c in stream]
        assert [c.text for c in chunks] == ["cloud completion"]
        assert cloud.calls[0][0] == "cloud/model:free"

    async def test_never_retries_after_partial_local_content(self, monkeypatch):
        """The core safety guarantee: once any content reached the caller,
        switching runtimes must not happen — it would risk a duplicated or
        incoherent answer."""
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: "cloud/model:free")
        cloud = _FakeCloud()
        agent = _Agent(_PartialThenRaisingOllama(), ModelRouter(CONFIG), _GEN_DEFAULTS, cloud)
        _, stream = await agent.respond_events([{"role": "user", "content": "hi"}])
        with pytest.raises(RuntimeError, match="dropped mid-stream"):
            async for _ in stream:
                pass
        assert cloud.calls == []

    async def test_no_cloud_client_propagates_original_local_error(self):
        agent = _Agent(_RaisingOllama(), ModelRouter(CONFIG), _GEN_DEFAULTS, None)
        _, stream = await agent.respond_events([{"role": "user", "content": "hi"}])
        with pytest.raises(RuntimeError, match="Ollama unreachable"):
            async for _ in stream:
                pass

    async def test_no_cloud_model_available_raises_chained_from_local_error(self, monkeypatch):
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: None)
        cloud = _FakeCloud()
        agent = _Agent(_RaisingOllama(), ModelRouter(CONFIG), _GEN_DEFAULTS, cloud)
        _, stream = await agent.respond_events([{"role": "user", "content": "hi"}])
        with pytest.raises(RuntimeError) as excinfo:
            async for _ in stream:
                pass
        assert "no cloud fallback" in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, RuntimeError)
        assert "Ollama unreachable" in str(excinfo.value.__cause__)
        assert cloud.calls == []
