from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from backend.memory.db import init_db, make_session_factory
from backend.workflows import run_store as rs


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_save_run_creates_then_updates(session):
    created = rs.save_run(
        session,
        run_id="run-1",
        workflow_id="wf-1",
        project_id=None,
        status="awaiting_validation",
        node_results={"a": {"status": "success", "result": {"x": 1}, "error": None}},
        pending_nodes=["b"],
        approved_nodes=set(),
    )
    assert created.status == "awaiting_validation"

    updated = rs.save_run(
        session,
        run_id="run-1",
        workflow_id="wf-1",
        project_id=None,
        status="completed",
        node_results={
            "a": {"status": "success", "result": {"x": 1}, "error": None},
            "b": {"status": "success", "result": {"y": 2}, "error": None},
        },
        pending_nodes=[],
        approved_nodes={"b"},
    )
    assert updated.id == created.id
    assert updated.status == "completed"
    assert updated.node_results_dict["b"]["result"] == {"y": 2}
    assert updated.pending_nodes_list == []
    assert updated.approved_nodes_set == {"b"}


def test_get_run_returns_none_when_missing(session):
    assert rs.get_run(session, "does-not-exist") is None


def test_list_runs_filters_by_workflow_and_project(session):
    rs.save_run(
        session, run_id="r1", workflow_id="wf-1", project_id="proj-1", status="completed",
        node_results={}, pending_nodes=[], approved_nodes=set(),
    )
    rs.save_run(
        session, run_id="r2", workflow_id="wf-2", project_id="proj-2", status="completed",
        node_results={}, pending_nodes=[], approved_nodes=set(),
    )

    assert [r.id for r in rs.list_runs(session, workflow_id="wf-1")] == ["r1"]
    assert [r.id for r in rs.list_runs(session, project_id="proj-2")] == ["r2"]
    assert {r.id for r in rs.list_runs(session)} == {"r1", "r2"}


def test_node_results_and_approved_nodes_round_trip_json(session):
    record = rs.save_run(
        session,
        run_id="run-1",
        workflow_id="wf-1",
        project_id=None,
        status="awaiting_validation",
        node_results={"a": {"status": "success", "result": None, "error": None}},
        pending_nodes=["b", "c"],
        approved_nodes={"a", "z"},
    )
    assert record.node_results_dict == {"a": {"status": "success", "result": None, "error": None}}
    assert record.pending_nodes_list == ["b", "c"]
    assert record.approved_nodes_set == {"a", "z"}
