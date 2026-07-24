from __future__ import annotations


def test_messages_empty_by_default(client):
    response = client.get("/messages")

    assert response.status_code == 200
    assert response.json() == []


def test_messages_reflects_security_evaluate_calls(client):
    eval_response = client.post(
        "/security/evaluate",
        json={
            "action_type": "network_call",
            "description": "ping",
            "requesting_agent": "atlas",
            "task_id": "t1",
        },
    )
    assert eval_response.status_code == 200

    response = client.get("/messages", params={"task_id": "t1"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    types = {m["type"] for m in body}
    assert "VALIDATION_REQUEST" in types
    assert types & {"VALIDATION_GRANTED", "VALIDATION_DENIED", "ESCALATION"}
    for m in body:
        assert m["task_id"] == "t1"
        assert "atlas" in (m["from"], m["to"])


def test_messages_filters_by_agent(client):
    client.post(
        "/security/evaluate",
        json={"action_type": "file_read", "description": "x", "requesting_agent": "scout"},
    )

    response = client.get("/messages", params={"agent": "scout"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all("scout" in (m["from"], m["to"]) for m in body)


def test_messages_filters_by_project_id(client):
    client.post(
        "/security/evaluate",
        json={
            "action_type": "network_call",
            "description": "ping",
            "requesting_agent": "atlas",
            "project_id": "proj-1",
        },
    )
    client.post(
        "/security/evaluate",
        json={
            "action_type": "network_call",
            "description": "ping",
            "requesting_agent": "atlas",
            "project_id": "proj-2",
        },
    )

    response = client.get("/messages", params={"project_id": "proj-1"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(m["project_id"] == "proj-1" for m in body)
