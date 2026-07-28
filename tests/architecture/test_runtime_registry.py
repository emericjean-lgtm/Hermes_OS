"""HOS-007 sentinel tests — RuntimeRegistry, RuntimeFactory & lifecycle.

Tests the dynamic runtime registry without any network call.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.ral.adapters.hermes_ollama import HermesOllamaRuntime
from backend.ral.adapters.stub_runtime import StubRuntime
from backend.ral.capabilities import ChatResponse
from backend.ral.event_bus import EventBusInterface
from backend.ral.runtime import RuntimeInterface, RuntimeStatus
from backend.ral.runtime_config import RuntimeConfig
from backend.ral.runtime_factory import RuntimeFactory, RuntimeLifecycle
from backend.ral.runtime_registry import RuntimeRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> RuntimeRegistry:
    """Return a fresh empty registry."""
    return RuntimeRegistry()


@pytest.fixture
def factory(registry: RuntimeRegistry) -> RuntimeFactory:
    """Return a factory wired to ``registry``."""
    return RuntimeFactory(registry=registry)


@pytest.fixture
def stub_runtime() -> StubRuntime:
    return StubRuntime(bus=None)


# ---------------------------------------------------------------------------
# 1. RuntimeRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get(registry: RuntimeRegistry, stub_runtime: StubRuntime) -> None:
    """Registering a runtime and retrieving it works."""
    registry.register("stub", stub_runtime)
    runtime = registry.get("stub")
    assert runtime is stub_runtime
    assert isinstance(runtime, RuntimeInterface)


def test_registry_unknown_runtime_raises_keyerror(registry: RuntimeRegistry) -> None:
    """Retrieving an unknown runtime raises ``KeyError``."""
    with pytest.raises(KeyError, match="Runtime 'missing' is not registered"):
        registry.get("missing")


def test_registry_multiple_runtimes_can_coexist(registry: RuntimeRegistry) -> None:
    """Several named runtimes can be registered at the same time."""
    runtime_a = StubRuntime(bus=None)
    runtime_b = StubRuntime(bus=None)
    registry.register("stub-a", runtime_a)
    registry.register("stub-b", runtime_b)
    assert registry.get("stub-a") is runtime_a
    assert registry.get("stub-b") is runtime_b
    assert set(registry.list_available()) == {"stub-a", "stub-b"}


def test_registry_remove_runtime(registry: RuntimeRegistry, stub_runtime: StubRuntime) -> None:
    """Removing a runtime makes it unavailable."""
    registry.register("stub", stub_runtime)
    registry.remove("stub")
    assert registry.list_available() == []
    with pytest.raises(KeyError):
        registry.get("stub")


# ---------------------------------------------------------------------------
# 2. RuntimeFactory
# ---------------------------------------------------------------------------


def test_factory_register_and_create(factory: RuntimeFactory) -> None:
    """A registered builder is used by ``create`` to produce a runtime."""
    factory.register_builder("stub", lambda **kw: StubRuntime(bus=None))
    runtime = factory.create("stub")
    assert isinstance(runtime, RuntimeInterface)
    assert runtime.name == "stub"


def test_factory_unknown_type_raises_valueerror(factory: RuntimeFactory) -> None:
    """Creating an unregistered runtime type raises ``ValueError``."""
    with pytest.raises(ValueError, match="Unknown runtime type 'unknown'"):
        factory.create("unknown")


def test_factory_dependency_injection_no_network(registry: RuntimeRegistry) -> None:
    """The factory injects dependencies without any real network call."""
    f = RuntimeFactory(registry=registry)
    f.register_builder(
        "ollama",
        lambda config: HermesOllamaRuntime(
            config=config,
            ollama_client=_FakeOllamaClient(),
            event_bus=None,
        ),
    )
    config = RuntimeConfig(model="test-model", endpoint="http://localhost:11434")
    runtime = f.create("ollama", config=config)
    assert isinstance(runtime, RuntimeInterface)
    assert runtime.name == "hermes-ollama"


# ---------------------------------------------------------------------------
# 3. RuntimeLifecycle
# ---------------------------------------------------------------------------


async def test_lifecycle_initialize_and_health_check(stub_runtime: StubRuntime) -> None:
    """RuntimeLifecycle.initialize sets status to STARTED and health_check passes."""
    assert not RuntimeLifecycle.health_check(stub_runtime)
    await RuntimeLifecycle.initialize(stub_runtime)
    assert stub_runtime.status == RuntimeStatus.STARTED
    assert RuntimeLifecycle.health_check(stub_runtime)
    await RuntimeLifecycle.shutdown(stub_runtime)
    assert not RuntimeLifecycle.health_check(stub_runtime)
    assert stub_runtime.status == RuntimeStatus.STOPPED


async def test_factory_created_runtime_is_registered(factory: RuntimeFactory) -> None:
    """When a factory is wired to a registry, ``create`` registers the runtime."""
    factory.register_builder("stub", lambda **kw: StubRuntime(bus=None))
    runtime = factory.create("stub")
    assert factory._registry is not None
    assert factory._registry.get("stub") is runtime


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------


class _FakeOllamaClient:
    """Minimal Ollama client double satisfying ``OllamaClientProtocol``."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> ChatResponse:
        return ChatResponse(content="fake", metadata={"model": model or "unknown"})

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        for token in ["hello", " ", "world"]:
            yield token

    async def chat_events(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        return
        yield  # type: ignore[unreachable]

    async def list_running_models(self) -> list[dict[str, Any]]:
        return []

    async def list_local_models(self) -> list[dict[str, Any]]:
        return []
