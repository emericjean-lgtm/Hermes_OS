"""Hermes sait annuler une modification (HOS-223).

## Ce qu'il ne savait pas faire

Trois constats, mesurés dans le code avant d'écrire une ligne :

- `propose_write` déposait une sauvegarde horodatée à chaque écrasement,
  la rendait à l'appelant et la publiait dans un événement — et **rien,
  nulle part, ne la relisait**. Aucune fonction du dépôt ne restaurait
  depuis un `backup_path`.
- `delete()` faisait `shutil.rmtree()` sur un répertoire sans rien
  garder. `move()` non plus.
- `snapshot_manager` sauve l'état de mission et dit explicitement qu'il
  ne copie pas les fichiers, en déléguant à ces sauvegardes. La
  délégation pointait vers un mécanisme sans retour.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.checkpoints import checkpoint as cp
from backend.checkpoints import git_ref, repli_fichiers
from backend.security.aegis_engine import Verdict


@dataclass
class _Decision:
    verdict: Verdict
    reason: str


class _Aegis:
    """Le même patron que `test_snapshot_manager` : une décision, pas un moteur.

    La décision est une dataclasse à part et non une classe imbriquée
    lisant `self` : ça marche — un corps de classe s'exécute dans la
    portée de la méthode — mais c'est un tour de passe-passe, et le
    détecteur de symboles du dépôt le signalait à juste titre.
    """

    def __init__(self, verdict=Verdict.ALLOW, reason: str = "ok") -> None:
        self._decision = _Decision(verdict, reason)
        self.derniere = None

    def evaluate(self, requete):
        self.derniere = requete
        return self._decision


# Chacune sa racine : les deux fixtures sont demandées ensemble par
# plusieurs tests, et partager `tmp_path` faisait initialiser un dépôt
# git dans le dossier censé ne pas en avoir. Le test disait « ce n'est
# pas un dépôt » sur un dossier que la fixture voisine venait de
# versionner.
@pytest.fixture
def dossier(tmp_path: Path) -> Path:
    """Un workspace ordinaire, sans dépôt git."""
    racine = tmp_path / "ws"
    (racine / "sous").mkdir(parents=True)
    (racine / "a.txt").write_text("version 1", encoding="utf-8")
    (racine / "sous" / "b.txt").write_text("profond", encoding="utf-8")
    return racine


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Une base jetable, pour les tests qui capturent l'état de mission.

    Même montage que `test_snapshot_manager` : sans les tables,
    `create_snapshot` échoue et `_prendre_l_etat` rend une chaîne vide —
    ce qui est le bon comportement mais ne mesure pas le couple.
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "snap.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))

    from backend.core.config import get_settings

    get_settings.cache_clear()
    from backend.memory.db import init_db, make_engine

    init_db(make_engine(str(tmp_path / "snap.db")))
    yield
    get_settings.cache_clear()


@pytest.fixture
def ailleurs(tmp_path: Path) -> Path:
    """Une destination de copie, hors du workspace copié."""
    chemin = tmp_path / "destination"
    chemin.mkdir()
    return chemin


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    """Un vrai dépôt git, avec un commit et un `.gitignore`."""
    racine = tmp_path / "depot"
    racine.mkdir()

    def git(*args):
        return subprocess.run(["git", *args], cwd=racine,
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (racine / "a.txt").write_text("version 1", encoding="utf-8")
    (racine / ".gitignore").write_text("ignore/\n", encoding="utf-8")
    (racine / "ignore").mkdir()
    (racine / "ignore" / "gros.bin").write_text("x" * 1000, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "initial")
    return racine


def _git(depot: Path, *args) -> str:
    return subprocess.run(["git", *args], cwd=depot, capture_output=True,
                          text=True).stdout


# ═══ Le chemin git ═══════════════════════════════════════════════════

def test_le_depot_est_reconnu(depot, dossier):
    """Demandé à git, pas testé sur `.git`.

    Un worktree lié porte un **fichier** `.git`, et un sous-dossier de
    dépôt n'en porte aucun tout en étant parfaitement versionné.
    """
    assert git_ref.est_un_depot(str(depot)) is True
    assert git_ref.est_un_depot(str(dossier)) is False


def test_l_index_de_l_utilisateur_n_est_jamais_touche(depot):
    """La pièce centrale, et celle qui détruirait du travail si elle cédait.

    Un `git add -A` sur l'index réel écraserait le travail en cours de
    quelqu'un — au moment précis où il lance une mission risquée. D'où
    `GIT_INDEX_FILE` sur un fichier temporaire.
    """
    (depot / "b.txt").write_text("mon travail", encoding="utf-8")
    subprocess.run(["git", "add", "b.txt"], cwd=depot, capture_output=True)
    avant = _git(depot, "diff", "--cached", "--name-only")
    assert avant.strip() == "b.txt", "le test lui-même serait vide"

    git_ref.prendre(str(depot), "essai")
    assert _git(depot, "diff", "--cached", "--name-only") == avant


def test_ni_head_ni_la_branche_ne_bougent(depot):
    """Une restauration arrive après un incident.

    Un incident n'est pas le moment de découvrir que sa branche a changé.
    """
    tete = _git(depot, "rev-parse", "HEAD").strip()
    branche = _git(depot, "rev-parse", "--abbrev-ref", "HEAD").strip()

    commit = git_ref.prendre(str(depot), "essai")
    (depot / "a.txt").write_text("saccage", encoding="utf-8")
    git_ref.restaurer(str(depot), commit)

    assert _git(depot, "rev-parse", "HEAD").strip() == tete
    assert _git(depot, "rev-parse", "--abbrev-ref", "HEAD").strip() == branche


def test_la_reference_est_hors_des_branches_et_des_tags(depot):
    """`refs/hermes/checkpoints/` : ni `git branch`, ni `git tag`, ni push.

    Le dépôt de l'utilisateur reste tel qu'il le connaît.
    """
    git_ref.prendre(str(depot), "essai")
    refs = _git(depot, "show-ref")
    assert "refs/hermes/checkpoints/" in refs
    assert "refs/heads/hermes" not in refs
    assert _git(depot, "tag").strip() == ""


def test_le_gitignore_est_honore(depot):
    """Gratuit, et décisif : un `node_modules/` de 400 Mio n'entre pas.

    L'assertion porte sur le **chemin ignoré**, pas sur la sous-chaîne
    « ignore » : la première version de ce test échouait sur
    `.gitignore` lui-même, qui la contient. Un test faux dans ce sens
    aurait été moins grave, mais l'inverse aurait passé sur rien.
    """
    commit = git_ref.prendre(str(depot), "essai")
    contenu = _git(depot, "ls-tree", "-r", "--name-only", commit).split()
    assert "a.txt" in contenu
    assert ".gitignore" in contenu
    assert "ignore/gros.bin" not in contenu


def test_un_fichier_ignore_survit_a_la_restauration(depot):
    """Il n'était pas dans le point de reprise ; le supprimer serait un dégât.

    Restaurer ne doit effacer que ce que la mission a produit, pas ce
    que git a délibérément laissé dehors.
    """
    commit = git_ref.prendre(str(depot), "essai")
    git_ref.restaurer(str(depot), commit)
    assert (depot / "ignore" / "gros.bin").exists()


def test_les_trois_cas_de_la_restauration(depot):
    """Modifié, supprimé, apparu depuis. Chacun son geste.

    Une restauration qui ne ferait que réécrire laisserait les fichiers
    créés depuis : elle ne restaurerait rien, elle mélangerait deux états.
    """
    (depot / "b.txt").write_text("existait", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=depot, capture_output=True)
    commit = git_ref.prendre(str(depot), "essai")

    (depot / "a.txt").write_text("SACCAGE", encoding="utf-8")
    (depot / "b.txt").unlink()
    (depot / "nouveau.txt").write_text("apparu depuis", encoding="utf-8")

    ecart = git_ref.ecart(str(depot), commit)
    assert ecart.a_restaurer == ("a.txt",)
    assert ecart.a_recreer == ("b.txt",)
    assert ecart.a_supprimer == ("nouveau.txt",)

    git_ref.restaurer(str(depot), commit)
    assert (depot / "a.txt").read_text(encoding="utf-8") == "version 1"
    assert (depot / "b.txt").read_text(encoding="utf-8") == "existait"
    assert not (depot / "nouveau.txt").exists()
    assert git_ref.ecart(str(depot), commit).vide


def test_le_commit_a_head_pour_parent(depot):
    """Détaché sans parent, un point de reprise n'est diffable contre rien.

    C'est l'écart avec Agent OS : avec un parent, on lit d'où il vient.
    """
    tete = _git(depot, "rev-parse", "HEAD").strip()
    commit = git_ref.prendre(str(depot), "essai")
    assert _git(depot, "rev-parse", commit + "^").strip() == tete


def test_supprimer_retire_la_reference(depot):
    """Sans quoi les objets restent protégés du ramasse-miettes.

    Le dépôt grossirait d'un point de reprise que plus personne ne peut
    lire.
    """
    commit = git_ref.prendre(str(depot), "essai")
    git_ref.supprimer(str(depot), commit)
    assert "refs/hermes/checkpoints/" not in _git(depot, "show-ref")


# ═══ Le repli fichiers ═══════════════════════════════════════════════

def test_le_repli_copie_et_hache(dossier, ailleurs):
    destination = ailleurs
    manifeste = repli_fichiers.prendre(str(dossier), destination)
    assert set(manifeste) == {"a.txt", "sous/b.txt"}
    assert repli_fichiers.verifier(destination) == []


def test_les_repertoires_de_bruit_sont_exclus(dossier, ailleurs):
    """La liste vient de `verification.py`, pas d'une seconde copie.

    Deux listes divergent ; celle-ci décide de ce qu'un point de reprise
    coûte.
    """
    (dossier / "node_modules").mkdir()
    (dossier / "node_modules" / "gros.js").write_text("y" * 5000,
                                                      encoding="utf-8")
    manifeste = repli_fichiers.prendre(str(dossier), ailleurs)
    assert not any("node_modules" in c for c in manifeste)


def test_une_copie_abimee_refuse_de_restaurer(dossier, ailleurs):
    """Le manifeste n'est pas une déclaration : il est revérifié.

    Restaurer à moitié depuis une copie abîmée laisserait un troisième
    état, ni l'ancien ni le nouveau, sans que rien le dise.
    """
    destination = ailleurs
    repli_fichiers.prendre(str(dossier), destination)
    (destination / repli_fichiers.NOM_CONTENU / "a.txt").write_text(
        "corrompu", encoding="utf-8")

    (dossier / "a.txt").write_text("saccage", encoding="utf-8")
    with pytest.raises(repli_fichiers.RepliCorrompu):
        repli_fichiers.restaurer(str(dossier), destination)
    # Rien n'a été écrit : le refus vient **avant** la première copie.
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "saccage"


def test_le_plafond_leve_plutot_que_tronquer(dossier, ailleurs):
    """Un point de reprise partiel est pire qu'absent.

    On croit avoir un filet, il ne retient qu'une partie du workspace, et
    on ne s'en aperçoit qu'en tombant.
    """
    with pytest.raises(repli_fichiers.TropGros):
        repli_fichiers.prendre(str(dossier), ailleurs, plafond=5)


# ═══ La façade : le couple fichiers + état ═══════════════════════════

def test_le_mecanisme_est_choisi_une_fois_et_range(depot, dossier):
    """Redemander « est-ce un dépôt ? » à la restauration choisirait mal.

    Un workspace peut être passé sous git *après* la prise ; le point de
    reprise, lui, n'a pas de commit.
    """
    assert cp.prendre(str(depot), avec_etat=False).mecanisme == "git"
    assert cp.prendre(str(dossier), avec_etat=False).mecanisme == "fichiers"


def test_l_apercu_ne_touche_a_rien(dossier):
    """Le même contrat que `preview_restore` et `propose_write`.

    Montrer la différence avant de l'appliquer.
    """
    point = cp.prendre(str(dossier), avec_etat=False)
    (dossier / "a.txt").write_text("saccage", encoding="utf-8")

    vue = cp.apercu(point.identifiant)
    assert vue.applique is False
    assert vue.a_restaurer == ("a.txt",)
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "saccage"


def test_ce_qui_sera_efface_est_une_liste_a_part(dossier):
    """Fondu dans « 12 fichiers touchés », le destructif disparaîtrait.

    C'est la seule des trois listes qui détruise du travail.
    """
    point = cp.prendre(str(dossier), avec_etat=False)
    (dossier / "nouveau.txt").write_text("apparu", encoding="utf-8")
    vue = cp.apercu(point.identifiant)
    assert vue.a_supprimer == ("nouveau.txt",)
    assert "à supprimer" in vue.resume()


def test_restaurer_passe_par_aegis_en_migration_de_donnees(dossier):
    """La même catégorie que `restore_snapshot`, et pour la même raison.

    Le §17.3 du cahier la classe en validation obligatoire à tous les
    niveaux d'autonomie : ce geste détruit tout ce qui a été fait depuis.
    """
    point = cp.prendre(str(dossier), avec_etat=False)
    aegis = _Aegis()
    cp.restaurer(aegis, point.identifiant)
    assert aegis.derniere.action_type == "data_migration"


def test_un_refus_d_aegis_ne_restaure_rien(dossier):
    point = cp.prendre(str(dossier), avec_etat=False)
    (dossier / "a.txt").write_text("saccage", encoding="utf-8")
    with pytest.raises(cp.CheckpointImpossible, match="refusée"):
        cp.restaurer(_Aegis(verdict=Verdict.DENY, reason="non"),
                     point.identifiant)
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "saccage"


def test_le_couple_fichiers_et_etat_est_repris_ensemble(dossier, base):
    """L'amélioration que le cahier demande sur Agent OS.

    Restaurer les fichiers sans l'état laisse une mission qui croit avoir
    fini un travail que le disque ne porte plus — et qui repartira de là.
    """
    point = cp.prendre(str(dossier), motif="essai", avec_etat=True)
    assert point.instantane, "aucun état capturé : le couple serait à moitié"

    (dossier / "a.txt").write_text("saccage", encoding="utf-8")
    reprise = cp.restaurer(_Aegis(), point.identifiant)
    assert reprise.etat_repris is True
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "version 1"


def test_un_etat_non_repris_est_dit_et_non_tu(dossier, base, monkeypatch):
    """Les fichiers sont déjà revenus quand on arrive là.

    Lever à ce moment laisserait le workspace restauré et l'appelant
    persuadé que rien n'a eu lieu — le pire des trois états.
    """
    point = cp.prendre(str(dossier), avec_etat=True)
    from backend.core import snapshot_manager

    def refuse(*a, **k):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(snapshot_manager, "restore_snapshot", refuse)
    (dossier / "a.txt").write_text("saccage", encoding="utf-8")

    reprise = cp.restaurer(_Aegis(), point.identifiant)
    assert reprise.applique is True
    assert reprise.etat_repris is False
    assert "base indisponible" in reprise.etat_non_repris
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "version 1"


def test_une_prise_ratee_ne_laisse_pas_de_fiche(dossier):
    """Un point de reprise qu'on croit avoir autorise le geste risqué."""
    avant = len(cp.lister())
    with pytest.raises(cp.CheckpointImpossible):
        cp.prendre(str(dossier), avec_etat=False, plafond=1)
    assert len(cp.lister()) == avant


def test_un_workspace_absent_est_refuse(tmp_path):
    with pytest.raises(cp.CheckpointImpossible, match="répertoire"):
        cp.prendre(str(tmp_path / "nexiste_pas"), avec_etat=False)


def test_lister_filtre_par_workspace(dossier, depot):
    cp.prendre(str(dossier), motif="un", avec_etat=False)
    cp.prendre(str(depot), motif="deux", avec_etat=False)
    assert [c.motif for c in cp.lister(str(dossier))] == ["un"]


def test_supprimer_retire_la_fiche_et_la_reference(depot):
    point = cp.prendre(str(depot), avec_etat=False)
    assert cp.supprimer(point.identifiant) is True
    assert "refs/hermes/checkpoints/" not in _git(depot, "show-ref")
    with pytest.raises(cp.CheckpointIntrouvable):
        cp.lire(point.identifiant)


def test_supprimer_un_inconnu_rend_faux():
    assert cp.supprimer("jamais_vu") is False


def test_le_point_de_reprise_vit_hors_du_workspace(dossier):
    """Rangé dans le dossier qu'il protège, il disparaîtrait avec lui.

    Et hors du dépôt : c'est la règle de HOS-215.
    """
    from backend.core.etat import racine

    point = cp.prendre(str(dossier), avec_etat=False)
    emplacement = cp._dossier(point.identifiant)
    assert racine() in emplacement.parents
    assert dossier not in emplacement.parents


# ═══ Le branchement ══════════════════════════════════════════════════

def test_le_checkpoint_est_pose_sur_le_chemin_des_missions():
    """Sinon c'est un cinquième orphelin.

    `approvals.py`, `DatabaseManager`, `MigrationManager` et le
    `backup_path` de `propose_write` sont déjà du code réel que personne
    n'appelle.
    """
    import inspect
    from backend.mission import graph_executor

    source = inspect.getsource(graph_executor.GraphExecutor._snapshot_workspace)
    assert "_prendre_le_filet" in source


def test_l_absence_de_filet_est_dite(dossier):
    """Un point de reprise absent en silence laisse partir avec le même aplomb.

    C'est la règle du tri-état (HOS-222), appliquée à la protection
    plutôt qu'à la mesure.
    """
    from backend.core.event_topics import BASELINE_TOPICS

    assert "mission.sans_filet" in BASELINE_TOPICS
    assert "mission.checkpoint" in BASELINE_TOPICS
