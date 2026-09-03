"""Un run dont le porteur est mort (HOS-240).

## Le défaut, tel qu'il était écrit dans son propre CHANGELOG

HOS-221 a livré `Statut.PERDU` en notant : « `Statut.PERDU` existe dans
le vocabulaire et **rien ne le pose**. » Neuf jalons plus tard, rien ne
le posait toujours. Un processus tué laissait donc ses runs `en_cours`
pour l'éternité, et la console d'opérations les affichait comme actifs.

`test_un_module_de_production_pose_perdu` est la garde qui a été
observée **rouge** sur cet état : avant ce jalon, aucun module hors
tests n'attribuait `Statut.PERDU`.

## Ce que ces gardes refusent autant que le défaut

Un run vivant marqué perdu est pire que le défaut d'origine : il ferait
croire à une panne et déclencherait une reprise en double. La moitié de
ce fichier tient donc l'autre sens — le processus courant, un second
Hermes qui tourne, et les lignes sans preuve, qui ne se rangent avec
aucun des deux.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.runs.reconciliation import (
    Bilan,
    empreinte_du_processus,
    processus_vivant,
    reconcilier,
)
from backend.runs.registre import Cause, Registre, Statut, TERMINAUX
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]

#: Une empreinte dont le PID ne peut pas exister. 2**22 dépasse le
#: `pid_max` de Linux comme la plage de Windows.
PROCESSUS_MORT = "4194304:1.0"


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def _forcer_l_empreinte(registre: Registre, identifiant: str, valeur) -> None:
    """Réécrire l'empreinte d'un run — pour simuler un porteur mort.

    Passe par le `DatabaseManager` et non par `Registre` : aucune API
    publique ne permet de mentir sur le porteur, et c'est voulu.
    """
    registre._db.execute("UPDATE runs SET processus = ? WHERE identifiant = ?",
                         (valeur, identifiant))


# ═══ La garde rouge : PERDU était inatteignable ══════════════════════

def test_un_module_de_production_pose_perdu():
    """Observée **rouge** avant HOS-240 : la liste était vide.

    Sur l'arbre syntaxique et non sur le texte — ce dépôt a payé cinq
    fois le prix d'une recherche de sous-chaîne, et ce fichier-ci
    *mentionne* `Statut.PERDU` à chaque paragraphe sans le poser.
    """
    import ast
    import io

    poseurs: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            arguments = list(noeud.args) + [k.value for k in noeud.keywords]
            if any(isinstance(a, ast.Attribute) and a.attr == "PERDU"
                   for a in arguments):
                poseurs.append(str(fichier.relative_to(RACINE)))
    assert poseurs, (
        "aucun module de production n'attribue Statut.PERDU — l'état "
        "existe dans le vocabulaire et rien ne le pose (HOS-221)")


# ═══ Le scénario réel : un processus qui meurt ═══════════════════════

def test_un_processus_tue_laisse_un_run_que_la_reconciliation_retrouve(tmp_path):
    """Le vrai scénario, avec un vrai processus vraiment tué.

    Pas de simulation d'empreinte : un sous-processus Python ouvre un
    run dans une base partagée puis est tué **sans** la moindre chance
    de clore quoi que ce soit — `os._exit` ne déroule ni `finally`, ni
    `atexit`, ni gestionnaire de contexte. C'est exactement ce que fait
    un `taskkill /F` ou une coupure de courant.
    """
    base = tmp_path / "runs"
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(RACINE)!r})
        from backend.config.config_models import DatabaseConfig
        from backend.runs.registre import Registre
        from backend.storage.database_manager import DatabaseManager

        registre = Registre(DatabaseManager(DatabaseConfig(name={str(base)!r})))
        run = registre.ouvrir(mission="m", objectif="mourir en cours de route")
        registre.demarrer(run.identifiant)
        print(run.identifiant)
        sys.stdout.flush()
        os._exit(1)          # ni finally, ni atexit : la mort sans adieu
    """)
    fils = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=180)
    assert fils.returncode == 1, fils.stderr
    identifiant = fils.stdout.strip().splitlines()[-1]

    registre = Registre(DatabaseManager(DatabaseConfig(name=str(base))))

    # Avant réconciliation : le run est en cours et personne ne le porte.
    # C'est le défaut lui-même, constaté.
    assert registre.lire(identifiant).statut is Statut.EN_COURS
    assert processus_vivant(registre.processus_de(identifiant)) is False

    bilan = reconcilier(registre)

    assert identifiant in bilan.perdus
    run = registre.lire(identifiant)
    assert run.statut is Statut.PERDU
    assert run.cause is Cause.PROCESSUS
    assert "n'existe plus" in run.raison


def test_un_run_jamais_demarre_est_aussi_un_orphelin(registre):
    """Tué entre `ouvrir()` et `demarrer()`.

    Un run resté `en_attente` n'attend personne : le processus qui
    devait le démarrer est mort. Ne regarder que `en_cours` aurait
    laissé la moitié du défaut en place.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    assert run.statut is Statut.EN_ATTENTE
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)

    assert run.identifiant in reconcilier(registre).perdus
    assert registre.lire(run.identifiant).statut is Statut.PERDU


# ═══ Ce qui ne doit jamais être déclaré perdu ════════════════════════

def test_le_run_du_processus_courant_n_est_jamais_perdu(registre):
    """Le pire faux positif possible : se déclarer mort soi-même."""
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)

    bilan = reconcilier(registre)
    assert bilan.perdus == []
    assert run.identifiant in bilan.vivants
    assert registre.lire(run.identifiant).statut is Statut.EN_COURS


def test_le_run_d_un_autre_hermes_vivant_n_est_pas_touche(registre):
    """Deux Hermes peuvent coexister sur la même base.

    Emporter les runs du voisin serait pire que le défaut d'origine :
    il tourne, et sa mission se ferait reprendre en double.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    # Un autre processus, réellement vivant : celui du parent de ce test.
    autre = empreinte_du_processus(os.getppid())
    if processus_vivant(autre) is not True:  # pragma: no cover
        pytest.skip("le processus parent n'est pas observable ici")
    _forcer_l_empreinte(registre, run.identifiant, autre)

    bilan = reconcilier(registre)
    assert bilan.perdus == []
    assert run.identifiant in bilan.vivants


def test_un_run_sans_empreinte_n_est_ni_vivant_ni_perdu(registre):
    """Les lignes d'avant HOS-240 n'ont aucune preuve attachée.

    Le tri-état de ce dépôt interdit de les ranger avec les morts :
    « aucune preuve » n'est pas « preuve de mort ». Elles sont comptées
    à part et signalées, ce qui laisse à un humain la décision qu'aucune
    donnée ne permet de prendre.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    _forcer_l_empreinte(registre, run.identifiant, None)

    bilan = reconcilier(registre)
    assert bilan.perdus == []
    assert bilan.vivants == []
    assert run.identifiant in bilan.indecidables
    assert registre.lire(run.identifiant).statut is Statut.EN_ATTENTE


def test_un_processus_illisible_est_indecidable_et_non_mort(registre):
    """Une empreinte corrompue est une panne d'observation, pas un décès."""
    run = registre.ouvrir(mission="m", objectif="o")
    _forcer_l_empreinte(registre, run.identifiant, "n'importe quoi")

    bilan = reconcilier(registre)
    assert run.identifiant in bilan.indecidables
    assert bilan.perdus == []


@pytest.mark.parametrize("statut", TERMINAUX)
def test_un_run_deja_arrive_n_est_jamais_reecrit(registre, statut):
    """L'invariant de HOS-221 tient jusque sous la réconciliation.

    Un run `reussi` que l'on repasserait `perdu` parce que son processus
    est mort — ce qu'il est forcément, la mission étant finie — effacerait
    des résultats réels à chaque redémarrage.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    registre.terminer(run.identifiant, statut, cause=Cause.MODELE,
                      raison="le vrai motif")
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)

    bilan = reconcilier(registre)

    assert run.identifiant not in bilan.perdus
    apres = registre.lire(run.identifiant)
    assert apres.statut is statut
    assert apres.cause is Cause.MODELE
    assert apres.raison == "le vrai motif"


# ═══ Idempotence et lignée ═══════════════════════════════════════════

def test_deux_reconciliations_de_suite_ne_changent_rien(registre):
    """Appelée à chaque démarrage : elle doit converger, pas dériver."""
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)

    premier = reconcilier(registre)
    avant = registre.lire(run.identifiant)
    second = reconcilier(registre)

    assert premier.perdus == [run.identifiant]
    assert second.perdus == []          # plus rien à faire
    assert second.examines == 0         # il n'est même plus candidat
    assert registre.lire(run.identifiant).to_dict() == avant.to_dict()


def test_la_lignee_et_la_cause_survivent_a_la_perte(registre):
    """Un run perdu reste rattaché à sa tentative précédente.

    Sans cela, la question « pourquoi cette mission a-t-elle été reprise
    trois fois ? » perdrait sa réponse au premier redémarrage.
    """
    premier = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(premier.identifiant)
    registre.terminer(premier.identifiant, Statut.ECHOUE, cause=Cause.QUOTA)
    reprise = registre.reprendre(premier.identifiant, motif="quota epuise")
    registre.demarrer(reprise.identifiant)
    _forcer_l_empreinte(registre, reprise.identifiant, PROCESSUS_MORT)

    reconcilier(registre)

    perdu = registre.lire(reprise.identifiant)
    assert perdu.statut is Statut.PERDU
    assert perdu.parent == premier.identifiant
    assert perdu.tentative == 2
    assert perdu.motif_de_reprise == "quota epuise"
    assert [r.identifiant for r in registre.lignee(reprise.identifiant)] == [
        premier.identifiant, reprise.identifiant]


def test_un_run_perdu_reste_reprenable(registre):
    """Perdu n'est pas condamné : on ne sait pas ce qu'il avait fait,
    donc la reprise est la seule suite raisonnable."""
    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)
    reconcilier(registre)

    reprise = registre.reprendre(run.identifiant,
                                 motif="processus disparu au redemarrage")
    assert reprise.parent == run.identifiant
    assert reprise.tentative == 2


# ═══ Robustesse ══════════════════════════════════════════════════════

def test_une_base_vide_ne_produit_rien(registre):
    bilan = reconcilier(registre)
    assert bilan.to_dict() == {"perdus": [], "vivants": [],
                               "indecidables": [], "examines": 0}


def test_une_base_illisible_ne_fait_pas_echouer_le_demarrage():
    """Appelée dans le `lifespan` : elle ne doit jamais lever.

    Un Hermes qui refuserait de démarrer parce qu'il n'a pas su lire son
    journal des runs échangerait un défaut d'affichage contre une panne
    totale.
    """
    class Cassé:
        def non_termines(self):
            raise RuntimeError("disque absent")

    assert reconcilier(Cassé()) == Bilan()


def test_perdu_a_sa_propre_cause():
    """`INCONNUE` aurait été un mensonge poli.

    Elle signifie « cherchée, non trouvée ». Ici la cause est connue et
    constatée : le processus porteur n'existe plus.
    """
    assert Cause.PROCESSUS.value == "processus"
    assert Cause.PROCESSUS is not Cause.INCONNUE


def test_la_colonne_est_ajoutee_a_une_base_anterieure(tmp_path):
    """Une base ouverte avant HOS-240 n'a pas la colonne `processus`.

    Sans migration, l'`INSERT` nommé de `ouvrir()` échouerait et plus
    aucun run ne s'ouvrirait : une correction d'observabilité aurait
    cassé l'exécution.
    """
    from backend.runs import registre as module

    # Le vrai schema de HOS-221, prive de la seule ligne que ce jalon
    # ajoute : reconstruire une table approximative ne prouverait rien.
    ancien = chr(10).join(l for l in module._SCHEMA.splitlines()
                          if "processus" not in l)
    assert "processus" not in ancien and "cree_le" in ancien

    db = DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs")))
    db.initialize()
    conn = db.get_connection()
    conn.executescript(ancien)
    conn.execute("INSERT INTO runs (identifiant, mission, statut, cree_le) "
                 "VALUES ('vieux', 'm', 'en_cours', '2026-01-01')")
    conn.commit()

    registre = Registre(db)          # migre en s'ouvrant

    colonnes = {l[1] for l in db.get_connection().execute(
        "PRAGMA table_info(runs)")}
    assert "processus" in colonnes
    # La ligne d'avant survit, sans empreinte — donc indécidable.
    assert reconcilier(registre).indecidables == ["vieux"]


def test_la_reconciliation_est_appelee_au_demarrage():
    """Un module correct que personne n'appelle ne corrige rien.

    C'est le défaut exact de J17 : dix routes justes, posées sur un
    routeur monté nulle part.
    """
    import ast
    import io

    arbre = ast.parse(io.open(RACINE / "backend" / "main.py",
                              encoding="utf-8").read())
    # `reconcilier` est passee a `asyncio.to_thread` : elle apparait comme
    # argument, pas comme `func` d'un appel. Chercher les seuls `n.func`
    # aurait declare la garde rouge alors que le cablage etait bon.
    appels = {ast.unparse(n) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any("reconcilier" in a for a in appels), (
        "`reconcilier` n'est appelée nulle part dans main.py — les runs "
        "orphelins resteraient en_cours au redémarrage")


def test_aucune_regle_d_orphelin_ne_repose_sur_un_delai():
    """Un délai mesure l'impatience de l'observateur, pas la mort.

    Une mission longue sur un modèle local lent dépasse n'importe quel
    seuil raisonnable, et se ferait déclarer perdue **en tournant**.
    """
    import ast
    import inspect

    from backend.runs import reconciliation

    arbre = ast.parse(inspect.getsource(reconciliation))
    noms = {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)}
    assert not ({"timedelta", "datetime", "time"} & noms), (
        "la réconciliation manipule du temps — un orphelin doit se "
        "démontrer par la mort de son porteur, jamais par son âge")
