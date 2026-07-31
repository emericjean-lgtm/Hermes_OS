"""Conversation Manager for Hermes OS (HOS-064).

Manages conversation sessions, message handling, and integration
with Hermes OS core systems (memory, missions, agents).
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

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


class ConversationManager:
    """Central manager for Hermes OS conversational interactions."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = threading.RLock()
        self._intent_analyzer = IntentAnalyzer()
        self._context_builder = ContextBuilder()
        self._response_generator = ResponseGenerator()
        self._callbacks: dict[str, list[Callable]] = {
            "message": [],
            "intent": [],
            "approval": [],
        }
        self._memory_manager: Any = None
        self._mission_planner: Any = None
        self._max_sessions = 100

    # ── Public API ──

    def set_memory_manager(self, mm: Any) -> None:
        self._memory_manager = mm
        self._context_builder.set_memory_manager(mm)

    def set_mission_planner(self, mp: Any) -> None:
        self._mission_planner = mp

    def create_session(self, user_id: str = "anonymous") -> ConversationSession:
        with self._lock:
            self._cleanup_old_sessions()
            session_id = f"conv_{uuid.uuid4().hex[:12]}"
            context = self._context_builder.build_initial_context(user_id)
            session = ConversationSession(
                session_id=session_id,
                user_id=user_id,
                context=context,
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> ConversationSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def handle_message(self, session_id: str, content: str) -> ConversationResponse:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                session = self.create_session()
                session_id = session.session_id

            # Add user message
            user_msg = Message(role=MessageRole.USER, content=content)
            session.messages.append(user_msg)
            session.status = ConversationStatus.PROCESSING
            session.updated_at = datetime.now(timezone.utc).isoformat()

            # Analyze intent
            intent = self._intent_analyzer.analyze(content)

            # Build context
            ctx = self._context_builder.build_context(content, session.context)

            # Update session context
            session.context = ctx

            # Generate response
            response = self._response_generator.generate(intent, ctx, content)
            response.session_id = session_id

            # Handle intent
            self._handle_intent(session, intent, ctx)

            # Add Hermes response
            hermes_msg = response.message
            session.messages.append(hermes_msg)

            # Update status
            if response.requires_approval:
                session.status = ConversationStatus.AWAITING_APPROVAL
            else:
                session.status = ConversationStatus.ACTIVE

            session.updated_at = datetime.now(timezone.utc).isoformat()

            # Trigger callbacks
            for cb in self._callbacks.get("message", []):
                try:
                    cb(session_id, content, response)
                except Exception:
                    pass

            return response

    def approve_action(self, session_id: str) -> ConversationResponse:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            session.status = ConversationStatus.PROCESSING
            intent = IntentResult(intent=IntentType.APPROVAL, confidence=0.95)
            ctx = session.context
            response = self._response_generator.generate(intent, ctx, "approved")
            response.session_id = session_id

            hermes_msg = response.message
            session.messages.append(hermes_msg)
            session.status = ConversationStatus.ACTIVE
            session.updated_at = datetime.now(timezone.utc).isoformat()

            for cb in self._callbacks.get("approval", []):
                try:
                    cb(session_id, True)
                except Exception:
                    pass

            return response

    def cancel_action(self, session_id: str) -> ConversationResponse:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            session.status = ConversationStatus.CANCELLED
            intent = IntentResult(intent=IntentType.CANCEL, confidence=0.95)
            ctx = session.context
            response = self._response_generator.generate(intent, ctx, "cancelled")
            response.session_id = session_id

            hermes_msg = response.message
            session.messages.append(hermes_msg)
            session.updated_at = datetime.now(timezone.utc).isoformat()

            return response

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            sessions = sorted(
                self._sessions.values(),
                key=lambda s: s.updated_at,
                reverse=True,
            )
            return [
                {
                    "session_id": s.session_id,
                    "user_id": s.user_id,
                    "status": s.status.value,
                    "message_count": len(s.messages),
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in sessions[:limit]
            ]

    def get_history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        return [
            {
                "role": m.role.value,
                "content": m.content,
                "timestamp": m.timestamp,
                "agent_id": m.agent_id,
                "mission_id": m.mission_id,
            }
            for m in session.messages[-limit:]
        ]

    def on(self, event: str, callback: Callable) -> None:
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    # ── Private ──

    def _handle_intent(self, session: ConversationSession, intent: IntentResult,
                       ctx: ConversationContext) -> None:
        for cb in self._callbacks.get("intent", []):
            try:
                cb(session.session_id, intent)
            except Exception:
                pass

    def _cleanup_old_sessions(self) -> None:
        if len(self._sessions) < self._max_sessions:
            return
        oldest = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
        )
        to_remove = len(self._sessions) - self._max_sessions + 10
        for s in oldest[:to_remove]:
            self._sessions.pop(s.session_id, None)
