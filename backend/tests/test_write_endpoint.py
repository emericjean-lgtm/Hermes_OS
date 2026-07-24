from __future__ import annotations


def test_write_returns_document(client):
    response = client.post("/write", json={"brief": "Write a short changelog entry."})

    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "Hello, world!"  # fake Ollama client's canned response
    assert body["model"]
    assert body["tier"]


def test_write_with_format_tone_and_context(client):
    response = client.post(
        "/write",
        json={
            "brief": "Summarize the release.",
            "format": "plain text",
            "tone": "casual",
            "context": "v0.5.0 adds Hermes Scribe.",
        },
    )

    assert response.status_code == 200
    assert response.json()["document"] == "Hello, world!"
