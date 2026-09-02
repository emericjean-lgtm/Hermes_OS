"""Le registre est branché sur le vrai chemin d'exécution (HOS-221).

L'incident que ce fichier empêche n'est pas dans la production : il est
dans ce dépôt. `backend/security/approvals.py`, `DatabaseManager` et
`MigrationManager` sont du code réel, correct, testé — et **appelés par
personne**. Un registre de runs qui finirait comme eux ne servirait
qu'à faire croire que la traçabilité existe.

Ces gardes tiennent la seule propriété qui compte : exécuter une mission
laisse une trace durable, avec sa lignée, sans qu'aucun appelant ait à y
penser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import (
    RuntimeUnavailableError,
    TaskExecutionOutcome,
)
from backend.runs.registre import Registre, Statut
from backend.storage.database_manager import DatabaseManager


class _Executeur:
    """Un exécuteur de tâche qui ne parle à aucun modèle.

    Le point mesuré ici est le branchement du registre, pas l'inférence.
    """

    def __init__(self, *, reussit: bool = True, jetons: int = 0) -> None:
        self.reussit = reussit
        self.jetons = jetons

    def execute(self, task, assignment=None, **_):
        if not self.reussit:
            # Le vrai chemin d'échec du moteur : c'est la seule exception
            # qu'``execute_task`` rattrape, et celle que lève réellement
            # un refus d'admission VRAM ou un délai Ollama dépassé.
            raise RuntimeUnavailableError("OOM tuile 192")
        return TaskExecutionOutcome(
            result="fait", runtime_id="ollama", model="qwen3.6-35b-a3b",
            duration_ms=12.0, prompt_tokens=self.jetons,
            completion_tokens=self.jetons * 2)


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def _executer(registre, executeur, *, objectif="produire la vidéo"):
    moteur = MissionExecutor(task_executor=executeur, registre=registre)
    # Sans reprise : on mesure la trace d'un échec, pas la politique de
    # réessai, qui a ses propres gardes ailleurs.
    meta = ExecutionMeta(mission_id="lune", user_goal=objectif,
                         max_retries_per_task=0)
    sm = moteur.prepare(meta, [TaskExecution(task_id="t1", title="plan 01",
                                             mission_id="lune")])
    identifiant = moteur.run_de(meta.execution_id)
    moteur.execute_task(sm, "t1")
    return moteur, moteur.finalize(sm), identifiant


# ── Le branchement lui-même ──────────────────────────────────────────

def test_preparer_une_execution_inscrit_un_run(registre):
    moteur = MissionExecutor(task_executor=_Executeur(), registre=registre)
    meta = ExecutionMeta(mission_id="lune", user_goal="produire la vidéo")
    moteur.prepare(meta, [TaskExecution(task_id="t1", mission_id="lune")])

    identifiant = moteur.run_de(meta.execution_id)
    assert identifiant, "aucun run ouvert — le registre serait un orphelin"

    run = registre.lire(identifiant)
    assert run.statut is Statut.EN_COURS
    assert run.mission == "lune"
    assert run.objectif == "produire la vidéo"


def test_une_execution_reussie_clot_son_run(registre):
    _, rapport, identifiant = _executer(registre, _Executeur())
    assert registre.lire(identifiant).statut is Statut.REUSSI


def test_une_execution_echouee_porte_sa_raison(registre):
    """La question sans réponse de la nuit du 30 août.

    Pas « ça a raté » mais « ça a raté avec ce message, sur cette
    mission, à cette tentative ».
    """
    _, rapport, identifiant = _executer(registre, _Executeur(reussit=False))
    run = registre.lire(identifiant)
    assert run.statut is Statut.ECHOUE
    assert "OOM tuile 192" in run.raison


def test_les_jetons_mesures_arrivent_au_registre(registre):
    """Mesurés par le runtime, pas ré-estimés ici.

    Une estimation refaite au registre divergerait de la télémétrie, et
    on ne saurait plus laquelle croire.
    """
    _, _, identifiant = _executer(registre, _Executeur(jetons=100))
    run = registre.lire(identifiant)
    assert run.jetons_entree == 100
    assert run.jetons_sortie == 200


def test_la_trace_survit_a_l_objet_moteur(registre, tmp_path):
    """Le point du jalon : elle est en base, pas dans un `deque`.

    `MissionExecutor._events` est explicitement « a diagnostic tail, not
    an archive », plafonné à 2000 entrées. Le registre, lui, se relit
    après un redémarrage.
    """
    _, _, identifiant = _executer(registre, _Executeur())
    autre = Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))
    assert autre.lire(identifiant).statut is Statut.REUSSI


def test_aucun_run_ne_reste_en_cours_apres_finalize(registre):
    """Un run qui resterait `en_cours` ressemblerait à un travail en cours.

    C'est la leçon du décodage qui a rampé quarante minutes : l'attente
    ressemble au travail.
    """
    _executer(registre, _Executeur())
    _executer(registre, _Executeur(reussit=False))
    assert registre.en_cours() == []


def test_deux_executions_de_la_meme_mission_font_deux_runs(registre):
    """Une reprise n'écrase pas la tentative qu'elle reprend.

    C'était le comportement du fichier JSON écrasé à chaque exécution.
    """
    _executer(registre, _Executeur(reussit=False))
    _executer(registre, _Executeur())
    runs = registre.de_la_mission("lune")
    assert len(runs) == 2
    assert {r.statut for r in runs} == {Statut.ECHOUE, Statut.REUSSI}


# ── La trace ne casse jamais la mission ──────────────────────────────

def test_un_registre_en_panne_ne_fait_pas_echouer_la_mission():
    """Une trace qui casse ce qu'elle décrit ne vaut rien.

    Même règle que `_sync_agent_started`, qui la documente déjà : la
    télémétrie est en meilleur effort.
    """
    class Casse:
        def ouvrir(self, **k): raise RuntimeError("base indisponible")
        def demarrer(self, i): raise RuntimeError("base indisponible")
        def terminer(self, i, s, **k): raise RuntimeError("base indisponible")

    moteur = MissionExecutor(task_executor=_Executeur(), registre=Casse())
    meta = ExecutionMeta(mission_id="lune", user_goal="o")
    sm = moteur.prepare(meta, [TaskExecution(task_id="t1", mission_id="lune")])
    moteur.execute_task(sm, "t1")
    rapport = moteur.finalize(sm)
    assert rapport.completed_tasks == 1


def test_run_de_ne_ment_pas_quand_le_registre_est_absent():
    """Rendre un identifiant qui ne désigne rien serait pire que None."""
    class Casse:
        def ouvrir(self, **k): raise RuntimeError("nope")
    moteur = MissionExecutor(task_executor=_Executeur(), registre=Casse())
    meta = ExecutionMeta(mission_id="m", user_goal="o")
    moteur.prepare(meta, [TaskExecution(task_id="t1")])
    assert moteur.run_de(meta.execution_id) is None


# ── Ce qui reste délibérément non fait ───────────────────────────────

def test_la_cause_n_est_pas_devinee_depuis_le_message():
    """Classer un échec demande la taxonomie, qui est son propre jalon.

    Deviner maintenant produirait des étiquettes fausses — et une
    étiquette fausse coûte plus cher qu'une case vide, parce qu'on la
    croit.
    """
    import inspect
    from backend.execution import mission_executor
    source = inspect.getsource(mission_executor.MissionExecutor._clore_le_run)
    assert "cause=" not in source
    assert "taxonomie" in source
