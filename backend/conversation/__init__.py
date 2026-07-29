"""Conversation package for Hermes OS (HOS-064)."""

from .conversation_manager import ConversationManager
from .conversation_models import (
    ConversationContext,
    ConversationResponse,
    ConversationSession,
    ConversationStatus,
    IntentResult,
    IntentType,
    Message,
    MessageRole,
)
from .context_builder import ContextBuilder
from .intent_analyzer import IntentAnalyzer
from .response_generator import ResponseGenerator
from .routes import (
    get_routes,
    handle_approve,
    handle_cancel,
    handle_get_context,
    handle_get_history,
    handle_list_sessions,
    handle_send_message,
    handle_start_session,
)

__all__ = [
    "ConversationManager",
    "ConversationSession",
    "ConversationContext",
    "ConversationResponse",
    "ConversationStatus",
    "IntentAnalyzer",
    "IntentResult",
    "IntentType",
    "ContextBuilder",
    "ResponseGenerator",
    "Message",
    "MessageRole",
    "handle_start_session",
    "handle_send_message",
    "handle_get_history",
    "handle_approve",
    "handle_cancel",
    "handle_get_context",
    "handle_list_sessions",
    "get_routes",
]
