"""Mission Graph Engine — DAG construction, validation, cycle detection (HOS-041)."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionStatus,
)


class MissionGraph:
    """DAG representation of a mission.

    Handles construction, validation, cycle detection, and topological ordering.
    """

    def __init__(self) -> None:
        self._missions: dict[str, Mission] = {}

    # ── Build ───────────────────────────────────────────────

    def build_graph(
        self,
        mission: Mission,
        nodes: list[MissionNode],
        edges: list[MissionEdge],
    ) -> None:
        """Build the DAG from nodes and edges."""
        mission.nodes = list(nodes)
        mission.edges = list(edges)
        # Auto-populate depends_on from edges
        for node in mission.nodes:
            node.depends_on = [
                e.source_id for e in mission.edges if e.target_id == node.node_id
            ]
        self._missions[mission.mission_id] = mission

    def add_node(self, mission: Mission, node: MissionNode) -> None:
        mission.nodes.append(node)

    def add_edge(self, mission: Mission, source_id: str, target_id: str) -> Optional[MissionEdge]:
        """Add a dependency edge source → target."""
        src = self._find_node(mission, source_id)
        tgt = self._find_node(mission, target_id)
        if src is None or tgt is None:
            return None
        edge = MissionEdge(source_id=source_id, target_id=target_id)
        mission.edges.append(edge)
        tgt.depends_on.append(source_id)
        return edge

    # ── Validation ──────────────────────────────────────────

    def validate_graph(self, mission: Mission) -> list[str]:
        """Validate the DAG. Returns list of issues (empty = valid)."""
        issues: list[str] = []

        # Check node IDs exist in edges
        node_ids = {n.node_id for n in mission.nodes}
        for edge in mission.edges:
            if edge.source_id not in node_ids:
                issues.append(f"Edge source '{edge.source_id}' not in nodes")
            if edge.target_id not in node_ids:
                issues.append(f"Edge target '{edge.target_id}' not in nodes")

        # Cycle detection
        if self._detect_cycles(mission):
            issues.append("Graph contains cycles — must be a DAG")

        # Orphan nodes (no edges)
        if mission.edges:
            in_edges = {e.target_id for e in mission.edges}
            out_edges = {e.source_id for e in mission.edges}
            for node in mission.nodes:
                nid = node.node_id
                if nid not in in_edges and nid not in out_edges:
                    # Single-node mission is valid
                    if len(mission.nodes) > 1:
                        issues.append(f"Orphan node '{nid}' ({node.title}) — no edges")

        if not issues:
            mission.status = MissionStatus.VALIDATED

        return issues

    def _detect_cycles(self, mission: Mission) -> bool:
        """Returns True if the graph contains a cycle."""
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in mission.edges:
            adjacency[edge.source_id].append(edge.target_id)

        # Kahn's algorithm
        in_degree: dict[str, int] = defaultdict(int)
        for u in adjacency:
            for v in adjacency[u]:
                in_degree[v] += 1

        # All nodes must be in in_degree
        for node in mission.nodes:
            in_degree.setdefault(node.node_id, 0)
            adjacency.setdefault(node.node_id, [])

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        visited = 0

        while queue:
            u = queue.popleft()
            visited += 1
            for v in adjacency[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        return visited != len(mission.nodes)

    # ── Topological Sort ────────────────────────────────────

    def topological_sort(self, mission: Mission) -> list[str]:
        """Return node IDs in topological order (Kahn's algorithm)."""
        adjacency: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = defaultdict(int)

        for edge in mission.edges:
            adjacency[edge.source_id].append(edge.target_id)
            in_degree[edge.target_id] += 1

        for node in mission.nodes:
            in_degree.setdefault(node.node_id, 0)
            adjacency.setdefault(node.node_id, [])

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while queue:
            u = queue.popleft()
            order.append(u)
            for v in adjacency[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        return order

    # ── Helpers ─────────────────────────────────────────────

    def _find_node(self, mission: Mission, node_id: str) -> Optional[MissionNode]:
        for n in mission.nodes:
            if n.node_id == node_id:
                return n
        return None
