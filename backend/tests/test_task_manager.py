from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from backend.memory.db import init_db, make_session_factory
from backend.tasks import task_manager as tm


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_create_task_defaults_to_todo_status(session):
    task = tm.create_task(session, title="Refactor auth")
    assert task.status == tm.TaskStatus.TODO.value
    assert task.priority == tm.TaskPriority.MEDIUM.value
    assert task.files_list == []
    assert task.models_used_list == []
    assert task.test_results_dict is None
    assert len(task.history_list) == 1
    assert task.history_list[0]["note"] == "Task created"


def test_create_task_rejects_invalid_priority(session):
    with pytest.raises(tm.InvalidTaskPriorityError):
        tm.create_task(session, title="x", priority="urgentissime")


def test_get_task_returns_none_for_unknown_id(session):
    assert tm.get_task(session, "does-not-exist") is None


def test_update_task_status_appends_history_and_changes_status(session):
    task = tm.create_task(session, title="Refactor auth")
    updated = tm.update_task(session, task.id, status="in_progress")
    assert updated.status == "in_progress"
    notes = [h["note"] for h in updated.history_list]
    assert "Status changed: todo -> in_progress" in notes


def test_update_task_same_status_does_not_duplicate_history(session):
    task = tm.create_task(session, title="x")
    tm.update_task(session, task.id, status="todo")
    updated = tm.update_task(session, task.id, status="todo")
    assert len(updated.history_list) == 1  # only "Task created"


def test_update_task_rejects_invalid_status(session):
    task = tm.create_task(session, title="x")
    with pytest.raises(tm.InvalidTaskStatusError):
        tm.update_task(session, task.id, status="not_a_real_status")


def test_update_task_merges_files_without_duplicates(session):
    task = tm.create_task(session, title="x")
    tm.update_task(session, task.id, files=["a.py", "b.py"])
    updated = tm.update_task(session, task.id, files=["b.py", "c.py"])
    assert updated.files_list == ["a.py", "b.py", "c.py"]


def test_update_task_merges_models_used_without_duplicates(session):
    task = tm.create_task(session, title="x")
    tm.update_task(session, task.id, models_used=["qwen3-coder:30b"])
    updated = tm.update_task(session, task.id, models_used=["qwen3-coder:30b", "deepseek-r1:14b"])
    assert updated.models_used_list == ["qwen3-coder:30b", "deepseek-r1:14b"]


def test_update_task_records_test_results(session):
    task = tm.create_task(session, title="x")
    updated = tm.update_task(session, task.id, test_results={"status": "passed", "count": 12})
    assert updated.test_results_dict == {"status": "passed", "count": 12}


def test_update_task_returns_none_for_unknown_id(session):
    assert tm.update_task(session, "does-not-exist", status="done") is None


def test_delete_task(session):
    task = tm.create_task(session, title="x")
    assert tm.delete_task(session, task.id) is True
    assert tm.get_task(session, task.id) is None


def test_delete_task_unknown_id_returns_false(session):
    assert tm.delete_task(session, "does-not-exist") is False


def test_list_tasks_filters_by_status(session):
    tm.create_task(session, title="a")
    b = tm.create_task(session, title="b")
    tm.update_task(session, b.id, status="in_progress")

    assert [t.title for t in tm.list_tasks(session, status="todo")] == ["a"]
    assert [t.title for t in tm.list_tasks(session, status="in_progress")] == ["b"]


def test_list_tasks_rejects_invalid_status_filter(session):
    with pytest.raises(tm.InvalidTaskStatusError):
        tm.list_tasks(session, status="not_real")


def test_list_tasks_orders_most_recent_first(session):
    tm.create_task(session, title="first")
    tm.create_task(session, title="second")
    assert [t.title for t in tm.list_tasks(session)] == ["second", "first"]
