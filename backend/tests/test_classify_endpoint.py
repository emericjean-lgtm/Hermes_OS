from __future__ import annotations


def test_classify_falls_back_to_default_on_unparseable_reply(client):
    response = client.post("/classify", json={"request": "Summarize this document."})

    assert response.status_code == 200
    body = response.json()
    # fake Ollama client's canned reply ("Hello, world!") isn't a known
    # task type, so this exercises the fallback path — parse_task_type's
    # own valid-label handling is covered directly in
    # test_hermes_swift_agent.py.
    assert body["task_type"] == "conversation"
    assert body["model"]
    assert body["tier"]


def test_classify_with_custom_default(client):
    response = client.post(
        "/classify", json={"request": "Something ambiguous.", "default": "research"}
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "research"
