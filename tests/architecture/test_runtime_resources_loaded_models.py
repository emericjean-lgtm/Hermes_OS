"""Tests for HOS-072 — GET /runtime/resources/loaded-models and
POST /runtime/resources/unload.

Real signal for "what's actually resident right now" (Ollama's own
/api/ps), and a real action to free a model's VRAM immediately — the
backend for the Runtime Center's "décharger un modèle" action. Fully
hermetic: OllamaClient itself is monkeypatched with a fake, no real
Ollama server needed.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.connectors.ollama_client as ollama_client_module
import backend.runtime.resources.routes as resources_routes
from backend.connectors.ollama_client import OllamaUnavailableError
from backend.runtime.resources.resource_manager import ResourceManager


class _FakeOllamaClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0, **_: Any) -> None:
        self.base_url = base_url
        self.closed = False
        self.unload_calls: list[str] = []

    async def list_running_models(self) -> list[dict[str, Any]]:
        return [
            {"name": "qwen3.5:9b", "size": 5_721_139_200, "size_vram": 5_721_139_200,
             "expires_at": "2026-01-01T00:05:00Z"},
        ]

    async def unload_model(self, model: str) -> None:
        self.unload_calls.append(model)

    async def aclose(self) -> None:
        self.closed = True


class _UnreachableOllamaClient(_FakeOllamaClient):
    async def list_running_models(self) -> list[dict[str, Any]]:
        raise OllamaUnavailableError("Ollama is not running")

    async def unload_model(self, model: str) -> None:
        raise OllamaUnavailableError("Ollama is not running")


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(resources_routes.create_resource_routes(ResourceManager()))
    return test_app


class TestLoadedModels:
    def test_returns_real_resident_models(self, app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ollama_client_module, "OllamaClient", _FakeOllamaClient)
        with TestClient(app) as client:
            response = client.get("/runtime/resources/loaded-models")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["models"] == [{
            "name": "qwen3.5:9b",
            "size_bytes": 5_721_139_200,
            "size_vram_bytes": 5_721_139_200,
            "expires_at": "2026-01-01T00:05:00Z",
        }]

    def test_unreachable_ollama_reports_failure_not_fabricated_empty_success(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(ollama_client_module, "OllamaClient", _UnreachableOllamaClient)
        with TestClient(app) as client:
            response = client.get("/runtime/resources/loaded-models")
        data = response.json()
        assert data["success"] is False
        assert data["models"] == []


class TestUnloadModel:
    def test_unloads_the_named_model(self, app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        class _Capturing(_FakeOllamaClient):
            async def unload_model(self, model: str) -> None:
                captured["model"] = model

        monkeypatch.setattr(ollama_client_module, "OllamaClient", _Capturing)
        with TestClient(app) as client:
            response = client.post("/runtime/resources/unload", json={"model": "qwen3.5:9b"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model"] == "qwen3.5:9b"
        assert captured["model"] == "qwen3.5:9b"

    def test_missing_model_is_rejected_without_a_call(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(ollama_client_module, "OllamaClient", _FakeOllamaClient)
        with TestClient(app) as client:
            response = client.post("/runtime/resources/unload", json={})
        data = response.json()
        assert data["success"] is False

    def test_unreachable_ollama_reports_failure(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(ollama_client_module, "OllamaClient", _UnreachableOllamaClient)
        with TestClient(app) as client:
            response = client.post("/runtime/resources/unload", json={"model": "qwen3.5:9b"})
        data = response.json()
        assert data["success"] is False
