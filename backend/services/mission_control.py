"""Hermes OS Mission Control Service Layer (HOS-027).

Central facade aggregating all kernel modules (HOS-009 through HOS-026)
into a single, unified API. No business logic is duplicated — every
method delegates to the appropriate kernel module.

Designed to be consumed by:
- Next.js frontend
- REST / WebSocket / GraphQL APIs
- MCP, CLI, SDK adapters
- Alexandrie, Homelable integrations
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ── HOS-010 / HOS-015 Runtime ────────────────────────────────────────
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector
from backend.ral.runtime_decision import RuntimeDecision, RuntimeDecisionEngine
from backend.ral.runtime_router import RuntimeRouter
from backend.ral.runtime_health import RuntimeHealthMonitor, RuntimeHealthStatus
from backend.ral.runtime_performance import RuntimePerformanceAnalyzer, RuntimePerformanceMetrics
from backend.ral.runtime_recovery import RuntimeRecoveryManager

# ── HOS-017 / HOS-018 / HOS-019 / HOS-020 Agent ─────────────────────
from backend.agent.task_planner import PlannedTask, PlanningStrategy, TaskPlanner
from backend.agent.lifecycle import AgentLifecycleManager, AgentState
from backend.agent.supervisor import (
    MissionContext,
    MissionInstance,
    MissionState,
    MultiAgentSupervisor,
)
from backend.agent.execution_engine import (
    ExecutionContext,
    ExecutionEngine,
    ExecutionResult,
)

# ── HOS-021 Memory ──────────────────────────────────────────────────
from backend.memory.unified_memory import (
    MemoryEntry,
    MemoryQuery,
    MemoryResult,
    MemoryScope,
    MemoryStatistics,
    UnifiedMemory,
)

# ── HOS-022 Skills ──────────────────────────────────────────────────
from backend.skills.orchestrator import (
    AdaptiveSkillOrchestrator,
    SkillDescriptor,
    SkillSelection,
    SkillStatistics,
)

# ── HOS-025 Events ──────────────────────────────────────────────────
from backend.events.system_event_bus import (
    EventFilter,
    EventSeverity,
    EventStatistics as BusStatistics,
    SystemEvent,
    SystemEventBus,
    SystemEventType,
)

# ── HOS-023 Hermes Agent ────────────────────────────────────────────
try:
    from backend.integrations.hermes_agent import (
        HermesAgentAdapter,
        HermesAgentConfiguration,
        HermesAgentSession,
        HermesAgentStatus,
        HermesAgentError,
        HermesAgentNotConnectedError,
        HermesAgentTask,
        HermesAgentExecution,
        HermesCapability,
    )
    _HERMES_AVAILABLE = True
except ImportError:
    _HERMES_AVAILABLE = False


# ======================================================================
# Exceptions
# ======================================================================


class MissionControlError(Exception):
    """Raised when a mission control operation fails."""


class MissionControlConfigurationError(MissionControlError):
    """Raised when configuration is invalid."""


# ======================================================================
# Enums
# ======================================================================


class MissionControlStatus(str, Enum):
    """Overall system status indicator."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"


# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class MissionControlConfiguration:
    """Configuration for the mission control service.

    Attributes:
        default_planning_strategy: Strategy to use when creating plans.
        mission_timeout_s: Default mission timeout in seconds.
        runtime_failure_threshold: Consecutive failures before circuit opens.
        runtime_recovery_timeout: Seconds before half-open probe.
        event_history_size: Max events retained in the system event bus.
        log_events_to_bus: Whether to automatically publish all facade
            operations as system events.
        metadata: Free-form configuration metadata.
    """

    default_planning_strategy: PlanningStrategy = PlanningStrategy.BALANCED
    mission_timeout_s: float = 300.0
    runtime_failure_threshold: int = 3
    runtime_recovery_timeout: float = 30.0
    event_history_size: int = 5000
    log_events_to_bus: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionControlStatistics:
    """Aggregated statistics across all subsystems.

    Attributes:
        missions: Supervisor mission statistics.
        agents: Agent lifecycle statistics.
        runtimes: Runtime performance metrics (per runtime).
        events: System event bus statistics.
        memory: Memory layer statistics.
        skills: Skill orchestrator statistics.
        engine: Execution engine statistics.
        uptime_seconds: Seconds since service creation.
        metadata: Free-form metadata.
    """

    missions: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)
    runtimes: dict[str, RuntimePerformanceMetrics] = field(default_factory=dict)
    events: dict[str, Any] = field(default_factory=dict)
    memory: Optional[MemoryStatistics] = None
    skills: Optional[SkillStatistics] = None
    engine: Optional[dict[str, Any]] = None
    uptime_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionControlHealth:
    """Detailed system health snapshot.

    Attributes:
        status: Overall system status.
        kernel_status: Whether the core kernel modules are operational.
        runtime_status: Number of available / degraded / unavailable runtimes.
        memory_status: Whether the memory layer is operational.
        integrations_status: Status of optional integrations.
        event_bus_status: Whether the event bus is operational.
        uptime: Seconds since service creation.
        version: Semantic version string.
    """

    status: MissionControlStatus = MissionControlStatus.HEALTHY
    kernel_status: str = "operational"
    runtime_status: dict[str, int] = field(default_factory=lambda: {"available": 0, "degraded": 0, "unavailable": 0})
    memory_status: str = "operational"
    integrations_status: dict[str, str] = field(default_factory=dict)
    event_bus_status: str = "operational"
    uptime: float = 0.0
    version: str = "0.1.0"


# ======================================================================
# Mission Control Service
# ======================================================================


class MissionControlService:
    """Central facade for all Hermes OS kernel modules.

    The service is thread-safe and delegates every operation to the
    appropriate kernel module without duplicating business logic.

    Args:
        supervisor: Multi-agent supervisor for mission lifecycle.
        lifecycle: Agent lifecycle manager.
        execution_engine: Mission execution engine.
        decision_engine: Runtime decision engine.
        runtime_router: Runtime execution router.
        runtime_registry: Runtime instance registry.
        runtime_selector: Runtime selector.
        runtime_health: Runtime health monitor.
        runtime_performance: Runtime performance analyzer.
        runtime_recovery: Runtime recovery / circuit breaker manager.
        memory: Unified memory layer.
        skills: Adaptive skill orchestrator.
        event_bus: System event bus.
        hermes_adapter: Optional Hermes Agent adapter.
        planner: Optional task planner (created with default strategy if not provided).
        config: Service configuration.
    """

    def __init__(
        self,
        supervisor: MultiAgentSupervisor,
        lifecycle: AgentLifecycleManager,
        execution_engine: ExecutionEngine,
        decision_engine: RuntimeDecisionEngine,
        runtime_router: RuntimeRouter,
        runtime_registry: RuntimeRegistry,
        runtime_selector: RuntimeSelector,
        runtime_health: RuntimeHealthMonitor,
        runtime_performance: RuntimePerformanceAnalyzer,
        runtime_recovery: RuntimeRecoveryManager,
        memory: UnifiedMemory,
        skills: AdaptiveSkillOrchestrator,
        event_bus: SystemEventBus,
        *,
        hermes_adapter: Any = None,
        planner: Optional[TaskPlanner] = None,
        config: Optional[MissionControlConfiguration] = None,
    ) -> None:
        self._supervisor = supervisor
        self._lifecycle = lifecycle
        self._engine = execution_engine
        self._decision = decision_engine
        self._router = runtime_router
        self._registry = runtime_registry
        self._selector = runtime_selector
        self._health = runtime_health
        self._performance = runtime_performance
        self._recovery = runtime_recovery
        self._memory = memory
        self._skills = skills
        self._bus = event_bus
        self._hermes = hermes_adapter
        self._planner = planner or TaskPlanner(strategy=config.default_planning_strategy if config else PlanningStrategy.BALANCED)
        self._config = config or MissionControlConfiguration()
        # perf_counter, not time(): uptime must not jump when the wall clock is
        # adjusted (NTP, DST), and time() resolves to 15.6 ms on Windows, which
        # reported a freshly built service as having 0.0s of uptime.
        self._created_at = time.perf_counter()
        self._lock = threading.RLock()

    @property
    def config(self) -> MissionControlConfiguration:
        """Return the current configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Internal: event publishing helper
    # ------------------------------------------------------------------

    def _publish(
        self,
        event_type: SystemEventType | str,
        source: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        severity: EventSeverity | str = EventSeverity.INFO,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Publish a system event if logging is enabled."""
        if self._config.log_events_to_bus:
            self._bus.publish(
                event_type=event_type,
                source=source,
                payload=payload or {},
                severity=severity,
                metadata=metadata or {},
            )

    # ==================================================================
    # MISSION FACADE
    # ==================================================================

    def create_mission(
        self,
        title: str,
        objective: str,
        tasks: list[PlannedTask],
        *,
        mission_id: Optional[str] = None,
        priority: int = 5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MissionInstance:
        """Create and plan a new mission.

        Delegates to :meth:`MultiAgentSupervisor.create_mission`.

        Args:
            title: Mission title.
            objective: Mission objective.
            tasks: List of planned tasks.
            mission_id: Optional explicit mission id.
            priority: Mission priority (1 = highest).
            metadata: Optional metadata.

        Returns:
            The created mission instance (READY state after planning).
        """
        with self._lock:
            ctx = MissionContext(
                mission_id=mission_id or f"mission_{int(time.time())}",
                title=title,
                objective=objective,
                priority=priority,
                metadata=metadata or {},
            )
            mission = self._supervisor.create_mission(ctx, tasks)
            self._publish(SystemEventType.MISSION, "mission_control.create_mission", payload={
                "mission_id": ctx.mission_id,
                "title": title,
                "state": mission.state.value,
            })
            return mission

    def start_mission(self, mission_id: str) -> MissionInstance:
        """Start a mission.

        Delegates to :meth:`MultiAgentSupervisor.start_mission`.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        mission = self._supervisor.start_mission(mission_id)
        # Also start the execution engine if the mission was created through it.
        self._publish(SystemEventType.MISSION, "mission_control.start_mission", payload={
            "mission_id": mission_id,
        })
        return mission

    def pause_mission(self, mission_id: str) -> MissionInstance:
        """Pause a running mission.

        Delegates to :meth:`MultiAgentSupervisor.pause_mission`.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        mission = self._supervisor.pause_mission(mission_id)
        self._publish(SystemEventType.MISSION, "mission_control.pause_mission", payload={
            "mission_id": mission_id,
        })
        return mission

    def resume_mission(self, mission_id: str) -> MissionInstance:
        """Resume a paused mission.

        Delegates to :meth:`MultiAgentSupervisor.resume_mission`.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        mission = self._supervisor.resume_mission(mission_id)
        self._publish(SystemEventType.MISSION, "mission_control.resume_mission", payload={
            "mission_id": mission_id,
        })
        return mission

    def cancel_mission(self, mission_id: str) -> MissionInstance:
        """Cancel a mission.

        Delegates to :meth:`MultiAgentSupervisor.cancel_mission`.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        mission = self._supervisor.cancel_mission(mission_id)
        self._publish(SystemEventType.MISSION, "mission_control.cancel_mission", payload={
            "mission_id": mission_id,
        })
        return mission

    def get_mission(self, mission_id: str) -> MissionInstance:
        """Return a mission by id.

        Delegates to :meth:`MultiAgentSupervisor.get_mission`.

        Args:
            mission_id: Mission identifier.

        Returns:
            The mission instance.
        """
        return self._supervisor.get_mission(mission_id)

    def list_missions(
        self,
        *,
        state: Optional[MissionState] = None,
    ) -> list[MissionInstance]:
        """List all missions, optionally filtered by state.

        Delegates to :meth:`MultiAgentSupervisor.list_missions`.

        Args:
            state: Optional mission state filter.

        Returns:
            List of matching mission instances.
        """
        return self._supervisor.list_missions(state=state)

    def tick_supervisor(self) -> list[str]:
        """Advance all running missions by one step.

        Delegates to :meth:`MultiAgentSupervisor.tick`.

        Returns:
            List of mission ids that changed state.
        """
        return self._supervisor.tick()

    # ==================================================================
    # RUNTIME FACADE
    # ==================================================================

    def list_runtimes(self) -> list[dict[str, Any]]:
        """List all registered runtimes with their status and capabilities.

        Delegates to :class:`RuntimeRegistry`, :class:`RuntimeHealthMonitor`,
        and :class:`RuntimePerformanceAnalyzer`.

        Returns:
            A list of dicts with runtime info.
        """
        names = self._registry.list_available()
        result: list[dict[str, Any]] = []
        for name in names:
            try:
                runtime = self._registry.get(name)
                health = self._health.check_runtime(name)
                metrics = self._performance.get_metrics(name)
                caps = list(runtime.capabilities.available) if runtime.capabilities else []
                circuit = self._recovery.should_retry(name)
                result.append({
                    "name": name,
                    "status": runtime.status.value if isinstance(runtime.status, Enum) else runtime.status,
                    "health": health.value if isinstance(health, Enum) else health,
                    "capabilities": caps,
                    "circuit_allowed": circuit,
                    "metrics": {
                        "executions": metrics.executions,
                        "failures": metrics.failures,
                        "avg_latency_ms": metrics.avg_latency_ms,
                        "success_rate": metrics.success_rate,
                        "reliability_score": metrics.reliability_score,
                        "performance_score": metrics.performance_score,
                    },
                })
            except Exception:
                result.append({"name": name, "status": "error"})
        return result

    def runtime_health(self, runtime_name: str) -> dict[str, Any]:
        """Return detailed health information for a runtime.

        Args:
            runtime_name: Runtime identifier.

        Returns:
            Health status dict.
        """
        health = self._health.check_runtime(runtime_name)
        metrics = self._health.get_metrics(runtime_name)
        return {
            "health": health.value if isinstance(health, Enum) else health,
            "executions": metrics.executions,
            "failures": metrics.failures,
            "failure_rate": metrics.failure_rate,
            "avg_latency_ms": metrics.avg_latency_ms,
        }

    def runtime_metrics(self, runtime_name: str) -> RuntimePerformanceMetrics:
        """Return performance metrics for a runtime.

        Delegates to :meth:`RuntimePerformanceAnalyzer.get_metrics`.

        Args:
            runtime_name: Runtime identifier.

        Returns:
            Performance metrics.
        """
        return self._performance.get_metrics(runtime_name)

    def select_runtime(
        self,
        capability: str,
        *,
        preference: Optional[str] = None,
        preferred_name: Optional[str] = None,
    ) -> RuntimeDecision:
        """Select the best runtime for a capability.

        Delegates to :meth:`RuntimeDecisionEngine.select_runtime`.

        Args:
            capability: Required capability.
            preference: Optional deployment hint.
            preferred_name: Optional preferred runtime name.

        Returns:
            A RuntimeDecision with the selection.
        """
        return self._decision.select_runtime(
            capability,
            preference=preference,
            preferred_name=preferred_name,
        )

    def rank_runtimes(self) -> list[tuple[str, RuntimePerformanceMetrics]]:
        """Rank all runtimes by reliability and performance.

        Delegates to :meth:`RuntimePerformanceAnalyzer.rank_runtimes`.

        Returns:
            Sorted list of (name, metrics) tuples.
        """
        return self._performance.rank_runtimes()

    # ==================================================================
    # EXECUTION FACADE
    # ==================================================================

    def start_execution(
        self,
        mission: MissionContext,
        tasks: list[PlannedTask],
        *,
        execution_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExecutionContext:
        """Start a mission execution.

        Delegates to :meth:`ExecutionEngine.start`.

        Args:
            mission: Mission context.
            tasks: List of planned tasks.
            execution_id: Optional execution id.
            metadata: Optional metadata.

        Returns:
            The execution context.
        """
        ctx = self._engine.start(mission, tasks, execution_id=execution_id, metadata=metadata)
        self._publish(SystemEventType.EXECUTION, "mission_control.start_execution", payload={
            "execution_id": ctx.execution_id,
            "mission_id": ctx.mission_id,
        })
        return ctx

    def tick_execution(self) -> list[str]:
        """Advance execution by one step.

        Delegates to :meth:`ExecutionEngine.tick`.

        Returns:
            List of event descriptions.
        """
        return self._engine.tick()

    def pause_execution(self) -> None:
        """Pause the current execution.

        Delegates to :meth:`ExecutionEngine.pause`.
        """
        self._engine.pause()
        self._publish(SystemEventType.EXECUTION, "mission_control.pause_execution")

    def resume_execution(self) -> None:
        """Resume a paused execution.

        Delegates to :meth:`ExecutionEngine.resume`.
        """
        self._engine.resume()
        self._publish(SystemEventType.EXECUTION, "mission_control.resume_execution")

    def cancel_execution(self) -> None:
        """Cancel the current execution.

        Delegates to :meth:`ExecutionEngine.cancel`.
        """
        self._engine.cancel()
        self._publish(SystemEventType.EXECUTION, "mission_control.cancel_execution")

    def recover_execution(self) -> bool:
        """Attempt to recover a failed execution.

        Delegates to :meth:`ExecutionEngine.recover`.

        Returns:
            True if recovery was initiated.
        """
        recovered = self._engine.recover()
        if recovered:
            self._publish(SystemEventType.EXECUTION, "mission_control.recover_execution", severity=EventSeverity.WARNING)
        return recovered

    def get_execution_status(self) -> dict[str, Any]:
        """Return execution status.

        Delegates to :meth:`ExecutionEngine.get_status`.

        Returns:
            Status dict.
        """
        return self._engine.get_status()

    def get_execution_result(self) -> Optional[ExecutionResult]:
        """Return the execution result.

        Delegates to :meth:`ExecutionEngine.get_result`.

        Returns:
            Result or None if not finished.
        """
        return self._engine.get_result()

    # ==================================================================
    # MEMORY FACADE
    # ==================================================================

    def store_memory(
        self,
        content: str,
        *,
        scope: MemoryScope | str = MemoryScope.SESSION,
        title: str = "",
        tags: Optional[frozenset[str]] = None,
        importance: int = 1,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store a new memory entry.

        Delegates to :meth:`UnifiedMemory.store`.

        Args:
            content: The content to store.
            scope: Memory scope.
            title: Optional title.
            tags: Optional tags.
            importance: Importance 1-10.
            metadata: Optional metadata.

        Returns:
            The stored entry.
        """
        entry = self._memory.store(content, scope=scope, title=title, tags=tags, importance=importance, metadata=metadata)
        self._publish(SystemEventType.MEMORY, "mission_control.store_memory", payload={
            "entry_id": entry.id,
            "scope": entry.scope.value if isinstance(entry.scope, Enum) else entry.scope,
        })
        return entry

    def search_memory(self, query: MemoryQuery) -> MemoryResult:
        """Search memory entries.

        Delegates to :meth:`UnifiedMemory.search`.

        Args:
            query: Search parameters.

        Returns:
            Search result.
        """
        return self._memory.search(query)

    def update_memory(
        self,
        entry_id: str,
        *,
        content: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[frozenset[str]] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Update a memory entry.

        Delegates to :meth:`UnifiedMemory.update`.

        Args:
            entry_id: Entry to update.
            content: New content.
            title: New title.
            tags: New tags.
            importance: New importance.
            metadata: Merged metadata.

        Returns:
            Updated entry.
        """
        return self._memory.update(entry_id, content=content, title=title, tags=tags, importance=importance, metadata=metadata)

    def get_memory(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by id.

        Delegates to :meth:`UnifiedMemory.get`.

        Args:
            entry_id: Entry identifier.

        Returns:
            Entry or None.
        """
        return self._memory.get(entry_id)

    def get_memory_statistics(self) -> MemoryStatistics:
        """Return memory layer statistics.

        Delegates to :meth:`UnifiedMemory.get_statistics`.

        Returns:
            Memory statistics.
        """
        return self._memory.get_statistics()

    # ==================================================================
    # SKILLS FACADE
    # ==================================================================

    def list_skills(self) -> list[SkillDescriptor]:
        """Return all registered skills.

        Delegates to the skill repository.

        Returns:
            List of skill descriptors.
        """
        return self._skills._repository.list_all()  # noqa: SLF001

    def select_skills(
        self,
        *,
        required_capabilities: Optional[frozenset[str]] = None,
        tags: Optional[frozenset[str]] = None,
        preferred_ids: Optional[frozenset[str]] = None,
    ) -> SkillSelection:
        """Select skills by capabilities, tags or explicit ids.

        Delegates to :meth:`AdaptiveSkillOrchestrator.select_skills`.

        Args:
            required_capabilities: Required capabilities.
            tags: Skill tags to search.
            preferred_ids: Explicit skill ids.

        Returns:
            Selection result.
        """
        return self._skills.select_skills(
            required_capabilities=required_capabilities,
            tags=tags,
            preferred_ids=preferred_ids,
        )

    def recommend_skills(
        self,
        mission_description: str,
        *,
        max_recommendations: int = 5,
    ) -> list[SkillDescriptor]:
        """Recommend skills for a mission.

        Delegates to :meth:`AdaptiveSkillOrchestrator.recommend`.

        Args:
            mission_description: Description of the mission.
            max_recommendations: Max recommendations.

        Returns:
            List of recommended skills.
        """
        return self._skills.recommend(mission_description, max_recommendations=max_recommendations)

    def load_skill_bundle(self, bundle_id: str) -> int:
        """Load all skills from a bundle.

        Delegates to :meth:`AdaptiveSkillOrchestrator.load_bundle`.

        Args:
            bundle_id: Bundle identifier.

        Returns:
            Number of skills loaded.
        """
        count = self._skills.load_bundle(bundle_id)
        self._publish(SystemEventType.SKILL, "mission_control.load_skill_bundle", payload={
            "bundle_id": bundle_id,
            "count": count,
        })
        return count

    def get_skill_statistics(self) -> SkillStatistics:
        """Return skill orchestrator statistics.

        Delegates to :meth:`AdaptiveSkillOrchestrator.get_statistics`.

        Returns:
            Skill statistics.
        """
        return self._skills.get_statistics()

    # ==================================================================
    # OBSERVABILITY FACADE (SystemEventBus)
    # ==================================================================

    def query_events(
        self,
        filter_: Optional[EventFilter] = None,
    ) -> list[SystemEvent]:
        """Query system events.

        Delegates to :meth:`SystemEventBus.query`.

        Args:
            filter_: Optional event filter.

        Returns:
            List of matching events.
        """
        return self._bus.query(filter_)

    def publish_event(
        self,
        event_type: SystemEventType | str,
        source: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        severity: EventSeverity | str = EventSeverity.INFO,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SystemEvent:
        """Publish a system event.

        Delegates to :meth:`SystemEventBus.publish`.

        Args:
            event_type: Event type family.
            source: Source identifier.
            payload: Event payload.
            severity: Event severity.
            metadata: Optional metadata.

        Returns:
            The published event.
        """
        return self._bus.publish(
            event_type=event_type,
            source=source,
            payload=payload,
            severity=severity,
            metadata=metadata,
        )

    def export_events(
        self,
        *,
        filter_: Optional[EventFilter] = None,
        indent: Optional[int] = None,
    ) -> str:
        """Export events as JSON.

        Delegates to :meth:`SystemEventBus.export`.

        Args:
            filter_: Optional event filter.
            indent: JSON indentation.

        Returns:
            JSON string.
        """
        return self._bus.export(filter_=filter_, indent=indent)

    def get_bus_statistics(self) -> BusStatistics:
        """Return system event bus statistics.

        Delegates to :meth:`SystemEventBus.statistics`.

        Returns:
            Bus statistics.
        """
        return self._bus.statistics()

    def clear_events(self) -> None:
        """Clear the event history.

        Delegates to :meth:`SystemEventBus.clear`.
        """
        self._bus.clear()

    # ==================================================================
    # INTEGRATION FACADE (Hermes Agent)
    # ==================================================================

    def connect_hermes_agent(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> bool:
        """Connect to Hermes Agent.

        Args:
            base_url: Ollama API base URL.
            timeout: HTTP client timeout.

        Returns:
            True if connected successfully.

        Raises:
            MissionControlError: If Hermes Agent adapter is not available.
        """
        if not _HERMES_AVAILABLE or self._hermes is None:
            raise MissionControlError("Hermes Agent adapter is not available.")
        try:
            self._hermes.connect(base_url=base_url, timeout=timeout)
            self._publish(SystemEventType.INTEGRATION, "mission_control.connect_hermes_agent", payload={
                "base_url": base_url,
            })
            return True
        except HermesAgentNotConnectedError:
            return False

    def disconnect_hermes_agent(self) -> bool:
        """Disconnect from Hermes Agent.

        Returns:
            True if disconnected.
        """
        if not _HERMES_AVAILABLE or self._hermes is None:
            return False
        try:
            self._hermes.disconnect()
            self._publish(SystemEventType.INTEGRATION, "mission_control.disconnect_hermes_agent")
            return True
        except Exception:
            return False

    def hermes_health(self) -> str:
        """Check Hermes Agent health.

        Returns:
            Connection status string.
        """
        if not _HERMES_AVAILABLE or self._hermes is None:
            return "unavailable"
        return self._hermes.health()

    def execute_hermes_task(
        self,
        task_type: str,
        messages: list[dict[str, Any]],
        *,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a task through Hermes Agent.

        Args:
            task_type: Type of task (e.g. "chat", "code").
            messages: Conversation messages.
            session_id: Optional session id.

        Returns:
            Task execution result as dict.
        """
        if not _HERMES_AVAILABLE or self._hermes is None:
            raise MissionControlError("Hermes Agent adapter is not available.")
        execution = self._hermes.execute_task(task_type, messages, session_id=session_id)
        return {
            "success": execution.success,
            "content": execution.content,
            "duration_ms": execution.duration_ms,
            "task_id": execution.task_id if hasattr(execution, "task_id") else None,
        }

    def list_hermes_sessions(self) -> list[dict[str, Any]]:
        """List Hermes Agent sessions.

        Returns:
            List of session dicts.
        """
        if not _HERMES_AVAILABLE or self._hermes is None:
            return []
        return self._hermes.list_sessions()

    # ==================================================================
    # SYSTEM FACADE
    # ==================================================================

    def health(self) -> MissionControlHealth:
        """Return a comprehensive system health snapshot.

        Checks all subsystems and aggregates their status.

        Returns:
            Detailed health snapshot.
        """
        # ── Kernel status ──
        kernel_ok = True
        try:
            _ = self._registry.list_available()
        except Exception:
            kernel_ok = False

        # ── Runtime status ──
        available = degraded = unavailable = 0
        for name in self._registry.list_available():
            try:
                h = self._health.check_runtime(name)
                if h == RuntimeHealthStatus.AVAILABLE:
                    available += 1
                elif h == RuntimeHealthStatus.DEGRADED:
                    degraded += 1
                else:
                    unavailable += 1
            except Exception:
                unavailable += 1

        # ── Integrations status ──
        integrations: dict[str, str] = {}
        if _HERMES_AVAILABLE and self._hermes is not None:
            try:
                integrations["hermes_agent"] = self._hermes.health()
            except Exception:
                integrations["hermes_agent"] = "error"
        else:
            integrations["hermes_agent"] = "not_configured"

        # ── Aggregate ──
        bus_ok = True
        try:
            _ = self._bus.statistics()
        except Exception:
            bus_ok = False

        overall = MissionControlStatus.HEALTHY
        if not kernel_ok:
            overall = MissionControlStatus.UNHEALTHY
        elif degraded > 0 or unavailable > 0:
            overall = MissionControlStatus.DEGRADED

        return MissionControlHealth(
            status=overall,
            kernel_status="operational" if kernel_ok else "unhealthy",
            runtime_status={"available": available, "degraded": degraded, "unavailable": unavailable},
            memory_status="operational",
            integrations_status=integrations,
            event_bus_status="operational" if bus_ok else "unhealthy",
            uptime=time.perf_counter() - self._created_at,
        )

    def diagnostics(self) -> dict[str, Any]:
        """Return a full diagnostic snapshot of all subsystems.

        Returns:
            A nested dict with detailed subsystem information.
        """
        return {
            "uptime_seconds": time.perf_counter() - self._created_at,
            "missions": {
                "count": len(self._supervisor._missions),  # noqa: SLF001
                "states": self._mission_state_distribution(),
            },
            "agents": {
                "total": len(self._lifecycle.list_agents()),
                "by_state": self._agent_state_distribution(),
            },
            "runtimes": {
                "registered": self._registry.list_available(),
                "health": self._runtime_health_summary(),
            },
            "memory": {
                "total_entries": self._memory.get_statistics().total_entries,
            },
            "skills": {
                "registered": len(self._skills._repository.list_all()),  # noqa: SLF001
            },
            "events": {
                "published": self._bus.statistics().total_published,
                "history_size": self._bus.statistics().history_size,
            },
            "integrations": {
                "hermes_agent": "available" if (_HERMES_AVAILABLE and self._hermes is not None) else "unavailable",
            },
        }

    def status(self) -> MissionControlStatus:
        """Return the overall system status.

        A lightweight check.

        Returns:
            The current overall status.
        """
        return self.health().status

    def statistics(self) -> MissionControlStatistics:
        """Return aggregated statistics from all subsystems.

        Collects statistics from every kernel module into a single
        :class:`MissionControlStatistics` object.

        Returns:
            Combined statistics.
        """
        with self._lock:
            # ── Supervisor statistics ──
            sup_stats = self._supervisor.get_statistics()

            # ── Agent lifecycle statistics ──
            all_agents = self._lifecycle.list_agents()
            running = sum(1 for a in all_agents if a.state == AgentState.RUNNING)

            # ── Memory statistics ──
            mem_stats = self._memory.get_statistics()

            # ── Skill statistics ──
            skill_stats = self._skills.get_statistics()

            # ── Event bus statistics ──
            bus_stats = self._bus.statistics()

            # ── Runtime performance metrics ──
            perf_metrics = self._performance.get_all_metrics()

            # ── Execution engine statistics ──
            try:
                engine_stats = {
                    "state": self._engine.get_status().get("state", "idle"),
                    "task_progress": self._engine.get_status().get("task_progress", {}),
                    "statistics": self._engine.get_statistics(),
                }
            except Exception:
                engine_stats = {"state": "idle"}

            return MissionControlStatistics(
                missions={
                    "started": sup_stats.missions_started,
                    "completed": sup_stats.missions_completed,
                    "failed": sup_stats.missions_failed,
                    "agents_created": sup_stats.agents_created,
                    "agents_running": sup_stats.agents_running,
                },
                agents={
                    "total": len(all_agents),
                    "running": running,
                },
                runtimes=perf_metrics,
                events={
                    "published": bus_stats.total_published,
                    "consumed": bus_stats.total_consumed,
                    "subscribers": bus_stats.subscriber_count,
                },
                memory=mem_stats,
                skills=skill_stats,
                engine=engine_stats,
                uptime_seconds=time.perf_counter() - self._created_at,
            )

    # ------------------------------------------------------------------
    # Internal helpers for diagnostics
    # ------------------------------------------------------------------

    def _mission_state_distribution(self) -> dict[str, int]:
        """Count missions per state."""
        counts: dict[str, int] = {}
        for m in self._supervisor.list_missions():
            state = m.state.value
            counts[state] = counts.get(state, 0) + 1
        return counts

    def _agent_state_distribution(self) -> dict[str, int]:
        """Count agents per state."""
        counts: dict[str, int] = {}
        for a in self._lifecycle.list_agents():
            state = a.state.value
            counts[state] = counts.get(state, 0) + 1
        return counts

    def _runtime_health_summary(self) -> dict[str, str]:
        """Map runtime names to health status strings."""
        summary: dict[str, str] = {}
        for name in self._registry.list_available():
            try:
                h = self._health.check_runtime(name)
                summary[name] = h.value
            except Exception:
                summary[name] = "error"
        return summary
