from __future__ import annotations

# Uses only deterministic tools (tasks_*) as node actions, so /workflows/*
# runs never touch Ollama — same reasoning as test_workflow_engine.py.

_WORKFLOW = {
    "id": "wf-1",
    "name": "Test Workflow",
    "nodes": [
        {"id": "create", "action": "tasks_create", "params": {"title": "hello"}},
        {"id": "list", "action": "tasks_list", "params": {}},
    ],
    "edges": [{"from": "create", "to": "list"}],
}


def test_list_workflows_empty_by_default(client):
    response = client.get("/workflows")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_workflow(client):
    create_response = client.post("/workflows", json=_WORKFLOW)
    assert create_response.status_code == 200
    assert create_response.json()["id"] == "wf-1"

    get_response = client.get("/workflows/wf-1")
    assert get_response.status_code == 200
    assert get_response.json()["nodes"][0]["action"] == "tasks_create"


def test_create_workflow_persists_across_list(client):
    client.post("/workflows", json=_WORKFLOW)

    response = client.get("/workflows")

    assert [w["id"] for w in response.json()] == ["wf-1"]


def test_create_invalid_workflow_returns_400(client):
    bad = dict(_WORKFLOW, edges=[{"from": "create", "to": "ghost"}])

    response = client.post("/workflows", json=bad)

    assert response.status_code == 400


def test_get_missing_workflow_returns_404(client):
    response = client.get("/workflows/does-not-exist")

    assert response.status_code == 404


def test_delete_workflow(client):
    client.post("/workflows", json=_WORKFLOW)

    delete_response = client.delete("/workflows/wf-1")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": "wf-1"}

    assert client.get("/workflows/wf-1").status_code == 404


def test_delete_missing_workflow_returns_404(client):
    response = client.delete("/workflows/does-not-exist")

    assert response.status_code == 404


def test_simulate_workflow(client):
    client.post("/workflows", json=_WORKFLOW)

    response = client.post("/workflows/wf-1/simulate")

    assert response.status_code == 200
    body = response.json()
    assert body["execution_order"] == ["create", "list"]
    assert body["human_validation_nodes"] == []


def test_simulate_missing_workflow_returns_404(client):
    response = client.post("/workflows/does-not-exist/simulate")

    assert response.status_code == 404


def test_run_workflow(client):
    client.post("/workflows", json=_WORKFLOW)

    response = client.post("/workflows/wf-1/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["node_results"]["create"]["status"] == "success"
    assert body["node_results"]["list"]["status"] == "success"


def test_create_workflow_with_project_id_and_filter_list(client):
    scoped = dict(_WORKFLOW, id="wf-scoped", project_id="proj-1")
    created = client.post("/workflows", json=scoped)
    assert created.json()["project_id"] == "proj-1"
    client.post("/workflows", json=dict(_WORKFLOW, id="wf-other", project_id="proj-2"))

    response = client.get("/workflows", params={"project_id": "proj-1"})

    assert [w["id"] for w in response.json()] == ["wf-scoped"]


def test_run_workflow_propagates_project_id(client):
    scoped = dict(_WORKFLOW, id="wf-scoped", project_id="proj-1")
    client.post("/workflows", json=scoped)

    response = client.post("/workflows/wf-scoped/run", json={})

    assert response.json()["project_id"] == "proj-1"


def test_run_workflow_halts_at_human_validation_gate(client):
    gated = dict(
        _WORKFLOW,
        id="wf-gated",
        nodes=[
            dict(_WORKFLOW["nodes"][0], human_validation=True),
            _WORKFLOW["nodes"][1],
        ],
    )
    client.post("/workflows", json=gated)

    response = client.post("/workflows/wf-gated/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_validation"
    assert body["pending_nodes"] == ["create"]

    approved_response = client.post(
        "/workflows/wf-gated/run", json={"approved_nodes": ["create"]}
    )
    assert approved_response.json()["status"] == "completed"


def test_run_missing_workflow_returns_404(client):
    response = client.post("/workflows/does-not-exist/run", json={})

    assert response.status_code == 404
