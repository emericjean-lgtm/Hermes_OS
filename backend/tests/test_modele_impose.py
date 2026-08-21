"""L'operateur doit pouvoir trancher tant que le routeur ne sait pas (HOS-144).

Le routeur choisit sur des profils **vides** : `task_scores={}`,
`benchmark_score=0.0`, `total_runs=0` pour les sept modeles du catalogue.
Il retient donc invariablement le plus petit, `lfm2.5-2.6b-125k`, note
`code 28` — pour « rediger une section » comme pour « ecrire les tests
unitaires du module auth ».

Mesure du 2026-08-21, trois deroules de cahier consecutifs : ce modele n'a
jamais ecrit dans le workspace. Ses seules tentatives visaient
`/home/user/skills/skills360-industry/SKILL.md`, un chemin POSIX qui
n'existe pas sur cette machine. Il ne travaillait pas sur la tache : il
inventait un systeme.

`HERMES_MISSION_MODEL` n'est donc pas un reglage de confort. C'est la seule
facon actuelle de confier une campagne a un modele capable, et il est nomme
comme le contournement qu'il est — la vraie correction est de charger les
scores mesures du catalogue dans les profils du routeur.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import RealTaskExecutor, modele_impose


@pytest.fixture
def executeur():
    """Un executeur ou tout modele est juge capable, pour isoler la seule
    regle que ces tests mesurent : qui du routeur ou de l'operateur decide."""
    return RealTaskExecutor(chat=lambda **_: None,
                            agentic_capable_for=lambda m: True)


class TestQuandRienNEstImpose:
    def test_le_choix_du_routeur_passe(self, executeur, monkeypatch):
        monkeypatch.delenv("HERMES_MISSION_MODEL", raising=False)

        assert executeur._agentic_model("ornith-9b-256k") == "ornith-9b-256k"

    @pytest.mark.parametrize("valeur", ["", "   "])
    def test_une_valeur_vide_n_impose_rien(self, monkeypatch, valeur):
        monkeypatch.setenv("HERMES_MISSION_MODEL", valeur)

        assert modele_impose() == ""


class TestQuandLOperateurTranche:
    def test_son_choix_prime_sur_le_routeur(self, executeur, monkeypatch):
        monkeypatch.setenv("HERMES_MISSION_MODEL", "gpt-oss-20b-64k")

        assert executeur._agentic_model("lfm2.5-2.6b-125k") == "gpt-oss-20b-64k"

    def test_la_substitution_est_journalisee(self, executeur, monkeypatch,
                                             caplog):
        """Un modele qui change sans que rien ne le dise rend un rapport de
        mission intracable — on ne saurait plus qui a fait le travail."""
        import logging

        monkeypatch.setenv("HERMES_MISSION_MODEL", "gpt-oss-20b-64k")

        with caplog.at_level(logging.INFO):
            executeur._agentic_model("lfm2.5-2.6b-125k")

        assert "gpt-oss-20b-64k" in caplog.text
        assert "lfm2.5-2.6b-125k" in caplog.text, (
            "le choix ecarte doit apparaitre, sinon la trace ne dit pas ce "
            "qui a ete remplace")


class TestCeQueLImpositionNeContournePas:
    """Imposer un modele qui ne sait pas piloter la boucle d'outils
    produirait une mission qui rapporte un succes sans rien accomplir — le
    defaut que tout ce travail existe pour supprimer."""

    def test_un_modele_incapable_est_quand_meme_substitue(self, monkeypatch):
        executeur = RealTaskExecutor(
            chat=lambda **_: None,
            agentic_capable_for=lambda m: m != "un-modele-incapable")
        monkeypatch.setenv("HERMES_MISSION_MODEL", "un-modele-incapable")

        retenu = executeur._agentic_model("ornith-9b-256k")

        assert retenu != "un-modele-incapable"
