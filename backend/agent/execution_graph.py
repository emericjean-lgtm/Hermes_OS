"""Agent Execution Graph — DAG-based task orchestration (HOS-017).

Provides a thread-safe, validated DAG for orchestrating multi-step agent
workflows. Nodes represent agent tasks; edges represent dependencies and
execution order.

The graph is independent of the Runtime Abstraction Layer (RAL) but is
designed to be used alongside it: each node references a *runtime
capability* that the RuntimeLayer can resolve.

No concrete agent (Coder, QA, Documentation, etc.) is imported here.
"""
from __future__ import annotations

import json
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class NodeStatus(str, Enum):
    """Lifecycle status of an agent node."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeType(str, Enum):
    """Canonical node types for agent tasks."""

    TASK = "task"
    DECISION = "decision"
    PARALLEL = "parallel"
    SUBGRAPH = "subgraph"
    OBSERVER = "observer"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentNode:
    """An immutable node in an execution graph.

    Attributes:
        id: Unique node identifier.
        name: Human-readable name.
        type: Node type (task, decision, parallel, …).
        status: Current lifecycle status.
        runtime_capability: The RAL capability required to execute this
            node (e.g. ``"chat"``, ``"code"``, ``"review"``).
        metadata: Free-form payload (inputs, configuration, …).
    """

    id: str
    name: str
    type: NodeType | str = NodeType.TASK
    status: NodeStatus | str = NodeStatus.PENDING
    runtime_capability: str = "chat"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentEdge:
    """A directed edge between two nodes.

    Attributes:
        source: Source node id.
        target: Target node id.
        condition: Optional condition expression (string or dict).
            An empty string means unconditional.
        metadata: Free-form metadata.
    """

    source: str
    target: str
    condition: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExecutionGraphError(Exception):
    """Raised when a graph operation is invalid."""


class CycleError(ExecutionGraphError):
    """Raised when a cycle is detected in the graph."""


class ValidationError(ExecutionGraphError):
    """Raised when graph validation fails."""


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class ExecutionGraphValidator:
    """Stateless graph validation logic.

    All methods return lists of error messages; an empty list means the
    check passed.
    """

    @staticmethod
    def detect_cycles(nodes: dict[str, AgentNode], edges: list[AgentEdge]) -> list[str]:
        """Return error messages for every cycle found using Kahn's algorithm.

        Args:
            nodes: Mapping of node id → AgentNode.
            edges: List of all edges.

        Returns:
            A list of error descriptions, or an empty list if the graph
            is acyclic.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}

        for edge in edges:
            if edge.source in adjacency and edge.target in in_degree:
                adjacency[edge.source].append(edge.target)
                in_degree[edge.target] += 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        visited = 0

        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(nodes):
            cycled_nodes = [nid for nid, deg in in_degree.items() if deg > 0]
            return [f"Cycle detected involving nodes: {cycled_nodes}"]
        return []

    @staticmethod
    def check_invalid_references(
        nodes: dict[str, AgentNode],
        edges: list[AgentEdge],
    ) -> list[str]:
        """Return errors for edges referencing non-existent nodes."""
        errors: list[str] = []
        for edge in edges:
            if edge.source not in nodes:
                errors.append(f"Edge source '{edge.source}' does not exist.")
            if edge.target not in nodes:
                errors.append(f"Edge target '{edge.target}' does not exist.")
        return errors

    @staticmethod
    def check_orphan_nodes(
        nodes: dict[str, AgentNode],
        edges: list[AgentEdge],
    ) -> list[str]:
        """Return errors for islands: nodes with no incoming *or* outgoing
        edges when at least one edge exists in the graph.

        A flat graph (zero edges) is **not** orphan — all nodes are
        independent roots and that is a valid DAG.  Similarly, a graph
        with a single node is valid.
        """
        if len(nodes) <= 1 or not edges:
            return []

        has_incoming: set[str] = {e.target for e in edges}
        has_outgoing: set[str] = {e.source for e in edges}
        connected = has_incoming | has_outgoing

        orphans = [nid for nid in nodes if nid not in connected]
        if orphans:
            return [f"Orphan node(s): {orphans}"]
        return []

    @staticmethod
    def validate(
        nodes: dict[str, AgentNode],
        edges: list[AgentEdge],
    ) -> list[str]:
        """Run all validation checks and return combined errors."""
        errors: list[str] = []
        errors.extend(ExecutionGraphValidator.check_invalid_references(nodes, edges))
        errors.extend(ExecutionGraphValidator.detect_cycles(nodes, edges))
        errors.extend(ExecutionGraphValidator.check_orphan_nodes(nodes, edges))
        return errors


# ---------------------------------------------------------------------------
# Execution Plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphExecutionPlan:
    """A derived execution plan produced from a validated graph.

    Attributes:
        execution_order: Nodes in topologically-sorted execution order.
        levels: Nodes grouped by topological level (level 0 = no deps,
            level 1 = depends on level 0, etc.). Each level can run in
            parallel.
        dependencies: Mapping from node id to list of dependency node ids.
        stats: Summary statistics (node count, edge count, levels, …).
    """

    execution_order: tuple[str, ...] = ()
    levels: tuple[frozenset[str], ...] = ()
    dependencies: dict[str, tuple[str, ...]] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Execution Graph
# ---------------------------------------------------------------------------


class ExecutionGraph:
    """Thread-safe DAG of agent nodes.

    The graph enforces no cycles and no duplicate IDs on write operations.
    Edges are stored in insertion order.

    Args:
        nodes: Optional initial nodes.
        edges: Optional initial edges.
    """

    def __init__(
        self,
        nodes: Optional[list[AgentNode]] = None,
        edges: Optional[list[AgentEdge]] = None,
    ) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._edges: list[AgentEdge] = []
        self._lock = threading.RLock()

        if nodes:
            for node in nodes:
                self._nodes[node.id] = node
        if edges:
            for edge in edges:
                self._edges.append(edge)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: AgentNode) -> None:
        """Add a node to the graph.

        Args:
            node: Node to add.

        Raises:
            ExecutionGraphError: If a node with the same id already exists.
        """
        with self._lock:
            if node.id in self._nodes:
                raise ExecutionGraphError(
                    f"Node '{node.id}' already exists."
                )
            self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all edges referencing it.

        Args:
            node_id: Id of the node to remove.

        Raises:
            ExecutionGraphError: If the node does not exist.
        """
        with self._lock:
            if node_id not in self._nodes:
                raise ExecutionGraphError(
                    f"Node '{node_id}' does not exist."
                )
            del self._nodes[node_id]
            self._edges = [
                e for e in self._edges
                if e.source != node_id and e.target != node_id
            ]

    def get_node(self, node_id: str) -> AgentNode:
        """Return a node by id.

        Raises:
            ExecutionGraphError: If the node does not exist.
        """
        with self._lock:
            if node_id not in self._nodes:
                raise ExecutionGraphError(
                    f"Node '{node_id}' does not exist."
                )
            return self._nodes[node_id]

    def list_nodes(self) -> list[AgentNode]:
        """Return all nodes."""
        with self._lock:
            return list(self._nodes.values())

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, edge: AgentEdge) -> None:
        """Add a directed edge.

        The graph is validated for cycles and references immediately.

        Args:
            edge: Edge to add.

        Raises:
            ExecutionGraphError: If the edge connects non-existent nodes
                or would create a cycle.
        """
        with self._lock:
            # Check node existence.
            errors = ExecutionGraphValidator.check_invalid_references(
                self._nodes, self._edges + [edge]
            )
            if errors:
                raise ExecutionGraphError("; ".join(errors))

            # Check cycle.
            test_edges = self._edges + [edge]
            cycle_errors = ExecutionGraphValidator.detect_cycles(
                self._nodes, test_edges
            )
            if cycle_errors:
                raise CycleError("; ".join(cycle_errors))

            self._edges.append(edge)

    def remove_edge(self, source: str, target: str) -> None:
        """Remove the first edge matching source → target.

        Args:
            source: Source node id.
            target: Target node id.

        Raises:
            ExecutionGraphError: If no such edge exists.
        """
        with self._lock:
            for i, edge in enumerate(self._edges):
                if edge.source == source and edge.target == target:
                    self._edges.pop(i)
                    return
            raise ExecutionGraphError(
                f"Edge '{source} → {target}' does not exist."
            )

    def list_edges(self) -> list[AgentEdge]:
        """Return all edges."""
        with self._lock:
            return list(self._edges)

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def get_roots(self) -> list[AgentNode]:
        """Return nodes with no incoming edges."""
        with self._lock:
            targets = {e.target for e in self._edges}
            return [n for n in self._nodes.values() if n.id not in targets]

    def get_leaves(self) -> list[AgentNode]:
        """Return nodes with no outgoing edges."""
        with self._lock:
            sources = {e.source for e in self._edges}
            return [n for n in self._nodes.values() if n.id not in sources]

    def topological_sort(self) -> list[AgentNode]:
        """Return nodes in topologically-sorted order (Kahn's algorithm).

        Raises:
            CycleError: If the graph contains a cycle.
        """
        with self._lock:
            in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
            adjacency: dict[str, list[str]] = {nid: [] for nid in self._nodes}

            for edge in self._edges:
                if edge.source in adjacency and edge.target in in_degree:
                    adjacency[edge.source].append(edge.target)
                    in_degree[edge.target] += 1

            queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
            sorted_ids: list[str] = []

            while queue:
                current = queue.popleft()
                sorted_ids.append(current)
                for neighbor in adjacency[current]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if len(sorted_ids) != len(self._nodes):
                raise CycleError("Graph contains a cycle — topological sort is not possible.")

            return [self._nodes[nid] for nid in sorted_ids]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Run all validation checks.

        Returns:
            A list of error messages, or an empty list if valid.
        """
        with self._lock:
            return ExecutionGraphValidator.validate(self._nodes, self._edges)

    # ------------------------------------------------------------------
    # Execution plan
    # ------------------------------------------------------------------

    def generate_plan(self) -> GraphExecutionPlan:
        """Generate an execution plan from the validated graph.

        Returns:
            A :class:`GraphExecutionPlan` with topologically-sorted order,
            levels, dependencies and statistics.

        Raises:
            ValidationError: If the graph is not valid.
        """
        errors = self.validate()
        if errors:
            raise ValidationError("; ".join(errors))

        with self._lock:
            # Topological order.
            sorted_nodes = self.topological_sort()

            # Build dependency map.
            deps: dict[str, list[str]] = {nid: [] for nid in self._nodes}
            for edge in self._edges:
                deps[edge.target].append(edge.source)

            # Compute levels (BFS layers).
            in_degree = {nid: 0 for nid in self._nodes}
            adj = defaultdict(list)
            for edge in self._edges:
                if edge.source in in_degree:
                    adj[edge.source].append(edge.target)
                    in_degree[edge.target] += 1

            level_of: dict[str, int] = {}
            queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
            for nid in queue:
                level_of[nid] = 0

            while queue:
                current = queue.popleft()
                for neighbor in adj[current]:
                    in_degree[neighbor] -= 1
                    level_of[neighbor] = max(
                        level_of.get(neighbor, 0),
                        level_of[current] + 1,
                    )
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            max_level = max(level_of.values()) if level_of else 0
            levels: list[frozenset[str]] = []
            for lvl in range(max_level + 1):
                nodes_at_level = frozenset(
                    nid for nid, l in level_of.items() if l == lvl
                )
                if nodes_at_level:
                    levels.append(nodes_at_level)

            return GraphExecutionPlan(
                execution_order=tuple(n.id for n in sorted_nodes),
                levels=tuple(levels),
                dependencies={nid: tuple(deps[nid]) for nid in self._nodes},
                stats={
                    "node_count": len(self._nodes),
                    "edge_count": len(self._edges),
                    "level_count": len(levels),
                    "root_count": len(self.get_roots()),
                    "leaf_count": len(self.get_leaves()),
                },
            )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the graph to a plain dictionary.

        Returns:
            A JSON-compatible dict with ``nodes`` and ``edges`` lists.
        """
        with self._lock:
            nodes = []
            for node in self._nodes.values():
                nd: dict[str, Any] = {
                    "id": node.id,
                    "name": node.name,
                    "type": node.type.value if isinstance(node.type, NodeType) else node.type,
                    "status": node.status.value if isinstance(node.status, NodeStatus) else node.status,
                    "runtime_capability": node.runtime_capability,
                    "metadata": node.metadata,
                }
                nodes.append(nd)

            edges = []
            for edge in self._edges:
                ed: dict[str, Any] = {
                    "source": edge.source,
                    "target": edge.target,
                    "condition": edge.condition,
                    "metadata": edge.metadata,
                }
                edges.append(ed)

            return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionGraph:
        """Deserialise a graph from a dictionary produced by :meth:`to_dict`.

        Args:
            data: A dict with ``nodes`` and ``edges`` lists.

        Returns:
            A new :class:`ExecutionGraph` instance.
        """
        nodes = []
        for nd in data.get("nodes", []):
            node_type = nd.get("type", "task")
            status = nd.get("status", "pending")
            try:
                node_type = NodeType(node_type)
            except ValueError:
                pass
            try:
                status = NodeStatus(status)
            except ValueError:
                pass
            nodes.append(AgentNode(
                id=nd["id"],
                name=nd.get("name", nd["id"]),
                type=node_type,
                status=status,
                runtime_capability=nd.get("runtime_capability", "chat"),
                metadata=nd.get("metadata", {}),
            ))

        edges = []
        for ed in data.get("edges", []):
            edges.append(AgentEdge(
                source=ed["source"],
                target=ed["target"],
                condition=ed.get("condition", ""),
                metadata=ed.get("metadata", {}),
            ))

        return cls(nodes=nodes, edges=edges)
