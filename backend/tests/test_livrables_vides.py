"""§8 declaree verifiee au-dessus de quatre commentaires (HOS-156).

Campagne Skill360 du 2026-08-24. §8 ORGANISATION a rendu :

    models/atelier.py       # Atelier model placeholder
    models/employe.py       # Employe model placeholder
    models/poste.py         # Poste model placeholder
    models/responsable.py   # Responsable model placeholder

et deux tests qui produisaient le vert : l'un importait un fichier ne
contenant qu'un commentaire, l'autre verifiait que le fichier qu'on venait
de creer existait. Verdict : **verifiee**.

Trois sections successives ont ensuite laisse `responsable.py` a l'etat de
commentaire, alors que la relation responsable <-> ateliers etait la seule
contrainte que le cahier tenait a ne pas voir figee.

Comme pour les autres gardes, la moitie de ces tests porte sur ce qui ne
doit **pas** etre signale : verifie sur les 549 modules du depot, zero
signalement.
"""
from __future__ import annotations

from backend.mission import livrables_vides as vides, programme


# -- ce qui doit etre signale -----------------------------------------

def test_un_commentaire_seul_ne_fait_pas_un_livrable() -> None:
    assert vides.est_un_placeholder("# Atelier model placeholder")


def test_un_docstring_et_un_pass_non_plus() -> None:
    assert vides.est_un_placeholder('"""Le modele Atelier."""\npass\n')


def test_plusieurs_commentaires_non_plus() -> None:
    assert vides.est_un_placeholder(
        "# models/responsable.py\n"
        "# Placeholder for a Responsable entity.\n"
        "# Add fields such as id, name, and any related responsibilities.\n")


# -- ce qui ne doit **pas** l'etre ------------------------------------

def test_une_classe_meme_vide_est_du_contenu() -> None:
    """`class A: pass` declare un type ; le commentaire ne declare rien."""
    assert not vides.est_un_placeholder("class Atelier:\n    pass\n")


def test_un_module_de_reexport_est_du_contenu() -> None:
    """Un module qui ne fait que republier n'a rien d'autre a contenir."""
    assert not vides.est_un_placeholder("from .atelier import Atelier\n")


def test_un_module_de_constantes_est_du_contenu() -> None:
    assert not vides.est_un_placeholder('"""Reglages."""\nMAX = 10\n')


def test_un_fichier_vide_n_a_rien_pretendu() -> None:
    """Il ne se donne pas pour un livrable, contrairement au placeholder."""
    assert not vides.est_un_placeholder("")
    assert not vides.est_un_placeholder("\n\n  \n")


def test_un_fichier_qui_ne_compile_pas_releve_d_un_autre_garde() -> None:
    assert not vides.est_un_placeholder("class A(:\n")


def test_un_init_vide_est_la_forme_normale_d_un_paquet(tmp_path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "__init__.py").write_text("# paquet\n",
                                                     encoding="utf-8")

    assert vides.verdict(str(tmp_path)) is None


# -- l'incident, de bout en bout --------------------------------------

def test_le_verdict_nomme_le_fichier_et_ce_qu_il_contient(tmp_path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "atelier.py").write_text(
        "# Atelier model placeholder\n", encoding="utf-8")

    faute = vides.verdict(str(tmp_path))

    assert faute is not None
    assert faute["fichier"].endswith("atelier.py")
    assert "placeholder" in faute["apercu"]


def test_une_section_livrant_un_placeholder_est_bloquante() -> None:
    """Le point du garde : §8 ne devait pas passer pour faite.

    Des fichiers ecrits et des tests verts ne suffisent pas quand les
    fichiers ne definissent rien — la section suivante se construira
    dessus.
    """
    bloque, raison = programme.bloquant({
        "created": ["models/atelier.py"],
        "tests": {"ran": True, "passed": True},
        "livrable_vide": {"fichier": "models/atelier.py",
                          "apercu": "# Atelier model placeholder"},
    })

    assert bloque
    assert "livrable vide" in raison
    assert "models/atelier.py" in raison


def test_le_brief_de_reparation_dit_quoi_ecrire() -> None:
    brief = programme.diagnostic({
        "livrable_vide": {"fichier": "models/responsable.py",
                          "apercu": "# Placeholder for a Responsable entity."},
    }, "peu importe")

    assert "models/responsable.py" in brief
    # Il doit couper court a la parade : « mais mon test passe ».
    assert "importer" in brief


def test_le_depot_lui_meme_ne_declenche_rien() -> None:
    """Un garde qui signale du code legitime coute plus qu'il ne rapporte."""
    from pathlib import Path

    fautes = [
        p for p in Path("backend").rglob("*.py")
        if "__pycache__" not in p.parts and p.name not in vides._TOLERES
        and vides.est_un_placeholder(p.read_text(encoding="utf-8",
                                                 errors="replace"))
    ]

    assert fautes == []


# -- la portee du garde (HOS-158) -------------------------------------

def test_une_section_n_est_pas_bloquee_pour_le_jalon_d_une_autre(tmp_path) -> None:
    """Un garde qui reproche a une mission le travail d'une autre.

    Sans portee, le garde inspectait tout le workspace. Une section qui ne
    touche pas au placeholder du voisin serait bloquee sans aucun moyen de
    s'en sortir — le faux echec type, et ce projet a mesure que cinq de ses
    huit defauts d'instrumentation en produisaient.
    """
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "voisin.py").write_text(
        "# jalon laisse par une autre section\n", encoding="utf-8")
    (tmp_path / "models" / "mien.py").write_text(
        "class Atelier:\n    pass\n", encoding="utf-8")

    assert vides.verdict(str(tmp_path), touches=["models/mien.py"]) is None


def test_le_jalon_de_la_section_elle_meme_est_bien_signale(tmp_path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "mien.py").write_text(
        "# Placeholder for the Employee domain model.\n", encoding="utf-8")

    faute = vides.verdict(str(tmp_path), touches=["models/mien.py"])

    assert faute is not None and faute["fichier"].endswith("mien.py")


def test_un_fichier_annonce_mais_absent_ne_leve_pas(tmp_path) -> None:
    """Le manifeste signale l'absence ; ce garde n'a rien a en dire."""
    assert vides.verdict(str(tmp_path), touches=["models/jamais_ecrit.py"]) is None


def test_les_chemins_windows_du_diff_sont_acceptes(tmp_path) -> None:
    """Le diff du workspace rend `models\employe.py`, pas `models/employe.py`."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "employe.py").write_text("# vide\n", encoding="utf-8")

    assert vides.verdict(str(tmp_path), touches=[r"models\employe.py"])


def test_la_suppression_est_nommee_comme_issue(tmp_path) -> None:
    """L'agent avait argumente son placeholder ; le message ne repondait pas.

    §9 a ecrit « The concrete implementation resides in employees_api.py.
    No concrete class is defined here to avoid duplication. » L'argument se
    defend — mais la bonne action etait de supprimer le fichier, et le
    message ne le disait pas.
    """
    (tmp_path / "x.py").write_text("# rien ici\n", encoding="utf-8")

    m = vides.message(str(tmp_path))

    assert "supprimes le fichier" in m
    assert "import le trouvera" in m


# -- les livrables non-Python (HOS-171) -------------------------------

def test_un_javascript_qui_s_avoue_jalon_est_signale() -> None:
    """§27 FRONTEND declaree verifiee au-dessus de deux lignes.

        frontend/app.js   // Frontend JS placeholder
                          console.log('Frontend loaded');

    Cinq livrables annonces, cinq presents, tests passes. Le garde de
    HOS-156 l'aurait vu sans hesiter s'il avait regarde ailleurs que dans
    les `.py`.
    """
    assert vides.est_un_jalon_hors_python(
        "app.js", "// Frontend JS placeholder\nconsole.log('Frontend loaded');\n")


def test_un_fichier_qui_n_a_que_des_commentaires_est_signale() -> None:
    assert vides.est_un_jalon_hors_python("style.css", "/* a completer */\n")


def test_du_vrai_javascript_est_laisse_tranquille() -> None:
    src = "export function charger(){ return fetch('/api/kpi').then(r=>r.json()); }\n"
    assert not vides.est_un_jalon_hors_python("api.js", src)


def test_un_css_court_mais_reel_est_laisse_tranquille() -> None:
    """Un fichier court n'est pas un jalon : il faut qu'il s'avoue tel."""
    assert not vides.est_un_jalon_hors_python("style.css", "body { margin: 0; }\n")


def test_un_html_minimal_est_laisse_tranquille() -> None:
    src = "<!DOCTYPE html><html><body><h1>Skills360</h1></body></html>"
    assert not vides.est_un_jalon_hors_python("index.html", src)


def test_un_fichier_vide_n_a_rien_pretendu_hors_python() -> None:
    assert not vides.est_un_jalon_hors_python("x.js", "")


def test_le_verdict_voit_le_frontend(tmp_path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "app.js").write_text(
        "// Frontend JS placeholder\nconsole.log('ok');\n", encoding="utf-8")

    faute = vides.verdict(str(tmp_path), touches=["frontend/app.js"])

    assert faute is not None and faute["fichier"].endswith("app.js")


def test_le_frontend_de_hermes_os_ne_declenche_rien() -> None:
    """Un garde qui signale du code legitime coute plus qu'il ne rapporte."""
    from pathlib import Path

    src = Path("frontend/src")
    if not src.is_dir():
        return
    fautes = [
        p for p in src.rglob("*")
        if p.is_file() and p.suffix.lower() in vides._EXTENSIONS_SURVEILLEES
        and vides.est_un_jalon_hors_python(
            p.name, p.read_text(encoding="utf-8", errors="replace"))
    ]

    assert fautes == []
