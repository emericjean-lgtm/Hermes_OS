"""Knowledge Graph for HOS-047 — navigable graph connecting all Hermes entities."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable, Optional

from backend.memory.memory_models import KnowledgeEdge, KnowledgeNode


class KnowledgeGraph:
    """Thread-safe knowledge graph connecting missions, tasks, agents, runtimes,
    models, skills, workspaces, docs, benchmarks, decisions, incidents.

    Navigable via BFS/DFS from any node.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        # Adjacency for traversal
        self._outgoing: dict[str, list[str]] = defaultdict(list)  # node → edge IDs
        self._incoming: dict[str, list[str]] = defaultdict(list)

    def add_node(self, node: KnowledgeNode) -> KnowledgeNode:
        with self._lock:
            self._nodes[node.node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> Optional[KnowledgeEdge]:
        with self._lock:
            if source_id not in self._nodes or target_id not in self._nodes:
                return None
            edge = KnowledgeEdge(source_id=source_id, target_id=target_id, relation=relation, weight=weight)
            self._edges[edge.edge_id] = edge
            self._outgoing[source_id].append(edge.edge_id)
            self._incoming[target_id].append(edge.edge_id)

        if self._on_event:
            self._on_event("graph.updated", {"relation": relation, "source": source_id, "target": target_id}, severity="info")
        return edge

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        return self._nodes.get(node_id)

    def find_nodes(self, node_type: str = "", label_contains: str = "") -> list[KnowledgeNode]:
        with self._lock:
            results = list(self._nodes.values())
        if node_type:
            results = [n for n in results if n.node_type == node_type]
        if label_contains:
            q = label_contains.lower()
            results = [n for n in results if q in n.label.lower()]
        return results

    def get_neighbors(self, node_id: str, relation: str = "") -> list[KnowledgeNode]:
        """Get all neighbors with optional relation filter."""
        with self._lock:
            neighbors = []
            for eid in self._outgoing.get(node_id, []):
                edge = self._edges.get(eid)
                if edge and (not relation or edge.relation == relation):
                    node = self._nodes.get(edge.target_id)
                    if node:
                        neighbors.append(node)
            for eid in self._incoming.get(node_id, []):
                edge = self._edges.get(eid)
                if edge and (not relation or edge.relation == relation):
                    node = self._nodes.get(edge.source_id)
                    if node:
                        neighbors.append(node)
        return neighbors

    def traverse(self, start_id: str, max_depth: int = 3) -> dict[str, any]:
        """BFS traversal returning connected subgraph."""
        visited: set[str] = set()
        nodes: list[dict] = []
        edges: list[dict] = []
        queue = [(start_id, 0)]

        with self._lock:
            while queue:
                nid, depth = queue.pop(0)
                if nid in visited or depth > max_depth:
                    continue
                visited.add(nid)
                node = self._nodes.get(nid)
                if node:
                    nodes.append({"id": node.node_id, "type": node.node_type, "label": node.label})
                for eid in self._outgoing.get(nid, []) + self._incoming.get(nid, []):
                    edge = self._edges.get(eid)
                    if edge:
                        edges.append({"source": edge.source_id, "target": edge.target_id, "relation": edge.relation})
                        if edge.source_id not in visited:
                            queue.append((edge.source_id, depth + 1))
                        if edge.target_id not in visited:
                            queue.append((edge.target_id, depth + 1))

        return {"nodes": nodes, "edges": edges, "traversal_depth": max_depth}

    def get_all_edges(self) -> list[KnowledgeEdge]:
        with self._lock:
            return list(self._edges.values())

    def stats(self) -> dict:
        with self._lock:
            return {"total_nodes": len(self._nodes), "total_edges": len(self._edges),
                    "by_type": {t: sum(1 for n in self._nodes.values() if n.node_type == t) for t in
                                set(n.node_type for n in self._nodes.values())}}
