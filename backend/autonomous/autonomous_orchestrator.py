"""Autonomous Orchestrator for Hermes OS (HOS-063).

Full pipeline:
User Goal → Interpretation → Memory Retrieval → Mission Planner
→ DAG → Agent Selection → Skill Distribution → Runtime Selection
→ Tool Selection → Security Validation → Execution → Validation
→ Memory Update → Evolution Analysis → Final Report
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Callable

from .autonomous_guard import AutonomousGuard, GuardVerdict
from .autonomous_interpreter import AutonomousInterpreter
from .autonomous_memory_loop import AutonomousMemoryLoop
from .autonomous_models import (
    AUTONOMOUS_EVENTS,
    AutonomousDecision,
    AutonomousGoal,
    AutonomousReport,
    AutonomousSession,
    DecisionType,
    GoalStatus,
)
from .decision_engine import DecisionEngine

logger = logging.getLogger("hermes_os.autonomous.orchestrator")


class AutonomousOrchestrator:
    """Central orchestrator for autonomous goal execution.

    Full pipeline orchestrating all Hermes subsystems.
    """

    #: Safety valve on the DAG walk (HOS-067), mirrors mission/routes.py's
    #: own constant — execute_step() runs every currently-ready node, so a
    #: well-formed graph needs at most one pass per dependency level.
    MAX_EXECUTION_PASSES = 100

    def __init__(
        self,
        on_event: Callable | None = None,
        mission_executor: Any = None,
        mission_planner: Any = None,
        graph_executor: Any = None,
    ) -> None:
        """
        Args:
            mission_executor: runs the planned tasks for real (HOS-050). Used
                by the legacy single-task path (see ``_execute_plan``) —
                still the fallback when ``mission_planner``/``graph_executor``
                are not supplied. Defaults to a :class:`MissionExecutor`,
                whose own default task executor drives a real runtime.
            mission_planner: the real Mission Planner (HOS-042) — same
                instance ``/missions`` uses. When supplied together with
                ``graph_executor``, ``start_goal`` decomposes the goal into a
                real multi-node DAG instead of one flat task (HOS-067) — see
                ``_plan_and_execute_via_dag``. ``None`` (the default, and
                every existing caller/test before this change) keeps the
                legacy single-task behaviour unchanged.
            graph_executor: the real DAG walker (HOS-041) — same instance
                ``/missions`` drives via ``start_mission``/``execute_step``.
                Required alongside ``mission_planner`` to use the real path.
        """
        self._lock = threading.RLock()
        self._on_event = on_event

        self.interpreter = AutonomousInterpreter()
        self.decisions = DecisionEngine()
        self.guard = AutonomousGuard()
        self.memory_loop = AutonomousMemoryLoop()

        if mission_executor is None:
            from backend.execution.mission_executor import MissionExecutor

            mission_executor = MissionExecutor(on_event=on_event)
        self.mission_executor = mission_executor
        self.mission_planner = mission_planner
        self.graph_executor = graph_executor
        # Set by the bootstrap (see service_registry.py's
        # _make_autonomous_engine) so goal execution reports the real model
        # Model Intelligence picked — see set_model_adapter().
        self._model_adapter: Any = None

        # Bounded, like _reports already was. These two were plain dicts that
        # grew forever: a 1600-mission run leaked ~10 KiB per mission and never
        # released any of it, and throughput decayed from 972 to 453 missions/s
        # as they filled (RC3 P5). OrderedDict + eviction keeps recent history
        # queryable without an unbounded retention policy nobody chose.
        self._sessions: OrderedDict[str, AutonomousSession] = OrderedDict()
        self._goals: OrderedDict[str, AutonomousGoal] = OrderedDict()
        # Secondary index so get_session() is O(1). It used to scan every
        # session on each lookup, which is what made the decay superlinear.
        self._session_by_goal: dict[str, str] = {}
        self._reports: deque[AutonomousReport] = deque(maxlen=50)
        self._execution_count = 0
        # Live counters, so get_status() does not have to scan every goal.
        self._status_counts: dict[str, int] = {}

    # ── Public API ──

    def set_model_adapter(self, adapter: Any) -> None:
        """Inject Model Intelligence's ModelAutonomousAdapter (HOS-065B).

        Optional and off by default (None): every existing caller/test that
        builds this orchestrator without one keeps behaving exactly as
        before — goal execution just doesn't get reported to Model
        Intelligence. This is a reporting seam, not a decision one: the
        model that actually runs is still chosen by RealTaskExecutor's own
        model_for hook (backend/core/bootstrap/service_registry.py), so
        this adapter never gets asked to pick a model itself
        (select_model_for_goal) — that would create a second decision-maker
        that could disagree with what the report says actually happened.
        """
        self._model_adapter = adapter

    def start_goal(
        self, user_request: str, context: dict[str, Any] | None = None
    ) -> AutonomousGoal:
        """Start a full autonomous goal execution.

        1. Interpret goal
        2. Create session
        3. Plan (decisions)
        4. Execute (real, through MissionExecutor)
        5. Validate
        6. Learn
        7. Report

        Runs **outside** ``self._lock`` (HOS-102). This whole body used to
        sit inside one ``with self._lock:``, held across planning and real
        local inference — minutes. Every other method that takes the lock
        was blocked for that entire time, which meant that while a goal was
        running you could not list goals, could not read ``get_status``, and
        **could not cancel the goal** — the one operation an operator
        actually needs from a run that is going wrong. Measured: a
        ``GET /autonomous/goals`` issued during a live goal timed out after
        25 s with no response.

        The same defect was already removed from ``MissionExecutor`` by
        HOS-069 for the same reason. The lock is now taken only around the
        mutations of the shared containers (``_goals``, ``_sessions``,
        ``_session_by_goal``, ``_reports``); ``goal`` and ``session`` are
        objects this call owns, and a reader that catches a status
        mid-transition sees either the old value or the new one, never a
        torn container.
        """
        ctx = context or {}

        # 1. Interpret
        goal = self.interpreter.interpret(user_request, ctx)
        goal.status = GoalStatus.ANALYZING
        with self._lock:
            self._goals[goal.goal_id] = goal
            self._evict_oldest()
        self._publish(AUTONOMOUS_EVENTS["goal_received"], {
            "goal_id": goal.goal_id, "request": user_request,
        })

        # 2. Create session
        session = AutonomousSession(
            session_id=f"session_{goal.goal_id}",
            goal_id=goal.goal_id,
            status=GoalStatus.PLANNING,
        )
        with self._lock:
            self._sessions[session.session_id] = session
            self._session_by_goal[session.goal_id] = session.session_id

        # Security, before any planning work happens (HOS-067):
        # 1. If the goal is bound to a local project, it must be visible
        #    to Hermes at all — the same ALLOWED_PATHS whitelist every
        #    other file access in this codebase respects, checked here
        #    as a plain read (mutating actions a task later takes are
        #    still separately gated at the point of use).
        if goal.local_path:
            path_verdict = self.guard.check_action(
                "file_read", goal.local_path,
                context={"target_path": goal.local_path},
            )
            if path_verdict != GuardVerdict.ALLOW:
                goal.status = GoalStatus.FAILED
                self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                    "goal_id": goal.goal_id,
                    "reason": f"local_path {goal.local_path!r} denied by Aegis",
                })
                return goal

        # 2. Is *this* goal's execution authorized right now? Before this,
        #    AutonomousGuard's set_security_engine/set_policy_engine hooks
        #    were never wired to anything (confirmed by a repo-wide
        #    search) — every goal reached ALLOW regardless of
        #    autonomy_level. See AegisSecurityAdapter (autonomous_guard.py)
        #    and _make_autonomous_engine (service_registry.py).
        #
        #    Deliberately risk-based, not a blanket gate on every goal:
        #    a pure text generation/analysis goal with no project binding
        #    has no real-world footprint (no file/git/network action is
        #    even reachable from it today — see the module's own report
        #    on what execution actually does), so gating it identically
        #    to one bound to a real repo would just be friction with no
        #    corresponding risk, and would silently defeat the entire
        #    point of this tab at the shipped autonomy_level. A goal
        #    touching a real project, or one the interpreter already
        #    flagged security-sensitive (constraints["security_required"],
        #    from words like "secure"/"security" in the request), is the
        #    real trigger for asking Aegis.
        is_risk_relevant = bool(
            goal.local_path or goal.repository or goal.contraints.get("security_required")
        )
        if is_risk_relevant:
            guard_verdict = self.guard.check_action(
                "autonomous_goal_execute", f"goal/{goal.goal_id}",
                context={"goal_id": goal.goal_id, "target_path": goal.local_path or None},
            )
            if guard_verdict == GuardVerdict.BLOCK:
                goal.status = GoalStatus.FAILED
                self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                    "goal_id": goal.goal_id, "reason": "Guard blocked",
                })
                return goal
            if guard_verdict == GuardVerdict.REVIEW:
                # A real human-in-the-loop signal, not a fabricated pause —
                # Aegis's own REQUIRE_HUMAN_VALIDATION verdict. Resuming a
                # paused goal today only flips its status (see
                # resume_goal); it does not yet re-enter planning/
                # execution — a real, separate gap, not hidden here.
                goal.status = GoalStatus.PAUSED
                session.status = GoalStatus.PAUSED
                self._publish(AUTONOMOUS_EVENTS["goal_paused"], {
                    "goal_id": goal.goal_id, "reason": "Requires human validation (Aegis)",
                })
                return goal

        # 3. Plan
        goal.status = GoalStatus.PLANNING
        self._publish(AUTONOMOUS_EVENTS["goal_analyzed"], {
            "goal_id": goal.goal_id, "interpretation": goal.interpreted_goal,
        })

        use_real_pipeline = self.mission_planner is not None and self.graph_executor is not None
        dag_mission = None
        if use_real_pipeline:
            # Real multi-node DAG via the same pipeline /missions uses
            # (HOS-067) — decomposition, dependencies, per-task runtime
            # recommendation, all real; publishes its own plan_created.
            plan_decisions, dag_mission = self._plan_via_dag(goal, session, ctx)
            if dag_mission is None:
                # Planning itself produced nothing real to run — report
                # that honestly rather than falling back to a fabricated
                # single task.
                goal.status = GoalStatus.FAILED
                self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                    "goal_id": goal.goal_id, "reason": "planning produced no executable tasks",
                })
                return goal

            # Le dossier demandé n'a pas pu devenir un workspace autorisé
            # (HOS-119). Exécuter quand même donnerait des tâches sans
            # aucun outil de fichier, qui rapporteraient leur réussite
            # au-dessus d'un dossier intact — c'est exactement ce qui a été
            # mesuré avant ce correctif.
            if self._workspace_refuse(goal, dag_mission.context.project_id):
                goal.status = GoalStatus.FAILED
                raison = (
                    f"le dossier {goal.local_path!r} n'a pas pu être validé comme "
                    "workspace (inexistant, inaccessible ou en lecture seule) — "
                    "cet objectif demande d'écrire des fichiers et n'aurait eu "
                    "aucun outil pour le faire"
                )
                logger.warning("objectif %s refusé : %s", goal.goal_id, raison)
                self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                    "goal_id": goal.goal_id, "reason": raison,
                })
                return goal
        else:
            plan_decisions = self._create_plan(goal, ctx)
            session.active_agents = [d.selected_option for d in plan_decisions
                                     if d.decision_type == DecisionType.AGENT_SELECTION]
            session.timeline.append({
                "event": "plan_created",
                "timestamp": time.time(),
                "decisions": [d.decision_id for d in plan_decisions],
            })
            self._publish(AUTONOMOUS_EVENTS["plan_created"], {
                "goal_id": goal.goal_id, "decisions": len(plan_decisions),
            })

        # 4. Execute
        goal.status = GoalStatus.EXECUTING
        session.status = GoalStatus.EXECUTING
        self._publish(AUTONOMOUS_EVENTS["execution_started"], {
            "goal_id": goal.goal_id, "session_id": session.session_id,
        })

        # Execute for real through the Mission Executor (HOS-050), or the
        # real DAG pipeline (HOS-067) when wired.
        #
        # This replaced `success = random.random() > 0.15` and
        # `duration = random.uniform(500, 5000)`. Those two lines meant every
        # autonomous goal returned a fabricated outcome with an invented
        # duration, and because the API reported success no caller could tell.
        # Outcome and duration are now whatever actually happened.
        if use_real_pipeline:
            exec_result = self._execute_via_dag(goal, session, dag_mission)
        else:
            exec_result = self._execute_plan(goal, session, plan_decisions)
        success = exec_result["success"]
        duration = exec_result["duration_ms"]
        if not success and exec_result.get("runtime_available") is False:
            # The work could not be attempted at all. That is a failed goal,
            # not a completed one, and the reason has to reach the report.
            goal.status = GoalStatus.FAILED
            self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                "goal_id": goal.goal_id,
                "reason": "runtime_unavailable",
                "detail": exec_result.get("error", ""),
            })

        # 5. Validate
        goal.status = GoalStatus.VALIDATING

        # 6. Generate report
        report = AutonomousReport(
            goal_id=goal.goal_id,
            user_request=goal.user_request,
            interpreted_goal=goal.interpreted_goal,
            execution_summary=exec_result["summary"],
            results=exec_result["results"],
            improvements=exec_result["improvements"],
            lessons=exec_result["lessons"],
            decisions=[d.to_dict() for d in plan_decisions],
            total_duration_ms=duration,
            agents_used=session.active_agents,
            # Measured, not asserted. This was hardcoded to
            # ["ktransformers"] regardless of what ran — and nothing ran.
            runtimes_used=exec_result["runtimes_used"],
            tools_used=[d.selected_option for d in plan_decisions
                       if d.decision_type == DecisionType.TOOL_SELECTION],
            success=success,
        )

        # 7. Learn
        goal.status = GoalStatus.LEARNING
        self.memory_loop.process_report(report)
        self._publish(AUTONOMOUS_EVENTS["learning_completed"], {
            "goal_id": goal.goal_id, "lessons": len(report.lessons),
        })

        # 8. Complete
        goal.status = GoalStatus.COMPLETED if success else GoalStatus.FAILED
        import datetime as _dt
        goal.completed_at = _dt.datetime.now(_dt.timezone.utc)
        session.status = goal.status
        session.end_time = goal.completed_at
        with self._lock:
            self._reports.append(report)
            self._execution_count += 1

        if success:
            self._publish(AUTONOMOUS_EVENTS["execution_completed"], {
                "goal_id": goal.goal_id, "duration_ms": duration,
            })
        else:
            self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                "goal_id": goal.goal_id, "reason": "Execution failed",
            })

        return goal

    def pause_goal(self, goal_id: str) -> bool:
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.status not in (GoalStatus.EXECUTING, GoalStatus.PLANNING):
                return False
            goal.status = GoalStatus.PAUSED
            return True

    def resume_goal(self, goal_id: str) -> bool:
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.status != GoalStatus.PAUSED:
                return False
            goal.status = GoalStatus.EXECUTING
            return True

    def cancel_goal(self, goal_id: str) -> bool:
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return False
            goal.status = GoalStatus.CANCELLED
            return True

    def get_goal(self, goal_id: str) -> AutonomousGoal | None:
        with self._lock:
            return self._goals.get(goal_id)

    def list_goals(self, limit: int = 50) -> list[AutonomousGoal]:
        """Goals most recently started first.

        ``get_status`` has always counted these; nothing could enumerate
        them. That left a goal reachable only by an id the caller had to
        have captured at start time — so the Autonomous Center lost track
        of a running goal the moment its component unmounted, and a page
        reload made the goal permanently unreachable while it kept running
        (HOS-102).
        """
        with self._lock:
            # _goals is insertion-ordered and start_goal appends, so the
            # newest are at the end.
            return list(reversed(list(self._goals.values())))[:limit]

    def _project_pour(self, goal: AutonomousGoal) -> str:
        """L'id du Project validé couvrant `goal.local_path`, ou "".

        Rend "" quand l'objectif n'a pas de dossier — beaucoup n'en ont pas
        besoin, et leur en imposer un serait refuser du travail légitime.
        Rend "" aussi quand le dossier existe mais ne se valide pas ; c'est
        `_workspace_refuse` qui décide alors d'arrêter, pas cette fonction.
        """
        if not goal.local_path:
            return ""
        try:
            from backend.projects.store import get_project_store

            projet = get_project_store().ensure_for_path(
                goal.local_path, name=f"autonome-{goal.goal_id[-8:]}")
        except Exception:
            logger.warning("workspace non résolu pour %s", goal.goal_id, exc_info=True)
            return ""
        return projet.id if projet else ""

    @staticmethod
    def _workspace_refuse(goal: AutonomousGoal, project_id: str) -> bool:
        """Un objectif qui réclame un dossier sans pouvoir l'obtenir.

        Il doit s'arrêter là. Le laisser courir, c'est ce qui vient de
        produire six tâches « réussies » en 41 secondes au-dessus d'un
        dossier vide, avec un rapport affirmatif — un mensonge confiant,
        indiscernable d'un vrai succès. Un refus immédiat et lisible coûte
        moins cher et dit la vérité.
        """
        return bool(goal.local_path) and not project_id

    def _marcher_le_graphe(self, mission, terminal) -> int:
        """Faire avancer le DAG jusqu'au bout, ou jusqu'au plafond de passes.

        Extrait pour que la reprise (HOS-118) réutilise exactement la même
        marche que la première tentative. Réécrire la boucle une seconde
        fois aurait laissé les deux dériver — l'une bornée, l'autre non.
        """
        passes = 0
        while mission.status not in terminal and passes < self.MAX_EXECUTION_PASSES:
            stepped = self.graph_executor.execute_step(mission)
            passes += 1
            if stepped == 0:
                break
        return passes

    def get_session(self, goal_id: str) -> AutonomousSession | None:
        with self._lock:
            session_id = self._session_by_goal.get(goal_id)
            return self._sessions.get(session_id) if session_id else None

    def get_report(self, goal_id: str) -> AutonomousReport | None:
        for r in self._reports:
            if r.goal_id == goal_id:
                return r
        return None

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            goals = list(self._goals.values())
            return {
                "total_goals": len(goals),
                "active": sum(1 for g in goals if g.status in
                              (GoalStatus.ANALYZING, GoalStatus.PLANNING, GoalStatus.EXECUTING)),
                "completed": sum(1 for g in goals if g.status == GoalStatus.COMPLETED),
                "failed": sum(1 for g in goals if g.status == GoalStatus.FAILED),
                "cancelled": sum(1 for g in goals if g.status == GoalStatus.CANCELLED),
                "total_executions": self._execution_count,
                "active_sessions": len(self._sessions),
                "interpreter": {"history": len(self.interpreter.get_history())},
                "decisions": self.decisions.stats(),
                "guard": self.guard.stats(),
                "memory_loop": self.memory_loop.get_learning_summary(),
            }

    # ── Private ──

    #: TaskCategory value -> a *real* registered agent id (config/agents.yaml
    #: — HOS-067). Replaces DecisionEngine's fake agent alternatives
    #: ("klaatcode", "ohmypi", "code_intelligence", "mission_planner") for
    #: the real DAG path — none of those names has ever been a registered
    #: Hermes agent. This is a category heuristic, not a measured score:
    #: agent SELECTION is now real, but nothing yet makes execution actually
    #: dispatch per-agent behaviour (still a single generic RealTaskExecutor
    #: call regardless of which agent is named) — a real, separate gap, not
    #: hidden by this change.
    _CATEGORY_AGENT: dict[str, str] = {
        "implementation": "atlas", "optimization": "atlas",
        "integration": "atlas", "deployment": "atlas",
        "testing": "veritas", "review": "veritas",
        "documentation": "hermes_scribe",
        "analysis": "minerva",
        "planning": "kronos",
        "security": "aegis",
        "design": "hermes_prime", "custom": "hermes_prime",
    }

    def _plan_via_dag(
        self, goal: AutonomousGoal, session: AutonomousSession, context: dict,
    ) -> tuple[list[AutonomousDecision], Any]:
        """Decompose the goal into a real multi-node DAG via the same
        Mission Planner ``/missions`` uses (HOS-067), instead of the single
        flat task ``_create_plan``/``_execute_plan`` build by hand.

        Returns ``(decisions, mission)``; ``mission`` is ``None`` when
        planning produced no executable tasks — the caller must fail the
        goal honestly rather than fabricate a task that was never planned.
        """
        from backend.mission.planner.planner_models import PlanningRequest

        request = PlanningRequest(
            user_request=goal.user_request,
            objective=goal.interpreted_goal,
            context=context,
            repository=goal.repository,
            branch=goal.branch,
            # Real prior-experience summary (Phase D) reaches the same
            # decomposition prompt /missions' own `specification` field
            # already threads into _build_user_prompt() — not a second,
            # parallel context channel.
            specification=goal.knowledge_context,
            tags=[t for t in (goal.domain, goal.language) if t],
        )
        result = self.mission_planner.plan(request)

        if not result.task_breakdowns:
            return [], None

        plan_decisions = self._decisions_from_plan(goal, result)
        session.active_agents = sorted({
            d.selected_option for d in plan_decisions
            if d.decision_type == DecisionType.AGENT_SELECTION
        })
        session.timeline.append({
            "event": "plan_created",
            "timestamp": time.time(),
            "decisions": [d.decision_id for d in plan_decisions],
        })
        self._publish(AUTONOMOUS_EVENTS["plan_created"], {
            "goal_id": goal.goal_id, "decisions": len(plan_decisions),
        })

        mission = self.mission_planner.build_mission(
            result,
            title=(goal.interpreted_goal or goal.user_request)[:100],
            objective=goal.user_request,
        )
        mission.context.local_path = goal.local_path
        mission.context.repository = goal.repository
        mission.context.branch = goal.branch
        # Le chemin devient un Project validé, sans quoi la mission n'aura
        # aucun outil de fichier (HOS-119).
        #
        # `_workspace_project_for` résout `task.mission_id -> mission.
        # context.project_id -> Project actif et validé`. Un `local_path`
        # brut ne franchit pas cette chaîne : elle rendait `None`, la tâche
        # partait en complétion simple, et le modèle sommé d'écrire un
        # fichier sans pouvoir le faire produisait un appel d'outil **en
        # texte**. Mesuré : 6 tâches sur 6 « réussies », 41 s, zéro fichier.
        mission.context.project_id = self._project_pour(goal)
        session.mission_id = mission.mission_id

        # HOS-068: make this mission visible through /missions too — before
        # this, build_mission() registered it with the GraphExecutor (so
        # execution works) but never with mission/routes.py's own registry,
        # so GET /missions never listed a mission Autonomous had started.
        try:
            from backend.mission import routes as mission_routes

            mission_routes.register_mission(mission)
        except Exception:
            logger.debug("mission registration failed for %s", mission.mission_id, exc_info=True)

        return plan_decisions, mission

    def _decisions_from_plan(self, goal: AutonomousGoal, result: Any) -> list[AutonomousDecision]:
        """Real per-task decisions derived from the real planning result
        (HOS-067) — no DecisionEngine call here: its agent/tool/skill
        alternatives are still hardcoded lists never checked against a real
        registry (see decision_engine.py's own module docstring and
        CHANGELOG). A real plan already carries real category, runtime
        recommendation (with its own reasoning string), and required-skills
        data per task — this reads that instead of inventing a parallel
        heuristic.
        """
        decisions: list[AutonomousDecision] = []
        for task in result.task_breakdowns:
            agent = self._CATEGORY_AGENT.get(task.category.value, "hermes_prime")
            decisions.append(AutonomousDecision(
                decision_id=f"dec_{task.task_id}_agent",
                decision_type=DecisionType.AGENT_SELECTION,
                reason=f"Category {task.category.value!r} maps to {agent!r} (config/agents.yaml).",
                confidence=0.6,
                selected_option=agent,
                context={"task_id": task.task_id, "category": task.category.value},
            ))

            rec = result.runtime_recommendations.get(task.task_id)
            if rec is not None:
                decisions.append(AutonomousDecision(
                    decision_id=f"dec_{task.task_id}_runtime",
                    decision_type=DecisionType.RUNTIME_SELECTION,
                    reason=rec.reasoning,
                    confidence=rec.confidence,
                    selected_option=rec.model_name,
                    alternatives=[{"name": a} for a in rec.alternatives],
                    context={"task_id": task.task_id},
                ))

            if task.required_skills:
                decisions.append(AutonomousDecision(
                    decision_id=f"dec_{task.task_id}_skill",
                    decision_type=DecisionType.SKILL_SELECTION,
                    reason=f"Task requires: {', '.join(task.required_skills)}.",
                    confidence=0.7,
                    selected_option=task.required_skills[0],
                    context={"task_id": task.task_id, "all_skills": task.required_skills},
                ))
        return decisions

    def _execute_via_dag(
        self, goal: AutonomousGoal, session: AutonomousSession, mission: Any,
    ) -> dict[str, Any]:
        """Build and walk the real DAG (HOS-067) — the same
        build_graph()/start_mission()/execute_step() sequence
        ``/missions/{id}/start`` drives, so an autonomous goal's mission
        shows up identically in ``/missions`` too (one shared source of
        truth, not a second, disconnected execution path).
        """
        from backend.mission.mission_models import MissionStatus, NodeStatus

        started = time.perf_counter()
        issues = self.graph_executor.build_graph(mission, mission.nodes, mission.edges)
        if issues:
            duration_ms = (time.perf_counter() - started) * 1000.0
            return self._dag_result(
                success=False, duration_ms=duration_ms, mission=mission,
                error="; ".join(issues),
                summary=f"Mission graph invalid: {'; '.join(issues)}",
            )

        if not self.graph_executor.start_mission(mission):
            duration_ms = (time.perf_counter() - started) * 1000.0
            return self._dag_result(
                success=False, duration_ms=duration_ms, mission=mission,
                error=f"mission could not start (status={mission.status.value})",
                summary="Mission could not start",
            )

        terminal = (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED)
        self._marcher_le_graphe(mission, terminal)

        # La reprise, que ce chemin ne faisait pas (HOS-118).
        #
        # `GraphExecutor` produit déjà le brief quand le disque contredit un
        # succès annoncé — il le pose dans `metadata["retry_brief"]`. Mais
        # seule la route des missions le consommait ; ici il était écrit puis
        # abandonné. La vérification tournait, la décision était prise, et
        # rien ne se passait : exactement l'état que HOS-100 avait corrigé
        # pour les missions et laissé ouvert du côté autonome.
        from backend.mission.retry_policy import preparer_reprise

        if preparer_reprise(mission, executor=self.graph_executor):
            self._marcher_le_graphe(mission, terminal)

        duration_ms = (time.perf_counter() - started) * 1000.0
        completed = [n for n in mission.nodes if n.status == NodeStatus.COMPLETED]
        failed = [n for n in mission.nodes if n.status == NodeStatus.FAILED]
        success = bool(completed) and not failed and mission.status == MissionStatus.COMPLETED

        summary = f"{len(completed)}/{len(mission.nodes)} task(s) completed in {duration_ms:.0f}ms"
        # See TaskDecomposer.decompose_with_method: the real LLM decomposition
        # can silently fail (timeout, unparseable response) and fall back to
        # a generic, request-independent task template. A "completed"
        # status here would otherwise look identical to a real result.
        if mission.metadata.get("decomposition_method") == "generic_fallback":
            summary = (
                "WARNING: real decomposition failed and this ran a generic, "
                "request-independent task template, not a plan for what was "
                "actually asked. " + summary
            )
        return self._dag_result(
            success=success, duration_ms=duration_ms, mission=mission, error="",
            summary=summary,
        )

    def _dag_result(
        self, *, success: bool, duration_ms: float, mission: Any, error: str, summary: str,
    ) -> dict[str, Any]:
        from backend.mission.mission_models import NodeStatus

        completed = [n for n in mission.nodes if n.status == NodeStatus.COMPLETED]
        failed = [n for n in mission.nodes if n.status == NodeStatus.FAILED]
        # preferred_runtime holds a model tag before a node runs (from
        # RuntimeRecommender) and the real serving provider ("ollama"/
        # "openrouter") after — node_execution.py overwrites it once the
        # node actually executes. This means the specific model tag isn't
        # recoverable from the node afterward; models_used is left honestly
        # empty here rather than reporting the pre-execution recommendation
        # as if it were what actually ran. A real limitation shared with
        # /missions, not autonomous-specific — worth fixing there directly.
        runtimes_used = sorted({n.preferred_runtime for n in completed if n.preferred_runtime})

        plan_is_generic = mission.metadata.get("decomposition_method") == "generic_fallback"

        lessons: list[str] = []
        improvements: list[str] = []
        if error:
            improvements.append("Provide a reachable runtime / valid mission graph before dispatching autonomous goals")
        if plan_is_generic:
            improvements.append(
                "Real decomposition failed for this goal (timeout, or an "
                "unparseable model response) — this ran a generic template "
                "instead. Retry, or check the planning role's model/timeout."
            )
        if failed:
            lessons.append(
                f"{len(failed)} task(s) failed: "
                + "; ".join(f"{n.title}: {n.result_summary or 'no detail'}" for n in failed[:3])
            )
        if completed:
            avg = sum(n.actual_duration_ms for n in completed) / len(completed)
            lessons.append(f"{len(completed)} task(s) averaged {avg:.0f}ms")

        return {
            "success": success,
            "duration_ms": duration_ms,
            "runtime_available": not bool(error),
            "error": error,
            "runtimes_used": runtimes_used,
            "summary": summary,
            "improvements": improvements,
            "lessons": lessons,
            "results": {
                "success": success,
                "duration_ms": round(duration_ms, 1),
                "tasks_total": len(mission.nodes),
                "tasks_completed": len(completed),
                "tasks_failed": len(failed),
                "tokens": 0,
                "models_used": [],
                "outputs": [
                    {"task": n.title, "chars": len(n.result_summary or ""),
                     "content": n.result_summary or ""}
                    for n in completed
                ],
                "decomposition_method": mission.metadata.get("decomposition_method", "llm"),
                "plan_is_generic": plan_is_generic,
            },
        }

    def _create_plan(self, goal: AutonomousGoal, context: dict) -> list[AutonomousDecision]:
        """Create a plan: select agents, runtime, tools, skills."""
        decisions = []

        # Agent selection
        agent_dec = self.decisions.select_agent(goal.domain, {
            "domain": goal.domain, "language": goal.language,
        })
        decisions.append(agent_dec)
        self._publish("autonomous.decision.made", {
            "goal_id": goal.goal_id, "decision": agent_dec.to_dict(),
        })

        # Runtime selection
        runtime_dec = self.decisions.select_runtime(goal.domain, goal.complexity)
        decisions.append(runtime_dec)

        # Tool selection
        tool_dec = self.decisions.select_tool(goal.domain, {"language": goal.language})
        decisions.append(tool_dec)

        # Skill selection
        skill_dec = self.decisions.select_skill(goal.domain, goal.language)
        decisions.append(skill_dec)

        self._publish(AUTONOMOUS_EVENTS["agent_selected"], {
            "goal_id": goal.goal_id,
            "selected_agent": agent_dec.selected_option,
        })

        return decisions

    def _execute_plan(
        self,
        goal: AutonomousGoal,
        session: AutonomousSession,
        plan_decisions: list[AutonomousDecision],
    ) -> dict[str, Any]:
        """Turn the plan into real tasks, run them, and report what happened.

        Everything returned here is measured. ``success`` is true only when every
        task actually completed and validated; ``duration_ms`` is wall-clock;
        ``runtimes_used`` lists the runtimes that really served a task.

        A goal whose runtime is unavailable comes back with
        ``runtime_available: False`` so the caller can fail it rather than
        recording a completion that never occurred.
        """
        from backend.execution.execution_models import (
            ExecutionMeta,
            ExecutionPriority,
            TaskExecution,
            TaskExecutionStatus,
        )

        started = time.perf_counter()

        # DecisionEngine produces *selection* decisions (agent, runtime, tool,
        # skill, workflow) — it does not decompose a goal into sub-tasks. So the
        # unit of work is the goal itself, carrying the selections the planner
        # made. One honest task beats inventing a decomposition the planner never
        # produced.
        def _selected(kind: DecisionType) -> str:
            for d in plan_decisions:
                if d.decision_type == kind and d.selected_option:
                    return str(d.selected_option)
            return ""

        task = TaskExecution(
            task_id=f"{goal.goal_id}-t0",
            node_id=f"{goal.goal_id}-n0",
            title=goal.interpreted_goal or goal.user_request,
            status=TaskExecutionStatus.PENDING,
            assigned_agent=_selected(DecisionType.AGENT_SELECTION),
            assigned_runtime=_selected(DecisionType.RUNTIME_SELECTION),
            assigned_skills=[d.selected_option for d in plan_decisions
                             if d.decision_type == DecisionType.SKILL_SELECTION
                             and d.selected_option],
            assigned_tools=[d.selected_option for d in plan_decisions
                            if d.decision_type == DecisionType.TOOL_SELECTION
                            and d.selected_option],
        )
        tasks = [task]

        meta = ExecutionMeta(
            mission_id=goal.goal_id,
            user_goal=goal.user_request,
            priority=ExecutionPriority.NORMAL,
        )

        results: list[dict[str, Any]] = []
        runtimes: list[str] = []
        unavailable: str = ""

        try:
            # prepare() returns the state machine execute_task() needs.
            state_machine = self.mission_executor.prepare(meta, tasks)
            for task in tasks:
                outcome = self.mission_executor.execute_task(
                    state_machine, task.task_id
                )
                results.append(outcome)
                if outcome.get("runtime_available") is False:
                    unavailable = outcome.get("error", "runtime unavailable")
                    break
        except Exception as exc:  # the executor itself failed
            unavailable = f"{type(exc).__name__}: {exc}"

        duration_ms = (time.perf_counter() - started) * 1000.0

        for task in tasks:
            if task.assigned_runtime and task.assigned_runtime not in runtimes:
                runtimes.append(task.assigned_runtime)

        completed = [t for t in tasks if t.status == TaskExecutionStatus.COMPLETED]
        failed = [t for t in tasks if t.status == TaskExecutionStatus.FAILED]
        success = bool(completed) and not failed and not unavailable

        # Real model(s) Model Intelligence picked and Ollama actually served
        # for this goal — previously computed inside RealTaskExecutor and
        # then discarded before reaching this report (see mission_executor.py).
        models_used = sorted({r.get("model") for r in results if r.get("model")})
        self._report_model_feedback(goal, tasks, results)

        summary = (
            f"{len(completed)}/{len(tasks)} task(s) completed on "
            f"{', '.join(runtimes) or 'no runtime'} in {duration_ms:.0f}ms"
        )
        if unavailable:
            summary = f"Execution could not run: {unavailable}"

        lessons: list[str] = []
        improvements: list[str] = []
        if unavailable:
            improvements.append(
                "Provide a reachable runtime before dispatching autonomous goals"
            )
        if failed:
            lessons.append(
                f"{len(failed)} task(s) failed validation: "
                + "; ".join(f"{t.title}: {'; '.join(t.errors[-1:]) or 'no detail'}"
                            for t in failed[:3])
            )
        if completed:
            avg = sum(t.duration_ms for t in completed) / len(completed)
            lessons.append(
                f"{goal.domain} tasks averaged {avg:.0f}ms on "
                f"{', '.join(runtimes) or 'unknown runtime'}"
            )

        return {
            "success": success,
            "duration_ms": duration_ms,
            "runtime_available": not bool(unavailable),
            "error": unavailable,
            "runtimes_used": runtimes,
            "summary": summary,
            "improvements": improvements,
            "lessons": lessons,
            "results": {
                "success": success,
                "duration_ms": round(duration_ms, 1),
                "tasks_total": len(tasks),
                "tasks_completed": len(completed),
                "tasks_failed": len(failed),
                "tokens": sum(
                    int(t.resources_used.get("total_tokens", 0) or 0) for t in tasks
                ),
                # The specific model(s) actually served this goal (e.g.
                # "qwen3:1.7b"), not the runtime provider name already in
                # runtimes_used (e.g. "ollama") — see mission_executor.py.
                "models_used": models_used,
                # `content` used to be missing entirely: only the task's own
                # title and a character count were kept, so a goal that ran
                # for real (tokens spent, seconds elapsed, confirmed against
                # Ollama) still left the user with no way to read what the
                # model actually said — the one thing they asked for.
                "outputs": [
                    {"task": t.title, "chars": len(str(t.result or "")),
                     "content": str(t.result or "")}
                    for t in completed
                ],
            },
        }

    def _report_model_feedback(
        self, goal: AutonomousGoal, tasks: list, results: list[dict[str, Any]],
    ) -> None:
        """Feed ModelAutonomousAdapter (HOS-065B) with what a task actually
        did, so its per-goal history and stats reflect real usage — before
        this, they stayed empty forever because nothing ever called
        record_feedback(). Never raises: a reporting failure must not turn
        an already-completed goal into a failed one."""
        if self._model_adapter is None:
            return
        from backend.execution.execution_models import TaskExecutionStatus
        from backend.model_intelligence.model_autonomous_adapter import (
            ModelExecutionFeedback,
        )

        for task, outcome in zip(tasks, results):
            model_id = outcome.get("model")
            if not model_id:
                continue
            try:
                self._model_adapter.record_feedback(ModelExecutionFeedback(
                    goal_id=goal.goal_id,
                    model_id=model_id,
                    task_type=goal.domain or "general",
                    duration_ms=task.duration_ms,
                    tokens_used=int(task.resources_used.get("total_tokens", 0) or 0),
                    success=task.status == TaskExecutionStatus.COMPLETED,
                    errors=list(task.errors[-3:]) if task.errors else [],
                ))
            except Exception:
                pass

    #: How much autonomous history stays resident. Chosen to be generous for a
    #: Cockpit that lists recent goals while still being a bound — an unbounded
    #: dict is not a retention policy, it is the absence of one.
    MAX_RETAINED_GOALS = 500

    def _evict_oldest(self) -> None:
        """Drop the oldest goals and their sessions once the cap is exceeded."""
        while len(self._goals) > self.MAX_RETAINED_GOALS:
            goal_id, _ = self._goals.popitem(last=False)
            session_id = self._session_by_goal.pop(goal_id, None)
            if session_id is not None:
                self._sessions.pop(session_id, None)

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass
