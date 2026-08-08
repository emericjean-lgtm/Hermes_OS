"""Tests for HOS-070 — GET /api/v1/agents (list) carries the same real
fields as GET /api/v1/agents/{id} (detail).

Found via manual browser verification: the list endpoint omitted
successful_tasks/failed_tasks (only the detail endpoint had them), so a
dispatched agent's own list row showed "0 ok, 0 failed" even at a real
100% success rate — the Cockpit reads the list row it already has rather
than re-fetching detail per selection. Also verifies the real trust score
(HOS-070 Phase C) reaches both endpoints.

Fully hermetic: real AgentSupervisor/AgentTrustEngine, no HTTP server or
Ollama needed — calls the route handler coroutines directly.
"""
from __future__ import annotations

import asyncio

from backend.agents.agent_models import AgentCapability
from backend.agents.agent_supervisor import AgentSupervisor
from backend.security.agent_trust_engine import AgentTrustEngine


def _setup():
    import backend.agents.routes as agent_routes

    supervisor = AgentSupervisor()
    trust = AgentTrustEngine()
    agent_routes.create_agent_routes(supervisor)
    agent_routes.set_trust_engine(trust)
    agent = supervisor.create_agent(name="tester", capabilities=[AgentCapability.CHAT])
    return agent_routes, supervisor, trust, agent


class TestListAgentsCarriesRealFields:
    def test_list_includes_task_and_trust_fields(self):
        agent_routes, supervisor, trust, agent = _setup()
        supervisor.registry.update_metrics(agent.agent_id, 42.0, True)
        trust.record_result("tester", True)

        result = asyncio.run(agent_routes.list_agents())

        row = next(a for a in result["agents"] if a["name"] == "tester")
        assert row["total_tasks"] == 1
        assert row["successful_tasks"] == 1
        assert row["failed_tasks"] == 0
        assert row["trust_score"] == trust.get_score("tester").score
        assert row["trust_level"] == trust.get_score("tester").level.value

    def test_list_and_detail_agree_on_task_counts(self):
        """The exact bug found in the browser: list and detail must not
        disagree about the same agent's own counts."""
        agent_routes, supervisor, trust, agent = _setup()
        supervisor.registry.update_metrics(agent.agent_id, 10.0, True)
        supervisor.registry.update_metrics(agent.agent_id, 10.0, False)

        listed = asyncio.run(agent_routes.list_agents())
        detail = asyncio.run(agent_routes.get_agent(agent.agent_id))

        row = next(a for a in listed["agents"] if a["name"] == "tester")
        assert row["successful_tasks"] == detail["successful_tasks"] == 1
        assert row["failed_tasks"] == detail["failed_tasks"] == 1
        assert row["total_tasks"] == detail["total_tasks"] == 2

    def test_no_trust_engine_reports_none_not_a_fabricated_score(self):
        import backend.agents.routes as agent_routes

        supervisor = AgentSupervisor()
        agent_routes.create_agent_routes(supervisor)
        agent_routes.set_trust_engine(None)
        supervisor.create_agent(name="untrusted", capabilities=[AgentCapability.CHAT])

        result = asyncio.run(agent_routes.list_agents())

        row = next(a for a in result["agents"] if a["name"] == "untrusted")
        assert row["trust_score"] is None
        assert row["trust_level"] is None
