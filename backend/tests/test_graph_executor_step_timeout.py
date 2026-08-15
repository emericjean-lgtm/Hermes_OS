"""Une étape de mission finit toujours par rendre un verdict (HOS-112).

`execute_step` attendait ses nœuds sur un `as_completed` sans délai, puis
sortait d'un `with ThreadPoolExecutor(...)` qui joint tous les fils. Deux
attentes non bornées à la suite : un nœud muet immobilisait la mission
entière, sans trace, sans événement, et sans que rien ne finisse par
échouer.

En pratique chaque nœud est borné par le délai de `RealTaskExecutor`
(900 s pour une boucle d'agent). Mais cette borne appartient à l'exécuteur
*injecté* : le graphe ne la connaît pas, et un `execute_node` fourni par
un appelant qui n'en aurait aucune bloquerait ici pour toujours. Une
garantie qui repose sur la politesse de son appelant n'en est pas une.

Ces tests utilisent un délai de quelques centaines de millisecondes ; en
production il vaut 1200 s, très au-dessus du budget d'un nœud, parce que
c'est un dernier recours et non une politique d'exécution.
"""
from __future__ import annotations

import threading
import time

import pytest

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import Mission, MissionNode, MissionStatus, NodeStatus


@pytest.fixture
def noeud_muet():
    """Un nœud qui ne rend jamais la main — libéré au démontage.

    Le libérer est indispensable : les fils d'un `ThreadPoolExecutor` ne
    sont pas des démons et sont joints à la fin du processus. Un test qui
    laisserait le sien bloqué ferait pendre la suite entière à la sortie —
    précisément le défaut qu'il vérifie.
    """
    liberation = threading.Event()
    yield liberation
    liberation.set()


def _mission_a_deux_noeuds() -> Mission:
    mission = Mission(title="t", description="d", objective="o")
    mission.nodes = [
        MissionNode(node_id="rapide", title="rend la main"),
        MissionNode(node_id="muet", title="ne rend jamais la main"),
    ]
    return mission


def _demarrer(executeur: GraphExecutor, mission: Mission) -> None:
    executeur.build_graph(mission, mission.nodes, [])
    mission.status = MissionStatus.READY
    executeur.start_mission(mission)


def test_un_noeud_muet_ne_fige_pas_l_etape(noeud_muet):
    evenements: list[tuple[str, dict]] = []

    def execute_node(node: MissionNode) -> bool:
        if node.node_id == "muet":
            noeud_muet.wait()
            return True
        return True

    executeur = GraphExecutor(
        execute_node=execute_node,
        max_parallel_tasks=2,
        step_timeout_s=0.3,
        on_event=lambda t, p, severity="info": evenements.append((t, p)),
    )
    mission = _mission_a_deux_noeuds()
    _demarrer(executeur, mission)

    depart = time.monotonic()
    executeur.execute_step(mission)
    ecoule = time.monotonic() - depart

    assert ecoule < 10, f"l'étape a attendu {ecoule:.1f}s malgré un délai de 0,3s"


def test_le_noeud_muet_est_compte_en_echec_et_l_autre_non(noeud_muet):
    def execute_node(node: MissionNode) -> bool:
        if node.node_id == "muet":
            noeud_muet.wait()
        return True

    executeur = GraphExecutor(
        execute_node=execute_node, max_parallel_tasks=2, step_timeout_s=0.3,
    )
    mission = _mission_a_deux_noeuds()
    _demarrer(executeur, mission)

    executeur.execute_step(mission)

    par_id = {n.node_id: n.status for n in mission.nodes}
    assert par_id["rapide"] == NodeStatus.COMPLETED
    assert par_id["muet"] == NodeStatus.FAILED


def test_le_depassement_est_annonce_et_nomme_le_noeud(noeud_muet):
    """Un nœud abandonné en silence est indiscernable d'un nœud qui a
    échoué pour une raison qu'on aurait pu corriger."""
    evenements: list[tuple[str, dict]] = []

    def execute_node(node: MissionNode) -> bool:
        if node.node_id == "muet":
            noeud_muet.wait()
        return True

    executeur = GraphExecutor(
        execute_node=execute_node,
        max_parallel_tasks=2,
        step_timeout_s=0.3,
        on_event=lambda t, p, severity="info": evenements.append((t, p)),
    )
    mission = _mission_a_deux_noeuds()
    _demarrer(executeur, mission)

    executeur.execute_step(mission)

    depassements = [p for t, p in evenements if t == "mission.step_timeout"]
    assert len(depassements) == 1
    assert depassements[0]["nodes"] == ["ne rend jamais la main"]
    assert depassements[0]["timeout_s"] == 0.3


def test_sans_noeud_muet_le_delai_ne_se_declenche_pas():
    """Le garde-fou ne doit pas se manifester sur une exécution saine."""
    evenements: list[tuple[str, dict]] = []

    executeur = GraphExecutor(
        execute_node=lambda node: True,
        max_parallel_tasks=2,
        step_timeout_s=0.3,
        on_event=lambda t, p, severity="info": evenements.append((t, p)),
    )
    mission = _mission_a_deux_noeuds()
    _demarrer(executeur, mission)

    executeur.execute_step(mission)

    assert not [t for t, _ in evenements if t == "mission.step_timeout"]
    assert all(n.status == NodeStatus.COMPLETED for n in mission.nodes)


def test_le_delai_par_defaut_reste_au_dessus_du_budget_d_un_agent():
    """1200 s contre les 900 s de `_HERMES_AGENT_TIMEOUT_S`.

    Si ce plafond descendait sous le budget d'un nœud, il cesserait d'être
    un dernier recours pour devenir une politique d'exécution — et
    couperait des agents qui travaillent réellement.
    """
    from backend.execution.task_executor import _HERMES_AGENT_TIMEOUT_S
    from backend.mission.graph_executor import STEP_TIMEOUT_S

    assert STEP_TIMEOUT_S > _HERMES_AGENT_TIMEOUT_S
