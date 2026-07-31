"""Response Generator for Hermes OS (HOS-064).

Generates contextual responses based on user intent, conversation context,
and Hermes OS system state.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any

from .conversation_models import (
    ConversationContext,
    ConversationResponse,
    IntentResult,
    IntentType,
    Message,
    MessageRole,
)

logger = logging.getLogger("hermes_os.conversation.response")

_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _background_loop() -> asyncio.AbstractEventLoop:
    """Boucle asyncio dédiée, partagée par toutes les conversations.

    ``handle_message`` est synchrone et peut être appelé depuis le thread d'une
    requête FastAPI, où une boucle tourne déjà : on ne peut donc pas utiliser
    ``asyncio.run``. Même approche que ``RealTaskExecutor``.
    """
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None or _LOOP.is_closed():
            _LOOP = asyncio.new_event_loop()
            threading.Thread(target=_LOOP.run_forever, daemon=True,
                             name="hermes-conversation").start()
        return _LOOP


def _run_sync(coro: Any, timeout: float) -> str:
    """Exécute la coroutine d'inférence et renvoie le texte produit."""
    future = asyncio.run_coroutine_threadsafe(coro, _background_loop())
    try:
        result = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        logger.warning("inférence de conversation expirée après %.0fs", timeout)
        return ""
    return _extract_text(result)


def _extract_text(result: Any) -> str:
    """Le texte de la réponse, quelle que soit la forme rendue par le client."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        for key in ("content", "response", "text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        message = result.get("message")
        if isinstance(message, dict):
            value = message.get("content")
            if isinstance(value, str):
                return value.strip()
    for attr in ("content", "response", "text"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _default_chat(*, messages: list[dict[str, Any]], model: str) -> Any:
    """Client Ollama réel, construit depuis la configuration comme ailleurs."""
    from backend.connectors.ollama_client import OllamaClient
    from backend.core.config import get_settings

    settings = get_settings()
    client = OllamaClient(
        base_url=settings.ollama_api_url,
        timeout=120,
        default_num_ctx=settings.ollama_num_ctx,
    )
    try:
        return await client.chat(messages, model=model)
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result


class ResponseGenerator:
    """Generates Hermes responses based on intent and context."""

    #: Modèle par défaut du chat. Le plus rapide du parc mesuré (123 tps sur
    #: RX 6800) : une conversation doit répondre, pas faire patienter.
    DEFAULT_CHAT_MODEL = "qwen3:4b"

    #: Au-delà, on rend la main plutôt que de laisser l'utilisateur attendre.
    CHAT_TIMEOUT_S = 120.0

    #: Accusés de réception, pas des questions. Quand l'utilisateur valide ou
    #: annule une action, il doit recevoir une confirmation fiable et constante
    #: — pas une phrase improvisée par un modèle, qui peut changer de formulation
    #: voire de langue d'un appel à l'autre.
    CONTROL_INTENTS = frozenset({IntentType.APPROVAL, IntentType.CANCEL})

    def __init__(self, chat: Any = None, model: str = "") -> None:
        """
        Args:
            chat: ``async (messages, model) -> objet`` effectuant l'inférence
                réelle. Injecté pour que les tests restent hermétiques ; par
                défaut, un client Ollama construit depuis ``get_settings()``,
                exactement comme ``RealTaskExecutor``.
            model: modèle à interroger. Vide → :attr:`DEFAULT_CHAT_MODEL`.
        """
        self._templates: dict[str, str] = self._load_templates()
        self._chat = chat
        self._model = model or self.DEFAULT_CHAT_MODEL

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
        """Répond réellement à l'utilisateur, en interrogeant le modèle.

        Ce générateur ne faisait que formater un gabarit choisi par mots-clés :
        « Quelle est la capitale de la France ? » renvoyait « Voici ce que je
        peux vous dire à ce sujet… », et « Explique-moi un reverse proxy »
        déclenchait le gabarit de génération de documentation. Aucun modèle
        n'était consulté, donc aucune question n'obtenait de réponse.

        Le gabarit reste le repli quand le modèle est injoignable — et il est
        alors annoncé comme tel, pas présenté comme une réponse.
        """
        if intent not in self.CONTROL_INTENTS:
            answer = self._ask_model(user_msg, result, ctx)
            if answer:
                return answer

        template = self._templates.get(intent.value, self._templates["unknown"])
        rendered = template.format(
            user_message=user_msg[:100],
            domain=result.domain,
            confidence=result.confidence * 100,
            complexity=result.complexity,
            agents=", ".join(ctx.active_agents) if ctx.active_agents else "none",
            mission=ctx.active_mission_id or "none",
            goal=ctx.active_goal_id or "none",
        )
        if intent in self.CONTROL_INTENTS:
            # Pour un accusé de réception, le gabarit est la réponse attendue :
            # rien n'a échoué, il n'y a donc rien à signaler.
            return rendered
        return (
            f"{rendered}\n\n"
            "_(Modèle de langage injoignable : réponse générique. "
            "Vérifiez qu'Ollama tourne pour obtenir une vraie réponse.)_"
        )

    def _ask_model(self, user_msg: str, result: IntentResult,
                   ctx: ConversationContext) -> str:
        """Interroge le modèle. Chaîne vide si l'inférence n'a pas abouti."""
        messages = [
            {"role": "system", "content": self._system_prompt(result, ctx)},
            {"role": "user", "content": user_msg},
        ]
        try:
            return _run_sync(self._chat_fn()(messages=messages, model=self._model),
                             self.CHAT_TIMEOUT_S)
        except Exception:
            logger.warning("inférence de conversation indisponible", exc_info=True)
            return ""

    def _system_prompt(self, result: IntentResult, ctx: ConversationContext) -> str:
        """Le contexte réel de Hermes, pour que la réponse soit située."""
        parts = [
            "Tu es Hermes, assistant de développement. Réponds directement, "
            "précisément et dans la langue de l'utilisateur. Pas de préambule.",
            f"Intention détectée : {result.intent.value} (domaine {result.domain}).",
        ]
        if ctx.active_agents:
            parts.append(f"Agents actifs : {', '.join(ctx.active_agents)}.")
        if ctx.active_mission_id:
            parts.append(f"Mission en cours : {ctx.active_mission_id}.")
        return " ".join(parts)

    def _chat_fn(self) -> Any:
        if self._chat is not None:
            return self._chat
        self._chat = _default_chat
        return self._chat

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
