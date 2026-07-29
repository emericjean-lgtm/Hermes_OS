"""Context Sharing for the Multi-Agent Collaboration Engine (HOS-044).

Allows agents to share context, results, observations, and decisions
with fine-grained permission control.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.agents.collaboration.collaboration_models import SharedContext


class ContextSharing:
    """Manages shared contexts between agents.

    Supports permission-based visibility and editing.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.Lock()
        self._on_event = on_event
        self._contexts: dict[str, SharedContext] = {}
        self._by_owner: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    def share(
        self,
        owner_id: str,
        mission_id: str,
        title: str,
        content: dict,
        context_type: str = "result",
        visible_to: Optional[list[str]] = None,
        editable_by: Optional[list[str]] = None,
    ) -> SharedContext:
        """Share a context with other agents."""
        ctx = SharedContext(
            owner_id=owner_id,
            mission_id=mission_id,
            context_type=context_type,
            title=title,
            content=dict(content),
            visible_to=visible_to or [],
            editable_by=editable_by or [],
        )
        with self._lock:
            self._contexts[ctx.share_id] = ctx
            self._by_owner.setdefault(owner_id, []).append(ctx.share_id)
            self._by_mission.setdefault(mission_id, []).append(ctx.share_id)

        if self._on_event:
            self._on_event("context.shared", {
                "share_id": ctx.share_id,
                "owner_id": owner_id,
                "mission_id": mission_id,
                "type": context_type,
            }, severity="info")
        return ctx

    def get(self, share_id: str, agent_id: str = "") -> Optional[SharedContext]:
        """Get shared context. Respects visibility permissions."""
        ctx = self._contexts.get(share_id)
        if ctx is None:
            return None
        # Visibility check: owner always sees, or if visible_to is empty (public), or agent in list
        if agent_id and ctx.visible_to and agent_id not in ctx.visible_to and agent_id != ctx.owner_id:
            return None
        return ctx

    def can_edit(self, share_id: str, agent_id: str) -> bool:
        """Check if an agent can edit a shared context."""
        ctx = self._contexts.get(share_id)
        if ctx is None:
            return False
        if agent_id == ctx.owner_id:
            return True
        if not ctx.editable_by:
            return True  # no restrictions
        return agent_id in ctx.editable_by

    def update(
        self,
        share_id: str,
        agent_id: str,
        content: dict,
    ) -> bool:
        """Update a shared context (if permitted)."""
        if not self.can_edit(share_id, agent_id):
            return False
        with self._lock:
            ctx = self._contexts.get(share_id)
            if ctx is None:
                return False
            ctx.content.update(content)
        return True

    def get_by_owner(self, owner_id: str) -> list[SharedContext]:
        with self._lock:
            ctx_ids = self._by_owner.get(owner_id, [])
            return [self._contexts[cid] for cid in ctx_ids if cid in self._contexts]

    def get_by_mission(self, mission_id: str) -> list[SharedContext]:
        with self._lock:
            ctx_ids = self._by_mission.get(mission_id, [])
            return [self._contexts[cid] for cid in ctx_ids if cid in self._contexts]

    def get_visible_to(self, agent_id: str) -> list[SharedContext]:
        """Get all contexts visible to an agent."""
        visible = []
        with self._lock:
            for ctx in self._contexts.values():
                if not ctx.visible_to or agent_id in ctx.visible_to or agent_id == ctx.owner_id:
                    visible.append(ctx)
        return visible

    def remove(self, share_id: str, agent_id: str) -> bool:
        """Remove a shared context (owner only)."""
        with self._lock:
            ctx = self._contexts.get(share_id)
            if ctx is None or ctx.owner_id != agent_id:
                return False
            self._contexts.pop(share_id, None)
            if ctx.owner_id in self._by_owner:
                self._by_owner[ctx.owner_id] = [c for c in self._by_owner[ctx.owner_id] if c != share_id]
            if ctx.mission_id in self._by_mission:
                self._by_mission[ctx.mission_id] = [c for c in self._by_mission[ctx.mission_id] if c != share_id]
        return True
