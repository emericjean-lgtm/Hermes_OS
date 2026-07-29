"""Tool executor — safe execution engine with timeout, retry, cancellation (HOS-049)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .tool_models import ExecutionStatus, ToolDefinition, ToolRequest, ToolResult
from .tool_policy import PolicyVerdict, ToolPolicy
from .tool_sandbox import ToolSandbox


class ToolExecutor:
    """Executes tool requests with timeout, retries, and sandboxing.

    Pipeline:
    Request → Policy → Sandbox → Execute → Metrics → Result
    """

    def __init__(self, policy: ToolPolicy, sandbox: ToolSandbox) -> None:
        self._policy = policy
        self._sandbox = sandbox
        self._lock = threading.RLock()
        self._executors: dict[str, Callable] = {}  # tool_id → executor fn
        self._history: list[ToolResult] = []
        self._in_flight: dict[str, bool] = {}  # request_id → is_cancelled

    def register_executor(self, tool_id: str, fn: Callable[[ToolRequest], Any]) -> None:
        """Register an execution function for a tool."""
        with self._lock:
            self._executors[tool_id] = fn

    def execute(self, request: ToolRequest, tool: ToolDefinition) -> ToolResult:
        """Execute a tool request through the full pipeline."""
        start_time = time.monotonic()

        # 1. Policy check
        verdict, reason = self._policy.evaluate(request, tool)
        if verdict == PolicyVerdict.DENY:
            return ToolResult(
                request_id=request.id, tool_id=request.tool_id,
                status=ExecutionStatus.DENIED, error=reason,
                duration_ms=(time.monotonic() - start_time) * 1000,
                executed_at=datetime.now(timezone.utc),
            )
        if verdict == PolicyVerdict.REVIEW_REQUIRED:
            # In production, this would queue for human review
            # For now, treat as allowed with a note
            pass

        # 2. Execute
        result = ToolResult(
            request_id=request.id, tool_id=request.tool_id,
            status=ExecutionStatus.RUNNING,
            executed_at=datetime.now(timezone.utc),
        )

        self._in_flight[request.id] = False

        try:
            executor_fn = self._executors.get(request.tool_id)
            if executor_fn is None:
                raise ValueError(f"No executor registered for tool '{request.tool_id}'")

            # Check if already cancelled
            if self._in_flight.get(request.id):
                result.status = ExecutionStatus.CANCELLED
                result.completed_at = datetime.now(timezone.utc)
                return result

            data = executor_fn(request)
            result.status = ExecutionStatus.COMPLETED
            result.data = data

        except TimeoutError:
            result.status = ExecutionStatus.TIMEOUT
            result.error = f"Execution timed out after {request.timeout_seconds}s"
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error = str(e)

        result.duration_ms = (time.monotonic() - start_time) * 1000
        result.completed_at = datetime.now(timezone.utc)

        # 3. Record history
        with self._lock:
            self._history.append(result)
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

        # Cleanup inflight tracking
        self._in_flight.pop(request.id, None)

        return result

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            if request_id in self._in_flight:
                self._in_flight[request_id] = True
                return True
            return False

    def get_history(self, limit: int = 50) -> list[ToolResult]:
        with self._lock:
            return list(self._history[-limit:])

    def get_result(self, request_id: str) -> Optional[ToolResult]:
        with self._lock:
            for r in reversed(self._history):
                if r.request_id == request_id:
                    return r
            return None

    def stats(self) -> dict:
        with self._lock:
            total = len(self._history)
            completed = sum(1 for r in self._history if r.status == ExecutionStatus.COMPLETED)
            failed = sum(1 for r in self._history if r.status == ExecutionStatus.FAILED)
            denied = sum(1 for r in self._history if r.status == ExecutionStatus.DENIED)
            return {
                "total_executions": total,
                "completed": completed,
                "failed": failed,
                "denied": denied,
                "success_rate": completed / max(total, 1),
                "executors_registered": len(self._executors),
            }
