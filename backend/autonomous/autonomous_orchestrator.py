"""Autonomous Orchestrator for Hermes OS (HOS-063).

Full pipeline:
User Goal → Interpretation → Memory Retrieval → Mission Planner
→ DAG → Agent Selection → Skill Distribution → Runtime Selection
→ Tool Selection → Security Validation → Execution → Validation
→ Memory Update → Evolution Analysis → Final Report
"""

from __future__ import annotations

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


class AutonomousOrchestrator:
    """Central orchestrator for autonomous goal execution.

    Full pipeline orchestrating all Hermes subsystems.
    """

    def __init__(
        self,
        on_event: Callable | None = None,
        mission_executor: Any = None,
    ) -> None:
        """
        Args:
            mission_executor: runs the planned tasks for real (HOS-050). Injected
                so this orchestrator keeps deciding and something else executes.
                Defaults to a :class:`MissionExecutor`, whose own default task
                executor drives a real runtime.
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
        """
        with self._lock:
            ctx = context or {}

            # 1. Interpret
            goal = self.interpreter.interpret(user_request, ctx)
            goal.status = GoalStatus.ANALYZING
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
            self._sessions[session.session_id] = session
            self._session_by_goal[session.goal_id] = session.session_id

            # 3. Plan
            goal.status = GoalStatus.PLANNING
            self._publish(AUTONOMOUS_EVENTS["goal_analyzed"], {
                "goal_id": goal.goal_id, "interpretation": goal.interpreted_goal,
            })

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

            # Guard check before execution
            guard_verdict = self.guard.check_action(
                "goal.execute", f"goal/{goal.goal_id}",
                context={"goal_id": goal.goal_id},
            )
            if guard_verdict != GuardVerdict.ALLOW:
                goal.status = GoalStatus.FAILED
                self._publish(AUTONOMOUS_EVENTS["goal_failed"], {
                    "goal_id": goal.goal_id, "reason": "Guard blocked",
                })
                return goal

            # 4. Execute
            goal.status = GoalStatus.EXECUTING
            session.status = GoalStatus.EXECUTING
            self._publish(AUTONOMOUS_EVENTS["execution_started"], {
                "goal_id": goal.goal_id, "session_id": session.session_id,
            })

            # Execute for real through the Mission Executor (HOS-050).
            #
            # This replaced `success = random.random() > 0.15` and
            # `duration = random.uniform(500, 5000)`. Those two lines meant every
            # autonomous goal returned a fabricated outcome with an invented
            # duration, and because the API reported success no caller could tell.
            # Outcome and duration are now whatever actually happened.
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
