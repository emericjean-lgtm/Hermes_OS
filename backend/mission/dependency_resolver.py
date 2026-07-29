"""Dependency Resolver for the Mission Graph Engine (HOS-041).

Resolves which nodes are ready, blocked, or parallelizable.
"""

from __future__ import annotations

from typing import Optional

from backend.mission.mission_models import (
    Mission,
    MissionNode,
    NodeStatus,
)


class DependencyResolver:
    """Resolves dependencies and identifies executable nodes."""

    def get_ready_nodes(self, mission: Mission) -> list[MissionNode]:
        """Return nodes whose dependencies are all satisfied.

        A node is ready if:
        - All its direct dependencies are COMPLETED
        - It is not already COMPLETED, FAILED, RUNNING, or BLOCKED
        """
        ready: list[MissionNode] = []
        for node in mission.nodes:
            if node.status in (
                NodeStatus.COMPLETED,
                NodeStatus.FAILED,
                NodeStatus.RUNNING,
                NodeStatus.BLOCKED,
            ):
                continue

            deps_satisfied = self._dependencies_satisfied(mission, node)
            if deps_satisfied:
                ready.append(node)

        return ready

    def get_blocked_nodes(self, mission: Mission) -> list[MissionNode]:
        """Return nodes that are blocked by unresolved dependencies."""
        blocked: list[MissionNode] = []
        for node in mission.nodes:
            if node.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.BLOCKED):
                continue
            if not self._dependencies_satisfied(mission, node):
                blocked.append(node)
        return blocked

    def _dependencies_satisfied(self, mission: Mission, node: MissionNode) -> bool:
        """Check if all dependencies of a node are completed."""
        if not node.depends_on:
            return True

        for dep_id in node.depends_on:
            dep_node = self._find_node(mission, dep_id)
            if dep_node is None:
                return False  # Dependency doesn't exist — can't be satisfied
            if dep_node.status != NodeStatus.COMPLETED:
                return False
        return True

    def get_parallel_groups(self, mission: Mission) -> list[list[str]]:
        """Return groups of nodes that can execute in parallel.

        Uses topological levels: nodes at the same level can run concurrently.
        """
        adjacency: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}
        for node in mission.nodes:
            adjacency[node.node_id] = []
            in_degree[node.node_id] = 0

        for edge in mission.edges:
            adjacency[edge.source_id].append(edge.target_id)
            in_degree[edge.target_id] += 1

        # BFS by level
        from collections import deque
        current: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        groups: list[list[str]] = []

        while current:
            level: list[str] = sorted(current)
            groups.append(level)
            next_level: deque[str] = deque()
            for u in level:
                for v in adjacency.get(u, []):
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_level.append(v)
            current = next_level

        return groups

    def mark_completed(self, mission: Mission, node_id: str) -> bool:
        """Mark a node as completed."""
        node = self._find_node(mission, node_id)
        if node is None:
            return False
        node.status = NodeStatus.COMPLETED
        from datetime import datetime, timezone
        node.completed_at = datetime.now(timezone.utc)
        return True

    def mark_failed(self, mission: Mission, node_id: str) -> bool:
        """Mark a node as failed — blocks dependents."""
        node = self._find_node(mission, node_id)
        if node is None:
            return False
        node.status = NodeStatus.FAILED

        # Cascade: block all dependents
        dependents = self._get_dependents(mission, node_id)
        for dep in dependents:
            if dep.status == NodeStatus.PENDING:
                dep.status = NodeStatus.BLOCKED

        return True

    def get_progress(self, mission: Mission) -> dict:
        """Return progress summary."""
        total = len(mission.nodes)
        completed = sum(1 for n in mission.nodes if n.status == NodeStatus.COMPLETED)
        failed = sum(1 for n in mission.nodes if n.status == NodeStatus.FAILED)
        ready = len(self.get_ready_nodes(mission))
        blocked = len(self.get_blocked_nodes(mission))
        running = sum(1 for n in mission.nodes if n.status == NodeStatus.RUNNING)
        skipped = sum(1 for n in mission.nodes if n.status == NodeStatus.SKIPPED)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "ready": ready,
            "running": running,
            "blocked": blocked,
            "skipped": skipped,
            "pending": total - completed - failed - running - skipped,
            "progress_pct": round(completed / max(total, 1) * 100, 1),
        }

    # ── Helpers ─────────────────────────────────────────────

    def _find_node(self, mission: Mission, node_id: str) -> Optional[MissionNode]:
        for n in mission.nodes:
            if n.node_id == node_id:
                return n
        return None

    def _get_dependents(self, mission: Mission, node_id: str) -> list[MissionNode]:
        """Get all nodes that depend on node_id."""
        direct = [
            e.target_id for e in mission.edges if e.source_id == node_id
        ]
        results: list[MissionNode] = []
        for tid in direct:
            n = self._find_node(mission, tid)
            if n:
                results.append(n)
        return results
