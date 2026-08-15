"""Un `success: True` ne doit plus masquer un verdict non mesuré (HOS-121).

L'incident, mesuré sur l'essai Skills360 : la mission a rapporté
`success: True, 7/7`, sur un livrable dont les tests ne compilaient même
pas. Le filet de HOS-119 avait pourtant répondu correctement :

    {"ran": false, "runner": "pytest", "passed": false, "exit_code": null,
     "reason": "verification_run needs autonomy level 'high' to auto-allow;
                current level is 'medium'."}

`config/security.yaml` livre `autonomy_level: medium` et `verification_run`
exige `high` : le filet est **inerte au niveau par défaut**. L'instrument
était honnête — il disait « je n'ai pas mesuré », pas « ça passe ». C'est le
rapport d'objectif autonome qui ne le répétait pas : il ne portait que
`success`, et rien d'autre.

La correction n'est pas de baisser le seuil de sécurité — faire tourner le
code d'un projet tiers sans surveillance au niveau par défaut est une vraie
décision, prise ailleurs. C'est de faire remonter les **trois états** déjà
distingués en interne.
"""
from __future__ import annotations

from backend.autonomous.autonomous_models import AutonomousReport
from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator


class TestLesTroisEtats:
    def test_sans_verification_la_qualite_est_non_mesuree(self):
        """Et surtout pas « vérifiée ». C'est tout l'incident."""
        rapport = AutonomousReport(goal_id="g", success=True)

        assert rapport.qualite == "non_mesuree"
        assert rapport.to_dict()["qualite"] == "non_mesuree"

    def test_le_cas_exact_de_l_essai_skills360(self):
        """Vérification tentée, tests non lancés faute de niveau
        d'autonomie : c'est « non mesurée », pas « vérifiée »."""
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={
                "verified": False, "contradicted": False, "measured": True,
                "tests": {"ran": False, "runner": "pytest", "passed": False,
                          "reason": "verification_run needs autonomy level "
                                    "'high' to auto-allow; current level is "
                                    "'medium'."},
            })

        assert rapport.qualite == "non_mesuree"

    def test_des_tests_en_echec_contredisent_le_succes_annonce(self):
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "measured": True,
                          "tests": {"ran": True, "passed": False,
                                    "exit_code": 1}})

        assert rapport.qualite == "contredite", (
            "des tests qui échouent doivent l'emporter sur un workspace "
            "qui a changé")

    def test_un_workspace_contredit_l_est_aussi(self):
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": False, "contradicted": True,
                          "measured": True})

        assert rapport.qualite == "contredite"

    def test_verifiee_n_est_dit_que_quand_ca_l_est(self):
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "contradicted": False,
                          "measured": True,
                          "tests": {"ran": True, "passed": True,
                                    "exit_code": 0}})

        assert rapport.qualite == "verifiee"


class TestPartielle:
    """Le défaut de ce champ lui-même, trouvé en mesurant (HOS-122).

    Le quatrième lancement de l'essai Skills360 a rendu
    `qualite: "verifiee"` au-dessus de

        tests: {"ran": false, "reason": "verification_run needs autonomy
                level 'high' to auto-allow; current level is 'medium'."}

    Le disque avait changé, le manifeste tenait — mais les tests du
    livrable n'avaient pas tourné. On avait remplacé un `success` trompeur
    par un `verifiee` qui l'était tout autant.
    """

    def test_le_cas_exact_du_quatrieme_lancement(self):
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={
                "verified": True, "contradicted": False, "measured": True,
                "manifeste": {"declares": 3, "manquants": [], "tenu": True},
                "tests": {"ran": False, "runner": "pytest", "passed": False,
                          "reason": "verification_run needs autonomy level "
                                    "'high' to auto-allow; current level is "
                                    "'medium'."},
            })

        assert rapport.qualite == "partielle", (
            "le manifeste tenu et le disque changé sont de vraies mesures — "
            "elles ne valent simplement pas les tests du livrable")

    def test_partielle_n_est_pas_non_mesuree(self):
        """Ce qui a été constaté l'a été. Le rabattre sur « non mesurée »
        jetterait une information vraie."""
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "measured": True,
                          "manifeste": {"manquants": [], "tenu": True}})

        assert rapport.qualite == "partielle"

    def test_des_tests_qui_passent_font_basculer_en_verifiee(self):
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "measured": True,
                          "manifeste": {"manquants": [], "tenu": True},
                          "tests": {"ran": True, "passed": True}})

        assert rapport.qualite == "verifiee"


class TestLeManifeste:
    def test_un_livrable_promis_et_absent_contredit(self):
        """Écrire six fichiers dont aucun n'est celui qu'on avait promis
        n'est pas avoir fait le travail (HOS-122)."""
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": False, "measured": True,
                          "manifeste": {"declares": 3,
                                        "manquants": ["identity_model.py"],
                                        "tenu": False}})

        assert rapport.qualite == "contredite"

    def test_un_manifeste_tenu_ne_suffit_pas_a_dire_verifiee(self):
        """Les fichiers promis existent ; rien ne dit qu'ils fonctionnent."""
        rapport = AutonomousReport(
            goal_id="g", success=True,
            verification={"verified": True, "measured": True,
                          "manifeste": {"declares": 3, "manquants": [],
                                        "tenu": True}})

        assert rapport.qualite != "verifiee"


class TestLeRapportPorteLesDeux:
    def test_success_et_qualite_voyagent_ensemble(self):
        """Séparés, `success` seul a menti une fois. La paire est
        l'information ; l'un sans l'autre ne l'est pas."""
        rendu = AutonomousReport(goal_id="g", success=True).to_dict()

        assert rendu["success"] is True
        assert "qualite" in rendu
        assert "verification" in rendu


class TestLaSourceDuVerdict:
    """Le verdict vient de la mission, là où `GraphExecutor` l'a écrit."""

    def test_il_est_lu_sur_les_metadonnees_de_la_mission(self):
        class _Mission:
            metadata = {"verification": {"verified": True, "measured": True}}

        lu = AutonomousOrchestrator._verification_de(_Mission())

        assert lu == {"verified": True, "measured": True}

    def test_sans_mission_dag_rien_n_est_invente(self):
        """Un objectif exécuté hors du pipeline DAG n'a pas de verdict, et
        le rapport doit le dire par une absence — pas par un succès."""
        assert AutonomousOrchestrator._verification_de(None) is None

    def test_une_mission_sans_verdict_rend_None(self):
        class _Mission:
            metadata: dict = {}

        assert AutonomousOrchestrator._verification_de(_Mission()) is None

    def test_un_verdict_malforme_ne_passe_pas_pour_un_verdict(self):
        class _Mission:
            metadata = {"verification": "oui"}

        assert AutonomousOrchestrator._verification_de(_Mission()) is None
