"""Tests for the Mission Graph Engine (HOS-041)."""

from __future__ import annotations

import json
import tempfile
import threading

import pytest

from backend.mission.dependency_resolver import DependencyResolver
from backend.mission.graph_executor import GraphExecutor
from backend.mission.graph_serializer import GraphSerializer
from backend.mission.mission_graph import MissionGraph
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionStatus,
    NodeStatus,
)


# ─── Helpers ────────────────────────────────────────────────

def _make_node(nid: str, title: str = "", deps: list[str] | None = None) -> MissionNode:
    return MissionNode(node_id=nid, title=title or nid, depends_on=deps or [])


def _make_edge(src: str, tgt: str) -> MissionEdge:
    return MissionEdge(source_id=src, target_id=tgt)


def _make_mission(nodes: list[MissionNode], edges: list[MissionEdge]) -> Mission:
    m = Mission(title="Test Mission")
    m.nodes = list(nodes)
    m.edges = list(edges)
    # Populate depends_on from edges
    for node in m.nodes:
        node.depends_on = [e.source_id for e in edges if e.target_id == node.node_id]
    return m


def _make_software_mission() -> tuple[Mission, list[MissionNode], list[MissionEdge]]:
    """Example: building a software project."""
    nodes = [
        _make_node("init", "Initialize Project"),
        _make_node("db", "Design Database"),
        _make_node("api", "Build API Layer", ["init", "db"]),
        _make_node("frontend", "Build Frontend", ["init"]),
        _make_node("auth", "Add Authentication", ["api"]),
        _make_node("tests", "Write Tests", ["api", "frontend"]),
        _make_node("deploy", "Deploy to Production", ["tests", "auth"]),
    ]
    edges = [
        _make_edge("init", "db"),
        _make_edge("init", "frontend"),
        _make_edge("db", "api"),
        _make_edge("init", "api"),
        _make_edge("api", "auth"),
        _make_edge("api", "tests"),
        _make_edge("frontend", "tests"),
        _make_edge("tests", "deploy"),
        _make_edge("auth", "deploy"),
    ]
    mission = _make_mission(nodes, edges)
    return mission, nodes, edges


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def graph() -> MissionGraph:
    return MissionGraph()


@pytest.fixture
def resolver() -> DependencyResolver:
    return DependencyResolver()


@pytest.fixture
def executor() -> GraphExecutor:
    return GraphExecutor()


# ─── 1. Mission Model Tests ────────────────────────────────


class TestMissionModels:
    def test_mission_creation(self):
        m = Mission(title="Test", objective="Build X")
        assert m.mission_id
        assert m.total_nodes() == 0
        assert m.progress_pct() == 0.0

    def test_node_creation(self):
        n = _make_node("n1", "Task 1", ["dep1", "dep2"])
        assert n.node_id == "n1"
        assert n.status == NodeStatus.PENDING
        assert len(n.depends_on) == 2

    def test_edge_creation(self):
        e = _make_edge("a", "b")
        assert e.source_id == "a"
        assert e.target_id == "b"

    def test_progress_tracking(self):
        mission, nodes, edges = _make_software_mission()
        assert mission.total_nodes() == 7
        assert mission.completed_nodes() == 0
        nodes[0].status = NodeStatus.COMPLETED
        assert mission.completed_nodes() == 1
        assert mission.progress_pct() == 14.3


# ─── 2. DAG Validation Tests ───────────────────────────────


class TestDAGValidation:
    def test_valid_dag(self, graph: MissionGraph):
        mission, nodes, edges = _make_software_mission()
        issues = graph.validate_graph(mission)
        assert len(issues) == 0
        assert mission.status == MissionStatus.VALIDATED

    def test_cycle_detection(self, graph: MissionGraph):
        """A → B → C → A is a cycle."""
        nodes = [_make_node("a"), _make_node("b"), _make_node("c")]
        edges = [_make_edge("a", "b"), _make_edge("b", "c"), _make_edge("c", "a")]
        mission = _make_mission(nodes, edges)
        issues = graph.validate_graph(mission)
        assert any("cycle" in i.lower() for i in issues)

    def test_missing_node_in_edge(self, graph: MissionGraph):
        nodes = [_make_node("a"), _make_node("b")]
        edges = [_make_edge("a", "nonexistent")]
        mission = _make_mission(nodes, edges)
        issues = graph.validate_graph(mission)
        assert len(issues) > 0

    def test_single_node_valid(self, graph: MissionGraph):
        nodes = [_make_node("solo")]
        mission = _make_mission(nodes, [])
        issues = graph.validate_graph(mission)
        assert len(issues) == 0

    def test_diamond_dag(self, graph: MissionGraph):
        """A → B, A → C, B + C → D"""
        nodes = [_make_node("a"), _make_node("b"), _make_node("c"), _make_node("d")]
        edges = [_make_edge("a", "b"), _make_edge("a", "c"), _make_edge("b", "d"), _make_edge("c", "d")]
        mission = _make_mission(nodes, edges)
        issues = graph.validate_graph(mission)
        assert len(issues) == 0


# ─── 3. Topological Sort Tests ─────────────────────────────


class TestTopologicalSort:
    def test_linear_chain(self, graph: MissionGraph):
        nodes = [_make_node("a"), _make_node("b"), _make_node("c")]
        edges = [_make_edge("a", "b"), _make_edge("b", "c")]
        mission = _make_mission(nodes, edges)
        order = graph.topological_sort(mission)
        assert order == ["a", "b", "c"]

    def test_software_mission_order(self, graph: MissionGraph):
        mission, _, _ = _make_software_mission()
        order = graph.topological_sort(mission)
        assert order[0] == "init"
        assert order[-1] == "deploy"
        assert order.index("init") < order.index("db")
        assert order.index("db") < order.index("api")


# ─── 4. Dependency Resolver Tests ──────────────────────────


class TestDependencyResolver:
    def test_ready_nodes_initial(self, resolver: DependencyResolver):
        mission, _, _ = _make_software_mission()
        ready = resolver.get_ready_nodes(mission)
        assert len(ready) == 1
        assert ready[0].node_id == "init"

    def test_ready_after_complete(self, resolver: DependencyResolver):
        mission, _, _ = _make_software_mission()
        resolver.mark_completed(mission, "init")
        ready = resolver.get_ready_nodes(mission)
        ready_ids = {n.node_id for n in ready}
        assert "db" in ready_ids
        assert "frontend" in ready_ids

    def test_blocked_nodes(self, resolver: DependencyResolver):
        mission, _, _ = _make_software_mission()
        blocked = resolver.get_blocked_nodes(mission)
        blocked_ids = {n.node_id for n in blocked}
        assert "init" not in blocked_ids  # Root has no deps
        assert "deploy" in blocked_ids

    def test_parallel_groups(self, resolver: DependencyResolver):
        mission, _, _ = _make_software_mission()
        groups = resolver.get_parallel_groups(mission)
        assert len(groups) >= 3
        assert groups[0] == ["init"]
        # db and frontend can run in parallel after init
        assert len(groups[1]) == 2
        assert "db" in groups[1]
        assert "frontend" in groups[1]

    def test_mark_failed_cascades(self, resolver: DependencyResolver):
        mission, _, _ = _make_software_mission()
        resolver.mark_completed(mission, "init")
        resolver.mark_failed(mission, "db")
        # api depends on db → should be blocked
        api = next(n for n in mission.nodes if n.node_id == "api")
        assert api.status == NodeStatus.BLOCKED


# ─── 5. Graph Executor Tests ───────────────────────────────


class TestGraphExecutor:
    def test_build_graph(self, executor: GraphExecutor):
        m = Mission(title="Test")
        nodes = [_make_node("a"), _make_node("b")]
        edges = [_make_edge("a", "b")]
        issues = executor.build_graph(m, nodes, edges)
        assert len(issues) == 0
        assert m.status == MissionStatus.READY

    def test_start_and_execute(self, executor: GraphExecutor):
        m = Mission(title="Test")
        nodes = [_make_node("a"), _make_node("b"), _make_node("c")]
        edges = [_make_edge("a", "b"), _make_edge("b", "c")]
        executor.build_graph(m, nodes, edges)

        assert executor.start_mission(m)
        assert m.status == MissionStatus.RUNNING

        # Execute step — should process 'a'
        count = executor.execute_step(m)
        assert count == 1

        # 'a' completed → 'b' ready
        progress = executor.get_progress(m)
        assert progress["completed"] == 1
        assert progress["ready"] == 1

    def test_execute_full_chain(self, executor: GraphExecutor):
        m = Mission(title="Test")
        nodes = [_make_node("a"), _make_node("b"), _make_node("c")]
        edges = [_make_edge("a", "b"), _make_edge("b", "c")]
        executor.build_graph(m, nodes, edges)
        executor.start_mission(m)

        for _ in range(3):
            executor.execute_step(m)

        progress = executor.get_progress(m)
        assert progress["completed"] == 3
        assert m.status == MissionStatus.COMPLETED

    def test_cancel_mission(self, executor: GraphExecutor):
        m = Mission(title="Test")
        executor.build_graph(m, [_make_node("a")], [])
        executor.start_mission(m)
        assert executor.cancel_mission(m)
        assert m.status == MissionStatus.CANCELLED

    def test_graph_data(self, executor: GraphExecutor):
        m, nodes, edges = _make_software_mission()
        executor.build_graph(m, nodes, edges)
        data = executor.get_graph_data(m)
        assert len(data["nodes"]) == 7
        assert len(data["edges"]) == 9
        assert len(data["parallel_groups"]) >= 3


# ─── 6. Serialization Tests ────────────────────────────────


class TestGraphSerializer:
    def test_json_roundtrip(self):
        serializer = GraphSerializer()
        mission, _, _ = _make_software_mission()
        json_str = serializer.to_json(mission)
        data = json.loads(json_str)
        assert data["schema_version"] == "1.0.0"
        restored = serializer.from_json(json_str)
        assert restored.title == mission.title
        assert restored.total_nodes() == mission.total_nodes()
        assert len(restored.edges) == len(mission.edges)

    def test_file_export_import(self):
        serializer = GraphSerializer()
        mission, _, _ = _make_software_mission()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            serializer.export_to_file(mission, f.name)
            path = f.name

        restored = serializer.import_from_file(path)
        assert restored.title == mission.title
        assert restored.total_nodes() == 7


# ─── 7. Event Publishing Tests ─────────────────────────────


class TestMissionEvents:
    def test_events_on_build(self):
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        executor = GraphExecutor(on_event=on_event)
        m = Mission(title="Test")
        executor.build_graph(m, [_make_node("a"), _make_node("b")], [_make_edge("a", "b")])

        assert any(e["type"] == "mission.created" for e in events)

    def test_events_on_execution(self):
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        executor = GraphExecutor(on_event=on_event)
        m = Mission(title="Test")
        executor.build_graph(m, [_make_node("a"), _make_node("b")], [_make_edge("a", "b")])
        executor.start_mission(m)
        executor.execute_step(m)
        executor.execute_step(m)

        types = {e["type"] for e in events}
        assert "mission.created" in types
        assert "mission.started" in types
        assert "mission.node_ready" in types
        assert "mission.node_completed" in types


# ─── 8. Thread Safety Tests ────────────────────────────────


class TestMissionThreadSafety:
    def test_concurrent_builds(self):
        errors: list[Exception] = []
        missions: list[Mission] = []

        def worker() -> None:
            try:
                executor = GraphExecutor()
                m = Mission(title="Concurrent")
                executor.build_graph(m, [_make_node("a"), _make_node("b")], [_make_edge("a", "b")])
                missions.append(m)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(missions) == 10

    def test_concurrent_progress_access(self, executor: GraphExecutor):
        m, nodes, edges = _make_software_mission()
        executor.build_graph(m, nodes, edges)
        executor.start_mission(m)
        errors: list[Exception] = []

        def reader() -> None:
            for _ in range(50):
                try:
                    executor.get_progress(m)
                except Exception as e:
                    errors.append(e)

        def stepper() -> None:
            for _ in range(10):
                try:
                    executor.execute_step(m)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=stepper)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
