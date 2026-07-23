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
def client(monkeypatch, fake_ollama_client, models_config, tmp_path) -> TestClient:
    """TestClient wired to a real AgentRegistry (loading real config/*.yaml)
    but with the fake Ollama client injected, so agents that do call
    Ollama (chat agents) never hit the network, while agents that build
    their own state from real config (e.g. AegisAgent from security.yaml)
    behave exactly as they would in production.

    SQLITE_PATH/CHROMA_PATH are pointed at tmp_path and get_settings()'s
    cache is cleared around the test: EchoAgent persists to real files on
    construction (see agents/echo.py), and without this override every
    test run would read/write the developer's actual data/db/ folder."""
    import backend.main as main_module
    from backend.core.agent_registry import AgentRegistry
    from backend.core.config import get_settings
    from backend.core.router import ModelRouter

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    get_settings.cache_clear()

    router = ModelRouter(models_config)
    registry = AgentRegistry(fake_ollama_client, router, models_config)
    monkeypatch.setattr("backend.api.routes.chat.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.system.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.security.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.files.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.memory.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.tasks.get_agent_registry", lambda: registry)

    try:
        yield TestClient(main_module.app)
    finally:
        get_settings.cache_clear()


@pytest.fixture
def echo_agent(monkeypatch, fake_ollama_client, models_config, tmp_path):
    """A real EchoAgent (real SQLite, real ChromaDB) isolated to tmp_path,
    for tests that want to call it directly rather than through HTTP.
    Only exercise the SQLite-backed methods (remember/list_memories/
    forget) against this fixture — index_document/recall go through
    EchoAgent's real OllamaEmbeddingFunction, which needs a live Ollama
    server this sandbox doesn't have (see test_semantic.py for
    ChromaDB-side coverage with a fake embedding function instead)."""
    from backend.agents.echo import EchoAgent
    from backend.core.config import get_settings
    from backend.core.router import ModelRouter

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    get_settings.cache_clear()

    router = ModelRouter(models_config)
    agent = EchoAgent(fake_ollama_client, router, models_config)

    try:
        yield agent
    finally:
        get_settings.cache_clear()


@pytest.fixture
def kronos_agent(monkeypatch, fake_ollama_client, models_config, tmp_path):
    """A real KronosAgent (real SQLite, same isolation pattern as
    echo_agent) for tests that call it directly rather than through
    HTTP. No live Ollama needed: task_manager is fully deterministic."""
    from backend.agents.kronos import KronosAgent
    from backend.core.config import get_settings
    from backend.core.router import ModelRouter

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    router = ModelRouter(models_config)
    agent = KronosAgent(fake_ollama_client, router, models_config)

    try:
        yield agent
    finally:
        get_settings.cache_clear()
