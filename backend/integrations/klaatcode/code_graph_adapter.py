"""Code Knowledge Graph Adapter (HOS-054D).

Bridges KlaatCode code analysis results into the Hermes Knowledge Graph (HOS-047).
Transforms code structure (files, classes, functions, dependencies) into
navigable knowledge nodes and edges.

Relations:
- FILE_IMPORTS: between files
- CLASS_CONTAINS: class contains methods/fields
- FUNCTION_CALLS: function calls another
- DEPENDS_ON: module/file dependency
- MODIFIED_BY_AGENT: agent modified this entity
- TESTED_BY: test file covers this entity
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import KnowledgeNode


# ── Relation constants ──────────────────────────────────────

class CodeRelation:
    FILE_IMPORTS = "FILE_IMPORTS"
    CLASS_CONTAINS = "CLASS_CONTAINS"
    FUNCTION_CALLS = "FUNCTION_CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    MODIFIED_BY_AGENT = "MODIFIED_BY_AGENT"
    TESTED_BY = "TESTED_BY"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"


# ── Data classes ────────────────────────────────────────────

@dataclass
class CodeEntity:
    """A code entity extracted from KlaatCode analysis."""
    entity_id: str = ""
    name: str = ""
    entity_type: str = ""  # file, class, function, module, test
    file_path: str = ""
    language: str = ""
    line_start: int = 0
    line_end: int = 0
    parent_id: str = ""
    agent_id: str = ""
    mission_id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeRelationship:
    """Relationship between two code entities."""
    source_id: str = ""
    target_id: str = ""
    relation: str = ""
    weight: float = 1.0


# ── Adapter ─────────────────────────────────────────────────

class CodeGraphAdapter:
    """Transforms KlaatCode analysis into Knowledge Graph nodes and edges.

    Thread-safe. Connects to KnowledgeGraph (HOS-047).
    """

    def __init__(
        self,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._kg = knowledge_graph
        self._on_event = on_event
        self._entities: dict[str, CodeEntity] = {}
        self._relationships: list[CodeRelationship] = []
        self._indexed_count = 0

    # ── Indexing ────────────────────────────────────────────

    def index_analysis(
        self,
        analysis_data: dict[str, Any],
        agent_id: str = "",
        mission_id: str = "",
    ) -> dict[str, int]:
        """Index a KlaatCode project analysis into the Knowledge Graph.

        Args:
            analysis_data: Parsed KlaatCode analysis result.
            agent_id: The agent that performed the analysis.
            mission_id: Parent mission.

        Returns:
            Dict with counts: files, classes, functions, edges.
        """
        files = analysis_data.get("files", [])
        project = analysis_data.get("project", {})
        lang = project.get("language", "")

        nodes_added = 0
        edges_added = 0

        for file_info in files:
            file_path = file_info.get("path", "")
            if not file_path:
                continue

            # Create file node
            file_node = KnowledgeNode(
                node_type="file",
                label=file_path,
                properties={
                    "path": file_path,
                    "language": lang,
                    "agent_id": agent_id,
                    "mission_id": mission_id,
                    "entity_type": "file",
                },
            )
            if self._kg:
                self._kg.add_node(file_node)
            self._entities[file_node.node_id] = CodeEntity(
                entity_id=file_node.node_id, name=file_path,
                entity_type="file", file_path=file_path, language=lang,
                agent_id=agent_id, mission_id=mission_id,
            )
            nodes_added += 1

            # Index classes
            for cls in file_info.get("classes", []):
                cls_name = cls.get("name", "")
                cls_node = KnowledgeNode(
                    node_type="class",
                    label=f"{file_path}::{cls_name}",
                    properties={
                        "name": cls_name,
                        "file": file_path,
                        "language": lang,
                        "agent_id": agent_id,
                        "entity_type": "class",
                    },
                )
                if self._kg:
                    self._kg.add_node(cls_node)
                    self._kg.add_edge(file_node.node_id, cls_node.node_id,
                                      CodeRelation.CLASS_CONTAINS)
                nodes_added += 1
                edges_added += 1

            # Index functions
            for func in file_info.get("functions", []):
                func_name = func.get("name", "")
                func_node = KnowledgeNode(
                    node_type="function",
                    label=f"{file_path}::{func_name}",
                    properties={
                        "name": func_name,
                        "file": file_path,
                        "language": lang,
                        "agent_id": agent_id,
                        "entity_type": "function",
                    },
                )
                if self._kg:
                    self._kg.add_node(func_node)
                nodes_added += 1

            # Index imports
            for imp in file_info.get("imports", []):
                target = imp.get("module", "") or imp.get("file", "")
                if target and file_path != target:
                    # Find or create target node
                    target_id = self._find_or_create_file_node(target, lang, agent_id, mission_id)
                    if self._kg and target_id:
                        self._kg.add_edge(file_node.node_id, target_id, CodeRelation.FILE_IMPORTS)
                    edges_added += 1

            # Index dependencies
            for dep in file_info.get("dependencies", []):
                dep_name = dep.get("name", "")
                if dep_name:
                    dep_id = self._find_or_create_file_node(dep_name, lang, agent_id, mission_id)
                    if self._kg and dep_id:
                        self._kg.add_edge(file_node.node_id, dep_id, CodeRelation.DEPENDS_ON)
                    edges_added += 1

        # Record agent modification edges
        if agent_id:
            agent_node = KnowledgeNode(
                node_type="agent",
                label=f"agent:{agent_id}",
                properties={"agent_id": agent_id},
            )
            if self._kg:
                self._kg.add_node(agent_node)
                with self._lock:
                    entities_copy = list(self._entities.items())
                for eid, entity in entities_copy:
                    if entity.agent_id == agent_id and entity.entity_type == "file":
                        self._kg.add_edge(agent_node.node_id, entity.entity_id,
                                         CodeRelation.MODIFIED_BY_AGENT)

        with self._lock:
            self._indexed_count += 1

        if self._on_event:
            self._on_event("klaatcode.graph.indexed", {
                "nodes_added": nodes_added,
                "edges_added": edges_added,
                "agent_id": agent_id,
                "mission_id": mission_id,
            }, severity="info")

        return {"files": len(files), "classes": 0, "functions": 0,
                "nodes": nodes_added, "edges": edges_added}

    def add_test_relation(
        self, source_file: str, test_file: str, agent_id: str = ""
    ) -> bool:
        """Add a TESTED_BY relation between a source file and its test."""
        src_id = self._find_or_create_file_node(source_file, "", agent_id, "")
        tst_id = self._find_or_create_file_node(test_file, "", agent_id, "")
        if src_id and tst_id and self._kg:
            self._kg.add_edge(tst_id, src_id, CodeRelation.TESTED_BY)
            return True
        return False

    # ── Query ────────────────────────────────────────────────

    def get_file_graph(self, file_path: str) -> dict:
        """Get the subgraph centered on a file."""
        if not self._kg:
            return {"nodes": [], "edges": []}
        node = self._find_file_node(file_path)
        if node is None:
            return {"nodes": [], "edges": []}
        return self._kg.traverse(node.node_id, max_depth=2)

    def get_agent_modifications(self, agent_id: str) -> list[dict]:
        """Get all files modified by an agent."""
        with self._lock:
            return [
                {"entity_id": e.entity_id, "name": e.name, "type": e.entity_type,
                 "file_path": e.file_path, "language": e.language}
                for e in self._entities.values()
                if e.agent_id == agent_id
            ]

    def search_code_entities(self, query: str) -> list[dict]:
        """Search code entities by name."""
        results = []
        q = query.lower()
        with self._lock:
            for e in self._entities.values():
                if q in e.name.lower():
                    results.append({
                        "entity_id": e.entity_id, "name": e.name,
                        "type": e.entity_type, "file_path": e.file_path,
                        "language": e.language,
                    })
        return results[:20]

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_entities": len(self._entities),
                "total_relationships": len(self._relationships),
                "analyses_indexed": self._indexed_count,
                "by_type": {
                    t: sum(1 for e in self._entities.values() if e.entity_type == t)
                    for t in set(e.entity_type for e in self._entities.values())
                },
            }

    # ── Helpers ──────────────────────────────────────────────

    def _find_or_create_file_node(
        self, path: str, language: str, agent_id: str, mission_id: str
    ) -> str:
        """Find an existing file node or create one."""
        existing = self._find_file_node(path)
        if existing:
            return existing.node_id

        node = KnowledgeNode(
            node_type="file",
            label=path,
            properties={
                "path": path, "language": language,
                "agent_id": agent_id, "mission_id": mission_id,
                "entity_type": "file",
            },
        )
        if self._kg:
            self._kg.add_node(node)
        self._entities[node.node_id] = CodeEntity(
            entity_id=node.node_id, name=path, entity_type="file",
            file_path=path, language=language,
            agent_id=agent_id, mission_id=mission_id,
        )
        return node.node_id

    def _find_file_node(self, path: str) -> Optional[KnowledgeNode]:
        if not self._kg:
            return None
        nodes = self._kg.find_nodes(node_type="file", label_contains=path)
        for n in nodes:
            if n.label == path or n.properties.get("path") == path:
                return n
        return None
