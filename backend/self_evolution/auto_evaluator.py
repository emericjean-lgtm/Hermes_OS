"""auto_evaluator — cahier des charges §20 (self-evolution): evaluates a task's
success/failure once it reaches a terminal status.

Deterministic on purpose: Task.status is already the ground truth of an
execution's outcome (Kronos maintains it, see task_manager.py), so
nothing here needs an LLM call — matching self-evolution's own classification in
the cahier des charges' architecture table as a plain Python module,
unlike the model-backed agents in config/agents.yaml.
"""
from __future__ import annotations

from backend.tasks.task_manager import Task, TaskStatus

_SUCCESS_STATUSES = {TaskStatus.DONE}
_FAILURE_STATUSES = {TaskStatus.CANCELLED}
_PARTIAL_STATUSES = {TaskStatus.PARTIALLY_SUCCESSFUL}
TERMINAL_STATUSES = _SUCCESS_STATUSES | _FAILURE_STATUSES | _PARTIAL_STATUSES


def is_terminal(task: Task) -> bool:
    return TaskStatus(task.status) in TERMINAL_STATUSES


def evaluate(task: Task) -> bool | None:
    """True = clean success, False = failure, None = either not yet
    terminal or only a partial success — counted in progression stats
    (progression_tracker.py) but not a clean-enough signal to extract a
    skill from or reinforce one with (skill_extractor.py only acts on
    True)."""
    status = TaskStatus(task.status)
    if status in _SUCCESS_STATUSES:
        return True
    if status in _FAILURE_STATUSES:
        return False
    return None
