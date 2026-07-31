"""Runtime Recommender for the Intelligent Mission Planner (HOS-042).

Recommends optimal runtime/model for each task node using
Runtime Intelligence Layer, Discovery Engine, and Orchestrator.
"""

from __future__ import annotations

from typing import Any

from backend.mission.planner.planner_models import (
    ComplexityEstimate,
    RuntimeRecommendation,
    TaskBreakdown,
    TaskCategory,
)

# Complexity level → roles in config/models.yaml, ordered from primary
# choice to fallback. Role *names* rather than tags: the tags they resolve
# to have already changed once this deployment's lifetime (phi4:14b ->
# phi4-reasoning:14b-q4_K_M, qwen3:8b -> qwen3.5:9b) while the roles stayed
# stable, so resolving through config/models.yaml at call time is what
# keeps this mapping from re-drifting into naming models nobody installed
# — exactly the defect this replaced (see CHANGELOG).
_TIER_ROLES: dict[str, list[str]] = {
    "critical": ["code", "reasoning_escalation", "advanced_analysis"],
    "high": ["orchestrator", "reasoning", "security"],
    "medium": ["standard", "double_check"],
    "low": ["swift", "double_check"],
}


def _build_tier_mapping() -> dict[str, list[str]]:
    try:
        from backend.core.config import load_models_config

        roles: dict[str, dict[str, Any]] = load_models_config().get("roles") or {}
    except Exception:
        # A missing/unreadable config/models.yaml must not take the whole
        # module down at import time.
        return {}

    mapping: dict[str, list[str]] = {}
    for level, role_names in _TIER_ROLES.items():
        tags = [roles[r]["model"] for r in role_names if r in roles]
        if tags:
            mapping[level] = tags
    return mapping


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

    # Complexity → model tier mapping, resolved from config/models.yaml —
    # see _build_tier_mapping. Six of these six tags were never installed
    # in any deployment of this project before this fix (qwen3:30b-coder,
    # phi4:14b, qwen3:14b, gemma3:12b, codellama:13b, llama3.2:3b).
    _TIER_MAPPING: dict[str, list[str]] = _build_tier_mapping()

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
        tier = self._TIER_MAPPING.get(estimate.complexity_level) or self._TIER_MAPPING.get("medium") or []
        primary = tier[0] if tier else "qwen3.5:9b"
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
