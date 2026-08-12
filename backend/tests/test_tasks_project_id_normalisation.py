"""tasks_create -> tasks_list(project_id) must find the task (HOS-087).

Reported symptom: a task created with a project scope was invisible to a
listing filtered by that same project. The SQL filter was never wrong — it
is an exact match on ``Task.project_id`` — the two calls were simply
comparing different strings. Hermes Agent runs with the workspace as its
cwd, so it naturally names a project by its filesystem path, while Hermes OS
stores the canonical Project id.

Normalising at the MCP boundary is deliberate: that is where a caller with
only a path meets a store keyed by id. Unknown values pass through unchanged
rather than collapsing to None, because a scoped query that silently widens
to "every project" is worse than one that returns nothing.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def project_env(monkeypatch, tmp_path):
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "tasks.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()
    get_agent_registry.cache_clear()

    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    project = get_project_store().create(name="ws", root_path=str(workspace))

    yield project, workspace

    get_settings.cache_clear()
    get_project_store.cache_clear()
    get_agent_registry.cache_clear()


def test_created_by_path_is_listed_by_path(project_env):
    from backend.mcp_server import server

    _project, workspace = project_env
    server.tasks_create(title="Write the report", project_id=str(workspace))

    found = server.tasks_list(project_id=str(workspace))

    assert len(found) == 1, "a task created under this project was not listed under it"
    assert found[0]["title"] == "Write the report"


def test_path_and_id_name_the_same_scope(project_env):
    from backend.mcp_server import server

    project, workspace = project_env
    server.tasks_create(title="Ship it", project_id=str(workspace))

    by_id = server.tasks_list(project_id=project.id)
    by_path = server.tasks_list(project_id=str(workspace))
    by_subdir = server.tasks_list(project_id=str(workspace / "src"))

    assert [t["id"] for t in by_id] == [t["id"] for t in by_path] == [t["id"] for t in by_subdir]


def test_task_is_stored_under_the_canonical_id(project_env):
    """The stored value must be the id, not the path — otherwise every other
    consumer of Task.project_id inherits the same mismatch."""
    from backend.mcp_server import server

    project, workspace = project_env
    created = server.tasks_create(title="Normalise me", project_id=str(workspace))

    assert created["project_id"] == project.id


def test_projects_stay_isolated(project_env, tmp_path):
    from backend.mcp_server import server
    from backend.projects.store import get_project_store

    _project, workspace = project_env
    other_root = tmp_path / "other"
    other_root.mkdir()
    get_project_store().create(name="other", root_path=str(other_root))

    server.tasks_create(title="Mine", project_id=str(workspace))
    server.tasks_create(title="Theirs", project_id=str(other_root))

    assert [t["title"] for t in server.tasks_list(project_id=str(workspace))] == ["Mine"]
    assert [t["title"] for t in server.tasks_list(project_id=str(other_root))] == ["Theirs"]


def test_unknown_scope_returns_nothing_rather_than_everything(project_env, tmp_path):
    """An unresolvable project must not widen the query — leaking another
    project's tasks into a scoped listing is the dangerous failure here."""
    from backend.mcp_server import server

    _project, workspace = project_env
    server.tasks_create(title="Scoped", project_id=str(workspace))

    assert server.tasks_list(project_id=str(tmp_path / "nope")) == []


def test_unscoped_listing_still_sees_everything(project_env):
    from backend.mcp_server import server

    _project, workspace = project_env
    server.tasks_create(title="Scoped", project_id=str(workspace))
    server.tasks_create(title="Unscoped")

    assert len(server.tasks_list()) == 2
