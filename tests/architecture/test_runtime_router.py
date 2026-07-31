"""HOS-010 sentinel tests — Runtime Execution Router.

Tests the :class:`RuntimeRouter` resolution and capability routing
without any network call.
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.ral.capabilities import ChatResponse, ToolResult
from backend.ral.runtime import CapabilitySet, RuntimeStatus
from backend.ral.runtime_context import ActiveRuntimeContext
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
            metadata={"runtime_ctx": runtime_ctx},
        )


class _FakeToolsCapability:
    name = "tools"

    async def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        return ToolResult(output=f"invoked:{tool_name}", is_error=False)


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
        if "tools" in capabilities:
            self._caps["tools"] = _FakeToolsCapability()

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def start(self) -> None:
        self._status = RuntimeStatus.STARTED

    async def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def get(self, capability_name: str) -> Any:
        return self._caps.get(capability_name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_router() -> RuntimeRouter:
    """Build a RuntimeRouter backed by fresh registry and holder."""
    registry = RuntimeRegistry()
    holder = RuntimeHolder()
    context = ActiveRuntimeContext(registry=registry, holder=holder)
    selector = RuntimeSelector(registry)
    return RuntimeRouter(context=context, selector=selector)


# ---------------------------------------------------------------------------
# Active runtime resolution
# ---------------------------------------------------------------------------


async def test_router_uses_active_runtime_for_chat() -> None:
    router = _make_router()
    chatty = _FakeRuntime("chatty", ["chat"])
    await chatty.start()
    router._context.registry.register("chatty", chatty)
    router._context.set_active("chatty")

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert response.content == "fake-chat:1:chatty"
    assert response.metadata == {"runtime_ctx": None}


async def test_router_falls_back_to_selector_when_active_missing() -> None:
    router = _make_router()
    chatty = _FakeRuntime("chatty", ["chat"])
    await chatty.start()
    router._context.registry.register("chatty", chatty)

    response = await router.chat([{"role": "user", "content": "hello"}])

    assert response.content == "fake-chat:1:chatty"


async def test_router_uses_preferred_name() -> None:
    router = _make_router()
    local = _FakeRuntime("local-chat", ["chat"])
    cloud = _FakeRuntime("cloud-chat", ["chat"])
    await local.start()
    await cloud.start()
    router._context.registry.register("local", local)
    router._context.registry.register("cloud", cloud)

    response = await router.chat([], preferred_name="cloud")

    # The preferred runtime is selected even though the selector would
    # otherwise return the first registered runtime.
    assert "cloud-chat" in response.content


async def test_router_uses_fallback_runtime_when_active_unhealthy() -> None:
    router = _make_router()
    active = _FakeRuntime("active", ["chat"])
    fallback = _FakeRuntime("fallback", ["chat"])
    await fallback.start()
    # active is left STOPPED.
    router._context.registry.register("active", active)
    router._context.registry.register("fallback", fallback)
    router._context.set_active("active")
    router._context.set_fallback("fallback")

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert response.content == "fake-chat:1:fallback"


async def test_router_raises_when_no_runtime_available() -> None:
    router = _make_router()

    with pytest.raises(RuntimeExecutionError):
        await router.chat([{"role": "user", "content": "hi"}])


async def test_router_raises_when_active_unhealthy_and_no_fallback() -> None:
    router = _make_router()
    active = _FakeRuntime("active", ["chat"])
    router._context.registry.register("active", active)
    router._context.set_active("active")

    with pytest.raises(RuntimeExecutionError):
        await router.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Capability routing
# ---------------------------------------------------------------------------


async def test_router_routes_to_tools_capability() -> None:
    router = _make_router()
    tools = _FakeRuntime("tools", ["tools"])
    await tools.start()
    router._context.registry.register("tools", tools)

    result = await router.invoke_tool("do_thing", {"arg": 1})

    assert result == ToolResult(output="invoked:do_thing", is_error=False)


async def test_router_uses_local_preference() -> None:
    router = _make_router()
    local = _FakeRuntime("local-stub", ["chat"])
    cloud = _FakeRuntime("cloud-stub", ["chat"])
    await local.start()
    await cloud.start()
    router._context.registry.register("local", local)
    router._context.registry.register("cloud", cloud)

    response = await router.chat([], preference="local")

    assert "local-stub" in response.content



async def test_router_skips_active_runtime_missing_capability() -> None:
    router = _make_router()
    tools_only = _FakeRuntime("tools-only", ["tools"])
    chatty = _FakeRuntime("chatty", ["chat"])
    await chatty.start()
    router._context.registry.register("tools-only", tools_only)
    router._context.registry.register("chatty", chatty)
    router._context.set_active("tools-only")

    response = await router.chat([{"role": "user", "content": "hi"}])

    assert response.content == "fake-chat:1:chatty"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_router_raises_when_runtime_lacks_advertised_capability() -> None:
    """A runtime that advertises a capability but returns None violates the contract.

    The router must surface this as a RuntimeExecutionError rather than
    failing with an AttributeError.
    """
    router = _make_router()
    broken = _FakeRuntime("broken", ["chat"])
    broken._caps.pop("chat")  # type: ignore[attr-defined]
    await broken.start()
    router._context.registry.register("broken", broken)

    with pytest.raises(RuntimeExecutionError):
        await router.chat([{"role": "user", "content": "hi"}], preferred_name="broken")


async def test_router_raises_when_tool_runtime_unavailable() -> None:
    router = _make_router()
    chat_only = _FakeRuntime("chat-only", ["chat"])
    await chat_only.start()
    router._context.registry.register("chat-only", chat_only)

    with pytest.raises(RuntimeExecutionError):
        await router.invoke_tool("do_thing", {})
