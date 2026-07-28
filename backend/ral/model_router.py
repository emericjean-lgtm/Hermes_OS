"""Runtime Abstraction Layer — model routing contract.

This module defines the interface used by Hermes OS to decide which
runtime, provider, and model should handle a given task. The decision
relies on a structured request and a routing context (cost, VRAM,
capabilities, user preferences, project context).

No implementation is provided here; concrete routers are introduced by
HOS-006c.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRequest:
    """Description of the task to be routed.

    Attributes:
        task_type: High-level task category (e.g. ``"chat"``, ``"code"``).
        context_size: Estimated size of the context window required.
        priority: Integer priority (higher means more urgent).
        required_capabilities: Set of capability names the target must support.
        preferred_runtime: Optional runtime name requested by the caller.
    """

    task_type: str
    context_size: int
    priority: int
    required_capabilities: frozenset[str]
    preferred_runtime: str | None


@dataclass(frozen=True)
class RoutingContext:
    """Context and constraints used during routing.

    Attributes:
        available_runtimes: Names of runtimes currently registered.
        cost_budget: Optional maximum acceptable cost.
        vram_budget: Optional maximum acceptable VRAM in bytes/MiB/GiB.
        user_prefs: Free-form user preferences.
        project_context: Free-form project-level context.
    """

    available_runtimes: list[str]
    cost_budget: float | None
    vram_budget: float | None
    user_prefs: dict[str, typing.Any]
    project_context: dict[str, typing.Any]


@dataclass(frozen=True)
class DecisionStep:
    """One step in the routing evaluation (alternate or rejected option)."""

    runtime: str
    score: float
    reason: str


@dataclass(frozen=True)
class DecisionPath:
    """Explainability trace of the final routing decision."""

    evaluated_runtimes: list[str]
    filters_applied: list[str]


@dataclass(frozen=True)
class ModelDecision:
    """Final outcome of the Model Router.

    Attributes:
        runtime: Selected runtime name.
        provider: Selected provider name (e.g. ``"ollama"``, ``"openai"``).
        model_id: Selected model identifier.
        score: Final score assigned by the router.
        confidence: Confidence level in the decision (0.0 to 1.0).
        decision_path: Trace explaining how the decision was reached.
        alternatives: Other options considered, if any.
    """

    runtime: str
    provider: str
    model_id: str
    score: float
    confidence: float
    decision_path: DecisionPath
    alternatives: list[DecisionStep]


@typing.runtime_checkable
class ModelRouterInterface(typing.Protocol):
    """Contract for the Hermes OS model router."""

    async def decide(self, request: TaskRequest) -> ModelDecision:
        """Select the best runtime/provider/model for ``request``.

        The decision must be deterministic and explainable through the
        :attr:`ModelDecision.decision_path` field.
        """
        ...
