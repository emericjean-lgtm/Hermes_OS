"""Evolution Engine for Hermes OS (HOS-058).

Central orchestrator that manages the full self-evolution pipeline:

Collect Metrics → Analyze → Detect Improvement → Create Proposal
→ Simulate → Validate → Apply → Store Experience
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable

from .evolution_analyzer import EvolutionAnalyzer
from .evolution_models import (
    EVOLUTION_EVENTS,
    EvolutionProposal,
    EvolutionReport,
    EvolutionStatus,
    EvolutionType,
    OptimizationPattern,
    SystemMetrics,
)
from .evolution_simulator import EvolutionSimulator
from .evolution_validator import EvolutionValidator, ValidationVerdict
from .improvement_detector import ImprovementDetector


class EvolutionEngine:
    """Central orchestrator for self-evolution.

    Pipeline:
        1. Collect metrics
        2. Analyze (via EvolutionAnalyzer)
        3. Detect improvements (via ImprovementDetector)
        4. Create proposals
        5. Simulate impact (via EvolutionSimulator)
        6. Validate (via EvolutionValidator + Security)
        7. Apply
        8. Store experience
    """

    def __init__(self, on_event: Callable | None = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        self.analyzer = EvolutionAnalyzer()
        self.detector = ImprovementDetector()
        self.simulator = EvolutionSimulator()
        self.validator = EvolutionValidator()

        self._proposals: dict[str, EvolutionProposal] = {}
        self._reports: deque[EvolutionReport] = deque(maxlen=50)
        self._applied_count = 0
        self._total_gain = 0.0

    def ingest_metrics(self, metrics: SystemMetrics) -> list[EvolutionProposal]:
        """Ingest system metrics and run full analysis pipeline."""
        with self._lock:
            self.analyzer.ingest_metrics(metrics)

            # Analyze
            proposals = self.analyzer.analyze_all(metrics)
            for p in proposals:
                self._proposals[p.proposal_id] = p
                self._publish(EVOLUTION_EVENTS["proposal_created"], {
                    "proposal_id": p.proposal_id,
                    "type": p.evolution_type.value,
                    "target": p.target_component,
                    "description": p.description,
                })

            # Detect additional improvements
            self._run_detection(metrics)

            return proposals

    def run_full_pipeline(self, metrics: SystemMetrics) -> list[dict]:
        """Run the complete evolution pipeline.

        Returns results for each processed proposal.
        """
        proposals = self.ingest_metrics(metrics)
        results = []

        for proposal in proposals:
            # Simulate
            experiment = self.simulator.simulate(proposal)
            proposal.status = EvolutionStatus.SIMULATED
            self._publish(EVOLUTION_EVENTS["simulation_completed"], {
                "proposal_id": proposal.proposal_id,
                "result": experiment.result,
                "conclusion": experiment.conclusion,
            })

            # Validate
            verdict = self.validator.validate(proposal)

            if verdict == ValidationVerdict.ALLOW:
                self._apply_proposal(proposal)
                results.append({
                    "proposal_id": proposal.proposal_id,
                    "action": "applied",
                    "verdict": "allow",
                })
            elif verdict == ValidationVerdict.REVIEW:
                proposal.status = EvolutionStatus.DETECTED  # Keep for review
                results.append({
                    "proposal_id": proposal.proposal_id,
                    "action": "flagged_for_review",
                    "verdict": "review",
                })
            else:
                proposal.status = EvolutionStatus.REJECTED
                self._publish(EVOLUTION_EVENTS["failed"], {
                    "proposal_id": proposal.proposal_id,
                    "reason": "Rejected by validator",
                })
                results.append({
                    "proposal_id": proposal.proposal_id,
                    "action": "rejected",
                    "verdict": "deny",
                })

        return results

    def approve(self, proposal_id: str) -> bool:
        """Manually approve a proposal for application."""
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            proposal.status = EvolutionStatus.APPROVED
            self._publish(EVOLUTION_EVENTS["approved"], {
                "proposal_id": proposal_id,
                "type": proposal.evolution_type.value,
            })
            self._apply_proposal(proposal)
            return True

    def reject(self, proposal_id: str) -> bool:
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            proposal.status = EvolutionStatus.REJECTED
            return True

    def generate_report(self) -> EvolutionReport:
        """Generate an evolution report for the current period."""
        with self._lock:
            proposals = list(self._proposals.values())
            applied = [p for p in proposals if p.status == EvolutionStatus.APPLIED]
            rejected = [p for p in proposals if p.status == EvolutionStatus.REJECTED]

            report = EvolutionReport(
                report_id=f"report_{int(__import__('time').time())}",
                improvements_found=len(proposals),
                applied_changes=[p.description for p in applied],
                rejected_changes=[p.description for p in rejected],
                total_gain_percent=self._total_gain,
                proposals=[p.proposal_id for p in proposals],
            )
            self._reports.append(report)
            self._publish(EVOLUTION_EVENTS["report_generated"], {
                "report_id": report.report_id,
                "improvements_found": report.improvements_found,
                "applied": len(report.applied_changes),
            })
            return report

    def get_reports(self, limit: int = 10) -> list[EvolutionReport]:
        with self._lock:
            return list(self._reports)[-limit:]

    def get_proposals(self, status: EvolutionStatus | None = None) -> list[EvolutionProposal]:
        with self._lock:
            proposals = list(self._proposals.values())
            if status:
                proposals = [p for p in proposals if p.status == status]
            return sorted(proposals, key=lambda p: p.created_at, reverse=True)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            proposals = list(self._proposals.values())
            return {
                "total_proposals": len(proposals),
                "applied_count": self._applied_count,
                "total_gain_percent": round(self._total_gain, 1),
                "by_status": {
                    s.value: sum(1 for p in proposals if p.status == s)
                    for s in EvolutionStatus
                },
                "by_type": {
                    t.value: sum(1 for p in proposals if p.evolution_type == t)
                    for t in EvolutionType
                },
                "analyzer": self.analyzer.stats(),
                "detector": self.detector.stats(),
                "simulator": self.simulator.stats(),
                "validator": self.validator.stats(),
            }

    # ── Private ──

    def _run_detection(self, metrics: SystemMetrics) -> None:
        """Run improvement detectors on current metrics."""
        detectors = [
            ("runtime", self.detector.detect_runtime_underperformance(
                metrics.runtime_avg_latency_ms, metrics.runtime_error_rate)),
            ("skills", self.detector.detect_unnecessary_skills(metrics.skill_unused_ratio)),
            ("workflow", self.detector.detect_inefficient_workflow(
                metrics.mission_repeat_rate, metrics.mission_avg_duration_s * 1000)),
        ]
        for source, proposal in detectors:
            if proposal is not None:
                self._proposals[proposal.proposal_id] = proposal

    def _apply_proposal(self, proposal: EvolutionProposal) -> None:
        """Apply an approved proposal."""
        proposal.status = EvolutionStatus.APPLIED
        self._applied_count += 1
        self._total_gain += proposal.expected_gain
        self._publish(EVOLUTION_EVENTS["applied"], {
            "proposal_id": proposal.proposal_id,
            "expected_gain": proposal.expected_gain,
            "target": proposal.target_component,
        })

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass
