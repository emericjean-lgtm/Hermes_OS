"""Autonomous Engine for Hermes OS (HOS-063).

Central facade that provides the simple API:
- start_goal(pause/resume/cancel)
- get_status()
- generate_report()

Integrates all autonomous subsystems.
"""

from __future__ import annotations

from typing import Any, Callable

from .autonomous_orchestrator import AutonomousOrchestrator


class AutonomousEngine:
    """Central facade for the autonomous agentic core.

    Provides a simple public API while internally orchestrating
    all subsystems (interpreter, decision engine, guard, memory loop).
    """

    def __init__(self, on_event: Callable | None = None,
                 mission_executor: Any = None,
                 mission_planner: Any = None,
                 graph_executor: Any = None) -> None:
        """
        Args:
            mission_executor: the shared task-execution pipeline. Passed straight
                through to the orchestrator so the autonomous surface and the
                ``/missions`` DAG run on one engine instead of each building its
                own — the duplication R-002 P1 removes. When ``None`` the
                orchestrator still builds its own, which keeps direct
                construction working in tests.
            mission_planner: the real Mission Planner (HOS-042), passed
                through so a goal is decomposed into a real DAG (HOS-067)
                instead of one flat task — see AutonomousOrchestrator.
            graph_executor: the real DAG walker (HOS-041), passed through
                alongside ``mission_planner``.
        """
        self._orchestrator = AutonomousOrchestrator(
            on_event=on_event, mission_executor=mission_executor,
            mission_planner=mission_planner, graph_executor=graph_executor,
        )

    @property
    def orchestrator(self) -> AutonomousOrchestrator:
        return self._orchestrator

    def start_goal(self, user_request: str, context: dict | None = None) -> dict:
        goal = self._orchestrator.start_goal(user_request, context)
        return goal.to_dict()

    def pause_goal(self, goal_id: str) -> dict:
        ok = self._orchestrator.pause_goal(goal_id)
        return {"success": ok, "goal_id": goal_id}

    def resume_goal(self, goal_id: str) -> dict:
        ok = self._orchestrator.resume_goal(goal_id)
        return {"success": ok, "goal_id": goal_id}

    def cancel_goal(self, goal_id: str) -> dict:
        """Annuler un objectif.

        `semantique` est dans la réponse parce que le mot « annulé » se
        lit spontanément comme « arrêté maintenant », et que ce n'est pas
        ce qui se produit : un nœud déjà engagé termine. Un opérateur qui
        voit `success: true` et retrouve un agent au travail trente
        secondes plus tard doit pouvoir comprendre pourquoi sans lire le
        code (HOS-252).
        """
        ok = self._orchestrator.cancel_goal(goal_id)
        return {
            "success": ok,
            "goal_id": goal_id,
            "semantique": "aucune tâche nouvelle ne sera engagée ; un nœud "
                          "déjà engagé termine son travail",
        }

    def get_status(self) -> dict:
        return self._orchestrator.get_status()

    def get_goal(self, goal_id: str) -> dict | None:
        goal = self._orchestrator.get_goal(goal_id)
        return goal.to_dict() if goal else None

    def get_session(self, goal_id: str):
        """La session d'exécution d'un objectif, ou None.

        C'est elle qui porte `mission_id` — le lien entre un objectif et la
        mission DAG qu'il exécute réellement. L'orchestrateur l'indexait
        déjà (`_session_by_goal`) mais rien ne l'exposait au-dessus, ce qui
        rendait l'objectif impossible à relier à sa décomposition
        (HOS-117).
        """
        return self._orchestrator.get_session(goal_id)

    def list_goals(self, limit: int = 50) -> list[dict]:
        return [g.to_dict() for g in self._orchestrator.list_goals(limit)]

    def get_timeline(self, goal_id: str) -> dict:
        session = self._orchestrator.get_session(goal_id)
        if session:
            return {"goal_id": goal_id, "timeline": session.timeline, "status": session.status.value}
        return {"goal_id": goal_id, "timeline": [], "status": "not_found"}

    def get_report(self, goal_id: str) -> dict | None:
        report = self._orchestrator.get_report(goal_id)
        return report.to_dict() if report else None

    def generate_report(self, goal_id: str) -> dict | None:
        """Alias for get_report."""
        return self.get_report(goal_id)

    def get_decisions(self) -> list[dict]:
        return [d.to_dict() for d in self._orchestrator.decisions.get_decisions()]

    def get_learnings(self) -> dict:
        return self._orchestrator.memory_loop.get_learning_summary()
