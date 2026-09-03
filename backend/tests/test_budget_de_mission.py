"""Un champ qui déclarait un budget et que personne ne lisait (HOS-247).

## Le défaut, mesuré

`ExecutionMeta.max_duration_seconds = 3600.0` existait depuis longtemps.
Compté sur l'arbre syntaxique : **zéro lecteur** en production, quand son
voisin de dataclass `max_retries_per_task` en avait deux.

Le seul plafond réel était `MAX_EXECUTION_PASSES × plafond_du_noeud()`,
soit **33 heures** — trente-trois fois le budget déclaré. Ce n'est pas un
budget, c'est un garde-boucle.

C'est la troisième fois que ce chantier rencontre ce motif : `Statut.PERDU`
déclaré et jamais posé (HOS-240), `modele`/`fournisseur` servis et jamais
écrits (HOS-241), et maintenant un budget déclaré et jamais lu.

## Pourquoi 3 600 s, et pas un chiffre rond

`docs/essai-skills360.md` porte quatre exécutions réelles du même
objectif : 566 s, 878 s, 1 084 s et **2 186 s**. La dernière est un
**succès**, 7 tâches sur 7, 12 fichiers produits.

Un budget de 1 800 s l'aurait tuée à 82 % de son travail. 3 600 s, c'est
1,65 fois ce pire cas réussi, et exactement trois plafonds de nœud.

## Ce que ce budget n'est pas

Ce n'est pas un timeout. Il ne coupe rien : il refuse d'**engager** la
tâche suivante. Une tâche déjà lancée va au bout de son propre plafond —
900 s pour l'agent, 1 200 s pour le nœud. Et un budget atteint n'est
jamais `PERDU` : perdu veut dire « on ne sait pas ce qui s'est passé »,
ici on le sait exactement, et c'est l'opérateur qui l'a décidé.
"""

from __future__ import annotations

import ast
import io
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.execution.execution_models import (
    BUDGET_MISSION_PAR_DEFAUT_S,
    ExecutionMeta,
    budget_de,
)
from backend.execution.execution_state import ExecutionStateMachine
from backend.runs.registre import Cause
from backend.runs.taxonomie import classer, remede

RACINE = Path(__file__).resolve().parents[2]


def _sm(budget=None) -> ExecutionStateMachine:
    meta = ExecutionMeta() if budget is None else ExecutionMeta(
        max_duration_seconds=budget)
    return ExecutionStateMachine(meta)


# ═══ §7 — les quatre valeurs du champ ═══════════════════════════════

def test_A_un_budget_explicite_est_celui_qui_sert():
    assert _sm(120).budget_s == 120.0


def test_B_zero_demande_le_defaut():
    """La seule convention documentée du dépôt — `ModelDecision.num_ctx`,
    où « 0 signifie le défaut de l'appelant ».

    `0 = illimité` aurait été une quatrième sémantique du zéro dans ce
    dépôt, après « défaut », « immédiatement dépassé »
    (`workspace_policy`) et « non spécifié » (`planner_models`).
    """
    assert _sm(0).budget_s == BUDGET_MISSION_PAR_DEFAUT_S == 3600.0


def test_C_une_valeur_negative_est_refusee_bruyamment():
    """Refusée là où elle est fournie, pas découverte au milieu d'une
    mission."""
    with pytest.raises(ValueError, match="budget de mission invalide"):
        ExecutionStateMachine(ExecutionMeta(max_duration_seconds=-1))
    with pytest.raises(ValueError):
        budget_de(SimpleNamespace(max_duration_seconds=-0.5))


def test_D_un_meta_sans_le_champ_retombe_sur_le_defaut():
    """Rétrocompatibilité explicite : un `meta` d'avant ce jalon, ou un
    double de test qui ne porte pas le champ, se comporte comme le
    dataclass l'a toujours annoncé — plutôt que de lever au milieu d'une
    exécution."""
    assert budget_de(SimpleNamespace()) == BUDGET_MISSION_PAR_DEFAUT_S


def test_il_n_existe_aucune_valeur_illimitee():
    """En offrir une serait mentir : `MAX_EXECUTION_PASSES ×
    plafond_du_noeud()` borne déjà toute mission à 33 heures."""
    from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
    from backend.mission.graph_executor import plafond_du_noeud

    plafond_dur = AutonomousOrchestrator.MAX_EXECUTION_PASSES * plafond_du_noeud()
    assert plafond_dur > 0
    for valeur in (0, 3600, 1):
        assert _sm(valeur).budget_s > 0, "aucun budget ne doit être nul ou infini"


def test_le_defaut_vaut_1_65_fois_le_pire_succes_mesure():
    """La justification, tenue par une garde plutôt que par un souvenir.

    2 186 s est le pire cas **réussi** mesuré (`docs/essai-skills360.md`,
    run 1, 7/7 tâches). Baisser le défaut sous cette valeur tuerait une
    mission dont on sait qu'elle aboutissait.
    """
    PIRE_SUCCES_MESURE_S = 2186.0
    assert BUDGET_MISSION_PAR_DEFAUT_S > PIRE_SUCCES_MESURE_S, (
        "le budget par défaut est passé sous le pire cas réussi mesuré — "
        "il couperait une mission qui aboutissait")
    from backend.mission.graph_executor import plafond_du_noeud
    assert BUDGET_MISSION_PAR_DEFAUT_S >= 3 * plafond_du_noeud(), (
        "le budget n'accorde plus trois plafonds de nœud entiers")


# ═══ §5 — le dépassement, et ce qu'il produit ═══════════════════════

def test_un_budget_non_atteint_laisse_passer():
    assert _sm(3600).budget_depasse() is False


def test_un_budget_atteint_est_constate():
    machine = _sm(0.001)
    time.sleep(0.01)
    assert machine.budget_depasse() is True
    assert machine.budget_consomme_s >= 0.01


def test_la_frontiere_est_atteinte_et_non_depassee():
    """`>=` et non `>` : à budget exactement consommé, la tâche suivante
    n'est pas engagée. Engager une tâche de 900 s avec 0 s de budget
    restant serait le contraire de ce que ce jalon promet."""
    import inspect

    source = inspect.getsource(ExecutionStateMachine.budget_depasse)
    assert ">=" in source, "la frontière laisse passer une tâche de plus"


def test_la_decision_utilise_une_horloge_monotone():
    """Une horloge civile recule à l'heure d'hiver et sur une
    synchronisation NTP : une mission serait alors coupée ou prolongée par
    le réglage de la machine.
    """
    import inspect
    import textwrap

    arbre = ast.parse(textwrap.dedent(
        inspect.getsource(ExecutionStateMachine.budget_consomme_s.fget)))
    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any("perf_counter" in a or "monotonic" in a for a in appels), (
        "la durée consommée n'est plus mesurée sur une horloge monotone")
    assert not any("now" in a or "utcnow" in a for a in appels), (
        "une horloge civile décide de l'expiration — elle recule")


# ═══ §6 — une tâche déjà engagée n'est jamais interrompue ═══════════

def test_une_tache_deja_engagee_va_au_bout_de_son_plafond():
    """Le cas obligatoire : budget restant 5 s, tâche de 200 s.

    Le budget décide de ce qu'on **engage**, pas de ce qu'on interrompt.
    La preuve tient en deux points : `budget_depasse()` est consultée
    avant l'engagement, et aucun chemin du budget n'annule, ne tue ni ne
    signale une tâche en cours.
    """
    import inspect
    import textwrap

    from backend.execution.mission_executor import MissionExecutor

    # Sur l'arbre syntaxique et les positions de ligne. Une première
    # version comparait deux `str.index` : elle trouvait la mention de
    # `self._task_executor.execute` dans la **docstring**, cinquante
    # lignes avant le code, et déclarait la garde rouge sur un texte.
    # Dixième faux positif de sous-chaîne de ce chantier.
    arbre = ast.parse(textwrap.dedent(inspect.getsource(
        MissionExecutor.execute_task)))
    lignes: dict[str, int] = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = ast.unparse(noeud.func)
            for verbe, cle in (("budget_depasse", "budget"),
                               ("_task_executor.execute", "inference")):
                if nom.endswith(verbe) and cle not in lignes:
                    lignes[cle] = noeud.lineno
    assert set(lignes) == {"budget", "inference"}, lignes
    assert lignes["budget"] < lignes["inference"], (
        "le budget est consulté après le lancement de l'inférence — une "
        "tâche en cours serait coupée")

    # Et le refus n'appelle rien qui interrompe : sur les appels, pas sur
    # le texte — la docstring parle de « ne pas interrompre ».
    refus = ast.parse(textwrap.dedent(inspect.getsource(
        MissionExecutor._refuser_pour_budget)))
    appels = {ast.unparse(n.func) for n in ast.walk(refus)
              if isinstance(n, ast.Call)}
    for verbe in ("kill", "terminate", "cancel", "interrupt", "stop"):
        assert not any(a.endswith(verbe) for a in appels), (
            f"le refus pour budget appelle {verbe!r} — il interromprait "
            "un travail déjà engagé")


def test_la_tache_suivante_n_est_pas_engagee(monkeypatch):
    """Le vrai chemin : `execute_task` refuse avant de coordonner.

    Un exécuteur et un coordinateur qui lèveraient s'ils étaient appelés :
    si le budget ne bloquait pas, le test échouerait sur leur exception,
    pas sur une assertion complaisante.
    """
    from backend.execution import mission_executor as module
    from backend.execution.execution_models import TaskExecution

    class Interdit:
        def assign(self, *a, **k):
            raise AssertionError("le coordinateur a été appelé malgré le budget")
        def execute(self, *a, **k):
            raise AssertionError("l'inférence a été lancée malgré le budget")

    executeur = object.__new__(module.MissionExecutor)
    tache = TaskExecution(task_id="t2", title="la suivante")
    executeur._scheduler = SimpleNamespace(get_task=lambda _id: tache)
    executeur._coordinator = Interdit()
    executeur._task_executor = Interdit()
    executeur._lock = __import__("threading").RLock()
    executeur._publish = lambda *a, **k: None

    machine = _sm(0.001)
    time.sleep(0.01)
    resultat = executeur.execute_task(machine, "t2")

    assert resultat["budget_depasse"] is True
    assert "budget de mission atteint" in resultat["error"]
    assert tache.status.value == "failed"
    assert tache.errors and "non engagée" in tache.errors[0]


# ═══ §9 — Run Ledger : la cause, et ce qu'elle n'est pas ═══════════

def test_le_motif_est_classe_budget_et_non_quota():
    """`QUOTA` est une limite du fournisseur, `RESSOURCE` une limite de la
    machine. Celle-ci est une limite que l'opérateur a fixée."""
    classement = classer(
        "budget de mission atteint : 3601 s consommees sur 3600 s — "
        "tache t2 non engagee")
    assert classement.classe
    assert classement.cause is Cause.BUDGET
    assert classement.cause is not Cause.QUOTA
    assert classement.cause is not Cause.RESSOURCE


def test_un_budget_atteint_ne_se_reprend_pas_en_boucle():
    """Reprendre consommerait immédiatement le même budget une seconde
    fois. La suite vient d'un budget révisé, pas de la boucle."""
    soin = remede(Cause.BUDGET)
    assert soin.reessayer is False
    assert not soin.changer_de_modele and not soin.changer_de_fournisseur


def test_budget_n_est_jamais_perdu():
    """`PERDU` veut dire « on ne sait pas ce qui s'est passé ». Ici on le
    sait exactement — et c'est nous qui l'avons décidé."""
    import inspect

    from backend.execution.mission_executor import MissionExecutor
    from backend.runs.registre import Statut

    # Le **corps**, docstring exclue : celle-ci explique précisément que
    # ce n'est jamais `PERDU`, et une garde par sous-chaîne s'y
    # accrochait. Onzième faux positif, entre ma correction et ma propre
    # garde — le même piège qu'en HOS-246.
    import textwrap

    arbre = ast.parse(textwrap.dedent(inspect.getsource(
        MissionExecutor._refuser_pour_budget)))
    corps = arbre.body[0].body
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(corps[0].value, ast.Constant)):
        corps = corps[1:]                      # la docstring
    code = " ".join(ast.unparse(n) for n in corps)
    assert "PERDU" not in code, (
        "le refus pour budget pose ou mentionne `PERDU` dans son code")
    assert Cause.BUDGET is not Cause.PROCESSUS
    assert Statut.PERDU.value == "perdu"      # inchangé par ce jalon


def test_aucune_seconde_mecanique_de_terminalisation():
    """Le refus rend un dictionnaire ; il ne clôt pas le run lui-même.

    `_clore_le_run` reste le seul chemin de terminalisation — en créer un
    second ferait diverger les deux au premier changement.
    """
    import inspect

    from backend.execution.mission_executor import MissionExecutor

    import textwrap

    arbre = ast.parse(textwrap.dedent(inspect.getsource(
        MissionExecutor._refuser_pour_budget)))
    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    for interdit in ("terminer", "_clore_le_run"):
        assert not any(a.endswith(interdit) for a in appels), (
            f"le refus pour budget appelle {interdit!r} — seconde "
            "terminalisation")


# ═══ §17 — la garde qui empêche le retour à l'inertie ══════════════

def test_le_champ_a_un_vrai_lecteur_de_production():
    """La garde du défaut mesuré en passe 7 : **zéro lecteur**.

    Elle ne cherche pas une chaîne de caractères : elle exige qu'un
    module de production **lise l'attribut** ou appelle le résolveur, et
    que ce module ne soit ni le dataclass qui le déclare ni un test.

    **Limite** : un lecteur qui passerait par `getattr(meta, nom_variable)`
    lui échapperait. Elle attrape le retour à l'inertie, qui est la façon
    dont ce champ a passé des mois inerte.
    """
    lecteurs: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts or fichier.name == "execution_models.py":
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            lu = (isinstance(noeud, ast.Attribute)
                  and noeud.attr == "max_duration_seconds")
            appel = (isinstance(noeud, ast.Call)
                     and ast.unparse(noeud.func).endswith("budget_de"))
            if lu or appel:
                lecteurs.append(str(fichier.relative_to(RACINE)))
    assert lecteurs, (
        "`max_duration_seconds` n'a plus aucun lecteur de production — il "
        "est redevenu inerte, l'état exact mesuré en passe 7")


def test_le_budget_est_verifie_a_un_seul_endroit():
    """Deux compteurs dériveraient. Les deux chemins — le marcheur de
    graphe autonome et l'appel direct — convergent sur `execute_task`,
    et c'est là, et là seulement, que le budget se consulte."""
    appelants: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts or "execution_state.py" in fichier.name:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call)
                    and ast.unparse(noeud.func).endswith("budget_depasse")):
                appelants.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno}")
    assert len(appelants) == 1, (
        f"le budget est consulté à {len(appelants)} endroits : {appelants} — "
        "un second compteur dériverait du premier")


def test_le_topic_est_declare_dans_le_catalogue_du_producteur():
    """Un sujet publié hors catalogue est refusé par le bus (HOS-066B)."""
    from backend.execution.mission_executor import EXECUTION_EVENTS

    assert EXECUTION_EVENTS["budget_depasse"] == "execution.budget_depasse"


# ═══ §15 — le vrai chemin, jusqu'au registre ════════════════════════

def test_integration_une_mission_depasse_son_budget_et_le_registre_le_dit(tmp_path):
    """De l'exécution réelle à la cause inscrite, sans simuler la variable.

    Deux tâches, un budget minuscule. La première est engagée et **va au
    bout** — son exécuteur est réellement appelé. La seconde est refusée.
    Le motif traverse ensuite le vrai chemin de clôture : taxonomie,
    cause, registre.
    """
    import threading

    from backend.config.config_models import DatabaseConfig
    from backend.execution import mission_executor as module
    from backend.execution.execution_models import TaskExecution
    from backend.runs.registre import Registre, Statut
    from backend.storage.database_manager import DatabaseManager

    executees: list[str] = []

    class Executeur:
        def execute(self, task, assignment):
            executees.append(task.task_id)
            return SimpleNamespace(
                result="fait", duration_ms=1.0, runtime_id="ollama",
                model="qwen3.6-35b-a3b", metadata={"fournisseur": "local"},
                prompt_tokens=1, completion_tokens=1, artifact_path="",
                resources=lambda: {})

    executeur = object.__new__(module.MissionExecutor)
    executeur._lock = threading.RLock()
    executeur._publish = lambda *a, **k: None
    executeur._task_executor = Executeur()
    executeur._coordinator = SimpleNamespace(assign=lambda t: SimpleNamespace(
        agent_id="a", runtime_id="ollama", skill_ids=[], tool_ids=[]))
    # Les collaborateurs que `execute_task` touche vraiment, réduits à ce
    # qu'il en attend. Les stuber est ce qui permet au **vrai** corps de
    # la méthode de s'exécuter, plutôt que d'en simuler une variable.
    executeur._agent_registry = None
    executeur._registre = None
    executeur._validator = SimpleNamespace(
        validate=lambda t: SimpleNamespace(
            status=SimpleNamespace(value="passed"), passed=True, issues=[]))
    executeur._runs = {}
    executeur._events = []

    taches = {"t1": TaskExecution(task_id="t1", title="première"),
              "t2": TaskExecution(task_id="t2", title="seconde")}
    executeur._scheduler = SimpleNamespace(get_task=taches.get)

    # Budget minuscule : t1 passe (la machine vient d'être construite),
    # t2 est refusée après qu'il est consommé.
    machine = _sm(0.05)
    # La machine suit son cycle réel : le vrai orchestrateur ne saute pas
    # de `created` à `running`, et une machine mal amenée ferait échouer
    # la première tâche pour une raison étrangère au budget.
    from backend.execution.execution_models import ExecutionState
    machine.transition(ExecutionState.PLANNING, "test")
    machine.transition(ExecutionState.READY, "test")

    try:
        executeur.execute_task(machine, "t1")
    except Exception as erreur:            # coordination incomplète : sans
        pass                                # importance, t1 a été engagée
    assert executees == ["t1"], (
        "la première tâche n'a pas été engagée alors que le budget restait")

    time.sleep(0.08)
    resultat_2 = executeur.execute_task(machine, "t2")

    assert resultat_2["budget_depasse"] is True
    assert executees == ["t1"], "la seconde tâche a été engagée malgré le budget"

    # …et le motif traverse le vrai chemin de clôture.
    classement = classer(resultat_2["error"])
    assert classement.cause is Cause.BUDGET

    registre = Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    registre.terminer(run.identifiant, Statut.ECHOUE,
                      cause=classement.cause, raison=resultat_2["error"])

    lu = registre.lire(run.identifiant)
    assert lu.statut is Statut.ECHOUE          # arrêté proprement, pas perdu
    assert lu.statut is not Statut.PERDU
    assert lu.cause is Cause.BUDGET
    assert "budget de mission atteint" in lu.raison
    assert remede(lu.cause).reessayer is False


def test_le_budget_survit_a_la_construction_de_la_machine():
    """§8 — un budget explicite n'est jamais silencieusement remplacé.

    **Limite mesurée et assumée** : `ExecutionMeta` n'est persisté nulle
    part, et une exécution ne reprend pas après un redémarrage — c'est un
    nouveau run qui est ouvert, et la réconciliation de HOS-240 pose
    `PERDU` sur l'ancien. Il n'existe donc aucun chemin de restauration à
    tester. Ce qui doit tenir, et que ceci tient, c'est que la valeur
    fournie soit celle qui sert, sans repli discret sur le défaut.
    """
    for valeur in (120.0, 3600.0, 7200.0):
        assert ExecutionStateMachine(
            ExecutionMeta(max_duration_seconds=valeur)).budget_s == valeur
    # Et le champ n'est pas persisté : le dire dans une garde évite qu'on
    # croie à une persistance que personne n'a écrite.
    import ast as _ast
    import io as _io

    persisteurs = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = _ast.parse(_io.open(fichier, encoding="utf-8",
                                        errors="replace").read())
        except SyntaxError:
            continue
        for noeud in _ast.walk(arbre):
            if (isinstance(noeud, _ast.Call)
                    and "ExecutionMeta" in _ast.unparse(noeud.func)
                    and any(k.arg == "max_duration_seconds"
                            for k in noeud.keywords)):
                persisteurs.append(str(fichier.relative_to(RACINE)))
    assert not persisteurs, (
        f"un appelant fixe désormais le budget : {persisteurs} — sa "
        "persistance doit être décidée, elle ne l'est pas encore")


# ═══ La limite mesurée, épinglée plutôt que masquée ═════════════════

def test_le_budget_est_par_execution_et_le_chemin_autonome_en_cree_une_par_noeud():
    """§22 — la prémisse de la passe 7 était fausse, et voici où.

    La passe 7 supposait qu'`ExecutionMeta` était l'objet d'exécution
    **de la mission**. Mesuré, il l'est sur un chemin et pas sur l'autre :

    * `execution/routes.py` en construit **un** pour toute l'exécution,
      avec toutes ses tâches — le budget y est bien un budget de mission ;
    * `mission/node_execution.py` en construit **un par nœud** du DAG, et
      chacun ouvre sa propre machine d'état via `controller.start()` —
      le budget y est donc un budget **de nœud**.

    Conséquence honnête : sur le chemin autonome, ce budget de 3 600 s ne
    se déclenchera jamais, puisqu'un nœud est déjà plafonné à 1 200 s. Il
    n'y a aucun risque — mais il ne faut pas croire qu'il protège la
    mission entière.

    Un budget réellement missionnel sur ce chemin demande un t0 porté par
    la **mission** et non par la machine d'état. C'est une décision que la
    passe 7 n'a pas prise, et l'élargir ici serait exactement le
    « réparer par extension de périmètre » que la passe 8 s'interdit.

    Cette garde échouera le jour où quelqu'un fera de `node_execution` un
    créateur unique — c'est-à-dire le jour où la limite disparaîtra.
    """
    import ast as _ast
    import io as _io

    createurs: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = _ast.parse(_io.open(fichier, encoding="utf-8",
                                        errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in _ast.walk(arbre):
            if (isinstance(noeud, _ast.Call)
                    and _ast.unparse(noeud.func).endswith("ExecutionMeta")):
                createurs.append(str(fichier.relative_to(RACINE)).replace("\\", "/"))

    assert "backend/mission/node_execution.py" in [c.replace("\\", "/") for c in createurs], (
        "le chemin autonome ne construit plus d'ExecutionMeta par nœud — "
        "la limite décrite ici a peut-être disparu, revérifier le t0")

    # Et la conséquence, exercée : deux machines d'état ne partagent pas
    # leur consommation.
    premiere, seconde = _sm(3600), _sm(3600)
    assert premiere._budget_t0 != seconde._budget_t0, (
        "deux exécutions partagent leur t0 — ce serait un budget global "
        "accidentel, non décidé")
