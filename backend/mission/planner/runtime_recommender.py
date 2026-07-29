"""Runtime Recommender for the Intelligent Mission Planner (HOS-042).

Recommends optimal runtime/model for each task node using
Runtime Intelligence Layer, Discovery Engine, and Orchestrator.
"""

from __future__ import annotations

from backend.mission.planner.planner_models import (
    ComplexityEstimate,
    RuntimeRecommendation,
    TaskBreakdown,
    TaskCategory,
)


class RuntimeRecommender:
    """Recommends runtime configurations for mission tasks.

    Uses category-based heuristics — can be enhanced with
    real RuntimeIntelligence (HOS-037) and Discovery (HOS-040) integration.
    """

    # Category → benchmark profile mapping
    _CATEGORY_PROFILE: dict[TaskCategory, str] = {
        TaskCategory.ANALYSIS: "reasoning",
        TaskCategory.DESIGN: "reasoning",
        TaskCategory.IMPLEMENTATION: "coding",
        TaskCategory.TESTING: "coding",
        TaskCategory.DOCUMENTATION: "general_chat",
        TaskCategory.DEPLOYMENT: "general_chat",
        TaskCategory.REVIEW: "reasoning",
        TaskCategory.PLANNING: "reasoning",
        TaskCategory.INTEGRATION: "coding",
        TaskCategory.OPTIMIZATION: "coding",
        TaskCategory.SECURITY: "coding",
        TaskCategory.CUSTOM: "general_chat",
    }

    # Complexity → model tier mapping
    _TIER_MAPPING: dict[str, list[str]] = {
        "critical": ["qwen3:30b-coder", "deepseek-r1:32b", "phi4:14b"],
        "high": ["qwen3:14b", "deepseek-r1:14b", "gemma3:12b"],
        "medium": ["qwen3:8b", "codellama:13b", "llama3.2:3b"],
        "low": ["qwen3:4b", "qwen3:1.7b"],
    }

    def recommend(
        self,
        task: TaskBreakdown,
        estimate: ComplexityEstimate,
    ) -> RuntimeRecommendation:
        """Recommend runtime for a single task.

        Args:
            task: The task breakdown
            estimate: The complexity estimate for this task

        Returns:
            RuntimeRecommendation with preferred runtime and alternatives.
        """
        profile = self._CATEGORY_PROFILE.get(task.category, "general_chat")

        # Select model tier based on complexity
        tier = self._TIER_MAPPING.get(estimate.complexity_level, self._TIER_MAPPING["medium"])
        primary = tier[0] if tier else "qwen3:8b"
        alternatives = tier[1:] if len(tier) > 1 else []
        fallback = tier[1] if len(tier) > 1 else primary

        # Build reasoning
        reasoning = (
            f"Category '{task.category.value}' maps to profile '{profile}'. "
            f"Complexity level '{estimate.complexity_level}' ({estimate.complexity_score}/10) "
            f"suggests {primary}. Risk: {estimate.risk_level.value}."
        )

        if estimate.estimated_vram_gb > 8.0:
            reasoning += f" High VRAM estimate ({estimate.estimated_vram_gb}GB) — consider smaller model."
            alternatives.insert(0, "qwen3:4b")

        # Confidence based on how well the recommendation matches
        confidence = estimate.confidence
        if estimate.complexity_level in ("critical", "high"):
            confidence = min(confidence, 0.7)  # higher uncertainty for complex tasks

        return RuntimeRecommendation(
            task_id=task.task_id,
            runtime_id="",
            model_name=primary,
            benchmark_profile=profile,
            priority=estimate.suggested_priority,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            alternatives=[a for a in alternatives if a != primary][:3],
            fallback_runtime=fallback,
        )

    def recommend_all(
        self,
        tasks: list[TaskBreakdown],
        estimates: dict[str, ComplexityEstimate],
    ) -> dict[str, RuntimeRecommendation]:
        """Recommend runtimes for all tasks."""
        return {
            t.task_id: self.recommend(t, estimates.get(t.task_id, ComplexityEstimate()))
            for t in tasks
        }
