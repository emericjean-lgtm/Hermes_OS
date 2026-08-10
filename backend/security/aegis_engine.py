"""Aegis's deterministic decision engine (cahier des charges §17).

This is a rules engine on purpose, not an LLM call: security gates need
to be predictable and auditable. phi4-reasoning:14b-q4_K_M (Aegis's
configured model, see config/models.yaml) is used for an advisory pass
on require_human_validation cases only ("doute élevé sur l'intention",
§17.3) — see AegisAgent.advise() in agents/aegis.py. The deterministic
engine below is the non-negotiable first line of defense: it never
depends on model output, and the advisory pass can only annotate its
verdict with context for the human reviewer, never change it.
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
    # Set only by AegisAgent.advise(), never by AegisEngine itself — an
    # LLM's context for the human reviewer on a require_human_validation
    # verdict, not a factor in the verdict (see module docstring).
    advisory: str | None = None


class AegisEngine:
    def __init__(self, matrix: PermissionMatrix, allowed_paths: list[str]) -> None:
        self._matrix = matrix
        self._allowed_paths = [Path(p).resolve() for p in allowed_paths]

    def evaluate(
        self,
        action: ActionRequest,
        *,
        project_root: str | None = None,
        extra_allowed_paths: list[str] | None = None,
    ) -> AegisDecision:
        """project_root, when given, narrows the path_based check further
        than the whitelist — it can only restrict, never widen access.
        This is a per-action scoping tool (an operation known to belong to
        one specific project must not reach a sibling project's files even
        if that sibling is separately whitelisted) — orthogonal to
        extra_allowed_paths below.

        extra_allowed_paths is the opposite: it *widens* the whitelist for
        this call, on top of the engine's own static ALLOWED_PATHS. This is
        how a user-registered, validated Project grants real filesystem
        access without needing a config.yaml edit — the caller
        (AegisAgent._dynamic_allowed_paths) resolves the current set of
        ACTIVE, validation_status="valid" Project roots fresh on every
        call, so this engine stays DB-free and pure (a verdict is still
        fully determined by its inputs) while the *effective* whitelist is
        genuinely dynamic. A Project that is deleted, archived, or fails
        validation stops appearing in that list — and therefore stops
        granting access — the next time this is called, with nothing
        cached here."""
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
            if not self._is_within_whitelist(action.target_path, extra_allowed_paths):
                return AegisDecision(
                    verdict=Verdict.DENY,
                    reason=(
                        f"{action.target_path!r} is outside ALLOWED_PATHS and outside "
                        "every active, validated workspace — a hard boundary, not "
                        "negotiable by autonomy level (§17.1)."
                    ),
                    action_type=action.action_type,
                )
            if project_root is not None and not self._is_within_path(
                action.target_path, project_root
            ):
                return AegisDecision(
                    verdict=Verdict.DENY,
                    reason=(
                        f"{action.target_path!r} is inside the whitelist but outside "
                        f"the project's root {project_root!r} — project scoping only "
                        "narrows access, it never widens it."
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

    def _is_within_whitelist(
        self, target_path: str, extra_allowed_paths: list[str] | None = None
    ) -> bool:
        roots = list(self._allowed_paths)
        if extra_allowed_paths:
            for p in extra_allowed_paths:
                try:
                    roots.append(Path(p).resolve())
                except (OSError, RuntimeError):
                    continue
        if not roots:
            return False
        resolved = Path(target_path).resolve()
        return any(
            resolved == allowed or resolved.is_relative_to(allowed)
            for allowed in roots
        )

    @staticmethod
    def _is_within_path(target_path: str, root: str) -> bool:
        resolved = Path(target_path).resolve()
        resolved_root = Path(root).resolve()
        return resolved == resolved_root or resolved.is_relative_to(resolved_root)
