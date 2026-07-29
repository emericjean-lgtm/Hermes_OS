"""Agent Trust Engine for Hermes OS (HOS-057).

Calculates dynamic trust scores for agents based on:
- Historical success rate
- Policy violations
- Result quality
- Human approvals
- Recency of behavior
- Task complexity handled
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable

from .security_models import AgentTrustScore, TrustLevel


WEIGHTS = {
    "success_rate": 0.30,
    "policy_compliance": 0.25,
    "human_approvals": 0.15,
    "recent_behavior": 0.20,
    "tenure": 0.10,
}


class AgentTrustEngine:
    """Dynamic trust scoring engine for agents.

    Thread-safe. Maintains per-agent trust scores that update
    with every task execution and policy evaluation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scores: dict[str, AgentTrustScore] = {}
        self._on_update: list[Callable[[str, AgentTrustScore], None]] = []

    def on_trust_update(self, callback: Callable[[str, AgentTrustScore], None]) -> None:
        self._on_update.append(callback)

    def get_score(self, agent_id: str) -> AgentTrustScore:
        with self._lock:
            if agent_id not in self._scores:
                self._scores[agent_id] = AgentTrustScore(agent_id=agent_id)
            return self._scores[agent_id]

    def record_result(self, agent_id: str, success: bool, quality: float = 1.0) -> None:
        """Record a task result and recalculate trust score."""
        with self._lock:
            score = self._scores.get(agent_id)
            if score is None:
                score = AgentTrustScore(agent_id=agent_id)
                self._scores[agent_id] = score

            score.total_tasks += 1
            if success:
                score.success_count += 1
            else:
                score.failure_count += 1

            # Recent behavior: last 10 tasks
            self._update_recent_behavior(score, success)

            # Recalculate
            self._recalculate(score)

        self._notify(agent_id, score)

    def record_policy_violation(self, agent_id: str) -> None:
        """Record a policy violation and downgrade trust."""
        with self._lock:
            score = self._scores.get(agent_id)
            if score is None:
                score = AgentTrustScore(agent_id=agent_id)
                self._scores[agent_id] = score
            score.policy_violations += 1
            self._recalculate(score)
        self._notify(agent_id, score)

    def record_human_approval(self, agent_id: str) -> None:
        """Record a human approval and boost trust."""
        with self._lock:
            score = self._scores.get(agent_id)
            if score is None:
                score = AgentTrustScore(agent_id=agent_id)
                self._scores[agent_id] = score
            score.human_approvals += 1
            self._recalculate(score)
        self._notify(agent_id, score)

    def get_all_scores(self) -> list[AgentTrustScore]:
        with self._lock:
            return list(self._scores.values())

    def get_threshold(self, required: TrustLevel) -> float:
        """Get the minimum score for a trust level."""
        thresholds = {
            TrustLevel.UNKNOWN: 0,
            TrustLevel.LOW: 20,
            TrustLevel.MEDIUM: 40,
            TrustLevel.HIGH: 70,
            TrustLevel.VERIFIED: 90,
        }
        return thresholds.get(required, 0)

    def meets_threshold(self, agent_id: str, required: TrustLevel) -> bool:
        """Check if an agent meets a minimum trust level."""
        score = self.get_score(agent_id)
        return score.score >= self.get_threshold(required)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            scores = list(self._scores.values())
            return {
                "total_agents": len(scores),
                "average_score": round(
                    sum(s.score for s in scores) / max(len(scores), 1), 1
                ),
                "by_level": {
                    level.value: sum(1 for s in scores if s.level == level)
                    for level in TrustLevel
                },
                "total_violations": sum(s.policy_violations for s in scores),
                "total_approvals": sum(s.human_approvals for s in scores),
            }

    # ── Private ──

    def _update_recent_behavior(self, score: AgentTrustScore, latest_success: bool) -> None:
        """Update recent behavior score (last 10 tasks)."""
        recent_window = 10
        recent_tasks = min(score.total_tasks, recent_window)
        # Decay the existing recent_behavior
        if score.total_tasks > 1:
            score.recent_behavior = (
                (score.recent_behavior * (recent_tasks - 1) + (1.0 if latest_success else 0.0))
                / recent_tasks
            )
        else:
            score.recent_behavior = 1.0 if latest_success else 0.0

    def _recalculate(self, score: AgentTrustScore) -> None:
        """Recalculate the trust score from all factors."""
        success_rate = score.success_count / max(score.total_tasks, 1)
        policy_compliance = max(0.0, 1.0 - (score.policy_violations / max(score.total_tasks + score.policy_violations, 1)))
        approval_bonus = min(1.0, score.human_approvals / max(score.total_tasks, 1) * 2)
        tenure_factor = min(1.0, score.total_tasks / 100)

        raw = (
            success_rate * WEIGHTS["success_rate"]
            + policy_compliance * WEIGHTS["policy_compliance"]
            + approval_bonus * WEIGHTS["human_approvals"]
            + score.recent_behavior * WEIGHTS["recent_behavior"]
            + tenure_factor * WEIGHTS["tenure"]
        )
        score.score = round(raw * 100, 1)

        # Map score to trust level
        if score.score >= 85:
            score.level = TrustLevel.VERIFIED
        elif score.score >= 60:
            score.level = TrustLevel.HIGH
        elif score.score >= 35:
            score.level = TrustLevel.MEDIUM
        elif score.score >= 15:
            score.level = TrustLevel.LOW
        else:
            score.level = TrustLevel.UNKNOWN

    def _notify(self, agent_id: str, score: AgentTrustScore) -> None:
        for cb in self._on_update:
            try:
                cb(agent_id, score)
            except Exception:
                pass
