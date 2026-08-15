"""Un livrable ne s'écrit pas deux fois (HOS-119).

Mesuré sur un cahier des charges de trois livrables : **six fichiers**.
Chacun existait à la racine du workspace *et* dans un sous-dossier
répétant le nom de ce workspace.

    ./calculatrice.py        ./cahier_zkfzqhqu/calculatrice.py

Le modèle connaît le chemin de son workspace et le préfixe parfois — un
réflexe raisonnable. Le join le rejoignait à la racine et fabriquait un
dossier fantôme. Personne ne sait alors lequel des deux fait foi, et une
relecture de vérification peut confirmer le mauvais.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.tools.workspace_chat_tools import resolve_in_project


@pytest.fixture
def espace(tmp_path):
    racine = tmp_path / "cahier_abc123"
    racine.mkdir()
    return racine


class TestLePrefixeRedondant:
    def test_le_nom_du_workspace_en_tete_est_retire(self, espace):
        resolu = resolve_in_project(str(espace), "cahier_abc123/calculatrice.py")

        assert Path(resolu) == espace / "calculatrice.py"

    def test_un_chemin_deja_relatif_est_inchange(self, espace):
        resolu = resolve_in_project(str(espace), "calculatrice.py")

        assert Path(resolu) == espace / "calculatrice.py"

    def test_les_deux_ecritures_designent_le_meme_fichier(self, espace):
        """C'est tout l'objet : le modèle peut hésiter entre les deux
        formes, elles ne doivent plus produire deux fichiers."""
        avec = resolve_in_project(str(espace), "cahier_abc123/LISEZMOI.md")
        sans = resolve_in_project(str(espace), "LISEZMOI.md")

        assert avec == sans

    def test_le_prefixe_est_retire_meme_en_profondeur(self, espace):
        resolu = resolve_in_project(str(espace), "cahier_abc123/src/module.py")

        assert Path(resolu) == espace / "src" / "module.py"


class TestCeQuiNeDoitPasChanger:
    def test_un_sous_dossier_de_meme_nom_plus_loin_est_conserve(self, espace):
        """Seul le premier segment est retiré. Un projet qui contient
        légitimement `src/cahier_abc123/` garde son arborescence."""
        resolu = resolve_in_project(str(espace), "src/cahier_abc123/module.py")

        assert Path(resolu) == espace / "src" / "cahier_abc123" / "module.py"

    def test_un_fichier_portant_le_nom_du_workspace_est_conserve(self, espace):
        """`cahier_abc123` seul est un *fichier*, pas un préfixe : le
        retirer effacerait la cible."""
        resolu = resolve_in_project(str(espace), "cahier_abc123")

        assert Path(resolu) == espace / "cahier_abc123"

    def test_un_chemin_absolu_hors_racine_reste_intact(self, espace):
        """La frontière de sécurité ne bouge pas : Aegis doit voir le chemin
        tel qu'il a été demandé pour le refuser explicitement, pas une
        version réinterprétée."""
        dehors = r"C:\Windows\System32\drivers\etc\hosts"

        assert resolve_in_project(str(espace), dehors) == dehors

    def test_un_chemin_absolu_dans_la_racine_est_normalise(self, espace):
        cible = espace / "calculatrice.py"

        assert Path(resolve_in_project(str(espace), str(cible))) == cible
