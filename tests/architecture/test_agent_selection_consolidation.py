"""Tests for HOS-070 Phase B — AgentCoordinator delegates to the real
CapabilityMatcher when one is wired, instead of running two disconnected
agent-selection engines (this coordinator's own keyword-overlap scoring,
and CapabilityMatcher's real multi-criteria scoring — capability, load,
availability, success rate, runtime preference — HOS-043, previously
unreachable from any real execution).

Fully hermetic: uses the real AgentRegistry/CapabilityMatcher/AgentModels
classes against an in-memory registry, no real Ollama needed.
"""
from __future__ import annotations

from backend.agents.agent_models import Agent, AgentCapability, AgentStatus
from backend.agents.agent_registry import AgentRegistry
from backend.agents.capability_matcher import CapabilityMatcher
from backend.execution.agent_coordinator import AgentCoordinator
from backend.execution.execution_models import TaskExecution


def _matcher_with(*agents: Agent) -> tuple[AgentRegistry, CapabilityMatcher]:
    registry = AgentRegistry()
    for a in agents:
        registry.register(a)
    return registry, CapabilityMatcher(registry)


class TestDelegatesToRealMatcherWhenWired:
    def test_selects_the_agent_with_the_matching_capability(self):
        registry, matcher = _matcher_with(
            Agent(name="chatty", capabilities=[AgentCapability.CHAT], status=AgentStatus.READY),
            Agent(name="coder", capabilities=[AgentCapability.CODE_GENERATION], status=AgentStatus.READY),
        )
        coordinator = AgentCoordinator(capability_matcher=matcher)
        task = TaskExecution(task_id="t1", title="write a function", task_type="implementation")

        assignment = coordinator.assign(task)

        assert assignment.agent_id == "coder"

    def test_a_busy_agent_is_not_selected(self):
        """Real load-awareness: CapabilityMatcher filters to READY agents,
        so a genuinely busy agent (synced by MissionExecutor — HOS-070
        Phase A) is skipped in favor of an idle one with the same
        capability, unlike the old keyword scoring which only penalized
        load in the score rather than excluding a busy agent outright."""
        busy = Agent(name="busy-coder", capabilities=[AgentCapability.CODE_GENERATION],
                     status=AgentStatus.BUSY)
        idle = Agent(name="idle-coder", capabilities=[AgentCapability.CODE_GENERATION],
                     status=AgentStatus.READY)
        registry, matcher = _matcher_with(busy, idle)
        coordinator = AgentCoordinator(capability_matcher=matcher)
        task = TaskExecution(task_id="t1", title="write a function", task_type="implementation")

        assignment = coordinator.assign(task)

        assert assignment.agent_id == "idle-coder"

    def test_no_matching_capability_falls_back_to_any_ready_agent(self):
        registry, matcher = _matcher_with(
            Agent(name="generalist", capabilities=[AgentCapability.CHAT], status=AgentStatus.READY),
        )
        coordinator = AgentCoordinator(capability_matcher=matcher)
        task = TaskExecution(task_id="t1", title="deploy the service", task_type="deployment")

        assignment = coordinator.assign(task)

        assert assignment.agent_id == "generalist"

    def test_no_agents_at_all_falls_back_to_keyword_scoring(self):
        """An empty real registry (matcher finds nothing) must not crash —
        falls through to the coordinator's own keyword fallback, which
        also finds nothing and returns "default", exactly as it did before
        a matcher ever existed."""
        registry, matcher = _matcher_with()  # empty
        coordinator = AgentCoordinator(capability_matcher=matcher)
        task = TaskExecution(task_id="t1", title="anything", task_type="analysis")

        assignment = coordinator.assign(task)

        assert assignment.agent_id == "default"


class TestFallbackWithoutMatcher:
    def test_bare_coordinator_keeps_keyword_based_selection(self):
        """Existing behaviour, unchanged, for callers that never wire a
        matcher (the standalone /execution/start path; every pre-HOS-070
        test)."""
        coordinator = AgentCoordinator()  # no capability_matcher
        coordinator.register_agent(agent_id="coder", capabilities=["code_generation"])
        task = TaskExecution(task_id="t1", title="code_generation task")

        assignment = coordinator.assign(task)

        assert assignment.agent_id == "coder"
