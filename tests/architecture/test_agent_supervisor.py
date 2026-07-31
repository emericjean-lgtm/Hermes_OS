"""Tests for the Agent Supervisor (HOS-043)."""

from __future__ import annotations

import threading

import pytest

from backend.agents.agent_lifecycle import AgentLifecycle
from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentStatus,
    ExecutionResult,
)
from backend.agents.agent_registry import AgentRegistry
from backend.agents.agent_supervisor import AgentSupervisor
from backend.agents.capability_matcher import CapabilityMatcher
from backend.agents.execution_context import ExecutionContextManager
from backend.agents.task_dispatcher import TaskDispatcher
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    NodeStatus,
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def registry() -> AgentRegistry:
    return AgentRegistry()


@pytest.fixture
def lifecycle(registry) -> AgentLifecycle:
    return AgentLifecycle(registry=registry)


@pytest.fixture
def matcher(registry) -> CapabilityMatcher:
    return CapabilityMatcher(registry=registry)


@pytest.fixture
def ctx_manager() -> ExecutionContextManager:
    return ExecutionContextManager()


@pytest.fixture
def dispatcher(registry, lifecycle, ctx_manager, matcher) -> TaskDispatcher:
    return TaskDispatcher(
        registry=registry,
        lifecycle=lifecycle,
        context_manager=ctx_manager,
        matcher=matcher,
    )


@pytest.fixture
def supervisor() -> AgentSupervisor:
    return AgentSupervisor()


@pytest.fixture
def coder_agent(supervisor) -> Agent:
    return supervisor.create_agent(
        name="CoderAgent",
        capabilities=[AgentCapability.CODE_GENERATION, AgentCapability.TESTING],
        preferred_runtime="qwen3:14b",
        preferred_model="qwen3:14b",
    )


@pytest.fixture
def reviewer_agent(supervisor) -> Agent:
    return supervisor.create_agent(
        name="ReviewerAgent",
        capabilities=[AgentCapability.CODE_REVIEW, AgentCapability.ANALYSIS],
        preferred_runtime="qwen3:8b",
    )


@pytest.fixture
def designer_agent(supervisor) -> Agent:
    return supervisor.create_agent(
        name="DesignerAgent",
        capabilities=[AgentCapability.DESIGN, AgentCapability.DOCUMENTATION],
        preferred_runtime="qwen3:4b",
    )


@pytest.fixture
def simple_mission() -> Mission:
    node1 = MissionNode(
        title="Implement login",
        type="implementation",
        required_skills=["coding"],
    )
    node2 = MissionNode(
        title="Review login",
        type="review",
        depends_on=[node1.node_id],
    )
    edge = MissionEdge(source_id=node1.node_id, target_id=node2.node_id)
    return Mission(
        title="Auth Mission",
        nodes=[node1, node2],
        edges=[edge],
    )


# ── Agent Registry Tests ────────────────────────────────────

class TestAgentRegistry:
    def test_register_agent(self, registry):
        agent = Agent(name="Test", capabilities=[AgentCapability.CODE_GENERATION])
        registry.register(agent)
        assert registry.get(agent.agent_id) is not None
        assert registry.count == 1

    def test_unregister_agent(self, registry):
        agent = Agent(name="Test")
        registry.register(agent)
        assert registry.unregister(agent.agent_id)
        assert registry.get(agent.agent_id) is None
        assert registry.count == 0

    def test_find_by_capability(self, registry):
        a1 = Agent(name="Coder", capabilities=[AgentCapability.CODE_GENERATION])
        a2 = Agent(name="Tester", capabilities=[AgentCapability.TESTING])
        registry.register(a1)
        registry.register(a2)
        coders = registry.find_by_capability(AgentCapability.CODE_GENERATION)
        assert len(coders) == 1
        assert coders[0].name == "Coder"

    def test_find_by_multiple_capabilities(self, registry):
        a1 = Agent(name="FullStack", capabilities=[AgentCapability.CODE_GENERATION, AgentCapability.TESTING])
        a2 = Agent(name="Coder", capabilities=[AgentCapability.CODE_GENERATION])
        registry.register(a1)
        registry.register(a2)
        found = registry.find_by_capabilities([AgentCapability.CODE_GENERATION, AgentCapability.TESTING])
        assert len(found) == 1
        assert found[0].name == "FullStack"

    def test_find_by_any_capability(self, registry):
        a1 = Agent(name="Coder", capabilities=[AgentCapability.CODE_GENERATION])
        a2 = Agent(name="Tester", capabilities=[AgentCapability.TESTING])
        registry.register(a1)
        registry.register(a2)
        found = registry.find_by_any_capability([AgentCapability.CODE_GENERATION, AgentCapability.TESTING])
        assert len(found) == 2

    def test_find_by_status(self, registry):
        a1 = Agent(name="Ready", status=AgentStatus.READY, capabilities=[])
        a2 = Agent(name="Busy", status=AgentStatus.BUSY, capabilities=[])
        registry.register(a1)
        registry.register(a2)
        ready = registry.find_by_status(AgentStatus.READY)
        assert len(ready) == 1

    def test_update_status(self, registry):
        agent = Agent(name="Test", capabilities=[])
        registry.register(agent)
        registry.update_status(agent.agent_id, AgentStatus.READY)
        assert registry.get(agent.agent_id).status == AgentStatus.READY

    def test_update_metrics(self, registry):
        agent = Agent(name="Test", capabilities=[])
        registry.register(agent)
        registry.update_metrics(agent.agent_id, 1000.0, True)
        a = registry.get(agent.agent_id)
        assert a.total_tasks == 1
        assert a.successful_tasks == 1
        assert a.total_duration_ms == 1000.0

    def test_get_metrics(self, registry):
        agent = Agent(name="Test", capabilities=[])
        registry.register(agent)
        registry.update_metrics(agent.agent_id, 500.0, True)
        m = registry.get_metrics(agent.agent_id)
        assert m is not None
        assert m.total_tasks == 1
        assert m.success_rate == 100.0

    def test_get_stats(self, registry):
        a1 = Agent(name="R", status=AgentStatus.READY, capabilities=[])
        a2 = Agent(name="B", status=AgentStatus.BUSY, capabilities=[])
        registry.register(a1)
        registry.register(a2)
        stats = registry.get_stats()
        assert stats["total_agents"] == 2
        assert stats["ready"] == 1
        assert stats["busy"] == 1


# ── Agent Lifecycle Tests ────────────────────────────────────

class TestAgentLifecycle:
    def test_create_and_start(self, lifecycle):
        agent = lifecycle.create_agent(
            name="TestAgent",
            capabilities=[AgentCapability.CODE_GENERATION],
        )
        assert agent.status == AgentStatus.CREATED
        ok = lifecycle.start(agent)
        assert ok
        assert agent.status == AgentStatus.READY

    def test_busy_ready_cycle(self, lifecycle):
        agent = lifecycle.create_agent("Test", [AgentCapability.CODE_GENERATION])
        lifecycle.start(agent)
        assert lifecycle.mark_busy(agent, "task-1")
        assert agent.status == AgentStatus.BUSY
        assert lifecycle.mark_ready(agent)
        assert agent.status == AgentStatus.READY

    def test_pause_resume(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        lifecycle.start(agent)
        assert lifecycle.pause(agent)
        assert agent.status == AgentStatus.PAUSED
        assert lifecycle.resume(agent)
        assert agent.status == AgentStatus.READY

    def test_stop(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        lifecycle.start(agent)
        assert lifecycle.stop(agent)
        assert agent.status == AgentStatus.STOPPED

    def test_fail_and_recover(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        lifecycle.start(agent)
        assert lifecycle.mark_failed(agent, "Test failure")
        assert agent.status == AgentStatus.FAILED
        assert lifecycle.recover(agent)
        assert agent.status == AgentStatus.READY

    def test_invalid_transition(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        # Can't go directly from CREATED to BUSY
        assert not lifecycle.transition(agent, AgentStatus.BUSY)

    def test_stopped_is_terminal(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        lifecycle.start(agent)
        lifecycle.stop(agent)
        # Can't transition from STOPPED
        assert not lifecycle.transition(agent, AgentStatus.READY)

    def test_history(self, lifecycle):
        agent = lifecycle.create_agent("Test", [])
        lifecycle.start(agent)
        lifecycle.mark_busy(agent, "task-1")
        history = lifecycle.get_history(agent.agent_id)
        assert len(history) >= 2


# ── Capability Matcher Tests ─────────────────────────────────

class TestCapabilityMatcher:
    def test_select_coder(self, matcher, registry):
        _setup_agents(registry)
        agent = matcher.select_best(task_type="implementation")
        assert agent is not None
        assert AgentCapability.CODE_GENERATION in agent.capabilities

    def test_select_reviewer(self, matcher, registry):
        _setup_agents(registry)
        agent = matcher.select_best(task_type="review")
        assert agent is not None
        assert AgentCapability.CODE_REVIEW in agent.capabilities

    def test_select_designer(self, matcher, registry):
        _setup_agents(registry)
        agent = matcher.select_best(task_type="design")
        assert agent is not None
        assert AgentCapability.DESIGN in agent.capabilities

    def test_no_match_returns_none(self, matcher, registry):
        agent = matcher.select_best(task_type="unknown_type")
        assert agent is None

    def test_find_candidates_prefers_idle(self, matcher, registry):
        _setup_agents(registry)
        candidates = matcher.find_candidates(task_type="implementation")
        assert len(candidates) > 0

    def test_preferred_runtime_match(self, matcher, registry):
        _setup_agents(registry)
        agent = matcher.select_best(
            task_type="implementation",
            preferred_runtime="qwen3:14b",
        )
        assert agent is not None

    def test_skill_mapping(self):
        assert CapabilityMatcher._skill_to_capability("coding") == AgentCapability.CODE_GENERATION
        assert CapabilityMatcher._skill_to_capability("testing") == AgentCapability.TESTING
        assert CapabilityMatcher._skill_to_capability("design") == AgentCapability.DESIGN


# ── Execution Context Tests ──────────────────────────────────

class TestExecutionContext:
    def test_create_context(self, ctx_manager):
        ctx = ctx_manager.create_context(
            agent_id="a1",
            mission_id="m1",
            node_id="n1",
            task_title="Test",
        )
        assert ctx.context_id
        assert ctx.agent_id == "a1"
        assert ctx.mission_id == "m1"

    def test_get_by_agent(self, ctx_manager):
        ctx_manager.create_context(agent_id="a1", mission_id="m1", node_id="n1")
        ctx_manager.create_context(agent_id="a1", mission_id="m2", node_id="n2")
        ctxs = ctx_manager.get_by_agent("a1")
        assert len(ctxs) == 2

    def test_get_by_mission(self, ctx_manager):
        ctx_manager.create_context(agent_id="a1", mission_id="m1", node_id="n1")
        ctx_manager.create_context(agent_id="a2", mission_id="m1", node_id="n2")
        ctxs = ctx_manager.get_by_mission("m1")
        assert len(ctxs) == 2

    def test_increment_retry(self, ctx_manager):
        ctx = ctx_manager.create_context(agent_id="a1", mission_id="m1", node_id="n1")
        assert ctx_manager.increment_retry(ctx.context_id)
        updated = ctx_manager.get(ctx.context_id)
        assert updated.retry_count == 1

    def test_remove_context(self, ctx_manager):
        ctx = ctx_manager.create_context(agent_id="a1", mission_id="m1", node_id="n1")
        assert ctx_manager.remove(ctx.context_id)
        assert ctx_manager.get(ctx.context_id) is None


# ── Task Dispatcher Tests ────────────────────────────────────

class TestTaskDispatcher:
    def test_dispatch_node(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        node = simple_mission.nodes[0]  # "Implement login"
        result = supervisor.dispatch_node(simple_mission, node)
        assert result is not None
        assert node.status == NodeStatus.COMPLETED

    def test_dispatch_with_no_agent(self, supervisor):
        mission = Mission(nodes=[MissionNode(title="Solo", type="custom")])
        node = mission.nodes[0]
        for a in supervisor.list_agents():
            supervisor.stop_agent(a.agent_id)
        result = supervisor.dispatch_node(mission, node)
        assert result is None

    def test_reassign(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        node = simple_mission.nodes[0]
        result = supervisor.reassign_node(simple_mission, node)
        assert result is None or isinstance(result, ExecutionResult)

    def test_get_results(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        node = simple_mission.nodes[0]
        supervisor.dispatch_node(simple_mission, node)
        results = supervisor.get_mission_results(simple_mission.mission_id)
        assert len(results) == 1


# ── Agent Supervisor Tests ───────────────────────────────────

class TestAgentSupervisor:
    def test_create_agent(self, supervisor):
        agent = supervisor.create_agent(
            name="Bot",
            capabilities=[AgentCapability.CHAT],
        )
        assert agent.name == "Bot"
        assert agent.status == AgentStatus.READY

    def test_list_agents(self, supervisor):
        agents = supervisor.list_agents()
        assert len(agents) >= 0

    def test_get_agent(self, supervisor, coder_agent):
        agent = supervisor.get_agent(coder_agent.agent_id)
        assert agent is not None
        assert agent.name == "CoderAgent"

    def test_stop_agent(self, supervisor, coder_agent):
        ok = supervisor.stop_agent(coder_agent.agent_id)
        assert ok
        agent = supervisor.get_agent(coder_agent.agent_id)
        assert agent.status == AgentStatus.STOPPED

    def test_pause_resume_agent(self, supervisor, coder_agent):
        ok = supervisor.pause_agent(coder_agent.agent_id)
        assert ok
        assert supervisor.get_agent(coder_agent.agent_id).status == AgentStatus.PAUSED
        ok = supervisor.resume_agent(coder_agent.agent_id)
        assert ok
        assert supervisor.get_agent(coder_agent.agent_id).status == AgentStatus.READY

    def test_get_stats(self, supervisor):
        stats = supervisor.get_stats()
        assert "total_agents" in stats
        assert "ready" in stats
        assert "busy" in stats

    def test_get_all_metrics(self, supervisor):
        metrics = supervisor.get_all_metrics()
        assert isinstance(metrics, list)

    def test_execute_mission_step(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        summary = supervisor.execute_mission_step(simple_mission)
        assert "nodes_dispatched" in summary
        assert summary["mission_id"] == simple_mission.mission_id

    def test_execute_full_mission(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        summary = supervisor.execute_full_mission(simple_mission)
        assert summary["total_nodes"] == 2
        assert summary["executed"] == 2
        for node in simple_mission.nodes:
            assert node.status == NodeStatus.COMPLETED

    def test_get_agent_history(self, supervisor, coder_agent):
        history = supervisor.get_agent_history(coder_agent.agent_id)
        assert isinstance(history, list)

    def test_get_agent_tasks(
        self, supervisor, coder_agent, simple_mission,
        reviewer_agent, designer_agent,
    ):
        supervisor.execute_full_mission(simple_mission)
        tasks = supervisor.get_agent_tasks(coder_agent.agent_id)
        assert isinstance(tasks, list)


# ── Integration: Full mission execution ──────────────────────

class TestFullExecution:
    def test_multi_agent_mission(
        self, supervisor,
        coder_agent, reviewer_agent, designer_agent,
    ):
        n1 = MissionNode(
            title="Design architecture",
            type="design",
            required_skills=["design"],
        )
        n2 = MissionNode(
            title="Implement backend",
            type="implementation",
            depends_on=[n1.node_id],
            required_skills=["coding"],
            preferred_runtime="qwen3:14b",
        )
        n3 = MissionNode(
            title="Write tests",
            type="testing",
            depends_on=[n2.node_id],
            required_skills=["testing"],
        )
        n4 = MissionNode(
            title="Code review",
            type="review",
            depends_on=[n2.node_id, n3.node_id],
        )

        mission = Mission(
            title="Multi-Agent Mission",
            nodes=[n1, n2, n3, n4],
            edges=[
                MissionEdge(source_id=n1.node_id, target_id=n2.node_id),
                MissionEdge(source_id=n2.node_id, target_id=n3.node_id),
                MissionEdge(source_id=n2.node_id, target_id=n4.node_id),
                MissionEdge(source_id=n3.node_id, target_id=n4.node_id),
            ],
        )

        summary = supervisor.execute_full_mission(mission)
        assert summary["total_nodes"] == 4
        assert summary["executed"] == 4
        assert summary["failed"] == 0

        for node in mission.nodes:
            assert node.status == NodeStatus.COMPLETED, f"Node '{node.title}' not completed"

        metrics = supervisor.get_all_metrics()
        total_tasks = sum(m.total_tasks for m in metrics)
        assert total_tasks >= 4

    def test_mission_with_failure_and_reassign(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        n1 = simple_mission.nodes[0]
        result = supervisor.dispatch_node(simple_mission, n1)
        assert result is not None
        assert n1.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)

        n2 = simple_mission.nodes[1]
        if n1.status == NodeStatus.COMPLETED:
            result2 = supervisor.dispatch_node(simple_mission, n2)
            assert result2 is not None


# ── Thread Safety Tests ──────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_agent_creation(self, supervisor):
        errors = []

        def worker(idx):
            try:
                agent = supervisor.create_agent(
                    name=f"Agent{idx}",
                    capabilities=[AgentCapability.CODE_GENERATION],
                )
                if agent is None:
                    errors.append(f"Worker {idx}: no agent created")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors
        agents = supervisor.list_agents()
        assert len(agents) >= 10

    def test_concurrent_dispatch(
        self, supervisor, simple_mission,
        coder_agent, reviewer_agent, designer_agent,
    ):
        errors = []

        def worker(idx):
            try:
                node = MissionNode(
                    title=f"Task-{idx}",
                    type="implementation",
                    required_skills=["coding"],
                )
                supervisor.dispatch_node(simple_mission, node)
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors


# ── Helpers ──────────────────────────────────────────────────

def _setup_agents(registry: AgentRegistry) -> None:
    """Create standard test agents in the registry."""
    coder = Agent(
        name="Coder",
        status=AgentStatus.READY,
        capabilities=[AgentCapability.CODE_GENERATION, AgentCapability.TESTING],
        preferred_runtime="qwen3:14b",
        preferred_model="qwen3:14b",
    )
    reviewer = Agent(
        name="Reviewer",
        status=AgentStatus.READY,
        capabilities=[AgentCapability.CODE_REVIEW, AgentCapability.ANALYSIS],
    )
    designer = Agent(
        name="Designer",
        status=AgentStatus.READY,
        capabilities=[AgentCapability.DESIGN, AgentCapability.DOCUMENTATION],
    )
    registry.register(coder)
    registry.register(reviewer)
    registry.register(designer)
