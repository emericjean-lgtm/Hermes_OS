"""Le registre des exécutions, et ce qu'il empêche (HOS-221).

L'incident : la nuit du 29 au 30 août 2026, trois fois, la question
« qu'est-ce qui a été fait, avec quel modèle, et pourquoi le premier
essai a raté ? » n'a pas eu de réponse sans aller lire des fichiers JSON
**écrasés à chaque exécution**. La trace a dû être sauvée à la main,
pendant que la production tournait.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.runs.registre import Cause, Registre, Statut, TERMINAUX
from backend.storage.database_manager import DatabaseManager


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


# ── Le cycle de vie ──────────────────────────────────────────────────

def test_un_run_nait_en_attente(registre):
    """Naître `en_cours` mentirait sur l'horodatage.

    Un run créé pendant que la carte est occupée attend son tour. Le
    faire naître démarré ferait compter l'attente comme du travail.
    """
    run = registre.ouvrir(mission="m", objectif="o")
    assert run.statut is Statut.EN_ATTENTE
    assert run.demarre_le is None
    assert not run.termine


def test_un_run_est_relu_depuis_la_base(registre):
    """La trace survit à l'objet Python.

    C'est le point : la nuit du 30 août, elle vivait dans un fichier
    écrasé.
    """
    ouvert = registre.ouvrir(mission="m", modele="ltx", projet="lune",
                             workspace="C:/tmp")
    relu = registre.lire(ouvert.identifiant)
    assert relu is not None
    assert (relu.modele, relu.projet, relu.workspace) == ("ltx", "lune", "C:/tmp")


def test_lire_un_run_inconnu_rend_none(registre):
    assert registre.lire("jamais_vu") is None


# ── L'invariant d'état, dans le SQL ──────────────────────────────────

@pytest.mark.parametrize("terminal", TERMINAUX)
def test_un_etat_terminal_ne_se_reecrit_pas(registre, terminal):
    """Repris d'Agent OS, et écrit dans la requête, pas en Python.

    Une vérification en Python s'oublie sur un chemin ; un `CASE WHEN`
    dans le `UPDATE` ne peut pas être contourné par un appelant qui
    ignore la règle.
    """
    run = registre.ouvrir(mission="m")
    registre.terminer(run.identifiant, terminal)
    registre.terminer(run.identifiant, Statut.REUSSI)
    assert registre.lire(run.identifiant).statut is terminal


def test_le_gel_couvre_la_cause_et_la_raison(registre):
    """Geler le statut seul aurait produit une trace pire que rien.

    Un run figé sur `echoue` avec le motif d'un second appel a l'air
    d'une trace, et n'en est pas une.
    """
    run = registre.ouvrir(mission="m")
    registre.terminer(run.identifiant, Statut.ECHOUE,
                      cause=Cause.RESSOURCE, raison="OOM tuile 192", cout=1.5)
    registre.terminer(run.identifiant, Statut.REUSSI,
                      cause=Cause.INCONNUE, raison="réécrit", cout=99.0)

    apres = registre.lire(run.identifiant)
    assert apres.cause is Cause.RESSOURCE
    assert apres.raison == "OOM tuile 192"
    assert apres.cout == 1.5


def test_un_run_termine_ne_redemarre_pas(registre):
    run = registre.ouvrir(mission="m")
    registre.terminer(run.identifiant, Statut.REUSSI)
    registre.demarrer(run.identifiant)
    assert registre.lire(run.identifiant).statut is Statut.REUSSI


def test_perdu_n_est_pas_echoue(registre):
    """Un processus disparu n'est pas un échec.

    On ne sait pas ce qu'il avait fait avant de mourir — c'est
    précisément l'information qui manque, et la ranger sous « échoué »
    la ferait disparaître.
    """
    assert Statut.PERDU is not Statut.ECHOUE
    assert Statut.PERDU in TERMINAUX


# ── La lignée ────────────────────────────────────────────────────────

def test_une_reprise_porte_son_parent_et_son_rang(registre):
    a = registre.ouvrir(mission="m", modele="ltx", objectif="rendre le plan")
    registre.terminer(a.identifiant, Statut.ECHOUE, cause=Cause.RESSOURCE)
    b = registre.reprendre(a.identifiant, motif="tuile 192 a débordé")

    assert b.parent == a.identifiant
    assert b.tentative == 2
    # Ce qui définissait la mission suit ; ce qui décrivait la tentative
    # ratée ne suit pas.
    assert b.objectif == a.objectif
    assert b.statut is Statut.EN_ATTENTE
    assert b.cause is None


def test_une_reprise_sans_motif_est_refusee(registre):
    """Une lignée muette ne répond pas à la question qu'on lui posera.

    « Pourquoi trois tentatives ? » est exactement ce qu'on veut savoir
    six semaines plus tard.
    """
    a = registre.ouvrir(mission="m")
    registre.terminer(a.identifiant, Statut.ECHOUE)
    with pytest.raises(ValueError, match="pourquoi"):
        registre.reprendre(a.identifiant, motif="   ")


def test_une_reprise_peut_changer_de_modele(registre):
    """Le remède le plus fréquent : réessayer ailleurs."""
    a = registre.ouvrir(mission="m", modele="qwen3.8-27b")
    registre.terminer(a.identifiant, Statut.ECHOUE, cause=Cause.RESSOURCE)
    b = registre.reprendre(a.identifiant, motif="déborde en Q4",
                           modele="qwen3.6-35b-a3b")
    assert b.modele == "qwen3.6-35b-a3b"
    assert registre.lire(a.identifiant).modele == "qwen3.8-27b"


def test_la_lignee_se_lit_de_la_premiere_a_la_derniere(registre):
    a = registre.ouvrir(mission="m")
    registre.terminer(a.identifiant, Statut.ECHOUE, cause=Cause.RESSOURCE)
    b = registre.reprendre(a.identifiant, motif="ressource")
    registre.terminer(b.identifiant, Statut.ECHOUE, cause=Cause.CONTEXTE)
    c = registre.reprendre(b.identifiant, motif="contexte")

    chaine = registre.lignee(c.identifiant)
    assert [r.tentative for r in chaine] == [1, 2, 3]
    assert [r.cause for r in chaine] == [Cause.RESSOURCE, Cause.CONTEXTE, None]


def test_la_lignee_d_un_run_seul_est_lui_meme(registre):
    a = registre.ouvrir(mission="m")
    assert [r.identifiant for r in registre.lignee(a.identifiant)] == [a.identifiant]


def test_reprendre_un_run_inconnu_leve(registre):
    with pytest.raises(KeyError):
        registre.reprendre("jamais_vu", motif="peu importe")


# ── Les causes ───────────────────────────────────────────────────────

def test_les_causes_distinguent_les_remedes(registre):
    """Un retry aveugle ne sert à rien.

    Manquer de VRAM, dépasser un quota et écrire du code faux appellent
    trois remèdes différents. Les confondre sous « échec » fait
    réessayer à l'identique.
    """
    for cause in (Cause.RESSOURCE, Cause.QUOTA, Cause.SEMANTIQUE):
        run = registre.ouvrir(mission="m")
        registre.terminer(run.identifiant, Statut.ECHOUE, cause=cause)
        assert registre.lire(run.identifiant).cause is cause


# ── Les vues ─────────────────────────────────────────────────────────

def test_les_runs_d_une_mission_sont_ordonnes(registre):
    for i in range(3):
        registre.ouvrir(mission="lune", objectif=f"plan {i}")
    registre.ouvrir(mission="autre")
    assert len(registre.de_la_mission("lune")) == 3


def test_en_cours_ne_liste_que_ce_qui_tourne(registre):
    a = registre.ouvrir(mission="m")
    b = registre.ouvrir(mission="m")
    registre.demarrer(a.identifiant)
    registre.demarrer(b.identifiant)
    registre.terminer(b.identifiant, Statut.REUSSI)
    assert [r.identifiant for r in registre.en_cours()] == [a.identifiant]


# ── La structuration décidée en HOS-219 ──────────────────────────────

def test_les_trois_colonnes_de_structuration_existent(registre):
    """Trois colonnes coûtent trois colonnes maintenant.

    Et une migration sur données réelles six semaines plus tard — c'est
    la décision §8.2 du cahier.
    """
    run = registre.ouvrir(mission="m", utilisateur="local", projet="p",
                          workspace="C:/w")
    relu = registre.lire(run.identifiant)
    assert (relu.utilisateur, relu.projet, relu.workspace) == ("local", "p", "C:/w")


def test_utilisateur_vaut_local_par_defaut(registre):
    """Et n'est pas une identité vérifiée.

    Le garde qui interdit de s'en servir comme contrôle d'accès vit dans
    `test_decisions_hos_215_218.py`.
    """
    assert registre.ouvrir(mission="m").utilisateur == "local"


# ── Ce qui n'est délibérément pas ici ────────────────────────────────

def test_le_registre_ne_porte_pas_de_table_d_evenements():
    """Hermes a déjà un bus d'événements durable.

    En porter un second — comme le fait `run_events` chez Agent OS —
    créerait deux magasins d'événements, l'architecture parallèle que
    le cahier interdit à sa propre règle 4. Le registre porte les runs,
    le bus porte les événements, `run_id` les corrèle.
    """
    from backend.runs import registre as module
    assert "run_events" not in module._SCHEMA
    assert "CREATE TABLE" in module._SCHEMA
    assert module._SCHEMA.count("CREATE TABLE") == 1


def test_le_registre_reutilise_la_couche_de_base_existante():
    """Pas de troisième couche SQLite dans ce dépôt.

    `DatabaseManager` était orphelin — utilisé par personne hors de
    `backend/storage/` — mais réel et correct. Le doubler aurait ajouté
    une couche de plus au lieu de rebrancher celle qui existait.
    """
    import inspect
    source = inspect.getsource(Registre)
    assert "sqlite3.connect" not in source


def test_busy_timeout_est_pose(tmp_path):
    """Sans lui, deux écritures concurrentes lèvent au lieu d'attendre.

    WAL laisse un lecteur pendant une écriture, pas deux écrivains.
    C'était la seule PRAGMA qui manquait à `DatabaseManager`.
    """
    db = DatabaseManager(DatabaseConfig(name=str(tmp_path / "t")))
    db.initialize()
    (valeur,) = db.get_connection().execute("PRAGMA busy_timeout").fetchone()
    assert valeur == 5000
