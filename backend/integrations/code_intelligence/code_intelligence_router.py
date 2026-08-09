"""Code Intelligence Router (HOS-055D).

Intelligent routing layer that automatically selects KlaatCode, Oh My Pi,
or a hybrid combination based on task characteristics, historical success,
and resource constraints.

Scoring factors:
- Task type fit (primary heuristic)
- LSP / DAP / AST requirements
- Language proficiency
- Historical success rate
- Estimated cost (complexity × tokens)
- Resource availability
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from .code_intelligence_models import (
    CI_TO_KLAATCODE_TASK_TYPE,
    CI_TO_OHMYPI_TASK_TYPE,
    CodeIntelligenceTask,
    CodeIntelligenceTaskType,
    CodeProvider,
    HybridExecutionResult,
    ProviderExecutionResult,
    ProviderScore,
    RouteReason,
    RoutingDecision,
    SelectionStrategy,
)

# ── Scoring weights ──────────────────────────────────────────

FACTOR_WEIGHTS = {
    "task_fit": 0.30,
    "lsp_dap_ast": 0.20,
    "historical_success": 0.25,
    "cost_efficiency": 0.15,
    "language_match": 0.10,
}

# Task types real one-shot LLM generation can plausibly handle, mapped to a
# genuine config/models.yaml routing task_type (backend/core/router.py).
# DEBUGGING/DIAGNOSTICS/ARCHITECTURE_REVIEW are deliberately absent: they
# need a real debugger session, project-wide static analysis, or diagnostics
# tool a chat completion cannot provide — offering Hermes-native for those
# would be exactly the fabricated capability R-006 exists to remove.
HERMES_NATIVE_TASK_TYPES: dict[CodeIntelligenceTaskType, str] = {
    CodeIntelligenceTaskType.CODE_ANALYSIS: "code_analysis",
    CodeIntelligenceTaskType.CODE_GENERATION: "code_generation",
    CodeIntelligenceTaskType.REFACTORING: "code_refactor",
    CodeIntelligenceTaskType.CODE_REVIEW: "code_analysis",
    CodeIntelligenceTaskType.DOCUMENTATION: "code_analysis",
    CodeIntelligenceTaskType.TEST_GENERATION: "code_generation",
    CodeIntelligenceTaskType.OPTIMIZATION: "code_refactor",
}


class CodeIntelligenceRouter:
    """Routes code tasks to KlaatCode, Oh My Pi, or a hybrid of both.

    Thread-safe. Maintains execution history for adaptive scoring.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._klaatcode_success: deque[bool] = deque(maxlen=100)
        self._ohmypi_success: deque[bool] = deque(maxlen=100)
        self._hermes_native_success: deque[bool] = deque(maxlen=100)
        self._execution_history: list[dict[str, Any]] = []

    # ── Public API ──

    def decide(
        self,
        task: CodeIntelligenceTask,
        klaatcode_available: bool = True,
        ohmypi_available: bool = True,
        hermes_native_available: bool = False,
        force_provider: CodeProvider | None = None,
    ) -> RoutingDecision:
        """Determine the best provider(s) for a given code task.

        Args:
            task: The code intelligence task to route.
            klaatcode_available: Whether KlaatCode agent is available.
            ohmypi_available: Whether OhMyPi agent is available.
            hermes_native_available: Whether a real HermesNativeExecutor is
                bound. Defaults False (not True like the two external
                providers) so a bare ``CodeIntelligenceRouter()`` — as every
                pre-R-006 caller and test constructs — keeps its original
                klaatcode/ohmypi-only behaviour unless a caller that actually
                has an executor opts in.
            force_provider: Override to force a specific provider.

        Returns:
            RoutingDecision with selected provider and scoring details.
        """
        with self._lock:
            # Force override
            if force_provider is not None:
                if force_provider == CodeProvider.HYBRID:
                    return self._decide_hybrid(task, "Forced hybrid")
                return RoutingDecision(
                    task_type=task.task_type,
                    selected_provider=force_provider,
                    strategy=SelectionStrategy.SINGLE_BEST,
                    primary_reason=RouteReason.FALLBACK,
                    scores=[ProviderScore(provider=force_provider, score=1.0,
                                         reasoning=[f"Forced to {force_provider.value}"])],
                    metadata={"forced": True},
                )

            # Score every real candidate. Hybrid stays klaatcode+ohmypi only
            # (unchanged semantics) — hermes_native is single-best-only.
            kc_score = self._score_klaatcode(task) if klaatcode_available else None
            omp_score = self._score_ohmypi(task) if ohmypi_available else None
            hn_score = self._score_hermes_native(task) if hermes_native_available else None

            candidates: dict[CodeProvider, ProviderScore] = {}
            if kc_score is not None:
                candidates[CodeProvider.KLATCODE] = kc_score
            if omp_score is not None:
                candidates[CodeProvider.OHMYPI] = omp_score
            if hn_score is not None:
                candidates[CodeProvider.HERMES_NATIVE] = hn_score

            if not candidates:
                return RoutingDecision(
                    task_type=task.task_type,
                    selected_provider=CodeProvider.KLATCODE,
                    strategy=SelectionStrategy.SINGLE_BEST,
                    primary_reason=RouteReason.FALLBACK,
                    scores=[],
                    metadata={"error": "No providers available"},
                )

            if (
                kc_score is not None and omp_score is not None
                and self._should_use_hybrid(task, kc_score.score, omp_score.score)
            ):
                return self._decide_hybrid(
                    task,
                    f"Complementary: KC={kc_score.score:.2f} OMP={omp_score.score:.2f}",
                    kc_score, omp_score,
                )

            # Single best among whatever real candidates exist.
            winner, winner_score = max(candidates.items(), key=lambda kv: kv[1].score)
            others = [s for provider, s in candidates.items() if provider != winner]

            primary_reason = RouteReason.HIGHEST_HISTORICAL
            if winner_score.reasoning:
                first = winner_score.reasoning[0]
                for r in RouteReason:
                    if r.value in first:
                        primary_reason = r
                        break

            metadata: dict[str, Any] = {}
            if kc_score is not None:
                metadata["klaatcode_score"] = round(kc_score.score, 4)
            if omp_score is not None:
                metadata["ohmypi_score"] = round(omp_score.score, 4)
            if hn_score is not None:
                metadata["hermes_native_score"] = round(hn_score.score, 4)
            if len(candidates) >= 2:
                all_scores = [s.score for s in candidates.values()]
                metadata["score_diff"] = round(max(all_scores) - min(all_scores), 4)

            return RoutingDecision(
                task_type=task.task_type,
                selected_provider=winner,
                strategy=SelectionStrategy.SINGLE_BEST,
                primary_reason=primary_reason,
                scores=[winner_score, *others],
                metadata=metadata,
            )

    def record_result(
        self, provider: CodeProvider, success: bool, task_type: str = ""
    ) -> None:
        """Record execution result for adaptive historical scoring."""
        with self._lock:
            if provider == CodeProvider.KLATCODE:
                self._klaatcode_success.append(success)
            elif provider == CodeProvider.OHMYPI:
                self._ohmypi_success.append(success)
            elif provider == CodeProvider.HERMES_NATIVE:
                self._hermes_native_success.append(success)
            self._execution_history.append({
                "provider": provider.value,
                "success": success,
                "task_type": task_type,
            })
            if len(self._execution_history) > 500:
                self._execution_history = self._execution_history[-500:]

    def execute_hybrid(
        self,
        task: CodeIntelligenceTask,
        klaatcode_executor: Any,
        ohmypi_executor: Any,
        order: list[CodeProvider] | None = None,
    ) -> HybridExecutionResult:
        """Execute a task with both providers in hybrid mode.

        KlaatCode typically does analysis first, then Oh My Pi does
        LSP/DAP execution on the analyzed code.
        """
        providers = order or [CodeProvider.KLATCODE, CodeProvider.OHMYPI]
        kc_result = None
        omp_result = None
        errors = []

        for provider in providers:
            if provider == CodeProvider.KLATCODE and klaatcode_executor:
                try:
                    kc_result = self._execute_provider(
                        provider, task, klaatcode_executor
                    )
                    if not kc_result.success:
                        errors.append(f"KlaatCode: {kc_result.error}")
                except Exception as e:
                    errors.append(f"KlaatCode exception: {e}")
            elif provider == CodeProvider.OHMYPI and ohmypi_executor:
                try:
                    omp_result = self._execute_provider(
                        provider, task, ohmypi_executor
                    )
                    if not omp_result.success:
                        errors.append(f"OhMyPi: {omp_result.error}")
                except Exception as e:
                    errors.append(f"OhMyPi exception: {e}")

        kc_ok = kc_result and kc_result.success
        omp_ok = omp_result and omp_result.success
        overall = kc_ok or omp_ok

        return HybridExecutionResult(
            task_id=task.task_id,
            overall_success=overall,
            klaatcode_result=kc_result,
            ohmypi_result=omp_result,
            merged_data={
                "klaatcode": kc_result.data if kc_result else None,
                "ohmypi": omp_result.data if omp_result else None,
            },
            total_duration_ms=(
                (kc_result.duration_ms if kc_result else 0) +
                (omp_result.duration_ms if omp_result else 0)
            ),
            errors=errors,
        )

    def stats(self) -> dict[str, Any]:
        with self._lock:
            kc_success = list(self._klaatcode_success)
            omp_success = list(self._ohmypi_success)
            hn_success = list(self._hermes_native_success)
            return {
                "klaatcode": {
                    "total": len(kc_success),
                    "success_count": sum(1 for s in kc_success if s),
                    "success_rate": round(sum(1 for s in kc_success if s) / max(len(kc_success), 1) * 100, 1),
                },
                "ohmypi": {
                    "total": len(omp_success),
                    "success_count": sum(1 for s in omp_success if s),
                    "success_rate": round(sum(1 for s in omp_success if s) / max(len(omp_success), 1) * 100, 1),
                },
                "hermes_native": {
                    "total": len(hn_success),
                    "success_count": sum(1 for s in hn_success if s),
                    "success_rate": round(sum(1 for s in hn_success if s) / max(len(hn_success), 1) * 100, 1),
                },
                "total_executions": len(self._execution_history),
            }

    # ── Private scoring ──

    def _score_klaatcode(self, task: CodeIntelligenceTask) -> ProviderScore:
        """Score KlaatCode suitability for a task."""
        factors: dict[str, float] = {}
        reasoning: list[str] = []

        # Task fit: KlaatCode excels at analysis, architecture, diagnostics
        kc_strong = {CodeIntelligenceTaskType.CODE_ANALYSIS,
                     CodeIntelligenceTaskType.ARCHITECTURE_REVIEW,
                     CodeIntelligenceTaskType.DIAGNOSTICS,
                     CodeIntelligenceTaskType.CODE_REVIEW}
        kc_medium = {CodeIntelligenceTaskType.TEST_GENERATION,
                     CodeIntelligenceTaskType.OPTIMIZATION,
                     CodeIntelligenceTaskType.DOCUMENTATION}
        kc_weak = {CodeIntelligenceTaskType.DEBUGGING,
                   CodeIntelligenceTaskType.REFACTORING}

        if task.task_type in kc_strong:
            task_fit = 0.95
            reasoning.append("KlaatCode strong fit for this task type")
        elif task.task_type in kc_medium:
            task_fit = 0.70
            reasoning.append("KlaatCode medium fit for this task type")
        elif task.task_type in kc_weak:
            task_fit = 0.35
            reasoning.append("KlaatCode weak fit for this task type")
        else:
            task_fit = 0.60
        factors["task_fit"] = task_fit

        # LSP/DAP/AST: KlaatCode has none
        if task.requires_lsp or task.requires_dap or task.requires_ast:
            lsp_score = 0.10
            reasoning.append("KlaatCode lacks LSP/DAP/AST")
        else:
            lsp_score = 1.0
        factors["lsp_dap_ast"] = lsp_score

        # Historical success
        with self._lock:
            kc_hist = list(self._klaatcode_success)
            hist_score = sum(1 for s in kc_hist if s) / max(len(kc_hist), 1) if kc_hist else 0.80
        factors["historical_success"] = hist_score

        # Cost: KlaatCode is lighter (no tree-sitter, no LSP)
        cost_score = 0.85  # Mid-range
        factors["cost_efficiency"] = cost_score

        # Language match (neutral for KlaatCode)
        lang_score = 0.75
        factors["language_match"] = lang_score

        total = (
            factors["task_fit"] * FACTOR_WEIGHTS["task_fit"] +
            factors["lsp_dap_ast"] * FACTOR_WEIGHTS["lsp_dap_ast"] +
            factors["historical_success"] * FACTOR_WEIGHTS["historical_success"] +
            factors["cost_efficiency"] * FACTOR_WEIGHTS["cost_efficiency"] +
            factors["language_match"] * FACTOR_WEIGHTS["language_match"]
        )

        return ProviderScore(
            provider=CodeProvider.KLATCODE,
            score=round(total, 4),
            factors=factors,
            reasoning=reasoning,
        )

    def _score_ohmypi(self, task: CodeIntelligenceTask) -> ProviderScore:
        """Score Oh My Pi suitability for a task."""
        factors: dict[str, float] = {}
        reasoning: list[str] = []

        # Task fit: OhMyPi excels at LSP/DAP/AST tasks
        omp_strong = {CodeIntelligenceTaskType.REFACTORING,
                      CodeIntelligenceTaskType.DEBUGGING,
                      CodeIntelligenceTaskType.CODE_GENERATION}
        omp_medium = {CodeIntelligenceTaskType.CODE_ANALYSIS,
                      CodeIntelligenceTaskType.OPTIMIZATION,
                      CodeIntelligenceTaskType.CODE_REVIEW}
        omp_weak = {CodeIntelligenceTaskType.ARCHITECTURE_REVIEW,
                    CodeIntelligenceTaskType.DOCUMENTATION}

        if task.task_type in omp_strong:
            task_fit = 0.95
            reasoning.append("OhMyPi strong fit for this task type")
        elif task.task_type in omp_medium:
            task_fit = 0.65
            reasoning.append("OhMyPi medium fit for this task type")
        elif task.task_type in omp_weak:
            task_fit = 0.30
            reasoning.append("OhMyPi weak fit for this task type")
        else:
            task_fit = 0.55
        factors["task_fit"] = task_fit

        # LSP/DAP/AST: OhMyPi's strength
        lsp_count = sum([task.requires_lsp, task.requires_dap, task.requires_ast])
        if lsp_count > 0:
            lsp_score = 1.0
            reasoning.append("OhMyPi provides required LSP/DAP/AST")
        else:
            lsp_score = 0.60  # Still has them, just not needed
        factors["lsp_dap_ast"] = lsp_score

        # Historical success
        with self._lock:
            omp_hist = list(self._ohmypi_success)
            hist_score = sum(1 for s in omp_hist if s) / max(len(omp_hist), 1) if omp_hist else 0.78
        factors["historical_success"] = hist_score

        # Cost: OhMyPi is heavier (Rust binary, LSP/DAP servers)
        cost_score = 0.60
        factors["cost_efficiency"] = cost_score

        # Language match (OhMyPi has broader LSP support)
        lang_score = 0.85
        factors["language_match"] = lang_score

        total = (
            factors["task_fit"] * FACTOR_WEIGHTS["task_fit"] +
            factors["lsp_dap_ast"] * FACTOR_WEIGHTS["lsp_dap_ast"] +
            factors["historical_success"] * FACTOR_WEIGHTS["historical_success"] +
            factors["cost_efficiency"] * FACTOR_WEIGHTS["cost_efficiency"] +
            factors["language_match"] * FACTOR_WEIGHTS["language_match"]
        )

        return ProviderScore(
            provider=CodeProvider.OHMYPI,
            score=round(total, 4),
            factors=factors,
            reasoning=reasoning,
        )

    def _score_hermes_native(self, task: CodeIntelligenceTask) -> ProviderScore | None:
        """Score Hermes's own Model Intelligence -> Runtime -> Ollama path.

        Returns None when the task type has no real mapping in
        HERMES_NATIVE_TASK_TYPES — an ineligible task type is not "scored
        low", it is simply not a candidate, the same way klaatcode_available
        =False removes KlaatCode rather than giving it a token low score.
        """
        if task.task_type not in HERMES_NATIVE_TASK_TYPES:
            return None

        factors: dict[str, float] = {}
        reasoning: list[str] = []

        hn_strong = {CodeIntelligenceTaskType.CODE_GENERATION,
                     CodeIntelligenceTaskType.DOCUMENTATION,
                     CodeIntelligenceTaskType.TEST_GENERATION}
        hn_medium = {CodeIntelligenceTaskType.CODE_ANALYSIS,
                     CodeIntelligenceTaskType.CODE_REVIEW}
        hn_weak = {CodeIntelligenceTaskType.REFACTORING,
                   CodeIntelligenceTaskType.OPTIMIZATION}

        if task.task_type in hn_strong:
            task_fit = 0.80
            reasoning.append("Hermes-native strong fit for this task type")
        elif task.task_type in hn_medium:
            task_fit = 0.55
            reasoning.append("Hermes-native medium fit for this task type")
        elif task.task_type in hn_weak:
            task_fit = 0.30
            reasoning.append("Hermes-native weak fit for this task type")
        else:
            task_fit = 0.40
        factors["task_fit"] = task_fit

        # LSP/DAP/AST: Hermes-native has none of these — a real requirement
        # for one rules it out almost entirely, same treatment KlaatCode gets.
        if task.requires_lsp or task.requires_dap or task.requires_ast:
            lsp_score = 0.05
            reasoning.append("Hermes-native lacks LSP/DAP/AST")
        else:
            lsp_score = 0.70
        factors["lsp_dap_ast"] = lsp_score

        with self._lock:
            hn_hist = list(self._hermes_native_success)
            hist_score = sum(1 for s in hn_hist if s) / max(len(hn_hist), 1) if hn_hist else 0.70
        factors["historical_success"] = hist_score

        # Cost: no subprocess/CLI overhead, but a real model load/inference
        # cost applies — mid-high, not free.
        cost_score = 0.75
        factors["cost_efficiency"] = cost_score

        # Language match: Ollama's code models are broadly capable but not
        # tool-integrated the way LSP/AST-backed providers are.
        lang_score = 0.65
        factors["language_match"] = lang_score

        total = (
            factors["task_fit"] * FACTOR_WEIGHTS["task_fit"] +
            factors["lsp_dap_ast"] * FACTOR_WEIGHTS["lsp_dap_ast"] +
            factors["historical_success"] * FACTOR_WEIGHTS["historical_success"] +
            factors["cost_efficiency"] * FACTOR_WEIGHTS["cost_efficiency"] +
            factors["language_match"] * FACTOR_WEIGHTS["language_match"]
        )

        return ProviderScore(
            provider=CodeProvider.HERMES_NATIVE,
            score=round(total, 4),
            factors=factors,
            reasoning=reasoning,
        )

    def _should_use_hybrid(
        self, task: CodeIntelligenceTask, kc_score: float, omp_score: float
    ) -> bool:
        """Determine if hybrid mode is appropriate.

        Hybrid is used when:
        - Both scores are close (within 15%)
        - The task benefits from both approaches
        - e.g., code review: KC analyzes → OMP LSP validates
        """
        hybrid_tasks = {
            CodeIntelligenceTaskType.CODE_REVIEW,
            CodeIntelligenceTaskType.DIAGNOSTICS,
            CodeIntelligenceTaskType.OPTIMIZATION,
        }
        if task.task_type in hybrid_tasks:
            return True
        # Close scores and complex task
        if abs(kc_score - omp_score) < 0.15 and task.complexity > 0.6:
            return True
        return False

    def _decide_hybrid(
        self, task: CodeIntelligenceTask, reason: str,
        kc_score: ProviderScore | None = None,
        omp_score: ProviderScore | None = None,
    ) -> RoutingDecision:
        """Build a hybrid routing decision."""
        scores = []
        if kc_score:
            scores.append(kc_score)
        if omp_score:
            scores.append(omp_score)

        # Hybrid order: KC analyzes first, OMP executes second
        hybrid_order = [CodeProvider.KLATCODE, CodeProvider.OHMYPI]

        return RoutingDecision(
            task_type=task.task_type,
            selected_provider=CodeProvider.HYBRID,
            strategy=SelectionStrategy.HYBRID_BOTH,
            primary_reason=RouteReason.HIGHEST_HISTORICAL,
            scores=scores,
            hybrid_order=hybrid_order,
            metadata={"reason": reason},
        )

    def _execute_provider(
        self, provider: CodeProvider, task: CodeIntelligenceTask, executor: Any
    ) -> ProviderExecutionResult:
        """Execute a task with a specific provider's executor (agent)."""
        import time
        started = time.time()

        # Same real translation CodeIntelligenceAgent's single-provider path
        # applies (see CI_TO_KLAATCODE_TASK_TYPE/CI_TO_OHMYPI_TASK_TYPE) — the
        # hybrid path must not silently send an un-translated CI task_type
        # either.
        mapping = {
            CodeProvider.KLATCODE: CI_TO_KLAATCODE_TASK_TYPE,
            CodeProvider.OHMYPI: CI_TO_OHMYPI_TASK_TYPE,
        }.get(provider)
        provider_task_type = mapping.get(task.task_type) if mapping else task.task_type.value
        if provider_task_type is None:
            return ProviderExecutionResult(
                provider=provider,
                task_id=task.task_id,
                success=False,
                error=f"{provider.value} has no real capability for task type {task.task_type.value!r}",
                duration_ms=0.0,
            )

        try:
            result = executor.execute_task(
                provider_task_type,
                task.parameters,
                mission_id=task.mission_id,
                node_id=task.node_id,
            )
            duration_ms = (time.time() - started) * 1000

            return ProviderExecutionResult(
                provider=provider,
                task_id=task.task_id,
                success=result.outcome.value == "success",
                data=result.details.get("data") if result.details else None,
                error=result.error_message or "",
                duration_ms=duration_ms,
                mcp_action=result.details.get("mcp_action", "") if result.details else "",
            )
        except Exception as e:
            duration_ms = (time.time() - started) * 1000
            return ProviderExecutionResult(
                provider=provider,
                task_id=task.task_id,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
