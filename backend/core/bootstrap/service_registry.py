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

from dataclasses import dataclass
from typing import Any, Callable, Optional

from backend.core.integration.component_registry import ComponentCategory

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
    from backend.execution.task_executor import RealTaskExecutor

    return RealTaskExecutor(on_event=_dispatcher(c, "task_executor"))


def _make_execution_engine(c: Any) -> Any:
    from backend.execution.mission_executor import MissionExecutor

    return MissionExecutor(
        task_executor=c.get("task_executor"),
        on_event=_dispatcher(c, "execution_engine"),
    )


# ── Mission layer ─────────────────────────────────────────────────────

def _make_graph_executor(c: Any) -> Any:
    """The DAG traverser, with its node hook bound to the real engine.

    ``execute_node`` has always been an injection point and nothing ever used
    it, so it fell back to ``lambda n: True`` — every node of every mission was
    declared successful without any work being done (R-002 P1).
    """
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.node_execution import make_node_executor

    return GraphExecutor(
        on_event=_dispatcher(c, "mission_executor"),
        execute_node=make_node_executor(c.get("execution_engine")),
    )


def _bind_mission_routes(c: Any, svc: Any) -> list[Any]:
    from backend.mission.routes import create_mission_routes

    return [create_mission_routes(svc)]


def _make_mission_planner(c: Any) -> Any:
    from backend.mission.planner.mission_planner import MissionPlanner

    return MissionPlanner(
        graph_executor=c.get("mission_executor"),
        on_event=_dispatcher(c, "mission_planner"),
    )


def _bind_planner_routes(c: Any, svc: Any) -> list[Any]:
    from backend.mission.planner.routes import create_planner_routes
    from backend.mission.routes import set_mission_planner

    # The /missions router needs the planner to turn a described goal into a
    # DAG, but route binders run inline as each service is built and the planner
    # is built *after* the graph executor it depends on. Injecting from this side
    # keeps the ordering correct and avoids a mission_executor ↔ mission_planner
    # dependency cycle (R-002 P1).
    set_mission_planner(svc)
    return [create_planner_routes(svc)]


# ── Agent layer ───────────────────────────────────────────────────────

def _make_agent_supervisor(c: Any) -> Any:
    from backend.agents.agent_supervisor import AgentSupervisor

    return AgentSupervisor(on_event=_dispatcher(c, "agent_supervisor"))


def _bind_agent_routes(c: Any, svc: Any) -> list[Any]:
    from backend.agents.routes import create_agent_routes

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
    """Adopt the controller `backend.execution.routes` already built."""
    from backend.execution import routes as execution_routes

    return execution_routes._controller  # noqa: SLF001 - deliberate adoption


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
    )
    loop = getattr(getattr(engine, "orchestrator", None), "memory_loop", None)
    if loop is not None:
        loop.set_memory_manager(c.get("memory_manager"))
        loop.set_evolution_engine(c.get("evolution_engine"))
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
    from backend.model_intelligence.routes import create_model_intelligence_routes

    return [create_model_intelligence_routes(svc)]


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
        dependencies=("event_dispatcher",),
        produced_events=("execution.task_completed",),
        description="Performs the actual work for one task (R-001)",
        capabilities=("inference", "task_execution"),
    ),
    ServiceSpec(
        key="execution_engine",
        name="Task Execution Pipeline",
        category=ComponentCategory.EXECUTION,
        factory=_make_execution_engine,
        dependencies=("task_executor", "event_dispatcher"),
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
        # execution_engine is what its execute_node hook delegates to; without
        # it the DAG would fall back to declaring every node successful.
        dependencies=("event_dispatcher", "execution_engine"),
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
        dependencies=("mission_executor", "event_dispatcher"),
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
        dependencies=("event_dispatcher",),
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
        route_binder=_bind_execution_routes,
        produced_events=("execution.started", "execution.completed", "checkpoint.saved"),
        description="Execution state machine and controller (HOS-050)",
        adopts_module_singleton=True,
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
        dependencies=("event_dispatcher", "memory_manager", "evolution_engine",
                      "execution_engine"),
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
