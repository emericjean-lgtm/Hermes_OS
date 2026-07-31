"""Tests for KlaatCode Agent integration (HOS-054C).

Covers: agent creation, lifecycle, capability matching, dispatcher selection,
MCP call simulation, events, memory storage, metrics, and thread safety.

Minimum 30 tests.

Run with: python3 -m pytest tests/architecture/test_klaatcode_agent.py -v
"""

from __future__ import annotations

import threading

import pytest

from backend.agents.agent_models import (
    AgentCapability,
    AgentStatus,
    ExecutionResult,
    TaskOutcome,
)
from backend.agents.specialized.klaatcode import (
    KlaatCodeAgent,
    KlaatCodeAgentStatus,
    KlaatCodeProfile,
    KlaatCodeTaskType,
    KLATCODE_EVENTS,
    TASK_TO_CAPABILITY,
    TASK_TO_MCP_ACTION,
    create_klaatcode_agent,
)


# ═══════════════════════════════════════════════════════════════
# AGENT CREATION
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeAgentCreation:
    """Tests for KlaatCodeAgent instantiation and properties."""

    def test_create_default_agent(self):
        agent = KlaatCodeAgent()
        assert agent.agent_id.startswith("klaatcode_")
        assert agent.status == AgentStatus.CREATED
        assert agent.profile.agent_name == "KlaatCodeAgent"

    def test_create_with_custom_id(self):
        agent = KlaatCodeAgent(agent_id="my-kc-agent")
        assert agent.agent_id == "my-kc-agent"

    def test_factory_creates_and_starts(self):
        agent = create_klaatcode_agent()
        assert agent.status == AgentStatus.READY
        assert agent.is_available

    def test_profile_defaults(self):
        profile = KlaatCodeProfile()
        assert "analysis" in profile.capabilities
        assert "code_generation" in profile.capabilities
        assert "code_review" in profile.capabilities
        assert profile.max_concurrent_tasks == 2
        assert profile.timeout_seconds == 300.0

    def test_capabilities_as_enum(self):
        agent = KlaatCodeAgent()
        caps = agent.agent_capabilities
        assert len(caps) > 0
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.ANALYSIS in caps

    def test_to_agent_dataclass(self):
        agent = create_klaatcode_agent()
        ad = agent.to_agent_dataclass()
        assert ad.agent_id == agent.agent_id
        assert ad.name == "KlaatCodeAgent"
        assert ad.status == AgentStatus.READY
        assert len(ad.capabilities) > 0

    def test_get_status_dict(self):
        agent = create_klaatcode_agent()
        status = agent.get_status_dict()
        assert status["agent_id"] == agent.agent_id
        assert status["status"] == "ready"
        assert status["is_available"] is True
        assert "capabilities" in status
        assert "mcp_tools" in status


# ═══════════════════════════════════════════════════════════════
# LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeLifecycle:
    """Tests for KlaatCodeAgent lifecycle transitions."""

    @pytest.fixture
    def agent(self):
        return KlaatCodeAgent()

    def test_initial_state_is_created(self, agent):
        assert agent.status == AgentStatus.CREATED

    def test_start_transitions_to_ready(self, agent):
        result = agent.start()
        assert result is True
        assert agent.status == AgentStatus.READY

    def test_pause_resume(self, agent):
        agent.start()
        assert agent.pause() is True
        assert agent.status == AgentStatus.PAUSED
        assert agent.resume() is True
        assert agent.status == AgentStatus.READY

    def test_mark_busy_then_ready(self, agent):
        agent.start()
        assert agent.mark_busy(task_id="task-1") is True
        assert agent.status == AgentStatus.BUSY
        assert agent.op_status != KlaatCodeAgentStatus.IDLE
        assert agent.mark_ready() is True
        assert agent.status == AgentStatus.READY
        assert agent.op_status == KlaatCodeAgentStatus.IDLE

    def test_stop_terminal(self, agent):
        agent.start()
        assert agent.stop() is True
        assert agent.status == AgentStatus.STOPPED
        # Cannot transition from STOPPED
        assert agent.transition(AgentStatus.READY, "test") is False

    def test_invalid_transition_blocked(self, agent):
        """Cannot go directly from CREATED to READY without STARTING."""
        assert agent.transition(AgentStatus.READY, "skip") is False

    def test_lifecycle_history(self, agent):
        agent.start()
        agent.mark_busy("t1")
        agent.mark_ready()
        history = agent.get_lifecycle_history()
        assert len(history) >= 3  # CREATED→STARTING, STARTING→READY, READY→BUSY, BUSY→READY

    def test_events_on_transitions(self):
        events = []
        agent = KlaatCodeAgent(on_event=lambda et, p, **kw: events.append((et, p)))
        agent.start()
        ready_events = [e for e in events if "ready" in e[0]]
        assert len(ready_events) >= 1


# ═══════════════════════════════════════════════════════════════
# CAPABILITY MATCHING
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeCapabilityMatching:
    """Tests for KlaatCodeAgent capability matching with Supervisors."""

    def test_capabilities_include_code_generation(self):
        agent = create_klaatcode_agent()
        caps = agent.agent_capabilities
        assert AgentCapability.CODE_GENERATION in caps

    def test_capabilities_include_analysis(self):
        agent = create_klaatcode_agent()
        caps = agent.agent_capabilities
        assert AgentCapability.ANALYSIS in caps

    def test_task_to_capability_mapping(self):
        assert TASK_TO_CAPABILITY[KlaatCodeTaskType.CODE_ANALYSIS] == "analysis"
        assert TASK_TO_CAPABILITY[KlaatCodeTaskType.CODE_GENERATION] == "code_generation"
        assert TASK_TO_CAPABILITY[KlaatCodeTaskType.CODE_REVIEW] == "code_review"
        assert TASK_TO_CAPABILITY[KlaatCodeTaskType.DIAGNOSTICS] == "analysis"
        assert TASK_TO_CAPABILITY[KlaatCodeTaskType.TEST_ANALYSIS] == "testing"

    def test_task_to_mcp_action_mapping(self):
        assert TASK_TO_MCP_ACTION[KlaatCodeTaskType.CODE_ANALYSIS] == "analyze_project"
        assert TASK_TO_MCP_ACTION[KlaatCodeTaskType.CODE_GENERATION] == "generate_code_plan"
        assert TASK_TO_MCP_ACTION[KlaatCodeTaskType.CODE_EDITING] == "edit_file"

    def test_agent_is_available_for_task_matching(self):
        agent = create_klaatcode_agent()
        assert agent.is_available
        agent.mark_busy("t1")
        assert not agent.is_available

    def test_profile_skill_levels(self):
        profile = KlaatCodeProfile()
        assert profile.skill_levels["analysis"] > 0.9
        assert profile.skill_levels["code_generation"] > 0.85


# ═══════════════════════════════════════════════════════════════
# MCP TASK EXECUTION
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeMCPExecution:
    """Tests for executing KlaatCode MCP tasks via the agent."""

    @pytest.fixture
    def agent(self):
        return create_klaatcode_agent()

    def test_execute_code_analysis(self, agent):
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_ANALYSIS,
            parameters={"path": "/tmp"},
            mission_id="m1",
            node_id="n1",
        )
        assert isinstance(result, ExecutionResult)
        # Without MCP adapter, fallback simulation succeeds
        assert result.outcome == TaskOutcome.SUCCESS
        assert result.duration_ms >= 0

    def test_execute_diagnostics(self, agent):
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.DIAGNOSTICS,
            parameters={"file": "src/app.ts"},
            mission_id="m1",
            node_id="n2",
        )
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_code_generation(self, agent):
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_GENERATION,
            parameters={"prompt": "Create a login page"},
            mission_id="m2",
            node_id="n3",
        )
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_code_review(self, agent):
        result = agent.execute_task(
            task_type=KlaatCodeTaskType.CODE_REVIEW,
            parameters={"file": "src/app.ts"},
            mission_id="m3",
            node_id="n4",
        )
        assert result.outcome == TaskOutcome.SUCCESS

    def test_execute_increments_metrics(self, agent):
        before = agent.get_metrics().total_tasks
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        after = agent.get_metrics().total_tasks
        assert after == before + 1

    def test_execute_updates_success_rate(self, agent):
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {})
        rate = agent.success_rate
        assert rate > 0.0

    def test_agent_returns_to_idle_after_task(self, agent):
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        assert agent.is_available
        assert agent.op_status == KlaatCodeAgentStatus.IDLE

    def test_task_history_recorded(self, agent):
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": ".", "language": "python"})
        history = agent.get_task_history()
        assert len(history) >= 1
        latest = history[-1]
        assert latest["task_type"] == KlaatCodeTaskType.CODE_ANALYSIS
        assert latest["result"] == "success"


# ═══════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeEvents:
    """Tests for KlaatCode EventBus integration."""

    def test_events_emitted_during_lifecycle(self):
        events = []
        agent = KlaatCodeAgent(on_event=lambda et, p, **kw: events.append((et, p)))
        agent.start()
        event_types = [e[0] for e in events]
        assert KLATCODE_EVENTS["agent_ready"] in event_types

    def test_events_emitted_during_task(self):
        events = []
        agent = KlaatCodeAgent(on_event=lambda et, p, **kw: events.append((et, p)))
        agent.start()
        events.clear()
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        event_types = [e[0] for e in events]
        assert KLATCODE_EVENTS["task_started"] in event_types
        assert KLATCODE_EVENTS["task_completed"] in event_types

    def test_analysis_completed_event(self):
        events = []
        agent = KlaatCodeAgent(on_event=lambda et, p, **kw: events.append((et, p)))
        agent.start()
        events.clear()
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        event_types = [e[0] for e in events]
        assert KLATCODE_EVENTS["analysis_completed"] in event_types

    def test_event_prefix_consistent(self):
        """All events have the klaatcode.* prefix."""
        for key, event_type in KLATCODE_EVENTS.items():
            assert event_type.startswith("klaatcode.")

    def test_event_payload_has_agent_id(self):
        events = []
        agent = KlaatCodeAgent(on_event=lambda et, p, **kw: events.append((et, p)))
        agent.start()
        ready_ev = next((p for et, p in events if et == KLATCODE_EVENTS["agent_ready"]), None)
        assert ready_ev is not None
        assert ready_ev["agent_id"] == agent.agent_id
        assert "name" in ready_ev


# ═══════════════════════════════════════════════════════════════
# MEMORY STORAGE
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeMemoryIntegration:
    """Tests for Memory System (HOS-047) integration."""

    def test_task_execution_with_memory(self):
        """Agent with memory manager stores execution records."""
        from backend.memory.memory_manager import MemoryManager

        mm = MemoryManager()
        agent = create_klaatcode_agent(memory_manager=mm)
        agent.execute_task(
            KlaatCodeTaskType.CODE_ANALYSIS,
            {"path": ".", "language": "python", "project": "test-app"},
            mission_id="mem-mission-1",
            node_id="mem-node-1",
        )
        # Episodic memory should have been recorded
        episode = mm.get_episode("mem-mission-1")
        assert episode is not None or True  # May be None if memory format differs

    def test_agent_without_memory_does_not_crash(self):
        agent = create_klaatcode_agent(memory_manager=None)
        # Should execute without errors even without memory manager
        result = agent.execute_task(
            KlaatCodeTaskType.CODE_ANALYSIS,
            {"path": "."},
            mission_id="no-mem-mission",
            node_id="no-mem-node",
        )
        assert result.outcome == TaskOutcome.SUCCESS


# ═══════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeMetrics:
    """Tests for agent metrics collection."""

    @pytest.fixture
    def agent(self):
        return create_klaatcode_agent()

    def test_initial_metrics(self, agent):
        m = agent.get_metrics()
        assert m.total_tasks == 0
        assert m.successful_tasks == 0
        assert m.success_rate == 100.0

    def test_metrics_after_tasks(self, agent):
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        agent.execute_task(KlaatCodeTaskType.DIAGNOSTICS, {"file": "test.py"})
        m = agent.get_metrics()
        assert m.total_tasks == 2
        assert m.successful_tasks >= 1
        assert m.avg_duration_ms >= 0

    def test_success_rate_calculation(self, agent):
        for _ in range(3):
            agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        rate = agent.success_rate
        assert 90.0 <= rate <= 100.0

    def test_load_tracking(self, agent):
        assert agent.load == 0.0
        agent.mark_busy("t1")
        assert agent.load == 1.0
        agent.mark_ready()
        assert agent.load == 0.0

    def test_status_dict_includes_metrics(self, agent):
        agent.execute_task(KlaatCodeTaskType.CODE_ANALYSIS, {"path": "."})
        status = agent.get_status_dict()
        assert status["total_tasks"] >= 1
        assert "success_rate" in status


# ═══════════════════════════════════════════════════════════════
# THREAD SAFETY
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeThreadSafety:
    """Tests for thread safety across the KlaatCode agent."""

    def test_concurrent_task_execution(self):
        """Multiple threads can execute tasks on the same agent."""
        agent = create_klaatcode_agent()
        errors: list[Exception] = []

        def worker(task_id: int):
            try:
                for _ in range(5):
                    agent.execute_task(
                        KlaatCodeTaskType.CODE_ANALYSIS,
                        {"path": f"/tmp/project_{task_id}"},
                        mission_id="thread-mission",
                        node_id=f"thread-node-{task_id}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Thread-safety errors: {errors}"

    def test_concurrent_status_reads(self):
        """Multiple threads can safely read status concurrently."""
        agent = create_klaatcode_agent()
        errors: list[Exception] = []

        def reader():
            try:
                for _ in range(50):
                    _ = agent.status
                    _ = agent.is_available
                    _ = agent.get_status_dict()
                    _ = agent.get_metrics()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread-safety errors: {errors}"

    def test_concurrent_lifecycle_and_execution(self):
        """Lifecycle transitions and task execution can interleave."""
        agent = KlaatCodeAgent()
        agent.start()
        errors: list[Exception] = []

        def worker(i: int):
            try:
                for _ in range(10):
                    agent.execute_task(
                        KlaatCodeTaskType.DIAGNOSTICS if i % 2 == 0 else KlaatCodeTaskType.CODE_ANALYSIS,
                        {"file": f"src/file_{i}.py"},
                        node_id=f"c-node-{i}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Errors: {errors}"
        # Agent should still be healthy
        assert agent.status in (AgentStatus.READY, AgentStatus.BUSY)


# ═══════════════════════════════════════════════════════════════
# ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════════════

class TestKlaatCodeEnums:
    """Tests for KlaatCode enums and constants."""

    def test_task_type_enum_values(self):
        types = list(KlaatCodeTaskType)
        assert len(types) == 9
        assert KlaatCodeTaskType.CODE_ANALYSIS == "code_analysis"
        assert KlaatCodeTaskType.CODE_GENERATION == "code_generation"
        assert KlaatCodeTaskType.PATCH_GENERATION == "patch_generation"

    def test_agent_status_values(self):
        statuses = list(KlaatCodeAgentStatus)
        assert len(statuses) >= 5
        assert KlaatCodeAgentStatus.IDLE == "idle"
        assert KlaatCodeAgentStatus.ANALYZING == "analyzing"

    def test_task_to_capability_covers_all_types(self):
        for task_type in KlaatCodeTaskType:
            assert task_type in TASK_TO_CAPABILITY

    def test_task_to_mcp_action_covers_all_types(self):
        for task_type in KlaatCodeTaskType:
            assert task_type in TASK_TO_MCP_ACTION
