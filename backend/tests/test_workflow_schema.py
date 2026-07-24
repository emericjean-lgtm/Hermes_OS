from __future__ import annotations

import pytest

from backend.workflows.schema import InvalidWorkflowError, WorkflowDefinition


def _base_dict(**overrides) -> dict:
    data = {
        "id": "wf-1",
        "name": "Test Workflow",
        "nodes": [
            {"id": "a", "action": "tasks_create", "params": {"title": "x"}},
            {"id": "b", "action": "tasks_list"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    data.update(overrides)
    return data


def test_from_dict_round_trips_through_to_dict():
    workflow = WorkflowDefinition.from_dict(_base_dict())

    assert workflow.id == "wf-1"
    assert workflow.name == "Test Workflow"
    assert [n.id for n in workflow.nodes] == ["a", "b"]
    assert workflow.edges[0].from_node == "a"
    assert workflow.edges[0].to_node == "b"
    assert workflow.edges[0].condition == "always"

    data = workflow.to_dict()
    assert data == {
        "id": "wf-1",
        "name": "Test Workflow",
        "description": "",
        "nodes": [
            {"id": "a", "action": "tasks_create", "params": {"title": "x"}, "human_validation": False},
            {"id": "b", "action": "tasks_list", "params": {}, "human_validation": False},
        ],
        "edges": [{"from": "a", "to": "b", "condition": "always"}],
    }


def test_from_dict_defaults_name_to_id_when_missing():
    workflow = WorkflowDefinition.from_dict(
        {"id": "wf-2", "nodes": [{"id": "a", "action": "tasks_list"}]}
    )

    assert workflow.name == "wf-2"


def test_from_dict_missing_required_field_raises_invalid_workflow_error():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict({"id": "wf-3", "nodes": [{"action": "tasks_list"}]})


def test_no_nodes_is_invalid():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict({"id": "wf-4", "name": "x", "nodes": []})


def test_duplicate_node_ids_is_invalid():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict(
            _base_dict(
                nodes=[
                    {"id": "a", "action": "tasks_list"},
                    {"id": "a", "action": "tasks_list"},
                ],
                edges=[],
            )
        )


def test_edge_referencing_unknown_node_is_invalid():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict(_base_dict(edges=[{"from": "a", "to": "ghost"}]))


def test_edge_with_unknown_condition_is_invalid():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict(_base_dict(edges=[{"from": "a", "to": "b", "condition": "maybe"}]))


def test_cycle_is_invalid():
    with pytest.raises(InvalidWorkflowError):
        WorkflowDefinition.from_dict(
            _base_dict(edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}])
        )


def test_node_and_edge_lookup_helpers():
    workflow = WorkflowDefinition.from_dict(_base_dict())

    assert workflow.node("a").action == "tasks_create"
    with pytest.raises(InvalidWorkflowError):
        workflow.node("ghost")

    assert [e.to_node for e in workflow.outgoing_edges("a")] == ["b"]
    assert [e.from_node for e in workflow.incoming_edges("b")] == ["a"]
