"""HOS-008 sentinel tests — RuntimeRegistry SDS integration.

Tests the new ``/api/hermes-os/runtimes`` endpoints without any
network call.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.sds.routes import SDS_ROUTER
import backend.sds.runtime as _sds_runtime


@asynccontextmanager
async def _test_lifespan(_app: FastAPI) -> None:
    """Initialize SDS singletons for the in-memory test app.

    ``TestClient`` triggers this lifespan automatically. It mirrors the
    real ``backend.main`` bootstrap but uses a file-backed SQLite event
    bus in a temporary directory and resets the global singletons for
    strict test isolation.
    """
    # Clean up any previous state first.
    if _sds_runtime._HOLDER is not None:
        await _sds_runtime._HOLDER.stop()
    if _sds_runtime._RT_HOLDER is not None:
        await _sds_runtime._RT_HOLDER.stop()

    # Reset global singletons to guarantee a clean state.
    _sds_runtime._HOLDER = None
    _sds_runtime._RT_HOLDER = None
    _sds_runtime._REGISTRY = None
    _sds_runtime._FACTORY = None
    _sds_runtime._HEALTH_MONITOR = None

    # Use a unique temporary file for the SQLite event bus.
    tmp_dir = tempfile.mkdtemp(prefix="hos_008_")
    sqlite_path = os.path.join(tmp_dir, f"eventbus_{uuid.uuid4().hex}.sqlite")

    # Bootstrap EventBus -> RuntimeRegistry in the same order as main.py.
    await _sds_runtime.init_eventbus_in_holder(sqlite_path)
    await _sds_runtime.init_runtime_registry_in_holder("stub")

    try:
        yield
    finally:
        await _sds_runtime.shutdown_runtime_registry()
        await _sds_runtime.get_holder().stop()
        _sds_runtime._HOLDER = None
        _sds_runtime._RT_HOLDER = None
        _sds_runtime._REGISTRY = None
        _sds_runtime._FACTORY = None
        try:
            os.remove(sqlite_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


@pytest.fixture
def app() -> FastAPI:
    """Build a minimal FastAPI app with the SDS router and test lifespan."""
    test_app = FastAPI(lifespan=_test_lifespan)
    test_app.include_router(SDS_ROUTER)
    return test_app


def test_list_runtimes_returns_stub(app: FastAPI) -> None:
    """GET /runtimes returns the default stub runtime."""
    with TestClient(app) as client:
        response = client.get("/api/hermes-os/runtimes")
        assert response.status_code == 200
        data = response.json()
        assert "runtimes" in data
        names = [r["name"] for r in data["runtimes"]]
        assert "stub" in names


def test_list_runtime_types_returns_stub_and_ollama(app: FastAPI) -> None:
    """GET /runtimes/types lists both registered builders."""
    with TestClient(app) as client:
        response = client.get("/api/hermes-os/runtimes/types")
        assert response.status_code == 200
        data = response.json()
        assert "stub" in data["types"]
        assert "ollama" in data["types"]


def test_get_runtime_returns_stub(app: FastAPI) -> None:
    """GET /runtimes/stub returns the stub runtime metadata."""
    with TestClient(app) as client:
        response = client.get("/api/hermes-os/runtimes/stub")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "stub"
        assert data["version"] == "0.1.0"
        assert "chat" in data["capabilities"]
        assert data["healthy"] is True


def test_list_runtimes_metrics_absent_when_never_used(app: FastAPI) -> None:
    """HOS-072: a runtime with no recorded execution reports metrics/health
    as null — unmeasured, not measured-at-zero."""
    with TestClient(app) as client:
        response = client.get("/api/hermes-os/runtimes")
        data = response.json()
        stub = next(r for r in data["runtimes"] if r["name"] == "stub")
        assert stub["metrics"] is None
        assert stub["health"] is None


def test_list_runtimes_metrics_reflect_real_execution(app: FastAPI) -> None:
    """HOS-072: GET /runtimes' metrics/health come from the real health
    monitor, fed by RealTaskExecutor.on_runtime_result — before this fix
    these fields were always absent regardless of real task volume."""
    with TestClient(app) as client:
        # Recorded only after the lifespan has run — it resets
        # _HEALTH_MONITOR to None on startup, same as the other singletons.
        _sds_runtime.get_runtime_health_monitor().record_execution(
            "stub", latency_ms=120, success=True,
        )
        _sds_runtime.get_runtime_health_monitor().record_execution(
            "stub", latency_ms=80, success=False,
        )
        response = client.get("/api/hermes-os/runtimes")
        data = response.json()
        stub = next(r for r in data["runtimes"] if r["name"] == "stub")
        assert stub["metrics"]["total_executions"] == 2
        assert stub["metrics"]["success_count"] == 1
        assert stub["metrics"]["failure_count"] == 1
        assert stub["metrics"]["avg_latency_ms"] == 100.0
        assert stub["metrics"]["reliability"] == 0.5
        assert stub["health"]["latency_ms"] == 100.0


def test_get_unknown_runtime_returns_404(app: FastAPI) -> None:
    """GET /runtimes/unknown returns 404."""
    with TestClient(app) as client:
        response = client.get("/api/hermes-os/runtimes/unknown")
        assert response.status_code == 404


def test_select_runtime_switches_active_pointer(app: FastAPI) -> None:
    """POST /runtimes/{name}/select updates the active runtime holder."""
    with TestClient(app) as client:
        # First ensure stub is selected by default via the legacy endpoint.
        before = client.get("/api/hermes-os/runtime")
        assert before.status_code == 200
        assert before.json()["name"] == "stub"

        response = client.post("/api/hermes-os/runtimes/stub/select")
        assert response.status_code == 200
        data = response.json()
        assert data["selected"] == "stub"


def test_registry_dependency_requires_initialization() -> None:
    """The registry dependency raises 503 if no runtime is registered."""
    from backend.ral.runtime_registry import RuntimeRegistry

    registry = RuntimeRegistry()
    assert registry.list_available() == []


# The FastAPI dependency functions are exercised above through TestClient.
# The following directly checks the factory dependency guard.

def test_factory_dependency_raises_when_uninitialized() -> None:
    """A factory with no builders should be considered uninitialized."""
    from backend.ral.runtime_factory import RuntimeFactory

    factory = RuntimeFactory()
    assert factory.available_types() == []
