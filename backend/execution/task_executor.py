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

Known, documented limitation (HOS-069 audit): ``assigned_tools``
(AgentCoordinator's pick, an unrelated keyword-matched recommendation —
see agent_coordinator.py's ``_select_tools``) is still only ever a text
hint, never invoked as a real tool/MCP call. What *is* now real: when a
task's Mission is bound to an ACTIVE, validated Project (Workspace/
Filesystem tool layer, ``workspace_project_for`` below), this executor
offers the model real ``workspace_*`` filesystem tools and actually
executes them — the same real Aegis-gated ``file_tools.py`` calls the
Assistant chat makes, via the shared
``backend/tools/workspace_chat_tools.py`` adapter. This is deliberately
NOT built on ``BaseAgent.respond_events()`` (the chat path's own
tool-calling loop): that method does its own model selection via
``ModelRouter``, which would silently discard this executor's own
model resolution, VRAM admission checking, and cloud/local fallback —
all real, tuned machinery this executor must keep. Instead the loop
below is built directly on the same underlying primitive
(``OllamaClient.chat_events(tools=...)``), bounded the same way
(``_MAX_TOOL_ROUNDS``, mirroring ``agents/base_agent.py``'s own
constant), reusing this executor's already-resolved model/num_ctx.
Nothing here bypasses Aegis's tool-call security gate: every
``workspace_*`` call still goes through ``file_tools.py``'s real
``_check()``/Aegis evaluation exactly like the chat path's calls do.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.execution.task")

#: Repli quand la configuration n'est pas lisible. Le vrai plafond vient de
#: `settings.mission_max_tool_rounds` (HOS-118).
#:
#: Ce module reprenait le 3 de `agents/base_agent.py`, en dur. Le garde-fou
#: est le même — un modèle qui redemande des outils sans jamais répondre ne
#: doit pas bloquer une tâche — mais l'échelle ne l'est pas : un tour de
#: conversation tient en trois échanges, une tâche qui écrit du code et le
#: vérifie n'y tient pas. Confondre les deux plafonnait le travail réel à la
#: patience d'un chat.
_MAX_TOOL_ROUNDS = 3


def _tours_d_outils_max() -> int:
    """Le plafond de tours pour un nœud de mission.

    Lu à chaque boucle plutôt que figé à l'import : le réglage doit pouvoir
    changer sans redémarrer, comme le niveau d'autonomie (HOS-115).
    """
    try:
        from backend.core.config import get_settings

        return max(1, int(get_settings().mission_max_tool_rounds))
    except Exception:  # pragma: no cover - configuration illisible
        return _MAX_TOOL_ROUNDS

#: Toolsets Hermes OS makes available to Hermes Agent for mission work.
#: "coding" is Hermes Agent's own bundle (files, terminal, search, todo,
#: delegate, vision, browser — 32 tools as of v0.19.0). Hermes OS names what
#: is *available*; Hermes alone decides what to actually call. Passing
#: nothing is not a neutral default — it starts the agent with zero tools.
_HERMES_AGENT_TOOLSETS: tuple[str, ...] = ("coding",)

#: Used when the routed model cannot drive an agent loop. A single named
#: model rather than a capability query: this is the last resort *after*
#: capability resolution has already failed.
#:
#: Chosen from measured probe data (HOS-095/096), three trials each on real
#: agentic work:
#:
#:     lfm2.5-2.6b-128k   2.7B   3/3   ~25s warm    1.67 GB
#:     qwen3.5:9b-128k    9.7B   3/3   ~47s        10.18 GB
#:     devstral          23.6B   1/3   ~300s       spills 10.75 GB to CPU
#:     gemma4:12b-64k    11.9B   0/3   timeout      8.49 GB
#:
#: The smallest model wins on every axis: twice as fast as the 9B, six times
#: less VRAM, same perfect rate. It leaves ~14 GB free on a 16 GB card,
#: which is what makes an embedding model and an agent coexist without
#: eviction. LFM2.5 was post-trained with agentic reinforcement learning;
#: the models it beats are general ones asked to act like agents.
#:
#: This constant has moved twice, both times because a measurement refuted
#: the previous choice. It is a starting point for an unprobed deployment,
#: not a verdict — agentic_probe.py is what settles it.
_HERMES_AGENT_FALLBACK_MODEL = "lfm2.5-2.6b-128k"

#: An agent loop is not a completion. The default 180s here was sized for
#: one model call; a Hermes Agent task spawns a process, loads a toolset,
#: and may run up to _MAX_TOOL_ROUNDS of inference-plus-tool-execution on
#: local hardware. Measured: a trivial single-file task already takes
#: 37-57s, so a real multi-step task routinely exceeded 180s and every
#: task in a mission failed with "runtime 'hermes-agent' timed out" —
#: producing a mission that ran for 12 minutes and completed 0/5 tasks.
_HERMES_AGENT_TIMEOUT_S = 900.0


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
        workspace_project_for: ``(task) -> (project_id, project_root) |
            None`` — resolves the task's owning Mission's bound, ACTIVE,
            validated Project (Workspace/Filesystem tool layer). None
            (the default, and whatever this returns for a given task)
            means: behave exactly as before this existed — one plain
            chat completion, no tools. Only when this resolves to a real
            (project_id, project_root) pair does execute() route through
            the real, Aegis-gated workspace tool-calling loop instead.
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
        workspace_project_for: Optional[Callable[[Any], Optional[tuple[str, str]]]] = None,
        hermes_toolsets: tuple[str, ...] = _HERMES_AGENT_TOOLSETS,
        mission_brief_for: Optional[Callable[[Any], Optional[str]]] = None,
        upstream_results_for: Optional[Callable[[Any], Optional[str]]] = None,
        livrables_pour: Optional[Callable[[Any], Optional[str]]] = None,
        agentic_capable_for: Optional[Callable[[str], Optional[bool]]] = None,
        agentic_fallback_model: str = _HERMES_AGENT_FALLBACK_MODEL,
        agentic_timeout_s: float = _HERMES_AGENT_TIMEOUT_S,
    ) -> None:
        self._agentic_timeout_s = agentic_timeout_s
        self._hermes_toolsets = hermes_toolsets
        self._mission_brief_for = mission_brief_for
        self._upstream_results_for = upstream_results_for
        self._livrables_pour = livrables_pour
        self._agentic_capable_for = agentic_capable_for
        self._fallback_model = agentic_fallback_model
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
        self._workspace_project_for = workspace_project_for

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
                      or "hermes-agent")
        model = self._resolve_model(task, assignment)
        num_ctx = self._resolve_num_ctx(task)
        workspace = self._resolve_workspace(task)

        chat = self._chat or self._default_chat
        use_cloud = self._cloud_chat is not None and self._resolve_runtime(task) == "openrouter"
        if use_cloud:
            runtime_id = "openrouter"
        requested_runtime = runtime_id
        hermes_agent_runs_it = (runtime_id == "hermes-agent"
                                and self._chat is None and not use_cloud)

        messages = self._build_messages(
            task, assignment, workspace, hermes_agent=hermes_agent_runs_it,
        )
        prompt_chars = sum(len(m.get("content", "")) for m in messages)

        # HOS-085: when Hermes Agent is the runtime it IS the brain — it owns
        # reasoning, tool selection and tool execution, reaching this very
        # backend's tools through its own MCP client (its config.yaml points
        # mcp_servers at http://127.0.0.1:8010/mcp, the app mounted in
        # backend/main.py). Hermes OS must therefore NOT run its own
        # tool-calling loop on top: doing so made Hermes OS a second
        # cognitive orchestrator and silently bypassed Hermes entirely
        # whenever a mission was workspace-bound. _chat_with_tools_for stays
        # for the explicit local-Ollama runtime, which has no agent of its
        # own and would otherwise get no tools at all.
        boucle_d_outils = False
        if runtime_id == "hermes-agent" and self._chat is None and not use_cloud:
            chat = self._hermes_agent_chat_for(task, workspace)
        elif workspace is not None and not use_cloud:
            chat = self._chat_with_tools_for(workspace)
            boucle_d_outils = True

        started = time.perf_counter()
        try:
            active_chat = self._cloud_chat if use_cloud else chat
            if not use_cloud and runtime_id != "hermes-agent":
                self._check_vram_admission(model)
            response = self._run_coro(
                active_chat(messages=messages, model=model, num_ctx=num_ctx),
                # Une boucle a besoin de son propre budget — voir
                # _HERMES_AGENT_TIMEOUT_S. HOS-121 : la leçon avait été
                # apprise pour `hermes-agent` et jamais appliquée au chemin
                # frère. `_chat_with_tools_for` enchaîne jusqu'à
                # `mission_max_tool_rounds` inférences (12), et les 180 s de
                # `_timeout_s` couvraient la boucle **entière** — 15 s par
                # tour sur un matériel mesuré entre 13 et 89 tok/s.
                #
                # Mesuré sur l'essai Skills360 : la mission a tourné 878 s
                # et terminé 1/7 tâches, un nœud tombant sur
                # « runtime 'default' timed out after 180s » et bloquant les
                # cinq suivants. Signature identique à celle décrite six
                # lignes au-dessus de `_HERMES_AGENT_TIMEOUT_S`.
                self._budget_d_appel(runtime_id, boucle_d_outils),
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
                # Le budget réellement appliqué, pas `_timeout_s` : le
                # message annonçait 180 s même quand la boucle en avait eu
                # 900, ce qui envoyait droit sur la mauvaise constante.
                raise RuntimeUnavailableError(
                    f"runtime {runtime_id!r} timed out after "
                    f"{self._budget_d_appel(runtime_id, boucle_d_outils):.0f}s"
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
                # Real observability for the Workspace/Filesystem tool
                # layer: how many real workspace_* tool calls this task's
                # completion actually made (0 when no workspace was
                # bound, or the model never called one) — see
                # _run_tool_loop's ChatResponse.metadata.
                "tool_calls_made": int(meta.get("tool_calls_made") or 0),
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

    def _hermes_agent_chat_for(
        self, task: Any, workspace: Optional[tuple[str, str]],
    ) -> Callable[..., Any]:
        """A chat-shaped callable that runs the task through the installed
        Hermes Agent (NousResearch/hermes-agent) instead of a bare model call.

        The per-task context is captured in this closure rather than stashed
        on ``self``: the executor is shared and MissionExecutor can run tasks
        concurrently, so instance attributes would let one task read another
        task's workspace — the same reason _chat_with_tools_for is built this
        way.
        """
        project_id, project_root = workspace if workspace is not None else ("", "")
        runtime_ctx = {
            "mission_id": getattr(task, "mission_id", "") or "",
            "task_id": getattr(task, "task_id", "") or "",
            "task_type": getattr(task, "task_type", "") or "",
            "project_id": project_id,
            "workspace": project_root or self._scratch_workspace(task),
            "skills": list(getattr(task, "assigned_skills", []) or []),
            # Without this Hermes Agent starts with "0 tools · 0 skills" and
            # can only *describe* the work — verified live: the same task that
            # merely printed "Creating the file..." with no toolset actually
            # wrote the file once "coding" was passed. The adapter only sends
            # --toolsets when Hermes OS supplies one, so supplying none meant
            # a toolless agent. Hermes still decides which of these tools to
            # use, and when; Hermes OS only says which are available.
            "toolsets": list(self._hermes_toolsets),
        }

        async def _chat(*, messages: list[dict[str, Any]], model: str,
                        num_ctx: Optional[int] = None) -> Any:
            from backend.ral.adapters.hermes_agent_cli import (
                HermesAgentCliConfig,
                HermesAgentCliRuntime,
            )

            model = self._agentic_model(model)
            runtime = HermesAgentCliRuntime(
                HermesAgentCliConfig(model=model, timeout_seconds=self._agentic_timeout_s)
            )
            await runtime.start()
            cap = runtime.get("chat")
            if cap is None:
                raise RuntimeUnavailableError("Hermes Agent chat capability unavailable")
            return await cap.chat(messages, runtime_ctx={
                **runtime_ctx,
                "model": model,
                "policy": {"runtime": "hermes-agent", "num_ctx": num_ctx},
            })

        return _chat

    def _agentic_model(self, model: str) -> str:
        """Keep Hermes Agent off models that cannot drive its tool loop.

        HOS-085 shipped this as a hard-coded list of model names, which was
        a stopgap: it could not answer for a model nobody had thought to
        list. The question is now asked of the model's own capability
        profile (HOS-088) — Ollama's declared tool support, its parameter
        count, and a real measured run where one exists. Substitution is
        logged rather than silent: the router's pick is telemetry-backed
        reasoning, and overriding it is something an operator should see.
        """
        name = (model or "").strip()
        capable: Optional[bool] = None
        if name and self._agentic_capable_for is not None:
            try:
                capable = self._agentic_capable_for(name)
            except Exception:  # pragma: no cover - never fail a task over this
                logger.debug("agentic capability lookup failed for %r", name, exc_info=True)
        if capable:
            return name
        logger.info(
            "hermes-agent: substituting %r for %r — %s",
            self._fallback_model, name or "<unset>",
            "no capability profile available" if capable is None
            else "the routed model cannot drive an agent loop",
        )
        return self._fallback_model

    def _scratch_workspace(self, task: Any) -> str:
        """Where Hermes Agent runs a task that is bound to no Project.

        Never the process CWD: that is the Hermes OS source tree itself, and
        the adapter would otherwise hand Hermes Agent write access to the
        very codebase running it (HermesAgentCliConfig falls back to
        ``os.getcwd()`` when given no workspace). An empty per-mission
        scratch directory keeps an unbound mission harmless; a mission that
        needs real files is expected to bind a validated Project.
        """
        import tempfile
        from pathlib import Path

        mission_id = getattr(task, "mission_id", "") or "unbound"
        root = Path(tempfile.gettempdir()) / "hermes_os_scratch" / mission_id
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

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

    def _resolve_workspace(self, task: Any) -> Optional[tuple[str, str]]:
        """(project_id, project_root) for this task's real filesystem
        tool-calling, or None — see workspace_project_for's own
        docstring. Never raises: a broken resolver must degrade to "no
        workspace, no tools" (prior behavior), not fail the task."""
        if self._workspace_project_for is None:
            return None
        try:
            return self._workspace_project_for(task)
        except Exception:
            logger.debug("workspace_project_for callback failed", exc_info=True)
            return None

    def _budget_d_appel(self, runtime_id: str, boucle_d_outils: bool) -> float:
        """Combien de temps on accorde à ce que `chat` va vraiment faire.

        Trois choses très différentes se cachent derrière le même appel, et
        les mesurer avec le même chronomètre était le défaut (HOS-121) :

        * **une complétion simple** — un aller-retour, `_timeout_s` suffit
          et doit rester serré : au-delà, c'est que le modèle est en peine ;
        * **la boucle d'outils** (`_chat_with_tools_for`) — jusqu'à
          `mission_max_tool_rounds` inférences enchaînées, chacune suivie
          d'une lecture ou d'une écriture sur le disque ;
        * **Hermes Agent** — un processus, un toolset, sa propre boucle.

        Les deux derniers partagent le même budget parce qu'ils font la
        même chose : plusieurs tours sur du matériel local. Le retenir de
        `_timeout_s` reviendrait à demander douze inférences en trois
        minutes.
        """
        if runtime_id == "hermes-agent":
            return self._agentic_timeout_s
        if boucle_d_outils:
            return self._agentic_timeout_s
        return self._timeout_s

    def _chat_with_tools_for(
        self, workspace: tuple[str, str],
    ) -> Callable[..., Any]:
        """A chat-shaped callable (messages, model, num_ctx) -> ChatResponse
        that runs the real, bounded workspace tool-calling loop instead of
        a single plain completion — see the module docstring for why this
        is built directly on OllamaClient.chat_events(tools=...) rather
        than BaseAgent.respond_events()."""
        project_id, project_root = workspace

        async def _chat(*, messages: list[dict[str, Any]], model: str,
                        num_ctx: Optional[int] = None) -> Any:
            return await self._run_tool_loop(messages, model, num_ctx, project_id, project_root)

        return _chat

    async def _run_tool_loop(
        self, messages: list[dict[str, Any]], model: str, num_ctx: Optional[int],
        project_id: str, project_root: str,
    ) -> Any:
        from backend.connectors.ollama_client import OllamaClient, OllamaUnavailableError
        from backend.core.config import get_settings
        from backend.ral.capabilities import ChatResponse
        from backend.tools.verification_chat_tools import (
            execute_verification_tool, verification_tool_schemas,
        )
        from backend.tools.workspace_chat_tools import execute_workspace_tool, workspace_tool_schemas

        settings = get_settings()
        client = OllamaClient(
            settings.ollama_api_url,
            keep_alive=getattr(settings, "ollama_keep_alive", "10m"),
            timeout=self._timeout_s,
            default_num_ctx=num_ctx if num_ctx is not None
                            else getattr(settings, "ollama_num_ctx", 8192),
        )
        # Les fichiers *et* les runners (HOS-116). Une tâche qui sait écrire
        # mais pas lancer les tests ne peut jamais rapporter mieux que « j'ai
        # écrit » — jamais « j'ai écrit et ça passe ». C'est précisément la
        # différence que `MissionVerification` cherche à établir, et que la
        # boucle de reprise (HOS-099/100) exploite : une vérification qui
        # échoue déclenche une seconde tentative, encore faut-il pouvoir
        # échouer sur autre chose que l'absence d'artefact.
        #
        # Les runners restent une liste blanche nommée
        # (config/verification.yaml) : la tâche choisit `npm_test` ou
        # `pytest`, elle ne compose aucune commande.
        tools = workspace_tool_schemas() + verification_tool_schemas()
        working_messages = list(messages)
        tool_calls_made = 0
        try:
            for _round in range(_tours_d_outils_max()):
                content_parts: list[str] = []
                pending_calls: list[dict[str, Any]] = []
                async for chunk in client.chat_events(model, working_messages, tools=tools):
                    if chunk.kind == "content":
                        content_parts.append(chunk.text)
                    elif chunk.kind == "tool_calls":
                        pending_calls.extend(chunk.tool_calls or [])

                if not pending_calls:
                    return ChatResponse(
                        content="".join(content_parts),
                        metadata={"model": model, "provider": "ollama",
                                  "tool_calls_made": tool_calls_made},
                    )

                working_messages.append({
                    "role": "assistant", "content": "", "tool_calls": pending_calls,
                })
                for call in pending_calls:
                    fn = call.get("function", {})
                    name = fn.get("name", "")
                    arguments = fn.get("arguments") or {}
                    executeur = (
                        execute_verification_tool if name.startswith("verification_")
                        else execute_workspace_tool
                    )
                    try:
                        result = await executeur(
                            name, arguments, project_id=project_id, project_root=project_root,
                        )
                    except Exception as exc:
                        result = f"Tool {name!r} failed: {type(exc).__name__}: {exc}"
                    tool_calls_made += 1
                    working_messages.append({
                        "role": "tool", "content": str(result), "tool_name": name,
                    })

            # Ran out of rounds without a final answer — same forced,
            # tool-free final call as agents/base_agent.py's own loop, so
            # a model stuck re-requesting tools still returns something
            # rather than an empty completion.
            final_parts: list[str] = []
            async for chunk in client.chat_events(
                model,
                working_messages + [{
                    "role": "user",
                    "content": (
                        "Réponds maintenant avec les informations déjà trouvées "
                        "ci-dessus, du mieux que tu peux — aucun nouvel outil "
                        "n'est disponible."
                    ),
                }],
            ):
                if chunk.kind == "content":
                    final_parts.append(chunk.text)
            return ChatResponse(
                content="".join(final_parts),
                metadata={"model": model, "provider": "ollama",
                          "tool_calls_made": tool_calls_made},
            )
        except OllamaUnavailableError as exc:
            raise RuntimeUnavailableError(f"Ollama unavailable: {exc}") from exc
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

    def _build_messages(
        self,
        task: Any, assignment: Any, workspace: Optional[tuple[str, str]] = None,
        *,
        hermes_agent: bool = False,
    ) -> list[dict[str, Any]]:
        """Build the one chat completion this execution actually is.

        ``assigned_tools``/``tool_ids`` (AgentCoordinator's keyword-matched
        recommendation, an unrelated concept to the real workspace tools
        below) remains a text hint only, per the HOS-069 finding — nothing
        parses it or invokes anything from it. ``workspace``, when given
        (this task's Mission is bound to a real, validated Project — see
        _resolve_workspace), is different: real tools genuinely exist, and
        the paragraph below says so.

        ``hermes_agent`` selects *which* toolset the prompt may name. Hermes
        Agent arrives with its own ("coding") and is launched with the
        workspace as its cwd, so naming Hermes OS's ``workspace_*`` tools
        would describe an API it does not have — a prompt that lies about
        the tools available is worse than one that stays quiet. Only the
        local-Ollama path, whose tools this executor attaches itself via
        _chat_with_tools_for(), gets the explicit ``workspace_*`` listing.
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
        if workspace is not None:
            _project_id, project_root = workspace
            if hermes_agent:
                # Hermes Agent brings its own tools (the "coding" toolset) and
                # is launched with this directory as its cwd. Naming Hermes
                # OS's workspace_* tools here would advertise tools it does
                # not have — the prompt must describe the ground, not invent
                # an API for the brain that already owns one.
                system += (
                    f" Your working directory is {project_root!r} and you have "
                    f"real filesystem access to it. Inspect before you write: "
                    f"do not guess paths."
                )
            else:
                system += (
                    f" You have real filesystem access to the workspace at "
                    f"{project_root!r} via workspace_list/workspace_exists/"
                    f"workspace_read/workspace_write — paths are relative to "
                    f"that root. Use workspace_list before reading a file whose "
                    f"exact path you don't already know; do not guess paths."
                )

        # The node title alone is usually too thin to act on (see
        # _mission_brief_for): "Create test file" names no file and no
        # content. The Mission's objective is the only place the real
        # requirement survives decomposition.
        brief = ""
        if self._mission_brief_for is not None:
            try:
                brief = (self._mission_brief_for(task) or "").strip()
            except Exception:  # pragma: no cover - a brief is never worth failing over
                logger.debug("mission brief lookup failed", exc_info=True)
        user = (f"Mission objective: {brief}\n\nYour task in that mission: {title}"
                if brief else f"Task: {title}")

        # HOS-105: what the tasks this one depends on actually produced.
        # Before this, every task started from zero — result_summary was
        # written on each node and read by nobody — so a decomposed mission
        # behaved like a set of unrelated one-shot prompts. Carried as plain
        # text on purpose: it has to survive the model being swapped between
        # two tasks, which anything held as KV cache or a provider session
        # would not.
        upstream = ""
        if self._upstream_results_for is not None:
            try:
                upstream = (self._upstream_results_for(task) or "").strip()
            except Exception:  # pragma: no cover - context is never worth failing over
                logger.debug("upstream results lookup failed", exc_info=True)
        if upstream:
            user += (
                "\n\nAlready done by the tasks yours depends on:\n" + upstream
                + "\n\nBuild on that work — do not redo it. Anything it left "
                  "on disk is there; check before assuming."
            )

        # HOS-122 : le manifeste. `upstream` ne remonte que les dépendances
        # **directes** ; deux tâches sœurs restent aveugles l'une à
        # l'autre. C'est ainsi que l'essai Skills360 a produit deux
        # fichiers de tests de même nom de base, dont l'un écrit contre une
        # API imaginée. Le manifeste est la photo complète : qui écrit
        # quoi, dans toute la mission.
        livrables = ""
        if self._livrables_pour is not None:
            try:
                livrables = (self._livrables_pour(task) or "").strip()
            except Exception:  # pragma: no cover - un manifeste ne fait jamais échouer
                logger.debug("manifeste des livrables indisponible", exc_info=True)
        if livrables:
            user += "\n\n" + livrables

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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
