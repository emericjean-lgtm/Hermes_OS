"""Hermes-native code execution (R-006 Phase 3).

The third CodeIntelligenceRouter candidate, alongside KlaatCode and Oh My
Pi: Hermes's own Model Intelligence -> Runtime -> Ollama path, for task
types that are genuinely one-shot text generation/analysis
(``code_intelligence_router.HERMES_NATIVE_TASK_TYPES``). It exposes the
exact same ``execute_task(task_type, parameters, mission_id=, node_id=)``
-> ``ExecutionResult`` contract ``KlaatCodeAgent``/``OhMyPiAgent`` already
implement, so ``CodeIntelligenceAgent``/``CodeIntelligenceRouter`` treat it
as a third, interchangeable executor rather than a special case.

Uses the same ``ModelRouter``/``OllamaClient`` pair every other real
inference path in Hermes builds (see
``backend/core/bootstrap/service_registry.py::_make_mission_planner`` for
the identical construction) — no second routing or inference engine.
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.agents.agent_models import AgentStatus, ExecutionResult, TaskOutcome
from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.router import ModelRouter, UnknownTaskTypeError

from .capabilities import CI_EVENTS

TASK_LABELS: dict[str, str] = {
    "code_analysis": "code analysis",
    "code_generation": "code generation",
    "refactoring": "refactoring",
    "code_review": "code review",
    "documentation": "documentation",
    "test_generation": "test generation",
    "optimization": "optimization",
}


def _build_messages(task_type: str, parameters: dict[str, Any]) -> list[dict[str, str]]:
    label = TASK_LABELS.get(task_type, task_type)
    code = parameters.get("code") or parameters.get("content") or ""
    instruction = parameters.get("instruction") or parameters.get("prompt") or ""
    project_path = parameters.get("project_path", "")
    language = parameters.get("language", "")

    system = (
        f"You are Hermes OS's native code-intelligence assistant performing "
        f"a {label} task. Answer directly and concretely."
    )
    parts: list[str] = []
    if project_path and project_path != ".":
        parts.append(f"Project path: {project_path}")
    if language:
        parts.append(f"Language: {language}")
    if instruction:
        parts.append(f"Instruction: {instruction}")
    if code:
        parts.append(f"Code:\n```{language}\n{code}\n```")
    user_content = "\n\n".join(parts) or f"Perform a {label} task with no further context provided."

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


class HermesNativeExecutor:
    """Sync `execute_task` bridging into async Ollama, mirroring
    ``backend/execution/task_executor.py``'s dedicated-loop pattern — the
    established way this codebase calls async Ollama from a sync caller."""

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        model_router: ModelRouter,
        agent_id: str = "",
        on_event: Optional[Callable] = None,
    ) -> None:
        self._ollama = ollama_client
        self._router = model_router
        self._on_event = on_event
        self._agent_id = agent_id or f"hermes_native_{uuid.uuid4().hex[:8]}"
        self.status = AgentStatus.READY

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

        self._total_tasks = 0
        self._successful_tasks = 0

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_available(self) -> bool:
        return True

    # ── async/sync bridge ────────────────────────────────────────

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._loop is not None and not self._loop.is_closed():
                return self._loop

            ready = threading.Event()

            def runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(
                target=runner, name="hermes-native-ci-executor", daemon=True,
            )
            self._loop_thread.start()
            ready.wait(timeout=10)
            if self._loop is None:  # pragma: no cover - thread start failure
                raise RuntimeError("could not start the Hermes-native executor event loop")
            return self._loop

    def _run_coro(self, coro: Any, timeout: float) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        with self._loop_lock:
            loop, thread = self._loop, self._loop_thread
            self._loop, self._loop_thread = None, None
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)

    # ── execution ─────────────────────────────────────────────────

    def execute_task(
        self,
        task_type: str,
        parameters: dict[str, Any],
        mission_id: str = "",
        node_id: str = "",
        agent_id_override: str = "",
    ) -> ExecutionResult:
        from backend.integrations.code_intelligence.code_intelligence_models import (
            CodeIntelligenceTaskType,
        )
        from backend.integrations.code_intelligence.code_intelligence_router import (
            HERMES_NATIVE_TASK_TYPES,
        )

        agent = agent_id_override or self._agent_id
        started = datetime.now(timezone.utc)

        try:
            ci_task_type = CodeIntelligenceTaskType(task_type)
        except ValueError:
            ci_task_type = None
        model_task_type = HERMES_NATIVE_TASK_TYPES.get(ci_task_type) if ci_task_type else None
        if model_task_type is None:
            completed = datetime.now(timezone.utc)
            return ExecutionResult(
                context_id=node_id, agent_id=agent, node_id=node_id,
                outcome=TaskOutcome.FAILURE,
                started_at=started, completed_at=completed,
                duration_ms=0.0,
                summary=f"Hermes-native {task_type}: no model mapping",
                error_message=f"{task_type!r} has no Hermes-native routing mapping",
            )

        try:
            running = self._run_coro(self._ollama.list_running_models(), timeout=10)
            loaded = [
                m.get("name") or m.get("model") for m in running if isinstance(m, dict)
            ]
        except Exception:
            loaded = []

        try:
            decision = self._router.select_model(model_task_type, loaded_models=loaded)
        except UnknownTaskTypeError as exc:
            completed = datetime.now(timezone.utc)
            return ExecutionResult(
                context_id=node_id, agent_id=agent, node_id=node_id,
                outcome=TaskOutcome.FAILURE,
                started_at=started, completed_at=completed,
                duration_ms=0.0,
                summary=f"Hermes-native {task_type}: routing failed",
                error_message=str(exc),
            )

        messages = _build_messages(task_type, parameters)
        self._total_tasks += 1
        try:
            response = self._run_coro(
                self._ollama.chat(messages, model=decision.model), timeout=180,
            )
        except Exception as exc:
            completed = datetime.now(timezone.utc)
            duration_ms = (completed - started).total_seconds() * 1000
            self._publish(CI_EVENTS["hermes_native_failed"], {
                "task_type": task_type, "model": decision.model, "error": str(exc),
            })
            return ExecutionResult(
                context_id=node_id, agent_id=agent, node_id=node_id,
                outcome=TaskOutcome.FAILURE,
                started_at=started, completed_at=completed,
                duration_ms=duration_ms,
                summary=f"Hermes-native {task_type} via {decision.model}: failed",
                error_message=str(exc),
            )

        completed = datetime.now(timezone.utc)
        duration_ms = (completed - started).total_seconds() * 1000
        self._successful_tasks += 1
        self._publish(CI_EVENTS["hermes_native_completed"], {
            "task_type": task_type, "model": decision.model, "duration_ms": duration_ms,
        })

        return ExecutionResult(
            context_id=node_id, agent_id=agent, node_id=node_id,
            outcome=TaskOutcome.SUCCESS,
            started_at=started, completed_at=completed,
            duration_ms=duration_ms,
            summary=f"Hermes-native {task_type} via {decision.model}",
            details={
                "data": {
                    "content": response.content,
                    "model": decision.model,
                    "role": decision.role,
                    "tier": decision.tier,
                    "reason": decision.reason,
                },
            },
        )

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass
