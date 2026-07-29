"""Memory Manager — central orchestrator for HOS-047.

All other Hermes layers access memory through this single facade.
Coordinates working, episodic, semantic, procedural, document memory,
knowledge graph, embeddings, retrieval, and experience learning.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from backend.memory.document_memory import DocumentMemoryStore
from backend.memory.embedding_index import EmbeddingIndex
from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.experience_manager import ExperienceManager
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import (
    DocumentMemory,
    EpisodicMemory,
    KnowledgeEdge,
    KnowledgeNode,
    ProceduralMemory,
    SearchResult,
    SemanticMemory,
    WorkingMemory,
)
from backend.memory.procedural_memory import ProceduralMemoryStore
from backend.memory.retrieval_engine import RetrievalEngine
from backend.memory.semantic_memory import SemanticMemoryStore
from backend.memory.working_memory import WorkingMemoryStore


class MemoryManager:
    """Central memory orchestrator.

    Integrates all memory types with a unified API.
    All Hermes subsystems access memory through this facade.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        # Memory stores
        self._working = WorkingMemoryStore(on_event=on_event)
        self._episodic = EpisodicMemoryStore(on_event=on_event)
        self._semantic = SemanticMemoryStore(on_event=on_event)
        self._procedural = ProceduralMemoryStore(on_event=on_event)
        self._documents = DocumentMemoryStore(on_event=on_event)

        # Knowledge
        self._graph = KnowledgeGraph(on_event=on_event)
        self._embeddings = EmbeddingIndex(on_event=on_event)

        # Intelligence
        self._retrieval = RetrievalEngine(
            episodic=self._episodic,
            semantic=self._semantic,
            procedural=self._procedural,
            documents=self._documents,
            graph=self._graph,
            embeddings=self._embeddings,
            on_event=on_event,
        )
        self._experience = ExperienceManager(episodic=self._episodic, on_event=on_event)

    # ── Working Memory ───────────────────────────────────────

    def create_working_memory(self, mission_id: str, agent_id: str) -> WorkingMemory:
        return self._working.create(mission_id, agent_id)

    def get_working_memory(self, mission_id: str) -> Optional[WorkingMemory]:
        return self._working.get_by_mission(mission_id)

    def clear_working_memory(self, mission_id: str) -> bool:
        return self._working.clear(mission_id)

    # ── Episodic ─────────────────────────────────────────────

    def record_episode(self, episode: EpisodicMemory) -> EpisodicMemory:
        return self._episodic.record(episode)

    def get_episode(self, mission_id: str) -> Optional[EpisodicMemory]:
        return self._episodic.get_by_mission(mission_id)

    def find_similar_missions(self, tags: list[str], mission_type: str = "", limit: int = 10) -> list[EpisodicMemory]:
        return self._episodic.find_similar(tags, mission_type, limit)

    # ── Semantic ─────────────────────────────────────────────

    def store_concept(self, concept: SemanticMemory) -> SemanticMemory:
        return self._semantic.store(concept)

    def search_concepts(self, query: str, limit: int = 10) -> list[SemanticMemory]:
        return self._semantic.search(query, limit)

    # ── Procedural ───────────────────────────────────────────

    def store_procedure(self, procedure: ProceduralMemory) -> ProceduralMemory:
        return self._procedural.store(procedure)

    def find_procedures(self, query: str, limit: int = 10) -> list[ProceduralMemory]:
        return self._procedural.search(query, limit)

    # ── Documents ────────────────────────────────────────────

    def index_document(self, doc: DocumentMemory) -> DocumentMemory:
        # Also index in embeddings
        self._embeddings.index(doc.document_id, doc.title + " " + doc.content[:1000])
        return self._documents.index(doc)

    def search_docs(self, query: str, limit: int = 10) -> list[DocumentMemory]:
        return self._documents.search(query, limit)

    # ── Knowledge Graph ──────────────────────────────────────

    def add_graph_node(self, node: KnowledgeNode) -> KnowledgeNode:
        return self._graph.add_node(node)

    def add_graph_edge(self, source_id: str, target_id: str, relation: str) -> Optional[KnowledgeEdge]:
        return self._graph.add_edge(source_id, target_id, relation)

    def get_graph_neighbors(self, node_id: str, relation: str = "") -> list[KnowledgeNode]:
        return self._graph.get_neighbors(node_id, relation)

    def traverse_graph(self, start_id: str, max_depth: int = 3) -> dict:
        return self._graph.traverse(start_id, max_depth)

    # ── Search ───────────────────────────────────────────────

    def search(self, query: str, limit: int = 20, memory_types: Optional[list[str]] = None) -> list[SearchResult]:
        return self._retrieval.search(query, limit, memory_types)

    def search_experiences(self, query: str, limit: int = 10) -> list[SearchResult]:
        return self._retrieval.search_experiences(query, limit)

    # ── Experience ───────────────────────────────────────────

    def learn_from_mission(self, episode: EpisodicMemory) -> list[str]:
        return self._experience.learn_from_mission(episode)

    def recommend_for_mission(self, mission_type: str, tags: list[str]) -> dict:
        return self._experience.recommend_for_new_mission(mission_type, tags)

    def get_best_practices(self, mission_type: str = "", limit: int = 10) -> list[str]:
        return self._experience.get_best_practices(mission_type, limit)

    # ── Index ────────────────────────────────────────────────

    def index_text(self, entity_id: str, text: str) -> list[float]:
        return self._embeddings.index(entity_id, text)

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "working": self._working.stats(),
            "episodic": self._episodic.stats(),
            "semantic": self._semantic.stats(),
            "procedural": self._procedural.stats(),
            "documents": self._documents.stats(),
            "graph": self._graph.stats(),
            "embeddings": {"count": self._embeddings.count()},
        }
