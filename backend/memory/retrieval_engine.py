"""Retrieval Engine for HOS-047 — hybrid search: graph, embeddings, keywords, filters."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.document_memory import DocumentMemoryStore
from backend.memory.embedding_index import EmbeddingIndex
from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import SearchResult
from backend.memory.procedural_memory import ProceduralMemoryStore
from backend.memory.semantic_memory import SemanticMemoryStore


class RetrievalEngine:
    """Hybrid search across all memory types.

    Combines: keyword search, embedding similarity, graph traversal, filtered results.
    Returns scored results with justification.
    """

    def __init__(
        self,
        episodic: EpisodicMemoryStore,
        semantic: SemanticMemoryStore,
        procedural: ProceduralMemoryStore,
        documents: DocumentMemoryStore,
        graph: KnowledgeGraph,
        embeddings: EmbeddingIndex,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._episodic = episodic
        self._semantic = semantic
        self._procedural = procedural
        self._documents = documents
        self._graph = graph
        self._embeddings = embeddings

    def search(
        self,
        query: str,
        limit: int = 20,
        memory_types: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Hybrid search: embeddings + keyword across all or selected memory types."""
        types = set(memory_types or ["episodic", "semantic", "procedural", "document", "graph"])
        results: list[SearchResult] = []

        # Embedding search
        top_ids = [(eid, score) for eid, score in self._embeddings.search(query, limit * 2)]

        if "episodic" in types:
            for e in self._episodic.search_by_keyword(query, limit):
                results.append(SearchResult(
                    source_type="episodic", source_id=e.episode_id,
                    title=e.mission_title, snippet=e.mission_type,
                    score=0.7, justification="Keyword match in episodic memory",
                ))

        if "semantic" in types:
            for c in self._semantic.search(query, limit):
                results.append(SearchResult(
                    source_type="semantic", source_id=c.concept_id,
                    title=c.name, snippet=c.description,
                    score=0.8, justification="Semantic concept match",
                ))

        if "procedural" in types:
            for p in self._procedural.search(query, limit):
                results.append(SearchResult(
                    source_type="procedural", source_id=p.procedure_id,
                    title=p.name, snippet=p.description,
                    score=p.success_rate, justification=f"Procedure ({p.usage_count} uses, {p.success_rate:.0%} success)",
                ))

        if "document" in types:
            for d in self._documents.search(query, limit):
                results.append(SearchResult(
                    source_type="document", source_id=d.document_id,
                    title=d.title, snippet=d.summary or d.content[:200],
                    score=0.6, justification="Document content match",
                ))

        if "graph" in types:
            graph_nodes = self._graph.find_nodes(label_contains=query)
            for n in graph_nodes[:limit]:
                results.append(SearchResult(
                    source_type="graph", source_id=n.node_id,
                    title=n.label, snippet=n.node_type,
                    score=0.5, justification=f"Graph node ({n.node_type})",
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        if self._on_event and results:
            self._on_event("retrieval.completed", {
                "query": query, "result_count": len(results[:limit]),
            }, severity="info")

        return results[:limit]

    def search_experiences(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search mission experiences for learning."""
        return self.search(query, limit, memory_types=["episodic"])

    def search_procedures(self, query: str, limit: int = 10) -> list[SearchResult]:
        return self.search(query, limit, memory_types=["procedural"])

    def search_documents(self, query: str, limit: int = 10) -> list[SearchResult]:
        return self.search(query, limit, memory_types=["document"])
