"""Echo — memory & skills agent (cahier des charges §9.1, §11).

Always-on. Like Aegis, Echo does not subclass BaseAgent: its contract is
remember()/list_memories()/forget()/index_document()/recall(), not chat
completions. It wraps the SQLite long-term store (episodic.py) and the
ChromaDB documentary store (semantic.py).
"""
from __future__ import annotations

from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings
from backend.core.router import ModelRouter
from backend.memory import episodic
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.memory.episodic import MemoryEntry
from backend.memory.semantic import DocumentStore, OllamaEmbeddingFunction, chunk_text


class EchoAgent:
    name: ClassVar[str] = "echo"

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
    ) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config

        settings = get_settings()

        engine = make_engine(settings.sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)

        embedding_model = models_config["roles"]["embedding"]["model"]
        embedding_fn = OllamaEmbeddingFunction(settings.ollama_api_url, embedding_model)
        self._documents = DocumentStore(embedding_fn, persist_directory=settings.chroma_path)

    # ── Long-term memory (SQLite) ──────────────────────────────────
    def remember(
        self,
        *,
        type_: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 1.0,
    ) -> MemoryEntry:
        with self._session_factory() as session:
            return episodic.add_memory(
                session, type_=type_, content=content, tags=tags, confidence=confidence
            )

    def list_memories(self, *, type_: str | None = None) -> list[MemoryEntry]:
        with self._session_factory() as session:
            return episodic.list_memories(session, type_=type_)

    def forget(self, memory_id: str) -> bool:
        with self._session_factory() as session:
            return episodic.delete_memory(session, memory_id)

    # ── Documentary memory (ChromaDB) ──────────────────────────────
    def index_document(self, doc_id_prefix: str, text: str, metadata: dict) -> int:
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            self._documents.add_document(f"{doc_id_prefix}-{i}", chunk, {**metadata, "chunk": i})
        return len(chunks)

    def recall(self, query: str, n_results: int = 5) -> list[dict]:
        return self._documents.search(query, n_results=n_results)
