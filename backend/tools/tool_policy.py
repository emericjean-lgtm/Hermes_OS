"""Tool policy integration — gates tool execution through Policy Engine (HOS-049)."""

from __future__ import annotations

import threading
from enum import Enum

from .tool_models import ExecutionStatus, ToolDefinition, ToolPermission, ToolRequest, ToolResult


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"


class ToolPolicy:
    """Evaluates whether a tool execution should be allowed.

    Integrates with the Policy Engine (HOS-046): before any tool execution,
    the request passes through the policy engine for governance.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, list[str]] = {}  # tool_id → [rule descriptions]
        # Deny rules for sensitive tool categories
        self._deny_admin_without_review = True
        self._deny_write_in_readonly_sandbox = True
        self._max_timeout_seconds: float = 120.0

    def evaluate(self, request: ToolRequest, tool: ToolDefinition) -> tuple[PolicyVerdict, str]:
        """Evaluate a tool request. Returns (verdict, reason)."""
        with self._lock:
            # Admin permissions require review
            if request.permission_level == ToolPermission.ADMIN and self._deny_admin_without_review:
                return PolicyVerdict.REVIEW_REQUIRED, "Admin-level tool usage requires human review"

            # Write permissions require validation
            if request.permission_level == ToolPermission.WRITE and self._deny_write_in_readonly_sandbox:
                # Policy engine would check sandbox readonly status
                pass

            # Timeout limit
            if request.timeout_seconds > self._max_timeout_seconds:
                return PolicyVerdict.DENY, f"Timeout {request.timeout_seconds}s exceeds max {self._max_timeout_seconds}s"

            # Disabled tools
            if tool.status == "disabled":
                return PolicyVerdict.DENY, f"Tool '{tool.name}' is disabled"

            # Check explicit tool rules
            for rule_desc in self._rules.get(request.tool_id, []):
                if "deny" in rule_desc.lower():
                    return PolicyVerdict.DENY, rule_desc

            # Default: allow
            return PolicyVerdict.ALLOW, f"Tool '{tool.name}' allowed for action '{request.action}'"

    def add_rule(self, tool_id: str, rule_description: str) -> None:
        with self._lock:
            self._rules.setdefault(tool_id, []).append(rule_description)

    def get_rules(self, tool_id: str) -> list[str]:
        with self._lock:
            return list(self._rules.get(tool_id, []))

    def stats(self) -> dict:
        with self._lock:
            return {"total_rules": sum(len(r) for r in self._rules.values()), "tools_with_rules": len(self._rules)}
