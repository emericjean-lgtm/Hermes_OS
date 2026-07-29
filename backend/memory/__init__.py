"""Unified Memory & Knowledge Graph Engine (HOS-047).

Permanent brain of Hermes OS. Learning, retrieval, knowledge graph.
All subsystem memory access goes through MemoryManager.
"""

from backend.memory.memory_models import (
    WorkingMemory,
    EpisodicMemory,
    SemanticMemory,
    ProceduralMemory,
    DocumentMemory,
    KnowledgeNode,
    KnowledgeEdge,
    SearchResult,
)
from backend.memory.working_memory import WorkingMemoryStore
from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.semantic_memory import SemanticMemoryStore
from backend.memory.procedural_memory import ProceduralMemoryStore
from backend.memory.document_memory import DocumentMemoryStore
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.embedding_index import EmbeddingIndex
from backend.memory.retrieval_engine import RetrievalEngine
from backend.memory.experience_manager import ExperienceManager
from backend.memory.memory_manager import MemoryManager

__all__ = [
    "WorkingMemory", "EpisodicMemory", "SemanticMemory",
    "ProceduralMemory", "DocumentMemory", "KnowledgeNode",
    "KnowledgeEdge", "SearchResult",
    "WorkingMemoryStore", "EpisodicMemoryStore", "SemanticMemoryStore",
    "ProceduralMemoryStore", "DocumentMemoryStore",
    "KnowledgeGraph", "EmbeddingIndex", "RetrievalEngine",
    "ExperienceManager", "MemoryManager",
]
