"""Decision Explainer for Hermes OS (HOS-064).

Provides human-readable explanations for every AI decision made
by Hermes OS — agent selection, runtime choice, model selection, etc.
"""

from __future__ import annotations

import uuid
from typing import Any

from .explanation_models import (
    DecisionAlternative,
    DecisionExplanation,
    DecisionType,
    RiskLevel,
)


class DecisionExplainer:
    """Generates human-readable explanations for Hermes decisions."""

    def __init__(self) -> None:
        self._history: list[DecisionExplanation] = []
        self._max_history = 500

    def explain(self, decision_type: DecisionType, decision: str,
                reason: str, confidence: float,
                alternatives: list[dict[str, Any]] | None = None,
                risk_level: str = "low",
                affected: list[str] | None = None) -> DecisionExplanation:
        alts = []
        if alternatives:
            for a in alternatives:
                alts.append(DecisionAlternative(
                    name=a.get("name", "unknown"),
                    reason=a.get("reason", ""),
                    score=a.get("score", 0.0),
                    pros=a.get("pros", []),
                    cons=a.get("cons", []),
                ))

        explanation = DecisionExplanation(
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            decision_type=decision_type,
            decision=decision,
            reason=reason,
            confidence=confidence,
            alternatives=alts,
            risk_level=RiskLevel(risk_level) if risk_level in RiskLevel._value2member_map_ else RiskLevel.LOW,
            impact_description=self._describe_impact(decision_type, decision),
            rollback_possible=confidence > 0.3,
            affected_components=affected or [],
        )
        self._history.append(explanation)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        return explanation

    def explain_agent_selection(self, selected_agent: str, reason: str,
                                 confidence: float,
                                 alternatives: list[dict[str, Any]] | None = None
                                 ) -> DecisionExplanation:
        return self.explain(
            DecisionType.AGENT_SELECTION, selected_agent, reason, confidence,
            alternatives, "low", [selected_agent],
        )

    def explain_runtime_selection(self, runtime: str, reason: str,
                                   confidence: float,
                                   vram_gb: float = 0.0,
                                   alternatives: list[dict[str, Any]] | None = None
                                   ) -> DecisionExplanation:
        return self.explain(
            DecisionType.RUNTIME_SELECTION, runtime, reason, confidence,
            alternatives, "medium", [runtime],
        )

    def explain_model_selection(self, model: str, reason: str,
                                 confidence: float,
                                 vram_available: int = 0,
                                 alternatives: list[dict[str, Any]] | None = None
                                 ) -> DecisionExplanation:
        return self.explain(
            DecisionType.MODEL_SELECTION, model, reason, confidence,
            alternatives, "medium", [model],
        )

    def explain_policy_decision(self, action: str, reason: str,
                                 confidence: float,
                                 risk_level: str = "medium",
                                 alternatives: list[dict[str, Any]] | None = None
                                 ) -> DecisionExplanation:
        return self.explain(
            DecisionType.POLICY_DECISION, action, reason, confidence,
            alternatives, risk_level, [action],
        )

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {
                "decision_id": e.decision_id,
                "decision_type": e.decision_type.value,
                "decision": e.decision,
                "reason": e.reason,
                "confidence": e.confidence,
                "risk_level": e.risk_level.value,
                "timestamp": e.timestamp,
            }
            for e in self._history[-limit:]
        ]

    def get_explanation(self, decision_id: str) -> DecisionExplanation | None:
        for e in self._history:
            if e.decision_id == decision_id:
                return e
        return None

    def format_for_user(self, explanation: DecisionExplanation) -> str:
        lines = [
            f"**Décision : {explanation.decision}**",
            f"",
            f"**Raison :** {explanation.reason}",
            f"**Confiance :** {explanation.confidence * 100:.0f}%",
            f"**Niveau de risque :** {explanation.risk_level.value.upper()}",
        ]
        if explanation.alternatives:
            lines.append(f"")
            lines.append(f"**Alternatives considérées :**")
            for alt in explanation.alternatives:
                lines.append(f"- {alt.name} (score: {alt.score:.2f})")
                if alt.pros:
                    lines.append(f"  ✓ {', '.join(alt.pros)}")
                if alt.cons:
                    lines.append(f"  ✗ {', '.join(alt.cons)}")

        if explanation.affected_components:
            lines.append(f"")
            lines.append(f"**Composants affectés :** {', '.join(explanation.affected_components)}")

        lines.append(f"")
        lines.append(f"**Rollback possible :** {'Oui' if explanation.rollback_possible else 'Non'}")

        return "\n".join(lines)

    def _describe_impact(self, decision_type: DecisionType, decision: str) -> str:
        descriptions = {
            DecisionType.AGENT_SELECTION: f"L'agent {decision} sera utilisé pour cette tâche",
            DecisionType.RUNTIME_SELECTION: f"Le runtime {decision} gérera l'exécution",
            DecisionType.MODEL_SELECTION: f"Le modèle {decision} sera chargé pour l'inférence",
            DecisionType.TOOL_SELECTION: f"L'outil {decision} sera mis à disposition",
            DecisionType.SKILL_SELECTION: f"La compétence {decision} sera activée",
            DecisionType.WORKFLOW_DECISION: f"Le workflow {decision} sera exécuté",
            DecisionType.POLICY_DECISION: f"Politique appliquée : {decision}",
            DecisionType.SECURITY_DECISION: f"Décision de sécurité : {decision}",
        }
        return descriptions.get(decision_type, f"Décision prise : {decision}")
