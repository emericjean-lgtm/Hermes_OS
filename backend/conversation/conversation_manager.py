"""Conversation Manager for Hermes OS (HOS-064).

Manages conversation sessions, message handling, and integration
with Hermes OS core systems (memory, missions, agents).
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("hermes_os.conversation.manager")


def _title_of(session: ConversationSession) -> str:
    """The session's display title, using the same rule the store persists.

    Imported lazily so this module keeps working — degraded but working —
    if the persistence layer cannot be loaded at all.
    """
    try:
        from backend.conversation.conversation_store import derive_title

        return derive_title(session.messages)
    except Exception:  # pragma: no cover
        return ""


class ConversationManager:
    """Central manager for Hermes OS conversational interactions.

    Sessions live in ``_sessions`` for the life of the process and in
    SQLite for good (HOS-101). The dict is now a *cache* in front of the
    store rather than the only copy: an unknown session id is looked up on
    disk before being treated as new, and eviction (see
    ``_cleanup_old_sessions``) drops a transcript from memory without
    destroying it.
    """

    def __init__(self, store: Any = None) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        #: Constructed on first use, not here: merely instantiating a
        #: manager — which several tests and every import-time singleton do —
        #: must not open a database or fix a path that a fixture is about
        #: to monkeypatch.
        self._store = store
        self._store_ready = store is not None
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

    # ── Persistence (HOS-101) ───────────────────────────────────────

    def _store_or_none(self) -> Any:
        """The durable store, or None if it cannot be opened.

        A conversation that cannot be saved is still a conversation the
        user is having: losing the database must degrade this manager back
        to its previous in-memory behaviour, never fail a reply. The
        failure is logged once — ``_store_ready`` stops it from being
        retried (and re-logged) on every keystroke of a broken install.
        """
        if not self._store_ready:
            self._store_ready = True
            try:
                from backend.conversation.conversation_store import (
                    SqliteConversationStore,
                )

                self._store = SqliteConversationStore()
            except Exception:
                logger.warning(
                    "Conversation persistence unavailable — transcripts will "
                    "not survive a restart.", exc_info=True)
                self._store = None
        return self._store

    def _persist(self, session: ConversationSession) -> None:
        """Write a session through to disk. Never raises.

        Called after every mutation. ``sync`` derives what to write from
        the database, so calling it more often than necessary is cheap and
        calling it once too few only defers the write to the next turn.
        """
        store = self._store_or_none()
        if store is None:
            return
        try:
            store.sync(session)
        except Exception:  # pragma: no cover - persistence never breaks a reply
            logger.debug("conversation persist failed", exc_info=True)

    def _cached_or_loaded(self, session_id: str) -> ConversationSession | None:
        """A live session, rehydrating it from disk if it is not in memory.

        This is what makes a transcript survive both a restart and an
        eviction. Callers must hold ``self._lock`` (it is re-entrant).
        """
        session = self._sessions.get(session_id)
        if session is not None or not session_id:
            return session
        store = self._store_or_none()
        if store is None:
            return None
        try:
            restored = store.load(session_id)
        except Exception:  # pragma: no cover
            logger.debug("conversation load failed", exc_info=True)
            return None
        if restored is not None:
            self._sessions[session_id] = restored
        return restored

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
            self._persist(session)
            return session

    def get_session(self, session_id: str) -> ConversationSession | None:
        with self._lock:
            return self._cached_or_loaded(session_id)

    def set_project(self, session_id: str, project_id: str | None) -> ConversationSession | None:
        """Bind (or unbind, with project_id=None) this session to a Project
        (= authorized workspace). ContextBuilder.update_context() is a
        no-op placeholder (see context_builder.py) — this is the real,
        direct mutation it never provided. Filesystem tools only ever
        appear in _conversation_tools() once this has been called with a
        real project_id (see conversation/routes.py)."""
        with self._lock:
            session = self._cached_or_loaded(session_id)
            if session is None:
                return None
            session.context.active_project_id = project_id or ""
            session.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(session)
            return session

    # ── Streaming (HOS-074) ─────────────────────────────────────────

    #: How many prior messages travel with a new one. The chat used to send
    #: none at all (see ``build_model_messages``), so this is the first
    #: bound that has ever applied; generous enough for a real conversation,
    #: finite so a long session cannot silently overflow the context window.
    MAX_HISTORY_MESSAGES = 20

    def begin_stream(self, session_id: str, content: str) -> tuple[
            str, list[dict[str, str]], IntentResult]:
        """Record the user's message and return what the model needs.

        Split deliberately from :meth:`finish_stream`: the inference itself
        happens *between* the two, outside this manager's lock. Holding it
        across a 30–120 s generation (what ``handle_message`` does) blocks
        every other session operation app-wide for the whole duration — the
        same defect HOS-069 fixed in ``ExecutionController``.

        Returns ``(session_id, model_messages, intent)``. ``session_id`` is
        returned because an unknown one opens a fresh session, exactly as
        ``handle_message`` does.
        """
        with self._lock:
            session = self._cached_or_loaded(session_id)
            if not session:
                session = self.create_session()
                session_id = session.session_id

            session.messages.append(Message(role=MessageRole.USER, content=content))
            session.status = ConversationStatus.PROCESSING
            session.updated_at = datetime.now(timezone.utc).isoformat()

            intent = self._intent_analyzer.analyze(content)
            session.context = self._context_builder.build_context(content, session.context)
            model_messages = self.build_model_messages(session)
            # Written before the inference, not after it: a generation that
            # crashes, times out or is killed mid-stream must not take the
            # user's question down with it.
            self._persist(session)

        return session_id, model_messages, intent

    def build_model_messages(self, session: ConversationSession) -> list[dict[str, str]]:
        """The conversation as the model should see it.

        HOS-074: ``ResponseGenerator._ask_model`` only ever sent
        ``[system, user]`` — the prior turns were stored in the session and
        never transmitted, so the model answered every message as if it were
        the first one ("et le deuxième ?" had nothing to refer back to).
        Roles are mapped to what an OpenAI/Ollama-shaped API expects:
        Hermes's own ``hermes``/``agent`` roles are both ``assistant``.
        """
        history = session.messages[-self.MAX_HISTORY_MESSAGES:]
        messages = [{"role": "system", "content": self._system_prompt(session)}]
        for message in history:
            if message.role == MessageRole.USER:
                role = "user"
            elif message.role == MessageRole.SYSTEM:
                role = "system"
            else:
                role = "assistant"
            if message.content.strip():
                messages.append({"role": role, "content": message.content})
        return messages

    def _system_prompt(self, session: ConversationSession) -> str:
        """Hermes's own real state, so answers are situated rather than generic."""
        ctx = session.context
        parts = [
            "Tu es Hermes, l'assistant de développement de Hermes OS. "
            "Réponds directement, précisément, dans la langue de l'utilisateur. "
            "Utilise du Markdown (titres, listes, blocs de code annotés du "
            "langage) quand cela aide à la lecture. Pas de préambule inutile.",
        ]
        if ctx.active_agents:
            parts.append(f"Agents actifs : {', '.join(ctx.active_agents)}.")
        if ctx.active_mission_id:
            parts.append(f"Mission en cours : {ctx.active_mission_id}.")
        if ctx.current_model:
            parts.append(f"Modèle courant : {ctx.current_model}.")
        workspace_block = self._workspace_context_block(ctx.active_project_id)
        if workspace_block:
            parts.append(workspace_block)
        return " ".join(parts)

    def _workspace_context_block(self, project_id: str) -> str:
        """Real, bounded workspace context for the model — Phase 11's
        progressive discovery: name/root/permissions and a short top-level
        directory listing, never the full tree (that's what workspace_list
        is for, called on demand). Never raises: a workspace binding must
        degrade to "no workspace context" rather than break the turn."""
        if not project_id:
            return ""
        try:
            from backend.projects.store import get_project_store
            project = get_project_store().get(project_id)
        except Exception:
            return ""
        if project is None or not project.root_path:
            return ""

        lines = [
            "",
            "--- Espace de travail actif ---",
            f"Nom : {project.name}",
            f"Racine : {project.root_path}",
        ]
        if project.validation_status == "valid":
            perms = ["lecture"]
            if project.validated_writable:
                perms.append("écriture")
            lines.append(f"Permissions : {', '.join(perms)}.")
            try:
                from pathlib import Path
                entries = sorted(p.name for p in Path(project.root_path).iterdir())[:20]
                if entries:
                    lines.append(f"Contenu racine ({len(entries)} élément(s), liste tronquée) : "
                                 + ", ".join(entries))
            except OSError:
                pass
            lines.append(
                "Outils disponibles : workspace_list, workspace_exists, workspace_read, "
                "workspace_write. Utilise workspace_list avant de lire un fichier dont tu "
                "ne connais pas le chemin exact plutôt que de deviner."
            )
        else:
            lines.append(
                "Ce workspace n'est pas encore validé — les outils de fichier ne sont "
                "pas disponibles tant qu'il n'a pas été validé (voir Workspace/Projet)."
            )
        return "\n".join(lines)

    def finish_stream(self, session_id: str, content: str,
                      metadata: dict[str, Any] | None = None) -> None:
        """Persist the assistant's completed answer into the session.

        Called once the stream is exhausted — including when it was cut
        short by the user, in which case the partial text is what actually
        happened and is stored as such (an interrupted answer the model
        never sees again would silently corrupt the next turn's history).
        Never raises: losing a transcript line must not surface as a failed
        response the user already received.
        """
        try:
            with self._lock:
                session = self._cached_or_loaded(session_id)
                if session is None:
                    return
                if content.strip():
                    session.messages.append(Message(
                        role=MessageRole.HERMES,
                        content=content,
                        metadata=metadata or {},
                    ))
                session.status = ConversationStatus.ACTIVE
                session.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(session)
        except Exception:  # pragma: no cover - bookkeeping must never break a reply
            pass

    def handle_message(self, session_id: str, content: str) -> ConversationResponse:
        with self._lock:
            session = self._cached_or_loaded(session_id)
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
            self._persist(session)

            # Trigger callbacks
            for cb in self._callbacks.get("message", []):
                try:
                    cb(session_id, content, response)
                except Exception:
                    pass

            return response

    def approve_action(self, session_id: str) -> ConversationResponse:
        with self._lock:
            session = self._cached_or_loaded(session_id)
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
            self._persist(session)

            for cb in self._callbacks.get("approval", []):
                try:
                    cb(session_id, True)
                except Exception:
                    pass

            return response

    def cancel_action(self, session_id: str) -> ConversationResponse:
        with self._lock:
            session = self._cached_or_loaded(session_id)
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
            self._persist(session)

            return response

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Recent conversations, newest first.

        Answered from the store, which holds every conversation ever had —
        including the ones evicted from memory and the ones from before the
        last restart. Falls back to the in-memory cache only when there is
        no store, which is the same list this used to return.
        """
        store = self._store_or_none()
        if store is not None:
            try:
                return store.list_recent(limit=limit)
            except Exception:  # pragma: no cover
                logger.debug("conversation listing failed", exc_info=True)

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
                    "title": _title_of(s),
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

    def delete_session(self, session_id: str) -> bool:
        """Forget a conversation, in memory and on disk.

        Persistence without a way out is a liability, not a feature: a user
        who can never delete a transcript is a user who learns not to say
        anything in it.
        """
        with self._lock:
            existed = self._sessions.pop(session_id, None) is not None
        store = self._store_or_none()
        if store is not None:
            try:
                existed = store.delete(session_id) or existed
            except Exception:  # pragma: no cover
                logger.debug("conversation delete failed", exc_info=True)
        return existed

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
        """Evict the least recently used sessions from the in-memory cache.

        Before HOS-101 this was destruction: the dict was the only copy, so
        the 101st conversation permanently deleted the first. Now that every
        session is on disk, dropping one here only means the next access
        pays a rehydration — which is what a cache is supposed to do.
        """
        if len(self._sessions) < self._max_sessions:
            return
        oldest = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
        )
        to_remove = len(self._sessions) - self._max_sessions + 10
        for s in oldest[:to_remove]:
            self._sessions.pop(s.session_id, None)
