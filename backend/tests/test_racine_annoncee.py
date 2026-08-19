"""Le modèle doit savoir où il est (HOS-130).

Mesuré en traçant chaque résolution de chemin d'une seule section : sur
**145 résolutions, 101 pointaient hors du workspace — 69 %**. Le modèle
essayait successivement :

    /home/user/<dossier>     49 fois
    des formes Windows       36 fois
    /workspace               17 fois
    /                         7 fois

Il **devinait**, parce que rien ne lui disait jamais où il se trouvait. Ni
le brief de la section, ni le message de refus.

Aegis refusait correctement, mais un refus qui dit « accès interdit » sans
dire « voici la racine, donne un chemin relatif » laisse le modèle deviner
une racine de plus. Deux tiers de son budget d'outils partaient là — et
c'est le terrain sur lequel l'arbre fantôme se forme.
"""
from __future__ import annotations

import pytest

from backend.mission.programme import Section, brief_de_section
from backend.tools.workspace_chat_tools import (
    hors_du_workspace, resolve_in_project,
)

RACINE = r"C:\Users\emeri\Skill360-nuit"


class TestLeRefusEstActionnable:
    @pytest.mark.parametrize("chemin", [
        "/home/user/Skill360-nuit/models/position.py",
        "/workspace/models/position.py",
        "/etc/passwd",
    ])
    def test_une_racine_inventee_recoit_la_vraie(self, chemin):
        message = hors_du_workspace(RACINE, chemin,
                                    resolve_in_project(RACINE, chemin))

        assert message, "un chemin hors workspace doit être signalé"
        assert RACINE in message, "le refus doit nommer la vraie racine"
        assert "relatif" in message

    def test_il_dit_qu_aucune_ecriture_n_a_eu_lieu(self):
        """Sans ça le modèle peut croire que l'écriture est passée et
        enchaîner — c'est la famille de mensonge que ce dépôt traque."""
        message = hors_du_workspace(RACINE, "/home/user/x.py",
                                    resolve_in_project(RACINE, "/home/user/x.py"))

        assert "Aucune ecriture" in message

    def test_un_chemin_relatif_normal_ne_declenche_rien(self):
        chemin = "src/models/position.py"

        assert hors_du_workspace(RACINE, chemin,
                                 resolve_in_project(RACINE, chemin)) == ""

    def test_la_frontiere_de_securite_ne_bouge_pas(self):
        """On change ce qu'on dit d'un refus, pas ce qui est refusé :
        `resolve_in_project` rend toujours le chemin hors racine tel quel,
        pour qu'Aegis le rejette explicitement."""
        resolu = resolve_in_project(RACINE, "/etc/passwd")

        assert "Skill360-nuit" not in resolu


class TestLeBriefAnnonceLaRacine:
    def test_la_racine_est_nommee_quand_elle_est_connue(self):
        brief = brief_de_section(Section(11, "POSITIONS", "corps"),
                                 nom_du_cahier="SPEC.md", racine=RACINE)

        assert RACINE in brief
        assert "relatifs" in brief

    def test_la_forme_attendue_est_montree(self):
        """Une consigne abstraite se suit moins bien qu'une forme montrée.

        L'exemple était `src/models/x.py` — et la mission a créé ce
        fichier (HOS-131). C'est désormais un gabarit qu'on ne peut
        pas créer tel quel."""
        brief = brief_de_section(Section(11, "T", "corps"),
                                 nom_du_cahier="SPEC.md", racine=RACINE)

        assert "<dossier>/<fichier>" in brief
        assert "/home/" in brief, "nommer la forme fautive mesurée"

    def test_sans_racine_connue_rien_n_est_affirme(self):
        """Un brief qui annoncerait une racine vide serait pire que muet."""
        brief = brief_de_section(Section(11, "T", "corps"),
                                 nom_du_cahier="SPEC.md")

        assert "racine de ce dossier (" not in brief


class TestUnExempleNEstPasUneCommande:
    """Le défaut que j'ai introduit en corrigeant le précédent (HOS-131).

    La première version du brief disait :

        Écris `src/models/x.py`, jamais `/home/user/...`

    Mesuré au lancement suivant : la mission a créé **`src/models/x.py`**,
    un module de 40 lignes, à côté de ses vrais livrables. Elle a lu
    l'exemple comme une consigne — ce qui est une lecture raisonnable de
    « Écris `src/models/x.py` ».

    Un exemple dans un prompt doit être impossible à confondre avec un
    livrable. La forme `<dossier>/<fichier>` ne peut pas être créée telle
    quelle.
    """

    def test_aucun_chemin_plausible_n_est_donne_en_exemple(self):
        brief = brief_de_section(Section(6, "T", "corps"),
                                 nom_du_cahier="SPEC.md", racine=RACINE)

        assert "src/models/x.py" not in brief, (
            "un chemin qui ressemble à un livrable finit par en devenir un")

    def test_la_forme_attendue_reste_montree(self):
        """Retirer l'exemple entièrement serait revenir au défaut d'avant :
        c'est lui qui a fait disparaître l'arbre fantôme."""
        brief = brief_de_section(Section(6, "T", "corps"),
                                 nom_du_cahier="SPEC.md", racine=RACINE)

        assert "<dossier>/<fichier>" in brief

    def test_les_racines_fautives_mesurees_sont_toujours_nommees(self):
        brief = brief_de_section(Section(6, "T", "corps"),
                                 nom_du_cahier="SPEC.md", racine=RACINE)

        assert "/home/" in brief and "/workspace" in brief
