"""Huit applications dans un projet qui n'en demandait qu'une (HOS-169).

Le projet livre par la campagne Skill360 — 20 sections abouties, 124
fichiers, 74 tests verts — contient huit points d'entree distincts et aucun
assemblage. Deux d'entre eux vont jusqu'a instancier une application en
l'appelant `router` :

    backend/api/kpi.py:12    router = FastAPI(tags=["kpi"])
    backend/api/risk.py:19   router = FastAPI(tags=["risk"])

Le projet ne demarre pas comme un service ; il demarre comme huit services
qui s'ignorent.

C'est le troisieme maillon d'une chaine : `pile` transmet la decision de
langage, `arborescence` celle d'emplacement, celui-ci celle d'assemblage.
Chaque fois pour la meme raison — la liste des fichiers produits ne porte
pas la decision qu'ils incarnent.
"""
from __future__ import annotations

from backend.mission import assemblage


def _pose(base, chemin, contenu) -> None:
    f = base / chemin
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(contenu, encoding="utf-8")


def test_une_application_unique_est_designee_comme_racine(tmp_path) -> None:
    _pose(tmp_path, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")

    texte = assemblage.contrainte(str(tmp_path))

    assert "main.py" in texte
    assert "N'en cree pas une seconde" in texte.replace("é", "e")


def test_plusieurs_applications_sont_signalees_comme_un_defaut(tmp_path) -> None:
    """L'incident lui-meme."""
    _pose(tmp_path, "a.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    _pose(tmp_path, "b.py", "from fastapi import FastAPI\napp = FastAPI()\n")

    texte = assemblage.contrainte(str(tmp_path))

    assert "2 APPLICATIONS" in texte
    # Il doit interdire la suivante, pas seulement constater.
    assert "3" in texte


def test_une_application_deguisee_en_routeur_compte_quand_meme(tmp_path) -> None:
    """`router = FastAPI(...)` est une application, quel que soit son nom."""
    _pose(tmp_path, "kpi.py", 'from fastapi import FastAPI\nrouter = FastAPI(tags=["kpi"])\n')

    assert assemblage.points_d_entree(str(tmp_path))


def test_un_projet_vide_n_impose_rien(tmp_path) -> None:
    """Imposer une architecture que personne n'a choisie serait la
    supposition que le §5 d'un cahier interdit."""
    assert assemblage.contrainte(str(tmp_path)) == ""


def test_un_import_seul_ne_fait_pas_un_point_d_entree(tmp_path) -> None:
    _pose(tmp_path, "outils.py", "from fastapi import FastAPI\n\ndef f(): ...\n")

    assert assemblage.points_d_entree(str(tmp_path)) == []


def test_les_tests_ne_comptent_pas_comme_points_d_entree(tmp_path) -> None:
    """Un test qui monte son propre client est un banc d'essai."""
    _pose(tmp_path, "tests/test_api.py",
          "from fastapi import FastAPI\napp = FastAPI()\n")

    assert assemblage.points_d_entree(str(tmp_path)) == []


def test_un_assemblage_existant_est_reconnu(tmp_path) -> None:
    _pose(tmp_path, "main.py",
          "from fastapi import FastAPI\nimport kpi\n"
          "app = FastAPI()\napp.include_router(kpi.router)\n")

    assert assemblage.monte_un_routeur(str(tmp_path))


def test_un_routeur_monte_sur_lui_meme_ne_compte_pas(tmp_path) -> None:
    """`app.include_router(_router)` n'assemble rien d'autre que soi."""
    _pose(tmp_path, "seul.py",
          "from fastapi import FastAPI, APIRouter\n_router = APIRouter()\n"
          "app = FastAPI()\napp.include_router(_router)\n")

    assert not assemblage.monte_un_routeur(str(tmp_path))


def test_le_depot_lui_meme_ne_declenche_pas_de_faux_defaut() -> None:
    """Hermes OS a un point d'entree unique ; le garde doit le voir ainsi."""
    entrees = assemblage.points_d_entree(".")

    assert len(entrees) <= 1, f"points d'entree detectes : {entrees}"
