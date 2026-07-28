"""HOS-012 sentinel tests — Runtime Recovery & Failover Engine.

Tests the circuit breaker, recovery manager and router failover without
contacting any concrete backend.
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.ral.capabilities import ChatCapability, ChatResponse, ToolResult, ToolsCapability
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_recovery import (
    CircuitBreaker,
    CircuitState,
    ExecutionTrace,
    RuntimeRecoveryError,
    RuntimeRecoveryManager,
)
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_router import RuntimeExecutionError, RuntimeRouter
from backend.ral.runtime_selector import RuntimeSelector
from backend.sds.runtime import RuntimeHolder


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeChatCapability:
    name = "chat"

    def __init__(self, runtime_name: str, *, fail: bool = False) -> None:
        self._runtime_name = runtime_name
        self._fail = fail

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        if self._fail:
            raise RuntimeError("chat failed")
        return ChatResponse(
            content=f"ok:{self._runtime_name}",
            metadata={},
        )


class _FakeRuntime:
    """Minimal runtime implementing :class:`RuntimeInterface` for tests."""

    def __init__(self, name: str, *, fail_chat: bool = False) -> None:
        self.name = name
        self.version = "0.0.1"
        self.capabilities = CapabilitySet(frozenset(["chat"]))
        self._status = RuntimeStatus.STOPPED
        self._chat = _FakeChatCapability(name, fail=fail_chat)

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def start(self) -> None:
        self._status = RuntimeStatus.STARTED

    async def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def get(self, capability_name: str) -> Any:
        if capability_name == "chat":
            return self._chat
        return None


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.is_allowed()


def test_circuit_opens_after_failures() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.is_allowed()


def test_circuit_half_open_after_timeout() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.is_allowed()
    # Wait for recovery timeout.
    import time
    time.sleep(0.07)
    assert cb.is_allowed()
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_closes_after_success_in_half_open() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
    cb.record_failure()
    import time
    time.sleep(0.07)
    assert cb.is_allowed()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Recovery manager
# ---------------------------------------------------------------------------


def test_recovery_manager_tracks_failures() -> None:
    registry = RuntimeRegistry()
    selector = RuntimeSelector(registry)
    manager = RuntimeRecoveryManager(registry, selector, failure_threshold=2)

    registry.register("runtime", _FakeRuntime("runtime"))

    assert manager.should_retry("runtime")
    manager.record_failure("runtime")
    manager.record_failure("runtime")
    assert not manager.should_retry("runtime")

    manager.reset("runtime")
    assert manager.should_retry("runtime")


# ---------------------------------------------------------------------------
# Router failover
# ---------------------------------------------------------------------------


def _make_router(registry: RuntimeRegistry, *, max_retries: int = 2) -> RuntimeRouter:
    holder = RuntimeHolder()
    context = ActiveRuntimeContext(registry=registry, holder=holder)
    selector = RuntimeSelector(registry)
    manager = RuntimeRecoveryManager(registry, selector, failure_threshold=2)
    return RuntimeRouter(
        context=context,
        selector=selector,
        recovery_manager=manager,
        max_retries=max_retries,
    )


async def test_simple_fallback() -> None:
    registry = RuntimeRegistry()
    failing = _FakeRuntime("failing", fail_chat=True)
    backup = _FakeRuntime("backup")
    await failing.start()
    await backup.start()
    registry.register("failing", failing)
    registry.register("backup", backup)

    router = _make_router(registry, max_retries=1)
    # Force the router to pick "failing" first (active runtime).
    router._context.set_active("failing")

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert response.content == "ok:backup"
    trace = response.metadata["execution_trace"]
    assert trace["runtime_initial"] == "failing"
    assert trace["runtime_final"] == "backup"
    assert trace["retries"] == 1


async def test_router_retries_limited() -> None:
    registry = RuntimeRegistry()
    first = _FakeRuntime("first", fail_chat=True)
    second = _FakeRuntime("second", fail_chat=True)
    await first.start()
    await second.start()
    registry.register("first", first)
    registry.register("second", second)

    router = _make_router(registry, max_retries=1)

    with pytest.raises(RuntimeExecutionError):
        await router.chat([{"role": "user", "content": "hi"}])


async def test_no_fallback_raises() -> None:
    registry = RuntimeRegistry()
    only = _FakeRuntime("only", fail_chat=True)
    await only.start()
    registry.register("only", only)

    router = _make_router(registry, max_retries=0)

    with pytest.raises(RuntimeExecutionError):
        await router.chat([{"role": "user", "content": "hi"}])


async def test_recovery_after_success() -> None:
    registry = RuntimeRegistry()
    first = _FakeRuntime("first", fail_chat=True)
    second = _FakeRuntime("second")
    await first.start()
    await second.start()
    registry.register("first", first)
    registry.register("second", second)

    router = _make_router(registry, max_retries=2)

    # First call triggers failure and fallback.
    response = await router.chat([{"role": "user", "content": "hi"}])
    assert response.content == "ok:second"

    # Simulate fixing the first runtime and reset its circuit.
    router._recovery_manager.reset("first")

    # Mark first as healthy again for a subsequent request.
    first._chat._fail = False
    response = await router.chat([{"role": "user", "content": "hi"}])
    # The router should be able to pick first again since the circuit is closed.
    assert response.content == "ok:first"
