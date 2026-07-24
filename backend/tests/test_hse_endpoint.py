from __future__ import annotations


def test_process_task_extracts_skill_on_done(client):
    task = client.post("/tasks", json={"title": "Ship it"}).json()
    client.patch(f"/tasks/{task['id']}", json={"status": "done"})

    response = client.post(f"/hse/process/{task['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] is True
    assert body["skill_id"] is not None

    skill = client.get(f"/skills/{body['skill_id']}").json()
    assert skill["name"] == "Ship it"
    assert skill["source_task_id"] == task["id"]
    assert skill["status"] == "in_review"


def test_process_task_no_skill_on_cancelled(client):
    task = client.post("/tasks", json={"title": "Abandoned"}).json()
    client.patch(f"/tasks/{task['id']}", json={"status": "cancelled"})

    response = client.post(f"/hse/process/{task['id']}")
    body = response.json()
    assert body["outcome"] is False
    assert body["skill_id"] is None


def test_process_task_noop_for_non_terminal_task(client):
    task = client.post("/tasks", json={"title": "Still going"}).json()

    response = client.post(f"/hse/process/{task['id']}")
    body = response.json()
    assert body["outcome"] is None
    assert body["skill_id"] is None


def test_process_unknown_task_returns_404(client):
    response = client.post("/hse/process/does-not-exist")
    assert response.status_code == 404


def test_progression_reflects_task_and_skill_state(client):
    done = client.post("/tasks", json={"title": "a"}).json()
    client.patch(f"/tasks/{done['id']}", json={"status": "done"})
    client.post(f"/hse/process/{done['id']}")

    cancelled = client.post("/tasks", json={"title": "b"}).json()
    client.patch(f"/tasks/{cancelled['id']}", json={"status": "cancelled"})
    client.post(f"/hse/process/{cancelled['id']}")

    response = client.get("/hse/progression")
    assert response.status_code == 200
    body = response.json()
    assert body["tasks_terminal"] == 2
    assert body["tasks_succeeded"] == 1
    assert body["success_rate"] == 0.5
    assert body["skills_total"] == 1


def test_progression_scoped_to_project(client):
    task_a = client.post("/tasks", json={"title": "a", "project_id": "proj-1"}).json()
    client.patch(f"/tasks/{task_a['id']}", json={"status": "done"})
    client.post(f"/hse/process/{task_a['id']}")

    task_b = client.post("/tasks", json={"title": "b", "project_id": "proj-2"}).json()
    client.patch(f"/tasks/{task_b['id']}", json={"status": "done"})
    client.post(f"/hse/process/{task_b['id']}")

    response = client.get("/hse/progression", params={"project_id": "proj-1"})
    body = response.json()
    assert body["tasks_terminal"] == 1
    assert body["skills_total"] == 1
