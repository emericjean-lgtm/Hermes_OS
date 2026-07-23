from __future__ import annotations


def test_chat_streams_response_and_exposes_routing_headers(client):
    response = client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 200
    assert response.text == "Hello, world!"
    assert response.headers["X-Hermes-Model"]
    assert response.headers["X-Hermes-Role"] == "standard"


def test_chat_rejects_unknown_agent(client):
    response = client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "agent": "does_not_exist"},
    )
    assert response.status_code == 400


def test_chat_rejects_unknown_task_type(client):
    response = client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "task_type": "not_real"},
    )
    assert response.status_code == 400


def test_system_status_lists_enabled_agents(client):
    response = client.get("/system/status")
    assert response.status_code == 200
    body = response.json()
    assert "hermes_prime" in body["enabled_agents"]
