"""Complexity Estimator for the Intelligent Mission Planner (HOS-042).

Estimates task complexity, duration, resource needs, and risk.
"""

from __future__ import annotations

from backend.mission.planner.planner_models import (
    ComplexityEstimate,
    RiskLevel,
    TaskBreakdown,
    TaskCategory,
)


class ComplexityEstimator:
    """Estimates complexity, duration, resources, and risk for each task."""

    # Base estimates per category (hours, VRAM GB, RAM GB, tokens)
    _CATEGORY_BASE: dict[TaskCategory, tuple[float, float, float, int]] = {
        TaskCategory.ANALYSIS: (1.0, 1.0, 2.0, 2000),
        TaskCategory.DESIGN: (1.5, 1.5, 3.0, 3000),
        TaskCategory.IMPLEMENTATION: (4.0, 3.0, 4.0, 8000),
        TaskCategory.TESTING: (2.0, 2.0, 3.0, 4000),
        TaskCategory.DOCUMENTATION: (1.0, 1.0, 2.0, 3000),
        TaskCategory.DEPLOYMENT: (1.5, 2.0, 3.0, 2000),
        TaskCategory.REVIEW: (0.5, 1.0, 2.0, 1000),
        TaskCategory.PLANNING: (0.5, 1.0, 2.0, 1000),
        TaskCategory.INTEGRATION: (3.0, 2.5, 4.0, 5000),
        TaskCategory.OPTIMIZATION: (2.0, 3.0, 4.0, 4000),
        TaskCategory.SECURITY: (2.5, 2.0, 3.0, 4000),
        TaskCategory.CUSTOM: (2.0, 2.0, 3.0, 4000),
    }

    # Complexity factors based on keywords in description
    _COMPLEXITY_KEYWORDS: dict[str, float] = {
        "complex": 1.5,
        "advanced": 1.4,
        "enterprise": 1.5,
        "real-time": 1.5,
        "real time": 1.5,
        "distributed": 1.5,
        "scalable": 1.3,
        "multi": 1.3,
        "machine learning": 2.0,
        "ml": 2.0,
        "ai": 1.5,
        "llm": 1.5,
        "neural": 2.0,
        "concurrent": 1.4,
        "parallel": 1.4,
        "streaming": 1.4,
        "high availability": 1.5,
        "fault tolerant": 1.5,
        "secure": 1.3,
        "encrypted": 1.3,
        "migration": 1.4,
        "refactor": 1.3,
        "legacy": 1.4,
        "simple": 0.7,
        "basic": 0.7,
        "trivial": 0.5,
        "minor": 0.7,
    }

    # Risk factors
    _RISK_KEYWORDS: dict[str, RiskLevel] = {
        "critical": RiskLevel.CRITICAL,
        "production": RiskLevel.HIGH,
        "security": RiskLevel.HIGH,
        "data loss": RiskLevel.CRITICAL,
        "downtime": RiskLevel.HIGH,
        "breaking": RiskLevel.HIGH,
        "migration": RiskLevel.MEDIUM,
        "refactor": RiskLevel.MEDIUM,
        "experimental": RiskLevel.MEDIUM,
        "new": RiskLevel.LOW,
    }

    def estimate(self, task: TaskBreakdown) -> ComplexityEstimate:
        """Estimate complexity for a single task."""
        base_hours, base_vram, base_ram, base_tokens = self._CATEGORY_BASE.get(
            task.category, (2.0, 2.0, 3.0, 4000)
        )

        # Compute complexity multiplier from keywords
        text = (task.title + " " + task.description).lower()
        complexity_mult = 1.0
        for kw, factor in self._COMPLEXITY_KEYWORDS.items():
            if kw in text:
                complexity_mult = max(complexity_mult, factor)

        # Compute risk level
        risk = RiskLevel.LOW
        risk_factors: list[str] = []
        for kw, level in self._RISK_KEYWORDS.items():
            if kw in text:
                risk_factors.append(kw)
                if self._risk_gt(level, risk):
                    risk = level

        # Skill-based multiplier
        skill_mult = 1.0 + len(task.required_skills) * 0.1

        total_mult = complexity_mult * skill_mult

        # Duration estimate with range
        est_hours = base_hours * total_mult
        min_hours = est_hours * 0.5
        max_hours = est_hours * 2.0

        # Complexity score (0-10)
        complexity_score = min(10.0, total_mult * 4.0)
        if complexity_score <= 2.5:
            level = "low"
        elif complexity_score <= 5.0:
            level = "medium"
        elif complexity_score <= 7.5:
            level = "high"
        else:
            level = "critical"

        return ComplexityEstimate(
            task_id=task.task_id,
            complexity_score=round(complexity_score, 1),
            complexity_level=level,
            estimated_duration_hours=round(est_hours, 1),
            min_duration_hours=round(min_hours, 1),
            max_duration_hours=round(max_hours, 1),
            estimated_vram_gb=round(base_vram * complexity_mult, 1),
            estimated_ram_gb=round(base_ram * complexity_mult, 1),
            estimated_tokens=int(base_tokens * total_mult),
            risk_level=risk,
            risk_factors=risk_factors,
            suggested_priority=self._suggest_priority(risk, complexity_score),
            confidence=max(0.3, 1.0 - (complexity_mult - 1.0) * 0.5),
        )

    def estimate_all(self, tasks: list[TaskBreakdown]) -> dict[str, ComplexityEstimate]:
        """Estimate complexity for all tasks."""
        return {t.task_id: self.estimate(t) for t in tasks}

    def _suggest_priority(self, risk: RiskLevel, complexity: float) -> str:
        if risk == RiskLevel.CRITICAL or complexity >= 8.0:
            return "critical"
        elif risk == RiskLevel.HIGH or complexity >= 6.0:
            return "high"
        elif risk == RiskLevel.MEDIUM or complexity >= 4.0:
            return "normal"
        return "background"

    @staticmethod
    def _risk_gt(a: RiskLevel, b: RiskLevel) -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return order[a] > order[b]
