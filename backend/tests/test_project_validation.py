"""Project.root_path validation — real, on-disk-tested state, never a
claim (see project_manager.py's module docstring). Covers both the pure
validate_project_path() probe and the persisted validate_project()/
ProjectStore.validate() path that Aegis's dynamic whitelist actually
reads (agents/aegis.py's _dynamic_allowed_paths)."""
from __future__ import annotations

import pytest

from backend.memory.db import init_db, make_engine, make_session_factory
from backend.projects import project_manager
from backend.projects.project_manager import ValidationStatus


@pytest.fixture
def session(tmp_path):
    engine = make_engine(str(tmp_path / "test.db"))
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as s:
        yield s


def test_validate_path_missing_directory_is_inaccessible(tmp_path):
    result = project_manager.validate_project_path(str(tmp_path / "nope"))
    assert result["accessible"] is False
    assert result["readable"] is False
    assert result["writable"] is False


def test_validate_path_file_not_directory_is_inaccessible(tmp_path):
    f = tmp_path / "not-a-dir.txt"
    f.write_text("hi")
    result = project_manager.validate_project_path(str(f))
    assert result["accessible"] is False


def test_validate_path_real_directory_is_accessible_readable_writable(tmp_path):
    result = project_manager.validate_project_path(str(tmp_path))
    assert result["accessible"] is True
    assert result["readable"] is True
    assert result["writable"] is True
    assert result["resolved_path"] == str(tmp_path.resolve())


def test_validate_path_leaves_no_probe_file_behind(tmp_path):
    project_manager.validate_project_path(str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_validate_project_persists_result_and_normalizes_root_path(session, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    project = project_manager.create_project(session, name="p", root_path=str(sub) + "/")
    assert project.validation_status == ValidationStatus.UNVALIDATED.value

    validated = project_manager.validate_project(session, project.id)

    assert validated.validation_status == ValidationStatus.VALID.value
    assert validated.validated_accessible is True
    assert validated.validated_readable is True
    assert validated.validated_writable is True
    assert validated.validated_at is not None
    # Normalized to the resolved absolute form (cahier des charges:
    # "normalise et résous immédiatement le chemin") — no trailing slash.
    assert validated.root_path == str(sub.resolve())


def test_validate_project_missing_path_marks_invalid(session, tmp_path):
    project = project_manager.create_project(
        session, name="p", root_path=str(tmp_path / "missing")
    )
    validated = project_manager.validate_project(session, project.id)
    assert validated.validation_status == ValidationStatus.INVALID.value
    assert validated.validated_accessible is False


def test_validate_project_no_root_path_marks_invalid(session):
    project = project_manager.create_project(session, name="p", root_path=None)
    validated = project_manager.validate_project(session, project.id)
    assert validated.validation_status == ValidationStatus.INVALID.value


def test_validate_project_unknown_id_returns_none(session):
    assert project_manager.validate_project(session, "does-not-exist") is None


def test_update_project_changing_root_path_resets_validation(session, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    project = project_manager.create_project(session, name="p", root_path=str(sub))
    project_manager.validate_project(session, project.id)

    updated = project_manager.update_project(session, project.id, root_path=str(other))

    assert updated.validation_status == ValidationStatus.UNVALIDATED.value
    assert updated.validated_accessible is None
