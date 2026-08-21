"""Un symbole reference et jamais defini (HOS-135).

Trois lancements de la file, trois workspaces neufs, trois sections
differentes, et le meme defaut a chaque fois :

    run 7  §11  AttributeError: 'PositionAuthorization' has no attribute 'id'
    run 8  §6   AttributeError: 'User' has no attribute '_current_time'
    run 9  §6   NameError: name 'Optional' is not defined

Ce n'est pas de la variance, et aucun instrument ne le voyait : la porte de
syntaxe analyse chaque fichier et **les trois compilent parfaitement** ; le
detecteur de boucles d'import cherche autre chose ; le verdict des tests
l'attrape, mais a la fin de la mission, une fois le temps depense.
"""
from __future__ import annotations

import pytest

from backend.mission.symboles import message, verdict


class TestLesTroisDefautsMesures:
    def test_run_9_un_nom_utilise_sans_import(self):
        v = verdict("m.py", "def f(x: Optional[int]):\n    return x\n")

        assert v and "Optional" in v

    def test_run_8_une_methode_appelee_sur_self_et_jamais_definie(self):
        v = verdict("m.py",
                    "class User:\n"
                    "    def __init__(self):\n        self.nom = 1\n"
                    "    def go(self):\n        return self._current_time()\n")

        assert v and "_current_time" in v and "User" in v

    def test_run_7_un_attribut_lu_et_jamais_pose(self):
        v = verdict("m.py",
                    "class PositionAuthorization:\n"
                    "    def __init__(self, post_id):\n"
                    "        self.post_id = post_id\n"
                    "    def cle(self):\n        return self.id\n")

        assert v and "self.id" in v

    def test_une_annotation_de_retour_compte_aussi(self):
        """`visit_arg` n'explorait pas ses enfants : l'annotation d'un
        argument n'etait jamais visitee, et le defaut du run 9 passait au
        travers du module ecrit pour l'attraper."""
        assert verdict("m.py", "def f() -> Dict[str, int]:\n    return {}\n")


class TestCeQuiNeDoitJamaisEtreSignale:
    """Un faux echec coute autant qu'un faux succes : cinq des huit defauts
    de mesure de ce depot etaient des echecs imaginaires."""

    @pytest.mark.parametrize("source", [
        "from typing import Optional\n"
        "class A:\n    def __init__(self):\n        self.x = 1\n"
        "    def get(self) -> Optional[int]:\n        return self.x\n",
        "def f(items):\n    t = 0\n    for it in items:\n        t += it\n    return t\n",
        "def f(xs):\n    return [y * 2 for y in xs]\n",
        "def f():\n    try:\n        pass\n    except ValueError as e:\n        return e\n",
    ])
    def test_du_code_sain_ne_declenche_rien(self, source):
        assert verdict("m.py", source) is None

    def test_une_classe_qui_herite_fait_taire_l_analyse(self):
        """Elle recoit des attributs qu'on ne voit pas ici."""
        assert verdict("m.py", "from base import Base\n"
                               "class B(Base):\n"
                               "    def go(self):\n        return self.inconnu\n") is None

    def test_un_decorateur_fait_taire_l_analyse(self):
        """`@dataclass` fabrique des attributs depuis les annotations."""
        assert verdict("m.py", "from dataclasses import dataclass\n"
                               "@dataclass\nclass C:\n"
                               "    def go(self):\n        return self.champ\n") is None

    def test_un_import_etoile_fait_taire_l_analyse(self):
        """On ne sait plus ce qui entre dans la portee."""
        assert verdict("m.py", "from os import *\ndef f():\n    return path\n") is None

    def test_setattr_fait_taire_l_analyse(self):
        assert verdict("m.py", "class D:\n    def __init__(self):\n"
                               "        setattr(self, 'x', 1)\n"
                               "    def go(self):\n        return self.x\n") is None

    def test_une_constante_de_classe_n_est_pas_un_attribut_manquant(self):
        """Le motif qui produisait **20 faux positifs** sur les 574 fichiers
        de ce depot — `MAX_RETAINED = 100` en corps de classe, lu via
        `self.MAX_RETAINED`."""
        assert verdict("m.py", "class E:\n    MAX = 100\n"
                               "    def go(self):\n        return self.MAX\n") is None

    def test_un_fichier_qui_ne_compile_pas_releve_de_la_porte_de_syntaxe(self):
        """Diagnostiquer ici donnerait une cause fausse."""
        assert verdict("m.py", "def f(:\n") is None

    def test_une_extension_inconnue_n_est_pas_analysee(self):
        assert verdict("notes.md", "self.inconnu") is None


class TestSurLeDepotLuiMeme:
    def test_les_574_fichiers_du_backend_ne_declenchent_rien(self):
        """Le garde-fou le plus parlant : du code reel, ecrit par des
        humains, dont aucun ne doit etre signale. Ce test a trouve un vrai
        defaut latent — `logger` appele sans exister dans model_bench.py,
        dans le gestionnaire meme cense absorber une erreur."""
        from pathlib import Path

        signales = []
        for chemin in Path("backend").rglob("*.py"):
            if "__pycache__" in chemin.parts:
                continue
            v = verdict(str(chemin),
                        chemin.read_text(encoding="utf-8", errors="replace"))
            if v:
                signales.append(f"{chemin}: {v}")
        assert not signales, "faux positifs : " + " | ".join(signales[:3])


class TestLeMessage:
    def test_il_dit_que_le_fichier_compile(self):
        """Sinon le modele cherchera une erreur de syntaxe qui n'existe pas."""
        m = message("m.py", "def f(x: Optional[int]):\n    return x\n")

        assert "il compile" in m and "n'existe pas" in m

    def test_rien_n_est_ajoute_quand_tout_va_bien(self):
        assert message("m.py", "x = 1\n") == ""
