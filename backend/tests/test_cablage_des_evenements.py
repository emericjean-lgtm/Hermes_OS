"""Le câblage des événements, prouvé vite et pour de vrai (HOS-252, T-17).

## Ce que ce fichier reprend, et à qui

`tests/integration/test_assembly.py::TestEventWiring::
test_no_real_subsystem_event_is_dropped` prouvait la même propriété en
lançant un objectif autonome complet. Mesuré en passe 18 : deux
reproductions de 608 s et 531 s **sans terminer**, pour une assertion dont
la totalité de la valeur probante était acquise à 187 s — et un plafond de
conception de ~4 800 s (budget de mission 3 600 s, vérifié entre deux
tâches seulement, plus le plafond d'un nœud engagé).

Le test long reste, et reste `lent` : il garde la preuve du **chemin
autonome réel**, avec la planification par modèle et les familles de
topics qui n'existent que là. Ce fichier-ci garde la preuve du
**câblage**, en quelques secondes.

## La seule couture, et pourquoi elle ne fabrique pas de faux vert

`GraphExecutor`, `MissionExecutor`, `EventDispatcher` et `EventHub` sont
les vrais. Rien n'est simulé de la chaîne de publication : chaque topic
observé ici est publié par du code de production, au même endroit et avec
la même forme qu'en mission réelle.

Ce qui est remplacé est l'**exécuteur de tâche** — `task_executor`, un
paramètre du constructeur de `MissionExecutor` depuis toujours, prévu pour
ça (« Injected so the engine keeps orchestrating and something else
executes »). C'est l'inférence qui disparaît, pas l'orchestration.

Conséquence assumée et vérifiable : `execution.task_completed` n'apparaît
**pas** dans la liste attendue ici, parce que c'est `RealTaskExecutor` qui
le publie — précisément le composant remplacé. L'affirmer ici reviendrait
à vérifier un événement que le test aurait lui-même émis. Il est donc
attendu du côté lent, où le vrai exécuteur tourne.
"""

from __future__ import annotations

import logging

import pytest

from backend.core.bootstrap.event_wiring import EventDispatcher
from backend.core.event_hub import EVENT_TYPES, EventHub
from backend.execution.execution_controller import ExecutionController
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import (
    RuntimeUnavailableError,
    TaskExecutionOutcome,
)
from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import Mission, MissionEdge, MissionNode, MissionStatus
from backend.mission.node_execution import make_node_executor

# ── Les topics attendus, nommés un par un ────────────────────────────
#
# Une liste explicite plutôt qu'un `len(events) >= 26` : un compteur reste
# vert quand un topic disparaît et qu'un autre apparaît, ce qui est
# exactement la dérive qu'on surveille. Chaque entrée est justifiée par
# son émetteur.
#
# Aucune normalisation n'est nécessaire : ces topics sont des chaînes
# fixes, pas des familles paramétrées. Les 26 types mesurés en passe 18 se
# répartissent en trois groupes — ceux du câblage mission/exécution, ci-
# dessous ; ceux du chemin autonome et de la planification, prouvés par le
# test lent ; et ceux du démarrage des agents, publiés à la construction
# de l'application et couverts par les tests d'assemblage.

TOPICS_DU_CHEMIN_NOMINAL = (
    "mission.created",          # graph_executor.build_graph
    "mission.started",          # graph_executor.start_mission
    "mission.node_ready",       # graph_executor.execute_step
    "mission.node_completed",   # graph_executor.execute_step, nœud réussi
    "mission.completed",        # graph_executor.execute_step, mission finie
    "execution.started",        # mission_executor.prepare
    "execution.planning",       # mission_executor.prepare
    "execution.task_started",   # mission_executor.execute_task
    "execution.completed",      # mission_executor.finalize
)

TOPICS_DU_CHEMIN_D_ECHEC = (
    "mission.node_failed",      # graph_executor.execute_step, nœud échoué
    "execution.retry",          # mission_executor, cause reprenable
)

TOPICS_D_ANNULATION = ("mission.cancelled",)


class _ExecuteurDeterministe:
    """La couture : orchestrer sans inférer.

    Ne publie **aucun** événement, délibérément. Tous les topics observés
    par ce fichier viennent donc du code de production.
    """

    def __init__(self, reussit: bool = True) -> None:
        self.reussit = reussit
        self.appels = 0

    def execute(self, task, assignment=None, **_):
        self.appels += 1
        if not self.reussit:
            # La seule exception qu'`execute_task` rattrape, et celle que
            # lève réellement un refus d'admission VRAM ou un délai dépassé.
            raise RuntimeUnavailableError("runtime indisponible (test)")
        return TaskExecutionOutcome(
            result="fait", runtime_id="ollama", model="modele-de-test",
            duration_ms=1.0, prompt_tokens=1, completion_tokens=1)


class _HubObserve(EventHub):
    """Le vrai hub, qui note ce qui le traverse."""

    def __init__(self) -> None:
        super().__init__()
        self.vus: list[str] = []

    def publish(self, event_type, payload=None, *a, **k):
        self.vus.append(str(event_type))
        return super().publish(event_type, payload, *a, **k)


class _CaptureRejets(logging.Handler):
    """« not published » — le seul message que le hub émet en jetant."""

    def __init__(self) -> None:
        super().__init__()
        self.rejets: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        texte = record.getMessage()
        if "not published" in texte:
            self.rejets.append(texte)


def _chaine_reelle(executeur=None):
    """GraphExecutor → MissionExecutor → EventDispatcher → EventHub."""
    hub = _HubObserve()
    dispatcher = EventDispatcher(system_bus=None, event_hub=hub, source="test")
    moteur = MissionExecutor(
        task_executor=executeur or _ExecuteurDeterministe(), on_event=dispatcher)
    graphe = GraphExecutor(
        on_event=dispatcher,
        execute_node=make_node_executor(ExecutionController(moteur)),
    )
    return hub, graphe


def _mission_a_deux_noeuds():
    mission = Mission(title="Câblage", objective="produire deux artefacts")
    n1 = MissionNode(node_id="n1", title="Premier")
    n2 = MissionNode(node_id="n2", title="Second")
    return mission, [n1, n2], [MissionEdge(source_id="n1", target_id="n2")]


def _marcher(graphe, mission, passes: int = 8):
    for _ in range(passes):
        if graphe.execute_step(mission) == 0:
            break


@pytest.fixture
def rejets():
    """Le journal de rejet du hub, écouté pendant le test."""
    capture = _CaptureRejets()
    journal = logging.getLogger("backend.core.event_hub")
    precedent = journal.level
    journal.setLevel(logging.WARNING)
    journal.addHandler(capture)
    try:
        yield capture
    finally:
        journal.removeHandler(capture)
        journal.setLevel(precedent)


# ═══ Le câblage nominal ═══════════════════════════════════════════════

def test_chaque_topic_du_chemin_nominal_atteint_le_hub(rejets):
    """Un par un, pas un compteur.

    L'invariant historique (HOS-066B) est qu'un topic peut être construit
    dynamiquement — `AUTONOMOUS_EVENTS["goal_received"]`, une variable — et
    qu'aucun scan de littéraux ne le voit. On regarde donc ce qui traverse
    réellement le hub pendant qu'un vrai graphe s'exécute.
    """
    hub, graphe = _chaine_reelle()
    mission, noeuds, aretes = _mission_a_deux_noeuds()

    assert graphe.build_graph(mission, noeuds, aretes) == []
    assert graphe.start_mission(mission) is True
    _marcher(graphe, mission)

    assert mission.status == MissionStatus.COMPLETED
    manquants = [t for t in TOPICS_DU_CHEMIN_NOMINAL if t not in hub.vus]
    assert manquants == [], f"topics jamais publiés : {manquants}"
    assert rejets.rejets == []


def _trace_du_chemin_nominal():
    hub, graphe = _chaine_reelle()
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    _marcher(graphe, mission)
    return hub.vus


def _trace_du_chemin_d_echec():
    """Un runtime indisponible : la taxonomie juge la cause reprenable et
    `mission_executor` publie `execution.retry`."""
    hub, graphe = _chaine_reelle(_ExecuteurDeterministe(reussit=False))
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    _marcher(graphe, mission)
    return hub.vus


def _trace_de_l_annulation():
    hub, graphe = _chaine_reelle()
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    graphe.cancel_mission(mission)
    return hub.vus


def _trace_du_budget():
    """Le vrai chemin du budget, avec un budget de test minuscule.

    `MissionExecutor.prepare/execute_task` est le chemin de production —
    celui de `POST /execution/start` — et la seule chose de test ici est
    la **valeur** du budget. Rien n'est publié artificiellement : c'est
    `_refuser_pour_budget` qui émet, comme en mission réelle.
    """
    import time

    from backend.execution.execution_models import ExecutionMeta, TaskExecution

    hub = _HubObserve()
    dispatcher = EventDispatcher(system_bus=None, event_hub=hub, source="test")
    moteur = MissionExecutor(task_executor=_ExecuteurDeterministe(),
                             on_event=dispatcher)
    meta = ExecutionMeta(mission_id="budget", max_duration_seconds=0.001,
                         max_retries_per_task=0)
    sm = moteur.prepare(meta, [TaskExecution(task_id="t1", mission_id="budget")])
    # Le budget se vérifie **avant** d'engager la tâche : il suffit qu'il
    # soit consommé, et 1 ms l'est dès la construction terminée.
    time.sleep(0.05)
    moteur.execute_task(sm, "t1")
    moteur.finalize(sm)
    return hub.vus


#: Les quatre chemins que le câblage doit couvrir. Nommés plutôt
#: qu'implicites : c'est la liste qu'on étend quand un cinquième chemin
#: publie quelque chose de nouveau.
CHEMINS = {
    "nominal": _trace_du_chemin_nominal,
    "échec/retry": _trace_du_chemin_d_echec,
    "annulation": _trace_de_l_annulation,
    "budget": _trace_du_budget,
}


@pytest.mark.parametrize("chemin", sorted(CHEMINS))
def test_les_topics_publies_sont_declares(rejets, chemin):
    """La dérive que le test historique cherchait, sous sa forme actuelle.

    Depuis HOS-066B le hub **délivre** un topic inconnu au lieu de le
    jeter : la dérive ne détruit plus rien, mais un abonné qui filtre par
    type ne voit toujours pas passer l'événement. Le contrôle porte donc
    sur la déclaration, pas sur le rejet.

    C'est ce test qui a trouvé `mission.completed` absent du catalogue :
    `graph_executor` le publie par une variable, invisible à la collecte
    AST des littéraux.

    ## Pourquoi il est paramétré depuis HOS-254

    Il n'exerçait que la **trace nominale**. Deux topics ne se produisent
    que sur des chemins d'exception — `execution.retry` quand la taxonomie
    juge une cause reprenable, `execution.budget_depasse` quand une tâche
    n'est pas engagée — et tous deux étaient publiés sans être catalogués,
    donc invisibles à tout abonné qui filtre par type. Un test de câblage
    qui ne visite qu'un chemin ne câble qu'un chemin.

    La liste `CHEMINS` est la vraie assertion : ajouter un
    `publish("execution.nouveau")` sur l'un d'eux rend ce test rouge sans
    qu'on ait à le savoir à l'avance.
    """
    vus = CHEMINS[chemin]()

    assert vus, f"le chemin {chemin!r} n'a publié aucun événement"
    non_declares = sorted({t for t in vus if t not in EVENT_TYPES})
    assert non_declares == [], (
        f"chemin {chemin!r} : topics publiés par du vrai code et absents de "
        f"EVENT_TYPES — un abonné filtrant par type ne les verra jamais : "
        f"{non_declares}")


def test_les_chemins_d_exception_publient_bien_ce_qu_on_croit():
    """Le garde-fou du garde-fou.

    Si `execution.retry` ou `execution.budget_depasse` cessaient d'être
    émis, le test paramétré ci-dessus resterait vert — il ne vérifie que
    la déclaration de ce qu'il voit. Ces deux assertions garantissent
    qu'il voit bien quelque chose à vérifier.
    """
    assert "execution.retry" in _trace_du_chemin_d_echec()
    assert "execution.budget_depasse" in _trace_du_budget()


def test_le_chemin_d_echec_publie_aussi(rejets):
    """Un nœud qui échoue produit ses propres topics."""
    hub, graphe = _chaine_reelle(_ExecuteurDeterministe(reussit=False))
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    _marcher(graphe, mission)

    manquants = [t for t in TOPICS_DU_CHEMIN_D_ECHEC if t not in hub.vus]
    assert manquants == [], f"topics d'échec jamais publiés : {manquants}"
    assert rejets.rejets == []


def test_l_annulation_publie_son_topic(rejets):
    hub, graphe = _chaine_reelle()
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)

    assert graphe.cancel_mission(mission) is True
    manquants = [t for t in TOPICS_D_ANNULATION if t not in hub.vus]
    assert manquants == [], manquants
    assert rejets.rejets == []


# ═══ Anti-contournement ══════════════════════════════════════════════

def test_un_topic_malforme_est_refuse_et_journalise(rejets):
    """`dropped == []` garde son sens — sur les topics malformés.

    C'est tout ce que `"not published"` peut encore signaler
    (`event_hub.py:130`) ; l'affirmer explicitement évite de croire que
    cette assertion couvre encore les topics inconnus, qui sont désormais
    délivrés.
    """
    hub, _ = _chaine_reelle()
    for mauvais in ("sanspoint", "", ".debut", "fin.", "avec espace.x", None, 123):
        hub.publish(mauvais, {})

    assert len(rejets.rejets) == 7, rejets.rejets


def test_executer_une_mission_sans_regarder_les_evenements_ne_prouve_rien():
    """Une mission qui se termine n'est pas une preuve de câblage.

    Ce test existe pour qu'on ne remplace pas les assertions ci-dessus par
    « la mission est COMPLETED » : le hub peut être débranché et la
    mission réussir quand même.
    """
    moteur = MissionExecutor(task_executor=_ExecuteurDeterministe(), on_event=None)
    graphe = GraphExecutor(
        on_event=None, execute_node=make_node_executor(ExecutionController(moteur)))
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    _marcher(graphe, mission)

    assert mission.status == MissionStatus.COMPLETED, (
        "sans aucun abonné ni dispatcher, la mission se termine tout de "
        "même — donc son statut ne dit rien du câblage des événements")


def test_retirer_un_topic_attendu_rend_le_test_rouge():
    """La liste attendue mord : on le montre plutôt que de l'affirmer."""
    hub, graphe = _chaine_reelle()
    mission, noeuds, aretes = _mission_a_deux_noeuds()
    graphe.build_graph(mission, noeuds, aretes)
    graphe.start_mission(mission)
    _marcher(graphe, mission)

    ampute = [t for t in hub.vus if t != "mission.node_completed"]
    manquants = [t for t in TOPICS_DU_CHEMIN_NOMINAL if t not in ampute]
    assert manquants == ["mission.node_completed"], (
        "amputer un topic de la trace doit être détecté par la liste "
        "attendue ; s'il ne l'est pas, la liste ne sert à rien")
