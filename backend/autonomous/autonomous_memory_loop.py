"""Autonomous Memory Loop for Hermes OS (HOS-063).

After each autonomous mission, captures learnings and feeds them into:
- Episodic Memory
- Procedural Memory
- Evolution Engine
- Experience Manager

Creates a continuous learning feedback loop.
"""

from __future__ import annotations

from typing import Any

from .autonomous_models import AutonomousReport


class AutonomousMemoryLoop:
    """Learning feedback loop that captures outcomes from every mission.

    Collects: success/failure, errors, duration, resources, agents,
    models, tools. Feeds memory and evolution systems.
    """

    def __init__(self) -> None:
        self._memory_manager: Any = None
        self._evolution_engine: Any = None
        self._learnings: list[dict] = []

    def set_memory_manager(self, mm: Any) -> None:
        self._memory_manager = mm

    def set_evolution_engine(self, ee: Any) -> None:
        self._evolution_engine = ee

    def process_report(self, report: AutonomousReport) -> dict[str, Any]:
        """Process an autonomous report into memory and evolution."""
        results = {
            "memory_stored": False,
            "evolution_fed": False,
            "lessons_count": 0,
        }

        # Store in Episodic Memory
        if self._memory_manager and report.goal_id:
            try:
                self._memory_manager.record_episode({
                    "episode_id": f"auto_{report.goal_id}",
                    "mission_title": report.interpreted_goal[:100],
                    "success": report.success,
                    "duration_seconds": report.total_duration_ms / 1000.0,
                    "agents_used": report.agents_used,
                    "tags": ["autonomous"],
                    "lessons_learned": report.lessons,
                })
                results["memory_stored"] = True
            except Exception:
                pass

        # Feed Evolution Engine
        if self._evolution_engine:
            try:
                from .evolution_models import SystemMetrics
                metrics = SystemMetrics(
                    agent_success_rate=1.0 if report.success else 0.5,
                    agent_avg_duration_ms=report.total_duration_ms,
                    mission_avg_duration_s=report.total_duration_ms / 1000.0,
                )
                self._evolution_engine.ingest_metrics(metrics)
                results["evolution_fed"] = True
            except Exception:
                pass

        # Record learnings locally
        learning = {
            "goal_id": report.goal_id,
            "success": report.success,
            "lessons": report.lessons,
            "improvements": report.improvements,
            "timestamp": __import__("time").time(),
        }
        self._learnings.append(learning)

        return results

    def get_learnings(self, limit: int = 50) -> list[dict]:
        return self._learnings[-limit:]

    def get_learning_summary(self) -> dict[str, Any]:
        learnings = self._learnings
        if not learnings:
            return {"missions": 0, "success_rate": 0, "total_lessons": 0}
        success_count = sum(1 for l in learnings if l["success"])
        total_lessons = sum(len(l["lessons"]) for l in learnings)
        return {
            "missions": len(learnings),
            "success_rate": round(success_count / len(learnings) * 100, 1),
            "total_lessons": total_lessons,
        }
