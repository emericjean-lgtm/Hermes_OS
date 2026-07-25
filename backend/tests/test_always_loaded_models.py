"""§22 — models flagged `always_loaded` must be pinned in VRAM.

Regression guard for a real conformance gap: config/models.yaml described
swift and embedding as "Kept loaded at all times", but nothing enforced
it. OllamaClient sent one global keep_alive for every model, and the
embedding path (OllamaEmbeddingFunction, which bypasses OllamaClient by
design) sent no keep_alive at all — so both models were evicted on idle
and every later classification/RAG call paid a cold reload.
"""
from __future__ import annotations

import httpx
import pytest

from backend.connectors.ollama_client import OllamaClient
from backend.core.agent_registry import always_loaded_models
from backend.core.config import load_models_config
from backend.memory.semantic import OllamaEmbeddingFunction


def test_shipped_config_flags_swift_and_embedding():
    """The flag is only meaningful if the shipped config actually sets it."""
    roles = load_models_config()["roles"]
    assert roles["swift"]["always_loaded"] is True
    assert roles["embedding"]["always_loaded"] is True


def test_always_loaded_models_returns_tags_not_role_names():
    tags = always_loaded_models(
        {
            "roles": {
                "swift": {"model": "qwen3:1.7b", "always_loaded": True},
                "embedding": {"model": "nomic-embed-text", "always_loaded": True},
                "code": {"model": "qwen3-coder:30b"},
                "double_check": {"model": "qwen3:4b", "always_loaded": False},
            }
        }
    )
    assert tags == {"qwen3:1.7b", "nomic-embed-text"}


def test_always_loaded_models_on_empty_config():
    assert always_loaded_models({}) == set()


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("qwen3:1.7b", -1),  # pinned
        ("qwen3-coder:30b", "10m"),  # ordinary expiry
    ],
)
def test_keep_alive_per_model(model, expected):
    client = OllamaClient(
        "http://localhost:11434",
        keep_alive="10m",
        always_loaded_models={"qwen3:1.7b"},
    )
    assert client._keep_alive_for(model) == expected


def test_chat_stream_sends_the_pinned_keep_alive():
    """The value has to reach the wire, not just the helper."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.update(json.loads(request.read()))
        return httpx.Response(200, text='{"message":{"content":"hi"},"done":true}\n')

    client = OllamaClient(
        "http://localhost:11434", keep_alive="10m", always_loaded_models={"qwen3:1.7b"}
    )
    client._client = httpx.AsyncClient(
        base_url="http://localhost:11434", transport=httpx.MockTransport(handler)
    )

    import asyncio

    async def drain():
        async for _ in client.chat_stream("qwen3:1.7b", [{"role": "user", "content": "x"}]):
            pass

    asyncio.run(drain())
    assert sent["keep_alive"] == -1


def test_embedding_function_sends_keep_alive():
    """This path bypasses OllamaClient, so it needs its own guard."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.update(json.loads(request.read()))
        return httpx.Response(200, json={"embedding": [0.1, 0.2]})

    fn = OllamaEmbeddingFunction("http://localhost:11434", "nomic-embed-text")
    original = httpx.Client

    class PatchedClient(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    httpx.Client = PatchedClient
    try:
        vectors = fn(["some text"])
    finally:
        httpx.Client = original

    # ChromaDB's Embeddings are numpy arrays, so compare element-wise
    # rather than with `==` on the nested list (ambiguous truth value).
    assert len(vectors) == 1
    assert list(vectors[0]) == pytest.approx([0.1, 0.2])
    assert sent["keep_alive"] == -1
    assert sent["model"] == "nomic-embed-text"
