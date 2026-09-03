from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.connectors.ollama_client import StreamChunk
from fastapi.testclient import TestClient


class FakeOllamaClient:
    """Duck-types OllamaClientProtocol without any network I/O."""

    def __init__(
        self,
        running_models: list[str] | None = None,
        response_chunks: list[str] | None = None,
        thinking_chunks: list[str] | None = None,
    ) -> None:
        self._running = running_models or []
        self._chunks = response_chunks or ["Hello", ", ", "world", "!"]
        self._thinking = thinking_chunks or []
        self.last_chat_call: dict[str, Any] | None = None

    async def chat_events(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.last_chat_call = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "think": think,
        }
        for chunk in self._thinking:
            yield StreamChunk("thinking", chunk)
        for chunk in self._chunks:
            yield StreamChunk("content", chunk)

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Derived from chat_events, exactly as the real client is.

        Reimplementing it independently would let the fake keep passing
        after the real filter broke — a fake whose shape diverges from
        the real one quietly stops proving anything.
        """
        async for chunk in self.chat_events(model, messages, **kwargs):
            if chunk.kind == "content":
                yield chunk.text

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
    earlier test against different (or real) settings.

    get_message_bus's cache is cleared for the same reason: AegisAgent
    reaches the bus via that module-level singleton too (see
    agents/aegis.py), so a stale cached bus would keep writing to a
    previous test's (possibly already-deleted) tmp_path.

    WORKFLOWS_DIR is pointed at tmp_path too: backend/workflows/loader.py
    reads it fresh from get_settings() on every call (no lru_cache of its
    own), so without this a workflow test would read/write the real
    data/workflows/ folder.

    get_project_store's cache is cleared for the same reason as
    get_message_bus: /projects reaches it via that module-level singleton
    (see backend/projects/store.py) rather than a per-route override.

    get_gpu_monitor's cache is cleared too, and /system/status's own
    reference is overridden with a GpuMonitor built directly from
    fake_ollama_client — otherwise it would resolve the real singleton,
    which opens a real OllamaClient against get_agent_registry() (not the
    fake registry built below) and would try a real network call in
    list_running_models(). run_command is faked to always report "no
    GPU" (None), matching this sandbox's actual hardware."""
    import backend.main as main_module
    from backend.core.agent_registry import AgentRegistry, get_agent_registry
    from backend.core.config import get_settings
    from backend.core.message_bus import get_message_bus
    from backend.core.router import ModelRouter
    from backend.monitoring.gpu_monitor import GpuMonitor, get_gpu_monitor
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path / "workflows"))
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    get_gpu_monitor.cache_clear()

    router = ModelRouter(models_config)
    registry = AgentRegistry(fake_ollama_client, router, models_config)
    monkeypatch.setattr("backend.api.routes.chat.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.system.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.security.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.files.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.memory.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.tasks.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.research.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.verify.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.write.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.vision.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.classify.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.skills.get_agent_registry", lambda: registry)
    monkeypatch.setattr("backend.api.routes.evolution.get_agent_registry", lambda: registry)
    monkeypatch.setattr(
        "backend.api.routes.system.get_gpu_monitor",
        lambda: GpuMonitor(
            fake_ollama_client, get_settings(), run_command=lambda args: None, disk_path=str(tmp_path)
        ),
    )

    try:
        yield TestClient(main_module.app)
    finally:
        get_settings.cache_clear()
        get_agent_registry.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()
        get_gpu_monitor.cache_clear()


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
    OllamaClient and the developer's actual data/db/ folder. get_message_bus
    is cleared for the same reason (see the client fixture's docstring).
    WORKFLOWS_DIR is set for the same reason too, and get_project_store
    is cleared too — see the client fixture's docstring.

    get_gpu_monitor's cache is cleared for the same reason: the
    system_status MCP tool reaches it via that module-level singleton
    too. Unlike the `client` fixture, this doesn't override it with a
    fake — get_agent_registry() here builds a real (uncached, so freshly
    built) AgentRegistry backed by a real OllamaClient, and any test that
    exercises system_status must monkeypatch
    OllamaClient.list_running_models at the class level (see
    test_mcp_server.py's other tool tests for the pattern) to avoid a
    real network call; rocm-smi being genuinely absent from this sandbox
    already makes GpuMonitor degrade to gpu=None on its own."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    import backend.main as main_module
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.core.message_bus import get_message_bus
    from backend.monitoring.gpu_monitor import get_gpu_monitor
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "allowed"))
    monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path / "workflows"))
    (tmp_path / "allowed").mkdir()
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    get_gpu_monitor.cache_clear()

    app = main_module.create_app()

    # "localhost:8000" and not the old "mcp-test": FastMCP enables DNS-rebinding
    # protection by default and only allows Host headers matching
    # ['127.0.0.1:*', 'localhost:*', '[::1]:*'], so a synthetic hostname now gets
    # a bare "421 Misdirected Request" from the transport-security middleware
    # before any tool is reached. The port is required — the allow patterns end
    # in ":*", which is matched by prefix against "<host>:".
    MCP_TEST_BASE = "http://localhost:8000"

    def httpx_client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=MCP_TEST_BASE,
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
                f"{MCP_TEST_BASE}/mcp", httpx_client_factory=httpx_client_factory
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    finally:
        get_settings.cache_clear()
        get_agent_registry.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()
        get_gpu_monitor.cache_clear()


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


@pytest.fixture(autouse=True)
def _table_des_missions_propre():
    """Chaque test part d'une table de missions vide (HOS-245).

    Depuis que le registre des missions est **durable**, tous les
    `_RegistreMissions()` non injectés partagent une même table, sous la
    racine d'état que `conftest.py` déplace déjà vers un dossier
    temporaire. Sans ce nettoyage, un test hériterait des missions du
    précédent : `len(registre) == 1` deviendrait vrai ou faux selon
    l'ordre d'exécution, et la suite serait aléatoire sous
    `pytest-randomly`.

    C'est le prix de la persistance, et il se paie ici plutôt que dans
    chaque test.
    """
    yield
    try:
        from backend.mission.persistance import MagasinMissions

        MagasinMissions().vider()
    except Exception:  # pragma: no cover - base absente ou illisible
        pass
