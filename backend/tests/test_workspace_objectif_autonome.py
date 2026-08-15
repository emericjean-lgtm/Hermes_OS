"""Un objectif autonome obtient de vrais outils, ou il refuse (HOS-119).

Mesuré le 2026-08-15 sur un cahier des charges réduit : **6 tâches sur 6
« réussies », 41 secondes d'inférence, zéro fichier écrit**, et un rapport
affirmatif. La cause tenait en une phrase — un `local_path` brut n'est pas
un `project_id`, et `_workspace_project_for` exige un Project *enregistré
et validé*. La résolution rendait `None`, la tâche partait en complétion
simple, et le modèle sommé d'écrire un fichier sans pouvoir le faire a
produit un appel d'outil **en texte** vers un chemin Linux inventé. Ce
texte a été rangé comme résultat et compté comme réussite.

Aucun raisonnement n'aurait trouvé ça : il a fallu lancer un vrai cahier
et regarder le disque.
"""
from __future__ import annotations

import pytest

from backend.projects.project_manager import ValidationStatus


@pytest.fixture
def magasin(tmp_path, monkeypatch):
    from backend.core.config import get_settings
    from backend.projects.store import ProjectStore, get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "projets.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()
    yield ProjectStore(str(tmp_path / "projets.db"))
    get_settings.cache_clear()
    get_project_store.cache_clear()


class TestUnDossierDevientUnProject:
    def test_un_dossier_reel_est_enregistre_et_valide(self, magasin, tmp_path):
        espace = tmp_path / "travail"
        espace.mkdir()

        projet = magasin.ensure_for_path(str(espace))

        assert projet is not None
        assert projet.validation_status == ValidationStatus.VALID.value

    def test_un_dossier_inexistant_ne_donne_pas_de_workspace(self, magasin, tmp_path):
        """Et c'est le point : rendre un Project non validé ici aurait
        rétabli le faux succès sous une autre forme."""
        assert magasin.ensure_for_path(str(tmp_path / "absent")) is None

    def test_le_meme_dossier_ne_cree_pas_deux_projects(self, magasin, tmp_path):
        espace = tmp_path / "travail"
        espace.mkdir()

        premier = magasin.ensure_for_path(str(espace))
        second = magasin.ensure_for_path(str(espace))

        assert premier.id == second.id

    def test_un_chemin_ecrit_autrement_designe_le_meme_project(self, magasin, tmp_path):
        """`C:\\a\\b` et `C:\\a\\.\\b` sont le même dossier. Sans
        normalisation on enregistrerait deux Projects pour un seul dossier,
        et la whitelist d'Aegis grossirait à chaque objectif."""
        espace = tmp_path / "travail"
        espace.mkdir()

        premier = magasin.ensure_for_path(str(espace))
        second = magasin.ensure_for_path(str(tmp_path / "." / "travail"))

        assert premier.id == second.id

    def test_le_dossier_est_revalide_a_chaque_fois(self, magasin, tmp_path):
        """Un dossier autorisé hier peut avoir disparu. Se fier au verdict
        stocké accorderait un accès sur une mesure périmée."""
        espace = tmp_path / "ephemere"
        espace.mkdir()
        assert magasin.ensure_for_path(str(espace)) is not None

        espace.rmdir()

        assert magasin.ensure_for_path(str(espace)) is None


class TestLeRefus:
    """Le choix retenu : mieux vaut un refus lisible qu'un mensonge
    confiant. Un objectif sans dossier, lui, doit continuer de tourner —
    beaucoup n'ont rien à écrire."""

    def test_un_objectif_avec_dossier_mais_sans_project_est_refuse(self):
        from backend.autonomous.autonomous_models import AutonomousGoal
        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

        goal = AutonomousGoal(goal_id="g1", local_path=r"C:\dossier\absent")

        assert AutonomousOrchestrator._workspace_refuse(goal, "") is True

    def test_un_objectif_avec_un_project_valide_passe(self):
        from backend.autonomous.autonomous_models import AutonomousGoal
        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

        goal = AutonomousGoal(goal_id="g1", local_path=r"C:\dossier\reel")

        assert AutonomousOrchestrator._workspace_refuse(goal, "proj-1") is False

    def test_un_objectif_sans_dossier_n_est_jamais_refuse(self):
        """« Analyse cette idée » n'a pas besoin du disque. Lui imposer un
        workspace refuserait du travail parfaitement légitime."""
        from backend.autonomous.autonomous_models import AutonomousGoal
        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator

        goal = AutonomousGoal(goal_id="g1", local_path="")

        assert AutonomousOrchestrator._workspace_refuse(goal, "") is False
