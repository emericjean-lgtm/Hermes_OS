"""Runtime Abstraction Layer — runtime execution router (HOS-010).

Provides :class:`RuntimeRouter`, the central execution layer of Hermes OS.
The router resolves the best runtime for a requested capability, using the
active runtime first and falling back to :class:`~backend.ral.runtime_selector.RuntimeSelector`.

No code in this module depends on Ollama, Hermes Agent, or any concrete
backend. It only speaks the :class:`RuntimeInterface` / capability protocols.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.ral.capabilities import ChatCapability, ChatResponse, ToolsCapability, ToolResult
from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_health import RuntimeHealthMonitor, RuntimeHealthStatus
from backend.ral.runtime_selector import RuntimeSelector


class RuntimeExecutionError(Exception):
    """Raised when a runtime execution request cannot be fulfilled."""


class RuntimeRouter:
    """Route execution requests to the most appropriate available runtime.

    The router implements a deterministic resolution strategy:

    1. **Active runtime** — if an active runtime is set, healthy, and
       exposes the requested capability, use it.
    2. **Fallback runtime** — if ``allow_fallback`` is true and a fallback
       name is configured, try that runtime when the active one is unusable.
    3. **Explicit preference** — if ``preferred_name`` is given and the
       runtime is healthy and capable, use it.
    4. **Selector** — delegate to :class:`RuntimeSelector` to find a
       capable, healthy runtime.

    Args:
        context: The active runtime context (active + fallback pointers).
        selector: The capability-aware runtime selector.
    """

    def __init__(
        self,
        context: ActiveRuntimeContext,
        selector: RuntimeSelector,
        *,
        health_monitor: Optional[RuntimeHealthMonitor] = None,
    ) -> None:
        self._context = context
        self._selector = selector
        self._health_monitor = health_monitor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
        preferred_name: str | None = None,
        preference: str | None = None,
        allow_fallback: bool = True,
    ) -> ChatResponse:
        """Execute a chat request on the best available runtime.

        Args:
            messages: Conversation history.
            runtime_ctx: Optional runtime context forwarded to the
                capability implementation.
            preferred_name: Optional runtime name to try first.
            preference: Optional deployment hint (e.g. ``"local"``,
                ``"cloud"``).
            allow_fallback: Whether to try the configured fallback runtime
                when the active runtime is unavailable.

        Returns:
            The chat response from the selected runtime.

        Raises:
            RuntimeExecutionError: If no runtime can handle the request or
                the capability is missing on the selected runtime.
        """
        runtime = self._resolve_runtime(
            "chat",
            preferred_name=preferred_name,
            preference=preference,
            allow_fallback=allow_fallback,
        )
        cap = self._get_capability(runtime, "chat", ChatCapability)
        return await cap.chat(messages, runtime_ctx=runtime_ctx)

    async def invoke_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        preferred_name: str | None = None,
        preference: str | None = None,
        allow_fallback: bool = True,
    ) -> ToolResult:
        """Execute a tool invocation on the best available runtime.

        Args:
            tool_name: Name of the tool to invoke.
            args: Tool arguments.
            preferred_name: Optional runtime name to try first.
            preference: Optional deployment hint.
            allow_fallback: Whether to try the configured fallback runtime.

        Returns:
            The tool invocation result.

        Raises:
            RuntimeExecutionError: If no runtime can handle the request.
        """
        runtime = self._resolve_runtime(
            "tools",
            preferred_name=preferred_name,
            preference=preference,
            allow_fallback=allow_fallback,
        )
        cap = self._get_capability(runtime, "tools", ToolsCapability)
        return await cap.invoke(tool_name, args)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_runtime(
        self,
        capability: str,
        *,
        preferred_name: str | None = None,
        preference: str | None = None,
        allow_fallback: bool = True,
    ) -> RuntimeInterface:
        """Return the best runtime for ``capability`` following the strategy."""
        # 1. Active runtime, if healthy and capable.
        active = self._try_get_active()
        if active is not None and self._can_handle(active, capability):
            return active

        # 2. Fallback runtime, if allowed.
        if allow_fallback:
            fallback = self._try_get_fallback()
            if fallback is not None and self._can_handle(fallback, capability):
                return fallback

        # 3. Explicit preferred runtime.
        if preferred_name is not None:
            preferred = self._try_get_runtime(preferred_name)
            if preferred is not None and self._can_handle(preferred, capability):
                return preferred

        # 4. Capability-aware selector, with an extra pass through the
        #    health monitor to skip unavailable or error-prone runtimes.
        try:
            selected = self._selector.select(
                capability,
                preference=preference,
                preferred_name=preferred_name,
            )
        except Exception as exc:
            raise RuntimeExecutionError(
                f"No runtime available for capability '{capability}'."
            ) from exc

        if self._can_handle(selected, capability):
            return selected

        # The selector's pick did not survive health checks; try the rest
        # of the compatible runtimes in registry order.
        for candidate in self._selector.list_compatible(
            capability, preference=preference
        ):
            if candidate is selected:
                continue
            if self._can_handle(candidate, capability):
                return candidate

        raise RuntimeExecutionError(
            f"No runtime available for capability '{capability}'."
        )

    def _try_get_active(self) -> RuntimeInterface | None:
        """Return the active runtime, or ``None`` if none is set."""
        try:
            return self._context.active_runtime
        except RuntimeError:
            return None

    def _try_get_fallback(self) -> RuntimeInterface | None:
        """Return the configured fallback runtime, if any."""
        name = self._context.fallback_name
        if name is None:
            return None
        try:
            return self._context.registry.get(name)
        except KeyError:
            return None

    def _try_get_runtime(self, name: str) -> RuntimeInterface | None:
        """Return a runtime by name, or ``None`` if not registered."""
        try:
            return self._context.registry.get(name)
        except KeyError:
            return None

    def _can_handle(self, runtime: RuntimeInterface, capability: str) -> bool:
        """Return ``True`` if ``runtime`` is healthy and exposes ``capability``."""
        if not RuntimeLifecycle.health_check(runtime):
            return False
        if runtime.capabilities is None:
            return False
        if capability not in runtime.capabilities.available:
            return False

        # HOS-011: honour the health monitor if provided.
        if self._health_monitor is not None:
            name = self._name_of(runtime)
            if name is not None:
                if not self._health_monitor.is_available(name):
                    return False
                if self._health_monitor.is_error_prone(name):
                    return False

        return True

    def _name_of(self, runtime: RuntimeInterface) -> str | None:
        """Reverse-resolve the registry name of a runtime instance."""
        return self._context.registry.find_name(runtime)

    def _get_capability(
        self,
        runtime: RuntimeInterface,
        capability_name: str,
        capability_type: type,
    ) -> Any:
        """Retrieve a typed capability from ``runtime``.

        Raises:
            RuntimeExecutionError: If the runtime does not expose the
                requested capability.
        """
        instance = runtime.get(capability_name)
        if instance is None:
            raise RuntimeExecutionError(
                f"Runtime '{runtime.name}' does not expose capability '{capability_name}'."
            )
        if not isinstance(instance, capability_type):
            raise RuntimeExecutionError(
                f"Runtime '{runtime.name}' capability '{capability_name}' "
                f"does not satisfy {capability_type.__name__}."
            )
        return instance
