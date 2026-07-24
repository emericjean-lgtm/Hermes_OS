from __future__ import annotations

import pytest

from backend.workflows import loader
from backend.workflows.schema import WorkflowDefinition


@pytest.fixture
def isolated_workflows_dir(monkeypatch, tmp_path):
    from backend.core.config import get_settings

    monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path / "workflows"))
    get_settings.cache_clear()
    try:
        yield tmp_path / "workflows"
    finally:
        get_settings.cache_clear()


def _workflow(workflow_id: str = "wf-1") -> WorkflowDefinition:
    return WorkflowDefinition.from_dict(
        {"id": workflow_id, "name": "X", "nodes": [{"id": "a", "action": "tasks_list"}]}
    )


def test_list_workflow_ids_empty_when_no_dir_yet(isolated_workflows_dir):
    assert loader.list_workflow_ids() == []


def test_save_then_load_round_trips(isolated_workflows_dir):
    loader.save_workflow(_workflow())

    loaded = loader.load_workflow("wf-1")

    assert loaded.id == "wf-1"
    assert loaded.nodes[0].action == "tasks_list"


def test_load_missing_workflow_raises_file_not_found(isolated_workflows_dir):
    with pytest.raises(FileNotFoundError):
        loader.load_workflow("does-not-exist")


def test_list_workflow_ids_sorted(isolated_workflows_dir):
    loader.save_workflow(_workflow("b-flow"))
    loader.save_workflow(_workflow("a-flow"))

    assert loader.list_workflow_ids() == ["a-flow", "b-flow"]


def test_list_workflows_returns_loaded_definitions(isolated_workflows_dir):
    loader.save_workflow(_workflow("wf-1"))
    loader.save_workflow(_workflow("wf-2"))

    workflows = loader.list_workflows()

    assert sorted(w.id for w in workflows) == ["wf-1", "wf-2"]


def test_delete_workflow_returns_true_when_existed(isolated_workflows_dir):
    loader.save_workflow(_workflow())

    assert loader.delete_workflow("wf-1") is True
    assert loader.list_workflow_ids() == []


def test_delete_workflow_returns_false_when_missing(isolated_workflows_dir):
    assert loader.delete_workflow("does-not-exist") is False


def test_save_overwrites_existing_workflow(isolated_workflows_dir):
    loader.save_workflow(_workflow())
    updated = WorkflowDefinition.from_dict(
        {"id": "wf-1", "name": "Renamed", "nodes": [{"id": "a", "action": "tasks_list"}]}
    )

    loader.save_workflow(updated)

    assert loader.load_workflow("wf-1").name == "Renamed"


def test_save_and_load_round_trips_project_id(isolated_workflows_dir):
    workflow = WorkflowDefinition.from_dict(
        {
            "id": "wf-1",
            "name": "X",
            "nodes": [{"id": "a", "action": "tasks_list"}],
            "project_id": "proj-1",
        }
    )

    loader.save_workflow(workflow)

    assert loader.load_workflow("wf-1").project_id == "proj-1"


def test_list_workflows_filters_by_project_id(isolated_workflows_dir):
    loader.save_workflow(
        WorkflowDefinition.from_dict(
            {
                "id": "wf-1",
                "name": "X",
                "nodes": [{"id": "a", "action": "tasks_list"}],
                "project_id": "proj-1",
            }
        )
    )
    loader.save_workflow(
        WorkflowDefinition.from_dict(
            {
                "id": "wf-2",
                "name": "Y",
                "nodes": [{"id": "a", "action": "tasks_list"}],
                "project_id": "proj-2",
            }
        )
    )

    filtered = loader.list_workflows(project_id="proj-1")

    assert [w.id for w in filtered] == ["wf-1"]
