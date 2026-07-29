"""Intent Analyzer for Hermes OS (HOS-064).

Transforms natural language user messages into structured intents
with domain, complexity, and suggested actions.
"""

from __future__ import annotations

import re
from typing import Any

from .conversation_models import IntentResult, IntentType


class IntentAnalyzer:
    """Analyzes user messages to determine intent, domain, and complexity."""

    def __init__(self) -> None:
        self._history: list[dict[str, Any]] = []

    # ── Public API ──

    def analyze(self, message: str, context: dict[str, Any] | None = None) -> IntentResult:
        message_lower = message.lower().strip()
        ctx = context or {}

        intent = self._detect_intent(message_lower)
        domain = self._detect_domain(message_lower)
        confidence = self._calculate_confidence(message_lower, intent)
        complexity = self._estimate_complexity(message_lower, domain)
        entities = self._extract_entities(message_lower)
        action = self._suggest_action(intent, domain, entities)

        if intent == IntentType.UNKNOWN and "?" in message:
            intent = IntentType.QUESTION
            confidence = max(confidence, 0.6)

        result = IntentResult(
            intent=intent,
            domain=domain,
            confidence=confidence,
            complexity=complexity,
            suggested_action=action,
            extracted_entities=entities,
        )

        self._history.append({
            "message": message[:80],
            "intent": intent.value,
            "domain": domain,
            "confidence": confidence,
        })

        return result

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._history[-limit:]

    # ── Intent Detection ──

    def _detect_intent(self, text: str) -> IntentType:
        patterns: list[tuple[list[str], IntentType]] = [
            (["optimise", "optimize", "performance", "plus vite", "améliore",
              "improve", "speed up", "faster", "efficacité"], IntentType.OPTIMIZATION),
            (["analyse", "analyse", "regarde", "check", "inspecte",
              "inspect", "examine", "review", "explore"], IntentType.ANALYSIS),
            (["debug", "bug", "erreur", "error", "fix", "répare",
              "repair", "broken", "casse", "fail"], IntentType.DEBUG),
            (["refactor", "refactorise", "restructure", "remanie",
              "reorganise", "reorganize", "clean"], IntentType.REFACTOR),
            (["documente", "document", "doc", "readme", "manuel",
              "guide", "explique", "explain", "how to"], IntentType.DOCUMENTATION),
            (["crée", "create", "génère", "generate", "construis",
              "build", "développe", "develop", "nouveau"], IntentType.COMMAND),
            (["salut", "bonjour", "hello", "hi", "hey", "coucou",
              "bonsoir"], IntentType.GREETING),
            (["oui", "yes", "approuve", "approve", "valide", "validate",
              "accept", "go ahead", "fais-le", "d'accord"], IntentType.APPROVAL),
            (["annule", "cancel", "stop", "arrête", "abort",
              "non", "no", "pas ça"], IntentType.CANCEL),
        ]
        for keywords, intent_type in patterns:
            if any(kw in text for kw in keywords):
                return intent_type
        return IntentType.UNKNOWN

    def _detect_domain(self, text: str) -> str:
        domain_keywords = {
            "software": ["code", "script", "app", "logiciel", "software",
                        "api", "backend", "frontend", "web", "site"],
            "data": ["data", "donnée", "dataset", "base de donnée",
                    "database", "sql", "analyse"],
            "infrastructure": ["server", "serveur", "deploy", "docker",
                              "kubernetes", "cloud", "infra", "réseau"],
            "security": ["security", "sécurité", "vulnérabilité", "permission",
                        "auth", "authentification"],
            "documentation": ["doc", "readme", "manuel", "documentation",
                            "tutorial", "guide"],
        }
        for domain, keywords in domain_keywords.items():
            if any(kw in text for kw in keywords):
                return domain
        return "general"

    def _calculate_confidence(self, text: str, intent: IntentType) -> float:
        if intent == IntentType.UNKNOWN:
            return 0.0
        if intent == IntentType.GREETING:
            return 0.95
        word_count = len(text.split())
        if 3 <= word_count <= 20:
            return 0.85
        if word_count > 20:
            return 0.75
        return 0.6

    def _estimate_complexity(self, text: str, domain: str) -> float:
        base = 0.3
        words = text.split()
        if len(words) > 20:
            base += 0.2
        if len(words) > 40:
            base += 0.2
        complex_signals = ["full", "complet", "complex", "large", "microservices",
                          "entier", "entire", "production", "multi"]
        if any(s in text for s in complex_signals):
            base += 0.15
        if domain in ("infrastructure", "security"):
            base += 0.1
        return min(1.0, base)

    def _extract_entities(self, text: str) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        filename_match = re.search(r'[\w\-]+\.(py|js|ts|rs|go|java|rb|json|yaml|toml|md)', text)
        if filename_match:
            entities["file"] = filename_match.group(0)
        lang_match = re.search(r'\b(python|javascript|typescript|rust|golang|java)\b', text)
        if lang_match:
            entities["language"] = lang_match.group(0)
        number_match = re.search(r'\b(\d+)\b', text)
        if number_match:
            entities["number"] = int(number_match.group(1))
        return entities

    def _suggest_action(self, intent: IntentType, domain: str,
                        entities: dict[str, Any]) -> str:
        action_map = {
            IntentType.OPTIMIZATION: "create_optimization_mission",
            IntentType.ANALYSIS: "create_analysis_mission",
            IntentType.DEBUG: "create_debug_mission",
            IntentType.REFACTOR: "create_refactor_mission",
            IntentType.DOCUMENTATION: "create_documentation_mission",
            IntentType.COMMAND: "create_goal",
            IntentType.GREETING: "greet_user",
            IntentType.APPROVAL: "process_approval",
            IntentType.CANCEL: "cancel_current_action",
            IntentType.QUESTION: "answer_question",
        }
        return action_map.get(intent, "clarify_intent")
