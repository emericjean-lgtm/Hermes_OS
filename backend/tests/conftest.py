from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient


class FakeOllamaClient:
    """Duck-types OllamaClientProtocol without any network I/O."""

    def __init__(
        self,
        running_models: list[str] | None = None,
        response_chunks: list[str] | None = None,
    ) -> None:
        self._running = running_models or []
        self._chunks = response_chunks or ["Hello", ", ", "world", "!"]
        self.last_chat_call: dict[str, Any] | None = None

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        self.last_chat_call = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        for chunk in self._chunks:
            yield chunk

    async def list_running_models(self) -> list[dict[str, Any]]:
        return [{"name": name} for name in self._running]

    async def list_local_models(self) -> list[dict[str, Any]]:
        return [{"name": name} for name in self._running]


@pytest.fixture
def fake_ollama_client() -> FakeOllamaClient:
    return FakeOllamaClient()


@pytest.fixture
def models_config() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    with (repo_root / "config" / "models.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def security_config() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    with (repo_root / "config" / "security.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def client(monkeypatch, fake_ollama_client, models_config) -> TestClient:
    """TestClient wired to a real AgentRegistry (loading real config/*.yaml)
    but with the fake Ollama client injected, so agents that do call
    Ollama (chat agents) never hit the network, while agents that build
    their own state from real config (e.g. AegisAgent from security.yaml)
    behave exactly as they would in production."""
    import backend.main as main_module
    from backend.core.agent_registry import AgentRegistry
    from backend.core.router import ModelRouter

    router = ModelRouter(models_config)
    registry = AgentRegistry(fake_ollama_client, router, models_config)
    monkeypatch.setattr("backend.api.routes.chat.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.system.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.security.get_agent_registry", lambda: registry)
    return TestClient(main_module.app)
