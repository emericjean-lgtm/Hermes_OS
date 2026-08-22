"""Le type d'une tache, traduit dans la langue du routeur (HOS-150).

Le planificateur classe en `TaskCategory` — douze valeurs. Le routeur
raisonne en `TaskType` — dix. **Les deux vocabulaires ne se recouvraient que
sur trois mots**, mesure le 2026-08-22 :

    reconnues : analysis, documentation, optimization
    jetees    : design, implementation, testing, deployment, review,
                planning, integration, security, custom

Neuf categories sur douze etaient donc rejetees, et le routeur retombait sur
une inference par mots-cles du titre. `implementation` et `testing`, celles
qui portent le code, etaient du nombre.

L'ironie est dans le code : le commentaire de `_task_type_hint` annonce
transmettre « un signal reel et plus precis que la re-inference par
mots-cles », et cette valeur etait perdue a l'arrivee faute de vocabulaire
commun.
"""
from __future__ import annotations

import pytest

from backend.mission.planner.planner_models import TaskCategory
from backend.model_intelligence.adaptive_router import TaskType
from backend.model_intelligence.correspondance_types import (
    CORRESPONDANCE,
    est_du_code,
    type_du_routeur,
)


class TestLesDeuxVocabulairesSeRejoignent:
    def test_toute_categorie_du_planificateur_est_traduite(self):
        """Une categorie sans traduction retombe sur les mots-cles — c'est
        exactement l'etat qu'on corrige."""
        for categorie in TaskCategory:
            assert type_du_routeur(categorie.value) is not None, (
                f"{categorie.value!r} n'a pas de traduction")

    def test_toute_traduction_est_un_type_que_le_routeur_connait(self):
        """Traduire vers un type inexistant referait exactement le meme
        defaut, une couche plus loin."""
        connus = {t.value for t in TaskType}

        for categorie, traduit in CORRESPONDANCE.items():
            assert traduit in connus, (
                f"{categorie!r} traduit vers {traduit!r}, que le routeur "
                f"ne connait pas")


class TestLesChoixDeTraduction:
    @pytest.mark.parametrize("categorie,attendu", [
        ("implementation", "code_generation"),
        ("testing", "code_generation"),
        ("integration", "code_generation"),
        ("review", "code_review"),
        ("security", "code_review"),
        ("design", "reasoning"),
        ("planning", "reasoning"),
    ])
    def test_les_categories_jetees_ont_desormais_un_sens(self, categorie,
                                                         attendu):
        assert type_du_routeur(categorie) == attendu

    @pytest.mark.parametrize("categorie", ["analysis", "documentation",
                                           "optimization"])
    def test_les_trois_deja_reconnues_ne_changent_pas(self, categorie):
        """Elles fonctionnaient : les traduire autrement changerait un
        comportement qui n'avait pas de defaut."""
        assert type_du_routeur(categorie) == categorie


class TestCeQuOnNeSaitPasTraduire:
    def test_une_categorie_inconnue_rend_none(self):
        """`None` laisse l'inference par mots-cles reprendre la main.
        Rendre `general` remplacerait une inconnue par une affirmation
        fausse — le routeur traiterait « ecris le module d'authentification »
        comme une conversation."""
        assert type_du_routeur("quelque_chose_de_neuf") is None

    @pytest.mark.parametrize("vide", ["", "   ", None])
    def test_une_categorie_absente_aussi(self, vide):
        assert type_du_routeur(vide) is None

    def test_la_casse_et_les_espaces_ne_font_pas_une_inconnue(self):
        assert type_du_routeur("  Implementation  ") == "code_generation"


class TestCeQuiEstDuCode:
    """La question que pose un operateur voulant confier le code a un modele
    plus fort et le reste a un modele rapide."""

    @pytest.mark.parametrize("categorie", ["implementation", "testing",
                                           "integration", "review",
                                           "security"])
    def test_oui(self, categorie):
        assert est_du_code(categorie) is True

    @pytest.mark.parametrize("categorie", ["documentation", "planning",
                                           "design", "analysis", "custom",
                                           "", "inconnue"])
    def test_non(self, categorie):
        assert est_du_code(categorie) is False
