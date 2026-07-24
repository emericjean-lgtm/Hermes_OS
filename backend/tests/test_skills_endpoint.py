from __future__ import annotations

# No POST /skills exists on purpose (see backend/api/routes/skills.py) —
# skills are only created by the HSE pipeline, so every test here seeds
# through POST /tasks -> PATCH status=done -> POST /hse/process/{id},
# same as test_hse_endpoint.py.


def _make_skill(client, *, title="Deploy", project_id=None) -> dict:
    payload = {"title": title}
    if project_id is not None:
        payload["project_id"] = project_id
    task = client.post("/tasks", json=payload).json()
    client.patch(f"/tasks/{task['id']}", json={"status": "done"})
    processed = client.post(f"/hse/process/{task['id']}").json()
    return client.get(f"/skills/{processed['skill_id']}").json()


def test_list_skills_empty_by_default(client):
    response = client.get("/skills")
    assert response.status_code == 200
    assert response.json() == []


def test_get_skill_404_for_unknown_id(client):
    response = client.get("/skills/does-not-exist")
    assert response.status_code == 404


def test_use_skill_404_for_unknown_id(client):
    response = client.post("/skills/does-not-exist/use", json={"success": True})
    assert response.status_code == 404


def test_delete_skill_404_for_unknown_id(client):
    response = client.delete("/skills/does-not-exist")
    assert response.status_code == 404


def test_skill_lifecycle(client):
    skill = _make_skill(client)

    listed = client.get("/skills").json()
    assert [s["name"] for s in listed] == ["Deploy"]
    assert listed[0]["status"] == "in_review"

    used = client.post(f"/skills/{skill['id']}/use", json={"success": True}).json()
    assert used["confidence"] > skill["confidence"]
    assert used["uses"] == 1

    deleted = client.delete(f"/skills/{skill['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/skills/{skill['id']}").status_code == 404


def test_list_skills_filters_by_project_id(client):
    _make_skill(client, title="A", project_id="proj-1")
    _make_skill(client, title="B", project_id="proj-2")

    response = client.get("/skills", params={"project_id": "proj-1"})
    assert [s["name"] for s in response.json()] == ["A"]
