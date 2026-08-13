"""Graph Executor for the Mission Graph Engine (HOS-041).

Orchestrates mission execution through the DAG.
Integrates with RuntimeOrchestrator (HOS-038) for node execution.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.core.config import get_settings
from backend.mission.dependency_resolver import DependencyResolver
from backend.mission.mission_graph import MissionGraph
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionStatus,
    NodeStatus,
)


logger = logging.getLogger("hermes_os.mission.graph_executor")


class GraphExecutor:
    """Executes missions by traversing the DAG.

    Thread-safe. Publishes events via callback.
    """

    def __init__(
        self,
        on_event: Optional[Callable] = None,
        execute_node: Optional[Callable[[MissionNode], bool]] = None,
        max_parallel_tasks: Optional[int] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._graph = MissionGraph()
        self._resolver = DependencyResolver()
        # HOS-092: workspace fingerprints taken at start_mission, consumed
        # once at completion. Keyed by mission so concurrent missions cannot
        # read each other's baseline.
        self._snapshots: dict = {}
        self._on_event = on_event
        self._execute_node = execute_node or (lambda n: True)
        # HOS-068: bounded, deliberately small — see mission_max_parallel_tasks
        # in backend/core/config.py for the VRAM-exhaustion rationale on this
        # deployment's 16 GB card.
        self._max_parallel = (
            max_parallel_tasks
            if max_parallel_tasks is not None
            else get_settings().mission_max_parallel_tasks
        )

    # ── Mission Lifecycle ───────────────────────────────────

    def build_graph(
        self,
        mission: Mission,
        nodes: list[MissionNode],
        edges: list[MissionEdge],
    ) -> list[str]:
        """Build and validate a mission DAG."""
        # HOS-069: so node_execution.py can report which mission a real
        # execution belongs to (see MissionNode.mission_id's docstring).
        for node in nodes:
            node.mission_id = mission.mission_id
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

        # HOS-092: fingerprint the workspace now, so completion can be
        # confronted with what physically changed rather than with the
        # agent's account of it. Best-effort by construction — a snapshot
        # that fails must never prevent a mission from running.
        self._snapshot_workspace(mission)

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
        """Execute all ready nodes, up to ``self._max_parallel`` concurrently.

        Nodes are dispatched to a thread pool (HOS-068) — genuine concurrency
        is only possible because MissionExecutor.execute_task() no longer
        holds its lock across the slow inference call (see mission_executor.py).
        ``DependencyResolver``/``mission`` mutations are NOT performed from
        worker threads: each worker only calls ``self._execute_node(node)``
        (a self-contained, per-node call) and returns a bool; every
        ``mark_completed``/``mark_failed`` and event publish happens back on
        this calling thread after the futures resolve, so mission/graph state
        is never written from more than one thread at a time.
        """
        ready = self._resolver.get_ready_nodes(mission)
        count = 0

        for node in ready:
            node.status = NodeStatus.RUNNING

        results: dict[str, bool] = {}
        max_workers = min(len(ready), self._max_parallel) if ready else 0

        if max_workers <= 1:
            for node in ready:
                results[node.node_id] = self._execute_node(node)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_node = {
                    pool.submit(self._execute_node, node): node for node in ready
                }
                for future in as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        results[node.node_id] = future.result()
                    except Exception:
                        results[node.node_id] = False

        for node in ready:
            success = results.get(node.node_id, False)

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

                        verification = self._verify_workspace(mission, all_success)

                        # HOS-099/100: computed before and outside the event
                        # block on purpose. Retrying is a behaviour, not
                        # telemetry — making it conditional on someone having
                        # wired a listener meant a mission silently lost its
                        # second attempt whenever no handler was attached,
                        # which is exactly how this was first written and what
                        # the retry tests caught.
                        self._suggest_retry(mission, verification)

                        if self._on_event:
                            ev_type = "mission.completed" if all_success else "mission.completed"
                            payload = {
                                "mission_id": mission.mission_id,
                                "failed": progress["failed"],
                            }
                            if verification is not None:
                                payload["verification"] = verification
                            self._on_event(ev_type, payload,
                                           severity="info" if all_success else "error")
                            # A mission claiming success over an untouched
                            # workspace is the failure mode that hid five
                            # separate defects — it gets its own event so it
                            # is impossible to read the green one alone.
                            if verification is not None and verification.get("contradicted"):
                                self._on_event("mission.unverified", verification,
                                               severity="warning")

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

    def _suggest_retry(self, mission: Mission, verification: dict | None) -> None:
        """Emit the retry brief for a mission the filesystem contradicts.

        Publishes rather than re-running: relaunching a mission graph is the
        caller's decision (it owns scheduling, budgets and the operator's
        consent), and burying an automatic re-execution inside a completion
        handler would make a mission cost twice as much with nothing in the
        UI to say why.
        """
        try:
            from backend.mission.retry_policy import decide

            attempts = int(mission.metadata.get("attempts", 1))
            objective = mission.objective or mission.description or mission.title
            decision = decide(verification, objective=objective, attempts_made=attempts)
            if not decision.should_retry:
                logger.debug("no retry for %s: %s", mission.mission_id, decision.reason)
                return
            mission.metadata["retry_brief"] = decision.brief
            if self._on_event:
                self._on_event("mission.retry_suggested", {
                    "mission_id": mission.mission_id,
                    "attempt": decision.attempt,
                    "reason": decision.reason,
                    "brief": decision.brief,
                }, severity="warning")
        except Exception:  # pragma: no cover - diagnostics never break a run
            logger.debug("retry suggestion failed", exc_info=True)

    def _workspace_root(self, mission: Mission) -> str | None:
        """The directory a mission's work should land in, or None.

        Resolved through the same Project binding RealTaskExecutor uses, so
        verification looks at exactly the tree Hermes Agent was given.
        """
        project_id = getattr(mission.context, "project_id", "") or ""
        if not project_id:
            return None
        try:
            from backend.projects.store import get_project_store
            project = get_project_store().get(project_id)
        except Exception:
            return None
        return (project.root_path or None) if project is not None else None

    def _snapshot_workspace(self, mission: Mission) -> None:
        try:
            from backend.mission.verification import snapshot

            root = self._workspace_root(mission)
            if root:
                self._snapshots[mission.mission_id] = snapshot(root)
        except Exception:  # pragma: no cover - diagnostics never block a run
            logger.debug("workspace snapshot failed", exc_info=True)

    def _verify_workspace(self, mission: Mission, reported_success: bool) -> dict | None:
        """Confront the mission's verdict with the filesystem's."""
        try:
            from backend.mission.verification import snapshot, verify

            root = self._workspace_root(mission)
            before = self._snapshots.pop(mission.mission_id, None)
            after = snapshot(root) if root else None
            result = verify(mission.mission_id, reported_success, root, before, after)
            return result.as_dict()
        except Exception:  # pragma: no cover
            logger.debug("workspace verification failed", exc_info=True)
            return None

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
            # The measured fields are included so the Cockpit can show what a
            # node actually did. They were written by the node executor and
            # dropped here, leaving the graph view unable to distinguish a node
            # that ran for 16 s from one that never ran (R-002 P1).
            "nodes": [
                {
                    "id": n.node_id,
                    "title": n.title,
                    "status": n.status.value,
                    "type": n.type,
                    "duration_ms": round(n.actual_duration_ms, 1),
                    "runtime": n.preferred_runtime,
                    "result_summary": n.result_summary,
                    "depends_on": list(n.depends_on),
                }
                for n in mission.nodes
            ],
            "edges": [
                {"source": e.source_id, "target": e.target_id} for e in mission.edges
            ],
            "topological_order": order,
            "parallel_groups": parallel_groups,
            "progress": self.get_progress(mission),
        }
