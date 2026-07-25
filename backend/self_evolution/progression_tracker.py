"""progression_tracker — cahier des charges §20 (self-evolution): aggregate stats
(global success rate, skills created, evolution over time) — a read-only
computation over Kronos's tasks and Echo's skills, not its own persisted
state (nothing here needs a table of its own; it's cheap to recompute).
"""
from __future__ import annotations

from backend.core.config import get_settings
from backend.memory.skill_library import Skill, status_for
from backend.self_evolution.auto_evaluator import TERMINAL_STATUSES, evaluate
from backend.tasks.task_manager import Task, TaskStatus


def compute_progression(tasks: list[Task], skills: list[Skill]) -> dict:
    settings = get_settings()

    terminal = [t for t in tasks if TaskStatus(t.status) in TERMINAL_STATUSES]
    successes = sum(1 for t in terminal if evaluate(t) is True)
    success_rate = round(successes / len(terminal), 4) if terminal else None

    statuses = [
        status_for(
            s.confidence,
            min_confidence=settings.skill_min_confidence,
            auto_validate_threshold=settings.skill_auto_validate_threshold,
        )
        for s in skills
    ]

    return {
        "tasks_total": len(tasks),
        "tasks_terminal": len(terminal),
        "tasks_succeeded": successes,
        "success_rate": success_rate,
        "skills_total": len(skills),
        "skills_validated": statuses.count("validated"),
        "skills_in_review": statuses.count("in_review"),
        "skills_below_floor": statuses.count("below_floor"),
        "average_skill_confidence": (
            round(sum(s.confidence for s in skills) / len(skills), 4) if skills else None
        ),
    }
