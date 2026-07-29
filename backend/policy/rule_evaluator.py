"""Rule Evaluator for HOS-046.

Evaluates configurable rules against operation contexts.
Supports built-in rules: git_merge, workspace_delete, model_download, etc.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.policy.policy_models import (
    EvaluationContext,
    PolicyDecision,
    PolicyRule,
    RuleCategory,
)


class RuleEvaluator:
    """Evaluates policy rules against operation contexts.

    Built-in rules for common operations. Custom rules via register().
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._rules: dict[str, PolicyRule] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the default governance rules."""
        builtins = [
            PolicyRule(
                name="git_merge_requires_review",
                description="Git merge operations require human review",
                category=RuleCategory.OPERATION,
                condition="operation == 'git_merge'",
                decision=PolicyDecision.REVIEW_REQUIRED,
                require_approval_count=1,
                priority=10,
            ),
            PolicyRule(
                name="workspace_delete_requires_approval",
                description="Workspace deletion requires approval",
                category=RuleCategory.OPERATION,
                condition="operation == 'workspace_delete'",
                decision=PolicyDecision.REVIEW_REQUIRED,
                require_approval_count=1,
                priority=10,
            ),
            PolicyRule(
                name="model_download_allowed",
                description="Model downloads are allowed by default",
                category=RuleCategory.RESOURCE,
                condition="operation == 'model_download'",
                decision=PolicyDecision.ALLOW,
                priority=5,
            ),
            PolicyRule(
                name="cloud_runtime_requires_review",
                description="Cloud runtime usage requires review",
                category=RuleCategory.SECURITY,
                condition="operation == 'runtime_cloud'",
                decision=PolicyDecision.REVIEW_REQUIRED,
                require_approval_count=1,
                priority=10,
            ),
            PolicyRule(
                name="internet_access_allowed",
                description="Internet access is allowed by default",
                category=RuleCategory.INTEGRATION,
                condition="operation == 'internet_access'",
                decision=PolicyDecision.ALLOW,
                priority=1,
            ),
            PolicyRule(
                name="system_modification_denied",
                description="System modifications are denied",
                category=RuleCategory.SECURITY,
                condition="operation == 'system_modification'",
                decision=PolicyDecision.DENY,
                priority=20,
            ),
            PolicyRule(
                name="external_tool_requires_review",
                description="External tool usage requires review",
                category=RuleCategory.SECURITY,
                condition="operation == 'external_tool'",
                decision=PolicyDecision.REVIEW_REQUIRED,
                priority=8,
            ),
            PolicyRule(
                name="rollback_requires_approval",
                description="Git rollback operations require approval",
                category=RuleCategory.OPERATION,
                condition="operation == 'git_rollback'",
                decision=PolicyDecision.REVIEW_REQUIRED,
                require_approval_count=1,
                priority=10,
            ),
            PolicyRule(
                name="high_risk_requires_review",
                description="High-risk operations always require review",
                category=RuleCategory.SECURITY,
                condition="risk_level >= 7",
                decision=PolicyDecision.REVIEW_REQUIRED,
                priority=15,
            ),
            PolicyRule(
                name="critical_risk_denied",
                description="Critical risk operations are denied",
                category=RuleCategory.SECURITY,
                condition="risk_level >= 9",
                decision=PolicyDecision.DENY,
                priority=25,
            ),
        ]
        for r in builtins:
            self._rules[r.rule_id] = r

    def register(self, rule: PolicyRule) -> None:
        with self._lock:
            self._rules[rule.rule_id] = rule

    def remove(self, rule_id: str) -> bool:
        with self._lock:
            return self._rules.pop(rule_id, None) is not None

    def evaluate(
        self, context: EvaluationContext
    ) -> tuple[PolicyDecision, list[str], list[str]]:
        """Evaluate all matching rules against a context.

        Returns (strictest_decision, matched_rule_ids, reasons).
        Order: DENY > REVIEW_REQUIRED > ALLOW
        """
        decision = PolicyDecision.ALLOW
        matched: list[str] = []
        reasons: list[str] = []

        with self._lock:
            sorted_rules = sorted(
                self._rules.values(),
                key=lambda r: (r.enabled, r.priority),
                reverse=True,
            )

            for rule in sorted_rules:
                if not rule.enabled:
                    continue
                if not rule.applies_to_all:
                    if (rule.agent_ids and
                            context.agent_id not in rule.agent_ids):
                        continue
                    if (rule.mission_ids and
                            context.mission_id not in rule.mission_ids):
                        continue

                if self._matches(rule, context):
                    matched.append(rule.rule_id)
                    reasons.append(f"{rule.name}: {rule.decision.value}")

                    if rule.decision == PolicyDecision.DENY:
                        decision = PolicyDecision.DENY
                    elif (rule.decision == PolicyDecision.REVIEW_REQUIRED and
                          decision != PolicyDecision.DENY):
                        decision = PolicyDecision.REVIEW_REQUIRED

        return decision, matched, reasons

    def get_best_rule(
        self, context: EvaluationContext
    ) -> Optional[PolicyRule]:
        """Get the single most restrictive matching rule."""
        decision, matched, _ = self.evaluate(context)
        if not matched:
            return None
        # Return the rule matching the final decision with highest priority
        with self._lock:
            for rid in matched:
                r = self._rules.get(rid)
                if r and r.decision == decision:
                    return r
        return None

    def get_all(self) -> list[PolicyRule]:
        with self._lock:
            return list(self._rules.values())

    def get_by_category(self, category: RuleCategory) -> list[PolicyRule]:
        with self._lock:
            return [r for r in self._rules.values() if r.category == category]

    def _matches(self, rule: PolicyRule, ctx: EvaluationContext) -> bool:
        """Check if a rule's condition matches the context."""
        cond = rule.condition

        if cond.startswith("operation == '"):
            target = cond.split("'")[1]
            return ctx.operation == target

        if cond.startswith("risk_level >= "):
            threshold = float(cond.split(">= ")[1])
            return ctx.risk_level >= threshold

        if cond == "risk_level >= 7":
            return ctx.risk_level >= 7

        if cond == "risk_level >= 9":
            return ctx.risk_level >= 9

        # Generic: try eval with safe locals
        try:
            return bool(
                eval(cond, {"__builtins__": {}}, {
                    "operation": ctx.operation,
                    "risk_level": ctx.risk_level,
                    "agent_id": ctx.agent_id,
                    "mission_id": ctx.mission_id,
                })
            )
        except Exception:
            return False

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._rules),
                "enabled": sum(1 for r in self._rules.values() if r.enabled),
                "by_category": {
                    c.value: sum(1 for r in self._rules.values() if r.category == c)
                    for c in RuleCategory
                },
                "by_decision": {
                    d.value: sum(1 for r in self._rules.values() if r.decision == d)
                    for d in PolicyDecision
                },
            }
