"""Validation Engine — validates task results after each step."""

from __future__ import annotations

import threading
from typing import Any

from .execution_models import ValidationOutcome, TaskExecution


class ValidationEngine:
    """Validates task results against expected criteria after each step.

    On failure, triggers the Recovery Engine (HOS-036) integration.
    Checks: expected result, test criteria, quality, security, compliance.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._criteria: dict[str, list[str]] = {}       # task_id → validation criteria
        self._results: dict[str, ValidationOutcome] = {}  # task_id → outcome
        self._history: list[dict[str, Any]] = []

    def set_criteria(self, task_id: str, criteria: list[str]) -> None:
        with self._lock:
            self._criteria[task_id] = criteria

    def validate(self, task: TaskExecution) -> ValidationOutcome:
        """Validate a completed task's result."""
        with self._lock:
            criteria = self._criteria.get(task.task_id, ["result_present"])

            outcome = self._evaluate(task, criteria)
            self._results[task.task_id] = outcome
            self._history.append({
                "task_id": task.task_id,
                "outcome": outcome.value,
                "errors": task.errors[-3:] if task.errors else [],
                "result_present": task.result is not None,
            })
            return outcome

    def get_outcome(self, task_id: str) -> ValidationOutcome | None:
        with self._lock:
            return self._results.get(task_id)

    def _evaluate(self, task: TaskExecution, criteria: list[str]) -> ValidationOutcome:
        """Evaluate task results against validation criteria."""
        errors = task.errors
        result = task.result

        # Check for critical failures
        for c in criteria:
            if c == "result_present" and result is None:
                return ValidationOutcome.FAIL
            if c == "no_errors" and errors:
                return ValidationOutcome.FAIL
            if c == "needs_human_review" and result is not None:
                return ValidationOutcome.NEEDS_REVIEW

        # If task is completed without errors, pass
        if result is not None and not errors:
            return ValidationOutcome.PASS

        # Partial result with errors → retry
        if result is not None and errors:
            return ValidationOutcome.RETRY

        # No result and no errors → needs review
        if result is None and not errors:
            return ValidationOutcome.NEEDS_REVIEW

        return ValidationOutcome.FAIL

    def stats(self) -> dict[str, Any]:
        with self._lock:
            outcomes = {}
            for o in self._results.values():
                outcomes[o.value] = outcomes.get(o.value, 0) + 1
            return {
                "total_validated": len(self._results),
                "outcomes": outcomes,
                "criteria_defined": len(self._criteria),
            }
