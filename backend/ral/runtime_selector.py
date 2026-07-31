"""Runtime Abstraction Layer — runtime selection (HOS-009).

Provides :class:`RuntimeSelector`, a capability-aware runtime picker
built on top of :class:`~backend.ral.runtime_registry.RuntimeRegistry`.

The selector uses a small set of **extensible rules** (plain callable
predicates) so that future PRs can add routing criteria without touching
the core selection algorithm.

HOS-009 deliberately keeps the rules simple: the goal is the *foundation*
of runtime selection, not an AI router. Complex routing decisions will be
layered on top of this foundation in later PRs.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_registry import RuntimeRegistry

if TYPE_CHECKING:
    pass  # for future typing imports


class RuntimeSelectionError(Exception):
    """Raised when no runtime satisfies the requested selection criteria."""


SelectionRule = Callable[[RuntimeInterface], bool]


def _has_capability(capability: str) -> SelectionRule:
    """Return a rule that accepts runtimes advertising *capability*."""

    def rule(runtime: RuntimeInterface) -> bool:
        if runtime.capabilities is None:
            return False
        return capability in runtime.capabilities.available

    return rule


def _is_healthy() -> SelectionRule:
    """Return a rule that accepts only currently healthy runtimes."""

    def rule(runtime: RuntimeInterface) -> bool:
        return RuntimeLifecycle.health_check(runtime)

    return rule


def _preference_tag(tag: str) -> SelectionRule:
    """Return a rule that accepts runtimes whose ``name`` contains *tag*.

    .. note::
        This is the minimal HOS-009 interpretation of "local/cloud
        preference". Future PRs may replace it with a richer metadata
        field on ``RuntimeInterface`` without changing the selector API.
    """

    def rule(runtime: RuntimeInterface) -> bool:
        return tag.lower() in runtime.name.lower()

    return rule


class RuntimeSelector:
    """Select a runtime from a registry using extensible rules.

    Args:
        registry: The registry to query.  The selector does not take
            ownership of the registry; it only reads from it.
    """

    def __init__(self, registry: RuntimeRegistry) -> None:
        self._registry = registry

    def select(
        self,
        capability: str,
        *,
        preference: str | None = None,
        preferred_name: str | None = None,
    ) -> RuntimeInterface:
        """Select the best runtime for the requested criteria.

        Priority:

        1. If ``preferred_name`` is provided and that runtime is registered,
           healthy, and advertises ``capability``, return it.
        2. Otherwise, among all registered runtimes, pick the first one
           that is healthy, advertises ``capability``, and matches the
           optional ``preference``.

        Args:
            capability: Required capability (e.g. ``"chat"``).
            preference: Optional deployment hint such as ``"local"`` or
                ``"cloud"``.  Defaults to ``None``.
            preferred_name: Optional runtime name to try first.

        Returns:
            A runtime satisfying all applicable rules.

        Raises:
            RuntimeSelectionError: If no runtime matches the criteria.
        """
        # Priority 1: explicit preferred runtime.
        if preferred_name is not None:
            try:
                runtime = self._registry.get(preferred_name)
            except KeyError as exc:
                raise RuntimeSelectionError(
                    f"Preferred runtime '{preferred_name}' is not registered."
                ) from exc
            if _has_capability(capability)(runtime) and _is_healthy()(runtime):
                return runtime

        # Priority 2: build rule chain and evaluate all registered runtimes.
        rules: list[SelectionRule] = [
            _has_capability(capability),
            _is_healthy(),
        ]
        if preference is not None:
            rules.append(_preference_tag(preference))

        candidates = [self._registry.get(name) for name in self._registry.list_available()]

        for candidate in candidates:
            if all(rule(candidate) for rule in rules):
                return candidate

        detail = (
            f"No runtime available for capability '{capability}'"
            f"{f' with preference {preference!r}' if preference else ''}."
        )
        raise RuntimeSelectionError(detail)

    def list_compatible(
        self,
        capability: str,
        *,
        preference: str | None = None,
    ) -> list[RuntimeInterface]:
        """Return all runtimes that satisfy the requested criteria.

        Args:
            capability: Required capability.
            preference: Optional deployment hint.

        Returns:
            A list of matching runtimes, in registry order.
        """
        rules: list[SelectionRule] = [
            _has_capability(capability),
            _is_healthy(),
        ]
        if preference is not None:
            rules.append(_preference_tag(preference))

        candidates = [self._registry.get(name) for name in self._registry.list_available()]
        return [rt for rt in candidates if all(rule(rt) for rule in rules)]
