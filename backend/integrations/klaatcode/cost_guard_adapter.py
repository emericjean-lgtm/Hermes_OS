"""Cost Guard Adapter (HOS-054D).

Bridges KlaatCode tasks into the Runtime Orchestrator (HOS-038) for
cost-aware runtime and model recommendations.

Analyzes: task complexity, project size, token cost, estimated duration,
required runtime, and model fit.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Data classes ────────────────────────────────────────────

@dataclass
class TaskCostEstimate:
    """Estimated cost and resource requirements for a KlaatCode task."""
    task_id: str = ""
    task_type: str = ""
    complexity: float = 0.0  # 0.0 - 10.0
    project_size_files: int = 0
    project_size_lines: int = 0
    estimated_tokens: int = 0
    estimated_duration_ms: float = 0.0
    recommended_runtime: str = ""
    recommended_model: str = ""
    estimated_cost_tokens: float = 0.0
    vram_required_mb: float = 0.0
    ram_required_mb: float = 256.0
    fallback_runtime: str = ""
    justification: str = ""


@dataclass
class RuntimeRecommendation:
    """Recommendation from the Cost Guard for task execution."""
    task_id: str = ""
    primary_runtime: str = ""
    primary_model: str = ""
    fallback_runtime: str = ""
    estimated_cost: float = 0.0
    estimated_duration_ms: float = 0.0
    confidence: float = 0.0
    factors: dict[str, float] = field(default_factory=dict)
    reasoning: str = ""


# ── Complexity reference ────────────────────────────────────

# Complexity bands for different task types (0-10)
TASK_COMPLEXITY = {
    "code_analysis": 3.0,
    "inspect_code": 2.0,
    "search_code": 2.5,
    "code_generation": 6.0,
    "generate_code_plan": 5.5,
    "edit_file": 4.0,
    "refactoring": 7.0,
    "run_diagnostics": 2.0,
    "validate_changes": 3.0,
    "code_review": 5.0,
    "test_analysis": 4.5,
    "patch_generation": 6.5,
    "project_navigation": 3.5,
}

# Runtime recommendations by complexity
RUNTIME_BY_COMPLEXITY = {
    "low": {"runtime": "cpu", "model": "small"},
    "medium": {"runtime": "hybrid", "model": "medium"},
    "high": {"runtime": "gpu", "model": "large"},
    "extreme": {"runtime": "cloud_gpu", "model": "xl"},
}


# ── Adapter ─────────────────────────────────────────────────

class CostGuardAdapter:
    """Analyzes KlaatCode tasks and recommends optimal runtime/model/cost.

    Thread-safe. Bridges KlaatCode → Runtime Orchestrator (HOS-038).
    """

    def __init__(
        self,
        runtime_orchestrator: Any = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._orchestrator = runtime_orchestrator
        self._on_event = on_event
        self._estimates: dict[str, TaskCostEstimate] = {}
        self._recommendations: dict[str, RuntimeRecommendation] = {}
        self._analyzed_count = 0

    # ── Cost Estimation ─────────────────────────────────────

    def estimate_task(
        self,
        task_id: str,
        task_type: str,
        project_size_files: int = 0,
        project_size_lines: int = 0,
        parameters: Optional[dict] = None,
    ) -> TaskCostEstimate:
        """Estimate cost and resource requirements for a KlaatCode task.

        Args:
            task_id: Task identifier.
            task_type: Type of task (from KlaatCodeTaskType or MCP action).
            project_size_files: Number of files in the project.
            project_size_lines: Estimated lines of code.
            parameters: Task-specific parameters that may affect cost.

        Returns:
            TaskCostEstimate with complexity, tokens, duration, and recommendations.
        """
        complexity = TASK_COMPLEXITY.get(task_type, 5.0)

        # Adjust for project size
        if project_size_files > 100:
            complexity += 2.0
        elif project_size_files > 50:
            complexity += 1.0
        complexity = min(10.0, complexity)

        # Estimate tokens
        estimated_tokens = int(500 + project_size_lines * 0.5 + complexity * 200)

        # Estimate duration
        estimated_duration_ms = (complexity * 2000) + (project_size_lines * 0.5)

        # Pick runtime/model based on complexity
        if complexity < 3:
            band = "low"
        elif complexity < 6:
            band = "medium"
        elif complexity < 8:
            band = "high"
        else:
            band = "extreme"

        runtime_cfg = RUNTIME_BY_COMPLEXITY[band]

        estimate = TaskCostEstimate(
            task_id=task_id,
            task_type=task_type,
            complexity=round(complexity, 1),
            project_size_files=project_size_files,
            project_size_lines=project_size_lines,
            estimated_tokens=estimated_tokens,
            estimated_duration_ms=round(estimated_duration_ms, 0),
            recommended_runtime=runtime_cfg["runtime"],
            recommended_model=runtime_cfg["model"],
            estimated_cost_tokens=round(estimated_tokens * 0.0001, 4),
            vram_required_mb=complexity * 500,
            ram_required_mb=256 + project_size_lines * 0.1,
            fallback_runtime="cpu",
            justification=f"Complexity {complexity:.1f}/10, {project_size_files} files, {project_size_lines} lines → {band} band",
        )

        with self._lock:
            self._estimates[task_id] = estimate
            self._analyzed_count += 1

        if self._on_event:
            self._on_event("klaatcode.cost.estimated", {
                "task_id": task_id,
                "complexity": estimate.complexity,
                "estimated_tokens": estimate.estimated_tokens,
                "recommended_runtime": estimate.recommended_runtime,
            }, severity="info")

        return estimate

    # ── Runtime Recommendation ──────────────────────────────

    def recommend_runtime(
        self,
        task_id: str,
        task_type: str,
        project_size_files: int = 0,
        project_size_lines: int = 0,
    ) -> RuntimeRecommendation:
        """Generate a full runtime recommendation for a task.

        If connected to a RuntimeOrchestrator, delegates to it for
        more sophisticated decision-making.
        """
        estimate = self.estimate_task(
            task_id, task_type,
            project_size_files=project_size_files,
            project_size_lines=project_size_lines,
        )

        rec = RuntimeRecommendation(
            task_id=task_id,
            primary_runtime=estimate.recommended_runtime,
            primary_model=estimate.recommended_model,
            fallback_runtime=estimate.fallback_runtime,
            estimated_cost=estimate.estimated_cost_tokens,
            estimated_duration_ms=estimate.estimated_duration_ms,
            confidence=min(0.95, 0.5 + estimate.complexity * 0.05),
            factors={
                "complexity": estimate.complexity / 10.0,
                "project_size": min(1.0, project_size_files / 100.0),
                "estimated_tokens": min(1.0, estimate.estimated_tokens / 10000.0),
            },
            reasoning=estimate.justification,
        )

        # Try orchestrator for better recommendation
        if self._orchestrator and hasattr(self._orchestrator, 'evaluate'):
            try:
                orch_decision = self._orchestrator.evaluate(
                    task_context={"task_type": task_type, "complexity": estimate.complexity}
                )
                if orch_decision and orch_decision.selected_runtime:
                    rec.primary_runtime = orch_decision.selected_runtime
                    rec.confidence = max(rec.confidence, 0.7)
            except Exception:
                pass

        with self._lock:
            self._recommendations[task_id] = rec

        if self._on_event:
            self._on_event("klaatcode.runtime.recommended", {
                "task_id": task_id,
                "runtime": rec.primary_runtime,
                "model": rec.primary_model,
                "confidence": rec.confidence,
            }, severity="info")

        return rec

    # ── Query ────────────────────────────────────────────────

    def get_estimate(self, task_id: str) -> Optional[TaskCostEstimate]:
        with self._lock:
            return self._estimates.get(task_id)

    def get_recommendation(self, task_id: str) -> Optional[RuntimeRecommendation]:
        with self._lock:
            return self._recommendations.get(task_id)

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            avg_complexity = (
                sum(e.complexity for e in self._estimates.values()) / max(len(self._estimates), 1)
            )
            return {
                "tasks_analyzed": self._analyzed_count,
                "estimates_cached": len(self._estimates),
                "recommendations": len(self._recommendations),
                "avg_complexity": round(avg_complexity, 1),
                "by_runtime": {
                    rt: sum(1 for e in self._estimates.values() if e.recommended_runtime == rt)
                    for rt in set(e.recommended_runtime for e in self._estimates.values())
                },
            }
