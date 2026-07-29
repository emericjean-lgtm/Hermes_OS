"""Graph Executor for the Mission Graph Engine (HOS-041).

Orchestrates mission execution through the DAG.
Integrates with RuntimeOrchestrator (HOS-038) for node execution.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.mission.dependency_resolver import DependencyResolver
from backend.mission.mission_graph import MissionGraph
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionStatus,
    NodeStatus,
)


class GraphExecutor:
    """Executes missions by traversing the DAG.

    Thread-safe. Publishes events via callback.
    """

    def __init__(
        self,
        on_event: Optional[Callable] = None,
        execute_node: Optional[Callable[[MissionNode], bool]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._graph = MissionGraph()
        self._resolver = DependencyResolver()
        self._on_event = on_event
        self._execute_node = execute_node or (lambda n: True)

    # ── Mission Lifecycle ───────────────────────────────────

    def build_graph(
        self,
        mission: Mission,
        nodes: list[MissionNode],
        edges: list[MissionEdge],
    ) -> list[str]:
        """Build and validate a mission DAG."""
        self._graph.build_graph(mission, nodes, edges)
        issues = self._graph.validate_graph(mission)
        if not issues:
            mission.status = MissionStatus.READY

        if self._on_event:
            self._on_event("mission.created", {
                "mission_id": mission.mission_id,
                "nodes": len(nodes),
                "edges": len(edges),
                "valid": len(issues) == 0,
            }, severity="info")

        return issues

    def start_mission(self, mission: Mission) -> bool:
        """Start executing a validated mission."""
        if mission.status not in (MissionStatus.READY, MissionStatus.VALIDATED):
            return False

        with self._lock:
            mission.status = MissionStatus.RUNNING
            mission.started_at = datetime.now(timezone.utc)

        if self._on_event:
            self._on_event("mission.started", {
                "mission_id": mission.mission_id,
                "nodes": len(mission.nodes),
            }, severity="info")

        # Mark root nodes as ready
        for node in self._resolver.get_ready_nodes(mission):
            if self._on_event:
                self._on_event("mission.node_ready", {
                    "mission_id": mission.mission_id,
                    "node_id": node.node_id,
                    "title": node.title,
                }, severity="info")

        return True

    def execute_step(self, mission: Mission) -> int:
        """Execute all ready nodes. Returns count of nodes executed."""
        ready = self._resolver.get_ready_nodes(mission)
        count = 0

        for node in ready:
            node.status = NodeStatus.RUNNING
            success = self._execute_node(node)

            if success:
                self._resolver.mark_completed(mission, node.node_id)
                if self._on_event:
                    self._on_event("mission.node_completed", {
                        "mission_id": mission.mission_id,
                        "node_id": node.node_id,
                        "title": node.title,
                    }, severity="info")
            else:
                self._resolver.mark_failed(mission, node.node_id)
                if self._on_event:
                    self._on_event("mission.node_failed", {
                        "mission_id": mission.mission_id,
                        "node_id": node.node_id,
                        "title": node.title,
                    }, severity="error")
            count += 1

        # Check if mission is complete
        if count > 0:
            progress = self._resolver.get_progress(mission)
            if progress["completed"] + progress["failed"] + progress["skipped"] >= progress["total"]:
                with self._lock:
                    if mission.status not in (MissionStatus.FAILED, MissionStatus.COMPLETED):
                        all_success = progress["failed"] == 0
                        mission.status = MissionStatus.COMPLETED if all_success else MissionStatus.FAILED
                        mission.completed_at = datetime.now(timezone.utc)

                        if self._on_event:
                            ev_type = "mission.completed" if all_success else "mission.completed"
                            self._on_event(ev_type, {
                                "mission_id": mission.mission_id,
                                "failed": progress["failed"],
                            }, severity="info" if all_success else "error")

            # Notify newly ready nodes
            new_ready = self._resolver.get_ready_nodes(mission)
            for n in new_ready:
                if self._on_event:
                    self._on_event("mission.node_ready", {
                        "mission_id": mission.mission_id,
                        "node_id": n.node_id,
                        "title": n.title,
                    }, severity="info")

        return count

    def cancel_mission(self, mission: Mission) -> bool:
        with self._lock:
            if mission.status == MissionStatus.COMPLETED:
                return False
            mission.status = MissionStatus.CANCELLED
            mission.completed_at = datetime.now(timezone.utc)

        if self._on_event:
            self._on_event("mission.cancelled", {
                "mission_id": mission.mission_id,
            }, severity="info")
        return True

    def get_progress(self, mission: Mission) -> dict:
        return self._resolver.get_progress(mission)

    def get_graph_data(self, mission: Mission) -> dict:
        """Return graph data for visualization."""
        order = self._graph.topological_sort(mission)
        parallel_groups = self._resolver.get_parallel_groups(mission)
        return {
            "mission_id": mission.mission_id,
            "nodes": [
                {"id": n.node_id, "title": n.title, "status": n.status.value, "type": n.type}
                for n in mission.nodes
            ],
            "edges": [
                {"source": e.source_id, "target": e.target_id} for e in mission.edges
            ],
            "topological_order": order,
            "parallel_groups": parallel_groups,
            "progress": self.get_progress(mission),
        }
