from __future__ import annotations

_FAKE_IMAGE = "aGVsbG8="


def test_vision_analyze_returns_description(client):
    response = client.post("/vision/analyze", json={"images": [_FAKE_IMAGE]})

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Hello, world!"  # fake Ollama client's canned response
    assert body["model"]
    assert body["tier"]


def test_vision_analyze_with_prompt_and_context(client):
    response = client.post(
        "/vision/analyze",
        json={"images": [_FAKE_IMAGE], "prompt": "What error is shown?", "context": "A crash dialog."},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Hello, world!"


def test_vision_analyze_rejects_empty_images(client):
    response = client.post("/vision/analyze", json={"images": []})

    assert response.status_code == 422
