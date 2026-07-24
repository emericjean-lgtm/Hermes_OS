from __future__ import annotations


def test_list_projects_empty_by_default(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_project(client):
    create_response = client.post(
        "/projects", json={"name": "Website Redesign", "tags": ["pro", "client-x"]}
    )
    assert create_response.status_code == 200
    body = create_response.json()
    assert body["name"] == "Website Redesign"
    assert body["status"] == "active"
    assert body["tags"] == ["pro", "client-x"]

    get_response = client.get(f"/projects/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


def test_list_projects_after_create(client):
    client.post("/projects", json={"name": "A"})
    client.post("/projects", json={"name": "B"})

    response = client.get("/projects")

    assert {p["name"] for p in response.json()} == {"A", "B"}


def test_list_projects_filters_by_status_and_tag(client):
    active = client.post("/projects", json={"name": "Active", "tags": ["perso"]}).json()
    archived = client.post("/projects", json={"name": "Archived", "tags": ["pro"]}).json()
    client.patch(f"/projects/{archived['id']}", json={"status": "archived"})

    by_status = client.get("/projects", params={"status": "active"}).json()
    assert [p["id"] for p in by_status] == [active["id"]]

    by_tag = client.get("/projects", params={"tag": "perso"}).json()
    assert [p["id"] for p in by_tag] == [active["id"]]


def test_list_projects_invalid_status_returns_400(client):
    response = client.get("/projects", params={"status": "not-a-status"})

    assert response.status_code == 400


def test_get_missing_project_returns_404(client):
    response = client.get("/projects/does-not-exist")

    assert response.status_code == 404


def test_update_project(client):
    created = client.post("/projects", json={"name": "Old"}).json()

    response = client.patch(f"/projects/{created['id']}", json={"name": "New", "status": "archived"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New"
    assert body["status"] == "archived"


def test_update_missing_project_returns_404(client):
    response = client.patch("/projects/does-not-exist", json={"name": "X"})

    assert response.status_code == 404


def test_update_project_invalid_status_returns_400(client):
    created = client.post("/projects", json={"name": "X"}).json()

    response = client.patch(f"/projects/{created['id']}", json={"status": "not-a-status"})

    assert response.status_code == 400


def test_delete_project(client):
    created = client.post("/projects", json={"name": "X"}).json()

    delete_response = client.delete(f"/projects/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": created["id"]}

    assert client.get(f"/projects/{created['id']}").status_code == 404


def test_delete_missing_project_returns_404(client):
    response = client.delete("/projects/does-not-exist")

    assert response.status_code == 404
