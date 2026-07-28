"""HOS-011 sentinel tests — Runtime Health Monitor.

Tests the generic runtime health layer without contacting any concrete
backend (Ollama, cloud, etc.).
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.ral.capabilities import ChatCapability, ChatResponse
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_health import (
    RuntimeHealthError,
    RuntimeHealthMonitor,
    RuntimeHealthStatus,
    RuntimeMetrics,
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

    def __init__(self, runtime_name: str = "fake") -> None:
        self._runtime_name = runtime_name

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            content=f"fake-chat:{len(messages)}:{self._runtime_name}",
            metadata={},
        )


class _FakeRuntime:
    """Minimal runtime implementing :class:`RuntimeInterface` for tests."""

    def __init__(self, name: str, capabilities: list[str]) -> None:
        self.name = name
        self.version = "0.0.1"
        self.capabilities = CapabilitySet(frozenset(capabilities))
        self._status = RuntimeStatus.STOPPED
        self._caps: dict[str, Any] = {}
        if "chat" in capabilities:
            self._caps["chat"] = _FakeChatCapability(name)

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def start(self) -> None:
        self._status = RuntimeStatus.STARTED

    async def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def get(self, capability_name: str) -> Any:
        return self._caps.get(capability_name)


def _make_router(registry: RuntimeRegistry | None = None) -> RuntimeRouter:
    """Build a RuntimeRouter with an optional health monitor."""
    registry = registry or RuntimeRegistry()
    holder = RuntimeHolder()
    context = ActiveRuntimeContext(registry=registry, holder=holder)
    selector = RuntimeSelector(registry)
    monitor = RuntimeHealthMonitor(registry)
    return RuntimeRouter(context=context, selector=selector, health_monitor=monitor)


# ---------------------------------------------------------------------------
# Health monitor basics
# ---------------------------------------------------------------------------


def test_health_monitor_creation() -> None:
    registry = RuntimeRegistry()
    monitor = RuntimeHealthMonitor(registry)
    assert monitor.check_runtime is not None


def test_check_available_runtime() -> None:
    registry = RuntimeRegistry()
    chatty = _FakeRuntime("chatty", ["chat"])
    chatty._status = RuntimeStatus.STARTED
    registry.register("chatty", chatty)

    monitor = RuntimeHealthMonitor(registry)
    assert monitor.check_runtime("chatty") == RuntimeHealthStatus.AVAILABLE


def test_check_unavailable_runtime() -> None:
    registry = RuntimeRegistry()
    chatty = _FakeRuntime("chatty", ["chat"])
    # runtime is left STOPPED -> unavailable
    registry.register("chatty", chatty)

    monitor = RuntimeHealthMonitor(registry)
    assert monitor.check_runtime("chatty") == RuntimeHealthStatus.UNAVAILABLE


def test_check_unknown_runtime_raises() -> None:
    registry = RuntimeRegistry()
    monitor = RuntimeHealthMonitor(registry)

    with pytest.raises(RuntimeHealthError):
        monitor.check_runtime("missing")


def test_degraded_runtime_without_capabilities() -> None:
    registry = RuntimeRegistry()
    empty = _FakeRuntime("empty", [])
    empty._status = RuntimeStatus.STARTED
    registry.register("empty", empty)

    monitor = RuntimeHealthMonitor(registry)
    assert monitor.check_runtime("empty") == RuntimeHealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_initially_empty() -> None:
    registry = RuntimeRegistry()
    monitor = RuntimeHealthMonitor(registry)
    chatty = _FakeRuntime("chatty", ["chat"])
    chatty._status = RuntimeStatus.STARTED
    registry.register("chatty", chatty)

    metrics = monitor.get_metrics("chatty")
    assert metrics == RuntimeMetrics(runtime="chatty")


def test_record_execution_updates_metrics() -> None:
    registry = RuntimeRegistry()
    monitor = RuntimeHealthMonitor(registry)
    chatty = _FakeRuntime("chatty", ["chat"])
    chatty._status = RuntimeStatus.STARTED
    registry.register("chatty", chatty)

    monitor.record_execution("chatty", latency_ms=100, success=True)
    monitor.record_execution("chatty", latency_ms=200, success=False, error=ValueError("boom"))

    metrics = monitor.get_metrics("chatty")
    assert metrics.executions == 2
    assert metrics.failures == 1
    assert metrics.avg_latency_ms == 150.0
    assert metrics.failure_rate == 0.5
    assert metrics.last_error is not None


def test_error_prone_runtime() -> None:
    registry = RuntimeRegistry()
    monitor = RuntimeHealthMonitor(registry)
    chatty = _FakeRuntime("chatty", ["chat"])
    chatty._status = RuntimeStatus.STARTED
    registry.register("chatty", chatty)

    # 4 failures in 4 executions triggers the failure-count threshold.
    for _ in range(4):
        monitor.record_execution("chatty", success=False, error=RuntimeError("fail"))

    assert monitor.is_error_prone("chatty")


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


async def test_router_ignores_unavailable_runtime() -> None:
    registry = RuntimeRegistry()
    router = _make_router(registry)

    bad = _FakeRuntime("bad", ["chat"])
    good = _FakeRuntime("good", ["chat"])
    await good.start()
    registry.register("bad", bad)
    registry.register("good", good)

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert "good" in response.content


async def test_router_prefers_available_runtime() -> None:
    registry = RuntimeRegistry()
    router = _make_router(registry)

    first = _FakeRuntime("first", ["chat"])
    second = _FakeRuntime("second", ["chat"])
    await first.start()
    await second.start()
    registry.register("first", first)
    registry.register("second", second)

    # The first available runtime in registry order is selected.
    response = await router.chat([{"role": "user", "content": "hi"}])

    assert "first" in response.content


async def test_router_avoids_error_prone_runtime() -> None:
    registry = RuntimeRegistry()
    router = _make_router(registry)

    bad = _FakeRuntime("bad", ["chat"])
    good = _FakeRuntime("good", ["chat"])
    await bad.start()
    await good.start()
    registry.register("bad", bad)
    registry.register("good", good)

    # Mark the first runtime as error-prone.
    for _ in range(4):
        router._health_monitor.record_execution("bad", success=False, error=RuntimeError("fail"))

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert "good" in response.content


async def test_router_fallback_when_main_unavailable() -> None:
    registry = RuntimeRegistry()
    router = _make_router(registry)

    main = _FakeRuntime("main", ["chat"])
    fallback = _FakeRuntime("fallback", ["chat"])
    await fallback.start()
    registry.register("main", main)
    registry.register("fallback", fallback)

    context = router._context
    context.set_active("main")
    context.set_fallback("fallback")

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert "fallback" in response.content
