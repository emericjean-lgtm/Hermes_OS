"""Message Bus for the Multi-Agent Collaboration Engine (HOS-044).

Inter-agent messaging: direct, broadcast, group, help requests.
Thread-safe with conversation history.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.collaboration.collaboration_models import (
    AgentMessage,
    MessageType,
)


class MessageBus:
    """Dedicated inter-agent message bus.

    Supports direct messages, broadcasts, group conversations,
    help requests, and acknowledgements. Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.Lock()
        self._on_event = on_event
        self._messages: dict[str, AgentMessage] = {}
        # Indexes
        self._by_conversation: dict[str, list[str]] = {}
        self._by_recipient: dict[str, list[str]] = {}
        self._by_sender: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    # ── Send ─────────────────────────────────────────────────

    def send(
        self,
        sender_id: str,
        recipient_id: str,
        subject: str,
        body: str,
        conversation_id: str = "",
        mission_id: str = "",
        node_id: str = "",
        reply_to: str = "",
    ) -> AgentMessage:
        """Send a direct message."""
        msg = AgentMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            type=MessageType.DIRECT,
            subject=subject,
            body=body,
            conversation_id=conversation_id,
            reply_to=reply_to,
            mission_id=mission_id,
            node_id=node_id,
        )
        return self._store(msg)

    def broadcast(
        self,
        sender_id: str,
        subject: str,
        body: str,
        mission_id: str = "",
    ) -> AgentMessage:
        """Send a broadcast message to all agents."""
        msg = AgentMessage(
            sender_id=sender_id,
            type=MessageType.BROADCAST,
            subject=subject,
            body=body,
            mission_id=mission_id,
        )
        return self._store(msg)

    def send_group(
        self,
        sender_id: str,
        recipient_ids: list[str],
        subject: str,
        body: str,
        mission_id: str = "",
    ) -> list[AgentMessage]:
        """Send a message to a group of agents."""
        messages = []
        conv_id = AgentMessage().message_id  # group conversation ID
        for rid in recipient_ids:
            msg = self.send(
                sender_id=sender_id,
                recipient_id=rid,
                subject=subject,
                body=body,
                conversation_id=conv_id,
                mission_id=mission_id,
            )
            messages.append(msg)
        return messages

    def request_help(
        self,
        sender_id: str,
        subject: str,
        body: str,
        required_capabilities: list[str],
        mission_id: str = "",
        node_id: str = "",
    ) -> AgentMessage:
        """Send a help request."""
        msg = AgentMessage(
            sender_id=sender_id,
            type=MessageType.HELP_REQUEST,
            subject=subject,
            body=body,
            mission_id=mission_id,
            node_id=node_id,
            metadata={"required_capabilities": required_capabilities},
        )
        return self._store(msg)

    def respond_help(
        self,
        sender_id: str,
        help_request_id: str,
        body: str,
        accepted: bool = True,
    ) -> Optional[AgentMessage]:
        """Respond to a help request."""
        original = self._messages.get(help_request_id)
        if original is None:
            return None

        msg = AgentMessage(
            sender_id=sender_id,
            recipient_id=original.sender_id,
            type=MessageType.HELP_RESPONSE,
            subject=f"Re: {original.subject}",
            body=body,
            conversation_id=original.conversation_id or help_request_id,
            reply_to=help_request_id,
            mission_id=original.mission_id,
            node_id=original.node_id,
            metadata={"accepted": accepted},
        )
        return self._store(msg)

    # ── Read / Acknowledge ───────────────────────────────────

    def mark_read(self, message_id: str) -> bool:
        with self._lock:
            msg = self._messages.get(message_id)
            if msg is None:
                return False
            msg.read = True
            msg.read_at = datetime.now(timezone.utc)
            return True

    def acknowledge(self, message_id: str) -> bool:
        with self._lock:
            msg = self._messages.get(message_id)
            if msg is None:
                return False
            msg.acknowledged = True
            if self._on_event:
                self._on_event("message.received", {
                    "message_id": message_id,
                    "sender_id": msg.sender_id,
                    "recipient_id": msg.recipient_id,
                }, severity="info")
            return True

    # ── Query ────────────────────────────────────────────────

    def get(self, message_id: str) -> Optional[AgentMessage]:
        return self._messages.get(message_id)

    def get_conversation(self, conversation_id: str) -> list[AgentMessage]:
        with self._lock:
            msg_ids = self._by_conversation.get(conversation_id, [])
            return [self._messages[mid] for mid in msg_ids if mid in self._messages]

    def get_inbox(self, agent_id: str) -> list[AgentMessage]:
        """Get all messages for an agent (direct + broadcasts + help)."""
        with self._lock:
            direct = [
                self._messages[mid] for mid in self._by_recipient.get(agent_id, [])
                if mid in self._messages
            ]
            broadcasts = [
                m for m in self._messages.values()
                if m.type == MessageType.BROADCAST or m.type == MessageType.HELP_REQUEST
            ]
            return sorted(
                direct + broadcasts,
                key=lambda m: m.created_at,
                reverse=True,
            )

    def get_unread(self, agent_id: str) -> list[AgentMessage]:
        inbox = self.get_inbox(agent_id)
        return [m for m in inbox if not m.read]

    def get_sent(self, agent_id: str) -> list[AgentMessage]:
        with self._lock:
            msg_ids = self._by_sender.get(agent_id, [])
            return sorted(
                [self._messages[mid] for mid in msg_ids if mid in self._messages],
                key=lambda m: m.created_at,
                reverse=True,
            )

    def get_by_mission(self, mission_id: str) -> list[AgentMessage]:
        with self._lock:
            msg_ids = self._by_mission.get(mission_id, [])
            return [self._messages[mid] for mid in msg_ids if mid in self._messages]

    def get_help_requests(self) -> list[AgentMessage]:
        with self._lock:
            return [m for m in self._messages.values() if m.type == MessageType.HELP_REQUEST]

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_messages": len(self._messages),
                "by_type": {
                    t.value: sum(1 for m in self._messages.values() if m.type == t)
                    for t in MessageType
                },
                "read_count": sum(1 for m in self._messages.values() if m.read),
                "unread_count": sum(1 for m in self._messages.values() if not m.read),
            }

    # ── Helpers ──────────────────────────────────────────────

    def _store(self, msg: AgentMessage) -> AgentMessage:
        with self._lock:
            self._messages[msg.message_id] = msg
            if msg.conversation_id:
                self._by_conversation.setdefault(msg.conversation_id, []).append(msg.message_id)
            if msg.recipient_id:
                self._by_recipient.setdefault(msg.recipient_id, []).append(msg.message_id)
            self._by_sender.setdefault(msg.sender_id, []).append(msg.message_id)
            if msg.mission_id:
                self._by_mission.setdefault(msg.mission_id, []).append(msg.message_id)

        if self._on_event:
            self._on_event("message.sent", {
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "recipient_id": msg.recipient_id or "broadcast",
                "type": msg.type.value,
                "subject": msg.subject,
            }, severity="info")

        return msg
