"""Recovery Manager for Hermes OS (HOS-062).

Detects component failures and performs controlled restart/recovery
with cooldown and backoff.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable


class RecoveryManager:
    """Manages controlled recovery from component failures."""

    def __init__(self, max_attempts: int = 3, cooldown_s: int = 60):
        self._max_attempts = max_attempts
        self._cooldown_s = cooldown_s
        self._lock = threading.RLock()
        self._attempts: dict[str, list[float]] = {}
        self._recovery_actions: dict[str, Callable[[], bool]] = {}
        self._recovery_history: list[dict[str, Any]] = []
        self._max_history = 500

    # ── Public API ──

    def register_recovery(self, component: str, recover_fn: Callable[[], bool]) -> None:
        with self._lock:
            self._recovery_actions[component] = recover_fn

    def trigger_recovery(self, component: str, reason: str = "") -> bool:
        """Attempt to recover a component. Returns True if recovery succeeded."""
        with self._lock:
            if component not in self._recovery_actions:
                self._log_recovery(component, "failed", f"No recovery action registered: {reason}")
                return False

            now = time.time()
            attempts = self._attempts.get(component, [])

            # Prune old attempts outside cooldown
            attempts = [t for t in attempts if now - t < self._cooldown_s]

            if len(attempts) >= self._max_attempts:
                self._log_recovery(component, "skipped",
                                   f"Max attempts ({self._max_attempts}) reached: {reason}")
                return False

            # Check cooldown
            if attempts and (now - attempts[-1] < self._cooldown_s):
                remaining = int(self._cooldown_s - (now - attempts[-1]))
                self._log_recovery(component, "cooldown",
                                   f"In cooldown ({remaining}s remaining): {reason}")
                return False

            # Attempt recovery
            try:
                recover_fn = self._recovery_actions[component]
                success = recover_fn()
                attempts.append(time.time())
                self._attempts[component] = attempts

                if success:
                    self._log_recovery(component, "success", f"Recovered: {reason}")
                    self._attempts[component] = []  # Reset attempts on success
                    return True
                else:
                    self._log_recovery(component, "failed", f"Recovery failed: {reason}")
                    return False
            except Exception as e:
                attempts.append(time.time())
                self._attempts[component] = attempts
                self._log_recovery(component, "error", f"Recovery error: {e}: {reason}")
                return False

    def get_status(self, component: str) -> dict[str, Any]:
        with self._lock:
            attempts = self._attempts.get(component, [])
            now = time.time()
            recent = [t for t in attempts if now - t < self._cooldown_s]
            return {
                "component": component,
                "recent_attempts": len(recent),
                "has_recovery": component in self._recovery_actions,
                "max_attempts": self._max_attempts,
                "cooldown_s": self._cooldown_s,
                "in_cooldown": bool(recent) and (now - recent[-1] < self._cooldown_s),
                "recovery_available": component in self._recovery_actions,
            }

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._recovery_history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._recovery_history)
            successes = sum(1 for h in self._recovery_history if h["result"] == "success")
            failures = sum(1 for h in self._recovery_history if h["result"] == "failed")
            return {
                "total_attempts": total,
                "successes": successes,
                "failures": failures,
                "success_rate": (successes / total * 100) if total > 0 else 0.0,
                "components_with_recovery": list(self._recovery_actions.keys()),
            }

    def reset_attempts(self, component: str) -> None:
        with self._lock:
            if component in self._attempts:
                self._attempts[component] = []

    def reset_all(self) -> None:
        with self._lock:
            self._attempts.clear()

    # ── Private ──

    def _log_recovery(self, component: str, result: str, message: str) -> None:
        entry = {
            "component": component,
            "result": result,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._recovery_history.append(entry)
        if len(self._recovery_history) > self._max_history:
            self._recovery_history = self._recovery_history[-self._max_history:]
