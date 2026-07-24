"""Aegis's deterministic decision engine (cahier des charges §17).

This is a rules engine on purpose, not an LLM call: security gates need
to be predictable and auditable. phi4:14b (Aegis's configured model, see
config/models.yaml) is reserved for a later advisory pass on ambiguous
cases ("doute élevé sur l'intention", §17.3) — the deterministic engine
below is the non-negotiable first line of defense and never depends on
model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.security.permission_matrix import PermissionMatrix

_AUTONOMY_ORDER = {"low": 0, "medium": 1, "high": 2}


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HUMAN_VALIDATION = "require_human_validation"


@dataclass(frozen=True)
class ActionRequest:
    action_type: str
    description: str
    target_path: str | None = None  # required when the category is path_based
    requesting_agent: str = "unknown"  # message bus "from" — see agents/aegis.py
    task_id: str | None = None  # message bus "task_id", when this action is part of a task
    project_id: str | None = None  # message bus "project_id", when this action is project-scoped


@dataclass(frozen=True)
class AegisDecision:
    verdict: Verdict
    reason: str
    action_type: str


class AegisEngine:
    def __init__(self, matrix: PermissionMatrix, allowed_paths: list[str]) -> None:
        self._matrix = matrix
        self._allowed_paths = [Path(p).resolve() for p in allowed_paths]

    def evaluate(self, action: ActionRequest) -> AegisDecision:
        category = self._matrix.get_category(action.action_type)

        if category is None:
            return AegisDecision(
                verdict=Verdict.REQUIRE_HUMAN_VALIDATION,
                reason=(
                    f"Unknown action category {action.action_type!r} — "
                    "treated as out of scope (§17.3)."
                ),
                action_type=action.action_type,
            )

        if category.path_based:
            if not action.target_path:
                return AegisDecision(
                    verdict=Verdict.DENY,
                    reason=f"{action.action_type} requires target_path but none was given.",
                    action_type=action.action_type,
                )
            if not self._is_within_whitelist(action.target_path):
                return AegisDecision(
                    verdict=Verdict.DENY,
                    reason=(
                        f"{action.target_path!r} is outside ALLOWED_PATHS — "
                        "a hard boundary, not negotiable by autonomy level (§17.1)."
                    ),
                    action_type=action.action_type,
                )

        if category.mandatory_validation:
            return AegisDecision(
                verdict=Verdict.REQUIRE_HUMAN_VALIDATION,
                reason=f"{action.action_type} always requires human validation (§17.3).",
                action_type=action.action_type,
            )

        if not category.mutating:
            return AegisDecision(
                verdict=Verdict.ALLOW,
                reason=f"{action.action_type} is read-only and in scope.",
                action_type=action.action_type,
            )

        required = category.min_autonomy_for_auto_allow or "high"
        current_rank = _AUTONOMY_ORDER.get(self._matrix.autonomy_level, 0)
        required_rank = _AUTONOMY_ORDER.get(required, 2)

        if current_rank >= required_rank:
            return AegisDecision(
                verdict=Verdict.ALLOW,
                reason=(
                    f"{action.action_type} auto-allowed at autonomy level "
                    f"{self._matrix.autonomy_level!r}."
                ),
                action_type=action.action_type,
            )

        return AegisDecision(
            verdict=Verdict.REQUIRE_HUMAN_VALIDATION,
            reason=(
                f"{action.action_type} needs autonomy level {required!r} to "
                f"auto-allow; current level is {self._matrix.autonomy_level!r}."
            ),
            action_type=action.action_type,
        )

    def _is_within_whitelist(self, target_path: str) -> bool:
        if not self._allowed_paths:
            return False
        resolved = Path(target_path).resolve()
        return any(
            resolved == allowed or resolved.is_relative_to(allowed)
            for allowed in self._allowed_paths
        )
