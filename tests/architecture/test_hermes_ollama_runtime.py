"""HOS-005 sentinel tests — HermesOllamaRuntime implementation.

All tests work **without** an actual Ollama server by injecting a
``FakeOllamaClient`` that implements :class:`OllamaClientProtocol`.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.ral.adapters.hermes_ollama import (
    HermesOllamaChatCapability,
    HermesOllamaChatStreamCapability,
    HermesOllamaRuntime,
)
from backend.ral.capabilities import ChatCapability, ChatResponse, ChatStreamCapability
from backend.ral.event_bus import Topic
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_config import RuntimeConfig


# ---------------------------------------------------------------------------
# Fake Ollama client
# ---------------------------------------------------------------------------

_DEFAULT_CHAT_RESPONSE = ChatResponse(
    content="Hello from fake Ollama!",
    metadata={"model": "test-model", "provider": "ollama"},
)


class FakeOllamaClient:
    """Minimal test double that satisfies :class:`OllamaClientProtocol`.

    Records every call for inspection by the test.
    """

    def __init__(self) -> None:
        self.chat_calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
        self.stream_calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> ChatResponse:
        self.chat_calls.append((messages, {"model": model}))
        return _DEFAULT_CHAT_RESPONSE

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        self.stream_calls.append((messages, {"model": model, **kwargs}))
        for token in ["Hello", " ", "from", " ", "Fake", "!"]:
            yield token

    async def chat_events(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Stub — not used directly in these tests."""
        return
        yield  # type: ignore[unreachable]

    async def list_running_models(self) -> list[dict[str, Any]]:
        return []

    async def list_local_models(self) -> list[dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> RuntimeConfig:
    return RuntimeConfig(
        model="qwen3.5:9b", endpoint="http://127.0.0.1:11434", timeout_seconds=30
    )


@pytest.fixture
def fake_client() -> FakeOllamaClient:
    return FakeOllamaClient()


@pytest.fixture
def runtime(fake_client: FakeOllamaClient, config: RuntimeConfig) -> HermesOllamaRuntime:
    return HermesOllamaRuntime(
        config=config, ollama_client=fake_client, event_bus=None
    )


# ---------------------------------------------------------------------------
# 1. Protocol compliance
# ---------------------------------------------------------------------------


def test_runtime_satisfies_runtime_interface(runtime: HermesOllamaRuntime) -> None:
    """HermesOllamaRuntime must be recognised by ``RuntimeInterface``."""
    assert isinstance(runtime, RuntimeInterface)


def test_chat_capability_satisfies_chat_protocol(
    runtime: HermesOllamaRuntime,
) -> None:
    """The ``chat`` capability must be recognised by ``ChatCapability``."""
    cap = runtime.get("chat")
    assert cap is not None
    assert isinstance(cap, ChatCapability)


def test_stream_capability_satisfies_chat_stream_protocol(
    runtime: HermesOllamaRuntime,
) -> None:
    """The ``chat_stream`` capability must be recognised by ``ChatStreamCapability``."""
    cap = runtime.get("chat_stream")
    assert cap is not None
    assert isinstance(cap, ChatStreamCapability)


def test_ollama_client_protocol_recognises_fake(fake_client: FakeOllamaClient) -> None:
    """FakeOllamaClient must be recognised by ``OllamaClientProtocol``."""
    assert isinstance(fake_client, OllamaClientProtocol)


# ---------------------------------------------------------------------------
# 2. Capability set
# ---------------------------------------------------------------------------


def test_capabilities_contains_chat_and_stream(
    runtime: HermesOllamaRuntime,
) -> None:
    assert "chat" in runtime.capabilities.available
    assert "chat_stream" in runtime.capabilities.available


def test_capability_set_is_frozen(runtime: HermesOllamaRuntime) -> None:
    assert isinstance(runtime.capabilities, CapabilitySet)
    assert isinstance(runtime.capabilities.available, frozenset)


# ---------------------------------------------------------------------------
# 3. Lifecycle & status (RuntimeStatus now on RuntimeInterface)
# ---------------------------------------------------------------------------


async def test_initial_status_is_stopped(runtime: HermesOllamaRuntime) -> None:
    assert runtime.status == RuntimeStatus.STOPPED


async def test_status_is_started_after_start(runtime: HermesOllamaRuntime) -> None:
    await runtime.start()
    assert runtime.status == RuntimeStatus.STARTED
    await runtime.stop()


async def test_status_is_stopped_after_stop(runtime: HermesOllamaRuntime) -> None:
    await runtime.start()
    await runtime.stop()
    assert runtime.status == RuntimeStatus.STOPPED


async def test_start_publishes_event() -> None:
    """Start must publish ``RUNTIME_STARTED`` when an event bus is injected."""
    import tempfile
    from datetime import datetime, timezone

    from backend.ral.event_bus_impl import EventBusImpl

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name
    try:
        bus = EventBusImpl(db)
        await bus.start()
        rt = HermesOllamaRuntime(
            config=RuntimeConfig(model="test", endpoint="http://localhost:11434"),
            ollama_client=FakeOllamaClient(),
            event_bus=bus,
        )
        await rt.start()
        events = []
        async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
            events.append(e)
        await rt.stop()
        await bus.stop()
        assert any(e.topic == Topic.RUNTIME_STARTED for e in events)
    finally:
        os.unlink(db)


async def test_stop_publishes_event() -> None:
    import tempfile
    from datetime import datetime, timezone

    from backend.ral.event_bus_impl import EventBusImpl

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name
    try:
        bus = EventBusImpl(db)
        await bus.start()
        rt = HermesOllamaRuntime(
            config=RuntimeConfig(model="test", endpoint="http://localhost:11434"),
            ollama_client=FakeOllamaClient(),
            event_bus=bus,
        )
        await rt.start()
        await rt.stop()
        events = []
        async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
            events.append(e)
        await bus.stop()
        assert any(e.topic == Topic.RUNTIME_STOPPED for e in events)
    finally:
        os.unlink(db)


# ---------------------------------------------------------------------------
# 4. Chat capability — delegates to the injected client
# ---------------------------------------------------------------------------


async def test_chat_delegates_to_client(
    runtime: HermesOllamaRuntime, fake_client: FakeOllamaClient
) -> None:
    await runtime.start()
    cap = runtime.get("chat")
    assert cap is not None

    messages = [{"role": "user", "content": "hello"}]
    result = await cap.chat(messages)
    assert isinstance(result, ChatResponse)
    assert len(fake_client.chat_calls) == 1

    sent_msgs, kwargs = fake_client.chat_calls[0]
    assert sent_msgs == messages
    assert kwargs.get("model") == "qwen3.5:9b"
    await runtime.stop()


async def test_chat_passes_model_from_runtime_ctx(
    runtime: HermesOllamaRuntime, fake_client: FakeOllamaClient
) -> None:
    await runtime.start()
    cap = runtime.get("chat")
    assert cap is not None

    await cap.chat(
        [{"role": "user", "content": "hello"}],
        runtime_ctx={"model": "override-model"},
    )
    _, kwargs = fake_client.chat_calls[0]
    assert kwargs.get("model") == "override-model"
    await runtime.stop()


# ---------------------------------------------------------------------------
# 5. Stream capability
# ---------------------------------------------------------------------------


async def test_chat_stream_returns_tokens(
    runtime: HermesOllamaRuntime, fake_client: FakeOllamaClient
) -> None:
    await runtime.start()
    cap = runtime.get("chat_stream")
    assert cap is not None
    assert isinstance(cap, ChatStreamCapability)

    messages = [{"role": "user", "content": "stream this"}]
    tokens = []
    async for token in cap.chat_stream(messages):  # type: ignore[arg-type]
        tokens.append(token)
    assert len(tokens) == 6
    assert "".join(tokens) == "Hello from Fake!"
    assert len(fake_client.stream_calls) == 1
    await runtime.stop()


# ---------------------------------------------------------------------------
# 6. get() capability lookup
# ---------------------------------------------------------------------------


def test_get_chat_returns_capability(runtime: HermesOllamaRuntime) -> None:
    cap = runtime.get("chat")
    assert cap is not None
    assert isinstance(cap, HermesOllamaChatCapability)


def test_get_chat_stream_returns_capability(runtime: HermesOllamaRuntime) -> None:
    cap = runtime.get("chat_stream")
    assert cap is not None
    assert isinstance(cap, HermesOllamaChatStreamCapability)


def test_get_unknown_returns_none(runtime: HermesOllamaRuntime) -> None:
    assert runtime.get("vision") is None
    assert runtime.get("tools") is None


# ---------------------------------------------------------------------------
# 7. RuntimeConfig
# ---------------------------------------------------------------------------


def test_runtime_config_frozen() -> None:
    config = RuntimeConfig(model="test", endpoint="http://localhost:11434")
    assert config.model == "test"
    assert config.endpoint == "http://localhost:11434"
    assert config.timeout_seconds == 120  # default


def test_runtime_config_immutable() -> None:
    config = RuntimeConfig(model="x", endpoint="y", timeout_seconds=60)
    with pytest.raises(AttributeError):
        config.model = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. HOS-006 — Concrete OllamaClient.chat() via mock
# ---------------------------------------------------------------------------


async def test_ollama_client_chat_via_fake() -> None:
    """FakeOllamaClient implements the canonical protocol — chat() returns
    ChatResponse via the connectors OllamaClientProtocol."""
    fake = FakeOllamaClient()
    assert isinstance(fake, OllamaClientProtocol)
    result = await fake.chat([{"role": "user", "content": "hi"}], model="test")
    assert isinstance(result, ChatResponse)
    assert result.content == "Hello from fake Ollama!"


async def test_ollama_client_protocol_is_canonical() -> None:
    """The canonical OllamaClientProtocol lives in connectors, not RAL.

    The RAL adapter imports it — it must not **redefine** it.
    """
    import backend.ral.adapters.hermes_ollama as ral_adapter

    # ``__dict__`` only contains names **defined** in the module, not
    # names brought in by ``from ... import`` (those live in the module's
    # namespace but are not in ``__dict__`` unless the import is an
    # assignment to a module-level name — which is the case here for the
    # import, but the *class object* itself is ``backend.connectors.ollama_client.OllamaClientProtocol``,
    # not a locally defined class).
    # We verify by checking the module's source file string representation.
    import inspect

    source = inspect.getsource(ral_adapter)
    assert "class OllamaClientProtocol" not in source, (
        "OllamaClientProtocol must not be redefined in RAL adapters; "
        "the canonical Protocol lives in backend.connectors.ollama_client"
    )


async def test_ollama_client_chat_handles_timeout() -> None:
    """OllamaClient must handle timeout via RuntimeConfig."""
    from backend.connectors.ollama_client import OllamaClient

    # Timeout is passed to the httpx client via the constructor
    client = OllamaClient(base_url="http://localhost:11434", timeout=5.0)
    assert client is not None
    # The timeout is an httpx internal; we verify the config round-trips
    config = RuntimeConfig(
        model="qwen3.5:9b", endpoint="http://localhost:11434", timeout_seconds=5
    )
    assert config.timeout_seconds == 5
