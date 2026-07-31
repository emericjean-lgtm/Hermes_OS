"""Execution state machine for HOS-050 — manages lifecycle transitions."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .execution_models import (
    ExecutionCheckpoint,
    ExecutionMeta,
    ExecutionState,
    CheckpointType,
)


class ExecutionStateMachine:
    """Thread-safe state machine for mission execution lifecycle.

    Valid transitions:
        CREATED → PLANNING → READY → RUNNING → (VALIDATING → COMPLETED | FAILED)
                             ↓         ↓           ↓
                          CANCELLED  PAUSED → RUNNING (resume)
                                     WAITING_APPROVAL → RUNNING
    """

    VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
        ExecutionState.CREATED:           {ExecutionState.PLANNING, ExecutionState.CANCELLED},
        ExecutionState.PLANNING:          {ExecutionState.READY, ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.READY:             {ExecutionState.RUNNING, ExecutionState.CANCELLED},
        ExecutionState.RUNNING:           {ExecutionState.PAUSED, ExecutionState.WAITING_APPROVAL,
                                          ExecutionState.VALIDATING, ExecutionState.FAILED,
                                          ExecutionState.COMPLETED, ExecutionState.CANCELLED},
        ExecutionState.WAITING_APPROVAL:  {ExecutionState.RUNNING, ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.PAUSED:            {ExecutionState.RUNNING, ExecutionState.CANCELLED},
        ExecutionState.VALIDATING:        {ExecutionState.COMPLETED, ExecutionState.RUNNING,
                                          ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.COMPLETED:         set(),
        ExecutionState.FAILED:            {ExecutionState.RUNNING, ExecutionState.CANCELLED},  # retry
        ExecutionState.CANCELLED:         set(),
    }

    def __init__(self, meta: ExecutionMeta | None = None) -> None:
        self._lock = threading.RLock()
        self._state: ExecutionState = ExecutionState.CREATED
        self._history: list[tuple[ExecutionState, ExecutionState, str]] = []
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._meta = meta or ExecutionMeta()

    @property
    def state(self) -> ExecutionState:
        with self._lock:
            return self._state

    @property
    def history(self) -> list[tuple[ExecutionState, ExecutionState, str]]:
        with self._lock:
            return list(self._history)

    def can_transition(self, target: ExecutionState) -> bool:
        with self._lock:
            return target in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, target: ExecutionState, reason: str = "") -> ExecutionState:
        """Attempt a state transition. Returns the new state or raises ValueError."""
        with self._lock:
            if target not in self.VALID_TRANSITIONS.get(self._state, set()):
                allowed = self.VALID_TRANSITIONS.get(self._state, set())
                raise ValueError(
                    f"Invalid transition: {self._state.value} → {target.value}. "
                    f"Allowed: {[s.value for s in allowed]}"
                )
            old = self._state
            self._state = target
            self._history.append((old, target, reason))
            return self._state

    def save_checkpoint(self, checkpoint_type: CheckpointType = CheckpointType.AUTO,
                        metadata: dict[str, Any] | None = None) -> ExecutionCheckpoint:
        with self._lock:
            cp = ExecutionCheckpoint(
                execution_id=self._meta.execution_id,
                checkpoint_type=checkpoint_type,
                state=self._state,
                metadata_snapshot=metadata or {},
            )
            self._checkpoints[cp.checkpoint_id] = cp
            return cp

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            return self._checkpoints.get(checkpoint_id)

    def get_last_checkpoint(self) -> ExecutionCheckpoint | None:
        with self._lock:
            if not self._checkpoints:
                return None
            # max() returns the *first* of several equal maxima, and two
            # checkpoints saved inside one clock tick share created_at — which
            # is routine on Windows, whose clock is coarse. Iterating the
            # insertion-ordered dict backwards makes the most recently saved
            # checkpoint win such ties, which is what "last" means here.
            return max(reversed(self._checkpoints.values()), key=lambda c: c.created_at)

    def is_terminal(self) -> bool:
        return self.state in {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}

    def is_active(self) -> bool:
        return self.state in {ExecutionState.RUNNING, ExecutionState.VALIDATING}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "history_length": len(self._history),
                "checkpoints": len(self._checkpoints),
                "is_terminal": self.is_terminal(),
                "is_active": self.is_active(),
            }
