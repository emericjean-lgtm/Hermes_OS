from __future__ import annotations

import pytest

from backend.projects.project_manager import InvalidProjectStatusError, ProjectStatus
from backend.projects.store import ProjectStore, get_project_store


@pytest.fixture
def store(tmp_path) -> ProjectStore:
    return ProjectStore(str(tmp_path / "test.db"))


def test_create_and_get_round_trip(store):
    created = store.create(name="X", tags=["pro"])

    fetched = store.get(created.id)

    assert fetched is not None
    assert fetched.name == "X"
    assert fetched.tags_list == ["pro"]


def test_list_returns_all_projects(store):
    store.create(name="A")
    store.create(name="B")

    assert {p.name for p in store.list()} == {"A", "B"}


def test_update_and_delete(store):
    project = store.create(name="X")

    updated = store.update(project.id, status=ProjectStatus.ARCHIVED)
    assert updated.status == ProjectStatus.ARCHIVED.value

    assert store.delete(project.id) is True
    assert store.get(project.id) is None


def test_update_invalid_status_raises(store):
    project = store.create(name="X")

    with pytest.raises(InvalidProjectStatusError):
        store.update(project.id, status="bogus")


def test_get_project_store_is_cached(monkeypatch, tmp_path):
    from backend.core.config import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()
    try:
        assert get_project_store() is get_project_store()
    finally:
        get_settings.cache_clear()
        get_project_store.cache_clear()
