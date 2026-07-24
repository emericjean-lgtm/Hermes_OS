from __future__ import annotations


def test_create_and_get_task(client):
    created = client.post("/tasks", json={"title": "Refactor auth", "priority": "high", "agent": "atlas"})
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "Refactor auth"
    assert body["status"] == "todo"
    assert body["priority"] == "high"

    fetched = client.get(f"/tasks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Refactor auth"


def test_create_task_rejects_invalid_priority(client):
    response = client.post("/tasks", json={"title": "x", "priority": "urgentissime"})
    assert response.status_code == 400


def test_get_unknown_task_returns_404(client):
    response = client.get("/tasks/does-not-exist")
    assert response.status_code == 404


def test_update_task_status(client):
    created = client.post("/tasks", json={"title": "x"})
    task_id = created.json()["id"]

    updated = client.patch(f"/tasks/{task_id}", json={"status": "in_progress", "note": "started"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "in_progress"
    assert any(h["note"] == "started" for h in body["history"])


def test_update_task_rejects_invalid_status(client):
    created = client.post("/tasks", json={"title": "x"})
    task_id = created.json()["id"]
    response = client.patch(f"/tasks/{task_id}", json={"status": "not_real"})
    assert response.status_code == 400


def test_update_unknown_task_returns_404(client):
    response = client.patch("/tasks/does-not-exist", json={"status": "done"})
    assert response.status_code == 404


def test_delete_task(client):
    created = client.post("/tasks", json={"title": "x"})
    task_id = created.json()["id"]

    deleted = client.delete(f"/tasks/{task_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": task_id}

    assert client.get(f"/tasks/{task_id}").status_code == 404


def test_delete_unknown_task_returns_404(client):
    assert client.delete("/tasks/does-not-exist").status_code == 404


def test_list_tasks_filters_by_status(client):
    client.post("/tasks", json={"title": "a"})
    b = client.post("/tasks", json={"title": "b"}).json()
    client.patch(f"/tasks/{b['id']}", json={"status": "blocked"})

    todo = client.get("/tasks", params={"status": "todo"})
    blocked = client.get("/tasks", params={"status": "blocked"})
    assert [t["title"] for t in todo.json()] == ["a"]
    assert [t["title"] for t in blocked.json()] == ["b"]


def test_list_tasks_rejects_invalid_status_filter(client):
    response = client.get("/tasks", params={"status": "not_real"})
    assert response.status_code == 400


def test_create_and_filter_task_by_project_id(client):
    created = client.post("/tasks", json={"title": "a", "project_id": "proj-1"})
    assert created.json()["project_id"] == "proj-1"
    client.post("/tasks", json={"title": "b", "project_id": "proj-2"})

    response = client.get("/tasks", params={"project_id": "proj-1"})

    assert [t["title"] for t in response.json()] == ["a"]


def test_update_task_reassigns_project_id(client):
    created = client.post("/tasks", json={"title": "x", "project_id": "proj-1"})
    task_id = created.json()["id"]

    updated = client.patch(f"/tasks/{task_id}", json={"project_id": "proj-2"})

    assert updated.json()["project_id"] == "proj-2"


def test_update_task_run_hse_extracts_skill_on_done(client):
    created = client.post("/tasks", json={"title": "Ship it"}).json()
    task_id = created["id"]

    updated = client.patch(f"/tasks/{task_id}", json={"status": "done", "run_hse": True})
    assert updated.status_code == 200
    body = updated.json()
    assert body["hse"]["outcome"] is True
    assert body["hse"]["skill_id"] is not None

    skill = client.get(f"/skills/{body['hse']['skill_id']}").json()
    assert skill["name"] == "Ship it"


def test_update_task_without_run_hse_leaves_hse_null(client):
    created = client.post("/tasks", json={"title": "Ship it"}).json()
    updated = client.patch(f"/tasks/{created['id']}", json={"status": "done"})
    assert updated.json()["hse"] is None
    assert client.get("/skills").json() == []


def test_update_task_run_hse_is_noop_for_non_terminal_status(client):
    created = client.post("/tasks", json={"title": "x"}).json()
    updated = client.patch(f"/tasks/{created['id']}", json={"status": "in_progress", "run_hse": True})
    body = updated.json()
    assert body["hse"]["outcome"] is None
    assert body["hse"]["skill_id"] is None
