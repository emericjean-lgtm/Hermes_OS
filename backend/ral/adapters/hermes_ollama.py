"""Hermes Ollama runtime adapter (HOS-005).

Provides a concrete :class:`RuntimeInterface` implementation that
delegates inference calls to an Ollama server through the abstract
:class:`backend.connectors.ollama_client.OllamaClientProtocol`.
The adapter is fully testable without an actual Ollama instance by
injecting a mock client.

Typical usage::

    config = RuntimeConfig(model="qwen3.5:9b", endpoint="http://127.0.0.1:11434")
    client = OllamaClient(base_url=config.endpoint, timeout=config.timeout_seconds)
    runtime = HermesOllamaRuntime(config=config, ollama_client=client, event_bus=bus)
    await runtime.start()
    cap = runtime.get("chat")
    result = await cap.chat([{"role": "user", "content": "hello"}])
    await runtime.stop()
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.ral.capabilities import (
    CapabilityInterface,
    ChatCapability,
    ChatResponse,
    ChatStreamCapability,
)
from backend.ral.event_bus import EventBusInterface, Topic
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability implementations
# ---------------------------------------------------------------------------


class HermesOllamaChatCapability:
    """Chat capability backed by an :class:`OllamaClientProtocol` instance.

    Uses dependency injection for the client so the capability is
    testable without a live Ollama server.
    """

    name = "chat"

    def __init__(self, client: OllamaClientProtocol, config: RuntimeConfig) -> None:
        self._client = client
        self._config = config

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Delegate the chat request to the injected Ollama client."""
        model = self._config.model
        if runtime_ctx and "model" in runtime_ctx:
            model = runtime_ctx["model"]
        return await self._client.chat(messages, model=model)


class HermesOllamaChatStreamCapability:
    """Streaming chat capability backed by an :class:`OllamaClientProtocol`.

    Optional — only registered in the runtime's ``capabilities`` set if
    the injected client supports streaming.
    """

    name = "chat_stream"

    def __init__(self, client: OllamaClientProtocol, config: RuntimeConfig) -> None:
        self._client = client
        self._config = config

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from the injected Ollama client."""
        model = self._config.model
        if runtime_ctx and "model" in runtime_ctx:
            model = runtime_ctx["model"]
        # chat_stream on the connectors protocol takes model as first positional
        async for token in self._client.chat_stream(model, messages):
            yield token


# ---------------------------------------------------------------------------
# Runtime implementation
# ---------------------------------------------------------------------------


class HermesOllamaRuntime:
    """Concrete runtime adapter that wraps an Ollama inference endpoint.

    Satisfies :class:`RuntimeInterface` and exposes ``chat`` (and
    optionally ``chat_stream``) capabilities via dependency-injected
    :class:`OllamaClientProtocol`.

    The adapter does **not** import any concrete client or global
    configuration — it receives everything it needs through its
    constructor.
    """

    name = "hermes-ollama"
    version = "0.1.0"

    def __init__(
        self,
        config: RuntimeConfig,
        ollama_client: OllamaClientProtocol,
        event_bus: EventBusInterface | None = None,
    ) -> None:
        self._config = config
        self._client = ollama_client
        self._bus: EventBusInterface | None = event_bus
        self._status: RuntimeStatus = RuntimeStatus.STOPPED

        # Build capability instances
        self._chat = HermesOllamaChatCapability(client=ollama_client, config=config)
        self._chat_stream = HermesOllamaChatStreamCapability(
            client=ollama_client, config=config
        )

        # Determine available capabilities
        caps = {"chat", "chat_stream"}
        self._capabilities = CapabilitySet(available=frozenset(caps))

    # -- RuntimeInterface attributes ----------------------------------------

    @property
    def capabilities(self) -> CapabilitySet:
        return self._capabilities

    # -- RuntimeInterface status --------------------------------------------

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    # -- RuntimeInterface lifecycle -----------------------------------------

    async def start(self) -> None:
        """Transition to STARTED and publish ``RUNTIME_STARTED``."""
        self._status = RuntimeStatus.STARTED
        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STARTED,
                payload={"runtime": "hermes-ollama", "version": "0.1.0"},
            )
        logger.info(
            "HermesOllamaRuntime started (model=%s, endpoint=%s)",
            self._config.model,
            self._config.endpoint,
        )

    async def stop(self) -> None:
        """Transition to STOPPED and publish ``RUNTIME_STOPPED``."""
        self._status = RuntimeStatus.STOPPED
        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STOPPED,
                payload={"runtime": "hermes-ollama", "version": "0.1.0"},
            )
        logger.info("HermesOllamaRuntime stopped")

    # -- RuntimeInterface capability lookup ---------------------------------

    def get(self, capability_name: str) -> CapabilityInterface | None:
        if capability_name == "chat":
            return self._chat
        if capability_name == "chat_stream":
            return self._chat_stream
        return None
