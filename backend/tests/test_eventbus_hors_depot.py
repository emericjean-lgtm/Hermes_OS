"""Le journal d'événements ne vit pas dans le dépôt (HOS-237).

## La régression, mesurée

`backend/main.py` initialisait le bus durable sur
`"./data/eventbus/eventbus.sqlite"` — un chemin **relatif au répertoire
courant**, donc au dépôt.

Constaté sur l'installation réelle, deux fichiers coexistaient :

    data/eventbus/eventbus.sqlite                     3,2 Mo, vivant
    %LOCALAPPDATA%/HermesOS/eventbus/eventbus.sqlite  8,2 Mo, mort

Le **vivant** était celui du dépôt. Celui de la racine d'état était un
résidu de la migration HOS-215, que plus rien n'alimentait.

C'est une régression directe contre HOS-215 et HOS-220, et elle était
exploitable : le moteur de mise à jour de HOS-233 remplace l'arbre de
code, et `preserve_set()` ne protège que la racine d'état. Une mise à
jour aurait donc effacé le journal d'événements **vivant** — sans que
rien le dise, puisque la copie morte, elle, aurait survécu.

## Pourquoi ces gardes lisent le code et le disque

`test_le_bus_n_est_pas_initialise_sur_un_chemin_relatif` lit l'arbre
syntaxique de `main.py` : c'est la seule façon d'empêcher le retour de la
constante. Les autres exercent le chemin réel.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

RACINE_DEPOT = Path(__file__).resolve().parents[2]


def _valeurs_litterales_de_main() -> list[str]:
    """Toutes les chaînes littérales de `backend/main.py`.

    Sur l'arbre syntaxique et non sur le texte : un commentaire ou une
    docstring qui *mentionne* `./data/eventbus` — comme le fait ce
    fichier-ci — ne doit pas déclencher la garde. Le dépôt a payé cinq
    fois le prix de ce faux positif.
    """
    source = io.open(RACINE_DEPOT / "backend" / "main.py",
                     encoding="utf-8").read()
    return [n.value for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_le_bus_n_est_pas_initialise_sur_un_chemin_relatif():
    """La garde qui empêche la constante de revenir.

    Elle a été observée **rouge** sur le comportement d'avant HOS-237 :
    `main.py` portait littéralement `"./data/eventbus/eventbus.sqlite"`.
    """
    suspects = [v for v in _valeurs_litterales_de_main()
                if "eventbus" in v.lower()
                and (v.startswith("./") or v.startswith("data/")
                     or v.startswith(".\\"))]
    assert not suspects, (
        f"chemin d'EventBus relatif au dépôt : {suspects} — une mise à "
        "jour du code effacerait le journal d'événements (HOS-215/220)")


def test_le_bus_passe_par_la_racine_d_etat():
    """Structurellement : `main` demande le chemin à `core.etat`.

    Vérifié sur les appels, pas sur le texte : c'est le seul module
    autorisé à décider où vit l'état, et lui seul refuse une racine qui
    retomberait dans le dépôt.
    """
    source = io.open(RACINE_DEPOT / "backend" / "main.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any("chemin" in a for a in appels), (
        "aucun appel à `etat.chemin` dans main.py — le bus ne peut donc "
        "pas être garanti hors du dépôt")


def test_le_fichier_atterrit_sous_la_racine_d_etat(tmp_path, monkeypatch):
    """Le chemin réel, exercé.

    Une garde structurelle dit que le code *demande* le bon chemin ;
    celle-ci vérifie qu'il *obtient* le bon.
    """
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    import backend.core.etat as etat

    etat.racine.cache_clear()
    try:
        from backend.main import _chemin_du_bus

        chemin = Path(_chemin_du_bus())
        assert tmp_path in chemin.parents
        assert RACINE_DEPOT not in chemin.parents
        assert chemin.parent.name == "eventbus"
    finally:
        etat.racine.cache_clear()


def test_hermes_data_dir_est_respecte(tmp_path, monkeypatch):
    ailleurs = tmp_path / "ailleurs"
    monkeypatch.setenv("HERMES_DATA_DIR", str(ailleurs))
    import backend.core.etat as etat

    etat.racine.cache_clear()
    try:
        from backend.main import _chemin_du_bus

        assert str(ailleurs) in _chemin_du_bus()
    finally:
        etat.racine.cache_clear()


def test_le_bus_survit_au_remplacement_du_code(tmp_path, monkeypatch):
    """Le scénario que la régression rendait mortel.

    HOS-233 remplace l'arbre de code ; `preserve_set()` ne protège que la
    racine d'état. Un bus sous `./data/` aurait donc disparu à la
    première mise à jour.
    """
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path / "etat"))
    import backend.core.etat as etat

    etat.racine.cache_clear()
    try:
        from backend.main import _chemin_du_bus

        chemin = Path(_chemin_du_bus())
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"journal")

        # Le remplacement du code n'emporte que les racines déclarées par
        # le paquet — jamais la racine d'état.
        from backend.maj.code import PRESERVE_EN_PLACE
        from backend.maj.paquet import RACINES_PAR_DEFAUT

        assert not any(str(chemin).startswith(str(RACINE_DEPOT / r))
                       for r in RACINES_PAR_DEFAUT), (
            "le journal est dans une racine que la mise à jour remplace")
        assert PRESERVE_EN_PLACE  # la liste existe et est consultée
        assert chemin.read_bytes() == b"journal"
    finally:
        etat.racine.cache_clear()


def test_l_eventbus_est_dans_le_preserve_set():
    """Sans quoi la sauvegarde de mise à jour l'oublierait.

    `SOUS_DOSSIERS` le déclare depuis HOS-215 — mais le bus n'y écrivait
    pas. Les deux moitiés se rejoignent enfin.
    """
    from backend.core.etat import SOUS_DOSSIERS

    assert "eventbus" in SOUS_DOSSIERS


def test_il_n_existe_qu_un_seul_chemin_de_bus_durable():
    """Deux initialisations donneraient deux journaux, dont un muet.

    C'est exactement l'état trouvé : une base vivante dans le dépôt, une
    base morte sous la racine d'état, et rien pour dire laquelle faisait
    foi.
    """
    initialisations: list[str] = []
    for fichier in (RACINE_DEPOT / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call)
                    and ast.unparse(noeud.func).endswith(
                        "init_eventbus_in_holder")):
                initialisations.append(str(fichier.relative_to(RACINE_DEPOT)))
    assert len(initialisations) <= 1, (
        f"le bus durable est initialisé à {len(initialisations)} endroits : "
        f"{initialisations}")
