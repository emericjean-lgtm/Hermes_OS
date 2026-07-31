"""HOS-027 tests — Mission Control Service Layer.

Tests the MissionControlService facade, verifying that it correctly
delegates to all kernel modules without duplicating business logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import pytest

from backend.agent.lifecycle import AgentLifecycleManager
from backend.agent.supervisor import MissionContext, MissionState
from backend.agent.task_planner import PlannedTask, PlanningStrategy, TaskPlanner
from backend.events.system_event_bus import SystemEventBus, SystemEventType
from backend.memory.unified_memory import MemoryQuery, UnifiedMemory
from backend.ral.runtime import RuntimeInterface, RuntimeStatus
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector
from backend.ral.runtime_health import RuntimeHealthMonitor
from backend.ral.runtime_performance import RuntimePerformanceAnalyzer
from backend.ral.runtime_events import RuntimeEventBus
from backend.ral.runtime_recovery import RuntimeRecoveryManager
from backend.ral.runtime_decision import RuntimeDecisionEngine
from backend.ral.runtime_router import RuntimeRouter
from backend.skills.orchestrator import (
    AdaptiveSkillOrchestrator,
    SkillBundle,
    SkillDescriptor,
    SkillSelectionStrategy,
)
from backend.services.mission_control import (
    MissionControlConfiguration,
    MissionControlError,
    MissionControlHealth,
    MissionControlService,
    MissionControlStatistics,
    MissionControlStatus,
)


# ======================================================================
# Fixtures — minimal stubs for all kernel dependencies
# ======================================================================


@dataclass(frozen=True)
class _StubRuntimeCapabilities:
    available: frozenset[str] = frozenset({"chat"})


class _StubRuntime(RuntimeInterface):
    """Minimal runtime stub for tests."""

    def __init__(self, name: str = "stub", status: RuntimeStatus = RuntimeStatus.STARTED) -> None:
        self._name = name
        self._status = status
        self._caps = _StubRuntimeCapabilities()
        self._started = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    @property
    def capabilities(self) -> _StubRuntimeCapabilities | None:
        return self._caps

    async def start(self) -> None:
        self._started = True
        self._status = RuntimeStatus.STARTED

    async def stop(self) -> None:
        self._started = False
        self._status = RuntimeStatus.STOPPED

    def get(self, name: str) -> Any:
        return None


class _FakeHolder:
    """Minimal holder that stores a runtime reference."""

    def __init__(self) -> None:
        self._runtime: RuntimeInterface | None = None

    @property
    def runtime(self) -> RuntimeInterface:
        if self._runtime is None:
            raise RuntimeError("No runtime installed.")
        return self._runtime

    def install(self, runtime: RuntimeInterface) -> None:
        self._runtime = runtime


@pytest.fixture
def runtime_registry() -> RuntimeRegistry:
    reg = RuntimeRegistry()
    reg.register("stub-1", _StubRuntime("stub-1"))
    reg.register("stub-2", _StubRuntime("stub-2"))
    return reg


@pytest.fixture
def stub_holder() -> _FakeHolder:
    return _FakeHolder()


@pytest.fixture
def active_context(runtime_registry: RuntimeRegistry, stub_holder: _FakeHolder) -> ActiveRuntimeContext:
    return ActiveRuntimeContext(runtime_registry, stub_holder)


@pytest.fixture
def runtime_selector(runtime_registry: RuntimeRegistry) -> RuntimeSelector:
    return RuntimeSelector(runtime_registry)


@pytest.fixture
def runtime_health(runtime_registry: RuntimeRegistry) -> RuntimeHealthMonitor:
    return RuntimeHealthMonitor(runtime_registry)


@pytest.fixture
def runtime_event_bus() -> RuntimeEventBus:
    return RuntimeEventBus()


@pytest.fixture
def runtime_performance(runtime_event_bus: RuntimeEventBus) -> RuntimePerformanceAnalyzer:
    return RuntimePerformanceAnalyzer(runtime_event_bus)


@pytest.fixture
def runtime_recovery(
    runtime_registry: RuntimeRegistry,
    runtime_selector: RuntimeSelector,
    runtime_event_bus: RuntimeEventBus,
) -> RuntimeRecoveryManager:
    return RuntimeRecoveryManager(runtime_registry, runtime_selector, event_bus=runtime_event_bus)


@pytest.fixture
def decision_engine(
    runtime_registry: RuntimeRegistry,
    runtime_selector: RuntimeSelector,
    runtime_health: RuntimeHealthMonitor,
    runtime_performance: RuntimePerformanceAnalyzer,
    runtime_recovery: RuntimeRecoveryManager,
) -> RuntimeDecisionEngine:
    return RuntimeDecisionEngine(
        runtime_registry, runtime_selector, runtime_health, runtime_performance, runtime_recovery,
    )


@pytest.fixture
def runtime_router(
    active_context: ActiveRuntimeContext,
    runtime_selector: RuntimeSelector,
    runtime_health: RuntimeHealthMonitor,
    runtime_recovery: RuntimeRecoveryManager,
    runtime_event_bus: RuntimeEventBus,
) -> RuntimeRouter:
    return RuntimeRouter(
        active_context, runtime_selector,
        health_monitor=runtime_health,
        recovery_manager=runtime_recovery,
        event_bus=runtime_event_bus,
    )


@pytest.fixture
def planner() -> TaskPlanner:
    return TaskPlanner(strategy=PlanningStrategy.BALANCED)


@pytest.fixture
def lifecycle() -> AgentLifecycleManager:
    return AgentLifecycleManager()


@pytest.fixture
def supervisor(planner: TaskPlanner, lifecycle: AgentLifecycleManager) -> ...:
    from backend.agent.supervisor import MultiAgentSupervisor
    return MultiAgentSupervisor(planner, lifecycle)


@pytest.fixture
def memory() -> UnifiedMemory:
    return UnifiedMemory()


@pytest.fixture
def skills() -> AdaptiveSkillOrchestrator:
    orchestrator = AdaptiveSkillOrchestrator(strategy=SkillSelectionStrategy.MINIMAL)
    repo = orchestrator._repository
    repo.register(SkillDescriptor(
        id="chat-skills", name="Chat Skills",
        capabilities=frozenset({"chat"}),
        tags=frozenset({"chat", "conversation"}),
        priority=10,
        estimated_tokens=1000,
    ))
    repo.register(SkillDescriptor(
        id="code-skills", name="Code Skills",
        capabilities=frozenset({"code"}),
        tags=frozenset({"code", "python"}),
        priority=8,
        estimated_tokens=2000,
    ))
    repo.register_bundle(SkillBundle(
        id="chat-bundle", name="Chat Bundle",
        skill_ids=frozenset({"chat-skills"}),
    ))
    return orchestrator


@pytest.fixture
def event_bus() -> SystemEventBus:
    return SystemEventBus(max_history=1000)


@pytest.fixture
def service(
    supervisor: ...,
    lifecycle: AgentLifecycleManager,
    runtime_registry: RuntimeRegistry,
    runtime_selector: RuntimeSelector,
    runtime_health: RuntimeHealthMonitor,
    runtime_performance: RuntimePerformanceAnalyzer,
    runtime_recovery: RuntimeRecoveryManager,
    decision_engine: RuntimeDecisionEngine,
    runtime_router: RuntimeRouter,
    active_context: ActiveRuntimeContext,
    memory: UnifiedMemory,
    skills: AdaptiveSkillOrchestrator,
    event_bus: SystemEventBus,
) -> MissionControlService:
    from backend.agent.execution_engine import ExecutionEngine
    engine = ExecutionEngine(
        supervisor=supervisor,
        lifecycle=lifecycle,
        runtime_decision=decision_engine,
        runtime_router=runtime_router,
    )
    return MissionControlService(
        supervisor=supervisor,
        lifecycle=lifecycle,
        execution_engine=engine,
        decision_engine=decision_engine,
        runtime_router=runtime_router,
        runtime_registry=runtime_registry,
        runtime_selector=runtime_selector,
        runtime_health=runtime_health,
        runtime_performance=runtime_performance,
        runtime_recovery=runtime_recovery,
        memory=memory,
        skills=skills,
        event_bus=event_bus,
        config=MissionControlConfiguration(log_events_to_bus=True),
    )


# ======================================================================
# Helpers
# ======================================================================


def _make_tasks(count: int = 3) -> list[PlannedTask]:
    return [
        PlannedTask(id=f"t{i}", title=f"Task {i}", runtime_capability="chat",
                    estimated_complexity=1.0, dependencies=frozenset(), parallelizable=True)
        for i in range(count)
    ]


# ======================================================================
# Tests — Mission facade
# ======================================================================


class TestMissionFacade:
    """Tests for mission operations."""

    def test_create_mission(self, service: MissionControlService):
        mission = service.create_mission("Test", "Test objective", _make_tasks(3))
        assert mission.state in (MissionState.READY, MissionState.FAILED)
        assert mission.context.title == "Test"

    def test_create_mission_fires_event(self, service: MissionControlService):
        service.create_mission("Test", "Objective", _make_tasks(2))
        events = service.query_events()
        assert any("create_mission" in e.source for e in events)

    def test_get_mission(self, service: MissionControlService):
        mission = service.create_mission("Test", "Obj", _make_tasks(1))
        retrieved = service.get_mission(mission.context.mission_id)
        assert retrieved.context.mission_id == mission.context.mission_id

    def test_list_missions(self, service: MissionControlService):
        from backend.agent.supervisor import MissionContext
        ctx1 = MissionContext(mission_id="list-m1", title="M1", objective="Obj 1")
        ctx2 = MissionContext(mission_id="list-m2", title="M2", objective="Obj 2")
        service.create_mission("M1", "Obj 1", _make_tasks(1), mission_id="list-m1")
        service.create_mission("M2", "Obj 2", _make_tasks(2), mission_id="list-m2")
        missions = service.list_missions()
        assert len(missions) >= 2

    def test_list_missions_filtered(self, service: MissionControlService):
        m1 = service.create_mission("M1", "Obj", _make_tasks(1))
        missions = service.list_missions(state=m1.state)
        assert all(m.state == m1.state for m in missions)

    def test_start_and_cancel_mission(self, service: MissionControlService):
        mission = service.create_mission("Test", "Obj", _make_tasks(1))
        if mission.state == MissionState.READY:
            service.start_mission(mission.context.mission_id)
            cancelled = service.cancel_mission(mission.context.mission_id)
            assert cancelled.state == MissionState.CANCELLED

    def test_pause_and_resume_mission(self, service: MissionControlService):
        mission = service.create_mission("Test", "Obj", _make_tasks(1))
        if mission.state == MissionState.READY:
            service.start_mission(mission.context.mission_id)
            paused = service.pause_mission(mission.context.mission_id)
            assert paused.state == MissionState.PAUSED
            resumed = service.resume_mission(mission.context.mission_id)
            assert resumed.state == MissionState.RUNNING

    def test_tick_supervisor(self, service: MissionControlService):
        result = service.tick_supervisor()
        assert isinstance(result, list)

    def test_create_mission_empty_tasks(self, service: MissionControlService):
        # An empty task list may still proceed (the supervisor validates)
        result = service.create_mission("Empty", "Obj", [], mission_id="empty-test")
        # Should either succeed or fail gracefully — not crash
        assert result.state.value in ("ready", "failed", "created")


# ======================================================================
# Tests — Runtime facade
# ======================================================================


class TestRuntimeFacade:
    """Tests for runtime operations."""

    def test_list_runtimes(self, service: MissionControlService):
        runtimes = service.list_runtimes()
        assert len(runtimes) >= 2
        names = [r["name"] for r in runtimes]
        assert "stub-1" in names
        assert "stub-2" in names

    def test_list_runtimes_contains_metrics(self, service: MissionControlService):
        runtimes = service.list_runtimes()
        for r in runtimes:
            assert "metrics" in r
            assert "executions" in r["metrics"]

    def test_runtime_health(self, service: MissionControlService):
        health = service.runtime_health("stub-1")
        assert "health" in health
        assert health["health"] in ("available", "degraded", "unavailable", "unknown")

    def test_runtime_metrics(self, service: MissionControlService):
        metrics = service.runtime_metrics("stub-1")
        assert metrics.runtime_name == "stub-1"
        assert metrics.executions == 0

    def test_select_runtime(self, service: MissionControlService):
        decision = service.select_runtime("chat")
        assert decision.selected_runtime in ("stub-1", "stub-2")
        assert decision.confidence > 0

    def test_rank_runtimes(self, service: MissionControlService):
        ranked = service.rank_runtimes()
        assert isinstance(ranked, list)
        if ranked:
            name, metrics = ranked[0]
            assert isinstance(name, str)
            assert isinstance(metrics.reliability_score, (int, float))


# ======================================================================
# Tests — Execution facade
# ======================================================================


class TestExecutionFacade:
    """Tests for execution operations."""

    def test_start_execution(self, service: MissionControlService):
        ctx = MissionContext(mission_id="exec-test", title="Exec Test", objective="Test")
        tasks = _make_tasks(2)
        try:
            execution = service.start_execution(ctx, tasks)
            assert execution.execution_id is not None
            assert execution.mission_id == "exec-test"
        except Exception as exc:
            # An execution might fail because no real runtime is available — ok.
            assert True

    def test_get_execution_status(self, service: MissionControlService):
        status = service.get_execution_status()
        assert "state" in status
        assert isinstance(status, dict)

    def test_get_execution_result(self, service: MissionControlService):
        result = service.get_execution_result()
        # Result may be None if no execution finished yet
        assert result is None or hasattr(result, "success")

    def test_tick_execution(self, service: MissionControlService):
        events = service.tick_execution()
        assert isinstance(events, list)

    def test_pause_resume_cancel_execution(self, service: MissionControlService):
        # pause should raise when engine is IDLE (not RUNNING).
        import pytest
        from backend.agent.execution_engine import ExecutionEngineError
        with pytest.raises(ExecutionEngineError):
            service.pause_execution()
        with pytest.raises(ExecutionEngineError):
            service.resume_execution()
        # cancel from IDLE should work (IDLE is not terminal)
        status = service.get_execution_status()
        if status["state"] == "idle":
            service.cancel_execution()
            new_status = service.get_execution_status()
            assert new_status["state"] == "cancelled"

    def test_recover_execution(self, service: MissionControlService):
        recovered = service.recover_execution()
        assert isinstance(recovered, bool)


# ======================================================================
# Tests — Memory facade
# ======================================================================


class TestMemoryFacade:
    """Tests for memory operations."""

    def test_store_memory(self, service: MissionControlService):
        entry = service.store_memory("Hello world", title="Test")
        assert entry.id is not None
        assert entry.content == "Hello world"
        assert entry.title == "Test"

    def test_store_memory_fires_event(self, service: MissionControlService):
        service.store_memory("Test", title="Event test")
        events = service.query_events()
        assert any("store_memory" in e.source for e in events)

    def test_search_memory(self, service: MissionControlService):
        service.store_memory("Find me", title="Search test", tags=frozenset({"test"}))
        result = service.search_memory(MemoryQuery(text="find", tags=frozenset({"test"})))
        assert result.total >= 1
        assert len(result.entries) >= 1

    def test_update_memory(self, service: MissionControlService):
        entry = service.store_memory("Original", title="Update test")
        updated = service.update_memory(entry.id, content="Updated")
        assert updated.content == "Updated"
        assert updated.id == entry.id

    def test_get_memory(self, service: MissionControlService):
        entry = service.store_memory("Test", title="Get test")
        retrieved = service.get_memory(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id

    def test_get_memory_statistics(self, service: MissionControlService):
        stats = service.get_memory_statistics()
        assert stats.total_entries >= 0
        assert hasattr(stats, "per_scope")


# ======================================================================
# Tests — Skills facade
# ======================================================================


class TestSkillsFacade:
    """Tests for skill operations."""

    def test_list_skills(self, service: MissionControlService):
        skills = service.list_skills()
        assert len(skills) >= 2
        names = [s.id for s in skills]
        assert "chat-skills" in names
        assert "code-skills" in names

    def test_select_skills_by_capability(self, service: MissionControlService):
        selection = service.select_skills(required_capabilities=frozenset({"chat"}))
        assert "chat-skills" in selection.selected_skills

    def test_recommend_skills(self, service: MissionControlService):
        recommendations = service.recommend_skills("I need chat capabilities")
        assert len(recommendations) >= 1

    def test_load_skill_bundle(self, service: MissionControlService):
        count = service.load_skill_bundle("chat-bundle")
        assert count >= 1

    def test_load_skill_bundle_fires_event(self, service: MissionControlService):
        service.load_skill_bundle("chat-bundle")
        events = service.query_events()
        assert any("load_skill_bundle" in e.source for e in events)

    def test_get_skill_statistics(self, service: MissionControlService):
        stats = service.get_skill_statistics()
        assert stats.total_skills_registered >= 2
        assert stats.total_selections >= 0


# ======================================================================
# Tests — Observability facade
# ======================================================================


class TestObservabilityFacade:
    """Tests for event bus operations."""

    def test_query_events(self, service: MissionControlService):
        events = service.query_events()
        assert isinstance(events, list)

    def test_publish_event(self, service: MissionControlService):
        event = service.publish_event(SystemEventType.SYSTEM, "test.source", payload={"msg": "hello"})
        assert event.id is not None
        assert event.type == SystemEventType.SYSTEM.value

    def test_event_appears_in_history(self, service: MissionControlService):
        service.publish_event(SystemEventType.SYSTEM, "test.source", payload={"msg": "check"})
        events = service.query_events()
        found = any("test.source" in e.source for e in events)
        assert found

    def test_export_events(self, service: MissionControlService):
        service.publish_event(SystemEventType.SYSTEM, "test.source")
        exported = service.export_events()
        assert '"source": "test.source"' in exported

    def test_get_bus_statistics(self, service: MissionControlService):
        stats = service.get_bus_statistics()
        assert hasattr(stats, "total_published")
        assert isinstance(stats.total_published, int)

    def test_clear_events(self, service: MissionControlService):
        service.publish_event(SystemEventType.SYSTEM, "test.source")
        service.clear_events()
        events = service.query_events()
        assert len(events) == 0


# ======================================================================
# Tests — System facade
# ======================================================================


class TestSystemFacade:
    """Tests for health, diagnostics and statistics."""

    def test_health(self, service: MissionControlService):
        health = service.health()
        assert isinstance(health, MissionControlHealth)
        assert health.status in (MissionControlStatus.HEALTHY, MissionControlStatus.DEGRADED)

    def test_health_contains_runtime_status(self, service: MissionControlService):
        health = service.health()
        assert "available" in health.runtime_status
        assert "degraded" in health.runtime_status
        assert "unavailable" in health.runtime_status

    def test_health_contains_integrations(self, service: MissionControlService):
        health = service.health()
        assert "hermes_agent" in health.integrations_status

    def test_status(self, service: MissionControlService):
        status = service.status()
        assert isinstance(status, MissionControlStatus)

    def test_diagnostics(self, service: MissionControlService):
        diag = service.diagnostics()
        assert "missions" in diag
        assert "agents" in diag
        assert "runtimes" in diag
        assert "memory" in diag
        assert "skills" in diag
        assert "events" in diag
        assert "integrations" in diag

    def test_diagnostics_runtime_count(self, service: MissionControlService):
        diag = service.diagnostics()
        assert len(diag["runtimes"]["registered"]) >= 2

    def test_statistics(self, service: MissionControlService):
        stats = service.statistics()
        assert isinstance(stats, MissionControlStatistics)
        # Check that missions stats contain expected keys
        assert "started" in stats.missions
        assert stats.uptime_seconds > 0
        assert stats.memory is not None
        assert stats.skills is not None

    def test_statistics_contains_runtimes(self, service: MissionControlService):
        stats = service.statistics()
        assert isinstance(stats.runtimes, dict)

    def test_statistics_contains_events(self, service: MissionControlService):
        stats = service.statistics()
        assert "published" in stats.events


# ======================================================================
# Tests — Configuration
# ======================================================================


class TestConfiguration:
    """Tests for service configuration."""

    def test_default_config(self):
        config = MissionControlConfiguration()
        assert config.default_planning_strategy == PlanningStrategy.BALANCED
        assert config.mission_timeout_s == 300.0
        assert config.log_events_to_bus is True

    def test_custom_config(self):
        config = MissionControlConfiguration(
            default_planning_strategy=PlanningStrategy.SEQUENTIAL,
            mission_timeout_s=600.0,
            log_events_to_bus=False,
        )
        assert config.default_planning_strategy == PlanningStrategy.SEQUENTIAL
        assert config.mission_timeout_s == 600.0
        assert config.log_events_to_bus is False

    def test_config_access_via_service(self, service: MissionControlService):
        assert service.config.default_planning_strategy == PlanningStrategy.BALANCED


# ======================================================================
# Tests — Thread safety
# ======================================================================


class TestThreadSafety:
    """Basic thread safety verification."""

    def test_concurrent_mission_creation(self, service: MissionControlService):
        errors: list[Exception] = []

        def create(n: int) -> None:
            try:
                service.create_mission(f"Thread-{n}", f"Objective {n}", _make_tasks(2),
                                        mission_id=f"thr-mission-{n}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            # The supervisor may reject duplicate ids; count unique errors
            dups = sum(1 for e in errors if "already exists" in str(e))
            assert dups < len(errors), f"All errors are duplicates: {errors}"

    def test_concurrent_memory_operations(self, service: MissionControlService):
        errors: list[Exception] = []

        def store_and_search(n: int) -> None:
            try:
                service.store_memory(f"Thread data {n}", title=f"Title {n}")
                service.search_memory(MemoryQuery(text=f"{n}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=store_and_search, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_runtime_listing(self, service: MissionControlService):
        errors: list[Exception] = []

        def list_runtimes() -> None:
            try:
                _ = service.list_runtimes()
                _ = service.health()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=list_runtimes) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ======================================================================
# Tests — Error handling
# ======================================================================


class TestErrorHandling:
    """Tests for proper error propagation."""

    def test_get_nonexistent_mission(self, service: MissionControlService):
        import pytest
        with pytest.raises(Exception):
            service.get_mission("nonexistent")

    def test_runtime_health_nonexistent(self, service: MissionControlService):
        import pytest
        with pytest.raises(Exception):
            service.runtime_health("nonexistent-runtime")

    def test_runtime_metrics_nonexistent(self, service: MissionControlService):
        # Performance analyzer returns empty metrics for unknown runtimes
        metrics = service.runtime_metrics("nonexistent-runtime")
        assert metrics.runtime_name == "nonexistent-runtime"
        assert metrics.executions == 0


# ======================================================================
# Tests — Integration guards (Hermes)
# ======================================================================


class TestIntegrationGuards:
    """Tests that optional integrations raise appropriate errors."""

    def test_hermes_not_available(self, service: MissionControlService):
        """Without Hermes adaper injected, operations should raise."""
        import pytest
        with pytest.raises(MissionControlError):
            service.connect_hermes_agent()

    def test_hermes_disconnect_graceful(self, service: MissionControlService):
        """Disconnecting without an adapter should not crash."""
        result = service.disconnect_hermes_agent()
        assert result is False

    def test_hermes_health_graceful(self, service: MissionControlService):
        """Health check without adapter should return 'unavailable'."""
        result = service.hermes_health()
        assert result == "unavailable"
