"""Memory & Knowledge Graph models for HOS-047."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class MemoryType(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    DOCUMENT = "document"


class MemoryEntry:
    """Base memory entry."""

    def __init__(
        self,
        memory_id: str = "",
        memory_type: MemoryType = MemoryType.WORKING,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ):
        self.memory_id = memory_id or uuid4().hex
        self.memory_type = memory_type
        self.tags = tags or []
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at: Optional[datetime] = None
        self.score: float = 0.0


@dataclass
class WorkingMemory:
    """Active mission context — cleared after mission completion."""

    memory_id: str = field(default_factory=lambda: uuid4().hex)
    mission_id: str = ""
    agent_id: str = ""
    # Current state
    active_nodes: list[str] = field(default_factory=list)
    conversations: list[dict] = field(default_factory=list)
    runtime_decisions: list[dict] = field(default_factory=list)
    agent_states: dict[str, str] = field(default_factory=dict)
    # Transient
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EpisodicMemory:
    """Mission-level experiences: successes, failures, incidents, decisions."""

    episode_id: str = field(default_factory=lambda: uuid4().hex)
    mission_id: str = ""
    mission_title: str = ""
    mission_type: str = ""
    # Outcome
    success: bool = True
    total_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    duration_seconds: float = 0.0
    # Details
    agents_used: list[str] = field(default_factory=list)
    runtimes_used: list[str] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    # Learning
    lessons_learned: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    # Indexing
    tags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SemanticMemory:
    """Concepts, technologies, frameworks, patterns."""

    concept_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    category: str = ""  # technology, framework, pattern, tool, architecture
    description: str = ""
    # Relations
    related_concepts: list[str] = field(default_factory=list)
    used_in_missions: list[str] = field(default_factory=list)
    # Metadata
    tags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProceduralMemory:
    """Workflows, best practices, templates, resolution strategies."""

    procedure_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    category: str = ""  # workflow, best_practice, template, strategy
    # Content
    steps: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    # Versioning
    version: int = 1
    # Provenance
    derived_from_missions: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0
    tags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DocumentMemory:
    """Indexed documentation, code, specs, architecture."""

    document_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    path: str = ""
    content_type: str = ""  # markdown, pdf, code, readme, spec, architecture
    content: str = ""
    summary: str = ""
    # Chunking
    chunk_index: int = 0
    total_chunks: int = 1
    # Source
    mission_id: str = ""
    workspace_id: str = ""
    tags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph."""

    node_id: str = field(default_factory=lambda: uuid4().hex)
    node_type: str = ""  # mission, task, agent, runtime, model, skill, workspace, doc, benchmark, decision, incident
    label: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEdge:
    """An edge in the knowledge graph."""

    edge_id: str = field(default_factory=lambda: uuid4().hex)
    source_id: str = ""
    target_id: str = ""
    relation: str = ""  # used_in, depends_on, produced_by, reviewed_by, similar_to
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A hybrid search result."""

    result_id: str = field(default_factory=lambda: uuid4().hex)
    source_type: str = ""  # episodic, semantic, procedural, document, graph
    source_id: str = ""
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    justification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
