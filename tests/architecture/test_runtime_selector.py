"""HOS-009 sentinel tests — Runtime Selection & Active Runtime Context.

Tests the new selection and context abstractions without any network call.
"""

from __future__ import annotations

import pytest

from backend.ral.adapters.stub_runtime import StubRuntime
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelectionError, RuntimeSelector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeHolder:
    """Minimal holder stand-in for ActiveRuntimeContext tests."""

    def __init__(self) -> None:
        self._runtime: RuntimeInterface | None = None

    def install(self, runtime: RuntimeInterface) -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> RuntimeInterface:
        if self._runtime is None:
            raise RuntimeError("runtime_not_started")
        return self._runtime


class _CapabilityRuntime:
    """Runtime-like object with a configurable capability set and status."""

    def __init__(self, name: str, capabilities: frozenset[str], status: RuntimeStatus) -> None:
        self.name = name
        self.version = "0.0.1"
        self.capabilities = CapabilitySet(available=capabilities)
        self._status = status

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def start(self) -> None:
        self._status = RuntimeStatus.STARTED

    async def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def get(self, capability_name: str) -> object | None:
        return None


@pytest.fixture
def registry() -> RuntimeRegistry:
    return RuntimeRegistry()


@pytest.fixture
def holder() -> _FakeHolder:
    return _FakeHolder()


@pytest.fixture
def context(registry: RuntimeRegistry, holder: _FakeHolder) -> ActiveRuntimeContext:
    return ActiveRuntimeContext(registry=registry, holder=holder)


@pytest.fixture
def selector(registry: RuntimeRegistry) -> RuntimeSelector:
    return RuntimeSelector(registry)


# ---------------------------------------------------------------------------
# ActiveRuntimeContext
# ---------------------------------------------------------------------------


def test_context_set_active_switches_runtime(registry: RuntimeRegistry, holder: _FakeHolder) -> None:
    """Setting a runtime as active updates the underlying holder."""
    context = ActiveRuntimeContext(registry=registry, holder=holder)
    stub = StubRuntime(bus=None)
    registry.register("stub", stub)

    activated = context.set_active("stub")

    assert activated is stub
    assert holder.runtime is stub
    assert context.get_active_name() == "stub"


def test_context_set_active_unknown_runtime_raises_keyerror(context: ActiveRuntimeContext) -> None:
    """Activating an unknown runtime raises KeyError."""
    with pytest.raises(KeyError, match="'missing'"):
        context.set_active("missing")


def test_context_set_and_get_fallback(context: ActiveRuntimeContext) -> None:
    """The fallback pointer can be set and retrieved."""
    stub = StubRuntime(bus=None)
    context._registry.register("stub", stub)

    context.set_fallback("stub")

    assert context.fallback_name == "stub"


def test_context_set_fallback_unknown_raises_keyerror(context: ActiveRuntimeContext) -> None:
    """Setting an unknown fallback raises KeyError."""
    with pytest.raises(KeyError, match="'missing'"):
        context.set_fallback("missing")


def test_context_active_name_returns_none_when_holder_empty(context: ActiveRuntimeContext) -> None:
    """get_active_name returns None when no runtime is active."""
    assert context.get_active_name() is None


def test_context_active_name_reverse_resolves_registered_runtime(context: ActiveRuntimeContext) -> None:
    """get_active_name reverse-resolves the active runtime by identity."""
    stub = StubRuntime(bus=None)
    context._registry.register("stub", stub)
    context.set_active("stub")

    assert context.get_active_name() == "stub"


# ---------------------------------------------------------------------------
# RuntimeSelector
# ---------------------------------------------------------------------------


async def test_selector_selects_runtime_with_required_capability(registry: RuntimeRegistry) -> None:
    """Selector returns a runtime that advertises the requested capability."""
    stub = StubRuntime(bus=None)
    await stub.start()
    registry.register("stub", stub)
    selector = RuntimeSelector(registry)

    selected = selector.select("chat")

    assert selected is stub


async def test_selector_prefers_preferred_name_when_healthy(registry: RuntimeRegistry) -> None:
    """Selector returns the preferred runtime when it is healthy and capable."""
    stub = StubRuntime(bus=None)
    other = StubRuntime(bus=None)
    await stub.start()
    await other.start()
    registry.register("stub", stub)
    registry.register("other", other)
    selector = RuntimeSelector(registry)

    selected = selector.select("chat", preferred_name="other")

    assert selected is other


def test_selector_raises_when_no_runtime_matches(registry: RuntimeRegistry) -> None:
    """Selector raises RuntimeSelectionError when no runtime has the capability."""
    selector = RuntimeSelector(registry)

    with pytest.raises(RuntimeSelectionError, match="No runtime available for capability 'vision'"):
        selector.select("vision")


def test_selector_raises_when_preferred_name_missing(registry: RuntimeRegistry) -> None:
    """Selector raises RuntimeSelectionError when the preferred runtime is not registered."""
    selector = RuntimeSelector(registry)

    with pytest.raises(RuntimeSelectionError, match="Preferred runtime 'missing' is not registered"):
        selector.select("chat", preferred_name="missing")


def test_selector_ignores_unhealthy_runtimes(registry: RuntimeRegistry) -> None:
    """Selector skips runtimes whose status is not STARTED."""
    stopped = _CapabilityRuntime("stopped", frozenset({"chat"}), RuntimeStatus.STOPPED)
    started = _CapabilityRuntime("started", frozenset({"chat"}), RuntimeStatus.STARTED)
    registry.register("stopped", stopped)
    registry.register("started", started)
    selector = RuntimeSelector(registry)

    selected = selector.select("chat")

    assert selected is started


def test_selector_respects_preference_hint(registry: RuntimeRegistry) -> None:
    """Selector applies the local/cloud preference as a name substring hint."""
    local = _CapabilityRuntime("local-stub", frozenset({"chat"}), RuntimeStatus.STARTED)
    cloud = _CapabilityRuntime("cloud-stub", frozenset({"chat"}), RuntimeStatus.STARTED)
    registry.register("local", local)
    registry.register("cloud", cloud)
    selector = RuntimeSelector(registry)

    selected = selector.select("chat", preference="local")

    assert selected is local


def test_selector_lists_all_compatible_runtimes(registry: RuntimeRegistry) -> None:
    """list_compatible returns every runtime matching the criteria."""
    a = _CapabilityRuntime("a", frozenset({"chat"}), RuntimeStatus.STARTED)
    b = _CapabilityRuntime("b", frozenset({"chat"}), RuntimeStatus.STARTED)
    c = _CapabilityRuntime("c", frozenset({"vision"}), RuntimeStatus.STARTED)
    registry.register("a", a)
    registry.register("b", b)
    registry.register("c", c)
    selector = RuntimeSelector(registry)

    compatible = selector.list_compatible("chat")

    assert set(rt.name for rt in compatible) == {"a", "b"}


# ---------------------------------------------------------------------------
# Architecture compatibility
# ---------------------------------------------------------------------------


async def test_selector_only_reads_from_registry(registry: RuntimeRegistry) -> None:
    """RuntimeSelector never mutates the registry."""
    stub = StubRuntime(bus=None)
    await stub.start()
    registry.register("stub", stub)
    selector = RuntimeSelector(registry)

    selector.select("chat")

    assert registry.list_available() == ["stub"]
    assert registry.get("stub") is stub


def test_context_does_not_create_runtime_instances(context: ActiveRuntimeContext) -> None:
    """ActiveRuntimeContext manipulates references only; it does not build runtimes."""
    assert context._registry.list_available() == []
