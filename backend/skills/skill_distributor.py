"""Dynamic skill distributor — distributes skills across agents for a mission (HOS-048)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from .dependency_resolver import SkillDependencyResolver
from .skill_cache import SkillCache
from .skill_loader import SkillLoader
from .skill_models import SkillDistribution
from .skill_profiler import SkillProfiler
from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector


class SkillDistributor:
    """Orchestrates skill distribution across multiple agents for a mission.

    Pipeline:
    Mission → Agent task decomposition → Skill selection → Dependency resolution → Loading → Caching
    """

    def __init__(
        self,
        registry: SkillRegistry,
        selector: SkillSelector,
        resolver: SkillDependencyResolver,
        loader: SkillLoader,
        cache: SkillCache,
        profiler: SkillProfiler,
    ) -> None:
        self._registry = registry
        self._selector = selector
        self._resolver = resolver
        self._loader = loader
        self._cache = cache
        self._profiler = profiler
        self._lock = threading.RLock()
        self._distributions: dict[str, SkillDistribution] = {}
        self._history: list[dict] = []

    def distribute(
        self,
        mission_id: str,
        agent_tasks: dict[str, dict],  # agent_id → {description, categories, technologies, capabilities}
        max_skills_per_agent: int = 5,
    ) -> SkillDistribution:
        """Distribute skills to agents based on their assigned tasks."""
        with self._lock:
            distribution = SkillDistribution(mission_id=mission_id)

            for agent_id, task_info in agent_tasks.items():
                selections = self._selector.select(
                    task_description=task_info.get("description", ""),
                    categories=task_info.get("categories"),
                    technologies=task_info.get("technologies"),
                    agent_capabilities=task_info.get("capabilities"),
                    max_skills=max_skills_per_agent,
                )
                distribution.assignments[agent_id] = selections

                # Compute totals
                for sel in selections:
                    distribution.total_memory_mb += sel.estimated_cost_mb
                    distribution.total_tokens += sel.estimated_tokens

            self._distributions[distribution.id] = distribution

            self._history.append({
                "distribution_id": distribution.id,
                "mission_id": mission_id,
                "agents": list(agent_tasks.keys()),
                "total_skills": sum(len(s) for s in distribution.assignments.values()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._history) > 500:
                self._history = self._history[-500:]

            return distribution

    def load_distribution(self, distribution: SkillDistribution, agent_id: str) -> list[str]:
        """Load all skills for one agent's portion of a distribution."""
        loaded: list[str] = []

        for sel in distribution.assignments.get(agent_id, []):
            # Check cache first
            cached = self._cache.get(sel.skill_id)
            if cached:
                loaded.append(sel.skill_id)
                continue

            # Load
            instance = self._loader.load(
                sel.skill_id,
                agent_id=agent_id,
                mission_id=distribution.mission_id,
            )
            if instance and instance.load_state.value == "loaded":
                self._cache.put(sel.skill_id)
                loaded.append(sel.skill_id)

        return loaded

    def unload_agent_skills(self, agent_id: str) -> int:
        """Unload all skills for an agent."""
        count = 0
        for instance in self._loader.get_all_loaded():
            if instance.agent_id == agent_id:
                if self._loader.unload(instance.id):
                    self._cache.evict(instance.skill_id)
                    count += 1
        return count

    def clean_mission(self, mission_id: str) -> int:
        """Unload all skills for a completed mission."""
        count = 0
        for instance in self._loader.get_all_loaded():
            if instance.mission_id == mission_id:
                if self._loader.unload(instance.id):
                    self._cache.evict(instance.skill_id)
                    count += 1
        return count

    def get_distribution(self, distribution_id: str) -> Optional[SkillDistribution]:
        with self._lock:
            return self._distributions.get(distribution_id)

    def list_distributions(self) -> list[SkillDistribution]:
        with self._lock:
            return list(self._distributions.values())

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def stats(self) -> dict:
        with self._lock:
            total_skills = sum(
                len(s) for d in self._distributions.values() for s in d.assignments.values()
            )
            return {
                "total_distributions": len(self._distributions),
                "total_skills_distributed": total_skills,
                "loaded": self._loader.count_loaded(),
                "cached": self._cache.size(),
            }
