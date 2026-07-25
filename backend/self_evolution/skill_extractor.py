"""skill_extractor — cahier des charges §20 (self-evolution): turns a successfully
completed task into a reusable skill candidate.

Deterministic extraction from the task's own fields (title/objective/
history) — same "no LLM call needed" reasoning as auto_evaluator.py.

A newly extracted skill starts confidence at the midpoint between
SKILL_MIN_CONFIDENCE and SKILL_AUTO_VALIDATE_THRESHOLD: it did succeed
once (so it's above the floor), but a single success hasn't earned full
trust yet (so it starts below the auto-validate threshold, "en
révision" per §20 — see skill_library.status_for()). Reuses that go
well push it up via record_use(); this module only ever creates new
skills, it never reinforces an existing one — matching skill_extractor's
literal job ("détecte une procédure réussie et la transforme en skill")
as distinct from record_use()'s ("met à jour le score de confiance"
in auto_evaluator's slice of §20, exercised on repeat use of a skill
already retrieved for reuse, not on first extraction).
"""
from __future__ import annotations

from backend.core.config import get_settings
from backend.tasks.task_manager import Task


def extract(task: Task) -> dict | None:
    """Returns a skill_library.create_skill()-ready kwargs dict, or None
    if this task has nothing worth turning into a skill (no title)."""
    if not task.title.strip():
        return None

    settings = get_settings()
    initial_confidence = round(
        (settings.skill_min_confidence + settings.skill_auto_validate_threshold) / 2, 4
    )

    procedure_lines = [f"Objective: {task.objective}"] if task.objective.strip() else []
    procedure_lines += [entry["note"] for entry in task.history_list]

    return {
        "name": task.title.strip(),
        "description": task.description.strip(),
        "procedure": "\n".join(procedure_lines),
        "confidence": initial_confidence,
        "tags": [],
        "project_id": task.project_id,
        "source_task_id": task.id,
    }
