"""The embedding path must pin its own context (HOS-093).

Raising Ollama's process-wide OLLAMA_CONTEXT_LENGTH to 65536 — necessary so
Hermes Agent's tool schemas stop being truncated (HOS-090/091) — applies to
*every* model, including the one that embeds 512-word RAG chunks. Measured
consequence on this deployment:

    no num_ctx sent : ctx 32768, 5.88 GB VRAM, 57.5s per call  (0.64 GB model)
    num_ctx 2048    : ctx  2048, 2.23 GB VRAM,  2.4s per call

Document indexing timed out and the suite went red. config/models.yaml had
specified 2048 for the embedding role all along; the value was simply never
forwarded to Ollama.

Unlike the chat path, this one is fixable per request: /api/embeddings
honours `options`, whereas the OpenAI-compatible /v1 endpoint carries no
num_ctx at all.
"""
from __future__ import annotations

import httpx
import pytest

from backend.memory.semantic import OllamaEmbeddingFunction


def _capturing_client(captured: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    return httpx.MockTransport(handler)


@pytest.fixture
def captured(monkeypatch):
    seen: list[dict] = []
    original = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = _capturing_client(seen)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)
    return seen


def test_configured_context_is_sent(captured):
    fn = OllamaEmbeddingFunction("http://localhost:11434", "qwen3-embedding:0.6b", num_ctx=2048)

    fn(["some chunk of text"])

    assert captured[0]["options"]["num_ctx"] == 2048, (
        "without this the embedding model inherits Ollama's chat-sized "
        "default: 5.88 GB of VRAM and 57s per call, measured"
    )


def test_context_is_sent_for_every_chunk(captured):
    """Indexing embeds many chunks in one call; a per-request option that
    only lands on the first would leave the rest on the global default."""
    fn = OllamaEmbeddingFunction("http://localhost:11434", "m", num_ctx=2048)

    fn(["chunk one", "chunk two", "chunk three"])

    assert len(captured) == 3
    assert all(payload["options"]["num_ctx"] == 2048 for payload in captured)


def test_keep_alive_survives_the_change(captured):
    """The embedding role is always_loaded; pinning context must not have
    cost it its VRAM residency."""
    fn = OllamaEmbeddingFunction("http://localhost:11434", "m", keep_alive=-1, num_ctx=2048)

    fn(["text"])

    assert captured[0]["keep_alive"] == -1


def test_unset_context_sends_no_options(captured):
    """Callers that deliberately want Ollama's default must still get it —
    an empty options block would pin num_ctx to 0."""
    fn = OllamaEmbeddingFunction("http://localhost:11434", "m")

    fn(["text"])

    assert "options" not in captured[0]


def test_role_config_reaches_the_embedding_function():
    """config/models.yaml has said 2048 since HOS-079; the regression was
    that nothing forwarded it."""
    from backend.core.config import load_models_config

    role = load_models_config()["roles"]["embedding"]

    assert role.get("num_ctx"), "the embedding role must declare its own context"
    fn = OllamaEmbeddingFunction("http://x", role["model"], num_ctx=role.get("num_ctx"))
    assert fn._num_ctx == role["num_ctx"]  # noqa: SLF001
