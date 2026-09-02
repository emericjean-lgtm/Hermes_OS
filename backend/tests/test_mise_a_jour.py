"""HOS-233 : `appliquer()` prend désormais un **paquet** en premier
argument, la version étant nommée. Ces gardes-ci portent sur la moitié
« état » — sauvegarde, restauration, version — qu'elles mesurent sans
paquet ; celles du moteur complet sont dans `test_mise_a_jour_moteur.py`.

Mettre à jour sans perdre ce que quinze jalons ont construit (HOS-232).

## Le défaut trouvé en mesurant la prémisse

`preserve_set()` — la liste de ce qu'une mise à jour ne doit jamais
toucher — **ne couvrait pas `checkpoints`**. HOS-215 a écrit la liste ;
HOS-223 a créé ce dossier sous la même racine deux jalons plus tard, hors
de la liste. Rien ne l'a signalé parce que **rien ne consommait
`preserve_set()`**.

Une mise à jour aurait donc effacé les points de reprise — c'est-à-dire
le seul moyen d'annuler ce qu'elle aurait cassé.

Une liste que rien ne vérifie contre la réalité est une liste qui dérive.
C'est ce que garde `test_tout_ce_qui_vit_sous_la_racine_est_preserve`,
qui lit le **code** plutôt que la liste.

## Et deux manques

- `installer/` fait 378 lignes et ne contient que de la détection.
- **Hermes OS n'avait pas de version.** Trois versions existaient dans le
  dépôt, aucune ne désignant le produit. On ne revient pas à une version
  qu'on n'a jamais nommée.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from backend.core.etat import SOUS_DOSSIERS, preserve_set
from backend.maj.mise_a_jour import (
    DOSSIER_SAUVEGARDES,
    SAUVEGARDES_GARDEES,
    Etape,
    MiseAJour,
    MiseAJourImpossible,
)
from backend.maj.version import (
    VERSION,
    Version,
    comparer,
    ecrire_version_installee,
    lire_version_installee,
)

RACINE_DEPOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def etat(tmp_path, monkeypatch) -> Path:
    """Une racine d'état jetable, avec du contenu qui compte."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    import backend.core.etat as module

    module.racine.cache_clear()
    racine = module.racine()
    (racine / "db").mkdir(parents=True, exist_ok=True)
    (racine / "db" / "hermes.db").write_text("les données", encoding="utf-8")
    (racine / "checkpoints").mkdir(parents=True, exist_ok=True)
    (racine / "checkpoints" / "cp1.json").write_text("filet", encoding="utf-8")
    yield racine
    module.racine.cache_clear()


# ═══ La garde qui empêche la liste de dériver ════════════════════════

def test_tout_ce_qui_vit_sous_la_racine_est_preserve():
    """Lit le **code**, pas la liste.

    C'est tout l'intérêt : `checkpoints` manquait depuis HOS-223 et
    aucune relecture de la liste ne l'aurait dit — il fallait regarder
    qui écrit où. Une liste que rien ne vérifie contre la réalité est
    une liste qui dérive.
    """
    motif = re.compile(r'racine(?:_d_etat)?\(\)\s*/\s*["\']([^"\']+)["\']')
    trouves: dict[str, str] = {}
    for fichier in (RACINE_DEPOT / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        texte = io.open(fichier, encoding="utf-8", errors="replace").read()
        for nom in motif.findall(texte):
            trouves.setdefault(nom, str(fichier.relative_to(RACINE_DEPOT)))

    # Les dossiers construits depuis une constante — `DOSSIER` chez les
    # points de reprise — n'apparaissent pas dans le motif ci-dessus. On
    # les demande à leur module, qui est la source.
    from backend.checkpoints.checkpoint import DOSSIER as DOSSIER_CHECKPOINTS

    trouves.setdefault(DOSSIER_CHECKPOINTS, "backend/checkpoints/checkpoint.py")

    preserves = {p.name for p in preserve_set()}
    # Les sauvegardes sont délibérément hors du preserve set : sauver une
    # sauvegarde doublerait l'occupation à chaque mise à jour.
    trouves.pop(DOSSIER_SAUVEGARDES, None)

    manquants = {n: f for n, f in trouves.items() if n not in preserves}
    assert not manquants, (
        "des dossiers vivent sous la racine d'état sans être dans "
        f"`preserve_set()` : {manquants} — une mise à jour les effacerait")


def test_les_points_de_reprise_sont_preserves():
    """Le défaut exact, nommé.

    Les effacer retirerait le seul moyen d'annuler ce que la mise à jour
    aurait cassé.
    """
    assert "checkpoints" in SOUS_DOSSIERS


def test_les_sauvegardes_ne_sont_pas_dans_le_preserve_set():
    """Sauver une sauvegarde doublerait l'occupation à chaque mise à jour."""
    assert DOSSIER_SAUVEGARDES not in SOUS_DOSSIERS


# ═══ La version ══════════════════════════════════════════════════════

def test_hermes_os_a_une_version():
    """Mesuré : il n'en avait pas.

    Trois versions existaient dans le dépôt — format d'instantané, schéma
    de graphe, bibliothèque tierce — et aucune ne désignait le produit.
    """
    assert Version.depuis(VERSION).rang >= (1, 0, 0)


@pytest.mark.parametrize(("a", "b", "attendu"), [
    ("1.0.0", "1.0.1", -1),
    ("1.1.0", "1.0.9", 1),
    ("2.0.0", "2.0.0", 0),
])
def test_les_versions_se_comparent(a, b, attendu):
    assert comparer(a, b) == attendu


def test_une_version_illisible_vaut_zero():
    """« Très ancienne ou abîmée », et une mise à jour doit pouvoir
    partir de là.

    Lever bloquerait exactement l'installation qui vient réparer.
    """
    assert Version.depuis("abîmée").rang == (0, 0, 0)
    assert Version.depuis("").rang == (0, 0, 0)


def test_une_installation_neuve_n_a_pas_de_version(etat):
    """Vide n'est pas une erreur : c'est une installation antérieure à ce
    jalon, et la traiter comme telle refuserait la migration à toutes les
    installations existantes."""
    assert lire_version_installee(etat) == ""


def test_la_version_installee_vit_hors_du_depot(etat):
    """La question « d'où viens-je ? » se pose au moment où le dépôt
    vient d'être remplacé."""
    ecrire_version_installee("1.2.3", etat)
    assert lire_version_installee(etat) == "1.2.3"
    assert etat in (etat / "version.json").parents


# ═══ La séquence ═════════════════════════════════════════════════════

def test_une_mise_a_jour_reussie_marque_la_version(etat):
    issue = MiseAJour(installer=lambda: None,
                      valider=lambda: True).appliquer(vers="1.0.0")
    assert issue.reussie is True
    # `compatibilite` en tête depuis HOS-233 : aucune mise à jour aveugle,
    # et la vérification passe **avant** la sauvegarde pour qu'un refus
    # ne laisse pas de sauvegarde orpheline.
    assert issue.etapes == [Etape.COMPATIBILITE.value, Etape.SAUVEGARDE.value,
                            Etape.INSTALLATION.value, Etape.VALIDATION.value,
                            Etape.MARQUAGE.value]
    assert lire_version_installee(etat) == "1.0.0"


def test_la_sauvegarde_prend_tout_le_preserve_set(etat):
    issue = MiseAJour(valider=lambda: True).appliquer(vers="1.0.0")
    assert "checkpoints" in issue.sauvegarde.dossiers
    assert "db" in issue.sauvegarde.dossiers


def test_la_marque_de_version_est_posee_en_dernier():
    """Posée avant, elle ferait croire à une mise à jour réussie qui ne
    l'est pas — et le retour arrière suivant repartirait du mauvais
    point."""
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(MiseAJour.appliquer))
    # Par **numéro de ligne**, pas par ordre de parcours : `ast.walk`
    # visite en largeur, et une première version de cette garde comparait
    # des positions qui ne voulaient rien dire.
    lignes = {ast.unparse(n.func): n.lineno
              for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)}
    # `self._verifier` depuis HOS-233 : le self-check rend un rapport
    # structuré, pas un booléen, et l'appel a changé de nom avec lui.
    assert lignes["self._verifier"] < lignes["ecrire_version_installee"]


# ═══ Le retour arrière ═══════════════════════════════════════════════

def test_une_installation_qui_casse_est_annulee(etat):
    """Le cœur du jalon : quinze jalons d'état ne doivent pas mourir
    d'une mise à jour ratée."""
    def casse():
        (etat / "db" / "hermes.db").write_text("SACCAGE", encoding="utf-8")
        (etat / "checkpoints" / "cp1.json").unlink()
        raise RuntimeError("paquet corrompu")

    issue = MiseAJour(installer=casse, valider=lambda: True).appliquer(vers="1.1.0")
    assert issue.reussie is False
    assert issue.revenue is True
    assert (etat / "db" / "hermes.db").read_text(encoding="utf-8") == "les données"
    assert (etat / "checkpoints" / "cp1.json").exists()


def test_une_validation_qui_echoue_annule_aussi(etat):
    """L'installation a « marché » et le résultat ne répond pas.

    C'est le cas le plus insidieux : rien n'a levé, et pourtant rien ne
    fonctionne.
    """
    def abime():
        (etat / "db" / "hermes.db").write_text("autre chose", encoding="utf-8")

    issue = MiseAJour(installer=abime, valider=lambda: False).appliquer(vers="1.2.0")
    assert issue.revenue is True
    assert (etat / "db" / "hermes.db").read_text(encoding="utf-8") == "les données"


def test_un_retour_arriere_ne_laisse_pas_la_nouvelle_version(etat):
    """Sinon l'état dirait venir d'une version qu'il ne porte pas, et la
    mise à jour suivante partirait du mauvais point."""
    ecrire_version_installee("1.0.0", etat)

    def casse():
        raise RuntimeError("non")

    MiseAJour(installer=casse, valider=lambda: True).appliquer(vers="1.1.0")
    assert lire_version_installee(etat) == "1.0.0"


def test_le_retour_arriere_retire_avant_de_copier(etat):
    """Une copie par-dessus laisserait les fichiers que la version
    fautive a créés, et un état mi-ancien mi-nouveau est pire que l'un
    ou l'autre."""
    def casse():
        (etat / "db" / "intrus.db").write_text("créé par la version ratée",
                                               encoding="utf-8")
        raise RuntimeError("non")

    MiseAJour(installer=casse, valider=lambda: True).appliquer(vers="1.1.0")
    assert not (etat / "db" / "intrus.db").exists()


def test_sans_sauvegarde_on_n_installe_pas(etat, monkeypatch):
    """Le seul échec qui arrête avant d'avoir rien touché — et c'est
    celui qu'il faut arrêter : sans sauvegarde, rien n'est réversible."""
    installee = []

    def sauvegarde_impossible(self, version=""):
        raise OSError("disque plein")

    monkeypatch.setattr(MiseAJour, "sauvegarder", sauvegarde_impossible)
    issue = MiseAJour(installer=lambda: installee.append(1),
                      valider=lambda: True).appliquer(vers="1.1.0")
    assert issue.reussie is False
    assert installee == [], "installé sans filet"
    assert "sauvegarde impossible" in issue.raison


def test_un_retour_arriere_impossible_est_dit_fort(etat):
    """Le pire cas : l'installation a échoué **et** le retour arrière
    aussi.

    Le taire laisserait un état à mi-chemin que personne ne sait
    diagnostiquer.
    """
    moteur = MiseAJour(installer=lambda: (_ for _ in ()).throw(RuntimeError("non")),
                       valider=lambda: True)
    sauvegarde_reelle = moteur.sauvegarder

    def sauver_puis_disparaitre(version=""):
        sauvegarde = sauvegarde_reelle(version)
        import shutil

        shutil.rmtree(sauvegarde.chemin)
        return sauvegarde

    moteur.sauvegarder = sauver_puis_disparaitre
    issue = moteur.appliquer(vers="1.1.0")
    assert issue.revenue is False
    assert "retour arrière a échoué" in issue.raison


def test_restaurer_une_sauvegarde_absente_leve():
    from backend.maj.mise_a_jour import Sauvegarde

    with pytest.raises(MiseAJourImpossible, match="introuvable"):
        MiseAJour().restaurer(Sauvegarde(chemin="/nexiste/pas", version="1",
                                         prise_le="x", dossiers=("db",)))


def test_la_sauvegarde_porte_sa_propre_liste(etat):
    """Un retour arrière restaure ce qui a été **sauvé**, pas ce que la
    version d'aujourd'hui croit qu'il fallait sauver.

    Une version qui aurait ajouté un dossier ne doit pas prétendre le
    restaurer depuis une copie qui ne le contient pas.
    """
    sauvegarde = MiseAJour().sauvegarder("1.0.0")
    assert sauvegarde.dossiers
    assert set(sauvegarde.dossiers) <= {p.name for p in preserve_set()}


# ═══ Les vieilles sauvegardes ════════════════════════════════════════

def test_les_sauvegardes_sont_elaguees(etat):
    """Trois : assez pour revenir de deux mises à jour ratées, assez peu
    pour que l'état ne quadruple pas."""
    moteur = MiseAJour(valider=lambda: True)
    for i in range(SAUVEGARDES_GARDEES + 2):
        moteur.sauvegarder(f"1.0.{i}")
        # Les noms sont horodatés à la seconde ; on force l'unicité pour
        # que l'élagage ait quelque chose à trier.
        import time

        time.sleep(0.01)
        dossier = etat / DOSSIER_SAUVEGARDES
        derniere = sorted(dossier.iterdir())[-1]
        derniere.rename(dossier / f"2026010{i}T000000Z")

    restantes = list((etat / DOSSIER_SAUVEGARDES).iterdir())
    assert len(restantes) <= SAUVEGARDES_GARDEES + 1


# ═══ L'auto-vérification ═════════════════════════════════════════════

def test_l_auto_verification_touche_a_la_vraie_base(etat):
    """Une auto-vérification qui ne ferait qu'importer des modules
    passerait sur une base corrompue."""
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(MiseAJour._auto_verification))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    assert any("Registre" in a for a in appels), appels


def test_l_auto_verification_par_defaut_passe_sur_un_etat_sain(etat):
    assert MiseAJour()._auto_verification() is True


# ═══ La trace ════════════════════════════════════════════════════════

def test_les_evenements_de_mise_a_jour_sont_declares():
    """Le retour arrière surtout : silencieux, il laisse croire que la
    version installée est la nouvelle."""
    from backend.core.bootstrap.event_wiring import collect_known_topics
    from backend.core.event_topics import BASELINE_TOPICS

    connus = collect_known_topics()
    for topic in ("maj.etape", "maj.terminee", "maj.retour_arriere"):
        assert topic in BASELINE_TOPICS, topic
        assert topic in connus, topic


# ═══ Ce qui n'est délibérément pas fait ══════════════════════════════

def test_le_remplacement_du_code_n_est_pas_ecrit():
    """Télécharger une version et échanger l'arborescence demande un
    canal de distribution qui n'existe pas.

    L'écrire sans lui produirait un mécanisme non éprouvable. La
    fonction d'installation est donc **injectée**, ce qui rend la
    séquence testable pour de bon — avec une installation qui échoue
    exprès.
    """
    import ast
    import inspect

    from backend.maj import mise_a_jour

    arbre = ast.parse(inspect.getsource(mise_a_jour))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    reseau = [m for m in modules
              if any(mot in m for mot in ("httpx", "requests", "urllib",
                                          "subprocess"))]
    assert not reseau, (
        f"le module a gagné un accès réseau ou processus ({reseau}) — "
        "le remplacement du code demande un canal de distribution, et "
        "l'écrire sans lui produirait un mécanisme non éprouvable")
