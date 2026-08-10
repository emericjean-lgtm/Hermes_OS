"""Mission -> Project (authorized workspace) binding — the real link
between a Mission's context.project_id and Aegis's dynamic whitelist
(agents/aegis.py's _dynamic_allowed_paths / projects/store.py's
active_validated_project_roots), which RealTaskExecutor's workspace
tool-calling (execution/task_executor.py) resolves through
mission/routes.py's get_mission_by_id()."""
from __future__ import annotations

from backend.mission import routes as mission_routes
from backend.mission.mission_models import Mission, MissionContext


def test_create_mission_stores_project_id(client):
    response = client.post("/api/v1/missions", json={
        "title": "Test mission", "project_id": "proj-abc-123",
    })
    assert response.status_code == 200
    body = response.json()
    detail = client.get(f"/api/v1/missions/{body['mission_id']}").json()
    assert detail["project_id"] == "proj-abc-123"


def test_create_mission_without_project_id_defaults_empty(client):
    response = client.post("/api/v1/missions", json={"title": "No workspace"})
    body = response.json()
    detail = client.get(f"/api/v1/missions/{body['mission_id']}").json()
    assert detail["project_id"] == ""


def test_get_mission_by_id_resolves_registered_mission():
    mission = Mission(title="M", context=MissionContext(project_id="proj-xyz"))
    mission_routes.register_mission(mission)
    try:
        resolved = mission_routes.get_mission_by_id(mission.mission_id)
        assert resolved is not None
        assert resolved.context.project_id == "proj-xyz"
    finally:
        mission_routes._missions.pop(mission.mission_id, None)  # noqa: SLF001 - test cleanup


def test_get_mission_by_id_unknown_returns_none():
    assert mission_routes.get_mission_by_id("does-not-exist-at-all") is None


def test_check_mission_security_allows_local_path_inside_validated_project(
    tmp_path, monkeypatch,
):
    """The real fix: _check_mission_security used to consult only the
    static ALLOWED_PATHS whitelist — a Mission's local_path pointing at a
    freshly-registered, validated Project (outside the static config)
    would have been denied even though the exact same path is granted
    for a chat session bound to that Project. Both must agree."""
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated_static_only"))
    (tmp_path / "_unrelated_static_only").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()
    mission_routes._aegis_engine = None  # noqa: SLF001 - force a fresh engine for this test's ALLOWED_PATHS

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = get_project_store().create(name="ws", root_path=str(workspace))
    get_project_store().validate(project.id)

    mission = Mission(
        title="Bound mission",
        context=MissionContext(local_path=str(workspace)),
    )

    result = mission_routes._check_mission_security(mission)  # noqa: SLF001

    # None means "proceed" — the path was allowed, not denied/paused.
    assert result is None

    get_settings.cache_clear()
    get_project_store.cache_clear()
    mission_routes._aegis_engine = None  # noqa: SLF001 - don't leak this test's engine


def test_check_mission_security_denies_local_path_outside_everything(
    tmp_path, monkeypatch,
):
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated_static_only"))
    (tmp_path / "_unrelated_static_only").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()
    mission_routes._aegis_engine = None  # noqa: SLF001

    outside = tmp_path / "never_registered"
    outside.mkdir()
    mission = Mission(title="Unbound mission", context=MissionContext(local_path=str(outside)))

    result = mission_routes._check_mission_security(mission)  # noqa: SLF001

    assert result is not None
    assert "denied by Aegis" in result["error"]

    get_settings.cache_clear()
    get_project_store.cache_clear()
    mission_routes._aegis_engine = None  # noqa: SLF001
