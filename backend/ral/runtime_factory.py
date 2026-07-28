"""Runtime Abstraction Layer — runtime factory & lifecycle (HOS-007).

This module provides:

* :class:`RuntimeFactory`: a registry of builder functions that create
  concrete runtime adapters without importing them.
* :class:`RuntimeLifecycle`: a lightweight helper that maps the generic
  lifecycle verbs ``initialize``, ``health_check``, and ``shutdown`` onto
  the existing :class:`RuntimeInterface` methods. This keeps
  :class:`RuntimeInterface` unchanged and fully backward-compatible.

The factory contains **no business logic** and **no hard-coded runtime
imports**. Concrete adapters are registered as builder callables, keeping
Hermes OS decoupled from any particular runtime (Ollama, OpenAI,
Anthropic, vLLM, etc.).
"""

from __future__ import annotations

from typing import Any, Callable

from backend.ral.runtime import RuntimeInterface, RuntimeStatus
from backend.ral.runtime_registry import RuntimeRegistry

RuntimeBuilder = Callable[..., RuntimeInterface]


class RuntimeFactory:
    """Factory that creates runtime adapters from registered builders.

    The factory stores builder callables keyed by a runtime type name.
    Each builder receives keyword arguments and returns an object that
    satisfies :class:`RuntimeInterface`. This design avoids importing any
    concrete adapter inside the factory.
    """

    def __init__(self, registry: RuntimeRegistry | None = None) -> None:
        """Initialize the factory with an fresh builder registry.

        Args:
            registry: Optional :class:`RuntimeRegistry` used to store
                created runtimes automatically. If ``None``, the factory
                does not keep references to the runtimes it creates.
        """
        self._builders: dict[str, RuntimeBuilder] = {}
        self._registry = registry

    def register_builder(
        self,
        runtime_type: str,
        builder: RuntimeBuilder,
    ) -> None:
        """Register ``builder`` as the factory for ``runtime_type``.

        Args:
            runtime_type: Canonical runtime type name (e.g. ``"ollama"``,
                ``"openai"``).
            builder: Callable that returns a :class:`RuntimeInterface`
                instance when called with the appropriate arguments.
        """
        self._builders[runtime_type] = builder

    def create(self, runtime_type: str, **kwargs: Any) -> RuntimeInterface:
        """Create a runtime of type ``runtime_type`` using its builder.

        Args:
            runtime_type: Runtime type name.
            **kwargs: Arguments forwarded to the registered builder.

        Returns:
            A runtime instance satisfying :class:`RuntimeInterface`.

        Raises:
            ValueError: If ``runtime_type`` is not registered.
        """
        if runtime_type not in self._builders:
            raise ValueError(
                f"Unknown runtime type '{runtime_type}'. "
                f"Available types: {self.available_types()}"
            )
        runtime = self._builders[runtime_type](**kwargs)
        if self._registry is not None:
            self._registry.register(runtime_type, runtime)
        return runtime

    def available_types(self) -> list[str]:
        """Return the list of registered runtime type names.

        Returns:
            A sorted list of runtime type names.
        """
        return sorted(self._builders.keys())


class RuntimeLifecycle:
    """Lifecycle helper mapping generic verbs to :class:`RuntimeInterface`.

    This class is purely additive: it does not modify the Protocol and
    works with any runtime that already implements ``start``, ``stop``,
    and exposes ``status``.
    """

    @staticmethod
    async def initialize(runtime: RuntimeInterface) -> None:
        """Initialize ``runtime`` (maps to :meth:`RuntimeInterface.start`)."""
        await runtime.start()

    @staticmethod
    def health_check(runtime: RuntimeInterface) -> bool:
        """Return ``True`` if ``runtime`` is started and healthy.

        The current definition considers a runtime healthy when its
        ``status`` is :attr:`RuntimeStatus.STARTED`. Future implementations
        may perform deeper checks without changing this interface.
        """
        return runtime.status == RuntimeStatus.STARTED

    @staticmethod
    async def shutdown(runtime: RuntimeInterface) -> None:
        """Shut down ``runtime`` (maps to :meth:`RuntimeInterface.stop`)."""
        await runtime.stop()
