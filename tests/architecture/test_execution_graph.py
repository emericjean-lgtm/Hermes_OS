"""HOS-017 sentinel tests — Agent Execution Graph.

Tests the DAG-based task orchestration without any concrete agent or
network dependency.
"""

from __future__ import annotations

import json
import threading

import pytest

from backend.agent.execution_graph import (
    AgentEdge,
    AgentNode,
    CycleError,
    ExecutionGraph,
    ExecutionGraphError,
    GraphExecutionPlan,
    NodeStatus,
    NodeType,
    ValidationError,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_agent_node_defaults() -> None:
    n = AgentNode(id="n1", name="Node 1")
    assert n.id == "n1"
    assert n.name == "Node 1"
    assert n.type == NodeType.TASK
    assert n.status == NodeStatus.PENDING
    assert n.runtime_capability == "chat"
    assert n.metadata == {}


def test_agent_node_frozen() -> None:
    n = AgentNode(id="n1", name="N")
    with pytest.raises(AttributeError):
        n.id = "n2"  # type: ignore[misc]


def test_agent_edge_defaults() -> None:
    e = AgentEdge(source="a", target="b")
    assert e.source == "a"
    assert e.target == "b"
    assert e.condition == ""


def test_node_status_enum() -> None:
    assert NodeStatus.PENDING.value == "pending"
    assert NodeStatus.READY.value == "ready"
    assert NodeStatus.RUNNING.value == "running"
    assert NodeStatus.COMPLETED.value == "completed"
    assert NodeStatus.FAILED.value == "failed"


def test_node_type_enum() -> None:
    assert NodeType.TASK.value == "task"
    assert NodeType.DECISION.value == "decision"
    assert NodeType.PARALLEL.value == "parallel"


# ============================================================================
# Basic graph operations
# ============================================================================


def test_create_empty_graph() -> None:
    g = ExecutionGraph()
    assert g.list_nodes() == []
    assert g.list_edges() == []


def test_create_graph_with_initial_nodes() -> None:
    g = ExecutionGraph(
        nodes=[AgentNode(id="a", name="A"), AgentNode(id="b", name="B")],
    )
    assert len(g.list_nodes()) == 2


def test_add_node() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    assert g.get_node("a").name == "A"


def test_add_node_duplicate_raises() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    with pytest.raises(ExecutionGraphError, match="already exists"):
        g.add_node(AgentNode(id="a", name="Duplicate"))


def test_remove_node() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.remove_node("a")
    assert g.list_nodes() == []


def test_remove_node_removes_edges() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.remove_node("a")
    assert len(g.list_edges()) == 0


def test_remove_nonexistent_node_raises() -> None:
    g = ExecutionGraph()
    with pytest.raises(ExecutionGraphError, match="does not exist"):
        g.remove_node("nonexistent")


# ============================================================================
# Edge operations
# ============================================================================


def test_add_edge() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_edge(AgentEdge(source="a", target="b"))
    assert len(g.list_edges()) == 1


def test_add_edge_invalid_source_raises() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="b", name="B"))
    with pytest.raises(ExecutionGraphError, match="does not exist"):
        g.add_edge(AgentEdge(source="a", target="b"))


def test_add_edge_invalid_target_raises() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    with pytest.raises(ExecutionGraphError, match="does not exist"):
        g.add_edge(AgentEdge(source="a", target="b"))


def test_remove_edge() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.remove_edge("a", "b")
    assert g.list_edges() == []


def test_remove_edge_nonexistent_raises() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    with pytest.raises(ExecutionGraphError, match="does not exist"):
        g.remove_edge("a", "b")


# ============================================================================
# DAG validation and cycle detection
# ============================================================================


def test_valid_graph_validation_passes() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="b", target="c"))
    assert g.validate() == []


def test_detect_cycle() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="b", target="c"))
    with pytest.raises(CycleError):
        g.add_edge(AgentEdge(source="c", target="a"))


def test_detect_self_loop() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    with pytest.raises(CycleError):
        g.add_edge(AgentEdge(source="a", target="a"))


def test_validator_orphan_nodes() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    errors = g.validate()
    assert any("orphan" in err.lower() for err in errors)


def test_validator_no_orphans_with_single_node() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    assert g.validate() == []


# ============================================================================
# Graph queries
# ============================================================================


def test_get_roots() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="b", target="c"))
    roots = g.get_roots()
    assert len(roots) == 1
    assert roots[0].id == "a"


def test_get_leaves() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="b", target="c"))
    leaves = g.get_leaves()
    assert len(leaves) == 1
    assert leaves[0].id == "c"


# ============================================================================
# Topological sort
# ============================================================================


def test_topological_sort_simple() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="b", target="c"))
    order = g.topological_sort()
    assert [n.id for n in order] == ["a", "b", "c"]


def test_topological_sort_diamond() -> None:
    g = ExecutionGraph()
    for nid in ["a", "b", "c", "d"]:
        g.add_node(AgentNode(id=nid, name=nid))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="a", target="c"))
    g.add_edge(AgentEdge(source="b", target="d"))
    g.add_edge(AgentEdge(source="c", target="d"))
    order = g.topological_sort()
    idx = {nid: i for i, nid in enumerate(n.id for n in order)}
    assert idx["a"] < idx["b"]
    assert idx["a"] < idx["c"]
    assert idx["b"] < idx["d"]
    assert idx["c"] < idx["d"]


def test_topological_sort_with_cycle_raises() -> None:
    # Build the cyclic graph directly (bypassing add_edge validation)
    # to test that topological_sort detects it.
    g = ExecutionGraph(
        nodes=[AgentNode(id="a", name="A"), AgentNode(id="b", name="B")],
        edges=[AgentEdge(source="a", target="b"), AgentEdge(source="b", target="a")],
    )
    with pytest.raises(CycleError):
        g.topological_sort()


# ============================================================================
# Execution plan
# ============================================================================


def test_generate_plan() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_node(AgentNode(id="c", name="C"))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="a", target="c"))

    plan = g.generate_plan()
    assert isinstance(plan, GraphExecutionPlan)
    assert len(plan.execution_order) == 3
    assert plan.stats["node_count"] == 3
    assert plan.stats["edge_count"] == 2
    assert plan.stats["level_count"] >= 1


def test_plan_levels_reflect_dependencies() -> None:
    g = ExecutionGraph()
    for nid in ["a", "b", "c", "d"]:
        g.add_node(AgentNode(id=nid, name=nid))
    g.add_edge(AgentEdge(source="a", target="b"))
    g.add_edge(AgentEdge(source="a", target="c"))
    g.add_edge(AgentEdge(source="b", target="d"))
    g.add_edge(AgentEdge(source="c", target="d"))

    plan = g.generate_plan()
    # a should be level 0, b and c level 1, d level 2
    assert len(plan.levels) == 3
    assert "a" in plan.levels[0]


def test_plan_with_cycle_raises_validation_error() -> None:
    g = ExecutionGraph(
        nodes=[AgentNode(id="a", name="A"), AgentNode(id="b", name="B")],
        edges=[AgentEdge(source="a", target="b"), AgentEdge(source="b", target="a")],
    )
    with pytest.raises(ValidationError):
        g.generate_plan()


def test_plan_dependencies_map() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    g.add_node(AgentNode(id="b", name="B"))
    g.add_edge(AgentEdge(source="a", target="b"))
    plan = g.generate_plan()
    assert plan.dependencies["b"] == ("a",)
    assert plan.dependencies["a"] == ()


# ============================================================================
# Serialisation
# ============================================================================


def test_to_dict() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A", runtime_capability="chat"))
    g.add_node(AgentNode(id="b", name="B", runtime_capability="code"))
    g.add_edge(AgentEdge(source="a", target="b", condition="success"))

    data = g.to_dict()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["condition"] == "success"


def test_from_dict_roundtrip() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A", runtime_capability="chat"))
    g.add_node(AgentNode(id="b", name="B", runtime_capability="code"))
    g.add_edge(AgentEdge(source="a", target="b"))

    data = g.to_dict()
    g2 = ExecutionGraph.from_dict(data)
    assert len(g2.list_nodes()) == 2
    assert len(g2.list_edges()) == 1
    assert g2.get_node("a").name == "A"


def test_to_dict_json_compatible() -> None:
    g = ExecutionGraph()
    g.add_node(AgentNode(id="a", name="A"))
    data = g.to_dict()
    json_str = json.dumps(data, indent=2)
    assert '"id": "a"' in json_str


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_nodes_add() -> None:
    g = ExecutionGraph()

    def add_nodes(start: int, count: int) -> None:
        for i in range(start, start + count):
            g.add_node(AgentNode(id=f"n{i}", name=f"Node{i}"))

    threads = [
        threading.Thread(target=add_nodes, args=(0, 50)),
        threading.Thread(target=add_nodes, args=(50, 50)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(g.list_nodes()) == 100


def test_concurrent_reads_and_writes() -> None:
    g = ExecutionGraph()
    for i in range(10):
        g.add_node(AgentNode(id=f"n{i}", name=f"Node{i}"))

    errors: list[Exception] = []

    def add_edge_loop() -> None:
        for i in range(9):
            try:
                g.add_edge(AgentEdge(source=f"n{i}", target=f"n{i+1}"))
            except Exception as e:
                errors.append(e)

    def read_loop() -> None:
        for _ in range(100):
            try:
                _ = g.list_nodes()
                _ = g.get_roots()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=add_edge_loop)
    t2 = threading.Thread(target=read_loop)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
