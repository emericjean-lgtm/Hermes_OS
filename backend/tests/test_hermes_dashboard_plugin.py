"""Unit tests for config/hermes_agent_dashboard/plugin_api.py.

That file lives outside the backend/ package on purpose (it's meant to
be copied into ~/.hermes/plugins/hermes-ollama/dashboard/ and run inside
Hermes Agent's own Python process, not this one) — imported here via
importlib.util.spec_from_file_location, a fresh module object per test
so each test can point BACKEND_URL (read once, at import time) at its
own fake backend server.

Exercises the proxy logic (plugin_api.py's _get_json) against a real
local HTTP server, not a mocked urllib — the most faithful way to prove
the actual network call shape works, without needing a real Hermes
Ollama backend or Hermes Agent install (neither is reachable from this
sandbox, see README.md alongside plugin_api.py).
"""
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_PLUGIN_API_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "hermes_agent_dashboard" / "plugin_api.py"
)

_FAKE_RESPONSES = {
    "/system/status": {"gpu": None, "cpu_load_pct": 12.3, "loaded_models": []},
    "/projects": [{"id": "p1", "name": "Demo", "status": "active"}],
    "/tasks": [{"id": "t1", "status": "done"}],
    "/evolution/progression": {"success_rate": 1.0, "skills_total": 0},
}


class _FakeBackendHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server's required method name
        body = _FAKE_RESPONSES.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - silence test output
        pass


@pytest.fixture
def fake_backend():
    server = HTTPServer(("127.0.0.1", 0), _FakeBackendHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _load_plugin_api(monkeypatch, backend_url: str):
    monkeypatch.setenv("HERMES_OLLAMA_BACKEND_URL", backend_url)
    spec = importlib.util.spec_from_file_location(
        f"hermes_dashboard_plugin_api_{backend_url.rsplit(':', 1)[-1]}", _PLUGIN_API_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _client_for(module) -> TestClient:
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def test_backend_url_defaults_and_strips_trailing_slash(monkeypatch):
    monkeypatch.delenv("HERMES_OLLAMA_BACKEND_URL", raising=False)
    module = _load_plugin_api(monkeypatch, "http://127.0.0.1:8000/")
    assert module.BACKEND_URL == "http://127.0.0.1:8000"


def test_system_status_proxies_backend(monkeypatch, fake_backend):
    module = _load_plugin_api(monkeypatch, fake_backend)
    response = _client_for(module).get("/system-status")
    assert response.status_code == 200
    assert response.json() == _FAKE_RESPONSES["/system/status"]


def test_projects_proxies_backend(monkeypatch, fake_backend):
    module = _load_plugin_api(monkeypatch, fake_backend)
    response = _client_for(module).get("/projects")
    assert response.status_code == 200
    assert response.json() == _FAKE_RESPONSES["/projects"]


def test_tasks_proxies_backend(monkeypatch, fake_backend):
    module = _load_plugin_api(monkeypatch, fake_backend)
    response = _client_for(module).get("/tasks")
    assert response.status_code == 200
    assert response.json() == _FAKE_RESPONSES["/tasks"]


def test_progression_proxies_backend(monkeypatch, fake_backend):
    module = _load_plugin_api(monkeypatch, fake_backend)
    response = _client_for(module).get("/progression")
    assert response.status_code == 200
    assert response.json() == _FAKE_RESPONSES["/evolution/progression"]


def test_unreachable_backend_returns_502(monkeypatch):
    # Port 1 is a privileged port nothing is listening on: fails fast
    # with connection-refused rather than hanging on a real timeout.
    module = _load_plugin_api(monkeypatch, "http://127.0.0.1:1")
    response = _client_for(module).get("/system-status")
    assert response.status_code == 502
    assert "unreachable" in response.json()["detail"]
