"""Autonomous Memory Loop for Hermes OS (HOS-063).

After each autonomous mission, captures learnings and feeds them into:
- Episodic Memory
- Procedural Memory
- Evolution Engine
- Experience Manager

Creates a continuous learning feedback loop.
"""

from __future__ import annotations

import logging
from collections import deque
from itertools import islice
from typing import Any

from .autonomous_models import AutonomousReport

logger = logging.getLogger("hermes_os.autonomous.memory")


class AutonomousMemoryLoop:
    """Learning feedback loop that captures outcomes from every mission.

    Collects: success/failure, errors, duration, resources, agents,
    models, tools. Feeds memory and evolution systems.
    """

    #: Local learning tail. Durable learnings live in episodic memory and the
    #: evolution engine; this list is only the recent window get_learnings()
    #: serves, and it used to grow one entry per mission forever (RC3 P5).
    MAX_RETAINED_LEARNINGS = 1000

    def __init__(self) -> None:
        self._memory_manager: Any = None
        self._evolution_engine: Any = None
        self._learnings: deque[dict] = deque(maxlen=self.MAX_RETAINED_LEARNINGS)

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

        # Store in Episodic Memory.
        #
        # Two bugs used to live here, and they compounded: nothing ever called
        # set_memory_manager(), so this branch was dead in production; and when
        # it did run it passed a plain dict while record_episode() takes an
        # EpisodicMemory, so the bare `except: pass` swallowed the TypeError.
        # After six successful missions the Memory Center still reported
        # episodic.total = 0 (RC3 P2).
        if self._memory_manager and report.goal_id:
            from backend.memory.memory_models import EpisodicMemory

            try:
                self._memory_manager.record_episode(EpisodicMemory(
                    episode_id=f"auto_{report.goal_id}",
                    mission_id=report.goal_id,
                    mission_title=report.interpreted_goal[:100],
                    success=report.success,
                    duration_seconds=report.total_duration_ms / 1000.0,
                    agents_used=list(report.agents_used or []),
                    runtimes_used=list(report.runtimes_used or []),
                    decisions=list(report.decisions or []),
                    lessons_learned=list(report.lessons or []),
                    improvements=list(report.improvements or []),
                ))
                results["memory_stored"] = True
            except Exception:
                # Still non-fatal — a learning write must not fail the mission —
                # but no longer silent.
                logger.warning(
                    "episodic write-back failed for goal %s", report.goal_id,
                    exc_info=True,
                )

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
        if limit <= 0:
            return []
        start = max(len(self._learnings) - limit, 0)
        return list(islice(self._learnings, start, None))

    def get_learning_summary(self) -> dict[str, Any]:
        learnings = list(self._learnings)
        if not learnings:
            return {"missions": 0, "success_rate": 0, "total_lessons": 0}
        success_count = sum(1 for l in learnings if l["success"])
        total_lessons = sum(len(l["lessons"]) for l in learnings)
        return {
            "missions": len(learnings),
            "success_rate": round(success_count / len(learnings) * 100, 1),
            "total_lessons": total_lessons,
        }
