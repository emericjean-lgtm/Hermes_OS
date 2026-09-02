"""Tool policy integration — gates tool execution through Policy Engine (HOS-049)."""

from __future__ import annotations

from typing import Any

import threading
from enum import Enum

from .tool_models import ToolDefinition, ToolPermission, ToolRequest


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"


class ToolPolicy:
    """Evaluates whether a tool execution should be allowed.

    Integrates with the Policy Engine (HOS-046): before any tool execution,
    the request passes through the policy engine for governance.
    """

    def __init__(self, sandbox: Any = None) -> None:
        """`sandbox` : la source de vérité de l'état lecture seule.

        Injecté plutôt qu'importé : la politique ne doit pas décider
        seule quel sandbox fait foi, et un appelant de test doit pouvoir
        en fournir un. `None` reste accepté — voir `evaluate()` pour ce
        que la politique répond alors, et pourquoi elle n'interdit pas.
        """
        self._sandbox = sandbox
        self._lock = threading.RLock()
        self._rules: dict[str, list[str]] = {}  # tool_id → [rule descriptions]
        # Deny rules for sensitive tool categories
        self._deny_admin_without_review = True
        # HOS-238 : ce drapeau existait, valait `True`, et son corps était
        # un `pass`. Il gouverne maintenant une vraie vérification, contre
        # la source de vérité qui existait déjà — `ToolSandbox.read_only`.
        self._deny_write_in_readonly_sandbox = True
        self._max_timeout_seconds: float = 120.0

    def evaluate(self, request: ToolRequest, tool: ToolDefinition) -> tuple[PolicyVerdict, str]:
        """Evaluate a tool request. Returns (verdict, reason)."""
        with self._lock:
            # Admin permissions require review
            if request.permission_level == ToolPermission.ADMIN and self._deny_admin_without_review:
                return PolicyVerdict.REVIEW_REQUIRED, "Admin-level tool usage requires human review"

            # Write permissions: refuse a write into a read-only sandbox.
            #
            # HOS-238 : cette branche était un `pass` derrière un drapeau
            # nommé `_deny_write_in_readonly_sandbox` et un commentaire au
            # conditionnel — « Policy engine *would* check ». Une promesse
            # de sécurité qui ne s'exécutait pas, sur un chemin réel :
            # `KlaatCodeMCPAdapter` appelle `evaluate()` avant chaque
            # exécution, avec `WRITE` sur `EDIT_FILE`.
            #
            # La source de vérité — `ToolSandbox.get_config().read_only` —
            # existait depuis HOS-049, et `registration.py` construisait
            # déjà les deux objets à deux lignes d'écart sans les relier.
            if (request.permission_level == ToolPermission.WRITE
                    and self._deny_write_in_readonly_sandbox):
                if self._sandbox is None:
                    # « Autorisé » et « pas d'avis » ne sont pas la même
                    # réponse. Sans sandbox on ne peut pas savoir, et le
                    # dire vaut mieux que laisser croire qu'on a vérifié.
                    #
                    # On n'interdit pas pour autant : refuser toute
                    # écriture dès qu'aucun sandbox n'est câblé casserait
                    # tous les appelants, et une protection insupportable
                    # se débranche.
                    return (PolicyVerdict.ALLOW,
                            "écriture autorisée sans sandbox — l'état "
                            "lecture seule n'a pas pu être vérifié")
                if self._sandbox.get_config(request.tool_id).read_only:
                    return (PolicyVerdict.DENY,
                            f"le sandbox de '{tool.name}' est en lecture "
                            "seule : l'écriture est refusée")

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
