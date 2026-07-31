"""Evolution Validator for Hermes OS (HOS-058).

Validates evolution proposals through the Security Engine (HOS-057)
and Policy Engine (HOS-046) before application.

Rules:
- ALLOW: internal low-risk optimizations
- REVIEW: skill addition, critical model change, workflow modification
- DENY: security modification, permission changes
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .evolution_models import EvolutionProposal, RiskLevel


class ValidationVerdict(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


class EvolutionValidator:
    """Validates evolution proposals through security and policy rules.

    In production, integrates with SecurityEngine (HOS-057) and
    PolicyEngine (HOS-046) for full pipeline validation.
    """

    def __init__(self) -> None:
        # Auto-allow rules: evolution types that can be auto-applied at each risk level
        self._auto_allow_rules: dict[tuple[str, str], bool] = {
            ("runtime_optimization", "low"): True,
            ("runtime_optimization", "medium"): False,
            ("skill_improvement", "low"): True,
            ("skill_improvement", "medium"): True,
            ("model_switch", "low"): True,
            ("model_switch", "medium"): False,
            ("workflow_optimization", "low"): True,
            ("agent_improvement", "low"): True,
            ("agent_improvement", "medium"): False,
            ("memory_optimization", "low"): True,
            ("architecture_improvement", "low"): False,
            ("architecture_improvement", "medium"): False,
        }
        self._deny_rules: set[str] = {
            "architecture_improvement",
        }

    def validate(self, proposal: EvolutionProposal) -> ValidationVerdict:
        """Validate a proposal against security/policy rules.

        Returns ALLOW, REVIEW, or DENY verdict.
        """
        # DENY rules: never auto-apply
        if proposal.evolution_type.value in self._deny_rules:
            return ValidationVerdict.DENY

        # Check auto-allow rules first (overrides risk level)
        key = (proposal.evolution_type.value, proposal.risk_level.value)
        if self._auto_allow_rules.get(key, False):
            return ValidationVerdict.ALLOW

        # HIGH/CRITICAL risk always needs review
        if proposal.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return ValidationVerdict.REVIEW

        # Default: needs review
        return ValidationVerdict.REVIEW

    def set_auto_allow(self, evo_type: str, risk: str, allow: bool = True) -> None:
        """Override auto-allow rule for a specific type/risk combination."""
        self._auto_allow_rules[(evo_type, risk)] = allow

    def set_deny(self, evo_type: str, deny: bool = True) -> None:
        """Set or clear deny rule for an evolution type."""
        if deny:
            self._deny_rules.add(evo_type)
        else:
            self._deny_rules.discard(evo_type)

    def stats(self) -> dict[str, Any]:
        auto_allow_count = sum(1 for v in self._auto_allow_rules.values() if v)
        return {
            "auto_allow_rules": auto_allow_count,
            "deny_rules": len(self._deny_rules),
            "total_rules": len(self._auto_allow_rules) + len(self._deny_rules),
        }
