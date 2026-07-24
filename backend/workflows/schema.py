"""Workflow definitions — cahier des charges §15: a graph of agent
actions, defined in YAML under data/workflows/, executed by
backend/workflows/engine.py.

Kept as plain dataclasses (not Pydantic) to match task_manager.py's and
aegis_engine.py's domain-object style — Pydantic is reserved for the API
request/response boundary (backend/api/routes/workflows.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

_VALID_CONDITIONS = {"always", "on_success", "on_failure"}


class InvalidWorkflowError(ValueError):
    pass


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    action: str  # a tool name from mcp_server.server.get_tool_registry(), e.g. "research_query"
    params: dict = field(default_factory=dict)
    human_validation: bool = False


@dataclass(frozen=True)
class WorkflowEdge:
    from_node: str
    to_node: str
    condition: str = "always"  # always | on_success | on_failure


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    name: str
    description: str = ""
    nodes: tuple[WorkflowNode, ...] = ()
    edges: tuple[WorkflowEdge, ...] = ()
    project_id: str | None = None

    def __post_init__(self) -> None:
        _validate(self)

    def node(self, node_id: str) -> WorkflowNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise InvalidWorkflowError(f"No such node {node_id!r} in workflow {self.id!r}")

    def outgoing_edges(self, node_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.from_node == node_id]

    def incoming_edges(self, node_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.to_node == node_id]

    @staticmethod
    def from_dict(data: dict) -> WorkflowDefinition:
        try:
            nodes = tuple(
                WorkflowNode(
                    id=n["id"],
                    action=n["action"],
                    params=n.get("params", {}),
                    human_validation=n.get("human_validation", False),
                )
                for n in data.get("nodes", [])
            )
            edges = tuple(
                WorkflowEdge(
                    from_node=e["from"],
                    to_node=e["to"],
                    condition=e.get("condition", "always"),
                )
                for e in data.get("edges", [])
            )
            workflow_id = data["id"]
        except KeyError as exc:
            raise InvalidWorkflowError(f"Workflow definition missing required field: {exc}") from exc

        return WorkflowDefinition(
            id=workflow_id,
            name=data.get("name", workflow_id),
            description=data.get("description", ""),
            nodes=nodes,
            edges=edges,
            project_id=data.get("project_id"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "project_id": self.project_id,
            "nodes": [
                {
                    "id": n.id,
                    "action": n.action,
                    "params": n.params,
                    "human_validation": n.human_validation,
                }
                for n in self.nodes
            ],
            "edges": [
                {"from": e.from_node, "to": e.to_node, "condition": e.condition}
                for e in self.edges
            ],
        }


def _validate(workflow: WorkflowDefinition) -> None:
    if not workflow.nodes:
        raise InvalidWorkflowError(f"Workflow {workflow.id!r} has no nodes.")

    node_ids = {n.id for n in workflow.nodes}
    if len(node_ids) != len(workflow.nodes):
        raise InvalidWorkflowError(f"Workflow {workflow.id!r} has duplicate node ids.")

    for edge in workflow.edges:
        if edge.condition not in _VALID_CONDITIONS:
            raise InvalidWorkflowError(
                f"Edge {edge.from_node!r} -> {edge.to_node!r} has unknown condition "
                f"{edge.condition!r}. Valid: {sorted(_VALID_CONDITIONS)}"
            )
        if edge.from_node not in node_ids:
            raise InvalidWorkflowError(f"Edge references unknown node {edge.from_node!r}.")
        if edge.to_node not in node_ids:
            raise InvalidWorkflowError(f"Edge references unknown node {edge.to_node!r}.")

    _check_acyclic(workflow)


def _check_acyclic(workflow: WorkflowDefinition) -> None:
    """DFS-based cycle detection — the engine's node-readiness algorithm
    assumes a DAG."""
    white, gray, black = 0, 1, 2
    color = {n.id: white for n in workflow.nodes}

    def visit(node_id: str) -> None:
        color[node_id] = gray
        for edge in workflow.outgoing_edges(node_id):
            if color[edge.to_node] == gray:
                raise InvalidWorkflowError(
                    f"Workflow {workflow.id!r} has a cycle involving {edge.to_node!r}."
                )
            if color[edge.to_node] == white:
                visit(edge.to_node)
        color[node_id] = black

    for node in workflow.nodes:
        if color[node.id] == white:
            visit(node.id)
