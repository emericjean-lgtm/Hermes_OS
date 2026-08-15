"""Conversation models for Hermes OS (HOS-064)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    USER = "user"
    HERMES = "hermes"
    SYSTEM = "system"
    AGENT = "agent"


class IntentType(str, Enum):
    OPTIMIZATION = "optimization"
    ANALYSIS = "analysis"
    DEBUG = "debug"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    QUESTION = "question"
    COMMAND = "command"
    GREETING = "greeting"
    APPROVAL = "approval"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Message:
    role: MessageRole
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    mission_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class IntentResult:
    intent: IntentType = IntentType.UNKNOWN
    domain: str = "general"
    confidence: float = 0.0
    complexity: float = 0.3
    suggested_action: str = ""
    extracted_entities: dict[str, Any] = field(default_factory=dict)
    goal_id: str = ""


@dataclass
class ConversationContext:
    active_goal_id: str = ""
    active_mission_id: str = ""
    # The Project (= authorized workspace, see projects/project_manager.py)
    # this session is currently bound to. Empty means no workspace is
    # bound — filesystem tools are then not offered to the model at all
    # (see conversation/routes.py's _conversation_tools).
    active_project_id: str = ""
    active_agents: list[str] = field(default_factory=list)
    current_runtime: str = ""
    current_model: str = ""
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    workspace_status: str = ""
    security_level: str = "normal"
    environment_vars: dict[str, str] = field(default_factory=dict)
    # §12 — résumé des tours trop anciens pour être transmis mot pour mot
    # (HOS-120). Vide tant que la conversation tient entière dans la
    # fenêtre, ou quand la production du résumé a échoué : dans ce second
    # cas `build_model_messages` annonce le trou au modèle plutôt que de le
    # taire. Une chaîne vide n'a jamais le sens de « rien d'important
    # n'a été dit ».
    history_summary: str = ""
    # Combien de messages ce résumé couvre, pour savoir s'il est encore à
    # jour quand la conversation s'allonge. Recalculer à chaque tour
    # coûterait un appel modèle par message.
    history_summary_upto: int = 0


@dataclass
class ConversationSession:
    session_id: str = ""
    user_id: str = ""
    status: ConversationStatus = ConversationStatus.ACTIVE
    messages: list[Message] = field(default_factory=list)
    context: ConversationContext = field(default_factory=ConversationContext)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class ConversationResponse:
    session_id: str
    message: Message
    intent: IntentResult | None = None
    context_update: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    approval_request: dict[str, Any] | None = None
    suggested_actions: list[dict[str, str]] = field(default_factory=list)
    streaming: bool = False
