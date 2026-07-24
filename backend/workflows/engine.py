"""WorkflowEngine — executes a WorkflowDefinition's graph of agent
actions (cahier des charges §15).

Nodes dispatch through mcp_server.server.get_tool_registry(): the exact
same normalized, plain-params-in / dict-or-list-or-bool-or-str-out
callables MCP clients already call. Every one of those functions already
materializes whatever tuple/stream-returning agent method it wraps (see
e.g. research_query, verify_output) into a plain value, so the engine
itself stays agent-agnostic and doesn't duplicate a second adapter layer.

run() is genuinely synchronous within one call and does NOT persist
paused ("awaiting_validation") state across requests — there is no
background job / execution-state store anywhere in this codebase yet
(Kronos's tasks aren't auto-executed either; that's tracking, not
execution). A run halts at every human_validation node not already in
approved_nodes and returns without executing it or anything downstream
of it. Re-invoking run() with that node's id included in approved_nodes
re-executes the whole graph from the start and continues past the gate
once reached — an honest limitation, not a hidden one: cheap/idempotent
nodes (reads, Aegis checks) are fine to re-run, but true resume-without-
repeating needs persisted run state, deliberately left out of this pass.

simulate() is a pure dry-run: computes the structural execution order
(ignoring runtime success/failure, which doesn't exist yet) without
calling any tool or touching the message bus.
"""
from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.core.message_bus import MessageBus, MessageType, get_message_bus
from backend.workflows.schema import WorkflowDefinition, WorkflowEdge, WorkflowNode


class WorkflowExecutionError(RuntimeError):
    pass


@dataclass
class NodeResult:
    node_id: str
    status: str  # success | failed | skipped | awaiting_validation
    result: Any = None
    error: str | None = None


@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    status: str  # completed | failed | partially_successful | awaiting_validation
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    pending_nodes: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    workflow_id: str
    execution_order: list[str]
    human_validation_nodes: list[str]


class WorkflowEngine:
    def __init__(self) -> None:
        # Imported lazily, not at module level: mcp_server/server.py (for
        # workflow MCP tools) imports WorkflowEngine, and get_tool_registry
        # is defined in that same module — an eager import here would be
        # circular. By the time anything actually constructs a
        # WorkflowEngine, mcp_server.server has always finished loading.
        from backend.mcp_server.server import get_tool_registry

        self._tools = get_tool_registry()

    def simulate(self, workflow: WorkflowDefinition) -> SimulationResult:
        return SimulationResult(
            workflow_id=workflow.id,
            execution_order=self._topological_order(workflow),
            human_validation_nodes=[n.id for n in workflow.nodes if n.human_validation],
        )

    async def run(
        self, workflow: WorkflowDefinition, *, approved_nodes: set[str] | None = None
    ) -> WorkflowRun:
        approved_nodes = approved_nodes or set()
        execution_id = str(uuid.uuid4())
        bus = get_message_bus()

        results: dict[str, NodeResult] = {}
        done: set[str] = set()
        pending_nodes: list[str] = []
        remaining = {n.id for n in workflow.nodes}

        while remaining:
            ready = self._ready_nodes(workflow, done, results, remaining)
            if not ready:
                break  # nothing left is reachable (dead branches or gates upstream)

            for node_id in ready:
                remaining.discard(node_id)
                node = workflow.node(node_id)

                if node.human_validation and node_id not in approved_nodes:
                    results[node_id] = NodeResult(node_id=node_id, status="awaiting_validation")
                    pending_nodes.append(node_id)
                    continue  # NOT added to `done` -> blocks everything downstream

                results[node_id] = await self._execute_node(
                    workflow, node, results, bus, execution_id
                )
                done.add(node_id)

        for node_id in remaining:
            results[node_id] = NodeResult(node_id=node_id, status="skipped")

        return WorkflowRun(
            id=execution_id,
            workflow_id=workflow.id,
            status=self._overall_status(results, pending_nodes),
            node_results=results,
            pending_nodes=pending_nodes,
        )

    # ── execution ─────────────────────────────────────────────────────

    async def _execute_node(
        self,
        workflow: WorkflowDefinition,
        node: WorkflowNode,
        results: dict[str, NodeResult],
        bus: MessageBus,
        execution_id: str,
    ) -> NodeResult:
        from_agent = f"workflow:{workflow.id}"

        try:
            tool = self._tools.get(node.action)
            if tool is None:
                raise WorkflowExecutionError(f"Unknown action {node.action!r}")
            params = self._resolve_params(node.params, results)
        except WorkflowExecutionError as exc:
            return NodeResult(node_id=node.id, status="failed", error=str(exc))

        bus.publish(
            from_agent=from_agent,
            to_agent=node.action,
            type_=MessageType.TASK_DELEGATION,
            payload={"node_id": node.id, "params": params},
            task_id=execution_id,
        )

        try:
            value = tool(**params)
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:  # noqa: BLE001 - any tool failure becomes a node
            # failure (feeding on_failure branches), not a crashed run — that's
            # the entire point of conditional edges.
            bus.publish(
                from_agent=node.action,
                to_agent=from_agent,
                type_=MessageType.TASK_RESULT,
                payload={"node_id": node.id, "result": {"error": str(exc)}},
                task_id=execution_id,
            )
            return NodeResult(node_id=node.id, status="failed", error=str(exc))

        bus.publish(
            from_agent=node.action,
            to_agent=from_agent,
            type_=MessageType.TASK_RESULT,
            payload={"node_id": node.id, "result": {"value": value}},
            task_id=execution_id,
        )
        return NodeResult(node_id=node.id, status="success", result=value)

    def _resolve_params(self, params: dict, results: dict[str, NodeResult]) -> dict:
        return {
            key: self._resolve_value(value, results) if isinstance(value, str) else value
            for key, value in params.items()
        }

    def _resolve_value(self, value: str, results: dict[str, NodeResult]) -> Any:
        if not value.startswith("$steps."):
            return value

        parts = value[len("$steps.") :].split(".", 1)
        if len(parts) != 2:
            raise WorkflowExecutionError(
                f"Malformed placeholder {value!r}; expected $steps.<node_id>.<key>"
            )
        node_id, key = parts
        node_result = results.get(node_id)
        if node_result is None or node_result.status != "success":
            raise WorkflowExecutionError(
                f"Placeholder {value!r} references node {node_id!r}, which hasn't "
                "completed successfully."
            )
        if not isinstance(node_result.result, dict) or key not in node_result.result:
            raise WorkflowExecutionError(
                f"Placeholder {value!r}: node {node_id!r}'s result has no key {key!r}."
            )
        return node_result.result[key]

    # ── graph walk ────────────────────────────────────────────────────

    def _ready_nodes(
        self,
        workflow: WorkflowDefinition,
        done: set[str],
        results: dict[str, NodeResult],
        remaining: set[str],
    ) -> list[str]:
        ready = []
        for node_id in sorted(remaining):
            incoming = workflow.incoming_edges(node_id)
            if not incoming:
                ready.append(node_id)
                continue
            predecessors = {e.from_node for e in incoming}
            if not predecessors.issubset(done):
                continue  # still waiting on a predecessor to finish
            if any(self._edge_satisfied(e, results) for e in incoming):
                ready.append(node_id)
            # else: every inbound edge's condition failed -> permanently
            # unreachable this run; left in `remaining`, reported "skipped"
            # once the loop can't make further progress.
        return ready

    def _edge_satisfied(self, edge: WorkflowEdge, results: dict[str, NodeResult]) -> bool:
        if edge.condition == "always":
            return True
        predecessor = results.get(edge.from_node)
        if predecessor is None:
            return False
        if edge.condition == "on_success":
            return predecessor.status == "success"
        if edge.condition == "on_failure":
            return predecessor.status == "failed"
        return False

    def _overall_status(self, results: dict[str, NodeResult], pending_nodes: list[str]) -> str:
        if pending_nodes:
            return "awaiting_validation"
        statuses = {r.status for r in results.values()}
        if statuses <= {"success", "skipped"}:
            return "completed"
        if "success" in statuses:
            return "partially_successful"
        return "failed"

    def _topological_order(self, workflow: WorkflowDefinition) -> list[str]:
        """Structural order only — ignores edge conditions, since a
        dry-run has no runtime success/failure to evaluate them against.
        Always terminates: WorkflowDefinition rejects cycles at
        construction time."""
        in_degree = {n.id: 0 for n in workflow.nodes}
        for edge in workflow.edges:
            in_degree[edge.to_node] += 1

        frontier = sorted(node_id for node_id, degree in in_degree.items() if degree == 0)
        order: list[str] = []

        while frontier:
            node_id = frontier.pop(0)
            order.append(node_id)
            newly_ready = []
            for edge in workflow.outgoing_edges(node_id):
                in_degree[edge.to_node] -= 1
                if in_degree[edge.to_node] == 0:
                    newly_ready.append(edge.to_node)
            frontier = sorted(frontier + newly_ready)

        return order
