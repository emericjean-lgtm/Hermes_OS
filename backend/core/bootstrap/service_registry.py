"""Declarative catalogue of every Hermes OS subsystem (HOS-066B).

One spec per subsystem, holding everything the assembly needs to know:

* how to build it (``factory``),
* what it needs built first (``dependencies``),
* which routers it owns and how to bind them to it (``route_binder``),
* which topics it publishes and consumes (for the dependency report).

Keeping all four in one place is what lets the bootstrap, the dependency-graph
validation (STEP 8) and the health orchestrator (STEP 9) be *derived* rather
than maintained in parallel — three hand-kept lists would drift the way the
``EventHub`` allow-list did.

Nothing here contains behaviour. Every factory calls an existing constructor and
every binder calls an existing ``create_*_routes`` hook or wraps existing
handler functions. No subsystem is reimplemented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Optional

from backend.core.integration.component_registry import ComponentCategory

logger = logging.getLogger("hermes_os.bootstrap.services")

# A factory receives the container and returns the single instance.
Factory = Callable[[Any], Any]
# A binder receives (container, instance) and returns the routers to mount.
RouteBinder = Callable[[Any, Any], list[Any]]


@dataclass(frozen=True)
class ServiceSpec:
    """How to build, wire and expose one subsystem."""

    key: str
    name: str
    category: ComponentCategory
    factory: Factory
    dependencies: tuple[str, ...] = ()
    route_binder: Optional[RouteBinder] = None
    produced_events: tuple[str, ...] = ()
    consumed_events: tuple[str, ...] = ()
    description: str = ""
    #: Set for subsystems whose instance is a pre-existing module-level object
    #: that the container adopts rather than constructs, so "one instance only"
    #: holds across both access paths.
    adopts_module_singleton: bool = False
    capabilities: tuple[str, ...] = ()

    def component_id(self) -> str:
        return self.key


# ======================================================================
# Factories — each one calls an existing constructor, nothing more.
# ======================================================================


def _dispatcher(c: Any, source: str) -> Any:
    """The shared event seam, relabelled for one subsystem."""
    return c.get("event_dispatcher").scoped(source)


# ── Core / events ──────────────────────────────────────────────────────

def _make_event_hub(c: Any) -> Any:
    from backend.core.event_hub import get_event_hub

    return get_event_hub()


def _make_system_event_bus(c: Any) -> Any:
    from backend.events.system_event_bus import SystemEventBus

    return SystemEventBus(max_history=5000)


def _make_dispatcher(c: Any) -> Any:
    from backend.core.bootstrap.event_wiring import EventDispatcher

    return EventDispatcher(
        system_bus=c.get("system_event_bus"),
        event_hub=c.get("event_hub"),
    )


# ── Runtime layer ─────────────────────────────────────────────────────

def _make_resource_manager(c: Any) -> Any:
    """The resource manager, with a GPU monitor that actually probes hardware.

    ``ResourceManager`` defaults to ``NoopGPUMonitor()`` — the CI stub that
    always answers ``available=False`` — and nothing ever passed it a real one,
    so a production Hermes reported no GPU on a machine whose GPU was serving
    every inference. The real monitor is injected here rather than by changing
    that default, which keeps bare ``ResourceManager()`` construction hermetic
    for the unit suite.
    """
    from backend.runtime.resources.gpu_monitor import GPUMonitor
    from backend.runtime.resources.resource_manager import ResourceManager

    return ResourceManager(
        gpu_monitor=GPUMonitor(),
        on_event=_dispatcher(c, "resource_manager"),
    )


def _bind_resource_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.resources.routes import create_resource_routes

    return [create_resource_routes(svc)]


def _make_runtime_orchestrator(c: Any) -> Any:
    from backend.runtime.orchestrator.runtime_orchestrator import RuntimeOrchestrator

    return RuntimeOrchestrator(on_event=_dispatcher(c, "runtime_orchestrator"))


def _bind_orchestrator_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.orchestrator.routes import create_orchestrator_routes

    return [create_orchestrator_routes(svc)]


def _make_model_registry(c: Any) -> Any:
    from backend.runtime.discovery.model_registry import ModelRegistry

    return ModelRegistry()


def _make_discovery_engine(c: Any) -> Any:
    from backend.runtime.discovery.discovery_engine import DiscoveryEngine

    return DiscoveryEngine(
        registry=c.get("model_registry"),
        on_event=_dispatcher(c, "runtime_discovery"),
    )


def _bind_discovery_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.discovery.routes import create_discovery_routes

    return [create_discovery_routes(svc, c.get("model_registry"))]


def _make_recovery_engine(c: Any) -> Any:
    from backend.runtime.recovery.recovery_engine import RecoveryEngine

    return RecoveryEngine(on_event=_dispatcher(c, "runtime_recovery"))


def _bind_recovery_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.recovery.routes import create_recovery_routes

    return [create_recovery_routes(svc)]


def _make_learning_engine(c: Any) -> Any:
    from backend.runtime.intelligence.learning_engine import LearningEngine

    return LearningEngine(on_event=_dispatcher(c, "runtime_intelligence"))


def _bind_intelligence_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.intelligence.routes import create_intelligence_routes

    return [create_intelligence_routes(svc)]


def _make_simulation_engine(c: Any) -> Any:
    """Wired to the orchestrator and recovery engine through their callbacks.

    SimulationEngine takes getters rather than the services themselves, which is
    what lets it run against fakes in tests. Here they are pointed at the real
    orchestrator/recovery instances so simulation reflects live state.
    """
    from backend.runtime.simulation.simulation_engine import SimulationEngine

    orchestrator = c.get("runtime_orchestrator")
    recovery = c.get("recovery_engine")

    def get_candidates() -> list[str]:
        getter = getattr(orchestrator, "get_registered_runtimes", None)
        if callable(getter):
            try:
                return list(getter())
            except Exception:
                return []
        return []

    def is_recovering(runtime_id: str) -> bool:
        getter = getattr(recovery, "is_recovering", None)
        if callable(getter):
            try:
                return bool(getter(runtime_id))
            except Exception:
                return False
        return False

    return SimulationEngine(
        get_candidates=get_candidates,
        is_recovering=is_recovering,
        on_event=_dispatcher(c, "runtime_simulation"),
    )


def _bind_simulation_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.simulation.routes import create_simulation_routes

    return [create_simulation_routes(svc)]


def _make_runtime_event_bus(c: Any) -> Any:
    from backend.runtime.events.event_bus import RuntimeEventBus

    return RuntimeEventBus(max_history=1000)


def _bind_runtime_event_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.events.routes import create_runtime_event_routes

    return [create_runtime_event_routes(svc)]


def _make_kt_runtime(c: Any) -> Any:
    from backend.runtime.ktransformers import get_kt_runtime

    return get_kt_runtime()


def _bind_kt_routes(c: Any, svc: Any) -> list[Any]:
    from backend.runtime.ktransformers.kt_routes import router

    return [router]


# ── Execution layer ───────────────────────────────────────────────────
#
# These two used to be private to AutonomousOrchestrator, which built its own
# RealTaskExecutor and its own MissionExecutor on construction. That is what
# made Hermes carry two disjoint mission pipelines: /autonomous reached the real
# executor, /missions reached a GraphExecutor whose execute_node hook defaulted
# to ``lambda n: True``. Promoting them to services means there is exactly one
# task-execution engine in the process and every surface shares it (R-002 P1).

def _make_task_executor(c: Any) -> Any:
    """Wire the executor to Model Intelligence's AdaptiveRouter (HOS-065).

    Before this, ``AdaptiveRouter.recommend()`` was reachable only through
    ``POST /models/recommend`` — a real, working advisory endpoint the
    Models Center calls, but one nothing in the actual mission/task
    pipeline ever consulted. ``_resolve_model()`` always fell back to the
    hardcoded ``default_model``, and the profiler's scores never moved
    because nothing fed it a real outcome (the only thing that did,
    ``BenchmarkScheduler``, fabricates every number with ``random.uniform``
    and doesn't even persist them — see its module docstring). Routing
    through ``mi_routes``' own module-level accessors (the same ones
    ``_make_model_intelligence`` adopts below) rather than constructing a
    second ``AdaptiveRouter`` keeps this the one shared instance the Models
    Center's HTTP surface also reads from, so a real task execution now
    shows up in ``/models/history`` and ``/models/performance`` too.
    """
    from backend.core.config import load_models_config
    from backend.execution.task_executor import RealTaskExecutor
    from backend.model_intelligence import routes as mi_routes
    from backend.model_intelligence.model_intelligence_models import ModelPerformanceRecord

    # HOS-069: config/models.yaml's roles.*.vram_gb is HOS-065C's real,
    # measured VRAM footprint per model — not a guess. Loaded once here
    # (models.yaml is small and cached by load_models_config's lru_cache
    # anyway) into a flat model-tag -> vram_gb map for the admission check
    # below, decoupled from whichever router object picked the model.
    _vram_by_model: dict[str, float] = {}
    for _role in load_models_config().get("roles", {}).values():
        if isinstance(_role, dict) and _role.get("model") and _role.get("vram_gb"):
            _vram_by_model[_role["model"]] = float(_role["vram_gb"])

    def _vram_gb_for(model: str) -> Optional[float]:
        """Real, benchmarked VRAM footprint for a resolved model tag
        (HOS-069). None for a tag with no matching role entry — the
        admission check is then a safe no-op for it rather than blocking on
        an invented number."""
        return _vram_by_model.get(model)

    def _max_vram_mb_now() -> int:
        """Real, currently-free VRAM (HOS-071 Phase A) — replaces the
        static 8192MB default every recommendation used to reason against
        regardless of the card's real size or what else is resident right
        now. Falls back to that same 8192 default if the resource manager
        can't report real numbers (GPU unavailable), unchanged prior
        behaviour."""
        resource_manager = c.get("resource_manager")
        if resource_manager is None:
            return 8192
        try:
            gpu = resource_manager.get_gpu_info()
            if not gpu.available or gpu.vram_total_bytes <= 0:
                return 8192
            return max(0, int(gpu.vram_free_bytes / (1024 * 1024)))
        except Exception:
            return 8192

    def _task_type_hint(task: Any) -> Optional[str]:
        """The already-structured task type (HOS-070's TaskExecution.task_type,
        threaded from MissionNode.type) — a real, more precise signal than
        re-inferring one from keyword-matching the task's title text
        (HOS-071 Phase C). Empty/absent falls through to that same keyword
        inference, unchanged prior behaviour."""
        return getattr(task, "task_type", "") or None

    def _model_for(task: Any) -> Optional[str]:
        title = getattr(task, "title", "") or ""
        if not title:
            return None
        try:
            decision = mi_routes._get_router().recommend_for_text(  # noqa: SLF001
                title, max_vram_mb=_max_vram_mb_now(), task_type_hint=_task_type_hint(task),
            )
            return decision.model_id or None
        except Exception:
            return None

    def _num_ctx_for(task: Any) -> Optional[int]:
        """The chosen model's own operational context window (HOS-065C —
        config/models.yaml's roles.*.num_ctx, set from real benchmark data),
        not the one global default every call used to fall back to
        regardless of which model answered it. Re-resolves the same
        recommendation _model_for already made — cheap, in-memory, no
        network call — rather than changing model_for's return shape."""
        title = getattr(task, "title", "") or ""
        if not title:
            return None
        try:
            decision = mi_routes._get_router().recommend_for_text(  # noqa: SLF001
                title, max_vram_mb=_max_vram_mb_now(), task_type_hint=_task_type_hint(task),
            )
            return decision.num_ctx or None
        except Exception:
            return None

    def _runtime_for(task: Any) -> Optional[str]:
        """Which runtime AdaptiveRouter actually chose for this task
        (HOS-066C) — "openrouter" only when its cloud escalation gate said
        yes (no local model viable / task opted in, Aegis authorized, real
        quota available); anything else runs local exactly as before this
        existed. Re-resolves the same recommendation _model_for already
        made, same reasoning as _num_ctx_for above."""
        title = getattr(task, "title", "") or ""
        if not title:
            return None
        try:
            decision = mi_routes._get_router().recommend_for_text(  # noqa: SLF001
                title, max_vram_mb=_max_vram_mb_now(), task_type_hint=_task_type_hint(task),
            )
            runtime = decision.runtime.value
            return "openrouter" if runtime == "openrouter" else "hermes-agent"
        except Exception:
            return None

    def _local_fallback_for(task: Any) -> Optional[str]:
        """A real local model to retry against if a cloud call fails
        (HOS-066C) — the same ranking machinery, forced local-only
        (allow_cloud=False) so it can never recommend the very runtime that
        just failed."""
        title = getattr(task, "title", "") or ""
        if not title:
            return None
        try:
            decision = mi_routes._get_router().recommend_for_text(  # noqa: SLF001
                title, max_vram_mb=_max_vram_mb_now(), allow_cloud=False,
                task_type_hint=_task_type_hint(task),
            )
            return decision.model_id or None
        except Exception:
            return None

    def _record_feedback(task: Any, model: str, duration_ms: float,
                         tokens_used: int, success: bool) -> None:
        if not model:
            return
        router = mi_routes._get_router()  # noqa: SLF001
        task_type = router._infer_task_type(getattr(task, "title", "") or "")  # noqa: SLF001
        mi_routes._get_profiler().update_performance(ModelPerformanceRecord(  # noqa: SLF001
            model_id=model,
            task_type=task_type,
            duration_ms=round(duration_ms),
            tokens_used=tokens_used,
            success=success,
        ))
        # ModelMemoryAdapter's MODEL_USED_FOR_TASK relations (HOS-065B) —
        # record_model_for_task() existed and was never called by anything,
        # so get_best_model_for_task() always returned None. Same real
        # telemetry as the profiler update above, different shape (a
        # per-task-type win/loss graph, not an aggregate profile score).
        mi_routes._get_memory().record_model_for_task(  # noqa: SLF001
            model, task_type.value, success,
        )

    def _record_runtime_health(runtime_id: str, duration_ms: float, success: bool) -> None:
        """Feeds the RAL runtime registry's health monitor (HOS-072) — the
        real source GET /api/v1/runtimes reads for its metrics/health
        fields. Before this, nothing outside the SDS module's own routes
        ever called record_execution(), so every runtime's metrics stayed
        permanently empty regardless of how many real tasks it served."""
        from backend.sds.runtime import get_runtime_health_monitor

        get_runtime_health_monitor().record_execution(
            runtime_id, latency_ms=round(duration_ms), success=success,
        )

    return RealTaskExecutor(
        on_event=_dispatcher(c, "task_executor"),
        model_for=_model_for,
        on_execution=_record_feedback,
        on_runtime_result=_record_runtime_health,
        num_ctx_for=_num_ctx_for,
        cloud_chat=_make_cloud_chat(),
        runtime_for=_runtime_for,
        local_fallback_for=_local_fallback_for,
        resource_manager=c.get("resource_manager"),
        vram_gb_for=_vram_gb_for,
        workspace_project_for=_workspace_project_for,
        mission_brief_for=_mission_brief_for,
        agentic_capable_for=_agentic_capable_for,
    )


def _workspace_project_for(task: Any) -> Optional[tuple[str, str]]:
    """Workspace/Filesystem tool layer: resolves task.mission_id's Mission
    -> context.project_id -> an ACTIVE, validation_status="valid" Project
    -> (project_id, root_path), or None (no real filesystem tools for
    this task — prior behavior, unchanged). Same three-way check
    AegisAgent._dynamic_allowed_paths applies via
    projects.store.active_validated_project_roots, repeated here so a
    task isn't offered tools Aegis would just refuse — a UX choice, not
    the security boundary; file_tools re-checks independently regardless
    of what this returns."""
    mission_id = getattr(task, "mission_id", "") or ""
    if not mission_id:
        return None
    try:
        from backend.mission.routes import get_mission_by_id
        mission = get_mission_by_id(mission_id)
    except Exception:
        return None
    if mission is None:
        return None
    project_id = mission.context.project_id
    if not project_id:
        return None
    try:
        from backend.projects.project_manager import ProjectStatus, ValidationStatus
        from backend.projects.store import get_project_store
        project = get_project_store().get(project_id)
    except Exception:
        return None
    if project is None or not project.root_path:
        return None
    if project.status != ProjectStatus.ACTIVE.value:
        return None
    if project.validation_status != ValidationStatus.VALID.value:
        return None
    return (project_id, project.root_path)


def _mission_brief_for(task: Any) -> Optional[str]:
    """The Mission's own objective, for a task that only knows its node title.

    TaskDecomposer routinely produces generic node titles ("Create test
    file", "Verify file contents") and leaves node.description empty, so a
    task built from one carries no trace of what was actually asked. Live
    proof (HOS-085): a mission whose objective named the file, its three
    lines and the verification step reached Hermes Agent as nothing but
    ``Task: Create test file`` — the agent had no filename and no content
    to work from, wandered outside the workspace, and the mission still
    reported 4/4 completed. Passing the objective alongside the node title
    is what makes a decomposed task actionable at all.
    """
    mission_id = getattr(task, "mission_id", "") or ""
    if not mission_id:
        return None
    try:
        from backend.mission.routes import get_mission_by_id
        mission = get_mission_by_id(mission_id)
    except Exception:
        return None
    if mission is None:
        return None
    # objective first, then description: POST /missions maps them from two
    # separate payload fields and the Mission Center's create form only ever
    # fills "description", so a mission built from the UI has an empty
    # objective. mission/routes.py makes the same substitution in both
    # directions already (``mission.objective or mission.title``).
    for attr in ("objective", "description"):
        value = (getattr(mission, attr, "") or "").strip()
        if value:
            return value
    return None


@lru_cache(maxsize=64)
def _agentic_capable_for(model_id: str) -> Optional[bool]:
    """Can this model actually drive Hermes Agent's loop (HOS-088)?

    Asks Ollama's own ``/api/show`` for the model's declared capabilities and
    parameter count, then lets ModelProfile.agentic_capable apply the policy.
    Returns None when the model is unknown or Ollama is unreachable, which
    the caller treats as "not proven" rather than "yes" — handing Hermes a
    brain that cannot call tools produces a mission that reports success and
    accomplishes nothing, the exact failure HOS-085 chased down.

    Cached: this is asked once per task and the answer only changes when the
    model itself is replaced.
    """
    try:
        import httpx

        from backend.core.config import get_settings
        from backend.model_intelligence.model_intelligence_models import ModelProfile

        base = get_settings().ollama_api_url.rstrip("/")
        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{base}/api/show", json={"model": model_id})
            response.raise_for_status()
            payload = response.json()
    except Exception:
        logger.debug("agentic capability probe failed for %r", model_id, exc_info=True)
        return None

    capabilities = [str(c).lower() for c in (payload.get("capabilities") or [])]
    details = payload.get("details") or {}
    raw_size = str(details.get("parameter_size") or "").strip().upper()
    try:
        parameters_b = (float(raw_size.rstrip("B")) if raw_size.endswith("B")
                        else float(raw_size.rstrip("M")) / 1000.0 if raw_size.endswith("M")
                        else 0.0)
    except ValueError:
        parameters_b = 0.0

    # What the weights support, from the model's own metadata.
    info = payload.get("model_info") or {}
    supported_context = next(
        (int(v) for k, v in info.items()
         if k.endswith(".context_length") and isinstance(v, int)), 0,
    )
    profile = ModelProfile(
        model_id=model_id,
        name=model_id,
        parameters_b=parameters_b,
        context_window=supported_context or 4096,
        served_context=_served_context_for(model_id),
        declares_tools="tools" in capabilities,
        # An embedding model is not a chat model, however it advertises
        # itself — qwen3-embedding:0.6b reports "tools".
        chat_capable="embedding" not in capabilities,
    )
    return profile.agentic_capable


def _served_context_for(model_id: str) -> Optional[int]:
    """What Ollama is actually handing out for a currently-loaded model.

    ``/api/ps`` reports the context a loaded model was given, which is the
    number that matters and is routinely far below what the weights
    support: the OpenAI-compatible ``/v1`` endpoint Hermes Agent uses
    carries no num_ctx, so Ollama applies its own default
    (``OLLAMA_CONTEXT_LENGTH``). Returns None when the model is not
    resident — nothing has been served yet, so there is nothing to judge.
    """
    try:
        import httpx

        from backend.core.config import get_settings

        base = get_settings().ollama_api_url.rstrip("/")
        with httpx.Client(timeout=5.0) as client:
            running = client.get(f"{base}/api/ps").json().get("models") or []
    except Exception:
        return None
    for entry in running:
        name = str(entry.get("name") or "")
        if name == model_id or name.split(":")[0] == model_id.split(":")[0]:
            value = entry.get("context_length")
            return int(value) if isinstance(value, int) and value > 0 else None
    return None


def _make_cloud_chat() -> Optional[Any]:
    """OpenRouter chat callable for RealTaskExecutor (HOS-066C). None when
    OPENROUTER_API_KEY isn't configured — cloud is then entirely unreachable
    regardless of what AdaptiveRouter recommends, the safe default. A fresh
    OpenRouterClient per call, closed after — the same pattern
    RealTaskExecutor._default_chat already uses for OllamaClient."""
    from backend.core.config import get_settings

    settings = get_settings()
    if not settings.openrouter_api_key:
        return None

    async def _cloud_chat(*, messages: list[dict[str, Any]], model: str,
                          num_ctx: Optional[int] = None) -> Any:
        from backend.connectors.openrouter_client import OpenRouterClient

        client = OpenRouterClient(settings.openrouter_api_key)
        try:
            return await client.chat(messages, model=model, num_ctx=num_ctx)
        finally:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass

    return _cloud_chat


def _make_execution_engine(c: Any) -> Any:
    from backend.agents.capability_matcher import CapabilityMatcher
    from backend.execution.mission_executor import MissionExecutor

    agent_registry = c.get("agent_supervisor").registry
    return MissionExecutor(
        task_executor=c.get("task_executor"),
        on_event=_dispatcher(c, "execution_engine"),
        # HOS-070: the real AgentRegistry (backend/agents/), the one
        # GET /api/v1/agents and the Cockpit's Agent Center actually read
        # from. Without this, every agent showed its initial "READY, 0
        # tasks" state forever, regardless of how many real missions ran —
        # nothing updated it outside of agent create/stop.
        agent_registry=agent_registry,
        # HOS-070: the real, multi-criteria selection engine (HOS-043),
        # wrapping the same registry — replaces AgentCoordinator's own
        # simpler keyword scoring instead of leaving two disconnected
        # selection engines, only one of which was ever actually reachable.
        capability_matcher=CapabilityMatcher(agent_registry),
        # HOS-070: real per-agent trust scoring — AgentTrustEngine.
        # record_result() existed and was never called by anything. Not the
        # full SecurityEngine.check_access() gate (see MissionExecutor's
        # own docstring for why: no default permissions/policies are
        # configured anywhere, so that gate would default-deny every real
        # mission today).
        trust_engine=c.get("security_engine").trust,
    )


# ── Mission layer ─────────────────────────────────────────────────────

def _make_graph_executor(c: Any) -> Any:
    """The DAG traverser, with its node hook bound to the real engine.

    ``execute_node`` has always been an injection point and nothing ever used
    it, so it fell back to ``lambda n: True`` — every node of every mission was
    declared successful without any work being done (R-002 P1).

    HOS-069: bound to ``execution_controller``, not ``execution_engine``
    directly, so a real node execution registers where ``/api/v1/execution``
    can see it — see node_execution.py's module docstring.
    """
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.node_execution import make_node_executor

    return GraphExecutor(
        on_event=_dispatcher(c, "mission_executor"),
        execute_node=make_node_executor(c.get("execution_controller")),
    )


def _bind_mission_routes(c: Any, svc: Any) -> list[Any]:
    from backend.mission.routes import create_mission_routes

    return [create_mission_routes(svc)]


def _make_mission_planner(c: Any) -> Any:
    from backend.connectors.ollama_client import OllamaClient
    from backend.core.config import get_settings, load_models_config
    from backend.core.router import ModelRouter
    from backend.mission.planner.mission_planner import MissionPlanner
    from backend.mission.planner.task_decomposer import TaskDecomposer

    # Built the same way get_agent_registry() and RealTaskExecutor._default_chat
    # build theirs (backend/core/agent_registry.py, backend/execution/
    # task_executor.py) — this planner talks to whatever endpoint the rest
    # of Hermes talks to, never a hardcoded one. Giving TaskDecomposer both
    # a client and a router is what turns on LLM-driven decomposition; every
    # other caller (including every existing test) constructs TaskDecomposer()
    # with neither, which keeps the original keyword-matching behaviour.
    settings = get_settings()
    models_config = load_models_config()
    ollama_client = OllamaClient(
        settings.ollama_api_url,
        keep_alive=getattr(settings, "ollama_keep_alive", "10m"),
        default_num_ctx=getattr(settings, "ollama_num_ctx", 8192),
    )
    from backend.connectors.openrouter_client import OpenRouterClient

    decomposer = TaskDecomposer(
        ollama_client=ollama_client,
        router=ModelRouter(models_config),
        models_config=models_config,
        cloud_client=OpenRouterClient.from_settings(),
    )

    return MissionPlanner(
        graph_executor=c.get("mission_executor"),
        on_event=_dispatcher(c, "mission_planner"),
        decomposer=decomposer,
    )


def _bind_planner_routes(c: Any, svc: Any) -> list[Any]:
    from backend.mission.planner.routes import create_planner_routes
    from backend.mission.routes import (
        set_evolution_engine,
        set_memory_manager,
        set_mission_planner,
    )

    # The /missions router needs the planner to turn a described goal into a
    # DAG, but route binders run inline as each service is built and the planner
    # is built *after* the graph executor it depends on. Injecting from this side
    # keeps the ordering correct and avoids a mission_executor ↔ mission_planner
    # dependency cycle (R-002 P1).
    set_mission_planner(svc)
    # Same injection, same reason, for episodic write-back: /autonomous fed
    # episodic memory from mission one (AutonomousMemoryLoop), /missions
    # never did, even though both share one execution engine (R-002 P1).
    set_memory_manager(c.get("memory_manager"))
    # HOS-068: same reason again — mission completion now feeds
    # EvolutionEngine.ingest_metrics() (detection-only, see routes.py's
    # _feed_evolution_engine), mirroring what AutonomousMemoryLoop already
    # does for /autonomous goals.
    set_evolution_engine(c.get("evolution_engine"))
    return [create_planner_routes(svc)]


# ── Agent layer ───────────────────────────────────────────────────────

def _make_agent_supervisor(c: Any) -> Any:
    from backend.agents.agent_supervisor import AgentSupervisor

    return AgentSupervisor(on_event=_dispatcher(c, "agent_supervisor"))


def _bind_agent_routes(c: Any, svc: Any) -> list[Any]:
    from backend.agents.routes import create_agent_routes, set_trust_engine

    # HOS-070: real trust scores (fed by MissionExecutor — see
    # _make_execution_engine) surfaced through GET /api/v1/agents.
    set_trust_engine(c.get("security_engine").trust)
    return [create_agent_routes(svc)]


def _make_collaboration_engine(c: Any) -> Any:
    from backend.agents.collaboration.collaboration_engine import CollaborationEngine

    return CollaborationEngine(on_event=_dispatcher(c, "collaboration"))


def _bind_collaboration_routes(c: Any, svc: Any) -> list[Any]:
    from backend.agents.collaboration.routes import create_collaboration_routes

    return [create_collaboration_routes(svc)]


# ── Memory ────────────────────────────────────────────────────────────

def _make_memory_manager(c: Any) -> Any:
    from backend.memory.memory_manager import MemoryManager

    return MemoryManager(on_event=_dispatcher(c, "memory_manager"))


def _bind_memory_routes(c: Any, svc: Any) -> list[Any]:
    from backend.memory.routes import create_memory_routes

    return [create_memory_routes(svc)]


# ── Skills & tools (adopted module singletons) ────────────────────────

def _make_skill_distributor(c: Any) -> Any:
    """Adopt the distributor `backend.skills.routes` already assembled.

    That module builds the registry, profiler, cache, loader, selector and
    resolver at import time and wires them together correctly. Building a second
    set here would give the HTTP layer and the container two different skill
    registries — exactly the duplication this container exists to prevent.
    """
    from backend.skills import routes as skill_routes

    return skill_routes._distributor  # noqa: SLF001 - deliberate adoption


def _bind_skill_routes(c: Any, svc: Any) -> list[Any]:
    from backend.skills.routes import create_skill_routes

    return [create_skill_routes(svc)]


def _make_tool_platform(c: Any) -> Any:
    """Adopt the tool platform `backend.tools.routes` already assembled."""
    from backend.tools import routes as tool_routes

    return tool_routes._registry  # noqa: SLF001 - deliberate adoption


def _bind_tool_routes(c: Any, svc: Any) -> list[Any]:
    from backend.tools.routes import create_tool_routes, mcp_router

    # mcp_router carries its own /mcp prefix: the frontend calls /mcp/servers,
    # not /tools/mcp/servers.
    return [create_tool_routes(svc), mcp_router]


# ── Governance ────────────────────────────────────────────────────────

def _make_policy_engine(c: Any) -> Any:
    from backend.policy.policy_engine import PolicyEngine

    return PolicyEngine(on_event=_dispatcher(c, "policy_engine"))


def _bind_policy_routes(c: Any, svc: Any) -> list[Any]:
    from backend.policy.routes import approval_router, audit_router, create_policy_routes

    return [create_policy_routes(svc), approval_router, audit_router]


def _make_workspace_manager(c: Any) -> Any:
    import tempfile
    from pathlib import Path

    from backend.workspace.workspace_manager import WorkspaceManager

    # The default is a hardcoded POSIX /tmp path, which does not exist on
    # Windows; derive it from the platform temp dir instead.
    base = Path(tempfile.gettempdir()) / "hermes-workspaces"
    return WorkspaceManager(
        base_path=str(base),
        on_event=_dispatcher(c, "workspace_manager"),
    )


def _bind_workspace_routes(c: Any, svc: Any) -> list[Any]:
    from backend.workspace.routes import create_workspace_routes

    return [create_workspace_routes(svc)]


def _make_security_engine(c: Any) -> Any:
    from backend.security.security_engine import SecurityEngine

    return SecurityEngine(on_event=_dispatcher(c, "security_engine"))


def _bind_security_routes(c: Any, svc: Any) -> list[Any]:
    from backend.security.routes import create_security_routes

    return [create_security_routes(svc)]


# ── Execution ─────────────────────────────────────────────────────────

def _make_execution_controller(c: Any) -> Any:
    """Wrap the *shared* execution engine (HOS-069), not a private one.

    This used to "adopt" execution_routes' own module-level controller —
    built at import time around its own freshly-constructed
    ``MissionExecutor()``, completely disconnected from ``execution_engine``
    (the shared instance ``node_execution.py`` and
    ``AutonomousOrchestrator``'s DAG path drive directly). Every real task
    ever run through Missions or Autonomous executed on the shared engine;
    this controller's own ``_executions``/``_reports`` registries never saw
    any of it, so ``/execution/*`` and the Cockpit's Execution Center could
    never show real activity — "Aucune exécution enregistrée" was an
    accurate report of a structurally empty registry, not a display bug.
    """
    from backend.execution.execution_controller import ExecutionController

    return ExecutionController(c.get("execution_engine"))


def _bind_execution_routes(c: Any, svc: Any) -> list[Any]:
    from backend.execution.routes import create_execution_routes

    return [create_execution_routes(svc)]


# ── Autonomy / evolution / conversation / explainability ──────────────

def _make_autonomous_engine(c: Any) -> Any:
    """Build the engine and close its learning loop.

    ``AutonomousMemoryLoop`` exposes ``set_memory_manager`` /
    ``set_evolution_engine`` and nothing called either, so ``process_report``
    skipped the write-back entirely: after six successful missions the Memory
    Center still reported ``episodic.total = 0`` (RC3 P2). Wiring it here is the
    composition root doing its job — the same class of gap HOS-066B fixed for
    the route modules.
    """
    from backend.autonomous.autonomous_engine import AutonomousEngine

    engine = AutonomousEngine(
        on_event=_dispatcher(c, "autonomous_engine"),
        # The one shared pipeline. Without this the orchestrator builds a private
        # MissionExecutor and Hermes carries two task engines (R-002 P1).
        mission_executor=c.get("execution_engine"),
        # HOS-067: the same Mission Planner + DAG walker /missions uses, so a
        # goal is decomposed into a real multi-node DAG (TaskDecomposer,
        # dependencies, per-task runtime recommendation) instead of the one
        # flat task the orchestrator used to build by hand. Note: the
        # container key "mission_executor" names the GraphExecutor (DAG
        # walker, backend/mission/graph_executor.py) — a naming collision
        # with this factory's own `mission_executor` param (the *task*
        # execution pipeline, backend/execution/mission_executor.py). Both
        # names are inherited from ServiceSpec/AutonomousOrchestrator and
        # not changed here to keep this a wiring-only diff.
        mission_planner=c.get("mission_planner"),
        graph_executor=c.get("mission_executor"),
    )
    orchestrator = getattr(engine, "orchestrator", None)

    interpreter = getattr(orchestrator, "interpreter", None)
    if interpreter is not None:
        # HOS-067: real cross-memory retrieval before planning
        # (MemoryManager.recommend_for_mission — episodic + experience
        # manager). Before this, set_memory_manager() was never called on
        # the interpreter anywhere, so its own (differently broken) memory
        # call never executed — confirmed by a repo-wide search.
        interpreter.set_memory_manager(c.get("memory_manager"))

    loop = getattr(orchestrator, "memory_loop", None)
    if loop is not None:
        loop.set_memory_manager(c.get("memory_manager"))
        loop.set_evolution_engine(c.get("evolution_engine"))

    guard = getattr(orchestrator, "guard", None)
    if guard is not None:
        # HOS-067: connect AutonomousGuard to the real, deterministic Aegis
        # engine — before this, set_security_engine()/set_policy_engine()
        # were never called anywhere, so every autonomous goal reached
        # ALLOW regardless of autonomy_level (only the guard's own
        # hard-blocked-category list, which "goal.execute" never matched,
        # ever ran). Built the same way agents/aegis.py's AegisAgent
        # constructs its own — a second, disconnected instance rather than
        # a shared one, matching how model_intelligence/routes.py's cloud
        # gate does the same for the same reason (no bootstrap-level Aegis
        # service exists to share yet).
        from backend.autonomous.autonomous_guard import AegisSecurityAdapter
        from backend.core.config import get_settings, load_security_config
        from backend.security.aegis_engine import AegisEngine
        from backend.security.permission_matrix import PermissionMatrix

        settings = get_settings()
        aegis_engine = AegisEngine(
            PermissionMatrix(load_security_config()), settings.allowed_paths_list,
        )
        guard.set_security_engine(AegisSecurityAdapter(aegis_engine))

    # DecisionEngine.select_runtime() exposed the same four set_* hooks
    # (agent supervisor, runtime orchestrator, skill distributor, tool
    # router) and none was ever called anywhere in the codebase or its
    # tests — confirmed by a repo-wide search before this change. Every
    # "runtime selection" it ever produced named one of three runtimes
    # ("ktransformers", "default_llm", "local_model") that are not, and
    # have never been, registered anywhere. Wiring the real orchestrator
    # closes that gap for the one decision most visibly self-contradicted
    # a report's own measured `runtimes_used`; agent/tool/skill selection
    # remain heuristic on the legacy single-task path (see CHANGELOG) — the
    # real DAG path (HOS-067) derives them from the real plan instead.
    decisions = getattr(orchestrator, "decisions", None)
    if decisions is not None:
        decisions.set_runtime_orchestrator(c.get("runtime_orchestrator"))

    # ModelAutonomousAdapter (HOS-065B) existed, was never instantiated
    # anywhere, and its record_feedback() was never called — an autonomous
    # goal's model choice and outcome went nowhere but the profiler this
    # orchestrator already reports to via RealTaskExecutor.on_execution
    # (see _make_task_executor). This is a reporting seam, not a decision
    # one — see AutonomousOrchestrator.set_model_adapter()'s docstring for
    # why select_model_for_goal() is deliberately not used here.
    if orchestrator is not None:
        from backend.model_intelligence import routes as mi_routes
        from backend.model_intelligence.model_autonomous_adapter import (
            ModelAutonomousAdapter,
        )

        orchestrator.set_model_adapter(ModelAutonomousAdapter(
            adaptive_router=mi_routes._get_router(),  # noqa: SLF001
            on_event=_dispatcher(c, "autonomous_engine"),
        ))
    return engine


def _bind_autonomous_routes(c: Any, svc: Any) -> list[Any]:
    from backend.autonomous.routes import create_autonomous_routes

    return [create_autonomous_routes(svc)]


def _make_evolution_engine(c: Any) -> Any:
    from backend.evolution.evolution_engine import EvolutionEngine

    return EvolutionEngine(on_event=_dispatcher(c, "evolution_engine"))


def _bind_evolution_routes(c: Any, svc: Any) -> list[Any]:
    from backend.evolution.routes import create_evolution_routes

    return [create_evolution_routes(svc)]


def _make_conversation_manager(c: Any) -> Any:
    from backend.conversation.conversation_manager import ConversationManager

    return ConversationManager()


def _bind_conversation_routes(c: Any, svc: Any) -> list[Any]:
    from backend.conversation.routes import create_conversation_routes

    return [create_conversation_routes(svc)]


def _make_explainer(c: Any) -> Any:
    from backend.explainability.decision_explainer import DecisionExplainer

    return DecisionExplainer()


def _bind_explainability_routes(c: Any, svc: Any) -> list[Any]:
    from backend.explainability.routes import create_explainability_routes

    return [create_explainability_routes(svc)]


# ── Model intelligence ────────────────────────────────────────────────

def _make_model_intelligence(c: Any) -> Any:
    """Adopt the AdaptiveRouter `model_intelligence.routes` already assembled.

    Its ``_get_router()`` wires the profiler, analyzer and predictor together;
    constructing a bare ``AdaptiveRouter()`` here would give the container a
    second router with its own disconnected profiler, so model scores recorded
    through HTTP would be invisible to the container's instance.
    """
    from backend.model_intelligence import routes as mi_routes

    return mi_routes._get_router()  # noqa: SLF001 - deliberate adoption


def _bind_model_intelligence_routes(c: Any, svc: Any) -> list[Any]:
    from backend.model_intelligence import routes as mi_routes

    # HOS-071: real ResourceManager so /models/recommend's own default (no
    # explicit max_vram_mb) and /models/optimize reason about VRAM that is
    # actually free/total right now, not a static guess — same
    # set_trust_engine()-style optional injection HOS-070 used for Agents.
    mi_routes.set_resource_manager(c.get("resource_manager"))
    return [mi_routes.create_model_intelligence_routes(svc)]


# ── Integrations ──────────────────────────────────────────────────────

def _make_alexandrie(c: Any) -> Any:
    from backend.integrations.alexandrie.hermes_alexandrie_adapter import (
        HermesAlexandrieAdapter,
    )

    return HermesAlexandrieAdapter()


def _bind_alexandrie_routes(c: Any, svc: Any) -> list[Any]:
    from backend.integrations.alexandrie.routes import router

    return [router]


def _make_klaatcode(c: Any) -> Any:
    """Adopt the adapter `klaatcode.routes` already built (client+policy+sandbox)."""
    from backend.tools.connectors.klaatcode import routes as kc_routes

    return kc_routes._adapter  # noqa: SLF001 - deliberate adoption


def _bind_klaatcode_routes(c: Any, svc: Any) -> list[Any]:
    from backend.tools.connectors.klaatcode.routes import klaatcode_router

    return [klaatcode_router]


def _make_ohmypi(c: Any) -> Any:
    """Adopt the adapter `oh_my_pi.routes` already built."""
    from backend.tools.connectors.oh_my_pi import routes as omp_routes

    return omp_routes._adapter  # noqa: SLF001 - deliberate adoption


def _bind_ohmypi_routes(c: Any, svc: Any) -> list[Any]:
    from backend.tools.connectors.oh_my_pi.routes import ohmypi_router

    return [ohmypi_router]


def _make_code_intelligence(c: Any) -> Any:
    """Wire CodeIntelligenceAgent onto the same provider instances the
    ``klaatcode``/``ohmypi`` services and their HTTP routes already use
    (R-006). ``c.get("klaatcode")``/``c.get("ohmypi")`` return the exact
    adopted MCP adapters from ``_make_klaatcode``/``_make_ohmypi`` above —
    building fresh clients here would give the CI agent a second, unbound
    view of each provider instead of the live one.
    """
    from backend.agents.specialized.code_intelligence.code_intelligence_agent import (
        create_code_intelligence_agent,
    )
    from backend.agents.specialized.code_intelligence.hermes_native_executor import (
        HermesNativeExecutor,
    )
    from backend.agents.specialized.klaatcode.klaatcode_agent import KlaatCodeAgent
    from backend.agents.specialized.ohmypi.ohmypi_agent import OhMyPiAgent
    from backend.connectors.ollama_client import OllamaClient
    from backend.core.config import get_settings, load_models_config
    from backend.core.router import ModelRouter

    memory_manager = c.get("memory_manager")
    workspace_manager = c.get("workspace_manager")

    klaatcode_agent = KlaatCodeAgent(
        on_event=_dispatcher(c, "klaatcode_agent"),
        mcp_adapter=c.get("klaatcode"),
        memory_manager=memory_manager,
        workspace_manager=workspace_manager,
    )
    klaatcode_agent.start()

    ohmypi_agent = OhMyPiAgent(
        on_event=_dispatcher(c, "ohmypi_agent"),
        mcp_adapter=c.get("ohmypi"),
        memory_manager=memory_manager,
        workspace_manager=workspace_manager,
    )
    ohmypi_agent.start()

    # Same construction as _make_mission_planner's TaskDecomposer: every real
    # inference path builds its own ModelRouter/OllamaClient pair from the
    # same settings/config rather than sharing a container-wide singleton,
    # since neither is stateful in a way that needs single-instance sharing.
    settings = get_settings()
    models_config = load_models_config()
    ollama_client = OllamaClient(
        settings.ollama_api_url,
        keep_alive=getattr(settings, "ollama_keep_alive", "10m"),
        default_num_ctx=getattr(settings, "ollama_num_ctx", 8192),
    )
    hermes_native_executor = HermesNativeExecutor(
        ollama_client=ollama_client,
        model_router=ModelRouter(models_config),
        on_event=_dispatcher(c, "hermes_native_executor"),
    )

    return create_code_intelligence_agent(
        on_event=_dispatcher(c, "code_intelligence"),
        klaatcode_agent=klaatcode_agent,
        ohmypi_agent=ohmypi_agent,
        hermes_native_executor=hermes_native_executor,
        memory_manager=memory_manager,
    )


def _bind_code_intelligence_routes(c: Any, svc: Any) -> list[Any]:
    from backend.api.routes.code_intelligence import create_code_intelligence_routes

    return [create_code_intelligence_routes(svc)]


# ── Monitoring ────────────────────────────────────────────────────────

def _make_system_monitor(c: Any) -> Any:
    from backend.monitoring.system_monitor import SystemMonitor

    return SystemMonitor()


# ======================================================================
# The catalogue
# ======================================================================

SERVICE_SPECS: tuple[ServiceSpec, ...] = (
    # ── Core event plumbing (built first: everything else emits through it) ──
    ServiceSpec(
        key="event_hub",
        name="Event Hub",
        category=ComponentCategory.CORE,
        factory=_make_event_hub,
        description="WebSocket fan-out to connected Cockpit clients",
        capabilities=("event_fanout", "websocket"),
    ),
    ServiceSpec(
        key="system_event_bus",
        name="System Event Bus",
        category=ComponentCategory.CORE,
        factory=_make_system_event_bus,
        description="Durable, queryable pub/sub bus (HOS-025)",
        capabilities=("pubsub", "event_history"),
    ),
    ServiceSpec(
        key="event_dispatcher",
        name="Event Dispatcher",
        category=ComponentCategory.CORE,
        factory=_make_dispatcher,
        dependencies=("event_hub", "system_event_bus"),
        description="The single on_event seam handed to every subsystem",
        capabilities=("event_dispatch",),
    ),
    # ── Runtime ──
    ServiceSpec(
        key="resource_manager",
        name="Resource Manager",
        category=ComponentCategory.RUNTIME,
        factory=_make_resource_manager,
        dependencies=("event_dispatcher",),
        route_binder=_bind_resource_routes,
        produced_events=("resource.allocated", "resource.released", "resource.threshold"),
        description="VRAM/RAM allocation and thresholds (HOS-035)",
        capabilities=("vram_allocation", "ram_allocation"),
    ),
    ServiceSpec(
        key="runtime_orchestrator",
        name="Runtime Orchestrator",
        category=ComponentCategory.RUNTIME,
        factory=_make_runtime_orchestrator,
        dependencies=("event_dispatcher",),
        route_binder=_bind_orchestrator_routes,
        produced_events=("orchestrator.decision",),
        description="Runtime selection and arbitration (HOS-038)",
        capabilities=("runtime_selection",),
    ),
    ServiceSpec(
        key="model_registry",
        name="Model Registry",
        category=ComponentCategory.RUNTIME,
        factory=_make_model_registry,
        description="Discovered model catalogue (HOS-040)",
        capabilities=("model_catalogue",),
    ),
    ServiceSpec(
        key="runtime_discovery",
        name="Runtime Discovery",
        category=ComponentCategory.RUNTIME,
        factory=_make_discovery_engine,
        dependencies=("model_registry", "event_dispatcher"),
        route_binder=_bind_discovery_routes,
        produced_events=("discovery.completed", "benchmark.completed"),
        description="Model/runtime discovery and benchmarking (HOS-040)",
        capabilities=("discovery", "benchmark"),
    ),
    ServiceSpec(
        key="recovery_engine",
        name="Runtime Recovery Engine",
        category=ComponentCategory.RUNTIME,
        factory=_make_recovery_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_recovery_routes,
        produced_events=("recovery.started", "recovery.completed"),
        description="Failure recovery policies and actions (HOS-036)",
        capabilities=("recovery", "circuit_breaker"),
    ),
    ServiceSpec(
        key="runtime_intelligence",
        name="Runtime Intelligence",
        category=ComponentCategory.RUNTIME,
        factory=_make_learning_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_intelligence_routes,
        description="Scoring, learning and recommendations (HOS-037)",
        capabilities=("scoring", "recommendation"),
    ),
    ServiceSpec(
        key="runtime_simulation",
        name="Runtime Simulation",
        category=ComponentCategory.RUNTIME,
        factory=_make_simulation_engine,
        dependencies=("runtime_orchestrator", "recovery_engine", "event_dispatcher"),
        route_binder=_bind_simulation_routes,
        produced_events=("simulation.completed",),
        description="What-if simulation over live runtime state",
        capabilities=("simulation",),
    ),
    ServiceSpec(
        key="runtime_event_bus",
        name="Runtime Event Bus",
        category=ComponentCategory.RUNTIME,
        factory=_make_runtime_event_bus,
        route_binder=_bind_runtime_event_routes,
        produced_events=(
            "runtime.started",
            "runtime.failed",
            "runtime.health_changed",
            "routing.decision",
        ),
        consumed_events=("runtime.stopped", "runtime.recovered"),
        description="Runtime-scoped event stream + WebSocket (HOS-034)",
        capabilities=("runtime_events", "websocket"),
    ),
    ServiceSpec(
        key="ktransformers",
        name="KTransformers Runtime",
        category=ComponentCategory.INTEGRATION,
        factory=_make_kt_runtime,
        route_binder=_bind_kt_routes,
        produced_events=(
            "ktransformers.model.loaded",
            "ktransformers.inference.completed",
        ),
        description="KTransformers inference integration (HOS-052C)",
        adopts_module_singleton=True,
        capabilities=("inference", "moe_offload"),
    ),
    # ── Execution (shared by every mission surface) ──
    ServiceSpec(
        key="task_executor",
        name="Real Task Executor",
        category=ComponentCategory.EXECUTION,
        factory=_make_task_executor,
        # model_intelligence isn't consulted through the container (the
        # factory reaches its module-level singleton directly, like
        # _make_model_intelligence itself does) — declared here so the
        # dependency graph reflects the real coupling introduced by
        # model_for/on_execution rather than hiding it. resource_manager is
        # a real dependency (HOS-069): real VRAM admission checking before
        # each local inference call.
        dependencies=("event_dispatcher", "model_intelligence", "resource_manager"),
        produced_events=("execution.task_completed",),
        description="Performs the actual work for one task (R-001)",
        capabilities=("inference", "task_execution"),
    ),
    ServiceSpec(
        key="execution_engine",
        name="Task Execution Pipeline",
        category=ComponentCategory.EXECUTION,
        factory=_make_execution_engine,
        # agent_supervisor is a real dependency since HOS-070: its registry
        # is what a real task execution now syncs status/metrics into.
        # security_engine likewise: its AgentTrustEngine now gets fed real
        # outcomes.
        dependencies=("task_executor", "event_dispatcher", "agent_supervisor",
                      "security_engine"),
        produced_events=(
            "execution.started", "execution.planning", "execution.task_started",
            "execution.task_completed", "execution.completed", "execution.failed",
        ),
        description="Scheduler, coordinator, validation and feedback pipeline "
                    "shared by /missions and /autonomous (HOS-050)",
        capabilities=("task_pipeline", "validation", "scheduling"),
    ),
    # ── Mission ──
    ServiceSpec(
        key="mission_executor",
        name="Mission Graph Executor",
        category=ComponentCategory.MISSION,
        factory=_make_graph_executor,
        # execution_controller is what its execute_node hook delegates to
        # (HOS-069 — it wraps the same shared execution_engine, but routing
        # through it is what makes a real node execution visible to
        # /api/v1/execution); without it the DAG would fall back to
        # declaring every node successful.
        dependencies=("event_dispatcher", "execution_controller"),
        route_binder=_bind_mission_routes,
        produced_events=("mission.started", "mission.completed", "mission.failed"),
        description="Mission DAG execution (HOS-041)",
        capabilities=("mission_graph", "dag_execution"),
    ),
    ServiceSpec(
        key="mission_planner",
        name="Intelligent Mission Planner",
        category=ComponentCategory.MISSION,
        factory=_make_mission_planner,
        # memory_manager and evolution_engine aren't planning dependencies —
        # they ride along here because _bind_planner_routes is the injection
        # point that already reaches into backend.mission.routes' module
        # state after both mission_executor and this service exist (see its
        # docstring). HOS-068 adds evolution_engine for the same reason
        # memory_manager is already here: mission completion now feeds
        # EvolutionEngine.ingest_metrics(), mirroring the autonomous memory
        # loop's write-back.
        dependencies=("mission_executor", "event_dispatcher", "memory_manager", "evolution_engine"),
        route_binder=_bind_planner_routes,
        produced_events=("mission.created",),
        description="Mission decomposition and planning (HOS-042)",
        capabilities=("planning", "decomposition"),
    ),
    # ── Agents ──
    ServiceSpec(
        key="agent_supervisor",
        name="Agent Supervisor",
        category=ComponentCategory.AGENT,
        factory=_make_agent_supervisor,
        # security_engine is a real dependency of the *route binder*
        # (HOS-070: injects the real AgentTrustEngine into agents/routes.py),
        # not of the factory itself — declared here so build order puts it
        # first regardless.
        dependencies=("event_dispatcher", "security_engine"),
        route_binder=_bind_agent_routes,
        produced_events=("agent.registered", "agent.state_changed", "agent.failed"),
        description="Agent lifecycle and dispatch (HOS-043)",
        capabilities=("agent_lifecycle", "dispatch"),
    ),
    ServiceSpec(
        key="collaboration",
        name="Multi-Agent Collaboration",
        category=ComponentCategory.AGENT,
        factory=_make_collaboration_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_collaboration_routes,
        produced_events=("delegation.requested", "consensus.reached", "conflict.resolved"),
        description="Delegation, consensus, conflict resolution (HOS-044)",
        capabilities=("delegation", "consensus", "review"),
    ),
    # ── Memory ──
    ServiceSpec(
        key="memory_manager",
        name="Unified Memory",
        category=ComponentCategory.MEMORY,
        factory=_make_memory_manager,
        dependencies=("event_dispatcher",),
        route_binder=_bind_memory_routes,
        produced_events=("memory.stored", "memory.indexed", "experience.recorded"),
        description="Working/episodic/semantic/procedural memory (HOS-047)",
        capabilities=("hybrid_search", "knowledge_graph", "embeddings"),
    ),
    # ── Skills & tools ──
    ServiceSpec(
        key="skill_distributor",
        name="Dynamic Skills",
        category=ComponentCategory.SKILL,
        factory=_make_skill_distributor,
        route_binder=_bind_skill_routes,
        produced_events=("skill.loaded", "skill.selected", "skill.distributed"),
        description="Skill selection, loading and distribution (HOS-048)",
        adopts_module_singleton=True,
        capabilities=("skill_selection", "skill_distribution"),
    ),
    ServiceSpec(
        key="tool_platform",
        name="MCP & Tool Platform",
        category=ComponentCategory.TOOL,
        factory=_make_tool_platform,
        route_binder=_bind_tool_routes,
        produced_events=("tool.executed", "mcp.connected"),
        description="Tool registry, execution, MCP clients (HOS-049)",
        adopts_module_singleton=True,
        capabilities=("tool_execution", "mcp_client", "sandbox"),
    ),
    # ── Governance ──
    ServiceSpec(
        key="policy_engine",
        name="Policy & Human Approval",
        category=ComponentCategory.POLICY,
        factory=_make_policy_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_policy_routes,
        produced_events=("approval.requested", "approval.granted", "audit.created"),
        description="Policy evaluation, approval queue, audit log (HOS-046)",
        capabilities=("policy", "approval", "audit"),
    ),
    ServiceSpec(
        key="workspace_manager",
        name="Workspace & Sandbox",
        category=ComponentCategory.WORKSPACE,
        factory=_make_workspace_manager,
        dependencies=("event_dispatcher",),
        route_binder=_bind_workspace_routes,
        produced_events=("workspace.created", "workspace.locked", "artifact.created"),
        description="Isolated agent workspaces (HOS-045)",
        capabilities=("workspace", "isolation", "artifacts"),
    ),
    ServiceSpec(
        key="security_engine",
        name="Security & Trust",
        category=ComponentCategory.POLICY,
        factory=_make_security_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_security_routes,
        produced_events=(
            "security.permission.denied",
            "security.threat.detected",
            "security.agent.trust.updated",
        ),
        description="Permissions, trust, threats, isolation (HOS-057)",
        capabilities=("permissions", "trust", "threat_detection"),
    ),
    # ── Execution ──
    ServiceSpec(
        key="execution_controller",
        name="Autonomous Mission Execution",
        category=ComponentCategory.EXECUTION,
        factory=_make_execution_controller,
        # HOS-069: wraps the shared execution_engine rather than a private
        # instance — see _make_execution_controller's docstring.
        dependencies=("execution_engine",),
        route_binder=_bind_execution_routes,
        produced_events=("execution.started", "execution.completed", "checkpoint.saved"),
        description="Execution state machine and controller (HOS-050)",
        capabilities=("execution", "checkpointing"),
    ),
    # ── Autonomy, evolution, conversation, explainability ──
    ServiceSpec(
        key="autonomous_engine",
        name="Autonomous Agentic Core",
        category=ComponentCategory.EXECUTION,
        factory=_make_autonomous_engine,
        # memory_manager and evolution_engine are real dependencies: the factory
        # closes the learning loop with both, so they must be built first.
        # execution_engine is the shared task pipeline it now runs on.
        # runtime_orchestrator lets DecisionEngine report a runtime that is
        # actually registered instead of one of three that never were.
        # model_intelligence isn't consulted through the container (same
        # module-singleton reach-through as task_executor) — declared so the
        # dependency graph reflects the real coupling ModelAutonomousAdapter
        # introduces. mission_planner + mission_executor (the container key
        # for GraphExecutor, see _make_autonomous_engine's own note on the
        # naming collision) are HOS-067's real DAG pipeline.
        dependencies=("event_dispatcher", "memory_manager", "evolution_engine",
                      "execution_engine", "runtime_orchestrator", "model_intelligence",
                      "mission_planner", "mission_executor"),
        route_binder=_bind_autonomous_routes,
        produced_events=("goal.started", "goal.completed"),
        description="Goal-driven autonomous execution (HOS-063)",
        capabilities=("goal_execution", "autonomy"),
    ),
    ServiceSpec(
        key="evolution_engine",
        name="Self Evolution Engine",
        category=ComponentCategory.SYSTEM,
        factory=_make_evolution_engine,
        dependencies=("event_dispatcher",),
        route_binder=_bind_evolution_routes,
        produced_events=("proposal.created", "proposal.applied", "evolution.completed"),
        description="Improvement detection, simulation, application (HOS-058)",
        capabilities=("self_improvement", "proposal_simulation"),
    ),
    ServiceSpec(
        key="conversation_manager",
        name="Conversation Intelligence",
        category=ComponentCategory.SYSTEM,
        factory=_make_conversation_manager,
        route_binder=_bind_conversation_routes,
        produced_events=("conversation.started", "conversation.message"),
        description="Sessions, intent routing, contextual responses (HOS-064)",
        capabilities=("conversation", "intent_analysis"),
    ),
    ServiceSpec(
        key="explainability",
        name="Explainability",
        category=ComponentCategory.SYSTEM,
        factory=_make_explainer,
        route_binder=_bind_explainability_routes,
        produced_events=("decision.explained",),
        description="Human-readable decision explanations (HOS-064)",
        capabilities=("explanation",),
    ),
    ServiceSpec(
        key="model_intelligence",
        name="Model Intelligence",
        category=ComponentCategory.SYSTEM,
        factory=_make_model_intelligence,
        route_binder=_bind_model_intelligence_routes,
        # resource_manager is a route-binder-only dependency (HOS-071,
        # same pattern as agent_supervisor's security_engine dependency in
        # HOS-070): the factory itself doesn't need it, but
        # _bind_model_intelligence_routes does, and the dependency graph
        # should reflect that real coupling rather than hide it.
        dependencies=("resource_manager",),
        produced_events=("model.profiled", "model.recommended"),
        description="Model profiling, prediction, adaptive routing (HOS-065)",
        adopts_module_singleton=True,
        capabilities=("model_profiling", "adaptive_routing"),
    ),
    # ── Integrations ──
    ServiceSpec(
        key="alexandrie",
        name="Alexandrie Integration",
        category=ComponentCategory.INTEGRATION,
        factory=_make_alexandrie,
        route_binder=_bind_alexandrie_routes,
        produced_events=("alexandrie.synced", "alexandrie.circuit.opened"),
        description="Document sync, conflict resolution, graph (HOS-053B)",
        capabilities=("document_sync", "knowledge_import"),
    ),
    ServiceSpec(
        key="klaatcode",
        name="KlaatCode Integration",
        category=ComponentCategory.INTEGRATION,
        factory=_make_klaatcode,
        route_binder=_bind_klaatcode_routes,
        produced_events=("klaatcode.executed",),
        description="KlaatCode agent and MCP bridge (HOS-054D)",
        adopts_module_singleton=True,
        capabilities=("code_analysis", "code_execution"),
    ),
    ServiceSpec(
        key="ohmypi",
        name="Oh My Pi Integration",
        category=ComponentCategory.INTEGRATION,
        factory=_make_ohmypi,
        route_binder=_bind_ohmypi_routes,
        produced_events=("ohmypi.executed",),
        description="Oh My Pi capabilities bridge (HOS-055C)",
        adopts_module_singleton=True,
        capabilities=("shell", "automation"),
    ),
    ServiceSpec(
        key="code_intelligence",
        name="Code Intelligence Agent",
        category=ComponentCategory.AGENT,
        factory=_make_code_intelligence,
        dependencies=("klaatcode", "ohmypi", "memory_manager", "workspace_manager", "event_dispatcher"),
        route_binder=_bind_code_intelligence_routes,
        produced_events=(
            "ci.agent.ready", "ci.routing.decided", "ci.task.started",
            "ci.task.completed", "ci.task.failed", "ci.hybrid.executed",
            "ci.memory.recorded",
        ),
        description="Routes code tasks to KlaatCode/Oh My Pi (HOS-055D, R-006)",
        capabilities=("code_routing", "code_analysis", "code_execution"),
    ),
    # ── Monitoring ──
    ServiceSpec(
        key="system_monitor",
        name="System Monitor",
        category=ComponentCategory.SYSTEM,
        factory=_make_system_monitor,
        produced_events=("system.metrics",),
        description="CPU/RAM/disk sampling and history (HOS-062)",
        capabilities=("metrics", "monitoring"),
    ),
)


SPECS_BY_KEY: dict[str, ServiceSpec] = {s.key: s for s in SERVICE_SPECS}


def resolve_build_order() -> list[ServiceSpec]:
    """Topologically order the specs so dependencies are built first.

    Raises ``ValueError`` on an unknown dependency or a cycle — both are
    assembly bugs that must fail loudly at startup rather than produce a
    half-built container.
    """
    ordered: list[ServiceSpec] = []
    state: dict[str, int] = {}  # 0 = visiting, 1 = done

    def visit(key: str, trail: tuple[str, ...]) -> None:
        if state.get(key) == 1:
            return
        if state.get(key) == 0:
            cycle = " -> ".join(trail + (key,))
            raise ValueError(f"dependency cycle among services: {cycle}")
        spec = SPECS_BY_KEY.get(key)
        if spec is None:
            raise ValueError(
                f"service {trail[-1] if trail else '?'!r} depends on unknown service {key!r}"
            )
        state[key] = 0
        for dep in spec.dependencies:
            visit(dep, trail + (key,))
        state[key] = 1
        ordered.append(spec)

    for spec in SERVICE_SPECS:
        visit(spec.key, ())
    return ordered
