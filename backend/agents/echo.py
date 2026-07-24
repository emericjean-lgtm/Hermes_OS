"""Echo — memory & skills agent (cahier des charges §9.1, §11, §20).

Always-on. Like Aegis, Echo does not subclass BaseAgent: its contract is
remember()/list_memories()/forget()/index_document()/recall() plus the
skill-library methods below, not chat completions. It wraps the SQLite
long-term store (episodic.py), the ChromaDB documentary store
(semantic.py), and the SQLite skill library (skill_library.py) — HSE's
skill_extractor/pipeline (backend/self_evolution/) persist through Echo
rather than skill_library directly, the same "Echo owns the memory
tables, other modules go through it" split remember()/list_memories()
already establish.
"""
from __future__ import annotations

from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings
from backend.core.router import ModelRouter
from backend.memory import episodic, skill_library
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.memory.episodic import MemoryEntry
from backend.memory.semantic import DocumentStore, OllamaEmbeddingFunction, chunk_text
from backend.memory.skill_library import Skill


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
        project_id: str | None = None,
    ) -> MemoryEntry:
        with self._session_factory() as session:
            return episodic.add_memory(
                session,
                type_=type_,
                content=content,
                tags=tags,
                confidence=confidence,
                project_id=project_id,
            )

    def list_memories(
        self, *, type_: str | None = None, project_id: str | None = None
    ) -> list[MemoryEntry]:
        with self._session_factory() as session:
            return episodic.list_memories(session, type_=type_, project_id=project_id)

    def forget(self, memory_id: str) -> bool:
        with self._session_factory() as session:
            return episodic.delete_memory(session, memory_id)

    # ── Documentary memory (ChromaDB) ──────────────────────────────
    def index_document(
        self, doc_id_prefix: str, text: str, metadata: dict, *, project_id: str | None = None
    ) -> int:
        chunks = chunk_text(text)
        full_metadata = {**metadata, "project_id": project_id} if project_id else metadata
        for i, chunk in enumerate(chunks):
            self._documents.add_document(f"{doc_id_prefix}-{i}", chunk, {**full_metadata, "chunk": i})
        return len(chunks)

    def recall(self, query: str, n_results: int = 5, *, project_id: str | None = None) -> list[dict]:
        where = {"project_id": project_id} if project_id else None
        return self._documents.search(query, n_results=n_results, where=where)

    # ── Skill library (SQLite) — HSE, §20 ──────────────────────────
    def remember_skill(
        self,
        *,
        name: str,
        description: str = "",
        procedure: str = "",
        confidence: float,
        tags: list[str] | None = None,
        project_id: str | None = None,
        source_task_id: str | None = None,
    ) -> Skill:
        with self._session_factory() as session:
            return skill_library.create_skill(
                session,
                name=name,
                description=description,
                procedure=procedure,
                confidence=confidence,
                tags=tags,
                project_id=project_id,
                source_task_id=source_task_id,
            )

    def get_skill(self, skill_id: str) -> Skill | None:
        with self._session_factory() as session:
            return skill_library.get_skill(session, skill_id)

    def list_skills(self, *, project_id: str | None = None, tag: str | None = None) -> list[Skill]:
        with self._session_factory() as session:
            return skill_library.list_skills(session, project_id=project_id, tag=tag)

    def use_skill(self, skill_id: str, *, success: bool) -> Skill | None:
        with self._session_factory() as session:
            return skill_library.record_use(session, skill_id, success=success)

    def forget_skill(self, skill_id: str) -> bool:
        with self._session_factory() as session:
            return skill_library.delete_skill(session, skill_id)

    def decay_skills(self) -> int:
        """No-op (returns 0) unless .env's EBBINGHAUS_DECAY_ENABLED is
        set — meant to be called periodically, not per-request (see
        skill_library.apply_decay's docstring)."""
        if not get_settings().ebbinghaus_decay_enabled:
            return 0
        with self._session_factory() as session:
            return skill_library.apply_decay(session)
