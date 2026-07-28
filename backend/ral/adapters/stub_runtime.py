"""Stub runtime — minimal RuntimeInterface implementation (HOS-004).

Provides a concrete but inert runtime adapter that allows E2E validation
of the RAL integration (EventBus, SDS, lifecycle) without connecting to
any real agent engine.

Typical usage::

    stub = StubRuntime(bus=get_holder().bus)
    await stub.start()   # publishes RUNTIME_STARTED
    result = await stub.get("chat").chat([{"role":"user",
                                           "content":"hello"}])
    await stub.stop()    # publishes RUNTIME_STOPPED
"""
from __future__ import annotations

import logging
from typing import Any

from backend.ral.capabilities import (
    CapabilityInterface,
    ChatCapability,
    ChatResponse,
)
from backend.ral.event_bus import EventBusInterface, Topic
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability implementations
# ---------------------------------------------------------------------------


class StubChatCapability:
    """Chat capability that echoes the last user message."""

    name = "chat"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Echo the last user message as a stub response."""
        user_msg = "[stub] no user message found"
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")[:200]
                break
        return ChatResponse(
            content=f"[stub-runtime] echo: {user_msg}",
            metadata={"runtime": "stub", "version": "0.1.0"},
        )


# ---------------------------------------------------------------------------
# Runtime implementation
# ---------------------------------------------------------------------------


class StubRuntime:
    """In-memory runtime that satisfies :class:`RuntimeInterface`.

    Uses **dependency injection** for the event bus rather than a global
    accessor, so the stub is testable without a running EventBusImpl.
    """

    name = "stub"
    version = "0.1.0"
    capabilities = CapabilitySet(available=frozenset({"chat"}))

    def __init__(self, bus: EventBusInterface | None = None) -> None:
        self._bus: EventBusInterface | None = bus
        self._chat = StubChatCapability()
        self._status: RuntimeStatus = RuntimeStatus.STOPPED

    @property
    def status(self) -> RuntimeStatus:
        """Current lifecycle status of the stub runtime."""
        return self._status

    async def start(self) -> None:
        """Mark started and publish ``RUNTIME_STARTED``."""
        self._status = RuntimeStatus.STARTED
        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STARTED,
                payload={"runtime": "stub", "version": "0.1.0"},
            )
        logger.info("StubRuntime started")

    async def stop(self) -> None:
        """Mark stopped and publish ``RUNTIME_STOPPED``."""
        self._status = RuntimeStatus.STOPPED
        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STOPPED,
                payload={"runtime": "stub", "version": "0.1.0"},
            )
        logger.info("StubRuntime stopped")

    def get(self, capability_name: str) -> CapabilityInterface | None:
        """Return the matching capability or ``None``."""
        if capability_name == "chat":
            return self._chat
        return None
