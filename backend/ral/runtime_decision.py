"""Runtime Abstraction Layer — adaptive runtime decision engine (HOS-015).

Composes the outputs of HOS-009 through HOS-014 (registry, selector,
health monitor, performance analyzer, recovery manager) into a single,
explainable decision about which runtime should handle a request.

No concrete backend (Ollama, cloud, etc.) is contacted. All data comes
from the existing RAL abstractions.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.ral.runtime_health import RuntimeHealthMonitor
from backend.ral.runtime_performance import RuntimePerformanceAnalyzer
from backend.ral.runtime_policy import RuntimeExecutionContext, RuntimePolicyEngine
from backend.ral.runtime_recovery import RuntimeRecoveryManager
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector


class RuntimeDecisionError(Exception):
    """Raised when the decision engine cannot resolve a runtime."""


@dataclass(frozen=True)
class RuntimeDecisionScore:
    """Decomposed score for a single runtime candidate.

    Attributes:
        runtime_name: Identifier of the evaluated runtime.
        final_score: Weighted composite score (0-1000).
        health_score: Score derived from health status (0-200).
        reliability_score: Score derived from reliability metrics (0-250).
        performance_score: Score derived from performance metrics (0-200).
        capability_score: Score for capability match (0-150).
        policy_score: Score for preference/policy alignment (0-100).
        circuit_penalty: Penalty for open circuit breaker (0-100).
        metadata: Free-form key-value payload with evaluation details.
    """

    runtime_name: str
    final_score: float = 0.0
    health_score: float = 0.0
    reliability_score: float = 0.0
    performance_score: float = 0.0
    capability_score: float = 0.0
    policy_score: float = 0.0
    circuit_penalty: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeDecision:
    """Immutable result of a runtime selection decision.

    Attributes:
        selected_runtime: Name of the selected runtime.
        confidence: Normalised confidence in the decision (0.0-1.0).
        decision_score: Weighted composite score of the selected runtime.
        decision_reason: Human-readable explanation of the decision.
        candidate_scores: Scores for all evaluated candidates, sorted.
        timestamp: Unix timestamp of when the decision was made.
    """

    selected_runtime: str
    confidence: float = 0.0
    decision_score: float = 0.0
    decision_reason: str = ""
    candidate_scores: tuple[RuntimeDecisionScore, ...] = ()
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class RuntimeDecisionWeights:
    """Configurable weights for the composite decision score.

    All weights are applied as multiplicative factors. The defaults are
    chosen to prioritise health and reliability, then performance, then
    policy preferences.

    Attributes:
        health_weight: Weight applied to the health score.
        performance_weight: Weight applied to the performance score.
        reliability_weight: Weight applied to the reliability score.
        capability_weight: Weight applied to the capability score.
        policy_weight: Weight applied to the policy/preference score.
        circuit_penalty_weight: Weight applied to the circuit penalty.
    """

    health_weight: float = 1.0
    performance_weight: float = 1.0
    reliability_weight: float = 1.0
    capability_weight: float = 1.0
    policy_weight: float = 1.0
    circuit_penalty_weight: float = 1.0


class RuntimeDecisionEngine:
    """Composite runtime decision engine using HOS-009 to HOS-014.

    The engine queries the registered runtimes, evaluates each one against
    health, reliability, performance, capability and policy criteria, then
    produces a ranked decision with an accompanying explanation.

    Args:
        registry: Registry of available runtime instances.
        selector: Capability-aware runtime selector.
        health_monitor: Health monitor for runtime health status.
        performance_analyzer: Performance analyzer for reliability and
            performance scores.
        recovery_manager: Recovery manager for circuit breaker state.
        weights: Optional custom weights. Defaults to standard weights.
    """

    def __init__(
        self,
        registry: RuntimeRegistry,
        selector: RuntimeSelector,
        health_monitor: RuntimeHealthMonitor,
        performance_analyzer: RuntimePerformanceAnalyzer,
        recovery_manager: RuntimeRecoveryManager,
        *,
        weights: Optional[RuntimeDecisionWeights] = None,
        policy_engine: Optional[RuntimePolicyEngine] = None,
    ) -> None:
        self._registry = registry
        self._selector = selector
        self._health_monitor = health_monitor
        self._performance_analyzer = performance_analyzer
        self._recovery_manager = recovery_manager
        self._policy_engine = policy_engine
        self._weights = weights or RuntimeDecisionWeights()
        self._lock = threading.Lock()

    def set_weights(self, weights: RuntimeDecisionWeights) -> None:
        """Replace the weight configuration at runtime.

        Args:
            weights: New weight configuration.
        """
        with self._lock:
            self._weights = weights

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_runtime(
        self,
        capability: str,
        *,
        preference: Optional[str] = None,
        preferred_name: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> RuntimeDecision:
        """Select the best runtime for ``capability``.

        The engine evaluates every registered runtime that matches the
        capability, ranks them by composite score, and returns the best
        candidate with an explanation.

        Args:
            capability: Required capability identifier.
            preference: Optional deployment hint (``"local"``, ``"cloud"``).
            preferred_name: Optional runtime name to boost in scoring.
            min_confidence: Minimum confidence threshold. If the best
                candidate does not meet this threshold, a
                :class:`RuntimeDecisionError` is raised.

        Returns:
            A :class:`RuntimeDecision` detailing the selection.

        Raises:
            RuntimeDecisionError: If no candidate meets the requirements
                or the confidence threshold.
        """
        candidates = self.rank_candidates(
            capability,
            preference=preference,
            preferred_name=preferred_name,
        )

        if not candidates:
            raise RuntimeDecisionError(
                f"No candidate runtime available for capability '{capability}'"
                f"{f' with preference {preference!r}' if preference else ''}."
            )

        best = candidates[0]

        # Calculate confidence as the ratio of the best score to the
        # theoretical maximum (1000) or to the second-best score.
        if len(candidates) > 1 and candidates[1].final_score > 0:
            confidence = best.final_score / max(candidates[1].final_score, 1.0)
            confidence = min(confidence / 2.0, 1.0)  # normalise
        else:
            confidence = best.final_score / 1000.0 if best.final_score > 0 else 0.0

        if confidence < min_confidence:
            raise RuntimeDecisionError(
                f"Best candidate '{best.runtime_name}' (score={best.final_score:.1f}) "
                f"does not meet minimum confidence threshold {min_confidence:.2f}."
            )

        decision = RuntimeDecision(
            selected_runtime=best.runtime_name,
            confidence=min(confidence, 1.0),
            decision_score=best.final_score,
            decision_reason=self.explain_decision(best, candidates),
            candidate_scores=tuple(candidates),
        )
        return decision

    def _build_context(
        self,
        runtime_name: str,
        capability: str,
        *,
        preference: Optional[str] = None,
        preferred_name: Optional[str] = None,
    ) -> RuntimeExecutionContext:
        """Build an execution context for policy evaluation."""
        perf = self._performance_analyzer.get_metrics(runtime_name)
        provider = None
        if preference is not None:
            if preference.lower() == "local":
                provider = "local"
            elif preference.lower() == "cloud":
                provider = "cloud"
        return RuntimeExecutionContext(
            capability=capability,
            runtime_name=runtime_name,
            provider=provider,
            avg_latency_ms=perf.avg_latency_ms if perf.executions > 0 else None,
            reliability=perf.reliability_score,
        )

    def evaluate_runtime(
        self,
        runtime_name: str,
        capability: str,
        *,
        preference: Optional[str] = None,
        preferred_name: Optional[str] = None,
    ) -> RuntimeDecisionScore:
        """Evaluate a single runtime and return its decomposed score.

        Args:
            runtime_name: Name of the runtime to evaluate.
            capability: Required capability identifier.
            preference: Optional deployment hint.
            preferred_name: Optional preferred runtime name (used only
                for policy scoring against this runtime).

        Returns:
            A :class:`RuntimeDecisionScore` with the decomposed scores.

        Raises:
            RuntimeDecisionError: If the runtime is not registered.
        """
        try:
            runtime = self._registry.get(runtime_name)
        except KeyError as exc:
            raise RuntimeDecisionError(
                f"Runtime '{runtime_name}' is not registered."
            ) from exc

        # --- Policy evaluation first (HOS-016) ---
        policy_allowed = True
        policy_reason: Optional[str] = None
        policy_preferred: Optional[str] = None
        if self._policy_engine is not None:
            ctx = self._build_context(
                runtime_name, capability,
                preference=preference,
                preferred_name=preferred_name,
            )
            policy_result = self._policy_engine.evaluate(ctx)
            if not policy_result.allowed:
                raise RuntimeDecisionError(
                    f"Runtime '{runtime_name}' rejected by policy "
                    f"'{policy_result.policy_name}': {policy_result.rejected_reason}"
                )
            policy_allowed = policy_result.allowed
            policy_preferred = policy_result.preferred_runtime
            policy_reason = policy_result.rejected_reason

        w = self._weights
        meta: dict[str, Any] = {}
        if policy_preferred is not None:
            meta["policy_preferred"] = policy_preferred
        if policy_reason is not None:
            meta["policy_reason"] = policy_reason

        # --- Health score (0-200) ---
        try:
            health_status = self._health_monitor.check_runtime(runtime_name)
        except Exception as exc:
            meta["health_error"] = str(exc)
            health_status = "unknown"

        meta["health_status"] = health_status

        if health_status == "available":
            health_score = 200.0
        elif health_status == "degraded":
            health_score = 80.0
        elif health_status == "unavailable":
            health_score = 0.0
        else:
            health_score = 20.0

        # --- Reliability score (0-250) ---
        perf_metrics = self._performance_analyzer.get_metrics(runtime_name)
        reliability_score = perf_metrics.reliability_score * 2.5  # scale 0-100 → 0-250

        # --- Performance score (0-200) ---
        performance_score = perf_metrics.performance_score * 2.0  # scale 0-100 → 0-200

        # --- Capability score (0-150) ---
        if runtime.capabilities is not None and capability in runtime.capabilities.available:
            capability_score = 150.0
        else:
            capability_score = 0.0

        # --- Policy / preference score (0-100) ---
        policy_score = 0.0
        if preferred_name is not None and runtime_name == preferred_name:
            policy_score = 100.0
        if preference is not None:
            if preference.lower() in runtime_name.lower():
                policy_score = max(policy_score, 50.0)
        # Boost if the policy engine suggests this runtime.
        if policy_preferred is not None and runtime_name == policy_preferred:
            policy_score = max(policy_score, 100.0)

        # --- Circuit breaker penalty (0-100) ---
        circuit_penalty = 0.0
        if not self._recovery_manager.should_retry(runtime_name):
            circuit_penalty = 100.0 * w.circuit_penalty_weight
            meta["circuit_state"] = "open"

        # --- Composite final score (0-1000) ---
        raw = (
            health_score * w.health_weight
            + reliability_score * w.reliability_weight
            + performance_score * w.performance_weight
            + capability_score * w.capability_weight
            + policy_score * w.policy_weight
            - circuit_penalty
        )
        final_score = max(0.0, raw)

        meta["executions"] = perf_metrics.executions
        meta["successes"] = perf_metrics.successes
        meta["failures"] = perf_metrics.failures

        return RuntimeDecisionScore(
            runtime_name=runtime_name,
            final_score=final_score,
            health_score=health_score * w.health_weight,
            reliability_score=reliability_score * w.reliability_weight,
            performance_score=performance_score * w.performance_weight,
            capability_score=capability_score * w.capability_weight,
            policy_score=policy_score * w.policy_weight,
            circuit_penalty=circuit_penalty,
            metadata=meta,
        )

    def rank_candidates(
        self,
        capability: str,
        *,
        preference: Optional[str] = None,
        preferred_name: Optional[str] = None,
    ) -> list[RuntimeDecisionScore]:
        """Evaluate and rank all registered runtimes by composite score.

        Args:
            capability: Required capability identifier.
            preference: Optional deployment hint.
            preferred_name: Optional runtime name to boost.

        Returns:
            A list of :class:`RuntimeDecisionScore` sorted by descending
            ``final_score``. Runtimes that cannot provide the capability
            or have zero capability score are still included (they rank
            lowest), so callers can inspect the full landscape.
        """
        names = self._registry.list_available()
        scores: list[RuntimeDecisionScore] = []

        for name in names:
            try:
                score = self.evaluate_runtime(
                    name,
                    capability,
                    preference=preference,
                    preferred_name=preferred_name,
                )
            except RuntimeDecisionError:
                continue
            scores.append(score)

        scores.sort(key=lambda s: s.final_score, reverse=True)
        return scores

    def explain_decision(
        self,
        chosen: RuntimeDecisionScore,
        candidates: list[RuntimeDecisionScore],
    ) -> str:
        """Produce a human-readable explanation for why ``chosen`` was selected.

        Args:
            chosen: The winning candidate score.
            candidates: Full list of evaluated candidates (sorted).

        Returns:
            A plain-text explanation string.
        """
        lines: list[str] = []
        lines.append(
            f"Selected runtime '{chosen.runtime_name}' "
            f"(final score: {chosen.final_score:.1f}/1000)."
        )

        # Decompose the winner's scores.
        parts = []
        if chosen.health_score > 0:
            parts.append(f"health={chosen.health_score:.0f}/200")
        if chosen.reliability_score > 0:
            parts.append(f"reliability={chosen.reliability_score:.0f}/250")
        if chosen.performance_score > 0:
            parts.append(f"performance={chosen.performance_score:.0f}/200")
        if chosen.capability_score > 0:
            parts.append(f"capability={chosen.capability_score:.0f}/150")
        if chosen.policy_score > 0:
            parts.append(f"policy={chosen.policy_score:.0f}/100")
        if chosen.circuit_penalty > 0:
            parts.append(f"circuit_penalty=-{chosen.circuit_penalty:.0f}")

        if parts:
            lines.append("  Scores: " + ", ".join(parts))

        # Summary of other candidates.
        others = [s for s in candidates if s.runtime_name != chosen.runtime_name]
        if others:
            top_others = others[:3]  # show at most 3 runners-up
            lines.append("  Runners-up:")
            for other in top_others:
                lines.append(
                    f"    - {other.runtime_name}: {other.final_score:.1f}/1000"
                )

        lines.append(
            f"Evaluated {len(candidates)} candidate(s) for the requested capability."
        )
        return "\n".join(lines)
