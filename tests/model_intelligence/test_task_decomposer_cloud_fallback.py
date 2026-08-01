"""Tests for TaskDecomposer's cloud fallback (HOS-066C) — local LLM
decomposition is always tried first; a cloud retry only happens after it
has already failed, and rule-based decomposition remains the final safety
net if cloud fails or isn't available either.
"""
from __future__ import annotations

import json

from backend.connectors.ollama_client import StreamChunk
from backend.core.config import load_models_config
from backend.core.router import ModelRouter
from backend.mission.planner.planner_models import PlanningRequest
from backend.mission.planner.task_decomposer import TaskDecomposer

_LLM_CONTENT = json.dumps([
    {"title": "Design schema", "description": "Plan tables",
     "category": "design", "depends_on": []},
])


class _FailingOllama:
    async def chat_events(self, model, messages, *, temperature=None,
                          top_p=None, num_ctx=None, think=None):
        raise RuntimeError("Ollama unreachable")
        yield  # pragma: no cover - unreachable, satisfies generator syntax


class _WorkingOllama:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0

    async def chat_events(self, model, messages, *, temperature=None,
                          top_p=None, num_ctx=None, think=None):
        self.calls += 1
        yield StreamChunk("content", self._content)


class _FakeCloud:
    def __init__(self, content: str | None = None, *, fails: bool = False) -> None:
        self._content = content
        self._fails = fails
        self.calls: list[tuple] = []

    async def chat_events(self, model, messages, *, temperature=None, top_p=None):
        self.calls.append((model, messages))
        if self._fails:
            raise RuntimeError("OpenRouter unreachable")
            yield  # pragma: no cover
            return
        yield StreamChunk("content", self._content)


def _decomposer(ollama, cloud=None) -> TaskDecomposer:
    models_config = load_models_config()
    return TaskDecomposer(
        ollama_client=ollama, router=ModelRouter(models_config),
        models_config=models_config, cloud_client=cloud,
    )


class TestNoCloudFailurePath:
    def test_local_success_never_touches_cloud(self):
        ollama = _WorkingOllama(_LLM_CONTENT)
        cloud = _FakeCloud(_LLM_CONTENT)
        decomposer = _decomposer(ollama, cloud)
        breakdowns = decomposer.decompose(PlanningRequest(user_request="Build a database layer"))
        assert breakdowns[0].title == "Design schema"
        assert cloud.calls == []


class TestCloudFallback:
    def test_falls_back_to_cloud_when_local_fails(self, monkeypatch):
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: "cloud/model:free")
        cloud = _FakeCloud(_LLM_CONTENT)
        decomposer = _decomposer(_FailingOllama(), cloud)
        breakdowns = decomposer.decompose(PlanningRequest(user_request="Build a database layer"))
        assert breakdowns[0].title == "Design schema"
        assert cloud.calls[0][0] == "cloud/model:free"

    def test_falls_back_to_rule_based_when_cloud_also_fails(self, monkeypatch):
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: "cloud/model:free")
        cloud = _FakeCloud(fails=True)
        decomposer = _decomposer(_FailingOllama(), cloud)
        request = PlanningRequest(user_request="Create an authentication system")
        breakdowns = decomposer.decompose(request)
        # Degrades to the rule-based auth pattern, same safety net as a
        # malformed-JSON local response already relies on.
        assert any("auth" in b.title.lower() for b in breakdowns)

    def test_no_cloud_client_falls_back_to_rule_based(self):
        decomposer = _decomposer(_FailingOllama(), cloud=None)
        request = PlanningRequest(user_request="Create an authentication system")
        breakdowns = decomposer.decompose(request)
        assert any("auth" in b.title.lower() for b in breakdowns)

    def test_no_cloud_model_available_falls_back_to_rule_based(self, monkeypatch):
        import backend.model_intelligence.routes as mi_routes

        monkeypatch.setattr(mi_routes, "get_cloud_fallback_model", lambda tt: None)
        cloud = _FakeCloud(_LLM_CONTENT)
        decomposer = _decomposer(_FailingOllama(), cloud)
        request = PlanningRequest(user_request="Create an authentication system")
        breakdowns = decomposer.decompose(request)
        assert any("auth" in b.title.lower() for b in breakdowns)
        assert cloud.calls == []
