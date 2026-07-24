from __future__ import annotations

# Only the SQLite-backed endpoints (POST/GET/DELETE /memory) are exercised
# here. /memory/index and /memory/search go through EchoAgent's real
# OllamaEmbeddingFunction, which needs a live Ollama server this sandbox
# doesn't have — see test_semantic.py for ChromaDB-side coverage with a
# fake embedding function instead.


def test_create_and_list_memory(client):
    response = client.post(
        "/memory", json={"type": "preference", "content": "reply in French", "tags": ["locale"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "preference"
    assert body["content"] == "reply in French"
    assert body["tags"] == ["locale"]

    listed = client.get("/memory", params={"type": "preference"})
    assert listed.status_code == 200
    assert [e["content"] for e in listed.json()] == ["reply in French"]


def test_create_memory_deduplicates(client):
    first = client.post("/memory", json={"type": "preference", "content": "dark mode"})
    second = client.post("/memory", json={"type": "preference", "content": "dark mode"})
    assert first.json()["id"] == second.json()["id"]


def test_delete_memory(client):
    created = client.post("/memory", json={"type": "decision", "content": "use qwen3-coder"})
    memory_id = created.json()["id"]

    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": memory_id}

    listed = client.get("/memory", params={"type": "decision"})
    assert listed.json() == []


def test_delete_unknown_memory_returns_404(client):
    response = client.delete("/memory/does-not-exist")
    assert response.status_code == 404


def test_list_memory_without_type_returns_everything(client):
    client.post("/memory", json={"type": "preference", "content": "a"})
    client.post("/memory", json={"type": "decision", "content": "b"})
    response = client.get("/memory")
    assert {e["content"] for e in response.json()} == {"a", "b"}


def test_memory_scoped_to_project(client):
    created = client.post(
        "/memory", json={"type": "preference", "content": "a", "project_id": "proj-1"}
    )
    assert created.json()["project_id"] == "proj-1"
    client.post("/memory", json={"type": "preference", "content": "b", "project_id": "proj-2"})

    response = client.get("/memory", params={"project_id": "proj-1"})

    assert [e["content"] for e in response.json()] == ["a"]
