from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    test run would read/write the developer's actual data/db/ folder.

    get_agent_registry's own cache is cleared too: unlike the other
    agents, MinervaAgent calls get_agent_registry() directly (to reach
    Echo for retrieval — see agents/minerva.py), the same pattern the MCP
    server uses, rather than going through a per-route override. Without
    clearing it, that call could resolve to a stale registry built by an
    earlier test against different (or real) settings."""
    import backend.main as main_module
    from backend.core.agent_registry import AgentRegistry, get_agent_registry
    from backend.core.config import get_settings
    from backend.core.router import ModelRouter

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    get_settings.cache_clear()
    get_agent_registry.cache_clear()

    router = ModelRouter(models_config)
    registry = AgentRegistry(fake_ollama_client, router, models_config)
    monkeypatch.setattr("backend.api.routes.chat.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.system.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.security.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.files.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.memory.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.tasks.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.research.get_agent_registry", lambda: registry)

    try:
        yield TestClient(main_module.app)
    finally:
        get_settings.cache_clear()
        get_agent_registry.cache_clear()


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


@asynccontextmanager
async def open_mcp_session(monkeypatch, tmp_path):
    """A live MCP ClientSession talking to a freshly built app's mounted
    /mcp server over an in-process ASGI transport (no real socket).

    This is a plain async context manager, not a pytest fixture, on
    purpose: it wraps an anyio TaskGroup (inside FastMCP's session
    manager), and anyio cancel scopes must exit in the same asyncio Task
    they were entered in. A `yield`-ing async fixture's teardown runs via
    a *separate* run_until_complete() call than its setup — a different
    Task — which trips "Attempted to exit cancel scope in a different
    task than it was entered in". Called directly inside a test's own
    coroutine, setup and teardown share one Task, so this is safe.

    Uses backend.main.create_app() rather than the shared module-level
    `app` singleton: FastMCP's streamable-HTTP session manager can only
    run() once per instance (see create_mcp_server()'s docstring), so
    each test needs its own fresh app/MCP-server pair, not the one
    process-wide instance uvicorn would serve.

    Unlike the `client` fixture, MCP tools (backend/mcp_server/server.py)
    call get_agent_registry() directly rather than going through a
    per-route override, so isolation here clears *that* cache too (not
    just get_settings) and points SQLITE_PATH/CHROMA_PATH/ALLOWED_PATHS
    at tmp_path — otherwise this would build agents against the real
    OllamaClient and the developer's actual data/db/ folder."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    import backend.main as main_module
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    get_settings.cache_clear()
    get_agent_registry.cache_clear()

    app = main_module.create_app()

    def httpx_client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://mcp-test",
            headers=headers,
            timeout=timeout or httpx.Timeout(30),
            auth=auth,
            # Starlette's Mount 307-redirects "/mcp" -> "/mcp/"; the SDK's
            # own default httpx client factory sets this too (mcp.shared.
            # _httpx_utils.create_mcp_http_client), unlike httpx's default.
            follow_redirects=True,
        )

    try:
        async with app.router.lifespan_context(app):
            async with streamablehttp_client(
                "http://mcp-test/mcp", httpx_client_factory=httpx_client_factory
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    finally:
        get_settings.cache_clear()
        get_agent_registry.cache_clear()


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
