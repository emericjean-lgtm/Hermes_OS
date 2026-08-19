"""Le travail ne réécrit pas les documents qui le définissent (HOS-129).

L'incident, mesuré sur la première file réelle de 26 sections : une mission
a écrasé `PROJECT_SPEC.md`. Le cahier des charges est passé de **23 Ko et
342 lignes à 1,2 Ko**, ne contenant plus que la section sur laquelle elle
travaillait. La source de vérité du projet a été détruite par le projet.

Le §36 de ce cahier exigeait déjà une validation explicite pour toute
modification. La règle existait ; rien ne la faisait respecter.

La protection est posée dans `file_tools` et non dans `workspace_chat_tools`
**parce que c'est le goulot** : le serveur MCP appelle `file_tools`
directement, sans passer par l'adaptateur du chat. Une protection posée en
amont laisserait une porte ouverte.
"""
from __future__ import annotations

import pytest

from backend.security.aegis_engine import Verdict
from backend.tools import file_tools


class _Autorise:
    verdict = Verdict.ALLOW
    reason = "test"


class _Aegis:
    def evaluate(self, requete):
        return _Autorise()


@pytest.fixture
def projet(tmp_path):
    """Un workspace avec un cahier déclaré protégé."""
    (tmp_path / "PROJECT_SPEC.md").write_text("le cahier" * 100, encoding="utf-8")
    (tmp_path / "libre.py").write_text("x = 1\n", encoding="utf-8")
    liste = tmp_path / file_tools.FICHIER_PROTEGES
    liste.parent.mkdir(parents=True, exist_ok=True)
    liste.write_text("# commentaire\nPROJECT_SPEC.md\n", encoding="utf-8")
    return tmp_path


class TestCeQuiEstRefuse:
    def test_ecraser_le_cahier_est_refuse(self, projet):
        """L'incident exact."""
        avant = (projet / "PROJECT_SPEC.md").read_text(encoding="utf-8")

        resultat = file_tools.propose_write(
            _Aegis(), str(projet / "PROJECT_SPEC.md"), "## 13 REQUIRED LEVEL")

        assert resultat.applied is False
        assert resultat.verdict == "deny"
        assert (projet / "PROJECT_SPEC.md").read_text(encoding="utf-8") == avant

    def test_le_refus_dit_quoi_faire(self, projet):
        """« Lis-le, ne le réécris pas » : un refus sans consigne fait
        boucler le modèle sur la même tentative."""
        resultat = file_tools.propose_write(
            _Aegis(), str(projet / "PROJECT_SPEC.md"), "x")

        assert "Lis-le" in resultat.reason

    def test_y_ajouter_est_refuse_aussi(self, projet):
        resultat = file_tools.append(
            _Aegis(), str(projet / "PROJECT_SPEC.md"), "suite")

        assert resultat.success is False
        assert "protege" in resultat.reason.lower()

    def test_le_supprimer_est_refuse(self, projet):
        resultat = file_tools.delete(_Aegis(), str(projet / "PROJECT_SPEC.md"))

        assert resultat.success is False
        assert (projet / "PROJECT_SPEC.md").exists()

    def test_le_deplacer_est_refuse(self, projet):
        """Déplacer un cahier le fait disparaître de là où tout le monde le
        cherche — c'est une destruction avec un pas de plus."""
        resultat = file_tools.move(
            _Aegis(), str(projet / "PROJECT_SPEC.md"), str(projet / "vieux.md"))

        assert resultat.success is False
        assert (projet / "PROJECT_SPEC.md").exists()

    def test_ecrire_par_dessus_via_un_deplacement_aussi(self, projet):
        """La destination compte autant que la source."""
        resultat = file_tools.move(
            _Aegis(), str(projet / "libre.py"), str(projet / "PROJECT_SPEC.md"))

        assert resultat.success is False


class TestCeQuiResteLibre:
    def test_un_fichier_ordinaire_s_ecrit(self, projet):
        """La protection vise trois documents, pas le workspace."""
        resultat = file_tools.propose_write(
            _Aegis(), str(projet / "src" / "a.py"), "y = 2\n")

        assert resultat.applied is True
        assert (projet / "src" / "a.py").read_text(encoding="utf-8") == "y = 2\n"

    def test_sans_liste_rien_n_est_protege(self, tmp_path):
        """Un workspace sans déclaration se comporte comme avant : cette
        protection ne s'invite pas là où personne ne l'a demandée."""
        (tmp_path / "PROJECT_SPEC.md").write_text("a", encoding="utf-8")

        resultat = file_tools.propose_write(
            _Aegis(), str(tmp_path / "PROJECT_SPEC.md"), "b")

        assert resultat.applied is True

    def test_les_commentaires_de_la_liste_ne_protegent_rien(self, projet):
        """Une ligne `#` est une explication, pas un chemin."""
        assert file_tools._est_protege(str(projet / "# commentaire")) is False


class TestOuLaProtectionEstPosee:
    def test_elle_est_dans_file_tools_pas_dans_l_adaptateur(self):
        """Le serveur MCP appelle `file_tools` directement (server.py:252).
        Une protection posée dans `workspace_chat_tools` laisserait cette
        porte ouverte — c'est exactement le genre de second chemin
        d'écriture qui a coûté trois correctifs sur les chemins."""
        from pathlib import Path

        source = Path("backend/tools/file_tools.py").read_text(encoding="utf-8")

        assert source.count("_est_protege(") >= 6, (
            "chaque opération destructrice doit consulter la liste")

    def test_la_liste_est_relue_a_chaque_appel(self, projet):
        """Comme le niveau d'autonomie : un réglage de sécurité qui exige un
        redémarrage finit par ne jamais changer."""
        chemin = str(projet / "libre.py")
        assert file_tools._est_protege(chemin) is False

        liste = projet / file_tools.FICHIER_PROTEGES
        liste.write_text("libre.py\n", encoding="utf-8")

        assert file_tools._est_protege(chemin) is True
