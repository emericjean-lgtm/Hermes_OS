"""Real task execution (R-001).

This module replaces the one simulated step in an otherwise real pipeline.
``MissionExecutor.execute_task`` already coordinated an agent, a runtime, skills
and tools, then validated, retried and scheduled — all real. Between the
coordination and the validation sat:

    # 2. Simulate execution (in real system, this calls the agent via runtime)
    task.result = f"Simulated result for: {task.title}"
    task.duration_ms = 42.0  # simulated

So every mission "completed" with a fabricated result and a constant duration,
and the validator — which only checks that a result is present — passed it.
:class:`RealTaskExecutor` is the "calls the agent via runtime" the comment
promised.

Design constraints it has to respect:

* **Never fabricate.** If no runtime can serve the task, it raises
  :class:`RuntimeUnavailableError`. A task that could not run must fail, not
  report success with an invented result.
* **Sync entry point.** ``MissionExecutor`` is synchronous and is called from
  FastAPI's threadpool, while the Ollama client is async. The bridge is a
  dedicated background loop owned by this executor (see :meth:`_run_coro`)
  rather than ``asyncio.run``, which would fail when a loop is already running
  in the calling thread.
* **Real telemetry.** Latency is measured with ``perf_counter``; token counts
  and the model actually used come from the runtime's own response, not from an
  estimate.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.execution.task")


class RuntimeUnavailableError(RuntimeError):
    """No runtime could serve the task.

    A named type so callers can distinguish "the inference layer is down" —
    retryable, and never the task's fault — from "the model produced something
    unusable", which validation handles.
    """


@dataclass
class TaskExecutionOutcome:
    """What actually happened, measured rather than assumed."""

    result: str
    runtime_id: str
    model: str
    duration_ms: float
    prompt_chars: int = 0
    completion_chars: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    artifact_path: str = ""
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def resources(self) -> dict[str, float]:
        """Shape expected by ``TaskExecution.resources_used``."""
        return {
            "duration_ms": round(self.duration_ms, 2),
            "prompt_tokens": float(self.prompt_tokens),
            "completion_tokens": float(self.completion_tokens),
            "total_tokens": float(self.prompt_tokens + self.completion_tokens),
        }


# Rough token estimate, used only when the runtime does not report counts.
# Flagged as an estimate in the metadata so telemetry never presents it as
# measured — the point of R-001 is that reported numbers are real.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN) if text else 0


class RealTaskExecutor:
    """Executes a task by driving a real runtime and recording real telemetry.

    Args:
        chat: ``async (messages, model) -> object`` performing real inference.
            Defaults to the process-wide Ollama client.
        model_for: maps a task/agent to the model to use.
        workspace_manager: when supplied, each result is written as a real
            artifact so the output leaves a trace on disk.
        on_event: the shared event dispatcher.
        on_execution: ``(task, model, duration_ms, tokens_used, success) ->
            None``, called after every attempt — success or failure — with
            measured telemetry. The bootstrap wires this to Model
            Intelligence's profiler (HOS-065), which otherwise never learned
            from a single real execution (see CHANGELOG).
        timeout_s: hard ceiling on one inference call.
    """

    def __init__(
        self,
        chat: Optional[Callable[..., Any]] = None,
        *,
        model_for: Optional[Callable[[Any], str]] = None,
        workspace_manager: Any = None,
        on_event: Optional[Callable] = None,
        on_execution: Optional[Callable[[Any, str, float, int, bool], None]] = None,
        timeout_s: float = 180.0,
        default_model: str = "qwen3:4b",
    ) -> None:
        self._chat = chat
        self._model_for = model_for
        self._workspace = workspace_manager
        self._on_event = on_event
        self._on_execution = on_execution
        self._timeout_s = timeout_s
        self._default_model = default_model

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

        self._lock = threading.Lock()
        self._executions = 0
        self._failures = 0
        self._total_ms = 0.0
        self._total_tokens = 0

    # ── async/sync bridge ────────────────────────────────────────────

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """A dedicated loop in a daemon thread, created on first use.

        Not ``asyncio.run``: this executor is called from FastAPI's threadpool
        and from background schedulers, and ``asyncio.run`` raises if the
        calling thread already has a running loop. Owning one loop also keeps
        the HTTP client's connection pool warm across tasks.
        """
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
                target=runner, name="hermes-task-executor", daemon=True
            )
            self._loop_thread.start()
            ready.wait(timeout=10)
            if self._loop is None:  # pragma: no cover - thread start failure
                raise RuntimeUnavailableError("could not start the executor event loop")
            return self._loop

    def _run_coro(self, coro: Any, timeout: float) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        """Stop the background loop. Called by the bootstrap on shutdown."""
        with self._loop_lock:
            loop, thread = self._loop, self._loop_thread
            self._loop, self._loop_thread = None, None
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)

    # Alias so the bootstrap's shutdown probe finds it.
    shutdown = close

    # ── the real work ────────────────────────────────────────────────

    def execute(self, task: Any, assignment: Any = None) -> TaskExecutionOutcome:
        """Run one task for real, or raise.

        Raises:
            RuntimeUnavailableError: no runtime could serve the task. The caller
                must fail the task — fabricating a result is what R-001 exists
                to remove.
        """
        runtime_id = (getattr(assignment, "runtime_id", "")
                      or getattr(task, "assigned_runtime", "")
                      or "ollama")
        model = self._resolve_model(task, assignment)
        messages = self._build_messages(task, assignment)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)

        chat = self._chat or self._default_chat
        started = time.perf_counter()
        try:
            response = self._run_coro(
                chat(messages=messages, model=model), self._timeout_s
            )
        except RuntimeUnavailableError:
            self._record_failure()
            self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False)
            raise
        except asyncio.TimeoutError as exc:
            self._record_failure()
            self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False)
            raise RuntimeUnavailableError(
                f"runtime {runtime_id!r} timed out after {self._timeout_s:.0f}s"
            ) from exc
        except Exception as exc:
            self._record_failure()
            self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False)
            # Anything the runtime layer raises means the work did not happen.
            raise RuntimeUnavailableError(
                f"runtime {runtime_id!r} could not execute task "
                f"{getattr(task, 'task_id', '?')}: {type(exc).__name__}: {exc}"
            ) from exc

        duration_ms = (time.perf_counter() - started) * 1000.0
        content, meta = self._read_response(response)

        if not content.strip():
            self._record_failure()
            self._report_execution(task, model, duration_ms, 0, False)
            raise RuntimeUnavailableError(
                f"runtime {runtime_id!r} returned an empty completion"
            )

        # The runtime recorded is the one that actually served the request, taken
        # from the response, not the one the coordinator asked for. Reporting the
        # requested runtime would reintroduce exactly the dishonesty R-001 exists
        # to remove — the old report claimed "ktransformers" for work nothing did.
        served_by = str(meta.get("provider") or "").strip() or runtime_id
        outcome = TaskExecutionOutcome(
            result=content,
            runtime_id=served_by,
            model=str(meta.get("model") or model),
            duration_ms=duration_ms,
            prompt_chars=prompt_chars,
            completion_chars=len(content),
            prompt_tokens=int(meta.get("prompt_tokens") or _estimate_tokens(
                "".join(m.get("content", "") for m in messages))),
            completion_tokens=int(meta.get("completion_tokens")
                                  or _estimate_tokens(content)),
            metadata={
                "provider": served_by,
                "runtime_requested": runtime_id,
                "token_counts": "reported" if meta.get("prompt_tokens") else "estimated",
            },
        )
        outcome.artifact_path = self._persist_artifact(task, outcome)
        self._report_execution(task, outcome.model, duration_ms,
                                outcome.prompt_tokens + outcome.completion_tokens, True)

        with self._lock:
            self._executions += 1
            self._total_ms += duration_ms
            self._total_tokens += outcome.prompt_tokens + outcome.completion_tokens

        self._emit("execution.task_completed", {
            "task_id": getattr(task, "task_id", ""),
            "runtime": outcome.runtime_id,
            "model": outcome.model,
            "duration_ms": round(duration_ms, 1),
            "completion_tokens": outcome.completion_tokens,
        })
        logger.info(
            "task %s executed on %s/%s in %.0fms (%d completion tokens)",
            getattr(task, "task_id", "?"), outcome.runtime_id, outcome.model,
            duration_ms, outcome.completion_tokens,
        )
        return outcome

    # ── helpers ──────────────────────────────────────────────────────

    async def _default_chat(self, *, messages: list[dict[str, Any]], model: str) -> Any:
        """Real inference through the configured Ollama endpoint.

        Built from ``get_settings()`` the same way ``get_agent_registry()`` does,
        so this executor talks to whatever endpoint the rest of Hermes talks to
        rather than a hardcoded URL.
        """
        from backend.connectors.ollama_client import (
            OllamaClient,
            OllamaUnavailableError,
        )
        from backend.core.config import get_settings

        settings = get_settings()
        client = OllamaClient(
            settings.ollama_api_url,
            keep_alive=getattr(settings, "ollama_keep_alive", "10m"),
            timeout=self._timeout_s,
            default_num_ctx=getattr(settings, "ollama_num_ctx", 8192),
        )
        try:
            return await client.chat(messages, model=model)
        except OllamaUnavailableError as exc:
            raise RuntimeUnavailableError(f"Ollama unavailable: {exc}") from exc
        finally:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("closing Ollama client failed", exc_info=True)

    def _resolve_model(self, task: Any, assignment: Any) -> str:
        if self._model_for is not None:
            try:
                chosen = self._model_for(task)
                if chosen:
                    return str(chosen)
            except Exception:
                logger.debug("model_for callback failed", exc_info=True)
        return self._default_model

    @staticmethod
    def _build_messages(task: Any, assignment: Any) -> list[dict[str, Any]]:
        title = getattr(task, "title", "") or getattr(task, "task_id", "task")
        agent = getattr(assignment, "agent_id", "") or getattr(task, "assigned_agent", "")
        skills = list(getattr(assignment, "skill_ids", None)
                      or getattr(task, "assigned_skills", []) or [])
        tools = list(getattr(assignment, "tool_ids", None)
                     or getattr(task, "assigned_tools", []) or [])

        system = (
            "You are a Hermes OS execution agent"
            + (f" acting as '{agent}'" if agent else "")
            + ". Carry out the task and return only the requested artifact — no "
              "preamble, no commentary."
        )
        if skills:
            system += f" Relevant skills: {', '.join(skills)}."
        if tools:
            system += f" Available tools: {', '.join(tools)}."

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Task: {title}"},
        ]

    @staticmethod
    def _read_response(response: Any) -> tuple[str, dict[str, Any]]:
        """Pull content and telemetry out of whatever the runtime returned."""
        if isinstance(response, str):
            return response, {}
        content = (getattr(response, "content", None)
                   or (response.get("content") if isinstance(response, dict) else None)
                   or "")
        meta = (getattr(response, "metadata", None)
                or (response.get("metadata") if isinstance(response, dict) else None)
                or {})
        return str(content), dict(meta) if isinstance(meta, dict) else {}

    def _persist_artifact(self, task: Any, outcome: TaskExecutionOutcome) -> str:
        """Write the completion as a real artifact, if a workspace is wired."""
        if self._workspace is None:
            return ""
        creator = getattr(self._workspace, "create_artifact", None)
        if not callable(creator):
            return ""
        try:
            artifact = creator(
                workspace_id=getattr(task, "node_id", "") or getattr(task, "task_id", ""),
                name=f"{getattr(task, 'task_id', 'task')}.md",
                content=outcome.result,
            )
            return str(getattr(artifact, "path", "") or getattr(artifact, "id", ""))
        except Exception:
            logger.debug("artifact persistence failed", exc_info=True)
            return ""

    def _record_failure(self) -> None:
        with self._lock:
            self._failures += 1

    def _report_execution(self, task: Any, model: str, duration_ms: float,
                          tokens_used: int, success: bool) -> None:
        if self._on_execution is None:
            return
        try:
            self._on_execution(task, model, duration_ms, tokens_used, success)
        except Exception:  # pragma: no cover - feedback must never break execution
            logger.debug("model execution feedback failed", exc_info=True)

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(topic, payload)
        except Exception:  # pragma: no cover - a notification must never fail work
            logger.debug("event emission failed", exc_info=True)

    # ── telemetry ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            done = self._executions
            return {
                "executions": done,
                "failures": self._failures,
                "avg_duration_ms": round(self._total_ms / done, 1) if done else 0.0,
                "total_tokens": self._total_tokens,
                "simulated": False,
            }
