"""Runtime Abstraction Layer — runtime execution router (HOS-010 / HOS-012).

Provides :class:`RuntimeRouter`, the central execution layer of Hermes OS.
The router resolves the best runtime for a requested capability, uses the
active runtime first, and supports automatic failover via
:class:`~backend.ral.runtime_recovery.RuntimeRecoveryManager`.

No code in this module depends on Ollama, Hermes Agent, or any concrete
backend. It only speaks the :class:`RuntimeInterface` / capability protocols.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from backend.ral.capabilities import ChatCapability, ChatResponse, ToolsCapability, ToolResult
from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_health import RuntimeHealthMonitor
from backend.ral.runtime_events import RuntimeEvent, RuntimeEventBus, RuntimeEventType, Severity
from backend.ral.runtime_recovery import ExecutionTrace, RuntimeRecoveryManager
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

    When a ``recovery_manager`` is provided, the router transparently
    retries failed executions on alternative runtimes and enriches the
    result metadata with an :class:`ExecutionTrace`.

    Args:
        context: The active runtime context (active + fallback pointers).
        selector: The capability-aware runtime selector.
        health_monitor: Optional health monitor used to filter runtimes.
        recovery_manager: Optional recovery/failover manager.
        max_retries: Maximum number of fallback attempts after the first
            runtime fails.
    """

    def __init__(
        self,
        context: ActiveRuntimeContext,
        selector: RuntimeSelector,
        *,
        health_monitor: Optional[RuntimeHealthMonitor] = None,
        recovery_manager: Optional[RuntimeRecoveryManager] = None,
        event_bus: Optional[RuntimeEventBus] = None,
        max_retries: int = 2,
    ) -> None:
        self._context = context
        self._selector = selector
        self._health_monitor = health_monitor
        self._recovery_manager = recovery_manager
        self._event_bus = event_bus
        self._max_retries = max(max_retries, 0)

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
            The chat response from the selected runtime. The response
            ``metadata`` contains an ``execution_trace`` entry describing
            any fallback / retry that occurred.

        Raises:
            RuntimeExecutionError: If no runtime can handle the request.
        """
        result, trace = await self._execute_with_recovery(
            "chat",
            lambda runtime: self._get_chat_call(runtime, messages, runtime_ctx),
            preferred_name=preferred_name,
            preference=preference,
            allow_fallback=allow_fallback,
        )
        if self._recovery_manager is not None:
            return ChatResponse(
                content=result.content,
                metadata={**result.metadata, "execution_trace": trace.as_dict()},
            )
        return result

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
            The tool invocation result. The result ``metadata`` contains
            an ``execution_trace`` entry describing any fallback / retry.

        Raises:
            RuntimeExecutionError: If no runtime can handle the request.
        """
        result, trace = await self._execute_with_recovery(
            "tools",
            lambda runtime: self._get_tool_call(runtime, tool_name, args),
            preferred_name=preferred_name,
            preference=preference,
            allow_fallback=allow_fallback,
        )
        if self._recovery_manager is not None:
            return ToolResult(
                output=result.output,
                is_error=result.is_error,
                metadata={**result.metadata, "execution_trace": trace.as_dict()},
            )
        return result

    # ------------------------------------------------------------------
    # Event publication helper
    # ------------------------------------------------------------------

    def _publish(
        self,
        event_type: str,
        runtime_name: str,
        *,
        severity: Severity | str = Severity.INFO,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Publish a runtime event if an event bus was provided."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            RuntimeEvent(
                event_type=event_type,
                runtime_name=runtime_name,
                severity=severity,
                message=message,
                metadata=metadata or {},
            )
        )

    # ------------------------------------------------------------------
    # Capability helpers
    # ------------------------------------------------------------------

    async def _get_chat_call(
        self,
        runtime: RuntimeInterface,
        messages: list[dict[str, Any]],
        runtime_ctx: dict[str, Any] | None,
    ) -> ChatResponse:
        cap = self._get_capability(runtime, "chat", ChatCapability)
        return await cap.chat(messages, runtime_ctx=runtime_ctx)

    async def _get_tool_call(
        self,
        runtime: RuntimeInterface,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolResult:
        cap = self._get_capability(runtime, "tools", ToolsCapability)
        return await cap.invoke(tool_name, args)

    # ------------------------------------------------------------------
    # Recovery execution loop
    # ------------------------------------------------------------------

    async def _execute_with_recovery(
        self,
        capability: str,
        executor: Any,
        *,
        preferred_name: str | None = None,
        preference: str | None = None,
        allow_fallback: bool = True,
    ) -> tuple[Any, ExecutionTrace]:
        """Execute ``executor`` with optional retry / failover.

        Returns:
            A tuple ``(result, execution_trace)``.
        """
        attempted: set[str] = set()
        runtime_initial: str | None = None
        retries = 0
        fallback_reason: str | None = None
        last_error: BaseException | None = None

        while retries <= self._max_retries:
            try:
                runtime = self._resolve_runtime(
                    capability,
                    exclude=attempted,
                    preferred_name=preferred_name,
                    preference=preference,
                    allow_fallback=allow_fallback,
                )
            except RuntimeExecutionError as exc:
                # No more runtimes to try.
                raise RuntimeExecutionError(
                    f"No runtime available for capability '{capability}' "
                    f"after {retries} retry attempt(s)."
                ) from exc

            runtime_name = self._name_of(runtime)
            if runtime_name is None:
                raise RuntimeExecutionError(
                    f"Resolved runtime does not belong to the registry."
                )

            if runtime_initial is None:
                runtime_initial = runtime_name

            self._publish(
                RuntimeEventType.SELECTED,
                runtime_name,
                metadata={"capability": capability},
            )
            self._publish(
                RuntimeEventType.STARTED,
                runtime_name,
                metadata={"capability": capability},
            )

            start = time.monotonic()
            try:
                result = await executor(runtime)
                latency_ms = int((time.monotonic() - start) * 1000)
                self._publish(
                    RuntimeEventType.COMPLETED,
                    runtime_name,
                    metadata={"capability": capability, "latency_ms": latency_ms},
                )
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                last_error = exc
                self._publish(
                    RuntimeEventType.FAILED,
                    runtime_name,
                    severity=Severity.ERROR,
                    message=str(exc),
                    metadata={"capability": capability, "latency_ms": latency_ms},
                )
                if self._recovery_manager is not None:
                    fallback_reason = self._recovery_manager.recover(runtime_name, exc)
                attempted.add(runtime_name)
                retries += 1
                if retries <= self._max_retries:
                    self._publish(
                        RuntimeEventType.FALLBACK,
                        runtime_name,
                        severity=Severity.WARNING,
                        metadata={
                            "capability": capability,
                            "attempt": retries,
                            "reason": fallback_reason,
                        },
                    )
                continue

            if self._recovery_manager is not None:
                self._recovery_manager.record_success(runtime_name)

            if runtime_name != runtime_initial:
                self._publish(
                    RuntimeEventType.RECOVERED,
                    runtime_name,
                    severity=Severity.INFO,
                    metadata={
                        "capability": capability,
                        "runtime_initial": runtime_initial,
                        "runtime_final": runtime_name,
                    },
                )

            trace = ExecutionTrace(
                runtime_initial=runtime_initial,
                runtime_final=runtime_name,
                retries=max(0, retries),
                fallback_reason=fallback_reason,
            )
            return result, trace

        raise RuntimeExecutionError(
            f"Execution failed for capability '{capability}' after "
            f"{self._max_retries} fallback attempt(s)."
        ) from last_error

    # ------------------------------------------------------------------
    # Runtime resolution
    # ------------------------------------------------------------------

    def _resolve_runtime(
        self,
        capability: str,
        *,
        exclude: Optional[set[str]] = None,
        preferred_name: str | None = None,
        preference: str | None = None,
        allow_fallback: bool = True,
    ) -> RuntimeInterface:
        """Return the best runtime for ``capability`` following the strategy."""
        exclude = exclude or set()

        # 1. Active runtime, if healthy and capable.
        active = self._try_get_active()
        if active is not None:
            active_name = self._context.get_active_name()
            if active_name not in exclude and self._can_handle(active, capability):
                return active

        # 2. Fallback runtime, if allowed.
        if allow_fallback:
            fallback = self._try_get_fallback()
            if fallback is not None:
                fallback_name = self._context.fallback_name
                if fallback_name is not None and fallback_name not in exclude:
                    if self._can_handle(fallback, capability):
                        return fallback

        # 3. Explicit preferred runtime.
        if preferred_name is not None and preferred_name not in exclude:
            preferred = self._try_get_runtime(preferred_name)
            if preferred is not None and self._can_handle(preferred, capability):
                return preferred

        # 4. Capability-aware selector, with an extra pass through the
        #    health/recovery monitors to skip bad runtimes.
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

        selected_name = self._name_of(selected)
        if (selected_name not in exclude) and self._can_handle(selected, capability):
            return selected

        # The selector's pick did not survive checks; try the rest of the
        # compatible runtimes in registry order.
        for candidate in self._selector.list_compatible(
            capability, preference=preference
        ):
            candidate_name = self._name_of(candidate)
            if candidate_name in exclude:
                continue
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

        name = self._name_of(runtime)
        if name is None:
            return False

        # HOS-011: honour the health monitor if provided.
        if self._health_monitor is not None:
            if not self._health_monitor.is_available(name):
                return False
            if self._health_monitor.is_error_prone(name):
                return False

        # HOS-012: honour the recovery manager (circuit breaker).
        if self._recovery_manager is not None:
            if not self._recovery_manager.should_retry(name):
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
