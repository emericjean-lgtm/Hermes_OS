"""Un objectif autonome mène à sa décomposition (HOS-117).

L'orchestrateur construit une vraie mission DAG (`_execute_via_dag`) et la
session en garde l'identifiant — mais rien au-dessus ne l'exposait.
L'objectif était donc un cul-de-sac : compteurs et décisions visibles, la
liste des tâches jamais, alors que `GET /missions/{id}/graph` la rend en
entier.
"""
from __future__ import annotations

import pytest

from backend.autonomous import routes as autonomous_routes


class _Session:
    def __init__(self, mission_id: str):
        self.mission_id = mission_id


class _Engine:
    def __init__(self, goal: dict | None, session: _Session | None):
        self._goal = goal
        self._session = session
        self.sessions_demandees: list[str] = []

    def get_goal(self, goal_id: str):
        return dict(self._goal) if self._goal is not None else None

    def get_session(self, goal_id: str):
        self.sessions_demandees.append(goal_id)
        return self._session


@pytest.fixture(autouse=True)
def _moteur_neuf():
    autonomous_routes.reset_engine()
    yield
    autonomous_routes.reset_engine()


def _avec(engine, monkeypatch):
    monkeypatch.setattr(autonomous_routes, "get_engine", lambda: engine)


class TestLeLienVersLaMission:
    def test_l_objectif_porte_l_identifiant_de_sa_mission(self, monkeypatch):
        moteur = _Engine({"goal_id": "g1"}, _Session("m-42"))
        _avec(moteur, monkeypatch)

        assert autonomous_routes.handle_get_goal("g1")["mission_id"] == "m-42"

    def test_sans_session_le_champ_est_vide_et_non_absent(self, monkeypatch):
        """Une chaîne vide dit « pas encore de mission » ; un champ absent
        obligerait chaque appelant à distinguer « pas de mission » de
        « vieille version du backend »."""
        _avec(_Engine({"goal_id": "g1"}, None), monkeypatch)

        assert autonomous_routes.handle_get_goal("g1")["mission_id"] == ""

    def test_un_objectif_inconnu_reste_None(self, monkeypatch):
        """Et la session n'est même pas demandée : chercher la mission d'un
        objectif qui n'existe pas n'a pas de sens."""
        moteur = _Engine(None, _Session("m-42"))
        _avec(moteur, monkeypatch)

        assert autonomous_routes.handle_get_goal("absent") is None
        assert moteur.sessions_demandees == []

    def test_le_lien_n_est_pas_recopie_sur_le_dataclass(self, monkeypatch):
        """Enrichi à la route, pas ajouté à `AutonomousGoal` : le lien
        appartient à la session, et le dupliquer créerait deux sources pour
        un même fait, qui finiraient par diverger."""
        from backend.autonomous.autonomous_models import AutonomousGoal

        assert "mission_id" not in AutonomousGoal().to_dict()


class TestLeMoteurExpose:
    def test_get_session_delegue_a_l_orchestrateur(self):
        """Sans cette méthode, la route retombait sur un `getattr` de repli
        qui aurait rendu une chaîne vide en silence — un lien mort que rien
        n'aurait signalé."""
        from backend.autonomous.autonomous_engine import AutonomousEngine

        assert hasattr(AutonomousEngine, "get_session")
