"""Memory Adapter (HOS-055C).

Syncs Oh My Pi task results into Hermes Memory System (HOS-047).
Stores: experiences, effective corrections, code patterns, resolved errors.

Connects: OhMyPiAgent → ExperienceManager → ProceduralMemory → KnowledgeGraph
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


@dataclass
class OhMyPiExperience:
    experience_id: str = ""; task_type: str = ""; language: str = ""
    problem: str = ""; solution: str = ""; files_modified: list[str] = field(default_factory=list)
    success: bool = True; duration_ms: float = 0.0
    errors_resolved: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class OhMyPiMemoryAdapter:
    def __init__(self, memory_manager: Any = None, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._mm = memory_manager; self._on_event = on_event
        self._experiences: dict[str, OhMyPiExperience] = {}
        self._corrections: dict[str, list[str]] = {}
        self._patterns: list[str] = []

    def record_experience(self, experience: OhMyPiExperience) -> None:
        self._experiences[experience.experience_id] = experience
        if experience.success and experience.solution:
            self._corrections.setdefault(experience.task_type, []).append(experience.solution)
            if len(self._corrections[experience.task_type]) > 50:
                self._corrections[experience.task_type] = self._corrections[experience.task_type][-50:]

        if self._mm:
            try:
                from backend.memory.memory_models import EpisodicMemory, ProceduralMemory
                episode = EpisodicMemory(
                    episode_id=experience.experience_id,
                    mission_title=f"OhMyPi {experience.task_type}",
                    mission_type=experience.task_type,
                    success=experience.success,
                    total_nodes=1, completed_nodes=1 if experience.success else 0,
                    failed_nodes=0 if experience.success else 1,
                    duration_seconds=experience.duration_ms / 1000.0,
                    tags=["ohmypi", experience.task_type, f"lang:{experience.language}"],
                    lessons_learned=[f"{experience.problem} → {experience.solution}"],
                )
                self._mm.record_episode(episode)

                if experience.success:
                    procedure = ProceduralMemory(
                        name=f"ohmypi_fix_{experience.task_type}",
                        description=f"Fix pattern: {experience.solution}",
                        category="best_practice",
                        steps=[experience.problem, experience.solution],
                        success_rate=1.0, usage_count=1,
                        tags=["ohmypi", experience.task_type],
                    )
                    self._mm.store_procedure(procedure)
            except Exception: pass

        if self._on_event:
            self._on_event("ohmypi.memory.recorded", {
                "task_type": experience.task_type, "success": experience.success,
            })

    def get_effective_corrections(self, task_type: str, limit: int = 5) -> list[str]:
        return self._corrections.get(task_type, [])[-limit:]

    def find_pattern(self, problem_description: str) -> list[str]:
        """Find matching solutions for a problem description."""
        matches = []
        q = problem_description.lower()
        for exp in self._experiences.values():
            if q in exp.problem.lower():
                matches.append(exp.solution)
        return matches[:5]

    def add_code_pattern(self, pattern: str) -> None:
        self._patterns.append(pattern)
        if len(self._patterns) > 100: self._patterns = self._patterns[-100:]

    def stats(self) -> dict:
        success = sum(1 for e in self._experiences.values() if e.success)
        return {"total_experiences": len(self._experiences),
                "success_rate": round(success / max(len(self._experiences), 1) * 100, 1),
                "patterns_stored": len(self._patterns),
                "corrections_tracked": sum(len(c) for c in self._corrections.values())}
