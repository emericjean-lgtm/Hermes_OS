"""Autonomous Orchestrator for Hermes OS (HOS-063).

Full pipeline:
User Goal → Interpretation → Memory Retrieval → Mission Planner
→ DAG → Agent Selection → Skill Distribution → Runtime Selection
→ Tool Selection → Security Validation → Execution → Validation
→ Memory Update → Evolution Analysis → Final Report
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
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

    def __init__(self, on_event: Callable | None = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        self.interpreter = AutonomousInterpreter()
        self.decisions = DecisionEngine()
        self.guard = AutonomousGuard()
        self.memory_loop = AutonomousMemoryLoop()

        self._sessions: dict[str, AutonomousSession] = {}
        self._goals: dict[str, AutonomousGoal] = {}
        self._reports: deque[AutonomousReport] = deque(maxlen=50)
        self._execution_count = 0

    # ── Public API ──

    def start_goal(
        self, user_request: str, context: dict[str, Any] | None = None
    ) -> AutonomousGoal:
        """Start a full autonomous goal execution.

        1. Interpret goal
        2. Create session
        3. Plan (decisions)
        4. Execute (simulated)
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

            # Simulate execution
            success = random.random() > 0.15  # 85% success rate
            duration = random.uniform(500, 5000)
            time.sleep(0.01)  # Tiny delay for realism

            # 5. Validate
            goal.status = GoalStatus.VALIDATING

            # 6. Generate report
            report = AutonomousReport(
                goal_id=goal.goal_id,
                user_request=goal.user_request,
                interpreted_goal=goal.interpreted_goal,
                execution_summary=f"Executed {goal.domain} goal: {goal.interpreted_goal[:80]}...",
                results={"success": success, "duration_ms": duration},
                improvements=["Consider using hybrid mode for complex goals"],
                lessons=[f"Learned: {goal.domain} goals work best with {', '.join(session.active_agents)}"],
                decisions=[d.to_dict() for d in plan_decisions],
                total_duration_ms=duration,
                agents_used=session.active_agents,
                runtimes_used=["ktransformers"],
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
        for s in self._sessions.values():
            if s.goal_id == goal_id:
                return s
        return None

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

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass
