"""Un modele qui fabrique la dependance qui lui manque (HOS-148).

Mesure sur **deux campagnes consecutives**, la meme pathologie :

* §9 d'un deroule — `django/__init__.py`, `django/db/__init__.py`,
  `django/test.py` crees dans le workspace ;
* §6 du suivant — `flask/__init__.py`, en toutes lettres « Minimal Flask
  stub for tests », dont le `DummyClient` n'avait pas la moitie des
  methodes appelees :

      AttributeError: 'DummyClient' object has no attribute 'post'

Le modele ne dit pas « il me manque Flask ». Il **l'ecrit**.

Pire qu'une dependance absente : celle-ci echoue franchement, au premier
import, avec son nom dans le message. Un faux paquet la masque, laisse le
projet se construire par-dessus, et ne cede qu'au moment ou une methode non
implementee est appelee.
"""
from __future__ import annotations

import pytest

from backend.mission import faux_paquets as fp


def _paquet(racine, nom: str, contenu: str = "# stub\n"):
    dossier = racine / nom
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "__init__.py").write_text(contenu, encoding="utf-8")
    return dossier


class TestCeQuiEstRefuse:
    @pytest.mark.parametrize("nom", ["flask", "django", "numpy", "pytest"])
    def test_un_paquet_tiers_fabrique(self, tmp_path, nom):
        _paquet(tmp_path, nom)

        faux = fp.verdict(str(tmp_path))

        assert faux is not None and faux["paquet"] == nom

    def test_le_cas_mesure_avec_son_contenu(self, tmp_path):
        _paquet(tmp_path, "flask", "# Minimal Flask stub for tests\n")

        message = fp.message(str(tmp_path))

        assert "DÉPENDANCE FABRIQUÉE" in message
        assert "flask" in message
        assert "déclare-le comme dépendance" in message

    def test_meme_en_sous_dossier(self, tmp_path):
        _paquet(tmp_path / "src", "django")

        assert fp.verdict(str(tmp_path)) is not None

    def test_la_casse_ne_le_sauve_pas(self, tmp_path):
        _paquet(tmp_path, "Flask")

        assert fp.verdict(str(tmp_path)) is not None


class TestCeQuiPasse:
    """Un faux refus coute autant qu'une fuite. La liste est fermee et
    courte pour cette raison : une heuristique « ce nom ressemble a un
    paquet PyPI » refuserait des modules parfaitement legitimes."""

    @pytest.mark.parametrize("nom", ["models", "api", "tests", "services",
                                     "core", "utils", "domain"])
    def test_un_module_applicatif(self, tmp_path, nom):
        _paquet(tmp_path, nom)

        assert fp.verdict(str(tmp_path)) is None

    def test_un_dossier_sans_init_n_est_pas_un_paquet(self, tmp_path):
        """Un dossier `flask/` sans `__init__.py` ne masque rien : Python
        ne le prendra pas pour le paquet."""
        (tmp_path / "flask").mkdir()
        (tmp_path / "flask" / "notes.md").write_text("x", encoding="utf-8")

        assert fp.verdict(str(tmp_path)) is None

    def test_le_vrai_paquet_installe_est_ignore(self, tmp_path):
        """`.venv/Lib/site-packages/flask/` est le **vrai** Flask. Le
        signaler ferait echouer tout projet qui a ses dependances."""
        _paquet(tmp_path / ".venv" / "Lib" / "site-packages", "flask")

        assert fp.verdict(str(tmp_path)) is None

    def test_le_depot_lui_meme_ne_declenche_rien(self):
        assert fp.verdict("backend") is None


class TestALEcriture:
    """Dite au moment ou le `__init__.py` est ecrit, la faute ne coute
    qu'un tour. Decouverte plus tard, il faut defaire tout ce qui s'est
    appuye dessus."""

    def test_le_init_d_un_paquet_tiers_est_signale(self):
        rendu = fp.message_du_fichier(r"C:\ws\flask\__init__.py", r"C:\ws")

        assert "DÉPENDANCE FABRIQUÉE" in rendu

    def test_un_module_applicatif_ne_dit_rien(self):
        assert fp.message_du_fichier(r"C:\ws\models\__init__.py", r"C:\ws") == ""

    def test_un_autre_fichier_du_meme_dossier_ne_dit_rien(self):
        """On signale la creation du paquet, pas chacun de ses fichiers —
        repeter l'avertissement apprend a l'ignorer."""
        assert fp.message_du_fichier(r"C:\ws\flask\app.py", r"C:\ws") == ""


class TestLaContradiction:
    def test_il_contredit_meme_quand_les_tests_passent(self):
        """Ils passent justement parce que la doublure satisfait les
        imports. C'est un mensonge sur le contenu du workspace, pas une
        faiblesse du code."""
        from backend.mission.verification import (
            MissionVerification,
            WorkspaceDiff,
        )

        rapport = MissionVerification(
            mission_id="m", reported_success=True, workspace="/w",
            changes=WorkspaceDiff(created=("a.py",)), measured=True,
            tests={"ran": True, "passed": True},
            faux_paquet={"paquet": "flask", "chemin": "flask"})

        assert rapport.dependance_fabriquee is True
        assert rapport.contradicted is True

    def test_la_reparation_sait_quoi_supprimer(self):
        from backend.mission.programme import diagnostic

        texte = diagnostic({"faux_paquet": {"paquet": "flask",
                                            "chemin": "flask"}}, "echec")

        assert "flask" in texte and "Supprime-le" in texte
