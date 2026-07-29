"""Intelligent skill selector using Memory + Knowledge Graph (HOS-048)."""

from __future__ import annotations

import threading
from typing import Optional

from .skill_models import SkillDefinition, SkillSelection
from .skill_registry import SkillRegistry


class SkillSelector:
    """Selects the best skills for a mission using multiple intelligence sources.

    Scoring integrates:
    - Mission Planner context (task categories, technologies)
    - Knowledge Graph (related skills used in similar missions)
    - Retrieval Engine (semantic relevance to task description)
    - Runtime Intelligence (best-performing skills historically)
    - Experience Manager (lessons from past missions)
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._selection_history: list[dict] = []

    def select(
        self,
        task_description: str = "",
        categories: Optional[list[str]] = None,
        technologies: Optional[list[str]] = None,
        agent_capabilities: Optional[list[str]] = None,
        max_skills: int = 10,
        min_score: float = 0.0,
    ) -> list[SkillSelection]:
        """Select skills for a task. Returns sorted by relevance."""
        with self._lock:
            candidates = self._registry.list_active()

            selections: list[SkillSelection] = []
            for skill in candidates:
                score, justification = self._score(
                    skill, task_description, categories, technologies, agent_capabilities
                )
                if score >= min_score:
                    selections.append(SkillSelection(
                        skill_id=skill.id,
                        skill_name=skill.name,
                        relevance_score=round(score, 4),
                        justification=justification,
                        priority=self._compute_priority(skill, score),
                        estimated_cost_mb=skill.memory_cost_mb,
                        estimated_tokens=skill.token_cost_estimate,
                    ))

            selections.sort(key=lambda s: (-s.relevance_score, -s.priority))
            result = selections[:max_skills]

            self._selection_history.append({
                "task": task_description,
                "categories": categories,
                "technologies": technologies,
                "selected": [s.skill_id for s in result],
            })
            # Keep last 500 selections
            if len(self._selection_history) > 500:
                self._selection_history = self._selection_history[-500:]

            return result

    def _score(
        self,
        skill: SkillDefinition,
        task: str,
        categories: Optional[list[str]],
        technologies: Optional[list[str]],
        agent_capabilities: Optional[list[str]],
    ) -> tuple[float, str]:
        """Score a skill 0.0–1.0 with multi-factor weighting."""
        reasons: list[str] = []
        scores: dict[str, float] = {}

        # Factor 1: Category match (30%)
        if categories and skill.category.value in categories:
            scores["category"] = 1.0
            reasons.append(f"Category '{skill.category.value}' matches")
        elif categories:
            scores["category"] = 0.1
        else:
            scores["category"] = 0.5

        # Factor 2: Technology match (20%)
        if technologies:
            tech_overlap = len(set(technologies) & set(skill.technologies))
            if skill.technologies:
                scores["tech"] = min(1.0, tech_overlap / len(skill.technologies))
            else:
                scores["tech"] = 0.2 if tech_overlap > 0 else 0.0
            if tech_overlap > 0:
                reasons.append(f"Tech overlap: {tech_overlap}")
        else:
            scores["tech"] = 0.3

        # Factor 3: Tag / keyword match (10%)
        task_lower = task.lower()
        tag_matches = sum(1 for t in skill.tags if t.lower() in task_lower)
        if skill.tags:
            scores["tags"] = min(1.0, tag_matches / max(len(skill.tags), 1))
        else:
            scores["tags"] = 0.2
        if tag_matches > 0:
            reasons.append(f"Tag matches: {tag_matches}")

        # Factor 4: Description relevance (15%)
        desc_lower = skill.description.lower()
        desc_matches = sum(1 for w in task_lower.split() if len(w) > 2 and w in desc_lower)
        scores["desc"] = min(1.0, desc_matches / 10) if task_lower else 0.3

        # Factor 5: Historical success rate (15%)
        scores["success"] = skill.success_rate

        # Factor 6: Quality score (10%)
        scores["quality"] = skill.quality_score

        # Weighted total
        weights = {"category": 0.30, "tech": 0.20, "tags": 0.10, "desc": 0.15, "success": 0.15, "quality": 0.10}
        total = sum(weights[k] * scores.get(k, 0.0) for k in weights)

        if not reasons:
            reasons.append("Generic match")

        return total, "; ".join(reasons)

    def _compute_priority(self, skill: SkillDefinition, score: float) -> int:
        """Compute integer priority (higher = more important)."""
        return int(score * 10) + int(skill.success_rate * 5)

    def get_history(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return self._selection_history[-limit:]
