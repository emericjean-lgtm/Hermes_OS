"""Alexandrie Integration — HOS-053B production.

Hermes OS ↔ Alexandrie production bridge.
"""

from backend.integrations.alexandrie.alexandrie_models import (
    AlexandrieAccessLevel, AlexandrieConfig, AlexandrieNode, AlexandrieNodeType,
    AlexandrieSearchResult, CacheEvictionPolicy, ConflictResolution,
    DocumentMemoryEntry, HybridSearchResult, KnowledgeGraphEdge,
    SyncEvent, SyncStatus,
)
from backend.integrations.alexandrie.alexandrie_client import AlexandrieClient
from backend.integrations.alexandrie.document_cache import DocumentCache
from backend.integrations.alexandrie.hermes_alexandrie_adapter import (
    HermesAlexandrieAdapter, get_alexandrie_adapter,
)
from backend.integrations.alexandrie.routes import router

__all__ = [
    "AlexandrieAccessLevel", "AlexandrieClient", "AlexandrieConfig",
    "AlexandrieNode", "AlexandrieNodeType", "AlexandrieSearchResult",
    "CacheEvictionPolicy", "ConflictResolution", "DocumentCache",
    "DocumentMemoryEntry", "HermesAlexandrieAdapter", "HybridSearchResult",
    "KnowledgeGraphEdge", "SyncEvent", "SyncStatus",
    "get_alexandrie_adapter", "router",
]
