"""Un import relatif qui remonte au-dessus de son paquet (HOS-146).

Mesure du 2026-08-21, section §9 d'un deroule de cahier, sur les **deux**
passes. Le livrable contenait :

    # tests/test_atelier.py
    from django.test import TestCase
    from ..models import Atelier

et la collecte echouait avant le premier test :

    ImportError: attempted relative import beyond top-level package

Aucun instrument ne le voyait. La porte de syntaxe (HOS-121) compile le
fichier sans broncher — il est syntaxiquement parfait. La detection de
symboles (HOS-135) ne suit pas les imports. `imports_locaux` (HOS-124)
cherche des boucles, ce qui est une autre question. Le verdict des tests
l'a bien attrape, mais apres coup : la campagne s'est arretee la, apres
avoir consomme deux passes sur la section.

La regle est celle du langage : pour `a/b/c.py`, `.` vaut `a.b`, `..` vaut
`a`, et `...` sort de l'arbre. Le niveau maximal est le nombre de dossiers
au-dessus du fichier. Elle ne depend d'aucun `sys.path`, d'aucun outil de
test, d'aucune convention — un import qui la viole echoue partout.
"""
from __future__ import annotations

import pytest

from backend.mission import imports_relatifs as ir


class TestLaRegleDuLangage:
    @pytest.mark.parametrize("profondeur,niveau,invalide", [
        (1, 2, True),    # tests/test_atelier.py avec `from ..models` : le cas mesure
        (1, 1, False),   # `from .voisin` dans le meme dossier : valide
        (2, 2, False),   # a/b/c.py avec `..` : remonte a `a`, valide
        (2, 3, True),    # a/b/c.py avec `...` : sort de l'arbre
        (0, 1, True),    # un fichier a la racine n'a aucun paquet au-dessus
    ])
    def test_le_niveau_maximal_est_la_profondeur(self, profondeur, niveau,
                                                 invalide):
        source = "from " + "." * niveau + "module import Chose"

        fautes = ir.remontees_invalides(source, profondeur)

        assert bool(fautes) is invalide

    def test_un_import_absolu_n_est_jamais_concerne(self):
        source = "from django.test import TestCase\nimport os"

        assert ir.remontees_invalides(source, 0) == []

    def test_la_ligne_est_rendue(self):
        """« un import est invalide quelque part » envoie chercher
        partout."""
        source = "import os\n\nfrom ..models import Atelier\n"

        fautes = ir.remontees_invalides(source, 1)

        assert fautes == [(3, 2)]


class TestCeDontIlSeTait:
    def test_un_fichier_qui_ne_compile_pas(self):
        """La porte de syntaxe s'en occupe deja ; deux messages pour un
        seul defaut envoient l'agent corriger deux fois."""
        assert ir.remontees_invalides("def f(:\n", 2) == []

    def test_un_projet_absent(self):
        assert ir.verdict("/dossier/qui/n/existe/pas") is None

    def test_le_message_est_vide_quand_tout_va_bien(self, tmp_path):
        (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")

        assert ir.message(str(tmp_path)) == ""


class TestSurUnProjetReel:
    def test_le_cas_mesure_est_attrape(self, tmp_path):
        paquet = tmp_path / "tests"
        paquet.mkdir()
        (paquet / "test_atelier.py").write_text(
            "from django.test import TestCase\nfrom ..models import Atelier\n",
            encoding="utf-8")

        faute = ir.verdict(str(tmp_path))

        assert faute is not None
        assert faute["ligne"] == 2 and faute["niveau"] == 2
        assert "test_atelier.py" in faute["fichier"]

    def test_le_message_nomme_le_fichier_et_la_ligne(self, tmp_path):
        paquet = tmp_path / "api"
        paquet.mkdir()
        (paquet / "atelier.py").write_text("from ..models import A\n",
                                           encoding="utf-8")

        message = ir.message(str(tmp_path))

        assert "atelier.py" in message and ":1" in message
        assert "beyond top-level package" in message

    def test_le_depot_lui_meme_ne_declenche_rien(self):
        """574 fichiers Python. Un faux positif ici ferait echouer toutes
        les missions du projet, et c'est la moitie des defauts de mesure de
        ce depot qui etaient des echecs imaginaires."""
        assert ir.verdict("backend") is None


class TestLaContradiction:
    """Un import hors paquet contredit un succes annonce **sans reserve**,
    contrairement a une boucle d'import dont seules certaines sont fatales.
    Celle-ci echoue partout et toujours."""

    def test_il_contredit_meme_avec_des_fichiers_ecrits(self):
        from backend.mission.verification import (
            MissionVerification,
            WorkspaceDiff,
        )

        rapport = MissionVerification(
            mission_id="m", reported_success=True, workspace="/w",
            changes=WorkspaceDiff(created=("a.py",)), measured=True,
            imports_remontent={"fichier": "api/atelier.py", "ligne": 4,
                               "niveau": 2, "profondeur": 1})

        assert rapport.import_hors_paquet is True
        assert rapport.contradicted is True

    def test_le_rapport_porte_le_detail(self):
        """Sans cela, il dirait « contredite » sans dire quel fichier ni
        quelle ligne — et le diagnostic repartirait de zero."""
        from backend.mission.verification import (
            MissionVerification,
            WorkspaceDiff,
        )

        faute = {"fichier": "api/atelier.py", "ligne": 4, "niveau": 2,
                 "profondeur": 1}
        rapport = MissionVerification(
            mission_id="m", reported_success=True, workspace="/w",
            changes=WorkspaceDiff(), measured=True, imports_remontent=faute)

        assert rapport.as_dict()["imports_remontent"] == faute
