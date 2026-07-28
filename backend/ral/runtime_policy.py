"""Runtime Abstraction Layer — runtime policy engine (HOS-016).

Provides a declarative policy layer that controls which runtimes may be
used based on context (confidentiality, deployment preference, capability
requirements, etc.).

Policies are evaluated by priority — the highest-priority matching policy
wins — and the engine integrates with :class:`RuntimeDecisionEngine` to
filter out denied runtimes and boost preferred ones.

No concrete backend is contacted. Policies are pure in-memory rules.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


class RuntimePolicyError(Exception):
    """Raised when a policy operation cannot be completed."""


@dataclass(frozen=True)
class RuntimePolicyRule:
    """A single declarative rule within a :class:`RuntimePolicy`.

    All fields are optional. A rule is considered *matching* when every
    non-``None`` field is satisfied by the execution context. An empty
    rule (all ``None``) matches everything.

    Attributes:
        allowed_runtimes: Set of runtime names that are permitted.
        denied_runtimes: Set of runtime names that are forbidden.
        required_capabilities: Set of capability names that the runtime
            must expose.
        local_only: If ``True``, only local runtimes are allowed.
        cloud_allowed: If ``False``, cloud runtimes are forbidden.
        preferred_runtime: Name of the runtime to prefer when applicable.
        preferred_provider: Name of the provider to prefer.
        confidential: If ``True``, only runtimes marked as confidential
            (private) are allowed.
        max_latency_ms: Maximum acceptable average latency.
        min_reliability: Minimum acceptable reliability score (0-100).
        metadata: Free-form metadata attached to the rule.
    """

    allowed_runtimes: Optional[frozenset[str]] = None
    denied_runtimes: Optional[frozenset[str]] = None
    required_capabilities: Optional[frozenset[str]] = None
    local_only: Optional[bool] = None
    cloud_allowed: Optional[bool] = None
    preferred_runtime: Optional[str] = None
    preferred_provider: Optional[str] = None
    confidential: Optional[bool] = None
    max_latency_ms: Optional[float] = None
    min_reliability: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimePolicy:
    """An immutable, versioned policy.

    Policies are evaluated in **priority** order (highest first). A
    matching policy may either allow or deny a runtime. Ties are broken
    by ``name`` (lexicographic).

    Attributes:
        name: Unique policy identifier.
        enabled: Whether the policy is active.
        priority: Evaluation priority (higher = more important).
        description: Human-readable description.
        rules: Non-empty list of rules. All rules must match for the
            policy to apply.
    """

    name: str
    enabled: bool = True
    priority: int = 0
    description: str = ""
    rules: tuple[RuntimePolicyRule, ...] = (RuntimePolicyRule(),)


@dataclass(frozen=True)
class RuntimePolicyResult:
    """Result of evaluating a :class:`RuntimePolicy` against a context.

    Attributes:
        allowed: ``True`` if the runtime is permitted by the policy.
        policy_name: Name of the policy that produced this result.
        rejected_reason: Human-readable reason if ``allowed`` is ``False``.
        preferred_runtime: Suggested runtime name, if any.
        preferred_provider: Suggested provider, if any.
        applied_rules: Number of rules that were evaluated.
        metadata: Free-form metadata.
    """

    allowed: bool = True
    policy_name: str = ""
    rejected_reason: Optional[str] = None
    preferred_runtime: Optional[str] = None
    preferred_provider: Optional[str] = None
    applied_rules: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeExecutionContext:
    """Contextual information for runtime selection.

    Attributes:
        capability: Required capability (e.g. ``"chat"``).
        runtime_name: Name of the runtime being evaluated.
        provider: Provider identifier (e.g. ``"ollama"``, ``"openai"``).
        project_name: Project or tenant identifier.
        confidential: Whether the request contains confidential data.
        user_preference: Optional user preference hint.
        estimated_complexity: Estimated task complexity (0-10).
        avg_latency_ms: Historical average latency of the runtime.
        reliability: Historical reliability score (0-100).
        metadata: Free-form metadata.
    """

    capability: str = ""
    runtime_name: Optional[str] = None
    provider: Optional[str] = None
    project_name: Optional[str] = None
    confidential: Optional[bool] = None
    user_preference: Optional[str] = None
    estimated_complexity: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    reliability: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimePolicyEngine:
    """In-memory, thread-safe policy engine.

    Manages a set of named policies and evaluates them against an
    :class:`RuntimeExecutionContext`. Policies are evaluated in
    descending priority order — the first fully matching policy's
    result is returned.

    Args:
        policies: Optional initial set of policies.
    """

    def __init__(self, policies: Optional[list[RuntimePolicy]] = None) -> None:
        self._policies: dict[str, RuntimePolicy] = {}
        self._lock = threading.Lock()
        if policies:
            for policy in policies:
                self._policies[policy.name] = policy

    def register_policy(self, policy: RuntimePolicy) -> None:
        """Register or update a policy.

        If a policy with the same ``name`` already exists, it is
        overwritten. Otherwise, the policy is registered.

        Args:
            policy: The policy to register.

        Raises:
            RuntimePolicyError: If the policy has no rules.
        """
        if not policy.rules:
            raise RuntimePolicyError(
                f"Policy '{policy.name}' has no rules."
            )
        with self._lock:
            self._policies[policy.name] = policy

    def remove_policy(self, name: str) -> None:
        """Remove a policy by name.

        Args:
            name: Policy identifier.

        Raises:
            RuntimePolicyError: If the policy is not found.
        """
        with self._lock:
            if name not in self._policies:
                raise RuntimePolicyError(f"Policy '{name}' is not registered.")
            del self._policies[name]

    def evaluate(
        self,
        context: RuntimeExecutionContext,
    ) -> RuntimePolicyResult:
        """Evaluate ``context`` against all enabled policies.

        Policies are tested in descending priority. The first policy
        whose **all** rules match determines the result. If no policy
        matches, a default allow result is returned.

        Args:
            context: The execution context to evaluate.

        Returns:
            A :class:`RuntimePolicyResult` indicating whether the
            runtime is allowed and any preferences.
        """
        with self._lock:
            policies = list(self._policies.values())

        enabled = [
            p for p in sorted(policies, key=lambda p: (-p.priority, p.name))
            if p.enabled
        ]

        combined_result = RuntimePolicyResult()
        applied_rules_count = 0

        for policy in enabled:
            policy_allowed = True
            policy_reason = None
            policy_preferred_runtime = None
            policy_preferred_provider = None

            for rule in policy.rules:
                applied_rules_count += 1
                match, reason = self._match_rule(rule, context)
                if not match:
                    policy_allowed = False
                    policy_reason = reason
                    # A rule mismatch blocks this policy entirely.
                    break

                # Collect preference hints from the last matching rule.
                if rule.preferred_runtime is not None:
                    policy_preferred_runtime = rule.preferred_runtime
                if rule.preferred_provider is not None:
                    policy_preferred_provider = rule.preferred_provider

            # The first matching policy wins (highest priority).
            if policy_allowed or policy_reason is not None:
                combined_result = RuntimePolicyResult(
                    allowed=policy_allowed,
                    policy_name=policy.name,
                    rejected_reason=policy_reason,
                    preferred_runtime=policy_preferred_runtime,
                    preferred_provider=policy_preferred_provider,
                    applied_rules=applied_rules_count,
                    metadata={"policy_priority": policy.priority},
                )
                # If the policy denies, stop here.
                if not policy_allowed:
                    break
                # If the policy allows, we still stop (highest priority
                # wins).
                break

        return combined_result

    def list_policies(self) -> list[RuntimePolicy]:
        """Return all registered policies, sorted by descending priority."""
        with self._lock:
            return sorted(
                self._policies.values(),
                key=lambda p: (-p.priority, p.name),
            )

    def clear(self) -> None:
        """Remove **all** registered policies."""
        with self._lock:
            self._policies.clear()

    # ------------------------------------------------------------------
    # Rule matching
    # ------------------------------------------------------------------

    @staticmethod
    def _match_rule(
        rule: RuntimePolicyRule,
        ctx: RuntimeExecutionContext,
    ) -> tuple[bool, Optional[str]]:
        """Check if ``rule`` matches ``ctx``.

        Returns:
            A tuple ``(matches, reason)``. ``reason`` is ``None`` on
            match, or a description of the mismatch.
        """
        # --- allowed_runtimes ---
        if rule.allowed_runtimes is not None:
            if ctx.runtime_name is None or ctx.runtime_name not in rule.allowed_runtimes:
                return False, (
                    f"Runtime '{ctx.runtime_name}' is not in allowed set "
                    f"{sorted(rule.allowed_runtimes)}."
                )

        # --- denied_runtimes ---
        if rule.denied_runtimes is not None:
            if ctx.runtime_name is not None and ctx.runtime_name in rule.denied_runtimes:
                return False, (
                    f"Runtime '{ctx.runtime_name}' is explicitly denied."
                )

        # --- required_capabilities ---
        if rule.required_capabilities is not None:
            if ctx.capability not in rule.required_capabilities:
                return False, (
                    f"Capability '{ctx.capability}' is not in required set "
                    f"{sorted(rule.required_capabilities)}."
                )

        # --- local_only ---
        if rule.local_only is True:
            if ctx.provider is not None and "cloud" in ctx.provider.lower():
                return False, (
                    f"Provider '{ctx.provider}' is not local."
                )

        # --- cloud_allowed ---
        if rule.cloud_allowed is False:
            if ctx.provider is not None and "cloud" not in ctx.provider.lower():
                return False, (
                    f"Cloud providers are disallowed by policy."
                )

        # --- confidential ---
        if rule.confidential is True:
            if ctx.confidential is not True:
                return False, (
                    "Runtime does not support confidential processing."
                )

        # --- max_latency_ms ---
        if rule.max_latency_ms is not None:
            if ctx.avg_latency_ms is not None and ctx.avg_latency_ms > rule.max_latency_ms:
                return False, (
                    f"Average latency {ctx.avg_latency_ms:.0f}ms exceeds "
                    f"maximum {rule.max_latency_ms:.0f}ms."
                )

        # --- min_reliability ---
        if rule.min_reliability is not None:
            if ctx.reliability is not None and ctx.reliability < rule.min_reliability:
                return False, (
                    f"Reliability {ctx.reliability:.0f}/100 is below "
                    f"minimum {rule.min_reliability:.0f}/100."
                )

        return True, None
