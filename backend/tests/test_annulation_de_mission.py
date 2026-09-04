"""Annuler veut dire cesser d'engager, pas interrompre (HOS-252, T-18).

## Le défaut, mesuré en passe 18

`POST /autonomous/{id}/cancel` posait `goal.status = CANCELLED` et
s'arrêtait là. **Personne ne lisait ce champ** hors des compteurs de
`get_status` : la marche du graphe s'arrête sur `mission.status`, pas sur
celui de l'objectif. Un opérateur voyait `success: true` et l'objectif
continuait de travailler.

HOS-102 avait corrigé l'*accessibilité* de cet appel — le verrou tenu
pendant toute l'inférence le rendait injoignable — mais pas son *effet*.

## Ce qui n'a pas été créé

Aucune seconde primitive d'annulation. `graph_executor.cancel_mission`
reste la seule, et c'est celle que `cancel_goal` appelle désormais.
Aucun mécanisme de terminaison de processus non plus : l'invariant
« un nœud engagé n'est pas interrompu » est celui du budget missionnel
(HOS-247) et il tient ici aussi.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.execution.execution_controller import ExecutionController
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import TaskExecutionOutcome
from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import Mission, MissionEdge, MissionNode, MissionStatus
from backend.mission.node_execution import make_node_executor


class _ExecuteurLent:
    """Un nœud qui travaille, et qu'on n'a pas le droit d'interrompre."""

    def __init__(self, duree: float = 0.6) -> None:
        self.duree = duree
        self.demarres = 0
        self.termines = 0
        self.en_cours = threading.Event()

    def execute(self, task, assignment=None, **_):
        self.demarres += 1
        self.en_cours.set()
        time.sleep(self.duree)
        self.termines += 1
        return TaskExecutionOutcome(
            result="fait", runtime_id="ollama", model="m",
            duration_ms=self.duree * 1000, prompt_tokens=1, completion_tokens=1)


def _chaine(executeur):
    moteur = MissionExecutor(task_executor=executeur)
    return GraphExecutor(execute_node=make_node_executor(ExecutionController(moteur)))


def _mission(n: int = 3):
    mission = Mission(title="Annulation", objective="produire")
    noeuds = [MissionNode(node_id=f"n{i}", title=f"Étape {i}") for i in range(n)]
    aretes = [MissionEdge(source_id=f"n{i}", target_id=f"n{i + 1}")
              for i in range(n - 1)]
    return mission, noeuds, aretes


# ═══ La sémantique ════════════════════════════════════════════════════

def test_aucune_tache_nouvelle_n_est_engagee_apres_annulation():
    executeur = _ExecuteurLent(duree=0.05)
    graphe = _chaine(executeur)
    mission, noeuds, aretes = _mission(3)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    graphe.execute_step(mission)          # le premier nœud passe
    engages = executeur.demarres
    graphe.cancel_mission(mission)

    # La marche s'arrête sur l'état terminal ; on le montre en tentant
    # explicitement de continuer.
    assert mission.status == MissionStatus.CANCELLED
    assert executeur.demarres == engages, (
        "une tâche a été engagée après l'annulation")


def test_un_noeud_deja_engage_termine_son_travail():
    """L'invariant, prouvé plutôt qu'affirmé.

    Le nœud est lancé dans un fil, l'annulation tombe pendant qu'il
    travaille, et il doit malgré tout aller au bout. Une annulation qui le
    tuerait serait une seconde autorité de terminaison — ce que ce dépôt
    refuse tant qu'aucune décision n'a tranché la propriété des processus.
    """
    executeur = _ExecuteurLent(duree=0.8)
    graphe = _chaine(executeur)
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    fil = threading.Thread(target=graphe.execute_step, args=(mission,), daemon=True)
    fil.start()
    assert executeur.en_cours.wait(timeout=5), "le nœud n'a jamais démarré"

    graphe.cancel_mission(mission)
    fil.join(timeout=10)

    assert not fil.is_alive()
    assert executeur.termines == 1, (
        "le nœud engagé n'a pas terminé : l'annulation l'a interrompu, ce "
        "que l'invariant interdit")


def test_une_annulation_deux_fois_reste_terminale():
    graphe = _chaine(_ExecuteurLent(0.01))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    assert graphe.cancel_mission(mission) is True
    fini_le = mission.completed_at
    assert graphe.cancel_mission(mission) is True
    assert mission.status == MissionStatus.CANCELLED
    assert mission.completed_at >= fini_le


def test_une_mission_terminee_ne_s_annule_pas():
    graphe = _chaine(_ExecuteurLent(0.01))
    mission, noeuds, aretes = _mission(1)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    for _ in range(4):
        if graphe.execute_step(mission) == 0:
            break

    assert mission.status == MissionStatus.COMPLETED
    assert graphe.cancel_mission(mission) is False


# ═══ Le branchement de l'objectif autonome ═══════════════════════════

def _orchestrateur(graphe):
    from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

    return AutonomousOrchestrator(graph_executor=graphe)


def test_annuler_un_objectif_atteint_la_mission(monkeypatch):
    """Le fil qui manquait : `cancel_goal` doit toucher le graphe."""
    from backend.mission import routes as mission_routes

    graphe = _chaine(_ExecuteurLent(0.01))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    orchestrateur = _orchestrateur(graphe)
    objectif = type("O", (), {"goal_id": "g1", "status": None})()
    session = type("S", (), {"session_id": "s1", "mission_id": mission.mission_id})()
    orchestrateur._goals["g1"] = objectif
    orchestrateur._sessions["s1"] = session
    orchestrateur._session_by_goal["g1"] = "s1"
    monkeypatch.setattr(mission_routes, "get_mission_by_id",
                        lambda mid: mission if mid == mission.mission_id else None)

    assert orchestrateur.cancel_goal("g1") is True
    assert mission.status == MissionStatus.CANCELLED, (
        "cancel_goal n'a pas atteint la mission : c'est exactement le "
        "chemin mort mesuré en passe 18")


def test_poser_le_statut_de_l_objectif_ne_suffit_pas(monkeypatch):
    """Anti-régression : le drapeau seul ne doit plus être accepté.

    Si quelqu'un ramenait `cancel_goal` à son ancienne implémentation, ce
    test resterait vert sur la première assertion et rouge sur la seconde
    — c'est la seconde qui porte la propriété.
    """
    from backend.autonomous.autonomous_models import GoalStatus
    from backend.mission import routes as mission_routes

    graphe = _chaine(_ExecuteurLent(0.01))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    orchestrateur = _orchestrateur(graphe)
    objectif = type("O", (), {"goal_id": "g1", "status": None})()
    session = type("S", (), {"session_id": "s1", "mission_id": mission.mission_id})()
    orchestrateur._goals["g1"] = objectif
    orchestrateur._sessions["s1"] = session
    orchestrateur._session_by_goal["g1"] = "s1"
    monkeypatch.setattr(mission_routes, "get_mission_by_id", lambda mid: mission)

    orchestrateur.cancel_goal("g1")

    assert objectif.status == GoalStatus.CANCELLED     # l'ancien effet
    assert mission.status == MissionStatus.CANCELLED   # le nouveau, qui compte


def test_un_objectif_inconnu_est_refuse():
    orchestrateur = _orchestrateur(_chaine(_ExecuteurLent(0.01)))
    assert orchestrateur.cancel_goal("jamais-vu") is False


def test_un_objectif_sans_mission_est_pris_en_compte():
    """Refusé à la planification, déjà rapporté : rien à arrêter, et ce
    n'est pas un échec."""
    orchestrateur = _orchestrateur(_chaine(_ExecuteurLent(0.01)))
    objectif = type("O", (), {"goal_id": "g2", "status": None})()
    orchestrateur._goals["g2"] = objectif

    assert orchestrateur.cancel_goal("g2") is True


def test_la_reponse_dit_ce_qu_annuler_veut_dire():
    """Un opérateur ne doit pas lire `success: true` comme « arrêté »."""
    from backend.autonomous.autonomous_engine import AutonomousEngine

    class _Orchestrateur:
        def cancel_goal(self, goal_id):
            return True

    moteur = AutonomousEngine.__new__(AutonomousEngine)
    moteur._orchestrator = _Orchestrateur()
    reponse = moteur.cancel_goal("g1")

    assert reponse["success"] is True
    assert "engagé" in reponse["semantique"], reponse


def test_aucune_seconde_primitive_d_annulation():
    """Une garde AST : `cancel_mission` reste seule à décider."""
    import ast
    import io
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2] / "backend"
    interdits = ("CancellationManager", "MissionCanceller", "KillSwitch",
                 "ProcessReaper")
    trouves = []
    for fichier in racine.rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ClassDef) and noeud.name in interdits:
                trouves.append(f"{fichier.name}:{noeud.name}")
    assert trouves == [], trouves


def test_l_annulation_ne_termine_aucun_processus():
    """Aucun appel de terminaison sur le chemin d'annulation.

    Une annulation qui tuerait un processus enfant créerait une seconde
    autorité de propriété — la passe 7.1 l'interdit tant qu'une décision
    n'a pas tranché « absence d'enregistrement ≠ propriété utilisateur ».
    """
    import ast
    import inspect
    import textwrap

    from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

    source = textwrap.dedent(inspect.getsource(AutonomousOrchestrator.cancel_goal))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    tueurs = [a for a in appels
              if any(m in a.lower() for m in ("kill", "terminate", "taskkill"))]
    assert tueurs == [], tueurs
