"""Documentary / semantic memory — cahier des charges §11.3, §24.3.

ChromaDB's embedding-function protocol is synchronous, while the rest of
this app's Ollama client is async (backend/connectors/ollama_client.py).
Rather than bridge async into a sync callback, OllamaEmbeddingFunction
makes its own small synchronous HTTP calls — it is the one deliberate
exception to "always go through OllamaClient".
"""
from __future__ import annotations

import httpx
from chromadb import EmbeddingFunction, EphemeralClient, PersistentClient
from chromadb.api.types import Documents, Embeddings


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """Calls Ollama's /api/embeddings synchronously — used as ChromaDB's
    embedding function, per config/models.yaml's `embedding` role
    (qwen3-embedding:0.6b as of HOS-079). Must actually subclass
    chromadb.EmbeddingFunction (not just duck-type __call__/name) to pick
    up its default embed_query() implementation, which ChromaDB's query
    path requires."""

    def __init__(
        self, base_url: str, model: str, timeout: float = 60.0, keep_alive: object = -1,
        num_ctx: int | None = None,
    ) -> None:
        """`keep_alive` is forwarded to /api/embeddings; -1 means "hold in
        VRAM indefinitely". Defaults to -1 because config/models.yaml marks
        the embedding role `always_loaded`. This path previously sent no
        keep_alive at all, so nomic-embed-text fell back to Ollama's own
        short default and was evicted between indexing runs — every later
        RAG query then paid a cold reload (§22).

        `num_ctx` must be sent explicitly (HOS-093). Sending nothing lets
        Ollama apply its process-wide OLLAMA_CONTEXT_LENGTH, which is sized
        for agentic chat, not for embedding a 512-word chunk. Measured when
        that default was raised to 65536: this 0.64 GB model was loaded with
        32768 context and occupied **5.88 GB of VRAM** — nine times its
        weights — and a single embedding call took 57 seconds, timing out
        document indexing. config/models.yaml has always said 2048; it was
        simply never forwarded."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 - chromadb's protocol name
        vectors: Embeddings = []
        with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
            payload: dict = {
                "model": self._model,
                "keep_alive": self._keep_alive,
            }
            if self._num_ctx:
                # /api/embeddings honours options, unlike the OpenAI-compatible
                # /v1 endpoint the chat path uses — so here the context really
                # can be pinned per request.
                payload["options"] = {"num_ctx": self._num_ctx}
            for text in input:
                response = client.post(
                    "/api/embeddings",
                    json={**payload, "prompt": text},
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
        return vectors

    @staticmethod
    def name() -> str:  # required by chromadb's EmbeddingFunction protocol; must be static
        return "hermes_ollama_httpx"

    def get_config(self) -> dict:
        return {"base_url": self._base_url, "model": self._model, "timeout": self._timeout}

    @staticmethod
    def build_from_config(config: dict) -> "OllamaEmbeddingFunction":
        return OllamaEmbeddingFunction(
            base_url=config["base_url"], model=config["model"],
            timeout=config.get("timeout", 60.0), num_ctx=config.get("num_ctx"),
        )


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Word-based approximation of the 512-token / 64-token-overlap
    chunking described in §11.3. Counting real model tokens would need a
    tokenizer dependency; splitting on whitespace-delimited words is a
    close, dependency-free stand-in."""
    words = text.split()
    if not words:
        return []
    step = max(chunk_size - overlap, 1)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
        start += step
    return chunks


class DocumentStore:
    def __init__(
        self,
        embedding_function: OllamaEmbeddingFunction,
        *,
        persist_directory: str | None = None,
        collection_name: str = "documents",
        metadata: dict | None = None,
    ) -> None:
        self._client = (
            PersistentClient(path=persist_directory) if persist_directory else EphemeralClient()
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=embedding_function, metadata=metadata
        )

    def add_document(self, doc_id: str, text: str, metadata: dict) -> None:
        self._collection.add(ids=[doc_id], documents=[text], metadatas=[metadata])

    def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        result = self._collection.query(query_texts=[query], n_results=n_results, where=where)
        ids = result.get("ids") or [[]]
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        return [
            {"id": i, "content": d, "metadata": m or {}, "distance": dist}
            for i, d, m, dist in zip(
                ids[0], documents[0], metadatas[0], distances[0] or [None] * len(ids[0])
            )
        ]
