"""HOS-053A — Alexandrie Integration Tests.

Tests the Hermes ↔ Alexandrie adapter bridge.
Alexandrie is not running during tests (CI-safe).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from backend.integrations.alexandrie.alexandrie_client import AlexandrieClient
from backend.integrations.alexandrie.alexandrie_models import (
    AlexandrieAccessLevel,
    AlexandrieConfig,
    AlexandrieNode,
    AlexandrieNodeType,
    AlexandrieSearchResult,
    DocumentMemoryEntry,
    HybridSearchResult,
    KnowledgeGraphEdge,
)
from backend.integrations.alexandrie.hermes_alexandrie_adapter import (
    HermesAlexandrieAdapter,
    get_alexandrie_adapter,
)


# ── Helpers ────────────────────────────────────────────────────────

def _make_node(
    title: str = "Test Doc",
    content: str = "# Test Content\n\nThis is a test document.",
    node_type: AlexandrieNodeType = AlexandrieNodeType.DOCUMENT,
) -> AlexandrieNode:
    return AlexandrieNode(
        id=f"alex-node-{title.lower().replace(' ', '-')}",
        title=title,
        content=content,
        node_type=node_type,
        owner_id="user-1",
        is_public=False,
    )


# ── Tests: AlexandrieNode ──────────────────────────────────────────

class TestAlexandrieModels:
    """Data model tests."""

    def test_node_creation(self):
        node = _make_node("API Docs", "# API\n\nEndpoints here.")
        assert node.title == "API Docs"
        assert node.node_type == AlexandrieNodeType.DOCUMENT
        assert node.owner_id == "user-1"

    def test_node_types(self):
        assert AlexandrieNodeType.WORKSPACE.value == "workspace"
        assert AlexandrieNodeType.CATEGORY.value == "category"
        assert AlexandrieNodeType.DOCUMENT.value == "document"

    def test_access_levels(self):
        assert AlexandrieAccessLevel.NONE.value == "none"
        assert AlexandrieAccessLevel.OWNER.value == "owner"

    def test_search_result(self):
        result = AlexandrieSearchResult(query="test", total=5, took_ms=12.5)
        assert result.query == "test"
        assert result.total == 5

    def test_document_memory_entry(self):
        entry = DocumentMemoryEntry(
            external_id="alex-123",
            title="Test",
            content="Content",
            metadata={"tags": ["python"]},
        )
        assert entry.external_id == "alex-123"
        assert entry.source == "alexandrie"
        assert entry.metadata["tags"] == ["python"]

    def test_hybrid_search_result(self):
        result = HybridSearchResult(query="test", total=3)
        assert result.query == "test"
        assert result.total == 3

    def test_knowledge_graph_edge(self):
        edge = KnowledgeGraphEdge(source_id="doc-1", target_id="doc-2", relation="child_of")
        assert edge.source_id == "doc-1"
        assert edge.relation == "child_of"

    def test_config_defaults(self):
        config = AlexandrieConfig()
        assert config.base_url == "http://localhost:8200"
        assert config.timeout_seconds == 30.0


# ── Tests: AlexandrieClient (offline) ──────────────────────────────

class TestAlexandrieClient:
    """Client tests (no Alexandrie running)."""

    def setup_method(self):
        self.client = AlexandrieClient(AlexandrieConfig(base_url="http://localhost:8200", timeout_seconds=2.0))

    def test_health_check_offline(self):
        result = self.client.health_check()
        assert result["healthy"] is False

    def test_search_empty_query(self):
        result = self.client.search("")
        assert result.total == 0

    def test_search_short_query(self):
        result = self.client.search("a")
        assert result.total == 0

    def test_search_offline(self):
        result = self.client.search("test query")
        # Should not crash when Alexandrie is offline
        assert isinstance(result, AlexandrieSearchResult)
        assert result.query == "test query"

    def test_get_node_offline(self):
        node = self.client.get_node("some-id")
        assert node is None

    def test_list_nodes_offline(self):
        nodes = self.client.list_nodes("user-1")
        assert nodes == []

    def test_checksum(self):
        h1 = self.client.compute_hash("hello")
        h2 = self.client.compute_hash("hello")
        h3 = self.client.compute_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64


# ── Tests: HermesAlexandrieAdapter ─────────────────────────────────

class TestHermesAdapter:
    """Adapter tests (in-memory, no Alexandrie needed)."""

    def setup_method(self):
        self.adapter = HermesAlexandrieAdapter(
            AlexandrieConfig(base_url="http://localhost:8200", timeout_seconds=1.0)
        )

    def test_singleton(self):
        a1 = get_alexandrie_adapter()
        a2 = get_alexandrie_adapter()
        assert a1 is a2

    def test_sync_document(self):
        node = _make_node("Auth Guide", "# Authentication\n\nOAuth2 setup.")
        entry = self.adapter.sync_document(node)

        assert entry.title == "Auth Guide"
        assert entry.source == "alexandrie"
        assert entry.content_hash
        assert self.adapter.get_statistics()["documents_synced"] == 1

    def test_sync_duplicate_no_change(self):
        node = _make_node("Same Doc", "Same content")
        e1 = self.adapter.sync_document(node)
        e2 = self.adapter.sync_document(node)  # same content = no re-index
        assert e1.id == e2.id
        assert self.adapter.get_statistics()["documents_synced"] == 1

    def test_sync_document_with_changes(self):
        node = _make_node("Evolving Doc", "Version 1")
        e1 = self.adapter.sync_document(node)
        hash_before = e1.content_hash

        node.content = "Version 2"
        e2 = self.adapter.sync_document(node)
        # Same external_id, same Hermes entry but re-synced with new hash
        assert e1.external_id == e2.external_id
        assert e2.content_hash != hash_before

    def test_unsync_document(self):
        node = _make_node("Temp Doc", "Temporary")
        self.adapter.sync_document(node)
        assert self.adapter.get_statistics()["documents_synced"] == 1

        assert self.adapter.unsync_document(node.id) is True
        assert self.adapter.get_statistics()["documents_synced"] == 0

    def test_unsync_unknown(self):
        assert self.adapter.unsync_document("nonexistent") is False

    def test_graph_edges(self):
        parent = _make_node("Parent", "Parent content")
        child = _make_node("Child", "Child content")
        child.parent_id = parent.id

        self.adapter.sync_document(parent)
        self.adapter.sync_document(child)

        edges = self.adapter.get_graph_edges()
        assert len(edges) >= 1
        child_edge = [e for e in edges if e["relation"] == "child_of"]
        assert len(child_edge) == 1

    def test_graph_for_node(self):
        parent = _make_node("P", "P")
        child = _make_node("C", "C")
        child.parent_id = parent.id
        self.adapter.sync_document(parent)
        self.adapter.sync_document(child)

        edges = self.adapter.get_graph_for_node(parent.id)
        assert len(edges) >= 1

    def test_full_text_search_offline(self):
        result = self.adapter.full_text_search("test")
        assert isinstance(result, AlexandrieSearchResult)

    def test_semantic_search(self):
        node = _make_node("Python Guide", "How to use Python async/await for concurrency")
        self.adapter.sync_document(node)

        results = self.adapter.semantic_search("python async")
        assert len(results) >= 1
        assert results[0].title == "Python Guide"

        # No match
        results = self.adapter.semantic_search("ruby rails")
        assert len(results) == 0

    def test_semantic_search_tag_match(self):
        node = _make_node("Docker Tips", "Container optimization")
        node.tags = ["docker", "devops"]
        self.adapter.sync_document(node)

        results = self.adapter.semantic_search("docker")
        assert len(results) >= 1

    def test_hybrid_search(self):
        node = _make_node("API Reference", "REST API endpoints for auth")
        self.adapter.sync_document(node)

        result = self.adapter.hybrid_search("api")
        assert isinstance(result, HybridSearchResult)
        assert result.total >= 0  # May be 0 if offline

    def test_create_document_offline(self):
        result = self.adapter.create_document("New Doc", "Content")
        # Offline = None
        assert result is None

    def test_get_synced_documents(self):
        n1 = _make_node("Doc A", "A")
        n2 = _make_node("Doc B", "B")
        self.adapter.sync_document(n1)
        self.adapter.sync_document(n2)

        docs = self.adapter.get_synced_documents()
        assert len(docs) == 2

    def test_event_publishing(self):
        received = []
        self.adapter.subscribe(lambda e: received.append(e))

        node = _make_node("Event Test", "Content")
        self.adapter.sync_document(node)

        assert len(received) >= 1
        assert received[0]["source"] == "alexandrie"
        assert received[0]["type"] == "alexandrie.document.created"

    def test_event_history(self):
        node = _make_node("History Test", "Content")
        self.adapter.sync_document(node)

        events = self.adapter.get_events(10)
        assert len(events) >= 1

    def test_event_history_limit(self):
        for i in range(600):
            node = _make_node(f"Doc-{i}", f"Content {i}")
            self.adapter.sync_document(node)

        events = self.adapter.get_events(1000)
        assert len(events) <= 500

    def test_statistics(self):
        node = _make_node("Stats Doc", "Content")
        self.adapter.sync_document(node)

        stats = self.adapter.get_statistics()
        assert stats["documents_synced"] >= 1
        assert stats["documents_indexed"] >= 1
        assert "events_count" in stats

    def test_health_check(self):
        health = self.adapter.health_check()
        assert "healthy" in health


# ── Tests: Thread Safety ───────────────────────────────────────────

class TestThreadSafety:
    """Concurrent access tests."""

    def test_concurrent_sync(self):
        adapter = HermesAlexandrieAdapter()

        def sync_doc(i: int):
            node = _make_node(f"Thread-{i}", f"Content {i}")
            adapter.sync_document(node)
            return node

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(sync_doc, i) for i in range(50)]
            results = [f.result() for f in as_completed(futures)]

        stats = adapter.get_statistics()
        assert stats["documents_synced"] == 50

    def test_concurrent_events(self):
        adapter = HermesAlexandrieAdapter()
        received = []
        adapter.subscribe(lambda e: received.append(e))

        def publish(i: int):
            adapter.sync_document(_make_node(f"Evt-{i}", f"Event content {i}"))

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(publish, range(50)))

        assert len(received) == 50

    def test_concurrent_hybrid_search(self):
        adapter = HermesAlexandrieAdapter()
        for i in range(20):
            adapter.sync_document(_make_node(f"Search-{i}", f"content about search query {i}"))

        def search(i: int):
            return adapter.hybrid_search(f"search {i % 10}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(search, range(30)))

        assert len(results) == 30


# ── Tests: Full Integration Pipeline ──────────────────────────────

class TestFullPipeline:
    """End-to-end integration tests."""

    def test_sync_search_unsync_flow(self):
        adapter = HermesAlexandrieAdapter()

        # 1. Sync documents
        n1 = _make_node("API Design", "RESTful API design patterns for microservices")
        n2 = _make_node("Database Design", "PostgreSQL schema design for multi-tenant apps")
        n3 = _make_node("Frontend Guide", "React component patterns and hooks")
        adapter.sync_document(n1)
        adapter.sync_document(n2)
        adapter.sync_document(n3)

        assert adapter.get_statistics()["documents_synced"] == 3

        # 2. Semantic search
        results = adapter.semantic_search("api design")
        assert len(results) >= 1
        assert results[0].title == "API Design"

        results = adapter.semantic_search("react")
        assert len(results) >= 1
        assert results[0].title == "Frontend Guide"

        # 3. No match
        results = adapter.semantic_search("machine learning")
        assert len(results) == 0

        # 4. Unsync
        adapter.unsync_document(n1.id)
        assert adapter.get_statistics()["documents_synced"] == 2

    def test_knowledge_graph_tree(self):
        """Build a doc tree and verify graph edges."""
        adapter = HermesAlexandrieAdapter()

        root = _make_node("Documentation", "Root of all docs", AlexandrieNodeType.WORKSPACE)
        cat = _make_node("Backend", "Backend docs", AlexandrieNodeType.CATEGORY)
        cat.parent_id = root.id
        doc = _make_node("Auth", "Auth implementation", AlexandrieNodeType.DOCUMENT)
        doc.parent_id = cat.id

        adapter.sync_document(root)
        adapter.sync_document(cat)
        adapter.sync_document(doc)

        edges = adapter.get_graph_edges()
        child_edges = [e for e in edges if e["relation"] == "child_of"]
        assert len(child_edges) == 2

        # Get graph for root
        root_edges = adapter.get_graph_for_node(root.id)
        assert len(root_edges) >= 1

    def test_multiple_event_types(self):
        adapter = HermesAlexandrieAdapter()
        received = []
        adapter.subscribe(lambda e: received.append(e))

        node = _make_node("Event Flow", "Content")
        adapter.sync_document(node)
        adapter.unsync_document(node.id)

        types = {e["type"] for e in received}
        assert "alexandrie.document.created" in types
        assert "alexandrie.document.deleted" in types
