"""Le moteur de mise à jour, pour de bon (HOS-233).

## Ce que l'audit de J16 a trouvé

HOS-232 sauvegardait l'**état** et le restaurait. Il ne touchait pas au
code : `mise_a_jour.py` n'écrivait rien hors de la racine d'état. Le
moteur n'était donc pas un moteur de mise à jour — c'était un filet.

Trois défauts mesurés avant d'écrire une ligne :

1. **Aucun remplacement de code.**
2. **`workflows` vit sous la racine d'état réelle, hors `preserve_set()`.**
   La garde de HOS-232 ne l'a pas vu **parce qu'elle lit le code et non
   le disque** — un résidu de la migration HOS-215, annulée depuis.
3. **Le `.env` de l'utilisateur vit dans l'arbre de code.**
   `SettingsConfigDict(env_file=".env")` le résout depuis le répertoire
   courant, donc à la racine du dépôt. Un remplacement naïf détruirait
   la clé OpenRouter.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from backend.maj import code as _code
from backend.maj import paquet as _paquet
from backend.maj.mise_a_jour import Etape, MiseAJour
from backend.maj.version import (
    IncompatibiliteVersion,
    ecrire_version_installee,
    lire_version_installee,
    verifier_la_compatibilite,
)

SECRET = "sk-le-secret-de-lutilisateur-0123456789"


@pytest.fixture
def etat(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path / "etat"))
    import backend.core.etat as module

    module.racine.cache_clear()
    racine = module.racine()
    (racine / "db").mkdir(parents=True, exist_ok=True)
    (racine / "db" / "hermes.db").write_text("données v1", encoding="utf-8")
    (racine / "checkpoints").mkdir(parents=True, exist_ok=True)
    (racine / "checkpoints" / "cp.json").write_text("filet v1", encoding="utf-8")
    ecrire_version_installee("1.0.0", racine)
    yield racine
    module.racine.cache_clear()


@pytest.fixture
def installation(tmp_path) -> Path:
    """Un arbre de code, avec ce qu'un utilisateur y a mis."""
    racine = tmp_path / "hermes"
    (racine / "backend").mkdir(parents=True)
    (racine / "backend" / "app.py").write_text("VERSION 1", encoding="utf-8")
    (racine / "backend" / "ancien.py").write_text("v1 seulement", encoding="utf-8")
    (racine / ".env").write_text(f"OPENROUTER_API_KEY={SECRET}",
                                 encoding="utf-8")
    (racine / ".venv").mkdir()
    (racine / ".venv" / "gros.bin").write_text("x" * 100, encoding="utf-8")
    return racine


@pytest.fixture
def paquet(tmp_path) -> Path:
    racine = tmp_path / "paquet-v2"
    (racine / "backend").mkdir(parents=True)
    (racine / "backend" / "app.py").write_text("VERSION 2", encoding="utf-8")
    (racine / "hermes.json").write_text(
        json.dumps({"version": "1.1.0", "racines": ["backend"]}),
        encoding="utf-8")
    return racine


# ═══ Le paquet : validé avant de rien coûter ═════════════════════════

def test_un_repertoire_quelconque_n_est_pas_un_paquet(tmp_path):
    (tmp_path / "vide").mkdir()
    with pytest.raises(_paquet.PaquetInvalide, match="hermes.json"):
        _paquet.lire(tmp_path / "vide")


def test_un_paquet_sans_version_est_refuse(tmp_path):
    racine = tmp_path / "p"
    racine.mkdir()
    (racine / "hermes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(_paquet.PaquetInvalide, match="version"):
        _paquet.lire(racine)


def test_une_version_de_paquet_illisible_est_refusee(tmp_path):
    """Différent d'un **état installé** sans version, qui signifie « très
    ancien » et doit pouvoir être mis à jour.

    Ici c'est un paquet qu'on ne sait pas placer.
    """
    racine = tmp_path / "p"
    racine.mkdir()
    (racine / "hermes.json").write_text(json.dumps({"version": "abîmée"}),
                                        encoding="utf-8")
    with pytest.raises(_paquet.PaquetInvalide, match="illisible"):
        _paquet.lire(racine)


def test_un_paquet_qui_annonce_une_racine_absente_est_refuse(tmp_path):
    """L'installer viderait ce répertoire."""
    racine = tmp_path / "p"
    racine.mkdir()
    (racine / "hermes.json").write_text(
        json.dumps({"version": "1.0.0", "racines": ["backend"]}),
        encoding="utf-8")
    with pytest.raises(_paquet.PaquetInvalide, match="ne le contient pas"):
        _paquet.lire(racine)


@pytest.mark.parametrize("evasion", ["..", "../ailleurs", "/etc"])
def test_une_racine_qui_s_echappe_est_refusee(tmp_path, evasion):
    """Un paquet est du contenu qu'on n'a pas écrit.

    Un `..` ou un chemin absolu dans la liste des racines écrirait hors
    de l'installation — même confinement que `empreinte.couvre`.
    """
    racine = tmp_path / "p"
    racine.mkdir()
    (racine / "hermes.json").write_text(
        json.dumps({"version": "1.0.0", "racines": [evasion]}),
        encoding="utf-8")
    with pytest.raises(_paquet.PaquetInvalide):
        _paquet.lire(racine)


def test_un_paquet_invalide_ne_coute_rien(etat, installation, paquet):
    """Ni sauvegarde orpheline, ni étape."""
    (paquet / "hermes.json").unlink()
    issue = MiseAJour(installation=installation).appliquer(paquet)
    assert issue.reussie is False
    assert issue.etapes == []
    assert issue.sauvegarde is None


# ═══ La compatibilité : aucune mise à jour aveugle ═══════════════════

def test_une_installation_sans_version_est_acceptee():
    """Toutes celles qui existent aujourd'hui.

    La refuser interdirait la première mise à jour à tout le monde.
    """
    assert verifier_la_compatibilite("", "1.0.0")


def test_revenir_en_arriere_n_est_pas_une_mise_a_jour():
    """C'est un `restaurer()`, pas un `appliquer()`.

    Cette porte n'a pas les migrations descendantes, et faire passer
    l'une pour l'autre laisserait un schéma neuf sous un code ancien.
    """
    with pytest.raises(IncompatibiliteVersion, match="antérieure"):
        verifier_la_compatibilite("1.2.0", "1.1.0")


def test_une_version_trop_ancienne_est_refusee():
    with pytest.raises(IncompatibiliteVersion, match="minimum"):
        verifier_la_compatibilite("0.5.0", "2.0.0", depuis_au_moins="1.0.0")


def test_reinstaller_la_meme_version_est_permis():
    """Une réparation légitime."""
    assert "réinstallation" in verifier_la_compatibilite("1.0.0", "1.0.0")


def test_un_refus_de_compatibilite_ne_touche_a_rien(etat, installation, paquet):
    (paquet / "hermes.json").write_text(
        json.dumps({"version": "0.9.0", "racines": ["backend"]}),
        encoding="utf-8")
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert issue.etapes == []
    assert (installation / "backend" / "app.py").read_text(
        encoding="utf-8") == "VERSION 1"


# ═══ Le remplacement réel du code ════════════════════════════════════

def test_le_code_est_reellement_remplace(etat, installation, paquet):
    """Le manque central de J16 : le moteur ne touchait pas au code."""
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert issue.reussie is True
    assert Etape.REMPLACEMENT.value in issue.etapes
    assert (installation / "backend" / "app.py").read_text(
        encoding="utf-8") == "VERSION 2"


def test_le_remplacement_retire_ce_que_la_v2_n_a_plus(etat, installation,
                                                      paquet):
    """Une copie par-dessus laisserait un arbre mi-ancien mi-nouveau,
    qui importe et qui ment."""
    MiseAJour(installation=installation, valider=lambda: True).appliquer(paquet)
    assert not (installation / "backend" / "ancien.py").exists()


def test_le_secret_de_l_utilisateur_survit_au_remplacement(etat, installation,
                                                           paquet):
    """Mesuré : `.env` vit **dans** l'arbre de code.

    `SettingsConfigDict(env_file=".env")` le résout depuis le répertoire
    courant. Un remplacement naïf détruirait la clé OpenRouter.
    """
    MiseAJour(installation=installation, valider=lambda: True).appliquer(paquet)
    assert (installation / ".env").read_text(encoding="utf-8") == (
        f"OPENROUTER_API_KEY={SECRET}")


def test_les_environnements_installes_survivent(etat, installation, paquet):
    """`.venv` pèse des gigaoctets et se reconstruit.

    Le sauver ferait de chaque mise à jour une copie de plusieurs
    minutes, donc une mise à jour qu'on ne lance pas.
    """
    MiseAJour(installation=installation, valider=lambda: True).appliquer(paquet)
    assert (installation / ".venv" / "gros.bin").exists()


@pytest.mark.parametrize("protege", [".git", ".env", ".venv", "node_modules"])
def test_la_liste_des_preserves_en_place_est_explicite(protege):
    assert protege in _code.PRESERVE_EN_PLACE


# ═══ Les secrets ne fuient nulle part ════════════════════════════════

def test_le_secret_n_est_pas_copie_dans_la_sauvegarde(etat, installation,
                                                      paquet):
    """Une sauvegarde de secret est un secret de plus, en clair, dans un
    dossier que personne ne surveille."""
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    racine_sauvegarde = Path(issue.sauvegarde_code.chemin)
    for fichier in racine_sauvegarde.rglob("*"):
        if fichier.is_file():
            assert SECRET not in fichier.read_text(encoding="utf-8",
                                                   errors="replace")


def test_le_secret_n_est_pas_dans_le_manifeste(etat, installation, paquet):
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    manifeste = json.dumps({
        "etat": issue.sauvegarde.__dict__ if issue.sauvegarde else {},
        "code": issue.sauvegarde_code.__dict__ if issue.sauvegarde_code else {},
    }, default=str)
    assert SECRET not in manifeste
    # Le **nom** du fichier préservé est là, et c'est voulu : un lecteur
    # doit pouvoir vérifier qu'il a été protégé.
    assert ".env" in issue.sauvegarde_code.preserves


def test_le_secret_n_est_pas_dans_les_evenements(etat, installation, paquet,
                                                 caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert SECRET not in caplog.text
    assert SECRET not in json.dumps(issue.etapes) + issue.raison


def test_le_secret_n_est_pas_dans_le_rapport_de_sante(etat):
    from backend.maj.sante import verifier

    assert SECRET not in json.dumps(verifier().to_dict(), default=str)


# ═══ Les pannes, une par une ═════════════════════════════════════════

def test_echec_pendant_le_remplacement_revient(etat, installation, paquet,
                                               monkeypatch):
    def remplacement_qui_casse(*a, **k):
        (installation / "backend" / "app.py").write_text("MOITIÉ",
                                                         encoding="utf-8")
        raise RuntimeError("disque plein en plein remplacement")

    monkeypatch.setattr(_code, "remplacer", remplacement_qui_casse)
    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert issue.revenue is True
    assert (installation / "backend" / "app.py").read_text(
        encoding="utf-8") == "VERSION 1"


def test_echec_de_migration_revient(etat, installation, paquet):
    def migration_ratee():
        raise RuntimeError("schéma incompatible")

    issue = MiseAJour(installation=installation, migrer=migration_ratee,
                      valider=lambda: True).appliquer(paquet)
    assert issue.revenue is True
    assert (installation / "backend" / "app.py").read_text(
        encoding="utf-8") == "VERSION 1"
    assert lire_version_installee(etat) == "1.0.0"


def test_echec_de_self_check_revient(etat, installation, paquet):
    issue = MiseAJour(installation=installation,
                      valider=lambda: False).appliquer(paquet)
    assert issue.revenue is True
    assert (installation / "backend" / "app.py").read_text(
        encoding="utf-8") == "VERSION 1"


def test_le_point_de_reprise_survit_a_un_echec(etat, installation, paquet):
    """**Le test obligatoire** : c'est exactement la régression de J16.

    `preserve_set()` ne couvrait pas `checkpoints` — une mise à jour
    aurait effacé le seul moyen d'annuler ce qu'elle cassait.
    """
    def migration_qui_saccage():
        (etat / "checkpoints" / "cp.json").unlink()
        (etat / "db" / "hermes.db").write_text("SACCAGE", encoding="utf-8")
        raise RuntimeError("puis échoue")

    issue = MiseAJour(installation=installation, migrer=migration_qui_saccage,
                      valider=lambda: True).appliquer(paquet)
    assert issue.revenue is True
    assert (etat / "checkpoints" / "cp.json").read_text(
        encoding="utf-8") == "filet v1"
    assert (etat / "db" / "hermes.db").read_text(
        encoding="utf-8") == "données v1"


def test_un_echec_de_retour_arriere_est_fatal(etat, installation, paquet):
    """Ni installé, ni revenu. Le taire laisserait un état à mi-chemin
    que personne ne sait diagnostiquer."""
    moteur = MiseAJour(installation=installation,
                       migrer=lambda: (_ for _ in ()).throw(RuntimeError("non")),
                       valider=lambda: True)
    vraie = moteur.sauvegarder

    def sauver_puis_disparaitre(version=""):
        import shutil

        sauvegarde = vraie(version)
        shutil.rmtree(sauvegarde.chemin)
        return sauvegarde

    moteur.sauvegarder = sauver_puis_disparaitre
    issue = moteur.appliquer(paquet)
    assert issue.fatal is True
    assert issue.revenue is False
    assert issue.reussie is False
    assert "FATAL" in issue.resume()
    assert Etape.FATAL.value in issue.etapes


def test_un_update_interrompu_ne_marque_jamais_la_nouvelle_version(
        etat, installation, paquet):
    for casseur in (lambda: (_ for _ in ()).throw(RuntimeError("x")),):
        MiseAJour(installation=installation, migrer=casseur,
                  valider=lambda: True).appliquer(paquet)
    assert lire_version_installee(etat) == "1.0.0"


# ═══ Les trois sources du preserve set ═══════════════════════════════

def test_un_dossier_non_declare_est_quand_meme_sauve(etat, installation,
                                                     paquet):
    """Le défaut trouvé sur l'installation **réelle** : `workflows` vit
    sous la racine et n'est pas dans la liste.

    Perdre la donnée serait pire que la sauver sans l'avoir déclarée.
    """
    (etat / "surprise").mkdir()
    (etat / "surprise" / "x.json").write_text("données neuves",
                                              encoding="utf-8")

    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert "surprise" in issue.sauvegarde.dossiers
    assert "surprise" in issue.sauvegarde.non_declares


def test_un_dossier_non_declare_est_dit(etat, installation, paquet, caplog):
    """Mais le silence serait pire encore — c'est ainsi que
    `checkpoints` est passé, puis `workflows`."""
    import logging

    (etat / "surprise").mkdir()
    caplog.set_level(logging.WARNING)
    MiseAJour(installation=installation, valider=lambda: True).appliquer(paquet)
    assert "preserve_set" in caplog.text


def test_un_dossier_non_declare_est_restaure(etat, installation, paquet):
    (etat / "surprise").mkdir()
    (etat / "surprise" / "x.json").write_text("à ne pas perdre",
                                              encoding="utf-8")

    def saccage():
        (etat / "surprise" / "x.json").write_text("perdu", encoding="utf-8")
        raise RuntimeError("puis échoue")

    MiseAJour(installation=installation, migrer=saccage,
              valider=lambda: True).appliquer(paquet)
    assert (etat / "surprise" / "x.json").read_text(
        encoding="utf-8") == "à ne pas perdre"


# ═══ Le dépôt git de l'utilisateur ═══════════════════════════════════

def _git(depot: Path, *args) -> str:
    return subprocess.run(["git", *args], cwd=depot, capture_output=True,
                          text=True).stdout


def test_le_depot_de_l_utilisateur_est_intact(etat, tmp_path, paquet):
    """Agent OS n'a pas ce problème : son dossier d'application n'est pas
    un dépôt. Ici, `.git` porte l'historique, la branche, l'index et le
    travail non commité.
    """
    installation = tmp_path / "depot"
    (installation / "backend").mkdir(parents=True)
    (installation / "backend" / "app.py").write_text("VERSION 1",
                                                     encoding="utf-8")
    for commande in (("init", "-q"), ("config", "user.email", "t@t"),
                     ("config", "user.name", "t"), ("add", "-A"),
                     ("commit", "-qm", "v1")):
        subprocess.run(["git", *commande], cwd=installation,
                       capture_output=True)

    # Du travail en cours, non commité, dans l'index.
    (installation / "en_cours.txt").write_text("mon travail", encoding="utf-8")
    subprocess.run(["git", "add", "en_cours.txt"], cwd=installation,
                   capture_output=True)

    tete = _git(installation, "rev-parse", "HEAD").strip()
    branche = _git(installation, "rev-parse", "--abbrev-ref", "HEAD").strip()
    index = _git(installation, "diff", "--cached", "--name-only")
    assert index.strip() == "en_cours.txt", "le test lui-même serait vide"

    issue = MiseAJour(installation=installation,
                      valider=lambda: True).appliquer(paquet)
    assert issue.reussie is True

    assert _git(installation, "rev-parse", "HEAD").strip() == tete
    assert _git(installation, "rev-parse",
                "--abbrev-ref", "HEAD").strip() == branche
    assert _git(installation, "diff", "--cached", "--name-only") == index
    assert (installation / "en_cours.txt").read_text(
        encoding="utf-8") == "mon travail"


# ═══ L'état opérationnel est recalculé, pas restauré ═════════════════

def test_un_cooldown_n_est_pas_restaure_apres_retour_arriere(etat,
                                                             installation,
                                                             paquet):
    """Un écart de fournisseur décrit **maintenant**, et un retour
    arrière change ce maintenant.

    Le restaurer réappliquerait une décision prise pour un incident qui
    appartenait à l'installation d'avant.
    """
    from backend.ral import courtier as module_courtier
    from backend.ral.courtier import Etat as EtatFournisseur
    from backend.runs.registre import Cause

    module_courtier.reinitialiser()
    module_courtier.courtier().signaler_echec("openrouter", Cause.QUOTA)
    assert module_courtier.courtier().examiner(
        "openrouter").etat is EtatFournisseur.ECARTE

    MiseAJour(installation=installation,
              migrer=lambda: (_ for _ in ()).throw(RuntimeError("non")),
              valider=lambda: True).appliquer(paquet)

    assert module_courtier.courtier().examiner(
        "openrouter").etat is EtatFournisseur.DISPONIBLE
    module_courtier.reinitialiser()


def test_l_etat_operationnel_n_est_pas_persiste():
    """Décidé à partir du code réel, pas d'une règle arbitraire.

    Le courtier ne garde rien sur disque — son propre commentaire le dit
    depuis HOS-228 : « un écart est une réaction à un incident en
    cours ».
    """
    import ast
    import inspect

    from backend.ral import courtier

    arbre = ast.parse(inspect.getsource(courtier))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("sqlite" in m or "storage" in m for m in modules), modules


# ═══ Le self-check réel ══════════════════════════════════════════════

def test_le_self_check_touche_aux_vrais_invariants():
    """Pas un `import hermes` : il ouvre la base, lit les approbations,
    liste les points de reprise, charge la configuration et le RAL."""
    from backend.maj.sante import verifier

    rapport = verifier()
    noms = {c.nom for c in rapport.controles}
    for attendu in ("registre des runs", "base applicative", "approbations",
                    "configuration", "RAL", "points de reprise",
                    "bus d'événements"):
        assert attendu in noms, attendu


def test_un_controle_sans_objet_n_est_pas_un_echec():
    """Une installation neuve n'a pas de points de reprise.

    En exiger un ferait échouer la première mise à jour de tout le monde.
    """
    from backend.maj.sante import Controle, Etat, Rapport

    rapport = Rapport(controles=[
        Controle("points de reprise", Etat.INDISPONIBLE, critique=False)])
    assert rapport.sain is True


def test_un_echec_critique_rend_le_rapport_malsain():
    from backend.maj.sante import Controle, Etat, Rapport

    assert Rapport(controles=[
        Controle("registre des runs", Etat.ECHEC, critique=True)]).sain is False


def test_le_self_check_ne_s_arrete_pas_au_premier_echec():
    """Un rapport partiel dit ce qui a été testé avant que ça casse, pas
    ce qui va mal."""
    from backend.maj.sante import verifier

    assert len(verifier().controles) >= 9


# ═══ Ce qui n'est délibérément pas fait ══════════════════════════════

def test_aucun_telechargement():
    """Le canal de distribution n'existe pas, et l'écrire sans lui
    produirait un mécanisme non éprouvable."""
    import ast
    import inspect

    from backend.maj import code, mise_a_jour, paquet as module_paquet

    for module in (mise_a_jour, code, module_paquet):
        arbre = ast.parse(inspect.getsource(module))
        noms = {n.module for n in ast.walk(arbre)
                if isinstance(n, ast.ImportFrom) and n.module}
        noms |= {a.name for n in ast.walk(arbre)
                 if isinstance(n, ast.Import) for a in n.names}
        interdits = [m for m in noms
                     if any(x in m for x in ("httpx", "requests", "urllib",
                                             "subprocess", "socket"))]
        assert not interdits, (module.__name__, interdits)


def test_aucune_architecture_parallele():
    """Pas de second bus, pas de second registre, pas de second Aegis."""
    import ast
    import inspect

    from backend.maj import mise_a_jour

    source = inspect.getsource(mise_a_jour)
    arbre = ast.parse(source)
    classes = {n.name for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)}
    # Les seules classes du module sont sa séquence et ses données.
    assert classes <= {"MiseAJour", "MiseAJourImpossible", "Etape", "Issue",
                       "Sauvegarde"}


# ═══ Les migrations : le constat, et la garde ════════════════════════

def test_le_mecanisme_de_migration_vivant_est_add_missing_columns():
    """**Cas A**, constaté sur le code réel.

    `memory/db.py::_add_missing_columns` tourne à chaque `init_db()`,
    ajoute les colonnes nullables que les modèles déclarent et que la
    base n'a pas, et **refuse bruyamment** les non-nullables. C'est ce
    mécanisme qui a porté les colonnes de portée d'approbation (HOS-224)
    sur les bases existantes, sans migration écrite.

    Il est donc dans le self-check : `base applicative` appelle
    `init_db`, donc l'exécute.
    """
    import inspect

    from backend.maj import sante
    from backend.memory.db import _add_missing_columns, init_db

    assert "_add_missing_columns" in inspect.getsource(init_db)
    assert "init_db" in inspect.getsource(sante.verifier)
    assert _add_missing_columns is not None


def test_un_changement_non_additif_ne_peut_pas_passer_en_silence():
    """La garde du **cas B**.

    `_add_missing_columns` ne sait faire qu'une chose : ajouter une
    colonne nullable. Un `NOT NULL`, une clé primaire ou une colonne
    retirée demandent une vraie migration — et son propre code le dit
    déjà, en journalisant « Schema drift needs a real migration ».

    Ce test tient l'invariant : tant que ce refus existe, aucun schéma ne
    peut évoluer de façon destructive sans que quelqu'un l'ait décidé. Il
    tombe le jour où on retire ce garde-fou, et c'est alors le moment
    d'écrire le moteur de migration plutôt que de le contourner.
    """
    import inspect

    from backend.memory.db import _add_missing_columns

    source = inspect.getsource(_add_missing_columns)
    assert "not column.nullable or column.primary_key" in source
    assert "needs a real migration" in source


def test_le_second_moteur_de_migration_reste_dormant():
    """`MigrationManager` a un vrai `migrate()` et des migrations codées
    en dur à la version 1. Il est orphelin depuis HOS-221.

    Ne pas l'exhumer ici : deux moteurs de schéma sur la même base,
    c'est la question « lequel fait foi ? » à chaque incident. Ce test
    tombe si quelqu'un le rebranche — et c'est le moment de relire ce
    raisonnement plutôt que de le contourner.
    """
    import ast as _ast
    import io as _io
    from pathlib import Path as _P

    # Sur l'**arbre syntaxique**, pas sur le texte : `courtier.py` et
    # `registre.py` nomment `MigrationManager` dans un commentaire pour
    # expliquer pourquoi ils ne s'en servent pas, et une recherche de
    # sous-chaîne les accusait. Quatrième faux positif de ce genre sur
    # ce chantier — c'est un motif, pas un accident.
    racine = _P(__file__).resolve().parents[2]
    appelants = []
    for fichier in (racine / "backend").rglob("*.py"):
        if "tests" in fichier.parts or "storage" in fichier.parts:
            continue
        try:
            arbre = _ast.parse(_io.open(fichier, encoding="utf-8",
                                        errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        noms = {n.id for n in _ast.walk(arbre) if isinstance(n, _ast.Name)}
        noms |= {a.name for n in _ast.walk(arbre)
                 if isinstance(n, (_ast.Import, _ast.ImportFrom))
                 for a in n.names}
        if "MigrationManager" in noms:
            appelants.append(str(fichier.relative_to(racine)))
    assert not appelants, appelants
