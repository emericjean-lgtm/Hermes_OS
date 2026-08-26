"""Hermes ↔ Alexandrie Production Adapter — HOS-053B.

Full sync pipeline:
  Alexandrie doc → Adapter → Document Memory → Embedding Index → Knowledge Graph

Features:
- Incremental sync (since timestamp, checksum-based change detection)
- Conflict detection + resolution (source_wins/local_wins/last_write_wins/manual)
- Mission-linked documents (Mission Planner integration)
- Full Event Bus integration (6 event types)
- Cached document access (DocumentCache)
- Health monitoring with circuit-breaker pattern
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from backend.integrations.alexandrie.alexandrie_client import AlexandrieClient
from backend.integrations.alexandrie.alexandrie_models import (
    AlexandrieConfig,
    AlexandrieNode,
    AlexandrieSearchResult,
    ConflictResolution,
    DocumentMemoryEntry,
    HybridSearchResult,
    KnowledgeGraphEdge,
    SyncEvent,
    SyncStatus,
)
from backend.integrations.alexandrie.document_cache import DocumentCache

# --------------------------------------------------------------------
"""La synchronisation documentaire et l'ouverture du disjoncteur (HOS-181)."""
ALEXANDRIE_EVENTS: dict[str, str] = {
    "sync_started": "alexandrie.sync.started",
    "sync_completed": "alexandrie.sync.completed",
    "sync_failed": "alexandrie.sync.failed",
    "document_created": "alexandrie.document.created",
    "document_updated": "alexandrie.document.updated",
    "document_deleted": "alexandrie.document.deleted",
    "circuit_opened": "alexandrie.circuit.opened",
}


class HermesAlexandrieAdapter:
    """Production bridge between Hermes memory and Alexandrie documents.

    Pipeline:
      1. Fetch document from Alexandrie (with incremental support)
      2. Compute checksum, detect changes vs cached version
      3. Store in Hermes Document Memory with embedding stub
      4. Create Knowledge Graph edges (parent/child, mission links)
      5. Publish event on Hermes Event Bus
      6. Cache for fast hybrid search
    """

    def __init__(self, config: Optional[AlexandrieConfig] = None) -> None:
        self.config = config or AlexandrieConfig()
        self.client = AlexandrieClient(self.config)
        self._lock = threading.RLock()

        # Internal stores
        self._documents: dict[str, DocumentMemoryEntry] = {}
        self._external_index: dict[str, str] = {}  # alex_id → herm_id
        self._graph_edges: list[KnowledgeGraphEdge] = []
        self._sync_events: deque[SyncEvent] = deque(maxlen=2000)
        self._last_sync_at: Optional[datetime] = None

        # Cache
        self.cache = DocumentCache(
            max_entries=self.config.cache_max_entries,
            ttl_seconds=self.config.cache_ttl_seconds,
        )

        # Event Bus
        self._events: deque[dict[str, Any]] = deque(maxlen=500)
        self._event_callbacks: list[Any] = []

        # Circuit breaker
        self._failure_count = 0
        self._max_failures = 5
        self._circuit_open = False
        self._circuit_reset_at = 0.0

        # Mission-linked documents
        self._mission_docs: dict[str, list[str]] = {}  # mission_id → [alex_ids]

    # ── Event Bus ──────────────────────────────────────────────────

    def subscribe(self, callback: Any) -> None:
        self._event_callbacks.append(callback)

    def _publish(self, event_type: str, payload: dict[str, Any], severity: str = "info") -> None:
        event = {
            "id": str(hash(f"{event_type}_{payload}")),
            "type": event_type,
            "source": "alexandrie",
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with self._lock:
            self._events.append(event)
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def _record_sync_event(self, event_type: str, doc_id: str, status: SyncStatus, details: dict) -> None:
        evt = SyncEvent(event_type=event_type, document_id=doc_id, sync_status=status, details=details)
        self._sync_events.append(evt)

    # ── Circuit Breaker ────────────────────────────────────────────

    def _check_circuit(self) -> bool:
        if self._circuit_open:
            if time.time() > self._circuit_reset_at:
                self._circuit_open = False
                self._failure_count = 0
                return True
            return False
        return True

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._max_failures:
            self._circuit_open = True
            self._circuit_reset_at = time.time() + 30.0
            self._publish("alexandrie.circuit.opened", {"failures": self._failure_count}, severity="warning")

    def _record_success(self) -> None:
        self._failure_count = max(0, self._failure_count - 1)

    # ── Document Sync ──────────────────────────────────────────────

    def sync_document(
        self,
        node: AlexandrieNode,
        resolution: ConflictResolution = ConflictResolution.SOURCE_WINS,
    ) -> DocumentMemoryEntry:
        """Sync an Alexandrie node into Hermes document memory.

        Pipeline:
          1. Check cache for existing version
          2. Compute checksum, detect conflicts
          3. Create/update Hermes entry
          4. Create Knowledge Graph edges
          5. Publish event
        """
        content_hash = self.client.compute_hash(node.content)

        with self._lock:
            if node.id in self._external_index:
                herm_id = self._external_index[node.id]
                existing = self._documents.get(herm_id)
                if existing:
                    # Check for conflicts
                    if existing.content_hash and existing.content_hash != content_hash:
                        if resolution == ConflictResolution.SOURCE_WINS:
                            pass  # Proceed with update
                        elif resolution == ConflictResolution.LOCAL_WINS:
                            existing.sync_status = SyncStatus.CONFLICT
                            existing.conflict_info = {"remote_hash": content_hash, "local_hash": existing.content_hash}
                            self._record_sync_event("conflict_detected", node.id, SyncStatus.CONFLICT, existing.conflict_info)
                            return existing
                        elif resolution == ConflictResolution.MANUAL:
                            existing.sync_status = SyncStatus.CONFLICT
                            existing.conflict_info = {"remote_hash": content_hash, "local_hash": existing.content_hash, "needs_review": True}
                            self._record_sync_event("conflict_detected", node.id, SyncStatus.CONFLICT, existing.conflict_info)
                            return existing

                    # No change
                    if existing.content_hash == content_hash:
                        existing.last_synced_at = datetime.now(timezone.utc)
                        existing.sync_status = SyncStatus.SYNCED
                        self.cache.put(node.id, existing)
                        return existing

                    # Update existing
                    existing.title = node.title
                    existing.content = node.content
                    existing.content_hash = content_hash
                    existing.version = node.version
                    existing.last_synced_at = datetime.now(timezone.utc)
                    existing.sync_status = SyncStatus.SYNCED
                    existing.sync_error = None
                    self.cache.put(node.id, existing)
                    self._record_sync_event("document_updated", node.id, SyncStatus.SYNCED, {})
                    self._publish("alexandrie.document.updated", {"id": node.id, "title": node.title})
                    return existing

            # Create new entry
            entry = DocumentMemoryEntry(
                external_id=node.id,
                title=node.title,
                content=node.content,
                source="alexandrie",
                metadata={
                    "node_type": node.node_type.value,
                    "parent_id": node.parent_id,
                    "owner_id": node.owner_id,
                    "is_public": node.is_public,
                    "tags": node.tags,
                    "alexandrie_url": f"{self.config.base_url.rstrip('/')}/nodes/{node.id}",
                },
            )
            entry.content_hash = content_hash
            entry.version = node.version
            entry.sync_status = SyncStatus.SYNCED
            entry.last_synced_at = datetime.now(timezone.utc)

            self._documents[entry.id] = entry
            self._external_index[node.id] = entry.id
            self.cache.put(node.id, entry)

            # Knowledge graph: parent-child edge
            if node.parent_id:
                self._graph_edges.append(KnowledgeGraphEdge(source_id=node.id, target_id=node.parent_id, relation="child_of"))

            self._record_sync_event("document_created", node.id, SyncStatus.SYNCED, {})
            self._publish("alexandrie.document.created", {"id": node.id, "title": node.title})
            return entry

    def sync_all_documents(self, user_id: str, incremental: bool = True) -> dict[str, Any]:
        """Sync all documents from Alexandrie for a user.

        Incremental mode: only sync documents changed since last sync.
        """
        if not self._check_circuit():
            self._publish("alexandrie.sync.failed", {"user_id": user_id, "reason": "circuit_open"}, severity="error")
            return {"synced": 0, "failed": 0, "error": "circuit_breaker_open"}

        self._publish("alexandrie.sync.started", {"user_id": user_id, "incremental": incremental})

        since = self._last_sync_at if incremental else None
        try:
            nodes = self.client.list_nodes(user_id, since=since)
            synced = 0
            failed = 0

            for node in nodes:
                try:
                    self.sync_document(node)
                    synced += 1
                except Exception:
                    failed += 1

            self._last_sync_at = datetime.now(timezone.utc)
            self._record_success()
            self._publish("alexandrie.sync.completed", {"user_id": user_id, "synced": synced, "failed": failed})
            return {"synced": synced, "failed": failed}

        except Exception as e:
            self._record_failure()
            self._publish("alexandrie.sync.failed", {"user_id": user_id, "error": str(e)}, severity="error")
            return {"synced": 0, "failed": 0, "error": str(e)}

    def unsync_document(self, alexandrie_id: str) -> bool:
        """Remove document from Hermes memory."""
        with self._lock:
            herm_id = self._external_index.pop(alexandrie_id, None)
            if herm_id and herm_id in self._documents:
                del self._documents[herm_id]
                self.cache.remove(alexandrie_id)
                self._record_sync_event("document_deleted", alexandrie_id, SyncStatus.NOT_SYNCED, {})
                self._publish("alexandrie.document.deleted", {"id": alexandrie_id})
                return True
        return False

    def mark_outdated(self, alexandrie_id: str) -> bool:
        """Mark a document as needing re-sync."""
        with self._lock:
            herm_id = self._external_index.get(alexandrie_id)
            if herm_id and herm_id in self._documents:
                self._documents[herm_id].sync_status = SyncStatus.OUTDATED
                return True
        return False

    # ── Search ─────────────────────────────────────────────────────

    def full_text_search(self, query: str, limit: int = 20) -> AlexandrieSearchResult:
        if not self._check_circuit():
            return AlexandrieSearchResult(query=query)
        return self.client.search(query, include_content=True, limit=limit)

    def semantic_search(self, query: str, limit: int = 10) -> list[DocumentMemoryEntry]:
        """Keyword-based semantic search (stub — real embeddings future)."""
        query_lower = query.lower()
        results: list[tuple[float, DocumentMemoryEntry]] = []

        # Check cache first
        for entry in list(self._documents.values()):
            score = 0.0
            if query_lower in entry.title.lower():
                score += 0.5
            if query_lower in entry.content.lower():
                score += 0.3
            for tag in entry.metadata.get("tags", []):
                if query_lower in tag.lower():
                    score += 0.1
            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:limit]]

    def hybrid_search(self, query: str, limit: int = 10) -> HybridSearchResult:
        ft_result = self.full_text_search(query, limit)
        sem_results = self.semantic_search(query, limit)

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for node in ft_result.nodes:
            seen.add(node.id)
            merged.append({"source": "alexandrie", "id": node.id, "title": node.title, "content": node.content[:500], "score": 1.0, "match_type": "full_text"})
        for entry in sem_results:
            if entry.external_id not in seen:
                merged.append({"source": "hermes", "id": entry.external_id, "title": entry.title, "content": entry.content[:500], "score": 0.8, "match_type": "semantic"})

        return HybridSearchResult(query=query, full_text_results=ft_result.nodes, semantic_results=sem_results, merged_results=merged[:limit], total=len(merged))

    # ── Mission Integration ────────────────────────────────────────

    def link_document_to_mission(self, alexandrie_id: str, mission_id: str) -> bool:
        """Link a document to a mission for the Mission Planner."""
        with self._lock:
            if alexandrie_id not in self._external_index:
                return False
            herm_id = self._external_index[alexandrie_id]
            entry = self._documents.get(herm_id)
            if entry and mission_id not in entry.linked_mission_ids:
                entry.linked_mission_ids.append(mission_id)

            if mission_id not in self._mission_docs:
                self._mission_docs[mission_id] = []
            if alexandrie_id not in self._mission_docs[mission_id]:
                self._mission_docs[mission_id].append(alexandrie_id)
                self._graph_edges.append(KnowledgeGraphEdge(source_id=mission_id, target_id=alexandrie_id, relation="references", weight=0.8))
            return True

    def get_mission_documents(self, mission_id: str) -> list[dict[str, Any]]:
        """Get all documents linked to a mission."""
        doc_ids = self._mission_docs.get(mission_id, [])
        result: list[dict[str, Any]] = []
        for aid in doc_ids:
            cached = self.cache.get(aid)
            if cached:
                result.append({"id": aid, "title": cached.title, "status": cached.sync_status.value})
            else:
                herm_id = self._external_index.get(aid)
                if herm_id and herm_id in self._documents:
                    e = self._documents[herm_id]
                    result.append({"id": aid, "title": e.title, "status": e.sync_status.value})
        return result

    def find_relevant_documents(self, mission_tags: list[str], limit: int = 10) -> list[dict[str, Any]]:
        """Find documents relevant to a mission by tag/keyword matching."""
        scored: list[tuple[int, DocumentMemoryEntry]] = []
        for entry in self._documents.values():
            score = sum(1 for t in mission_tags if t.lower() in entry.title.lower() or any(t.lower() in tag.lower() for tag in entry.metadata.get("tags", [])))
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": e.external_id, "title": e.title, "relevance": s} for s, e in scored[:limit]]

    # ── Knowledge Graph ────────────────────────────────────────────

    def get_graph_edges(self) -> list[dict[str, Any]]:
        return [{"source": e.source_id, "target": e.target_id, "relation": e.relation, "weight": e.weight} for e in self._graph_edges]

    def get_graph_for_node(self, alexandrie_id: str) -> list[dict[str, Any]]:
        return [{"source": e.source_id, "target": e.target_id, "relation": e.relation} for e in self._graph_edges if e.source_id == alexandrie_id or e.target_id == alexandrie_id]

    # ── Cache Management ───────────────────────────────────────────

    def cache_stats(self) -> dict[str, Any]:
        return self.cache.stats()

    def prune_cache(self) -> int:
        return self.cache.prune_expired()

    # ── Health & Stats ─────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        return self.client.health_check()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alexandrie_health": self.health_check(),
                "documents_synced": len(self._external_index),
                "documents_indexed": len(self._documents),
                "graph_edges": len(self._graph_edges),
                "cache": self.cache.stats(),
                "circuit_breaker": {"open": self._circuit_open, "failures": self._failure_count},
                "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
                "events_count": len(self._events),
            }

    def get_sync_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [{"type": e.event_type, "doc_id": e.document_id, "status": e.sync_status.value, "timestamp": e.timestamp.isoformat()} for e in list(self._sync_events)[-limit:]]

    def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)[-limit:]

    def get_linked_documents_for_mission(self, mission_id: str) -> list[dict[str, Any]]:
        return self.get_mission_documents(mission_id)

    # ── Statistics ─────────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        """Return adapter statistics."""
        with self._lock:
            return {
                "documents_synced": len(self._external_index),
                "documents_indexed": len(self._documents),
                "graph_edges": len(self._graph_edges),
                "cache_entries": self.cache.size(),
                "events_count": len(self._events),
                "sync_events_count": len(self._sync_events),
                "mission_links": len(self._mission_docs),
                "circuit_breaker": {
                    "open": self._circuit_open,
                    "failures": self._failure_count,
                },
            }

    def get_synced_documents(self) -> list[dict[str, Any]]:
        """Return all synced documents."""
        with self._lock:
            return [
                {
                    "id": entry.external_id,
                    "title": entry.title,
                    "source": entry.source,
                    "sync_status": entry.sync_status.value,
                    "version": entry.version,
                }
                for entry in self._documents.values()
            ]

    # ── Document CRUD passthrough ──────────────────────────────────

    def create_document(self, title: str, content: str, user_id: str = "", is_public: bool = False) -> Optional[AlexandrieNode]:
        if not self._check_circuit():
            return None
        node = AlexandrieNode(title=title, content=content, is_public=is_public)
        result = self.client.create_node(node)
        if result:
            self.sync_document(result)
        else:
            self._record_failure()
        return result

    def update_document(self, node_id: str, title: str = "", content: str = "") -> Optional[AlexandrieNode]:
        if not self._check_circuit():
            return None
        node = AlexandrieNode(title=title, content=content)
        result = self.client.update_node(node_id, node)
        if result:
            self.sync_document(result)
        else:
            self._record_failure()
        return result

    def get_document(self, node_id: str) -> Optional[AlexandrieNode]:
        cached = self.cache.get(node_id)
        if cached:
            return AlexandrieNode(id=cached.external_id, title=cached.title, content=cached.content)
        return self.client.get_node(node_id)

    def delete_document(self, node_id: str) -> bool:
        success = self.client.delete_node(node_id)
        if success:
            self.unsync_document(node_id)
        return success


_adapter_instance: Optional[HermesAlexandrieAdapter] = None
_adapter_lock = threading.Lock()


def get_alexandrie_adapter(config: Optional[AlexandrieConfig] = None) -> HermesAlexandrieAdapter:
    global _adapter_instance
    if _adapter_instance is None:
        with _adapter_lock:
            if _adapter_instance is None:
                _adapter_instance = HermesAlexandrieAdapter(config)
    return _adapter_instance
