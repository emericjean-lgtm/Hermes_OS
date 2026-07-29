"""Response Generator for Hermes OS (HOS-064).

Generates contextual responses based on user intent, conversation context,
and Hermes OS system state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .conversation_models import (
    ConversationContext,
    ConversationResponse,
    IntentResult,
    IntentType,
    Message,
    MessageRole,
)


class ResponseGenerator:
    """Generates Hermes responses based on intent and context."""

    def __init__(self) -> None:
        self._templates: dict[str, str] = self._load_templates()

    def generate(self, intent: IntentResult, context: ConversationContext,
                 user_message: str) -> ConversationResponse:
        intent_type = intent.intent
        content = self._build_content(intent_type, intent, context, user_message)
        requires_approval, approval_req = self._check_approval(intent_type, intent)

        message = Message(
            role=MessageRole.HERMES,
            content=content,
            metadata={"intent": intent_type.value, "confidence": intent.confidence},
        )

        suggestions = self._get_suggested_actions(intent_type, context)

        return ConversationResponse(
            session_id="",
            message=message,
            intent=intent,
            requires_approval=requires_approval,
            approval_request=approval_req,
            suggested_actions=suggestions,
        )

    def _build_content(self, intent: IntentType, result: IntentResult,
                       ctx: ConversationContext, user_msg: str) -> str:
        template = self._templates.get(intent.value, self._templates["unknown"])
        return template.format(
            user_message=user_msg[:100],
            domain=result.domain,
            confidence=result.confidence * 100,
            complexity=result.complexity,
            agents=", ".join(ctx.active_agents) if ctx.active_agents else "none",
            mission=ctx.active_mission_id or "none",
            goal=ctx.active_goal_id or "none",
        )

    def _check_approval(self, intent: IntentType,
                        result: IntentResult) -> tuple[bool, dict[str, Any] | None]:
        high_risk_intents = {IntentType.COMMAND, IntentType.REFACTOR, IntentType.DEBUG}
        if intent in high_risk_intents and result.complexity > 0.6:
            return True, {
                "action": f"{intent.value}_mission",
                "risk": "HIGH" if result.complexity > 0.8 else "MEDIUM",
                "complexity": result.complexity,
                "domain": result.domain,
                "description": f"Create a {intent.value} mission in {result.domain} domain",
            }
        return False, None

    def _get_suggested_actions(self, intent: IntentType,
                               ctx: ConversationContext) -> list[dict[str, str]]:
        suggestions: list[dict[str, str]] = []
        base_actions = {
            IntentType.OPTIMIZATION: [
                {"label": "Lancer optimisation", "action": "start_mission"},
                {"label": "Analyser d'abord", "action": "analyze_first"},
            ],
            IntentType.ANALYSIS: [
                {"label": "Lancer analyse", "action": "start_mission"},
                {"label": "Voir détails", "action": "show_details"},
            ],
            IntentType.DEBUG: [
                {"label": "Démarrer debug", "action": "start_mission"},
                {"label": "Diagnostic rapide", "action": "quick_diag"},
            ],
            IntentType.REFACTOR: [
                {"label": "Planifier refactoring", "action": "plan_mission"},
                {"label": "Analyse impact", "action": "impact_analysis"},
            ],
            IntentType.GREETING: [
                {"label": "Analyser projet", "action": "analyze_project"},
                {"label": "Voir missions", "action": "list_missions"},
                {"label": "État système", "action": "system_status"},
            ],
        }
        return base_actions.get(intent, [
            {"label": "En savoir plus", "action": "clarify"},
            {"label": "Voir options", "action": "show_options"},
        ])

    def _load_templates(self) -> dict[str, str]:
        return {
            "optimization": (
                "🔍 **Analyse d'optimisation détectée**\n\n"
                "J'ai compris que vous souhaitez optimiser votre projet. "
                "Voici ce que je propose :\n\n"
                "- **Domaine** : {domain}\n"
                "- **Confiance** : {confidence:.0f}%\n"
                "- **Complexité** : {complexity:.2f}\n\n"
                "Je peux lancer une mission d'optimisation complète avec "
                "analyse des performances, recommandations et application "
                "des améliorations."
            ),
            "analysis": (
                "📊 **Analyse demandée**\n\n"
                "Je lance une analyse de votre projet dans le domaine **{domain}**.\n"
                "Confiance : {confidence:.0f}%\n\n"
                "Je vais examiner le code, la structure et les performances "
                "pour vous fournir un rapport détaillé."
            ),
            "debug": (
                "🐛 **Diagnostic de bug en cours**\n\n"
                "J'ai détecté une demande de débogage. "
                "Laissez-moi analyser le problème.\n\n"
                "- **Domaine** : {domain}\n"
                "- **Complexité estimée** : {complexity:.2f}\n\n"
                "Je vais utiliser Oh My Pi pour le débogage LSP et "
                "mes agents d'analyse pour identifier la cause racine."
            ),
            "refactor": (
                "🔄 **Refactoring planifié**\n\n"
                "J'ai compris que vous souhaitez refactoriser votre code. "
                "Voici le plan proposé :\n\n"
                "- Analyse de la structure actuelle\n"
                "- Identification des améliorations\n"
                "- Application des modifications\n"
                "- Tests de validation\n\n"
                "Voulez-vous que je commence par une analyse d'impact ?"
            ),
            "documentation": (
                "📝 **Génération de documentation**\n\n"
                "Je peux générer de la documentation pour votre projet. "
                "Je vais analyser le code et produire :\n\n"
                "- Documentation technique\n"
                "- README mis à jour\n"
                "- Guides d'utilisation\n"
                "- Documentation API"
            ),
            "command": (
                "⚡ **Commande reçue**\n\n"
                "Je vais exécuter votre demande dans le domaine **{domain}**.\n\n"
                "Mission active : {mission}\n"
                "Agents disponibles : {agents}\n\n"
                "Je prépare le plan d'exécution..."
            ),
            "greeting": (
                "👋 **Bonjour !**\n\n"
                "Je suis Hermes, votre assistant IA de développement. "
                "Je peux vous aider à :\n\n"
                "🔍 **Analyser** votre code et vos projets\n"
                "⚡ **Optimiser** les performances\n"
                "🐛 **Déboguer** les problèmes\n"
                "🔄 **Refactoriser** le code\n"
                "📝 **Documenter** votre travail\n\n"
                "Que souhaitez-vous faire ?"
            ),
            "approval": (
                "✅ **Approbation enregistrée**\n\n"
                "J'ai bien pris en compte votre validation. "
                "Je poursuis l'exécution du plan."
            ),
            "cancel": (
                "🛑 **Action annulée**\n\n"
                "J'ai annulé l'opération en cours. "
                "N'hésitez pas à me donner de nouvelles instructions."
            ),
            "question": (
                "💡 **Réponse**\n\n"
                "Voici ce que je peux vous dire à ce sujet...\n\n"
                "Je peux également lancer une analyse plus approfondie "
                "si vous le souhaitez."
            ),
            "unknown": (
                "🤔 **Je n'ai pas bien compris**\n\n"
                "Pouvez-vous reformuler votre demande ?\n\n"
                "Je peux vous aider à :\n"
                "- Analyser du code\n"
                "- Déboguer des problèmes\n"
                "- Optimiser les performances\n"
                "- Refactoriser du code\n"
                "- Générer de la documentation"
            ),
        }
