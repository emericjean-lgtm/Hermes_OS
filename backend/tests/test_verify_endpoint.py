from __future__ import annotations


def test_verify_returns_parsed_verdict(client):
    response = client.post(
        "/verify",
        json={"output": "def add(a, b): return a - b", "context": "addition function"},
    )

    assert response.status_code == 200
    body = response.json()
    # fake Ollama client's canned reply ("Hello, world!") doesn't follow
    # the VERDICT/ISSUES/CORRECTIONS format, so parsing degrades to
    # "unknown" rather than a false "approved" — this is the wiring test,
    # parse_verdict's own format-handling is covered directly in
    # test_veritas_agent.py.
    assert body["verdict"] == "unknown"
    assert body["issues"] == []
    assert body["raw"] == "Hello, world!"
    assert body["model"]
    assert body["tier"]


def test_verify_without_criteria_or_context(client):
    response = client.post("/verify", json={"output": "some output"})

    assert response.status_code == 200
    assert response.json()["raw"] == "Hello, world!"
