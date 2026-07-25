"""WorkflowEngine — executes a WorkflowDefinition's graph of agent
actions (cahier des charges §15).

Nodes dispatch through mcp_server.server.get_tool_registry(): the exact
same normalized, plain-params-in / dict-or-list-or-bool-or-str-out
callables MCP clients already call. Every one of those functions already
materializes whatever tuple/stream-returning agent method it wraps (see
e.g. research_query, verify_output) into a plain value, so the engine
itself stays agent-agnostic and doesn't duplicate a second adapter layer.

run() persists its state after every call (backend/workflows/run_store.py,
same SQLite file as tasks/skills/memory) so a run halted at a
human_validation gate can actually be *resumed*, not just re-run from
scratch: pass the previous call's `run_id` back in, along with the
newly-approved node ids, and only nodes not already in a terminal state
(success/failed/skipped) get (re-)evaluated — everything already decided
is loaded from the persisted record as-is. approved_nodes accumulates
across resumes (a node approved once stays approved). Omit run_id to
start a fresh run, unchanged from before.

simulate() is a pure dry-run: computes the structural execution order
(ignoring runtime success/failure, which doesn't exist yet) without
calling any tool or touching the message bus.
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.core.config import get_settings
from backend.core.message_bus import MessageBus, MessageType, get_message_bus
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.workflows import run_store
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
    project_id: str | None = None


@dataclass
class SimulationResult:
    workflow_id: str
    execution_order: list[str]
    human_validation_nodes: list[str]
    # Nodes grouped into the waves run() would execute concurrently.
    # execution_order stays a flat list (existing callers depend on it);
    # this shows *what runs together*, which is the part a human actually
    # needs to judge whether a workflow will parallelize at all.
    execution_waves: list[list[str]] = field(default_factory=list)
    max_parallel: int = 1


@dataclass
class _PersistedRun:
    """Internal: a previous run() call's state, loaded back for resume."""

    node_results: dict[str, NodeResult]
    approved_nodes: set[str]


class WorkflowEngine:
    def __init__(self) -> None:
        # Imported lazily, not at module level: mcp_server/server.py (for
        # workflow MCP tools) imports WorkflowEngine, and get_tool_registry
        # is defined in that same module — an eager import here would be
        # circular. By the time anything actually constructs a
        # WorkflowEngine, mcp_server.server has always finished loading.
        from backend.mcp_server.server import get_tool_registry

        self._tools = get_tool_registry()

        settings = get_settings()
        self._max_parallel = settings.workflow_max_parallel
        engine = make_engine(settings.sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)

    def simulate(self, workflow: WorkflowDefinition) -> SimulationResult:
        waves = self._structural_waves(workflow)
        return SimulationResult(
            workflow_id=workflow.id,
            execution_order=self._topological_order(workflow),
            human_validation_nodes=[n.id for n in workflow.nodes if n.human_validation],
            execution_waves=waves,
            max_parallel=self._max_parallel,
        )

    def _structural_waves(self, workflow: WorkflowDefinition) -> list[list[str]]:
        """Group nodes into the waves run() would execute concurrently.

        Structural, like _topological_order: edge conditions are ignored,
        since a dry-run has no runtime outcome to evaluate them against.
        The real run may therefore produce fewer nodes per wave (a failed
        on_success edge prunes a branch) — never more, so this is an
        upper bound on parallelism, which is the useful direction for
        capacity planning.
        """
        in_degree = {n.id: 0 for n in workflow.nodes}
        for edge in workflow.edges:
            in_degree[edge.to_node] += 1

        waves: list[list[str]] = []
        remaining = dict(in_degree)
        while remaining:
            wave = sorted(nid for nid, degree in remaining.items() if degree == 0)
            if not wave:
                break  # unreachable: the schema rejects cycles at construction
            waves.append(wave)
            for node_id in wave:
                del remaining[node_id]
                for edge in workflow.outgoing_edges(node_id):
                    if edge.to_node in remaining:
                        remaining[edge.to_node] -= 1
        return waves

    async def run(
        self,
        workflow: WorkflowDefinition,
        *,
        run_id: str | None = None,
        approved_nodes: set[str] | None = None,
    ) -> WorkflowRun:
        newly_approved = approved_nodes or set()
        bus = get_message_bus()

        if run_id is not None:
            persisted = self._load_run(run_id)
            if persisted is None:
                raise WorkflowExecutionError(
                    f"No persisted run {run_id!r} to resume — check the id, or omit "
                    "run_id to start a fresh run."
                )
            execution_id = run_id
            results = persisted.node_results
            approved_nodes_total = persisted.approved_nodes | newly_approved
        else:
            execution_id = str(uuid.uuid4())
            results = {}
            approved_nodes_total = newly_approved

        # Only success/failed nodes are truly terminal and excluded from
        # re-evaluation on resume. "skipped" is deliberately NOT treated
        # as done here even though it's a terminal NodeResult status:
        # last time around it could mean either "a dead branch" (an
        # on_success/on_failure edge that didn't fire) or merely
        # "unreachable because an upstream gate was still pending" —
        # those are indistinguishable from the stored status alone. Both
        # "skipped" and "awaiting_validation" nodes go back through
        # _ready_nodes() below on every call; recomputing is cheap and
        # side-effect-free (no tool calls), and a genuinely dead branch
        # re-derives the exact same "skipped" outcome, so this is safe.
        done = {nid for nid, r in results.items() if r.status in {"success", "failed"}}
        pending_nodes: list[str] = []
        remaining = {n.id for n in workflow.nodes} - done

        while remaining:
            ready = self._ready_nodes(workflow, done, results, remaining)
            if not ready:
                break  # nothing left is reachable (dead branches or gates upstream)

            # A "wave" is every node whose predecessors are all done. By
            # construction no node in a wave depends on another in the
            # same wave, so they can run concurrently and _resolve_params
            # can read `results` without racing: everything it can
            # reference was resolved in an earlier wave.
            runnable: list[str] = []
            for node_id in ready:
                remaining.discard(node_id)
                node = workflow.node(node_id)

                if node.human_validation and node_id not in approved_nodes_total:
                    results[node_id] = NodeResult(node_id=node_id, status="awaiting_validation")
                    pending_nodes.append(node_id)
                    continue  # NOT added to `done` -> blocks everything downstream

                runnable.append(node_id)

            wave = await self._execute_wave(workflow, runnable, results, bus, execution_id)
            # Written back in the wave's sorted order, not completion
            # order: `results` is persisted and compared in tests, and a
            # dict whose key order depended on which tool happened to
            # finish first would make runs gratuitously non-reproducible.
            for node_id in runnable:
                results[node_id] = wave[node_id]
                done.add(node_id)

        for node_id in remaining:
            results[node_id] = NodeResult(node_id=node_id, status="skipped")

        run = WorkflowRun(
            id=execution_id,
            workflow_id=workflow.id,
            status=self._overall_status(results, pending_nodes),
            node_results=results,
            pending_nodes=pending_nodes,
            project_id=workflow.project_id,
        )
        self._save_run(run, approved_nodes_total)
        return run

    def get_run(self, run_id: str) -> WorkflowRun | None:
        """Fetch a persisted run's current state without executing
        anything — for checking status between resume calls."""
        record = self._load_run_record(run_id)
        if record is None:
            return None
        return WorkflowRun(
            id=record.id,
            workflow_id=record.workflow_id,
            status=record.status,
            node_results=self._deserialize_results(record.node_results_dict),
            pending_nodes=record.pending_nodes_list,
            project_id=record.project_id,
        )

    # ── persistence ───────────────────────────────────────────────────

    def _load_run_record(self, run_id: str) -> run_store.WorkflowRunRecord | None:
        with self._session_factory() as session:
            return run_store.get_run(session, run_id)

    def _load_run(self, run_id: str) -> _PersistedRun | None:
        record = self._load_run_record(run_id)
        if record is None:
            return None
        return _PersistedRun(
            node_results=self._deserialize_results(record.node_results_dict),
            approved_nodes=record.approved_nodes_set,
        )

    @staticmethod
    def _deserialize_results(raw: dict) -> dict[str, NodeResult]:
        return {
            node_id: NodeResult(
                node_id=node_id, status=r["status"], result=r.get("result"), error=r.get("error")
            )
            for node_id, r in raw.items()
        }

    def _save_run(self, run: WorkflowRun, approved_nodes: set[str]) -> None:
        with self._session_factory() as session:
            run_store.save_run(
                session,
                run_id=run.id,
                workflow_id=run.workflow_id,
                project_id=run.project_id,
                status=run.status,
                node_results={
                    node_id: {"status": nr.status, "result": nr.result, "error": nr.error}
                    for node_id, nr in run.node_results.items()
                },
                pending_nodes=run.pending_nodes,
                approved_nodes=approved_nodes,
            )

    # ── execution ─────────────────────────────────────────────────────

    async def _execute_wave(
        self,
        workflow: WorkflowDefinition,
        node_ids: list[str],
        results: dict[str, NodeResult],
        bus: MessageBus,
        execution_id: str,
    ) -> dict[str, NodeResult]:
        """Run one wave of independent nodes concurrently (§6).

        Concurrency is capped by settings.workflow_max_parallel — see that
        setting's comment for why unbounded fan-out is the wrong default
        on this hardware. A cap of 1 degrades to the previous sequential
        behaviour exactly, which is what makes it a safe escape hatch.
        """
        if not node_ids:
            return {}
        if len(node_ids) == 1:
            # Avoid the semaphore/gather machinery for the overwhelmingly
            # common linear case.
            node = workflow.node(node_ids[0])
            return {
                node_ids[0]: await self._execute_node(
                    workflow, node, results, bus, execution_id
                )
            }

        semaphore = asyncio.Semaphore(max(1, self._max_parallel))

        async def run_one(node_id: str) -> NodeResult:
            async with semaphore:
                return await self._execute_node(
                    workflow, workflow.node(node_id), results, bus, execution_id
                )

        # return_exceptions=True: _execute_node already converts any tool
        # failure into a "failed" NodeResult, so an exception escaping it
        # would be a bug in the engine itself. Surfacing that as one
        # failed node keeps the rest of the wave's real results — and the
        # error text — instead of losing the whole run to a traceback.
        outcomes = await asyncio.gather(
            *(run_one(node_id) for node_id in node_ids), return_exceptions=True
        )
        return {
            node_id: (
                outcome
                if isinstance(outcome, NodeResult)
                else NodeResult(node_id=node_id, status="failed", error=str(outcome))
            )
            for node_id, outcome in zip(node_ids, outcomes, strict=True)
        }

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
            project_id=workflow.project_id,
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
                project_id=workflow.project_id,
            )
            return NodeResult(node_id=node.id, status="failed", error=str(exc))

        bus.publish(
            from_agent=node.action,
            to_agent=from_agent,
            type_=MessageType.TASK_RESULT,
            payload={"node_id": node.id, "result": {"value": value}},
            task_id=execution_id,
            project_id=workflow.project_id,
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
