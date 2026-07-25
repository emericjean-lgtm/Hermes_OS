"""reflection_engine — cahier des charges §20 (self-evolution): a short post-task
reflection (what worked / what failed).

Deterministic templating over the task's own status/history rather than
an LLM call — same reasoning as auto_evaluator/skill_extractor, and it
keeps this gated cleanly behind .env's REFLECTION_ENABLED without
needing a live Ollama server to test. Stored as a Memory entry
(type="reflection") via Echo rather than a new table: the cahier des
charges' schema hints (§24.3) only define memory_long and skills, no
separate reflections table.
"""
from __future__ import annotations

from backend.tasks.task_manager import Task, TaskStatus

_VERDICTS = {
    TaskStatus.DONE: "succeeded",
    TaskStatus.CANCELLED: "was cancelled",
    TaskStatus.PARTIALLY_SUCCESSFUL: "partially succeeded",
}


def reflect(task: Task) -> str | None:
    """Returns a reflection string, or None if the task isn't at a
    terminal status yet (nothing to reflect on)."""
    verdict = _VERDICTS.get(TaskStatus(task.status))
    if verdict is None:
        return None
    steps = "; ".join(entry["note"] for entry in task.history_list)
    if steps:
        return f"Task '{task.title}' {verdict}. History: {steps}"
    return f"Task '{task.title}' {verdict}."
