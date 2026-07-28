"""HOS-023 sentinel tests — Hermes Agent Adapter.

Tests the adapter's data structures, lifecycle, task execution,
skill management, memory sync, subagent management, capabilities,
health checks, error handling, and thread safety — all without
real network calls.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.hermes_agent import (
    HermesAgentAdapter,
    HermesAgentCapabilities,
    HermesAgentConfiguration,
    HermesAgentError,
    HermesAgentExecution,
    HermesAgentSession,
    HermesAgentStatus,
    HermesAgentTask,
    HermesCapability,
)
from backend.memory.unified_memory import MemoryScope


# ============================================================================
# Dataclass tests
# ============================================================================


def test_configuration_defaults() -> None:
    cfg = HermesAgentConfiguration()
    assert cfg.base_url == "http://localhost:11434"
    assert cfg.keep_alive == "10m"
    assert cfg.timeout == 120.0
    assert cfg.max_attempts == 3
    assert cfg.auto_reconnect is True
    assert cfg.default_sensitivity == "standard"


def test_session_defaults() -> None:
    s = HermesAgentSession(session_id="s1", agent_name="prime")
    assert s.session_id == "s1"
    assert s.agent_name == "prime"
    assert s.message_count == 0


def test_task_defaults() -> None:
    t = HermesAgentTask(task_id="t1", agent_name="prime")
    assert t.task_id == "t1"
    assert t.status == "pending"
    assert t.result == ""
    assert t.error == ""


def test_execution_defaults() -> None:
    e = HermesAgentExecution(task_id="t1", agent_name="prime", success=True)
    assert e.task_id == "t1"
    assert e.success is True
    assert e.duration_ms == 0.0


def test_capabilities_defaults() -> None:
    caps = HermesAgentCapabilities(available=frozenset({"chat"}))
    assert "chat" in caps.available
    assert caps.models == ()


def test_hermes_capability_values() -> None:
    assert HermesCapability.CHAT.value == "chat"
    assert HermesCapability.CHAT_STREAM.value == "chat_stream"
    assert HermesCapability.TOOLS.value == "tools"
    assert HermesCapability.MEMORY.value == "memory"
    assert HermesCapability.SKILLS.value == "skills"
    assert HermesCapability.SUBAGENTS.value == "subagents"
    assert HermesCapability.DELEGATION.value == "delegation"


# ============================================================================
# Adapter creation
# ============================================================================


def test_adapter_defaults() -> None:
    adapter = HermesAgentAdapter()
    assert adapter.status == HermesAgentStatus.DISCONNECTED


def test_adapter_with_configuration() -> None:
    cfg = HermesAgentConfiguration(
        base_url="http://custom:11434",
        keep_alive="5m",
        timeout=60.0,
        max_attempts=5,
        auto_reconnect=False,
    )
    adapter = HermesAgentAdapter(configuration=cfg)
    assert adapter._config.base_url == "http://custom:11434"
    assert adapter._config.max_attempts == 5


def test_adapter_initial_state() -> None:
    adapter = HermesAgentAdapter()
    assert adapter.status == HermesAgentStatus.DISCONNECTED
    assert adapter.list_tasks() == []
    assert adapter.list_subagents() == {}


# ============================================================================
# Connection lifecycle (without real network)
# ============================================================================


@pytest.mark.asyncio
async def test_connect_with_mock_client() -> None:
    """Connect with a pre-supplied mock Ollama client."""
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(return_value=[{"name": "qwen3:14b"}])

    adapter = HermesAgentAdapter(ollama_client=mock_ollama)
    mock_agent = MagicMock()
    adapter._agent = mock_agent
    adapter._model_router = MagicMock()

    await adapter.connect()
    assert adapter.status == HermesAgentStatus.CONNECTED


@pytest.mark.asyncio
async def test_disconnect() -> None:
    adapter = HermesAgentAdapter()
    adapter._status = HermesAgentStatus.CONNECTED
    adapter._connect_time = 100.0

    await adapter.disconnect()
    assert adapter.status == HermesAgentStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_connect_ollama_unreachable_raises_error() -> None:
    """Connect should fail when Ollama is unreachable and auto_reconnect is off."""
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(side_effect=ConnectionError("refused"))

    cfg = HermesAgentConfiguration(auto_reconnect=False)
    adapter = HermesAgentAdapter(configuration=cfg, ollama_client=mock_ollama)
    mock_agent = MagicMock()
    adapter._agent = mock_agent
    adapter._model_router = MagicMock()

    with pytest.raises(HermesAgentError, match="Connection failed"):
        await adapter.connect()

    assert adapter.status == HermesAgentStatus.ERROR


# ============================================================================
# Task execution with mock agent
# ============================================================================


@pytest.mark.asyncio
async def test_execute_task_not_connected() -> None:
    adapter = HermesAgentAdapter()
    with pytest.raises(HermesAgentError, match="not connected"):
        await adapter.execute_task([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_execute_task_success() -> None:
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(return_value=[])

    mock_decision = MagicMock()
    mock_decision.model = "qwen3:14b"
    mock_decision.thinking = False

    # Proper async iterator for the stream.
    class MockStream:
        def __init__(self, items: list[str]) -> None:
            self._items = items
            self._idx = 0

        def __aiter__(self) -> "MockStream":
            return self

        async def __anext__(self) -> str:
            if self._idx >= len(self._items):
                raise StopAsyncIteration
            val = self._items[self._idx]
            self._idx += 1
            return val

    mock_agent = AsyncMock()
    mock_agent.respond = AsyncMock(
        return_value=(mock_decision, MockStream(["Hello", " world"]))
    )

    adapter = HermesAgentAdapter(ollama_client=mock_ollama, agent=mock_agent)
    adapter._model_router = MagicMock()
    adapter._status = HermesAgentStatus.CONNECTED

    execution = await adapter.execute_task(
        [{"role": "user", "content": "hello"}],
        task_type="chat",
    )

    assert execution.success is True
    assert execution.task_id is not None
    assert execution.content == "Hello world"
    assert execution.routing_decision is not None


@pytest.mark.asyncio
async def test_execute_task_failure() -> None:
    mock_ollama = AsyncMock()

    mock_agent = AsyncMock()
    mock_agent.respond = AsyncMock(side_effect=RuntimeError("Ollama crashed"))

    adapter = HermesAgentAdapter(ollama_client=mock_ollama, agent=mock_agent)
    adapter._model_router = MagicMock()
    adapter._status = HermesAgentStatus.CONNECTED

    execution = await adapter.execute_task(
        [{"role": "user", "content": "hello"}],
    )

    assert execution.success is False
    assert "Ollama crashed" in execution.error


# ============================================================================
# Task lifecycle
# ============================================================================


def test_task_cancel() -> None:
    adapter = HermesAgentAdapter()
    task_id = "test_task_1"

    adapter._tasks[task_id] = HermesAgentTask(
        task_id=task_id,
        agent_name="prime",
        status="running",
    )

    result = asyncio.run(adapter.cancel_task(task_id))
    assert result is True
    task = adapter.get_task(task_id)
    assert task is not None
    assert task.status == "cancelled"


def test_cancel_nonexistent_task() -> None:
    adapter = HermesAgentAdapter()
    result = asyncio.run(adapter.cancel_task("nonexistent"))
    assert result is False


def test_task_pause_resume() -> None:
    adapter = HermesAgentAdapter()
    task_id = "test_pause_1"

    adapter._tasks[task_id] = HermesAgentTask(
        task_id=task_id,
        agent_name="prime",
        status="running",
    )

    paused = asyncio.run(adapter.pause_task(task_id))
    assert paused is True
    task = adapter.get_task(task_id)
    assert task is not None
    assert task.status == "paused"

    resumed = asyncio.run(adapter.resume_task(task_id))
    assert resumed is True
    task = adapter.get_task(task_id)
    assert task is not None
    assert task.status == "running"


def test_pause_not_running() -> None:
    adapter = HermesAgentAdapter()
    result = asyncio.run(adapter.pause_task("nonexistent"))
    assert result is False


def test_list_tasks_by_status() -> None:
    adapter = HermesAgentAdapter()
    adapter._tasks["t1"] = HermesAgentTask(task_id="t1", agent_name="prime", status="completed")
    adapter._tasks["t2"] = HermesAgentTask(task_id="t2", agent_name="prime", status="running")
    adapter._tasks["t3"] = HermesAgentTask(task_id="t3", agent_name="prime", status="failed")

    running = adapter.list_tasks(status="running")
    assert len(running) == 1

    all_tasks = adapter.list_tasks()
    assert len(all_tasks) == 3


# ============================================================================
# Skills management
# ============================================================================


def test_list_skills_empty() -> None:
    adapter = HermesAgentAdapter()
    skills = adapter.list_skills()
    assert skills == []


def test_list_skills_with_registered() -> None:
    from backend.skills.orchestrator import SkillDescriptor

    adapter = HermesAgentAdapter()
    adapter._skill_orchestrator._repository.register(
        SkillDescriptor(id="s1", name="Test Skill", capabilities=frozenset({"chat"}))
    )
    skills = adapter.list_skills()
    assert len(skills) == 1
    assert skills[0].id == "s1"


def test_load_and_unload_skills() -> None:
    from backend.skills.orchestrator import SkillDescriptor

    adapter = HermesAgentAdapter()
    adapter._skill_orchestrator._repository.register(
        SkillDescriptor(id="s1", name="S1")
    )
    count = adapter.load_skills(["s1"])
    assert count == 1

    unloaded = adapter.unload_skills(["s1"])
    assert unloaded == 1


# ============================================================================
# Subagent management
# ============================================================================


def test_create_subagent() -> None:
    adapter = HermesAgentAdapter()
    result = adapter.create_subagent("code_agent", "prime")
    assert result == "code_agent"

    subagents = adapter.list_subagents()
    assert "code_agent" in subagents
    assert subagents["code_agent"] == "prime"


def test_create_duplicate_subagent_raises() -> None:
    adapter = HermesAgentAdapter()
    adapter.create_subagent("existing", "prime")
    with pytest.raises(HermesAgentError, match="already exists"):
        adapter.create_subagent("existing", "echo")


def test_list_subagents() -> None:
    adapter = HermesAgentAdapter()
    adapter.create_subagent("a1", "prime")
    adapter.create_subagent("a2", "echo")
    subs = adapter.list_subagents()
    assert len(subs) == 2


# ============================================================================
# Capabilities
# ============================================================================


@pytest.mark.asyncio
async def test_get_capabilities() -> None:
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(
        return_value=[{"name": "qwen3:14b"}, {"name": "nomic-embed-text"}]
    )

    adapter = HermesAgentAdapter(ollama_client=mock_ollama)
    adapter._status = HermesAgentStatus.CONNECTED

    caps = await adapter.get_capabilities()
    assert HermesCapability.CHAT.value in caps.available
    assert len(caps.models) == 2
    assert "prime" in caps.agents


# ============================================================================
# Health
# ============================================================================


@pytest.mark.asyncio
async def test_health_when_disconnected() -> None:
    adapter = HermesAgentAdapter()
    health = await adapter.health()
    assert health["status"] == "disconnected"
    assert health["ollama_reachable"] is False


@pytest.mark.asyncio
async def test_health_when_connected() -> None:
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(return_value=[{"name": "qwen3:14b"}])

    adapter = HermesAgentAdapter(ollama_client=mock_ollama)
    adapter._status = HermesAgentStatus.CONNECTED
    adapter._connect_time = 100.0

    health = await adapter.health()
    assert health["status"] == "connected"
    assert health["ollama_reachable"] is True
    assert health["models_available"] == 1


# ============================================================================
# Memory sync
# ============================================================================


@pytest.mark.asyncio
async def test_memory_sync_without_echo_agent() -> None:
    adapter = HermesAgentAdapter()

    adapter._memory.store("test content", title="test", scope=MemoryScope.SESSION)

    result = await adapter.sync_memory(scope=MemoryScope.SESSION)
    assert result["pushed"] == 0
    assert result["pulled"] == 0


# ============================================================================
# RuntimeInterface bridge
# ============================================================================


@pytest.mark.asyncio
async def test_as_runtime_returns_runtime_compatible_object() -> None:
    adapter = HermesAgentAdapter()
    runtime = adapter.as_runtime(runtime_name="test-runtime", runtime_version="1.0.0")
    assert runtime.name == "test-runtime"
    assert runtime.version == "1.0.0"
    assert "chat" in runtime.capabilities.available


@pytest.mark.asyncio
async def test_as_runtime_start_stop() -> None:
    mock_ollama = AsyncMock()
    mock_ollama.list_local_models = AsyncMock(return_value=[])
    mock_agent = MagicMock()

    adapter = HermesAgentAdapter(ollama_client=mock_ollama)
    adapter._agent = mock_agent
    adapter._model_router = MagicMock()

    runtime = adapter.as_runtime()
    assert runtime.status.name == "STOPPED"

    await runtime.start()
    assert runtime.status.name == "STARTED"

    await runtime.stop()
    assert runtime.status.name == "STOPPED"


# ============================================================================
# Error handling
# ============================================================================


def test_execute_task_no_agent() -> None:
    adapter = HermesAgentAdapter()
    adapter._status = HermesAgentStatus.CONNECTED
    adapter._agent = None

    with pytest.raises(HermesAgentError, match="No Hermes Agent"):
        asyncio.run(adapter.execute_task([{"role": "user", "content": "hi"}]))


def test_execute_task_stream_not_connected() -> None:
    adapter = HermesAgentAdapter()

    async def _try_stream() -> None:
        async for _ in adapter.execute_task_stream([{"role": "user", "content": "hi"}]):
            pass  # pragma: no cover

    with pytest.raises(HermesAgentError, match="not connected"):
        asyncio.run(_try_stream())


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_subagent_operations() -> None:
    adapter = HermesAgentAdapter()
    errors: list[Exception] = []

    def create_subagents() -> None:
        for i in range(20):
            try:
                adapter.create_subagent(f"agent_{i}", "prime")
            except Exception as e:
                errors.append(e)

    def list_subagents() -> None:
        for _ in range(20):
            try:
                adapter.list_subagents()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=create_subagents)
    t2 = threading.Thread(target=list_subagents)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert len(adapter.list_subagents()) == 20
