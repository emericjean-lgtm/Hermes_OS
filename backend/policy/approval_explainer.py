"""Approval Explainer for Hermes OS (HOS-064).

Enriches human approval requests with clear explanations
of risk, impact, and rollback options before users make decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.explainability.explanation_models import ApprovalRequest, RiskLevel


class ApprovalExplainer:
    """Generates clear, structured approval requests for human review."""

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[dict[str, Any]] = []

    def request_approval(self, action: str, description: str,
                         risk_level: str = "medium",
                         affected_agents: list[str] | None = None,
                         rollback_possible: bool = True,
                         explanation_data: dict[str, Any] | None = None
                         ) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=f"apr_{uuid.uuid4().hex[:8]}",
            action=action,
            description=description,
            risk_level=RiskLevel(risk_level) if risk_level in RiskLevel._value2member_map_ else RiskLevel.MEDIUM,
            impact=self._describe_impact(action, affected_agents),
            affected_agents=affected_agents or [],
            rollback_possible=rollback_possible,
            status="pending",
        )
        self._pending[req.request_id] = req
        self._history.append({
            "request_id": req.request_id,
            "action": action,
            "risk_level": risk_level,
            "status": "pending",
            "created_at": req.created_at,
        })
        return req

    def approve(self, request_id: str) -> ApprovalRequest | None:
        req = self._pending.get(request_id)
        if req:
            req.status = "approved"
            req.decided_at = datetime.now(timezone.utc).isoformat()
            self._update_history(request_id, "approved")
            return req
        return None

    def reject(self, request_id: str) -> ApprovalRequest | None:
        req = self._pending.get(request_id)
        if req:
            req.status = "rejected"
            req.decided_at = datetime.now(timezone.utc).isoformat()
            self._update_history(request_id, "rejected")
            return req
        return None

    def get_pending(self) -> list[ApprovalRequest]:
        return [r for r in self._pending.values() if r.status == "pending"]

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._pending.get(request_id)

    def format_for_user(self, request: ApprovalRequest) -> str:
        lines = [
            "🔔 **Action nécessitant votre approbation**",
            "",
            f"**Action :** {request.action}",
            f"**Description :** {request.description}",
            f"**Niveau de risque :** {request.risk_level.value.upper()}",
            f"**Impact :** {request.impact}",
        ]
        if request.affected_agents:
            lines.append(f"**Agents concernés :** {', '.join(request.affected_agents)}")
        lines.append(f"**Rollback possible :** {'Oui' if request.rollback_possible else 'Non - Action irréversible'}")
        lines.append("")
        lines.append("Souhaitez-vous approuver cette action ? (oui/non)")
        return "\n".join(lines)

    def _describe_impact(self, action: str, agents: list[str] | None) -> str:
        agent_count = len(agents) if agents else 0
        if "supprimer" in action.lower() or "delete" in action.lower():
            return "Cette action supprime des données de manière permanente"
        if "modifier" in action.lower() or "modify" in action.lower() or "edit" in action.lower():
            return f"Cette action modifie des ressources actives ({agent_count} agent(s) concerné(s))"
        if "exécuter" in action.lower() or "execute" in action.lower():
            return f"Cette action exécute des opérations potentiellement longues ({agent_count} agent(s))"
        if "déployer" in action.lower() or "deploy" in action.lower():
            return "Cette action déploie des changements en production"
        return f"Action affectant {agent_count} agent(s) dans le système"

    def _update_history(self, request_id: str, status: str) -> None:
        for entry in self._history:
            if entry["request_id"] == request_id:
                entry["status"] = status
                entry["decided_at"] = datetime.now(timezone.utc).isoformat()
                break
