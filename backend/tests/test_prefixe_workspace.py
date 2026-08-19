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


class TestUnCheminAbsoluAmputeDeSonLecteur:
    """L'incident du 2026-08-16, mesuré sur deux missions consécutives.

    Le modèle a écrit :

        Users/emeri/AppData/Local/Temp/memoire_X/identity_model.py

    — le chemin absolu de son workspace, **amputé de sa lettre de
    lecteur**. Sous Windows, `Path.is_absolute()` rend `False` là-dessus :
    sans drive, un chemin est « rooted » mais pas absolu. La branche des
    chemins absolus ne le voyait donc pas, et la règle « retirer un segment
    s'il égale le nom du dossier racine » ne reconnaissait pas `Users`.

    Résultat sur le disque : six niveaux de dossiers recréés **dans** le
    workspace, avec un double de chaque livrable dedans — et le double de
    `identity_model.py` faisait 424 octets contre 1737 pour l'original.
    Une relecture de vérification pouvait tomber sur le mauvais.
    """

    def test_le_chemin_complet_ampute_revient_a_la_racine(self, tmp_path):
        racine = tmp_path / "memoire_X"
        racine.mkdir()
        parties = "/".join(racine.parts[1:])  # sans la lettre de lecteur

        resolu = resolve_in_project(str(racine), f"{parties}/identity_model.py")

        assert Path(resolu) == racine / "identity_model.py"

    def test_un_prefixe_partiel_aussi(self, tmp_path):
        """Le modèle n'ampute pas toujours au même endroit."""
        racine = tmp_path / "memoire_X"
        racine.mkdir()
        deux = "/".join(racine.parts[-2:])

        resolu = resolve_in_project(str(racine), f"{deux}/a.py")

        assert Path(resolu) == racine / "a.py"

    def test_le_cas_d_un_seul_segment_ne_change_pas(self, tmp_path):
        """La règle d'origine (HOS-119) en est l'instance k=1."""
        racine = tmp_path / "cahier_zk"
        racine.mkdir()

        resolu = resolve_in_project(str(racine), "cahier_zk/calculatrice.py")

        assert Path(resolu) == racine / "calculatrice.py"

    def test_une_arborescence_legitime_est_preservee(self, tmp_path):
        """Le garde-fou : un projet qui contient réellement un sous-dossier
        portant le nom de sa racine garde sa structure, parce que le
        préfixe retiré doit reproduire la **fin** du chemin de la racine."""
        racine = tmp_path / "memoire_X"
        racine.mkdir()

        resolu = resolve_in_project(str(racine), "src/memoire_X/x.py")

        assert Path(resolu) == racine / "src" / "memoire_X" / "x.py"


class TestLaCasseDesCheminsWindows:
    """Le correctif du matin était incomplet, et deux essais l'ont montré.

    `_sans_prefixe_redondant` comparait ses segments avec `==`. Les chemins
    Windows ne sont pas sensibles à la casse : le modèle a écrit une
    variante en minuscules, aucun segment ne correspondait, et l'arbre
    fantôme est réapparu **après** la correction — six niveaux de dossiers
    dans le workspace, avec un double de chaque livrable.

    Reproduit avant d'être corrigé : sur quatre formes écrites de bout en
    bout par `execute_workspace_tool`, trois atterrissaient à la racine et
    seule la variante en minuscules créait l'arborescence.
    """

    def test_le_prefixe_en_minuscules_est_reconnu(self, tmp_path):
        racine = tmp_path / "MemoireX"
        racine.mkdir()
        parties = "/".join(p.lower() for p in racine.parts[1:])

        resolu = resolve_in_project(str(racine), f"{parties}/b.py")

        assert Path(resolu) == racine / "b.py"

    def test_le_prefixe_en_majuscules_aussi(self, tmp_path):
        racine = tmp_path / "MemoireX"
        racine.mkdir()
        parties = "/".join(p.upper() for p in racine.parts[1:])

        resolu = resolve_in_project(str(racine), f"{parties}/e.py")

        assert Path(resolu) == racine / "e.py"


class TestLesSegmentsSeComparentCommeLeSystemeDeFichiers:
    """Troisième correctif sur le même défaut, et le premier qui traite la
    cause (HOS-129).

    Après deux correctifs **vérifiés** — le préfixe multi-segments, puis la
    casse — un arbre fantôme de six niveaux est réapparu sur une file de
    26 sections. La forme qui cassait :

        Users/emeri/Skill360-nuit./src/models/auth.model.ts

    Windows **supprime les points et espaces finaux** d'un nom de dossier :
    le segment `Skill360-nuit.` crée bien le dossier `Skill360-nuit`, mais
    ne lui est pas égal comme chaîne. La comparaison voyait deux noms
    différents là où le système de fichiers n'en voit qu'un.

    Les segments sont donc normalisés comme le système les normalise.
    """

    def test_un_point_final_ne_casse_plus_la_reconnaissance(self, tmp_path):
        racine = tmp_path / "memoire_X"
        racine.mkdir()
        parties = "/".join(racine.parts[1:])

        resolu = resolve_in_project(str(racine), f"{parties}./src/a.py")

        assert Path(resolu) == racine / "src" / "a.py"

    def test_un_espace_final_non_plus(self, tmp_path):
        racine = tmp_path / "memoire_X"
        racine.mkdir()
        parties = "/".join(racine.parts[1:])

        resolu = resolve_in_project(str(racine), f"{parties} /src/a.py")

        assert Path(resolu) == racine / "src" / "a.py"

    def test_des_guillemets_autour_du_chemin_non_plus(self, tmp_path):
        """Un modèle en ajoute parfois, par mimétisme avec du JSON."""
        racine = tmp_path / "memoire_X"
        racine.mkdir()
        parties = "/".join(racine.parts[1:])

        resolu = resolve_in_project(str(racine), f'"{parties}/src/a.py')

        assert Path(resolu).parts[-2:] == ("src", "a.py")

    def test_une_arborescence_legitime_survit_toujours(self, tmp_path):
        """Le garde-fou : normaliser plus ne doit pas retirer plus."""
        racine = tmp_path / "memoire_X"
        racine.mkdir()

        resolu = resolve_in_project(str(racine), "src/memoire_X/x.py")

        assert Path(resolu) == racine / "src" / "memoire_X" / "x.py"
