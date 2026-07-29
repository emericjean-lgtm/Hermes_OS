"""Embedding Index for HOS-047 — abstraction over local embedding models."""

from __future__ import annotations

import hashlib
import threading
from typing import Callable, Optional


class EmbeddingIndex:
    """Abstract embedding index supporting Nomic Embed, BGE, E5, future models.

    Current implementation: lightweight hash-based embeddings for development.
    Production: pluggable with real embedding models via configure().
    """

    def __init__(self, dimension: int = 128, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._dimension = dimension
        self._embeddings: dict[str, list[float]] = {}  # entity_id → vector
        self._model_name = "hash-sim"

    def configure(self, model_name: str, dimension: int = 0) -> None:
        """Configure embedding model (future: Nomic, BGE, E5)."""
        self._model_name = model_name
        if dimension:
            self._dimension = dimension

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Uses deterministic hash-based embeddings for dev.
        Production: replace with real model inference.
        """
        h = hashlib.sha256(text.encode()).digest()
        vec = []
        for i in range(self._dimension):
            byte_val = h[i % len(h)]
            vec.append((byte_val / 255.0) * 2.0 - 1.0)  # [-1, 1]
        return vec

    def index(self, entity_id: str, text: str) -> list[float]:
        vec = self.embed(text)
        with self._lock:
            self._embeddings[entity_id] = vec
        return vec

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """Cosine similarity search. Returns (entity_id, score)."""
        query_vec = self.embed(query)
        results: list[tuple[str, float]] = []

        with self._lock:
            for eid, vec in self._embeddings.items():
                score = self._cosine_similarity(query_vec, vec)
                results.append((eid, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_embedding(self, entity_id: str) -> Optional[list[float]]:
        return self._embeddings.get(entity_id)

    def remove(self, entity_id: str) -> bool:
        with self._lock:
            return self._embeddings.pop(entity_id, None) is not None

    def count(self) -> int:
        return len(self._embeddings)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
