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


class TestLaTableParTypeDeTache:
    """54 taches, un seul modele (HOS-150).

    Mesure sur une campagne complete : le routeur proposait invariablement
    le plus petit (54 fois sur 54), et l'imposition d'un modele unique
    remplacait un uniforme par un autre. Aucune tache n'a jamais recu un
    modele choisi pour elle.

    Or les couts different d'un ordre de grandeur : gpt-oss-20b rend 9/9 au
    banc de code a 92,7 tok/s, Qwen3.8-27B rend 8/9 a 8,7 tok/s. Confier a
    ce dernier la redaction d'un fichier Markdown coute dix fois le temps
    pour rien.
    """

    TABLE = ("code_generation=qwen38-27b-64k,"
             "code_review=qwen38-27b-64k,"
             "*=gpt-oss-20b-64k")

    def test_le_code_va_au_modele_fort(self, executeur, monkeypatch):
        monkeypatch.setenv("HERMES_MISSION_MODEL", self.TABLE)

        for tt in ("code_generation", "code_review"):
            assert executeur._agentic_model("lfm2.5-2.6b-125k",
                                            tt) == "qwen38-27b-64k"

    def test_le_reste_va_au_modele_rapide(self, executeur, monkeypatch):
        monkeypatch.setenv("HERMES_MISSION_MODEL", self.TABLE)

        for tt in ("documentation", "reasoning", "analysis", ""):
            assert executeur._agentic_model("lfm2.5-2.6b-125k",
                                            tt) == "gpt-oss-20b-64k"

    def test_une_regle_precise_prime_sur_le_joker(self, executeur,
                                                  monkeypatch):
        """Sans cet ordre, `*` rendrait la table inutile."""
        monkeypatch.setenv("HERMES_MISSION_MODEL",
                           "*=petit,code_generation=grand")

        assert executeur._agentic_model("x", "code_generation") == "grand"
        assert executeur._agentic_model("x", "documentation") == "petit"

    def test_sans_joker_un_type_absent_n_impose_rien(self, executeur,
                                                     monkeypatch):
        """Le routeur reprend alors la main, plutot qu'un modele choisi au
        hasard dans la table."""
        monkeypatch.setenv("HERMES_MISSION_MODEL",
                           "code_generation=qwen38-27b-64k")

        assert executeur._agentic_model("ornith-9b-256k",
                                        "documentation") == "ornith-9b-256k"

    def test_un_nom_seul_vaut_toujours_pour_tout(self, executeur, monkeypatch):
        """L'ecriture d'avant HOS-150 ne doit pas changer de sens."""
        monkeypatch.setenv("HERMES_MISSION_MODEL", "gpt-oss-20b-64k")

        for tt in ("code_generation", "documentation", ""):
            assert executeur._agentic_model("x", tt) == "gpt-oss-20b-64k"

    def test_une_entree_malformee_est_ignoree_sans_casser(self, monkeypatch):
        monkeypatch.setenv("HERMES_MISSION_MODEL",
                           "=vide,code_generation=,ok=modele,,*=repli")

        assert modele_impose("ok") == "modele"
        assert modele_impose("code_generation") == "repli"

    def test_la_table_reste_soumise_a_la_verification_agentique(self,
                                                               monkeypatch):
        """Imposer par type ne contourne pas plus la capacite qu'imposer par
        nom : un modele incapable de piloter la boucle d'outils produirait
        une mission qui rapporte un succes sans rien accomplir."""
        executeur = RealTaskExecutor(
            chat=lambda **_: None,
            agentic_capable_for=lambda m: m != "un-incapable")
        monkeypatch.setenv("HERMES_MISSION_MODEL",
                           "code_generation=un-incapable,*=gpt-oss-20b-64k")

        retenu = executeur._agentic_model("ornith-9b-256k", "code_generation")

        assert retenu != "un-incapable"
