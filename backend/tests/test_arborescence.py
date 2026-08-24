"""Trois arborescences paralleles dans le meme projet (HOS-159).

Campagne Skill360 du 2026-08-24, trois sections d'affilee declarees
`signalee (contredite)` pour la meme raison — un livrable annonce a un
chemin, ecrit a un autre :

    §11  annonce tests/test_position_models.py     absent
    §12  annonce backend/models/position_skill.py  absent
    §13  annonce docs/required_level.md            absent

Ce n'etait pas un defaut de nommage. Le workspace portait trois
arborescences : `models/` et `backend/models/`, `api/` et `backend/api/`,
plus six fichiers a la racine. §12 a annonce `backend/models/position_skill.py`
alors que §11 avait cree `models/position_skill.py` deux minutes plus tot,
et §13 a ecrit `tests/docs/required_level.md` — un dossier `docs` **dans**
`tests`.

C'est le meme defaut que `pile.py` un cran plus haut : la memoire des
fichiers produits ne transmet pas la **decision** qu'ils incarnent.
"""
from __future__ import annotations

from backend.mission import arborescence


def _pose(base, chemins) -> None:
    for c in chemins:
        f = base / c
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n", encoding="utf-8")


def test_les_dossiers_de_code_sont_comptes(tmp_path) -> None:
    _pose(tmp_path, ["models/a.py", "models/b.py", "tests/t.py", "racine.py"])

    compte = arborescence.dossiers_de_code(str(tmp_path))

    assert compte["models"] == 2
    assert compte["tests"] == 1
    assert compte["."] == 1, "la racine est un emplacement legitime"


def test_un_projet_vide_n_impose_rien(tmp_path) -> None:
    """Imposer une arborescence que personne n'a choisie serait la
    supposition que le §5 du cahier interdit — meme retenue que `pile`."""
    assert arborescence.contrainte(str(tmp_path)) == ""


def test_deux_fichiers_ne_font_pas_une_convention(tmp_path) -> None:
    """Un debut qu'une section a encore le droit de reorganiser."""
    _pose(tmp_path, ["a.py", "b.py"])

    assert arborescence.contrainte(str(tmp_path)) == ""


def test_les_dossiers_techniques_ne_comptent_pas(tmp_path) -> None:
    _pose(tmp_path, ["models/a.py", "models/b.py", "models/c.py",
                     "__pycache__/x.py", ".venv/lib/y.py",
                     "node_modules/z.js"])

    compte = arborescence.dossiers_de_code(str(tmp_path))

    assert set(compte) == {"models"}


def test_la_documentation_n_est_pas_une_decision_d_architecture(tmp_path) -> None:
    """Un dossier plein de `.md` ne dit rien de l'ou vit le code."""
    _pose(tmp_path, ["models/a.py", "models/b.py", "models/c.py"])
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("# doc\n", encoding="utf-8")

    assert "docs" not in arborescence.dossiers_de_code(str(tmp_path))


def test_la_contrainte_nomme_les_dossiers_reels(tmp_path) -> None:
    _pose(tmp_path, ["models/a.py", "models/b.py", "tests/t.py"])

    texte = arborescence.contrainte(str(tmp_path))

    assert "models/" in texte and "tests/" in texte
    # L'incident lui-meme doit etre nomme, sinon la regle se discute.
    assert "backend/models/x.py" in texte
    assert "exactement" in texte


def test_la_liste_reste_lisible_sur_un_gros_projet(tmp_path) -> None:
    """Trente dossiers dans un brief se font ignorer autant que le silence."""
    _pose(tmp_path, [f"d{i}/f.py" for i in range(30)])

    texte = arborescence.contrainte(str(tmp_path))

    assert texte.count("fichier(s)") == arborescence.PLAFOND_DOSSIERS


def test_un_workspace_absent_ne_leve_pas() -> None:
    assert arborescence.contrainte(None) == ""
    assert arborescence.contrainte("Z:/nulle/part") == ""
