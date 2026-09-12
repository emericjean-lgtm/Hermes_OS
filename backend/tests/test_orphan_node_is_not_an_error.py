"""Two orchestration authorities disagreed on parallel tasks (HOS-301, §7).

## Le défaut

Une tâche indépendante — sans dépendance et dont rien ne dépend — est
exactement ce à quoi ressemble une branche parallèle (§7.2) dans ce modèle
de dépendances. Le planificateur le sait et le dit deux fois :
`DependencyBuilder.detect_inconsistencies` porte le commentaire « orphans
are fine — they're root tasks », et `ValidationEngine._check_orphans` ne
lève qu'un avertissement, jamais un échec.

`MissionGraph.validate_graph` prenait une décision différente sur la même
donnée : dès qu'une mission avait au moins une autre arête, un nœud sans
arête devenait une erreur bloquante. Un plan tout à fait ordinaire — une
chaîne séquentielle plus une tâche indépendante — échouait donc à la
construction, alors que rien en amont ne l'avait jugé invalide.

`MissionPlanner.build_mission` n'avait de plus aucun endroit correct où
poser ce refus : `mission.status = result.mission_id` écrivait une chaîne
dans un champ d'énumération, et le premier appelant lisant
`mission.status.value` (tous les routers de mission) plantait avec
`AttributeError`.
"""

from __future__ import annotations

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_graph import MissionGraph
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionStatus,
)
from backend.mission.planner.complexity_estimator import ComplexityEstimator
from backend.mission.planner.mission_planner import MissionPlanner
from backend.mission.planner.planner_models import (
    PlanningResult,
    TaskBreakdown,
    TaskCategory,
)
from backend.mission.planner.runtime_recommender import RuntimeRecommender
from backend.mission.planner.validation_engine import ValidationEngine


def _breakdowns_avec_tache_independante() -> list[TaskBreakdown]:
    """Chaîne séquentielle (implémenter → tester) + une tâche à part."""
    a = TaskBreakdown(title="Implement feature X",
                      category=TaskCategory.IMPLEMENTATION, order=0,
                      can_parallelize=True)
    b = TaskBreakdown(title="Test feature X", category=TaskCategory.TESTING,
                      order=1, can_parallelize=False)
    c = TaskBreakdown(title="Write unrelated README",
                      category=TaskCategory.DOCUMENTATION, order=2,
                      can_parallelize=True)
    return [a, b, c]


def _resultat_de_planification(planner: MissionPlanner) -> PlanningResult:
    breakdowns = _breakdowns_avec_tache_independante()
    dep_graph, groupes = planner._dep_builder.build_dependencies(breakdowns)  # noqa: SLF001

    result = PlanningResult(request_id="r-1")
    result.task_breakdowns = breakdowns
    result.dependency_graph = dep_graph
    result.parallel_groups = groupes
    result.complexity_estimates = ComplexityEstimator().estimate_all(breakdowns)
    result.runtime_recommendations = RuntimeRecommender().recommend_all(
        breakdowns, result.complexity_estimates)
    return result


# ═══ MissionGraph : la vérité qu'il ne doit plus contredire ═══════════


def test_orphan_node_is_not_a_graph_issue():
    """Un nœud indépendant à côté d'une autre arête n'est pas une erreur."""
    graph = MissionGraph()
    mission = Mission(title="t")
    nodes = [MissionNode(node_id="a", title="A"),
             MissionNode(node_id="b", title="B"),
             MissionNode(node_id="c", title="Tâche indépendante")]
    edges = [MissionEdge(source_id="a", target_id="b")]
    graph.build_graph(mission, nodes, edges)

    issues = graph.validate_graph(mission)

    assert issues == []
    assert mission.status == MissionStatus.VALIDATED


def test_cycle_detection_is_unaffected():
    """Garde de non-régression : un vrai défaut structurel reste détecté."""
    graph = MissionGraph()
    mission = Mission(title="t")
    nodes = [MissionNode(node_id="a", title="A"),
             MissionNode(node_id="b", title="B"),
             MissionNode(node_id="c", title="C")]
    edges = [MissionEdge(source_id="a", target_id="b"),
             MissionEdge(source_id="b", target_id="c"),
             MissionEdge(source_id="c", target_id="a")]
    graph.build_graph(mission, nodes, edges)

    issues = graph.validate_graph(mission)

    assert any("cycle" in i.lower() for i in issues)
    assert mission.status != MissionStatus.VALIDATED


def test_dangling_edge_is_unaffected():
    """Garde de non-régression : une arête vers un nœud absent reste une erreur."""
    graph = MissionGraph()
    mission = Mission(title="t")
    nodes = [MissionNode(node_id="a", title="A")]
    edges = [MissionEdge(source_id="a", target_id="does-not-exist")]
    graph.build_graph(mission, nodes, edges)

    issues = graph.validate_graph(mission)

    assert any("not in nodes" in i for i in issues)


# ═══ Autorité unique : le planificateur et le graphe sont d'accord ════


def test_planner_and_graph_agree_an_independent_task_is_valid():
    """Ce que `ValidationEngine` n'a jamais bloqué, `MissionGraph` non plus."""
    planner = MissionPlanner(graph_executor=GraphExecutor())
    result = _resultat_de_planification(planner)

    rapport = ValidationEngine().validate(result)
    assert not any("orphan" in i.lower() for i in rapport.issues)

    mission = planner.build_mission(result, title="t", objective="o")

    # La décision matérialisée doit rester lisible : un champ d'énumération
    # valide, pas une chaîne qui casse le premier `.value` venu.
    assert isinstance(mission.status, MissionStatus)
    # GraphExecutor.build_graph promotes VALIDATED to READY when nothing
    # is wrong — the point here is that it gets the chance to at all.
    assert mission.status.value == "ready"
    assert mission.metadata.get("graph_issues") is None


# ═══ Un vrai défaut structurel doit rester visible, pas corrompre l'état ═


class _GraphExecutorEnFaute:
    """Simule un défaut de structure réel (ce que `build_graph` renvoie
    quand `MissionGraph.validate_graph` trouve un cycle ou une arête
    absente — les deux vérifications que ce lot n'a pas touchées)."""

    def build_graph(self, mission, nodes, edges):  # noqa: ANN001
        mission.nodes = list(nodes)
        mission.edges = list(edges)
        return ["Graph contains cycles — must be a DAG"]


def test_a_genuine_graph_defect_marks_the_mission_failed_not_corrupted():
    planner = MissionPlanner(graph_executor=_GraphExecutorEnFaute())
    result = _resultat_de_planification(planner)

    mission = planner.build_mission(result, title="t", objective="o")

    assert mission.status is MissionStatus.FAILED
    assert mission.metadata["graph_issues"] == [
        "Graph contains cycles — must be a DAG"]
    # La régression exacte du défaut : plus jamais une chaîne à la place
    # de l'énumération.
    assert mission.status.value == "failed"
