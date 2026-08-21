"""La continuité porte sur le projet, pas sur la mission (HOS-141).

`derouler_cahier.py` lance les 26 sections d'un cahier comme autant
d'objectifs successifs **sur le même dossier**. Chaque objectif devient une
mission distincte : une session par mission, c'était donc une session par
section — et la section 4 ignorait tout de ce qu'avait fait la section 3.

Le harnais corrigeait l'amnésie entre les tâches d'une section et la
laissait intacte entre les sections. Or c'est entre les sections qu'elle
coûte le plus : le mesuré est une profondeur moyenne de 4,4 sections sur
neuf lancements, pour un cahier qui en compte 26.

Grouper par projet donne la continuité à toute la campagne. Deux missions
concurrentes sur un même projet partagent alors leur session : leurs tours
restent sérialisés par le verrou de session, et travailler sur un workspace
en sachant ce qu'une autre mission y a fait vaut mieux que l'ignorer.
"""
from __future__ import annotations

import pytest

from backend.ral.adapters.sessions_de_mission import (
    cle_de_session,
    porte_sur_une_mission_seule,
)


class TestSurQuoiPorteLaContinuite:
    def test_le_projet_prime_sur_la_mission(self):
        """Le cas du cahier : 26 missions, un seul projet."""
        section3 = cle_de_session({"project_id": "p-1", "mission_id": "m-3"})
        section4 = cle_de_session({"project_id": "p-1", "mission_id": "m-4"})

        assert section3 == section4, (
            "deux sections d'un même cahier doivent partager leur session")

    def test_sans_projet_on_retombe_sur_la_mission(self):
        """Une mission isolée n'a rien à partager avec personne."""
        assert cle_de_session({"mission_id": "m-9"}) == "mission:m-9"

    def test_deux_projets_ne_se_melangent_pas(self):
        assert (cle_de_session({"project_id": "p-1"})
                != cle_de_session({"project_id": "p-2"}))

    def test_sans_rien_il_n_y_a_pas_de_cle(self):
        """Pas de clé, pas de harnais : l'appelant retombe sur le mode
        jetable plutôt que d'ouvrir une session que rien n'identifie."""
        assert cle_de_session({}) == ""
        assert cle_de_session({"project_id": "  ", "mission_id": ""}) == ""

    def test_les_espaces_ne_font_pas_une_cle(self):
        assert cle_de_session({"project_id": " p-1 "}) == "projet:p-1"


class TestQuiPeutFermer:
    """Fermer une session de projet à la fin d'une mission jetterait le
    contexte juste avant la section suivante — l'amnésie qu'on corrige,
    réintroduite par la porte de service."""

    @pytest.mark.parametrize("ctx,fermable", [
        ({"mission_id": "m-1"}, True),
        ({"project_id": "p-1", "mission_id": "m-1"}, False),
    ])
    def test_seule_une_session_de_mission_se_ferme_avec_elle(self, ctx, fermable):
        assert porte_sur_une_mission_seule(cle_de_session(ctx)) is fermable
