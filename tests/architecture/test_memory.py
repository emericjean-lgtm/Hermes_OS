"""Tests for the Unified Memory & Knowledge Graph Engine (HOS-047)."""

from __future__ import annotations

import threading

import pytest

from backend.memory.document_memory import DocumentMemoryStore
from backend.memory.embedding_index import EmbeddingIndex
from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.experience_manager import ExperienceManager
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_manager import MemoryManager
from backend.memory.memory_models import (
    DocumentMemory,
    EpisodicMemory,
    KnowledgeEdge,
    KnowledgeNode,
    ProceduralMemory,
    SemanticMemory,
)
from backend.memory.procedural_memory import ProceduralMemoryStore
from backend.memory.retrieval_engine import RetrievalEngine
from backend.memory.semantic_memory import SemanticMemoryStore
from backend.memory.working_memory import WorkingMemoryStore


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def working() -> WorkingMemoryStore:
    return WorkingMemoryStore()


@pytest.fixture
def episodic() -> EpisodicMemoryStore:
    return EpisodicMemoryStore()


@pytest.fixture
def semantic() -> SemanticMemoryStore:
    return SemanticMemoryStore()


@pytest.fixture
def procedural() -> ProceduralMemoryStore:
    return ProceduralMemoryStore()


@pytest.fixture
def documents() -> DocumentMemoryStore:
    return DocumentMemoryStore()


@pytest.fixture
def graph() -> KnowledgeGraph:
    return KnowledgeGraph()


@pytest.fixture
def embeddings() -> EmbeddingIndex:
    return EmbeddingIndex()


@pytest.fixture
def experience(episodic) -> ExperienceManager:
    return ExperienceManager(episodic=episodic)


@pytest.fixture
def retrieval(episodic, semantic, procedural, documents, graph, embeddings) -> RetrievalEngine:
    return RetrievalEngine(episodic, semantic, procedural, documents, graph, embeddings)


@pytest.fixture
def manager() -> MemoryManager:
    return MemoryManager()


# ── Working Memory Tests ────────────────────────────────────

class TestWorkingMemory:
    def test_create(self, working):
        wm = working.create("m1", "agent1")
        assert wm.mission_id == "m1"

    def test_get_by_mission(self, working):
        working.create("m1", "agent1")
        assert working.get_by_mission("m1") is not None

    def test_update_conversation(self, working):
        wm = working.create("m1", "agent1")
        working.update_conversation(wm.memory_id, {"role": "agent", "content": "hello"})
        wm2 = working.get_by_mission("m1")
        assert len(wm2.conversations) == 1

    def test_clear(self, working):
        working.create("m1", "agent1")
        assert working.clear("m1")
        assert working.get_by_mission("m1") is None

    def test_stats(self, working):
        working.create("m1", "agent1")
        stats = working.stats()
        assert stats["active_memories"] >= 1


# ── Episodic Memory Tests ────────────────────────────────────

class TestEpisodicMemory:
    def test_record(self, episodic):
        e = EpisodicMemory(mission_id="m1", mission_title="Build API", tags=["api", "backend"])
        episodic.record(e)
        assert episodic.get_by_mission("m1") is not None

    def test_find_similar(self, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", mission_title="API v1", tags=["api", "rest"], success=True))
        episodic.record(EpisodicMemory(mission_id="m2", mission_title="Auth", tags=["auth", "oauth"], success=True))
        episodic.record(EpisodicMemory(mission_id="m3", mission_title="API v2", tags=["api", "graphql"], success=False))
        similar = episodic.find_similar(["api"])
        assert len(similar) >= 2

    def test_get_successful(self, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", success=True, tags=["x"]))
        episodic.record(EpisodicMemory(mission_id="m2", success=False, tags=["y"]))
        assert len(episodic.get_successful()) >= 1
        assert len(episodic.get_failed()) >= 1

    def test_search_by_keyword(self, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", mission_title="REST API", tags=["api"]))
        episodic.record(EpisodicMemory(mission_id="m2", mission_title="GraphQL API", tags=["graphql"]))
        results = episodic.search_by_keyword("REST")
        assert len(results) >= 1

    def test_stats(self, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", success=True, tags=["x"]))
        stats = episodic.stats()
        assert stats["total"] >= 1


# ── Semantic Memory Tests ────────────────────────────────────

class TestSemanticMemory:
    def test_store_and_get(self, semantic):
        c = SemanticMemory(name="Python", category="technology", description="Programming language")
        semantic.store(c)
        assert semantic.get_by_name("Python") is not None

    def test_search(self, semantic):
        semantic.store(SemanticMemory(name="React", category="framework", description="UI library", tags=["frontend"]))
        semantic.store(SemanticMemory(name="FastAPI", category="framework", description="API", tags=["backend", "framework"]))
        results = semantic.search("framework")
        assert len(results) == 1  # matches tags + description
        results2 = semantic.search("library")
        assert len(results2) == 1  # matches React description

    def test_get_by_category(self, semantic):
        semantic.store(SemanticMemory(name="Docker", category="tool", description="Containers"))
        results = semantic.get_by_category("tool")
        assert len(results) >= 1

    def test_stats(self, semantic):
        semantic.store(SemanticMemory(name="Git", category="tool"))
        stats = semantic.stats()
        assert stats["total"] >= 1


# ── Procedural Memory Tests ──────────────────────────────────

class TestProceduralMemory:
    def test_store(self, procedural):
        p = ProceduralMemory(name="API Deployment", category="workflow", steps=["Build", "Test", "Deploy"])
        procedural.store(p)
        assert procedural.get_latest("API Deployment") is not None

    def test_versioning(self, procedural):
        v1 = ProceduralMemory(name="Deploy", version=1, steps=["Step A"])
        v2 = ProceduralMemory(name="Deploy", version=2, steps=["Step A", "Step B"])
        procedural.store(v1)
        procedural.store(v2)
        versions = procedural.get_versions("Deploy")
        assert len(versions) == 2
        assert procedural.get_latest("Deploy").version == 2

    def test_record_usage(self, procedural):
        p = ProceduralMemory(name="Deploy", success_rate=0.5, usage_count=1)
        procedural.store(p)
        procedural.record_usage("Deploy", True)
        latest = procedural.get_latest("Deploy")
        assert latest.usage_count == 2

    def test_search(self, procedural):
        procedural.store(ProceduralMemory(name="CI/CD Pipeline", description="Automated CI/CD", tags=["ci", "automation"]))
        results = procedural.search("CI/CD")
        assert len(results) >= 1

    def test_stats(self, procedural):
        procedural.store(ProceduralMemory(name="Deploy", steps=["Build"]))
        stats = procedural.stats()
        assert stats["total_procedures"] >= 1


# ── Document Memory Tests ────────────────────────────────────

class TestDocumentMemory:
    def test_index(self, documents):
        d = DocumentMemory(title="README.md", content="Project documentation", content_type="markdown")
        documents.index(d)
        results = documents.search("documentation")
        assert len(results) >= 1

    def test_search(self, documents):
        documents.index(DocumentMemory(title="API Spec", content="REST API endpoints", tags=["api"]))
        documents.index(DocumentMemory(title="Auth Guide", content="Authentication flow", tags=["auth"]))
        results = documents.search("api")
        assert len(results) >= 1

    def test_stats(self, documents):
        documents.index(DocumentMemory(title="Doc", content="test"))
        stats = documents.stats()
        assert stats["total_documents"] >= 1


# ── Knowledge Graph Tests ────────────────────────────────────

class TestKnowledgeGraph:
    def test_add_node(self, graph):
        n = graph.add_node(KnowledgeNode(node_type="mission", label="Mission X"))
        assert graph.get_node(n.node_id) is not None

    def test_add_edge(self, graph):
        n1 = graph.add_node(KnowledgeNode(node_type="agent", label="Coder"))
        n2 = graph.add_node(KnowledgeNode(node_type="runtime", label="qwen3:14b"))
        e = graph.add_edge(n1.node_id, n2.node_id, "uses_runtime")
        assert e is not None

    def test_get_neighbors(self, graph):
        n1 = graph.add_node(KnowledgeNode(node_type="mission", label="M1"))
        n2 = graph.add_node(KnowledgeNode(node_type="task", label="T1"))
        n3 = graph.add_node(KnowledgeNode(node_type="task", label="T2"))
        graph.add_edge(n1.node_id, n2.node_id, "contains")
        graph.add_edge(n1.node_id, n3.node_id, "contains")
        neighbors = graph.get_neighbors(n1.node_id)
        assert len(neighbors) == 2

    def test_traverse(self, graph):
        n1 = graph.add_node(KnowledgeNode(node_type="mission", label="M1"))
        n2 = graph.add_node(KnowledgeNode(node_type="agent", label="Coder"))
        graph.add_edge(n1.node_id, n2.node_id, "executed_by")
        subgraph = graph.traverse(n1.node_id, max_depth=2)
        assert len(subgraph["nodes"]) >= 2
        assert len(subgraph["edges"]) >= 1

    def test_find_nodes(self, graph):
        graph.add_node(KnowledgeNode(node_type="model", label="qwen3:14b"))
        graph.add_node(KnowledgeNode(node_type="model", label="phi4:14b"))
        results = graph.find_nodes(node_type="model")
        assert len(results) == 2

    def test_stats(self, graph):
        graph.add_node(KnowledgeNode(node_type="mission", label="M1"))
        stats = graph.stats()
        assert stats["total_nodes"] >= 1


# ── Embedding Index Tests ────────────────────────────────────

class TestEmbeddingIndex:
    def test_embed(self, embeddings):
        vec = embeddings.embed("Hello world")
        assert len(vec) == 128

    def test_index_and_search(self, embeddings):
        embeddings.index("doc1", "Python programming language")
        embeddings.index("doc2", "JavaScript frontend framework")
        embeddings.index("doc3", "Rust systems programming")
        results = embeddings.search("python programming")
        assert len(results) >= 1
        assert results[0][0] == "doc1"

    def test_cosine_similarity(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert EmbeddingIndex._cosine_similarity(a, b) == pytest.approx(1.0)
        c = [0.0, 1.0, 0.0]
        assert EmbeddingIndex._cosine_similarity(a, c) == pytest.approx(0.0)

    def test_remove(self, embeddings):
        embeddings.index("doc1", "test")
        assert embeddings.remove("doc1")
        assert embeddings.count() == 0


# ── Experience Manager Tests ─────────────────────────────────

class TestExperienceManager:
    def test_learn_from_mission(self, experience, episodic):
        e = EpisodicMemory(mission_id="m1", mission_title="Build API",
                          success=True, completed_nodes=5, total_nodes=5,
                          models_used=["qwen3:14b"], tags=["api"])
        episodic.record(e)
        lessons = experience.learn_from_mission(e)
        assert len(lessons) >= 1

    def test_recommend_for_new_mission(self, experience, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", mission_title="API v1",
                                       mission_type="development", success=True,
                                       models_used=["qwen3:14b"], tags=["api"]))
        episodic.record(EpisodicMemory(mission_id="m2", mission_title="API v2",
                                       mission_type="development", success=True,
                                       models_used=["qwen3:14b"], tags=["api"]))
        rec = experience.recommend_for_new_mission("development", ["api"])
        assert "recommended_models" in rec
        assert "best_practices" in rec

    def test_get_best_practices(self, experience, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", success=True,
                                       improvements=["Use CI/CD"], tags=["devops"]))
        practices = experience.get_best_practices()
        assert len(practices) >= 1

    def test_get_frequent_errors(self, experience, episodic):
        episodic.record(EpisodicMemory(mission_id="m1", success=False,
                                       incidents=[{"description": "Timeout"}], tags=["bug"]))
        episodic.record(EpisodicMemory(mission_id="m2", success=False,
                                       incidents=[{"description": "Timeout"}], tags=["bug"]))
        errors = experience.get_frequent_errors()
        assert "Timeout" in errors


# ── Memory Manager Tests ─────────────────────────────────────

class TestMemoryManager:
    def test_full_workflow(self, manager):
        # Working memory
        wm = manager.create_working_memory("m1", "agent1")
        assert wm is not None

        # Episodic
        e = EpisodicMemory(mission_id="m1", mission_title="Test Mission",
                          success=True, tags=["test"], models_used=["qwen3:14b"])
        manager.record_episode(e)
        assert manager.get_episode("m1") is not None

        # Semantic
        manager.store_concept(SemanticMemory(name="Python", category="technology"))
        assert len(manager.search_concepts("Python")) >= 1

        # Procedural
        manager.store_procedure(ProceduralMemory(name="Deploy", steps=["Build", "Deploy"]))
        assert len(manager.find_procedures("Deploy")) >= 1

        # Document
        manager.index_document(DocumentMemory(title="Readme", content="Test docs"))
        assert len(manager.search_docs("Test")) >= 1

        # Graph
        n1 = manager.add_graph_node(KnowledgeNode(node_type="mission", label="M1"))
        n2 = manager.add_graph_node(KnowledgeNode(node_type="agent", label="Coder"))
        manager.add_graph_edge(n1.node_id, n2.node_id, "uses")
        assert len(manager.get_graph_neighbors(n1.node_id)) >= 1

        # Experience
        lessons = manager.learn_from_mission(e)
        assert len(lessons) >= 1

        # Search
        results = manager.search("Test")
        assert len(results) >= 1

        # Clear
        manager.clear_working_memory("m1")
        assert manager.get_working_memory("m1") is None

    def test_recommend_for_mission_reuses_experience(self, manager):
        """New mission automatically reuses past experience."""
        # Past missions
        manager.record_episode(EpisodicMemory(
            mission_id="past1", mission_title="Auth Service v1",
            mission_type="development", success=True,
            models_used=["qwen3:14b", "deepseek-r1:14b"],
            tags=["auth", "oauth", "security"],
        ))
        manager.record_episode(EpisodicMemory(
            mission_id="past2", mission_title="Auth Service v2",
            mission_type="development", success=True,
            models_used=["qwen3:14b"],
            tags=["auth", "jwt"],
        ))
        manager.record_episode(EpisodicMemory(
            mission_id="past3", mission_title="Database Migration",
            mission_type="development", success=False,
            models_used=["qwen3:4b"],
            incidents=[{"description": "Schema mismatch"}],
            tags=["database", "migration"],
        ))

        # New mission planning
        rec = manager.recommend_for_mission("development", ["auth", "oauth"])

        assert rec["similar_missions"] >= 2
        assert rec["similar_success_rate"] >= 50.0
        assert "qwen3:14b" in rec["recommended_models"]

        # Past auth experiences
        for exp in rec["past_experiences"]:
            assert "auth" in exp["title"].lower()

    def test_search_finds_relevant(self, manager):
        manager.record_episode(EpisodicMemory(mission_id="m1", mission_title="OAuth Implementation", tags=["auth"]))
        manager.store_concept(SemanticMemory(name="OAuth 2.0", category="technology", description="Authorization framework"))
        manager.index_document(DocumentMemory(title="Auth Guide", content="OAuth setup instructions", tags=["auth"]))

        results = manager.search("OAuth", limit=10)
        assert len(results) >= 1

    def test_stats(self, manager):
        manager.record_episode(EpisodicMemory(mission_id="m1", success=True, tags=["test"]))
        stats = manager.stats()
        assert "episodic" in stats
        assert "semantic" in stats
        assert "graph" in stats


# ── Thread Safety Tests ──────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_episodes(self, episodic):
        errors = []

        def worker(idx):
            try:
                episodic.record(EpisodicMemory(mission_id=f"m{idx}", tags=[f"tag{idx}"]))
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors
        assert episodic.stats()["total"] >= 20

    def test_concurrent_graph(self, graph):
        errors = []

        def worker(idx):
            try:
                n = graph.add_node(KnowledgeNode(node_type="test", label=f"Node{idx}"))
                graph.add_node(KnowledgeNode(node_type="target", label=f"Target{idx}"))
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors

    def test_concurrent_search(self, manager):
        for i in range(5):
            manager.record_episode(EpisodicMemory(mission_id=f"m{i}", mission_title=f"Mission {i}", tags=["search"]))
            manager.index_text(f"doc{i}", f"Document {i} about testing")

        errors = []

        def worker(idx):
            try:
                manager.search(f"Mission {idx % 5}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors
