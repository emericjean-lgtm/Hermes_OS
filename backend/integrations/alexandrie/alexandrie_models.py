"""Alexandrie integration models — HOS-053B production.

Full sync state machine, versioning, conflict detection, and
document lifecycle management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ──────────────────────────────────────────────────────────

class AlexandrieNodeType(str, Enum):
    WORKSPACE = "workspace"
    CATEGORY = "category"
    DOCUMENT = "document"


class AlexandrieAccessLevel(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


class SyncStatus(str, Enum):
    """Document sync state machine."""
    NOT_SYNCED = "not_synced"       # Never synced
    SYNCING = "syncing"              # Sync in progress
    SYNCED = "synced"                # Successfully synced
    OUTDATED = "outdated"            # Source changed, needs re-sync
    CONFLICT = "conflict"            # Both sides modified
    FAILED = "failed"                # Sync error
    DELETED_REMOTE = "deleted_remote"  # Document removed from Alexandrie


class ConflictResolution(str, Enum):
    """Conflict resolution strategies."""
    SOURCE_WINS = "source_wins"       # Alexandrie overwrites Hermes
    LOCAL_WINS = "local_wins"         # Hermes keeps its version
    LAST_WRITE_WINS = "last_write_wins"
    MANUAL = "manual"                 # Human decides


class CacheEvictionPolicy(str, Enum):
    LRU = "lru"
    TTL = "ttl"
    FIFO = "fifo"


# ── Alexandrie Document ────────────────────────────────────────────

@dataclass
class AlexandrieNode:
    """Mirrors Alexandrie's Go models.Node."""
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    content: str = ""
    node_type: AlexandrieNodeType = AlexandrieNodeType.DOCUMENT
    parent_id: Optional[str] = None
    workspace_id: Optional[str] = None
    owner_id: str = ""
    access_level: AlexandrieAccessLevel = AlexandrieAccessLevel.READ
    is_public: bool = False
    tags: list[str] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    search_relevance: float = 0.0


@dataclass
class AlexandrieSearchResult:
    query: str = ""
    nodes: list[AlexandrieNode] = field(default_factory=list)
    total: int = 0
    took_ms: float = 0.0


# ── Hermes Document Memory Entry ───────────────────────────────────

class DocumentMemoryEntry:
    """Hermes-side representation of an indexed document."""
    def __init__(
        self,
        external_id: str,
        title: str = "",
        content: str = "",
        source: str = "alexandrie",
        embedding: Optional[list[float]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.id: str = str(uuid4())
        self.external_id = external_id
        self.title = title
        self.content = content
        self.content_hash: str = ""
        self.source = source
        self.embedding = embedding or []
        self.metadata = metadata or {}
        self.version: int = 1
        self.sync_status: SyncStatus = SyncStatus.NOT_SYNCED
        self.indexed_at: datetime = datetime.now(timezone.utc)
        self.last_synced_at: Optional[datetime] = None
        self.sync_error: Optional[str] = None
        self.conflict_info: Optional[dict[str, Any]] = None
        self.linked_mission_ids: list[str] = []


class KnowledgeGraphEdge:
    """Edge in Hermes Knowledge Graph."""
    def __init__(self, source_id: str, target_id: str, relation: str = "references", weight: float = 1.0):
        self.source_id = source_id
        self.target_id = target_id
        self.relation = relation
        self.weight = weight


@dataclass
class HybridSearchResult:
    query: str = ""
    full_text_results: list[AlexandrieNode] = field(default_factory=list)
    semantic_results: list[DocumentMemoryEntry] = field(default_factory=list)
    merged_results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    took_ms: float = 0.0


# ── Sync Events ────────────────────────────────────────────────────

@dataclass
class SyncEvent:
    """Immutable sync event for audit trail."""
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""        # created, updated, deleted, sync_started, etc.
    document_id: str = ""
    synced_by: str = "hermes"
    sync_status: SyncStatus = SyncStatus.NOT_SYNCED
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Configuration ──────────────────────────────────────────────────

@dataclass
class AlexandrieConfig:
    base_url: str = "http://localhost:8200"
    api_path: str = "/api"
    api_key: Optional[str] = None
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"
    timeout_seconds: float = 30.0
    connect_timeout: float = 5.0
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    retry_backoff_max: float = 30.0
    health_check_interval_seconds: float = 30.0
    cache_max_entries: int = 1000
    cache_ttl_seconds: float = 300.0
    cache_eviction: CacheEvictionPolicy = CacheEvictionPolicy.TTL
    sync_batch_size: int = 50
    sync_max_concurrency: int = 4
