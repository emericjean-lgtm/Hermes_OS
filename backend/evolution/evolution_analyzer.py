"""Evolution Analyzer for Hermes OS (HOS-058).

Analyzes system metrics from runtime, agents, skills, missions, and memory
to detect improvement opportunities.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from .evolution_models import (
    EvolutionProposal,
    EvolutionStatus,
    EvolutionType,
    RiskLevel,
    SystemMetrics,
)


class EvolutionAnalyzer:
    """Analyzes system metrics and generates evolution proposals.

    Thread-safe. Maintains a sliding window of metrics for trend analysis.
    """

    def __init__(self) -> None:
        self._metric_history: deque[SystemMetrics] = deque(maxlen=100)
        self._proposals: list[EvolutionProposal] = []

    def ingest_metrics(self, metrics: SystemMetrics) -> None:
        """Ingest a system metrics snapshot for analysis."""
        self._metric_history.append(metrics)

    def analyze_runtime(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Analyze runtime performance for improvement opportunities."""
        proposals = []

        # High latency
        if metrics.runtime_avg_latency_ms > 500:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_latency",
                evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                target_component="runtime.orchestrator",
                description=f"Runtime latency too high: {metrics.runtime_avg_latency_ms:.0f}ms (threshold 500ms)",
                expected_gain=20.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.7,
                tags=["latency", "runtime"],
            ))

        # High error rate
        if metrics.runtime_error_rate > 0.10:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_errors",
                evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                target_component="runtime.orchestrator",
                description=f"Runtime error rate high: {metrics.runtime_error_rate*100:.1f}%",
                expected_gain=15.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
                tags=["errors", "runtime"],
            ))

        # Model score low
        if metrics.runtime_model_score < 0.5:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_model",
                evolution_type=EvolutionType.MODEL_SWITCH,
                target_component="runtime.orchestrator",
                description=f"Model score low: {metrics.runtime_model_score:.2f}, consider model switch",
                expected_gain=30.0,
                risk_level=RiskLevel.HIGH,
                confidence=0.6,
                tags=["model", "runtime"],
            ))

        return proposals

    def analyze_agents(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Analyze agent performance."""
        proposals = []

        if metrics.agent_success_rate < 0.6:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_agent_perf",
                evolution_type=EvolutionType.AGENT_IMPROVEMENT,
                target_component="agent.supervisor",
                description=f"Agent success rate low: {metrics.agent_success_rate*100:.1f}%",
                expected_gain=25.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.75,
                tags=["agents", "success_rate"],
            ))

        if metrics.agent_avg_duration_ms > 10000:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_agent_speed",
                evolution_type=EvolutionType.AGENT_IMPROVEMENT,
                target_component="agent.supervisor",
                description=f"Agent avg duration high: {metrics.agent_avg_duration_ms:.0f}ms",
                expected_gain=10.0,
                risk_level=RiskLevel.LOW,
                confidence=0.6,
                tags=["agents", "duration"],
            ))

        return proposals

    def analyze_skills(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Analyze skill usage."""
        proposals = []

        # Underutilized skills
        if metrics.skill_unused_ratio > 0.5:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_unused_skills",
                evolution_type=EvolutionType.SKILL_IMPROVEMENT,
                target_component="skills.distribution",
                description=f"High skill unused ratio: {metrics.skill_unused_ratio*100:.1f}%",
                expected_gain=15.0,
                risk_level=RiskLevel.LOW,
                confidence=0.8,
                tags=["skills", "unused"],
            ))

        # Low skill success
        if metrics.skill_success_rate < 0.7:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_skill_fail",
                evolution_type=EvolutionType.SKILL_IMPROVEMENT,
                target_component="skills.distribution",
                description=f"Skill success rate low: {metrics.skill_success_rate*100:.1f}%",
                expected_gain=20.0,
                risk_level=RiskLevel.LOW,
                confidence=0.7,
                tags=["skills", "success"],
            ))

        return proposals

    def analyze_missions(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Analyze mission execution patterns."""
        proposals = []

        if metrics.mission_blocked_count > 5:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_blocked",
                evolution_type=EvolutionType.WORKFLOW_OPTIMIZATION,
                target_component="execution.engine",
                description=f"High blocked missions: {metrics.mission_blocked_count}",
                expected_gain=25.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.7,
                tags=["missions", "blocked"],
            ))

        if metrics.mission_repeat_rate > 0.3:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_repeats",
                evolution_type=EvolutionType.WORKFLOW_OPTIMIZATION,
                target_component="execution.engine",
                description=f"High mission repeat rate: {metrics.mission_repeat_rate*100:.1f}%",
                expected_gain=10.0,
                risk_level=RiskLevel.LOW,
                confidence=0.6,
                tags=["missions", "repeats"],
            ))

        return proposals

    def analyze_memory(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Analyze memory system performance."""
        proposals = []

        if metrics.memory_hit_rate < 0.5:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_memory_hit",
                evolution_type=EvolutionType.MEMORY_OPTIMIZATION,
                target_component="memory.unified",
                description=f"Memory hit rate low: {metrics.memory_hit_rate*100:.1f}%",
                expected_gain=20.0,
                risk_level=RiskLevel.LOW,
                confidence=0.7,
                tags=["memory", "hit_rate"],
            ))

        if metrics.memory_prune_rate > 0.3:
            proposals.append(EvolutionProposal(
                proposal_id=f"evo_{int(time.time())}_memory_prune",
                evolution_type=EvolutionType.MEMORY_OPTIMIZATION,
                target_component="memory.unified",
                description=f"High memory prune rate: {metrics.memory_prune_rate*100:.1f}%",
                expected_gain=5.0,
                risk_level=RiskLevel.LOW,
                confidence=0.5,
                tags=["memory", "prune"],
            ))

        return proposals

    def analyze_all(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Run all analyses and return all proposals."""
        proposals = []
        proposals.extend(self.analyze_runtime(metrics))
        proposals.extend(self.analyze_agents(metrics))
        proposals.extend(self.analyze_skills(metrics))
        proposals.extend(self.analyze_missions(metrics))
        proposals.extend(self.analyze_memory(metrics))
        for p in proposals:
            self._proposals.append(p)
        return proposals

    def get_proposals(self, status: EvolutionStatus | None = None) -> list[EvolutionProposal]:
        if status:
            return [p for p in self._proposals if p.status == status]
        return list(self._proposals)

    def update_proposal_status(self, proposal_id: str, status: EvolutionStatus) -> bool:
        for p in self._proposals:
            if p.proposal_id == proposal_id:
                p.status = status
                return True
        return False

    def stats(self) -> dict[str, Any]:
        proposals = self._proposals
        return {
            "total_proposals": len(proposals),
            "by_type": {t.value: sum(1 for p in proposals if p.evolution_type == t) for t in EvolutionType},
            "by_status": {s.value: sum(1 for p in proposals if p.status == s) for s in EvolutionStatus},
            "metrics_samples": len(self._metric_history),
        }
