"""Quel modèle a réellement exécuté cette mission ? (HOS-241)

## Le défaut, mesuré

`backend/runs/registre.py` porte les colonnes `modele` et `fournisseur`
depuis HOS-221. `backend/services/vue_operations.py` les sert. Le Cockpit
les affiche. Et **personne ne les écrivait** : une recherche sur les
appelants de `ouvrir`/`terminer` ne trouve aucun `modele=` hors de la
définition du dataclass. Elles valaient la chaîne vide pour tous les runs
jamais enregistrés, si bien que la question du titre n'avait pas de
réponse — pas une mauvaise réponse : pas de réponse.

`runtime`, lui, était écrit — mais à `ouvrir()`, donc **avant**
l'exécution, depuis `assigned_runtime`. C'est l'intention du
coordinateur, pas le fait. Les deux diffèrent : une reprise change de
modèle, et une tâche assignée au cloud sans client cloud tourne en local.

## Ce que ce jalon n'a **pas** trouvé

L'audit visait « les bascules silencieuses de `RealTaskExecutor` ». Il
n'y en avait pas là où on les attendait : `task_executor` lit le runtime
qui a servi **dans la réponse**, pas dans la demande, et son commentaire
dit explicitement que faire l'inverse « réintroduirait la malhonnêteté
que R-001 existe pour supprimer ». Le maillon manquant était le dernier :
cette honnêteté ne traversait pas jusqu'au registre.

## La bascule silencieuse qui existait vraiment

`use_cloud = self._cloud_chat is not None and … == "openrouter"`.
Sans clé OpenRouter — le cas par défaut, mesuré en J17 : « 0 fournisseur
configuré » — une tâche explicitement assignée au cloud tournait en local
sans un seul message, et le registre inscrivait quand même « openrouter ».
"""

from __future__ import annotations

import ast
import io
import logging
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.runs.registre import Registre, Statut
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


# ═══ La garde rouge : le registre était muet sur le modèle ═══════════

def test_un_module_de_production_inscrit_le_modele_execute():
    """Observée **rouge** avant HOS-241 : personne n'écrivait `modele`.

    Sur l'arbre syntaxique : ce fichier-ci écrit `modele` à chaque
    paragraphe sans rien inscrire, et cinq faux positifs de sous-chaîne
    ont déjà été payés sur ce chantier.
    """
    ecrivains: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts or fichier.name == "registre.py":
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call)
                    and ast.unparse(noeud.func).endswith("constater")
                    and any(k.arg == "modele" for k in noeud.keywords)):
                ecrivains.append(str(fichier.relative_to(RACINE)))
    assert ecrivains, (
        "aucun module de production n'inscrit le modèle exécuté — la "
        "colonne existe, la vue l'affiche, et elle reste vide")


def test_le_registre_distingue_l_intention_du_fait(registre):
    """Le cœur du défaut, exercé de bout en bout.

    Le run naît sur ce que le coordinateur a demandé, puis apprend ce qui
    a réellement servi. Écraser la demande serait aussi faux que de la
    garder : les deux se lisent, et leur écart est l'information.
    """
    run = registre.ouvrir(mission="m", objectif="o", runtime="openrouter")
    registre.demarrer(run.identifiant)
    assert registre.lire(run.identifiant).modele == ""   # le défaut

    registre.constater(run.identifiant, runtime="ollama",
                       modele="qwen3.6-35b-a3b")

    apres = registre.lire(run.identifiant)
    assert apres.runtime == "ollama"
    assert apres.modele == "qwen3.6-35b-a3b"
    assert apres.statut is Statut.EN_COURS       # constater ne clôt rien


def test_un_constat_n_ecrase_pas_un_run_arrive(registre):
    """Le gel terminal de HOS-221 s'applique aussi aux faits.

    Un run clos dont on pourrait encore réécrire le modèle rendrait sa
    trace négociable — et une trace négociable ne prouve rien.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    registre.constater(run.identifiant, modele="le vrai")
    registre.terminer(run.identifiant, Statut.REUSSI)

    registre.constater(run.identifiant, modele="reecrit apres coup")

    assert registre.lire(run.identifiant).modele == "le vrai"


def test_constater_refuse_ce_qui_n_est_pas_un_fait_d_execution(registre):
    """Une porte d'écriture générique deviendrait un contournement du gel.

    `constater` existe pour trois colonnes ; lui laisser écrire `statut`
    ou `cause` ferait d'elle un second chemin vers la décision, sans
    aucune des gardes de `terminer`.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    with pytest.raises(ValueError, match="faits d'exécution"):
        registre.constater(run.identifiant, statut="reussi")
    with pytest.raises(ValueError):
        registre.constater(run.identifiant, cause="modele")


def test_un_constat_vide_n_efface_rien(registre):
    """Une tâche qui n'a jamais tourné n'a pas de modèle.

    Écrire la chaîne vide par-dessus un modèle constaté transformerait
    « une tâche sur trois n'a pas démarré » en « on ne sait pas ».
    """
    run = registre.ouvrir(mission="m", objectif="o")
    registre.constater(run.identifiant, modele="qwen3.6-35b-a3b")
    registre.constater(run.identifiant, modele="", runtime="")

    assert registre.lire(run.identifiant).modele == "qwen3.6-35b-a3b"


# ═══ Le chemin réel, jusqu'à la colonne ══════════════════════════════

def test_la_tache_porte_le_modele_qui_l_a_servie():
    """`TaskExecution` n'avait aucun champ pour le fait, seulement pour
    l'intention — `assigned_*`. Le modèle servi était capturé dans une
    variable locale de `mission_executor` et perdu à la ligne suivante.
    """
    from backend.execution.execution_models import TaskExecution

    tache = TaskExecution()
    assert tache.model_used == "", "vide tant que rien n'a tourné"
    assert hasattr(tache, "assigned_runtime")


def test_mission_executor_constate_avant_de_clore():
    """L'ordre est la garde : après `terminer`, le run est gelé.

    Constater après clore n'aurait rien écrit — et n'aurait rien dit non
    plus, puisque le gel est silencieux par conception.
    """
    import inspect
    import textwrap

    from backend.execution.mission_executor import MissionExecutor

    # `dedent`, pas `cleandoc` : cleandoc est fait pour les docstrings et
    # laisse la premiere ligne indentee, ce qui ne se parse pas.
    arbre = ast.parse(textwrap.dedent(
        inspect.getsource(MissionExecutor._clore_le_run)))
    lignes = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = ast.unparse(noeud.func)
            for verbe in ("constater", "terminer"):
                if nom.endswith(verbe) and verbe not in lignes:
                    lignes[verbe] = noeud.lineno
    assert set(lignes) == {"constater", "terminer"}
    # Comparé sur `lineno` et non sur l'ordre de parcours : `ast.walk` est
    # en largeur, et un test qui comparerait des positions de parcours
    # mesurerait la traversée, pas le code.
    assert lignes["constater"] < lignes["terminer"], (
        "le constat arrive après la clôture : le run est déjà gelé, et "
        "rien ne serait écrit")


def test_deux_modeles_sur_une_mission_sont_tous_les_deux_inscrits():
    """Le relais de phases (HOS-229) fait tourner le plan et l'exécution
    sur deux modèles. N'en garder qu'un ferait croire qu'un seul a servi.
    """
    from backend.execution.mission_executor import MissionExecutor

    joindre = MissionExecutor._joindre
    assert joindre(["a", "b"]) == "a, b"
    assert joindre(["a", "a", "b"]) == "a, b"     # dédoublonné, ordre gardé
    assert joindre(["", None, "a"]) == "a"        # les tâches non exécutées
    assert joindre([]) == ""


# ═══ La bascule silencieuse ══════════════════════════════════════════

def test_une_tache_cloud_sans_client_cloud_le_dit(caplog):
    """La bascule qui existait vraiment.

    Sans clé OpenRouter — mesuré en J17 : « 0 fournisseur configuré » —
    une tâche assignée au cloud tournait en local **sans un mot**.
    """
    from backend.execution import task_executor as module

    executeur = object.__new__(module.RealTaskExecutor)
    executeur._runtime_for = lambda _t: "openrouter"

    with caplog.at_level(logging.WARNING, logger=module.logger.name):
        assert executeur._resolve_runtime(object()) == "openrouter"

    # Le rappel lui-même n'alerte pas — c'est la branche d'exécution qui
    # constate l'absence de client. La garde structurelle ci-dessous tient
    # cette branche, qu'aucun test unitaire ne peut atteindre sans monter
    # un exécuteur complet.
    assert caplog.records == []


def test_la_branche_de_bascule_cloud_avertit():
    """Structurellement : la branche existe et journalise en `warning`.

    Elle est inatteignable sans un `RealTaskExecutor` complet et un vrai
    appel d'inférence ; la tenir sur l'arbre syntaxique vaut mieux que de
    ne pas la tenir.
    """
    source = io.open(RACINE / "backend" / "execution" / "task_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)

    trouvee = False
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If):
            continue
        test = ast.unparse(noeud.test)
        if "openrouter" not in test or "runtime_demande" not in test:
            continue
        corps = " ".join(ast.unparse(n) for n in noeud.body)
        if "logger.warning" in corps:
            trouvee = True
    assert trouvee, (
        "aucune branche n'avertit qu'une tâche assignée à openrouter "
        "s'exécute en local — la bascule serait de nouveau silencieuse")


def test_aucun_rappel_de_resolution_n_echoue_en_silence():
    """`logger.debug` n'apparaît nulle part au niveau par défaut.

    Un `runtime_for` qui lève faisait retomber la tâche sur le runtime
    par défaut sans laisser de trace : le choix de l'opérateur était
    défait, et rien ne le disait.
    """
    import inspect
    import textwrap

    from backend.execution.task_executor import RealTaskExecutor

    # **Tous** les rappels de résolution, découverts et non énumérés :
    # la première version de cette garde en listait trois, et il y en
    # avait six. Deux des trois manquants — `workspace` et `num_ctx` —
    # portaient les bascules les plus graves : une tâche sans outils, et
    # un contexte tronqué qui fait dire à l'agent qu'il n'a pas d'outils.
    methodes = [getattr(RealTaskExecutor, n) for n in dir(RealTaskExecutor)
                if n.startswith("_resolve_")]
    assert len(methodes) >= 5, "les rappels de résolution ont été renommés"
    for methode in methodes:
        arbre = ast.parse(textwrap.dedent(inspect.getsource(methode)))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ExceptHandler):
                corps = " ".join(ast.unparse(n) for n in noeud.body)
                assert "logger.debug" not in corps, (
                    f"{methode.__name__} avale son échec en `debug` — la "
                    "bascule qui suit serait invisible")


# ═══ Ce que le RAL reste ═════════════════════════════════════════════

def test_le_constat_ne_cree_pas_une_seconde_autorite():
    """`Registre.constater` enregistre ; elle ne décide pas.

    Un registre qui se mettrait à choisir un runtime deviendrait un
    second routeur à côté du RAL — exactement ce que ce dépôt interdit.
    """
    import inspect

    from backend.runs import registre as module

    arbre = ast.parse(inspect.getsource(module))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("ral" in (m or "").split(".") for m in modules), (
        "le registre importe le RAL — il deviendrait un second chemin "
        "vers la décision de routage")
