"""Tests for GET/POST /api/v1/code-intelligence (R-006 Phase 2).

Hermetic: the FastAPI app under test mounts only the code-intelligence
router against a fake agent that mirrors ``CodeIntelligenceAgent``'s real
public surface (get_status_dict, agent_capabilities, profile, execute_task,
get_task_history, _klaatcode_agent/_ohmypi_agent) — no Ollama, no real
KlaatCode/Oh My Pi subprocess calls. Real end-to-end reachability through
the full composition root is covered separately in
tests/integration/test_assembly.py.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agents.agent_models import AgentCapability, ExecutionResult, TaskOutcome
from backend.api.routes.code_intelligence import create_code_intelligence_routes
from backend.integrations.code_intelligence.code_intelligence_models import CodeProvider


class _FakeProfile:
    providers = ["klaatcode", "ohmypi"]


class _FakeMCPAdapter:
    def __init__(self, status: dict) -> None:
        self._status = status

    def get_status(self) -> dict:
        return self._status


class _FakeSubAgent:
    def __init__(self, *, available: bool, status: dict) -> None:
        self.is_available = available
        self._mcp_adapter = _FakeMCPAdapter(status)


class _FakeHermesNative:
    agent_id = "hermes_native_test"
    is_available = True


class _FakeCIAgent:
    """Mirrors CodeIntelligenceAgent's real public surface, not a mock of
    behaviour — the route module calls exactly these names."""

    def __init__(self) -> None:
        self.profile = _FakeProfile()
        self._klaatcode_agent = _FakeSubAgent(
            available=True, status={"installed": True, "server_bound": False},
        )
        self._ohmypi_agent = _FakeSubAgent(
            available=False, status={"installed": True},
        )
        self._hermes_native_executor = _FakeHermesNative()
        self.last_call: Optional[tuple[str, dict, str, str, Any]] = None
        self.next_outcome = TaskOutcome.SUCCESS

    @property
    def agent_capabilities(self) -> list[AgentCapability]:
        return [AgentCapability.CODE_GENERATION, AgentCapability.CODE_REVIEW]

    def get_status_dict(self) -> dict:
        return {"agent_id": "ci_test", "status": "ready", "total_tasks": 3}

    def get_task_history(self, limit: int = 50) -> list[dict]:
        return [{"task_id": "t1", "task_type": "code_analysis", "success": True}][:limit]

    def execute_task(
        self, task_type: str, parameters: dict, *, mission_id: str = "",
        node_id: str = "", force_provider: CodeProvider | None = None,
    ) -> ExecutionResult:
        self.last_call = (task_type, parameters, mission_id, node_id, force_provider)
        return ExecutionResult(
            outcome=self.next_outcome,
            duration_ms=42.0,
            summary=f"CI {task_type}: klaatcode success",
            details={
                "data": {"ok": True},
                "provider": "klaatcode",
                "strategy": "single_best",
                "decision": {"selected_provider": "klaatcode"},
            },
            error_message="" if self.next_outcome == TaskOutcome.SUCCESS else "boom",
        )


@pytest.fixture
def fake_agent() -> _FakeCIAgent:
    return _FakeCIAgent()


@pytest.fixture
def client(fake_agent: _FakeCIAgent) -> TestClient:
    app = FastAPI()
    app.include_router(create_code_intelligence_routes(fake_agent), prefix="/api/v1")
    return TestClient(app)


class TestStatus:
    def test_status_reflects_the_real_agent(self, client: TestClient):
        resp = client.get("/api/v1/code-intelligence/status")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "ci_test"


class TestCapabilities:
    def test_capabilities_are_real_not_fictional(self, client: TestClient, fake_agent):
        resp = client.get("/api/v1/code-intelligence/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["capabilities"] == ["code_generation", "code_review"]
        assert body["providers"] == ["klaatcode", "ohmypi"]
        assert "code_analysis" in body["task_types"]


class TestProviders:
    def test_providers_reuse_each_agents_own_status_check(self, client: TestClient):
        resp = client.get("/api/v1/code-intelligence/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["klaatcode"]["available"] is True
        assert body["klaatcode"]["status"]["installed"] is True
        assert body["ohmypi"]["available"] is False

    def test_hermes_native_provider_is_reported(self, client: TestClient):
        resp = client.get("/api/v1/code-intelligence/providers")
        body = resp.json()
        assert body["hermes_native"]["available"] is True
        assert body["hermes_native"]["status"]["agent_id"] == "hermes_native_test"

    def test_missing_hermes_native_executor_reports_unavailable(self, fake_agent):
        fake_agent._hermes_native_executor = None
        app = FastAPI()
        app.include_router(create_code_intelligence_routes(fake_agent), prefix="/api/v1")
        resp = TestClient(app).get("/api/v1/code-intelligence/providers")
        assert resp.status_code == 200
        assert resp.json()["hermes_native"] == {"available": False, "status": None}

    def test_missing_sub_agent_reports_unavailable_not_500(self, fake_agent):
        fake_agent._ohmypi_agent = None
        app = FastAPI()
        app.include_router(create_code_intelligence_routes(fake_agent), prefix="/api/v1")
        resp = TestClient(app).get("/api/v1/code-intelligence/providers")
        assert resp.status_code == 200
        assert resp.json()["ohmypi"] == {"available": False, "status": None}


class TestTaskEndpoints:
    @pytest.mark.parametrize(
        "path,expected_task_type",
        [
            ("/api/v1/code-intelligence/analyze", "code_analysis"),
            ("/api/v1/code-intelligence/review", "code_review"),
            ("/api/v1/code-intelligence/debug", "debugging"),
            ("/api/v1/code-intelligence/explain", "documentation"),
        ],
    )
    def test_each_endpoint_routes_to_its_real_task_type(
        self, client: TestClient, fake_agent: _FakeCIAgent, path, expected_task_type,
    ):
        resp = client.post(path, json={"project_path": "backend/"})
        assert resp.status_code == 200
        assert fake_agent.last_call[0] == expected_task_type
        assert fake_agent.last_call[1]["project_path"] == "backend/"
        body = resp.json()
        assert body["success"] is True
        assert body["provider"] == "klaatcode"

    def test_failed_execution_is_reported_not_hidden(self, client: TestClient, fake_agent):
        fake_agent.next_outcome = TaskOutcome.FAILURE
        resp = client.post("/api/v1/code-intelligence/debug", json={})
        assert resp.status_code == 200  # a failed task is not an HTTP error
        body = resp.json()
        assert body["success"] is False
        assert body["error"] == "boom"

    def test_force_provider_reaches_execute_task(self, client: TestClient, fake_agent):
        resp = client.post(
            "/api/v1/code-intelligence/analyze",
            json={"force_provider": "ohmypi"},
        )
        assert resp.status_code == 200
        assert fake_agent.last_call[4] == CodeProvider.OHMYPI

    def test_invalid_force_provider_is_422_not_500(self, client: TestClient):
        resp = client.post(
            "/api/v1/code-intelligence/analyze",
            json={"force_provider": "gpt-5-turbo-max"},
        )
        assert resp.status_code == 422
        assert "force_provider" in resp.json()["detail"]

    def test_malformed_parameters_is_422_not_500(self, client: TestClient):
        """parameters must be an object — a string must not reach
        execute_task() and blow up as a 500 (Phase 2's explicit contract)."""
        resp = client.post(
            "/api/v1/code-intelligence/review",
            json={"parameters": "not-an-object"},
        )
        assert resp.status_code == 422

    def test_missing_body_still_works_via_defaults(self, client: TestClient):
        """Every CodeTaskRequest field has a default — an empty body is a
        valid request, not a 422."""
        resp = client.post("/api/v1/code-intelligence/explain", json={})
        assert resp.status_code == 200


class TestHistory:
    def test_history_is_the_agents_real_log(self, client: TestClient):
        resp = client.get("/api/v1/code-intelligence/history?limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["history"][0]["task_id"] == "t1"


class TestUninitialized:
    def test_status_before_wiring_is_503_not_crash(self):
        """If a caller mounts the router before create_code_intelligence_routes
        supplies a real agent, every endpoint must fail loudly (503), never
        with an AttributeError on None."""
        import backend.api.routes.code_intelligence as ci_routes

        original = ci_routes._agent
        try:
            ci_routes._agent = None
            app = FastAPI()
            app.include_router(ci_routes.router, prefix="/api/v1")
            resp = TestClient(app).get("/api/v1/code-intelligence/status")
            assert resp.status_code == 503
        finally:
            ci_routes._agent = original
