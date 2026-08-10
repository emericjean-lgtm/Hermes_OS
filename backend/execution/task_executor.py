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

Known, documented limitation (HOS-069 audit, not fixed here — see
``_build_messages()``'s own docstring for the detail): this executor performs
one chat completion per task. ``assigned_tools`` (AgentCoordinator's pick) is
mentioned to the model as a text hint, never invoked as a real tool/MCP call.
Nothing here bypasses Aegis's tool-call security gate, because no real tool
call exists on this path for it to gate.
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
        on_runtime_result: ``(runtime_id, duration_ms, success) -> None``,
            called alongside ``on_execution`` with the runtime that actually
            served (or was attempted for) this call. The bootstrap wires
            this to the RAL runtime registry's health monitor (HOS-072),
            which otherwise never learned from a real execution either —
            ``GET /api/v1/runtimes`` reported permanently-empty metrics.
        num_ctx_for: maps a task to the context window to request — the
            per-role value real benchmarks informed (HOS-065C), not the one
            global default every call used to fall back to regardless of
            which model answered it. None (the default) preserves the old
            behaviour: the client's own configured default applies.
        cloud_chat: same shape as ``chat``, talking to OpenRouter instead of
            Ollama (HOS-066C). None (the default) disables cloud entirely —
            every task runs local, unchanged from before this existed.
        runtime_for: maps a task to ``"openrouter"``/``"ollama"``/None — the
            runtime AdaptiveRouter actually chose for it. Only ``"openrouter"``
            with ``cloud_chat`` set attempts a cloud call; anything else runs
            local exactly as before.
        local_fallback_for: maps a task to a real *local* model to retry
            against if the cloud call fails for any reason (quota exhausted,
            network error, model unavailable). Retrying against a real,
            different runtime is not fabrication — it is the automatic
            cloud-to-local fallback the escalation feature exists for.
        timeout_s: hard ceiling on one inference call.
        resource_manager: real GPU/VRAM telemetry (HOS-069,
            backend/runtime/resources/resource_manager.py — already existed,
            was never consulted by anything in the execution path). None
            (the default) disables admission checking entirely, matching
            prior behaviour: a task never waited for VRAM before this.
        vram_gb_for: maps a resolved model tag to its measured VRAM
            footprint (config/models.yaml's ``vram_gb``, from HOS-065C's
            real benchmarks — not a guess). Required alongside
            ``resource_manager`` for admission checking to actually run;
            either alone is a no-op.
        vram_wait_s / vram_poll_interval_s: how long to wait for VRAM to
            free up (another task finishing) before failing the task as
            ``RuntimeUnavailableError`` rather than risking the exact
            VRAM-exhaustion GraphExecutor's bounded parallelism (HOS-068)
            was already built to avoid.
        list_running_for / unload_for: real resident-model listing and
            active unload (HOS-072) — past the halfway point of the VRAM
            wait above, actively frees another resident model's VRAM
            instead of only ever waiting for its own keep_alive timer
            (up to 10 minutes by default). None (the default) builds real
            Ollama calls on demand; tests inject fakes to stay hermetic.
    """

    def __init__(
        self,
        chat: Optional[Callable[..., Any]] = None,
        *,
        model_for: Optional[Callable[[Any], str]] = None,
        workspace_manager: Any = None,
        on_event: Optional[Callable] = None,
        on_execution: Optional[Callable[[Any, str, float, int, bool], None]] = None,
        on_runtime_result: Optional[Callable[[str, float, bool], None]] = None,
        num_ctx_for: Optional[Callable[[Any], Optional[int]]] = None,
        cloud_chat: Optional[Callable[..., Any]] = None,
        runtime_for: Optional[Callable[[Any], Optional[str]]] = None,
        local_fallback_for: Optional[Callable[[Any], Optional[str]]] = None,
        timeout_s: float = 180.0,
        default_model: str = "qwen3.5:4b",
        resource_manager: Any = None,
        vram_gb_for: Optional[Callable[[str], Optional[float]]] = None,
        vram_wait_s: float = 20.0,
        vram_poll_interval_s: float = 1.0,
        list_running_for: Optional[Callable[[], Any]] = None,
        unload_for: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._chat = chat
        self._model_for = model_for
        self._workspace = workspace_manager
        self._on_event = on_event
        self._on_execution = on_execution
        self._on_runtime_result = on_runtime_result
        self._num_ctx_for = num_ctx_for
        self._cloud_chat = cloud_chat
        self._runtime_for = runtime_for
        self._local_fallback_for = local_fallback_for
        self._timeout_s = timeout_s
        self._default_model = default_model
        self._resource_manager = resource_manager
        self._vram_gb_for = vram_gb_for
        self._vram_wait_s = vram_wait_s
        self._vram_poll_interval_s = vram_poll_interval_s
        self._list_running_for = list_running_for
        self._unload_for = unload_for

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
        num_ctx = self._resolve_num_ctx(task)
        messages = self._build_messages(task, assignment)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)

        chat = self._chat or self._default_chat
        use_cloud = self._cloud_chat is not None and self._resolve_runtime(task) == "openrouter"
        if use_cloud:
            runtime_id = "openrouter"
        requested_runtime = runtime_id

        started = time.perf_counter()
        try:
            active_chat = self._cloud_chat if use_cloud else chat
            if not use_cloud:
                self._check_vram_admission(model)
            response = self._run_coro(
                active_chat(messages=messages, model=model, num_ctx=num_ctx), self._timeout_s
            )
        except Exception as exc:
            if use_cloud:
                # A real, different runtime exists (local) — retrying against
                # it is not fabrication, it is the automatic cloud-to-local
                # fallback this feature exists for. Any cloud failure
                # triggers it, not just quota exhaustion: a network hiccup or
                # a model going away deserves the same honest recovery.
                logger.warning(
                    "cloud runtime failed for task %s (%s: %s) — falling back to local",
                    getattr(task, "task_id", "?"), type(exc).__name__, exc,
                )
                fallback_model = self._resolve_local_fallback(task) or self._default_model
                try:
                    self._check_vram_admission(fallback_model)
                    response = self._run_coro(
                        chat(messages=messages, model=fallback_model, num_ctx=num_ctx),
                        self._timeout_s,
                    )
                    model = fallback_model
                    runtime_id = "ollama"
                except Exception as exc2:
                    self._record_failure()
                    self._report_execution(task, fallback_model,
                                           (time.perf_counter() - started) * 1000.0, 0, False,
                                           runtime_id="ollama")
                    raise RuntimeUnavailableError(
                        f"cloud runtime failed ({type(exc).__name__}: {exc}) and "
                        f"the local fallback also failed: {type(exc2).__name__}: {exc2}"
                    ) from exc2
            elif isinstance(exc, RuntimeUnavailableError):
                self._record_failure()
                self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False,
                                       runtime_id=runtime_id)
                raise
            elif isinstance(exc, asyncio.TimeoutError):
                self._record_failure()
                self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False,
                                       runtime_id=runtime_id)
                raise RuntimeUnavailableError(
                    f"runtime {runtime_id!r} timed out after {self._timeout_s:.0f}s"
                ) from exc
            else:
                self._record_failure()
                self._report_execution(task, model, (time.perf_counter() - started) * 1000.0, 0, False,
                                       runtime_id=runtime_id)
                # Anything the runtime layer raises means the work did not happen.
                raise RuntimeUnavailableError(
                    f"runtime {runtime_id!r} could not execute task "
                    f"{getattr(task, 'task_id', '?')}: {type(exc).__name__}: {exc}"
                ) from exc

        duration_ms = (time.perf_counter() - started) * 1000.0
        content, meta = self._read_response(response)

        if not content.strip():
            self._record_failure()
            self._report_execution(task, model, duration_ms, 0, False, runtime_id=runtime_id)
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
                "runtime_requested": requested_runtime,
                "token_counts": "reported" if meta.get("prompt_tokens") else "estimated",
            },
        )
        outcome.artifact_path = self._persist_artifact(task, outcome)
        self._report_execution(task, outcome.model, duration_ms,
                                outcome.prompt_tokens + outcome.completion_tokens, True,
                                runtime_id=outcome.runtime_id)

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

    async def _default_chat(self, *, messages: list[dict[str, Any]], model: str,
                            num_ctx: Optional[int] = None) -> Any:
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
            default_num_ctx=num_ctx if num_ctx is not None
                            else getattr(settings, "ollama_num_ctx", 8192),
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

    async def _default_list_running(self) -> list[dict[str, Any]]:
        """Real resident models, from Ollama's own /api/ps (HOS-072) —
        used by ``_try_free_vram_actively`` to pick which model to unload.
        Same client-construction pattern as ``_default_chat``."""
        from backend.connectors.ollama_client import OllamaClient
        from backend.core.config import get_settings

        settings = get_settings()
        client = OllamaClient(settings.ollama_api_url, timeout=10.0)
        try:
            return await client.list_running_models()
        finally:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("closing Ollama client failed", exc_info=True)

    async def _default_unload(self, model: str) -> None:
        """Actively free ``model``'s VRAM now (HOS-072) — see
        ``OllamaClient.unload_model``'s own docstring."""
        from backend.connectors.ollama_client import OllamaClient
        from backend.core.config import get_settings

        settings = get_settings()
        client = OllamaClient(settings.ollama_api_url, timeout=15.0)
        try:
            await client.unload_model(model)
        finally:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("closing Ollama client failed", exc_info=True)

    def _resolve_runtime(self, task: Any) -> Optional[str]:
        if self._runtime_for is not None:
            try:
                return self._runtime_for(task)
            except Exception:
                logger.debug("runtime_for callback failed", exc_info=True)
        return None

    def _resolve_local_fallback(self, task: Any) -> Optional[str]:
        if self._local_fallback_for is not None:
            try:
                return self._local_fallback_for(task)
            except Exception:
                logger.debug("local_fallback_for callback failed", exc_info=True)
        return None

    def _check_vram_admission(self, model: str) -> None:
        """Wait for real VRAM headroom before starting local inference
        (HOS-069) — the check GraphExecutor's bounded parallelism (HOS-068)
        reduced the *odds* of needing but never actually performed.

        Conservative by construction: it does not know whether ``model`` is
        already resident in Ollama (that isn't introspected here), so it
        always asks for its full footprint — occasionally waiting when the
        model was already loaded and would have needed no more VRAM, never
        the other way around. A no-op unless both ``resource_manager`` and
        ``vram_gb_for`` are wired (opt-in; prior behaviour otherwise).
        """
        if self._resource_manager is None or self._vram_gb_for is None:
            return
        try:
            vram_gb = self._vram_gb_for(model)
        except Exception:
            logger.debug("vram_gb_for callback failed for %s", model, exc_info=True)
            return
        if not vram_gb or vram_gb <= 0:
            return
        bytes_requested = int(vram_gb * 1024 ** 3)

        deadline = time.monotonic() + self._vram_wait_s
        reason = "insufficient VRAM"
        tried_unload = False
        while True:
            result = self._resource_manager.can_allocate(
                bytes_requested, "ollama", model_name=model,
            )
            if result.success:
                return
            reason = result.reason or reason
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeUnavailableError(
                    f"no VRAM admission for {model!r} ({vram_gb:.1f}GB "
                    f"requested) after {self._vram_wait_s:.0f}s: {reason}"
                )
            # HOS-072: past the halfway point with still no admission,
            # actively free VRAM instead of only ever waiting for another
            # resident model's own keep_alive timer to expire (up to 10
            # minutes by default — far longer than this admission wait).
            # Once per call: a second, different resident model failing to
            # help isn't worth repeating.
            if not tried_unload and remaining <= self._vram_wait_s / 2:
                tried_unload = True
                self._try_free_vram_actively(exclude_model=model)
            time.sleep(self._vram_poll_interval_s)

    def _try_free_vram_actively(self, *, exclude_model: str) -> None:
        """Unload the largest *other* resident Ollama model to free real
        VRAM now (HOS-072), instead of passively waiting for its own
        keep_alive timer. Best-effort and silent on any failure — a task
        that could not free extra VRAM this way still gets the rest of its
        normal admission wait, unaffected."""
        list_running = self._list_running_for or self._default_list_running
        unload = self._unload_for or self._default_unload
        try:
            resident = self._run_coro(list_running(), 10.0)
            victims = [
                m for m in resident
                if str(m.get("name") or m.get("model") or "") != exclude_model
            ]
            if not victims:
                return
            victim = max(victims, key=lambda m: int(m.get("size_vram", 0) or 0))
            victim_name = str(victim.get("name") or victim.get("model") or "")
            if not victim_name:
                return
            self._run_coro(unload(victim_name), 15.0)
            logger.info(
                "proactively unloaded %r to free VRAM for %r", victim_name, exclude_model,
            )
        except Exception:
            logger.debug("proactive VRAM unload failed", exc_info=True)

    def _resolve_model(self, task: Any, assignment: Any) -> str:
        # HOS-069: on a genuine retry (task.retries > 0 — MissionExecutor
        # already re-invokes this whole method for a RETRY outcome or a
        # RuntimeUnavailableError), prefer a real alternative over asking
        # the same primary-model call to fail the same way again. Reuses
        # local_fallback_for rather than adding a second recommendation
        # path — the same real, local-only (allow_cloud=False) ranking
        # already wired for HOS-066C's cloud-to-local fallback, just
        # consulted first instead of only after a cloud failure.
        if getattr(task, "retries", 0) > 0 and self._local_fallback_for is not None:
            try:
                fallback = self._local_fallback_for(task)
                if fallback:
                    return str(fallback)
            except Exception:
                logger.debug("local_fallback_for callback failed on retry", exc_info=True)
        if self._model_for is not None:
            try:
                chosen = self._model_for(task)
                if chosen:
                    return str(chosen)
            except Exception:
                logger.debug("model_for callback failed", exc_info=True)
        return self._default_model

    def _resolve_num_ctx(self, task: Any) -> Optional[int]:
        if self._num_ctx_for is not None:
            try:
                return self._num_ctx_for(task)
            except Exception:
                logger.debug("num_ctx_for callback failed", exc_info=True)
        return None

    @staticmethod
    def _build_messages(task: Any, assignment: Any) -> list[dict[str, Any]]:
        """Build the one chat completion this execution actually is.

        HOS-069 audit finding, documented rather than silently left as-is:
        ``tools`` below is a *text hint* in the system prompt ("Available
        tools: X, Y"), not a real tool-calling mechanism. This method never
        passes an OpenAI/Ollama-style ``tools=[...]`` schema to the runtime,
        and nothing downstream parses the model's response for a function
        call and actually invokes anything — no filesystem, git, or MCP
        call is ever made from this execution path. A model asked to "use"
        a tool can only produce text that *looks* like a tool invocation
        (e.g. a line reading ``klaatcode.analyze_project --config-file
        ...``), which is then stored as the task's real, honestly-reported
        result — text output, not a tool's actual return value. Aegis's
        Policy/Permission/Trust gate for tool calls is therefore never
        bypassed by this path: there is no real tool call here for it to
        gate. Wiring genuine tool-calling (a real function-call loop, each
        call gated by Aegis before it runs) is a separate, materially
        larger initiative — not something to half-implement inside this
        method.
        """
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
                          tokens_used: int, success: bool,
                          runtime_id: str = "") -> None:
        if runtime_id and self._on_runtime_result is not None:
            try:
                self._on_runtime_result(runtime_id, duration_ms, success)
            except Exception:  # pragma: no cover - feedback must never break execution
                logger.debug("runtime health feedback failed", exc_info=True)
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
