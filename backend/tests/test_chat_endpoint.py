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


def test_system_status_reports_gpu_and_hardware_telemetry(client):
    # The `client` fixture fakes run_command to always report "no GPU"
    # (this sandbox genuinely has none) and points disk_path at tmp_path.
    response = client.get("/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["gpu"] is None
    assert body["loaded_models"] == []
    assert body["alerts"] == []
    assert body["disk_total_gb"] > 0
    assert "ram_total_gb" in body
    assert "cpu_load_pct" in body
