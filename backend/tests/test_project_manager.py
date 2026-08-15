from __future__ import annotations

import time

import pytest

from backend.memory.db import init_db, make_engine, make_session_factory
from backend.projects import project_manager
from backend.projects.project_manager import InvalidProjectStatusError, ProjectStatus


@pytest.fixture
def session(tmp_path):
    engine = make_engine(str(tmp_path / "test.db"))
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as s:
        yield s


def test_create_project_defaults_to_active(session):
    project = project_manager.create_project(session, name="Website Redesign")

    assert project.name == "Website Redesign"
    assert project.status == ProjectStatus.ACTIVE.value
    assert project.description == ""
    assert project.root_path is None
    assert project.tags_list == []
    assert project.created_at == project.updated_at


def test_create_project_with_all_fields(session):
    project = project_manager.create_project(
        session,
        name="Client X",
        description="Freelance contract",
        root_path="/home/user/projects/client-x",
        tags=["pro", "client-x"],
    )

    assert project.description == "Freelance contract"
    assert project.root_path == "/home/user/projects/client-x"
    assert project.tags_list == ["pro", "client-x"]


def test_get_project_returns_none_when_missing(session):
    assert project_manager.get_project(session, "does-not-exist") is None


def test_get_project_returns_created_project(session):
    created = project_manager.create_project(session, name="X")

    fetched = project_manager.get_project(session, created.id)

    assert fetched is not None
    assert fetched.id == created.id


def test_list_projects_orders_most_recent_first(session):
    """Les deux dates doivent être distinctes pour que ce test porte sur
    la récence.

    Sous Windows l'horloge système avance par pas d'environ 15,6 ms : deux
    créations consécutives partagent leur `created_at`, l'ordre devient une
    égalité, et le test rendait un verdict différent d'une exécution à
    l'autre — sans rien dire de la règle qu'il décrit. La pause de 20 ms
    tient au-dessus de la granularité. Le départage des ex aequo, lui, est
    garanti côté requête (`list_projects`), pas ici (HOS-112).
    """
    first = project_manager.create_project(session, name="First")
    time.sleep(0.02)
    second = project_manager.create_project(session, name="Second")

    projects = project_manager.list_projects(session)

    assert [p.id for p in projects] == [second.id, first.id]


def test_list_projects_filters_by_status(session):
    active = project_manager.create_project(session, name="Active one")
    archived = project_manager.create_project(session, name="Archived one")
    project_manager.update_project(session, archived.id, status=ProjectStatus.ARCHIVED)

    active_only = project_manager.list_projects(session, status=ProjectStatus.ACTIVE)

    assert [p.id for p in active_only] == [active.id]


def test_list_projects_filters_by_invalid_status_raises(session):
    with pytest.raises(InvalidProjectStatusError):
        project_manager.list_projects(session, status="not-a-status")


def test_list_projects_filters_by_tag(session):
    project_manager.create_project(session, name="Pro one", tags=["pro"])
    project_manager.create_project(session, name="Perso one", tags=["perso"])

    pro_only = project_manager.list_projects(session, tag="pro")

    assert [p.name for p in pro_only] == ["Pro one"]


def test_update_project_updates_fields_and_timestamp(session):
    project = project_manager.create_project(session, name="Old name")

    updated = project_manager.update_project(
        session, project.id, name="New name", description="Updated", tags=["pro"]
    )

    assert updated is not None
    assert updated.name == "New name"
    assert updated.description == "Updated"
    assert updated.tags_list == ["pro"]
    assert updated.updated_at >= updated.created_at


def test_update_project_returns_none_when_missing(session):
    assert project_manager.update_project(session, "does-not-exist", name="X") is None


def test_update_project_invalid_status_raises(session):
    project = project_manager.create_project(session, name="X")

    with pytest.raises(InvalidProjectStatusError):
        project_manager.update_project(session, project.id, status="not-a-status")


def test_update_project_leaves_unspecified_fields_untouched(session):
    project = project_manager.create_project(session, name="X", description="original")

    updated = project_manager.update_project(session, project.id, name="Y")

    assert updated.description == "original"


def test_delete_project_returns_true_when_existed(session):
    project = project_manager.create_project(session, name="X")

    assert project_manager.delete_project(session, project.id) is True
    assert project_manager.get_project(session, project.id) is None


def test_delete_project_returns_false_when_missing(session):
    assert project_manager.delete_project(session, "does-not-exist") is False
