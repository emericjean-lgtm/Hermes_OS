"""Écrire des fichiers ne suffit pas : ils doivent tenir debout (HOS-119).

Mesuré sur un cahier des charges réduit : la mission a produit un module
correct, ses tests et sa documentation — **et les tests ne passaient pas**.
Elle avait nommé le fichier `calculatrice.py` en important `calculator`.
Le rapport annonçait 6 tâches sur 6 réussies.

`MissionVerification` répondait à « le workspace a-t-il changé ? ». Oui,
six fois. Elle ne répondait pas à « ce qui a été produit tient-il debout ? »
— alors que `verification_run` était branché depuis HOS-116.
"""
from __future__ import annotations

import pytest

from backend.mission.runner_applicable import runner_pour
from backend.mission.verification import MissionVerification, WorkspaceDiff


def _verif(**champs) -> MissionVerification:
    base = {
        "mission_id": "m1",
        "reported_success": True,
        "workspace": "C:/ws",
        "changes": WorkspaceDiff(created=["a.py"]),
    }
    return MissionVerification(**{**base, **champs})


class TestLesTroisEtatsNeSeConfondentPas:
    def test_aucun_verdict_n_est_pas_un_echec(self):
        """`None` veut dire « on n'a pas mesuré ». Le lire comme un échec
        marquerait en faute toute mission sans tests applicables."""
        assert _verif(tests=None).tests_echouent is False

    def test_un_runner_qui_n_a_pas_tourne_n_est_pas_un_echec(self):
        """Refusé par Aegis, dépendance absente : on ne conclut pas de ce
        qu'on n'a pas mesuré."""
        verif = _verif(tests={"ran": False, "reason": "require_human_validation"})

        assert verif.tests_echouent is False

    def test_des_tests_qui_echouent_sont_un_echec(self):
        verif = _verif(tests={"ran": True, "passed": False, "runner": "pytest"})

        assert verif.tests_echouent is True

    def test_des_tests_qui_passent_ne_le_sont_pas(self):
        verif = _verif(tests={"ran": True, "passed": True, "runner": "pytest"})

        assert verif.tests_echouent is False


class TestLEffetSurLeVerdict:
    def test_des_fichiers_ecrits_et_des_tests_qui_passent_sont_verifies(self):
        assert _verif(tests={"ran": True, "passed": True}).verified is True

    def test_des_fichiers_ecrits_mais_des_tests_qui_echouent_ne_le_sont_pas(self):
        """Le cas mesuré. Écrire est nécessaire, ça n'a jamais suffi."""
        verif = _verif(tests={"ran": True, "passed": False})

        assert verif.verified is False
        assert verif.contradicted is True

    def test_une_contradiction_declenche_la_meme_reprise(self):
        """Même famille de mensonge, constatée par un autre instrument :
        elle doit donc emprunter le chemin de reprise déjà construit."""
        from backend.mission.retry_policy import decide

        verif = _verif(tests={"ran": True, "passed": False})
        decision = decide(verif.as_dict(), objective="écrire le module")

        assert decision.should_retry is True

    def test_un_workspace_intact_reste_contredit_sans_tests(self):
        """L'ancien cas ne bouge pas."""
        verif = _verif(changes=WorkspaceDiff(), tests=None)

        assert verif.contradicted is True

    def test_une_mission_en_echec_n_est_jamais_dite_contredite(self):
        verif = _verif(reported_success=False, tests={"ran": True, "passed": False})

        assert verif.contradicted is False


class TestLeRunnerApplicable:
    def test_un_dossier_avec_des_tests_python_propose_pytest(self, tmp_path):
        """Un dossier fraîchement produit par une mission écrit
        `test_x.py` avant d'écrire `pytest.ini`."""
        (tmp_path / "test_calculatrice.py").write_text("", encoding="utf-8")

        assert runner_pour(str(tmp_path)) == "pytest"

    def test_un_projet_javascript_propose_npm(self, tmp_path):
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")

        assert runner_pour(str(tmp_path)) == "npm_test"

    def test_un_dossier_sans_marque_ne_propose_rien(self, tmp_path):
        """Et surtout pas `pytest` par défaut : le lancer sur un projet qui
        n'est pas Python produirait un faux échec, ce qui coûte aussi cher
        qu'un faux succès — cinq des huit défauts de mesure de ce dépôt
        étaient des échecs imaginaires."""
        (tmp_path / "LISEZMOI.md").write_text("bonjour", encoding="utf-8")

        assert runner_pour(str(tmp_path)) is None

    def test_un_dossier_inexistant_ne_propose_rien(self, tmp_path):
        assert runner_pour(str(tmp_path / "absent")) is None
