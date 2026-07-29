"""API routes for Hermes OS Explainability (HOS-064)."""

from __future__ import annotations

from typing import Any

from .decision_explainer import DecisionExplainer
from .explanation_models import DecisionType

_explainer: DecisionExplainer | None = None


def _get_explainer() -> DecisionExplainer:
    global _explainer
    if _explainer is None:
        _explainer = DecisionExplainer()
    return _explainer


def handle_explain(
    decision_type: str,
    decision: str,
    reason: str,
    confidence: float,
    alternatives: list[dict[str, Any]] | None = None,
    risk_level: str = "low",
    affected: list[str] | None = None,
) -> dict[str, Any]:
    """POST /explain"""
    dt = DecisionType(decision_type) if decision_type in DecisionType._value2member_map_ else DecisionType.AGENT_SELECTION
    explainer = _get_explainer()
    explanation = explainer.explain(dt, decision, reason, confidence, alternatives, risk_level, affected)
    return {
        "success": True,
        "decision_id": explanation.decision_id,
        "decision_type": explanation.decision_type.value,
        "decision": explanation.decision,
        "reason": explanation.reason,
        "confidence": explanation.confidence,
        "risk_level": explanation.risk_level.value,
        "alternatives": [
            {"name": a.name, "reason": a.reason, "score": a.score}
            for a in explanation.alternatives
        ],
        "explanation_text": explainer.format_for_user(explanation),
    }


def handle_get_explanation(decision_id: str) -> dict[str, Any]:
    """GET /explain/{id}"""
    explainer = _get_explainer()
    explanation = explainer.get_explanation(decision_id)
    if not explanation:
        return {"success": False, "error": f"Explanation {decision_id} not found"}
    return {
        "success": True,
        "decision_id": explanation.decision_id,
        "decision_type": explanation.decision_type.value,
        "decision": explanation.decision,
        "reason": explanation.reason,
        "confidence": explanation.confidence,
        "risk_level": explanation.risk_level.value,
        "impact_description": explanation.impact_description,
        "rollback_possible": explanation.rollback_possible,
        "affected_components": explanation.affected_components,
        "alternatives": [
            {"name": a.name, "reason": a.reason, "score": a.score,
             "pros": a.pros, "cons": a.cons}
            for a in explanation.alternatives
        ],
    }


def handle_list_explanations(limit: int = 20) -> dict[str, Any]:
    """GET /explain/history"""
    explainer = _get_explainer()
    return {
        "success": True,
        "explanations": explainer.get_history(limit),
        "total": limit,
    }
