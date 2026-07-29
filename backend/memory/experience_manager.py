"""Experience Manager for HOS-047 — extracts lessons, identifies patterns, proposes improvements."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.memory_models import EpisodicMemory


class ExperienceManager:
    """Learns from mission history.

    Extracts lessons, identifies frequent errors, computes best practices,
    and proposes improvements based on past experiences.
    """

    def __init__(
        self,
        episodic: EpisodicMemoryStore,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._episodic = episodic

    def learn_from_mission(self, episode: EpisodicMemory) -> list[str]:
        """Extract lessons from a completed mission."""
        lessons: list[str] = []

        if episode.success:
            lessons.append(f"Mission '{episode.mission_title}' succeeded with {episode.completed_nodes}/{episode.total_nodes} nodes")
            if episode.duration_seconds > 0:
                avg_time = episode.duration_seconds / max(episode.completed_nodes, 1)
                lessons.append(f"Average task duration: {avg_time:.1f}s")
            for model in episode.models_used:
                lessons.append(f"Model '{model}' was effective for this mission type")
        else:
            lessons.append(f"Mission '{episode.mission_title}' failed — {episode.failed_nodes} nodes failed")
            for incident in episode.incidents:
                lessons.append(f"Incident: {incident.get('description', '')}")

        episode.lessons_learned = lessons
        if self._on_event:
            self._on_event("experience.learned", {
                "mission_id": episode.mission_id,
                "lesson_count": len(lessons),
            }, severity="info")
        return lessons

    def find_similar_experiences(
        self, mission_type: str, tags: list[str], limit: int = 5
    ) -> list[EpisodicMemory]:
        """Find past missions similar to a new one."""
        return self._episodic.find_similar(tags, mission_type, limit)

    def get_best_practices(self, mission_type: str = "", limit: int = 10) -> list[str]:
        """Extract best practices from successful missions."""
        episodes = self._episodic.get_successful()
        if mission_type:
            episodes = [e for e in episodes if e.mission_type == mission_type]

        practices: set[str] = set()
        for e in episodes[:limit]:
            for improvement in e.improvements:
                practices.add(improvement)
            for lesson in e.lessons_learned:
                practices.add(lesson)
        return list(practices)[:limit]

    def get_frequent_errors(self, limit: int = 10) -> list[str]:
        """Identify frequent errors from failed missions."""
        failed = self._episodic.get_failed()
        error_counts: dict[str, int] = {}

        for e in failed:
            for incident in e.incidents:
                desc = incident.get("description", "")
                if desc:
                    error_counts[desc] = error_counts.get(desc, 0) + 1

        return sorted(error_counts, key=error_counts.get, reverse=True)[:limit]

    def recommend_for_new_mission(
        self, mission_type: str, tags: list[str]
    ) -> dict:
        """Generate recommendations for a new mission based on past experience."""
        similar = self.find_similar_experiences(mission_type, tags, limit=5)
        best_practices = self.get_best_practices(mission_type)
        frequent_errors = self.get_frequent_errors()

        # Recommend models that worked well
        model_counts: dict[str, int] = {}
        for e in similar:
            for model in e.models_used:
                model_counts[model] = model_counts.get(model, 0) + 1

        return {
            "similar_missions": len(similar),
            "similar_success_rate": round(
                sum(1 for e in similar if e.success) / max(len(similar), 1) * 100, 1
            ) if similar else 0,
            "recommended_models": sorted(model_counts, key=model_counts.get, reverse=True)[:3],
            "best_practices": best_practices[:5],
            "frequent_errors": frequent_errors[:5],
            "past_experiences": [
                {"id": e.episode_id, "title": e.mission_title, "success": e.success}
                for e in similar[:3]
            ],
        }

    def stats(self) -> dict:
        return self._episodic.stats()
