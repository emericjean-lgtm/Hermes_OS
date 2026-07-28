"""Runtime Abstraction Layer — capability protocols.

This module defines the nine capability contracts supported by the RAL.
Each capability is a :class:`typing.Protocol` that concrete runtime adapters
may implement. No implementation is provided here.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any


@typing.runtime_checkable
class CapabilityInterface(typing.Protocol):
    """Base protocol for all capabilities exposed by a runtime."""

    name: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatResponse:
    """Result of a chat completion request."""

    content: str
    metadata: dict[str, Any]


@typing.runtime_checkable
class ChatCapability(CapabilityInterface, typing.Protocol):
    """Capability to converse with a model through the runtime."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Send messages and return the model response."""
        ...


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool invocation."""

    output: Any
    is_error: bool


@typing.runtime_checkable
class ToolsCapability(CapabilityInterface, typing.Protocol):
    """Capability to invoke tools through the runtime."""

    async def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """Invoke a named tool with the provided arguments."""
        ...


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegationResult:
    """Result of a delegation request to another agent/runtime."""

    status: str
    result: Any


@typing.runtime_checkable
class DelegateCapability(CapabilityInterface, typing.Protocol):
    """Capability to delegate work to another agent or runtime."""

    async def delegate(
        self,
        target: str,
        prompt: str,
        *,
        isolation: bool = False,
    ) -> DelegationResult:
        """Delegate a prompt to the named target.

        Args:
            target: Identifier of the target agent/runtime.
            prompt: Task description to forward.
            isolation: If ``True``, run the delegation in an fresh, isolated
                context.
        """
        ...


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@typing.runtime_checkable
class MemoryCapability(CapabilityInterface, typing.Protocol):
    """Capability to store and retrieve runtime-scoped memory."""

    async def store(self, key: str, value: Any, *, scope: str) -> None:
        """Store ``value`` under ``key`` inside the given ``scope``."""
        ...

    async def retrieve(self, key: str, *, scope: str) -> Any:
        """Retrieve the value stored under ``key`` inside the given ``scope``."""
        ...


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserPage:
    """Reference to an opened browser page."""

    page_id: str
    url: str


@dataclass(frozen=True)
class BrowserAction:
    """Action to perform on a browser page."""

    action_type: str
    params: dict[str, Any]


@dataclass(frozen=True)
class BrowserResult:
    """Outcome of a browser action."""

    status: str
    data: Any


@typing.runtime_checkable
class BrowserCapability(CapabilityInterface, typing.Protocol):
    """Capability to interact with a web browser."""

    async def open(self, url: str) -> BrowserPage:
        """Open ``url`` and return a page reference."""
        ...

    async def act(self, page: BrowserPage, action: BrowserAction) -> BrowserResult:
        """Execute ``action`` on the given ``page``."""
        ...

    async def close(self, page: BrowserPage) -> None:
        """Close the given ``page``."""
        ...


# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SandboxSpec:
    """Specification of an execution sandbox for terminal commands."""

    environment: dict[str, str]
    workdir: str


@dataclass(frozen=True)
class TerminalResult:
    """Result of a terminal command execution."""

    exit_code: int
    stdout: str
    stderr: str


@typing.runtime_checkable
class TerminalCapability(CapabilityInterface, typing.Protocol):
    """Capability to run commands inside a sandboxed terminal."""

    async def run(
        self,
        command: str,
        *,
        sandbox: SandboxSpec,
        timeout: int | None,
    ) -> TerminalResult:
        """Run ``command`` inside ``sandbox`` and return its result."""
        ...


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@typing.runtime_checkable
class FilesCapability(CapabilityInterface, typing.Protocol):
    """Capability to read and write files through the runtime."""

    async def read(self, path: str, *, offset: int, limit: int) -> str:
        """Read up to ``limit`` characters from ``path`` starting at ``offset``."""
        ...

    async def write(self, path: str, content: str, *, mode: str) -> None:
        """Write ``content`` to ``path`` using the specified ``mode``."""
        ...


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisionResult:
    """Result of a vision analysis."""

    description: str
    inferred_objects: list[str]


@typing.runtime_checkable
class VisionCapability(CapabilityInterface, typing.Protocol):
    """Capability to analyze images through the runtime."""

    async def analyze(self, image: bytes, *, prompt: str) -> VisionResult:
        """Analyze ``image`` using the provided ``prompt``."""
        ...


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillDescriptor:
    """Metadata describing an available skill."""

    skill_id: str
    description: str


@dataclass(frozen=True)
class SkillResult:
    """Result of executing a skill."""

    success: bool
    output: Any


@typing.runtime_checkable
class SkillsCapability(CapabilityInterface, typing.Protocol):
    """Capability to list and execute runtime-provided skills."""

    async def list(self) -> list[SkillDescriptor]:
        """Return the list of skills available through the runtime."""
        ...

    async def execute(self, skill_id: str, args: dict[str, Any]) -> SkillResult:
        """Execute the named skill with the provided arguments."""
        ...


# ---------------------------------------------------------------------------
# Chat Stream — HOS-005 extension
# ---------------------------------------------------------------------------


@typing.runtime_checkable
class ChatStreamCapability(CapabilityInterface, typing.Protocol):
    """Optional capability to stream chat responses token by token.

    A runtime that supports streaming should also implement
    :class:`ChatCapability` for non-streaming consumption — the two
    protocols are independent so existing consumers are never broken.

    Implementations **must** yield empty strings as heartbeat / keep-alive
    tokens so the consumer can distinguish "still thinking" from a
    terminal error.
    """

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> typing.AsyncIterator[str]:
        """Stream the model response token by token.

        Args:
            messages: Conversation history (same format as
                :meth:`ChatCapability.chat`).
            runtime_ctx: Optional runtime context.

        Yields:
            Response tokens as they become available.
        """
        ...
        # This ``yield`` makes the return type an async generator.
        # It is never reached at runtime — it exists solely to satisfy
        # the ``typing.AsyncIterator[str]`` return annotation so that
        # a **protocol** (not an ABC) can declare an async generator
        # signature without forcing implementations to import extra
        # machinery.
        # See https://peps.python.org/pep-0544/#methods.
        yield  # type: ignore[return-value]
