"""L'état d'une mission survit — prouvé sur disque (HOS-252, T-19).

## L'asymétrie, mesurée en passe 18

Le registre des runs survivait ; la mission, non. `MagasinMissions`
n'était écrit que par `__setitem__`, c'est-à-dire **une seule fois, à
l'enregistrement**, avant tout démarrage. Relue sur disque après un vrai
travail :

    mission ayant tourné 531 s, 6 nœuds réussis sur 7
    -> READY / started_at=None / tous les nœuds PENDING

Conséquence directe sur HOS-248 : `started_at` est le **t0 canonique du
budget**, et il ne franchissait pas la frontière du processus. Une mission
reprise après redémarrage repartait donc avec 3 600 s entières.

C'est le pendant exact de HOS-245, qui avait rendu durable l'*existence*
d'une mission : ici c'est son *état*.

## Aucun second stockage

Le magasin est celui de M-8. Le persisteur est un appelable injecté dans
`GraphExecutor`, de la même forme que `on_event` et `execute_node` qui y
étaient déjà.
"""

from __future__ import annotations

import pytest

from backend.execution.execution_controller import ExecutionController
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import (
    RuntimeUnavailableError,
    TaskExecutionOutcome,
)
from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import Mission, MissionEdge, MissionNode, MissionStatus
from backend.mission.node_execution import make_node_executor
from backend.mission.persistance import MagasinMissions
from backend.storage.database_manager import DatabaseManager


class _Executeur:
    def __init__(self, reussit: bool = True) -> None:
        self.reussit = reussit

    def execute(self, task, assignment=None, **_):
        if not self.reussit:
            raise RuntimeUnavailableError("runtime indisponible (test)")
        return TaskExecutionOutcome(
            result="fait", runtime_id="ollama", model="m",
            duration_ms=1.0, prompt_tokens=1, completion_tokens=1)


@pytest.fixture
def magasin(tmp_path):
    """Un magasin jetable — le vrai, sur une base à lui."""
    from backend.config.config_models import DatabaseConfig

    return MagasinMissions(DatabaseManager(DatabaseConfig(name=str(tmp_path / "m"))))


def _chaine(magasin, executeur=None):
    """La vraie chaîne, avec le magasin en persisteur."""
    moteur = MissionExecutor(task_executor=executeur or _Executeur())
    return GraphExecutor(
        execute_node=make_node_executor(ExecutionController(moteur)),
        persister=magasin.enregistrer,
    )


def _mission(n: int = 2):
    mission = Mission(title="Durable", objective="produire")
    noeuds = [MissionNode(node_id=f"n{i}", title=f"Étape {i}") for i in range(n)]
    aretes = [MissionEdge(source_id=f"n{i}", target_id=f"n{i + 1}")
              for i in range(n - 1)]
    return mission, noeuds, aretes


def _relire(magasin, mission):
    """Ce que **le disque** dit, jamais l'objet en mémoire."""
    return magasin.lire(mission.mission_id)


# ═══ Les transitions déterminantes ════════════════════════════════════

def test_le_demarrage_est_durable(magasin):
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission()
    graphe.build_graph(mission, noeuds, aretes)
    magasin.enregistrer(mission)

    graphe.start_mission(mission)

    relue = _relire(magasin, mission)
    assert relue.status == MissionStatus.RUNNING
    assert relue.started_at is not None, (
        "started_at est le t0 du budget missionnel : sans lui sur disque, "
        "une reprise repart d'un budget entier")
    assert relue.started_at == mission.started_at


def test_chaque_noeud_terminal_est_durable(magasin):
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(3)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    graphe.execute_step(mission)
    apres_un = _relire(magasin, mission)
    termines = [n for n in apres_un.nodes if n.status.value == "completed"]
    assert len(termines) == 1, [n.status for n in apres_un.nodes]

    for _ in range(4):
        if graphe.execute_step(mission) == 0:
            break
    apres_tout = _relire(magasin, mission)
    assert all(n.status.value == "completed" for n in apres_tout.nodes)


def test_un_noeud_echoue_est_durable(magasin):
    graphe = _chaine(magasin, _Executeur(reussit=False))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    for _ in range(4):
        if graphe.execute_step(mission) == 0:
            break

    relue = _relire(magasin, mission)
    assert any(n.status.value == "failed" for n in relue.nodes)


def test_l_etat_terminal_de_la_mission_est_durable(magasin):
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    for _ in range(6):
        if graphe.execute_step(mission) == 0:
            break

    relue = _relire(magasin, mission)
    assert relue.status == MissionStatus.COMPLETED
    assert relue.completed_at is not None


def test_l_annulation_est_durable(magasin):
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    graphe.cancel_mission(mission)

    relue = _relire(magasin, mission)
    assert relue.status == MissionStatus.CANCELLED
    assert relue.completed_at is not None


# ═══ Le budget missionnel, inchangé ══════════════════════════════════

def test_le_budget_traverse_le_disque_sans_changer_de_sens(magasin):
    """HOS-248 n'est pas modifié : on rend seulement son t0 durable."""
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(2)
    mission.max_duration_seconds = 1234.0
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    relue = _relire(magasin, mission)
    assert relue.max_duration_seconds == 1234.0
    assert relue.started_at == mission.started_at


def test_une_meme_tentative_garde_son_t0(magasin):
    """Un nœud de plus ne réarme pas le chronomètre."""
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(3)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    t0 = _relire(magasin, mission).started_at

    graphe.execute_step(mission)
    assert _relire(magasin, mission).started_at == t0
    graphe.execute_step(mission)
    assert _relire(magasin, mission).started_at == t0


def test_une_nouvelle_tentative_repart_avec_un_nouveau_t0(magasin):
    """`start_mission` est ce qui ouvre une tentative, et il repose t0."""
    graphe = _chaine(magasin)
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    premier = _relire(magasin, mission).started_at

    # La reprise remet la mission en READY (retry_policy) ; on rejoue le
    # démarrage comme le ferait une seconde tentative.
    mission.status = MissionStatus.READY
    graphe.start_mission(mission)
    second = _relire(magasin, mission).started_at

    assert second > premier, "une nouvelle tentative doit repartir d'un t0 neuf"


# ═══ Atomicité : le cache ne ment pas ════════════════════════════════

def test_une_ecriture_reussie_se_relit_depuis_le_disque(magasin):
    """Écriture, cache, relecture — la chaîne complète."""
    from backend.mission.routes import _RegistreMissions

    registre = _RegistreMissions(magasin=magasin)
    mission, _, _ = _mission()
    mission.status = MissionStatus.RUNNING
    registre.persister(mission)

    assert magasin.lire(mission.mission_id).status == MissionStatus.RUNNING
    assert registre.get(mission.mission_id) is mission


def test_un_echec_d_ecriture_ne_produit_aucune_fausse_reussite(magasin):
    """Le cas qui distingue `persister` de `__setitem__`.

    `__setitem__` sert la création et avale l'échec du magasin — c'est un
    choix assumé, « une correction de persistance qui empêcherait de créer
    une mission serait un recul ». Mais il met le cache à jour quand même :
    la mémoire affirmerait une durabilité qui n'existe pas, ce qui est
    précisément le défaut que ce jalon ferme.
    """
    from backend.mission.routes import _RegistreMissions

    class _Casse:
        def enregistrer(self, mission):
            raise OSError("disque plein")

        def lire(self, mission_id):
            return None

        def tous(self):
            return []

    registre = _RegistreMissions(magasin=_Casse())
    mission, _, _ = _mission()
    mission.status = MissionStatus.RUNNING

    with pytest.raises(OSError):
        registre.persister(mission)

    assert registre.get(mission.mission_id) is None, (
        "le cache prétend qu'une mutation non écrite a réussi")


def test_un_echec_d_ecriture_remonte_jusqu_a_l_appelant(magasin):
    """`GraphExecutor` ne rattrape pas : un magasin muet rendrait la
    mission ingouvernable, et le silence coûterait plus cher."""
    def refuser(mission):
        raise OSError("disque plein")

    moteur = MissionExecutor(task_executor=_Executeur())
    graphe = GraphExecutor(
        execute_node=make_node_executor(ExecutionController(moteur)),
        persister=refuser)
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)

    with pytest.raises(OSError):
        graphe.start_mission(mission)


def test_sans_persisteur_le_comportement_est_celui_d_avant(magasin):
    """Les appelants qui construisent le moteur sans magasin ne changent
    pas de comportement."""
    moteur = MissionExecutor(task_executor=_Executeur())
    graphe = GraphExecutor(execute_node=make_node_executor(ExecutionController(moteur)))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)

    assert graphe.start_mission(mission) is True
    assert magasin.lire(mission.mission_id) is None


# ═══ Un autre processus ══════════════════════════════════════════════

def test_l_etat_se_relit_depuis_un_processus_neuf(tmp_path):
    """Le vrai redémarrage : deux interpréteurs, une base.

    Rien de l'objet en mémoire ne survit — seul le disque parle.
    """
    import json
    import os
    import subprocess
    import sys
    import textwrap

    racine = str(tmp_path / "etat")
    base = str(tmp_path / "missions")
    depot = str(__import__("pathlib").Path(__file__).resolve().parents[2])

    ecrire = textwrap.dedent(f'''
        import json, sys
        sys.path.insert(0, {depot!r})
        from backend.config.config_models import DatabaseConfig
        from backend.execution.execution_controller import ExecutionController
        from backend.execution.mission_executor import MissionExecutor
        from backend.execution.task_executor import TaskExecutionOutcome
        from backend.mission.graph_executor import GraphExecutor
        from backend.mission.mission_models import Mission, MissionEdge, MissionNode
        from backend.mission.node_execution import make_node_executor
        from backend.mission.persistance import MagasinMissions
        from backend.storage.database_manager import DatabaseManager

        class E:
            def execute(self, task, assignment=None, **_):
                return TaskExecutionOutcome(result="fait", runtime_id="ollama",
                                            model="m", duration_ms=1.0,
                                            prompt_tokens=1, completion_tokens=1)

        magasin = MagasinMissions(DatabaseManager(DatabaseConfig(name={base!r})))
        graphe = GraphExecutor(
            execute_node=make_node_executor(ExecutionController(
                MissionExecutor(task_executor=E()))),
            persister=magasin.enregistrer)
        m = Mission(title="Redemarrage", objective="produire")
        n = [MissionNode(node_id="n0", title="A"), MissionNode(node_id="n1", title="B")]
        graphe.build_graph(m, n, [MissionEdge(source_id="n0", target_id="n1")])
        graphe.start_mission(m)
        graphe.execute_step(m)
        print(json.dumps({{"id": m.mission_id, "t0": m.started_at.isoformat()}}))
    ''')

    relire = textwrap.dedent(f'''
        import json, sys
        sys.path.insert(0, {depot!r})
        from backend.config.config_models import DatabaseConfig
        from backend.mission.persistance import MagasinMissions
        from backend.storage.database_manager import DatabaseManager

        magasin = MagasinMissions(DatabaseManager(DatabaseConfig(name={base!r})))
        mid = sys.argv[1]
        m = magasin.lire(mid)
        print(json.dumps({{
            "statut": str(m.status),
            "t0": m.started_at.isoformat() if m.started_at else None,
            "budget": m.max_duration_seconds,
            "noeuds": [str(n.status) for n in m.nodes],
        }}))
    ''')

    env = {**os.environ, "HERMES_DATA_DIR": racine}
    p1 = subprocess.run([sys.executable, "-c", ecrire], capture_output=True,
                        text=True, env=env, timeout=180)
    assert p1.returncode == 0, p1.stderr[-1500:]
    ecrit = json.loads(p1.stdout.strip().splitlines()[-1])

    p2 = subprocess.run([sys.executable, "-c", relire, ecrit["id"]],
                        capture_output=True, text=True, env=env, timeout=180)
    assert p2.returncode == 0, p2.stderr[-1500:]
    relu = json.loads(p2.stdout.strip().splitlines()[-1])

    assert relu["statut"] == "MissionStatus.RUNNING"
    assert relu["t0"] == ecrit["t0"], (
        "le t0 canonique du budget n'a pas survécu au changement de processus")
    assert relu["budget"] == 3600.0
    assert "NodeStatus.COMPLETED" in relu["noeuds"], relu["noeuds"]


# ═══ Anti-contournement ══════════════════════════════════════════════

def test_aucun_second_magasin_de_missions():
    """Une garde AST : `MagasinMissions` reste le seul."""
    import ast
    import io
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2] / "backend"
    interdits = ("MissionStore", "MissionRepository", "MissionPersistence",
                 "MagasinMissionsV2", "MissionStateStore")
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


def test_une_mutation_en_memoire_sans_persistance_est_detectable(magasin):
    """Ce que le défaut donnait, et que le test doit savoir voir."""
    moteur = MissionExecutor(task_executor=_Executeur())
    graphe = GraphExecutor(  # sans persisteur : le comportement d'avant
        execute_node=make_node_executor(ExecutionController(moteur)))
    mission, noeuds, aretes = _mission(2)
    graphe.build_graph(mission, noeuds, aretes)
    magasin.enregistrer(mission)
    graphe.start_mission(mission)

    assert mission.status == MissionStatus.RUNNING           # en mémoire
    assert _relire(magasin, mission).status != MissionStatus.RUNNING  # sur disque
