"""Working Memory for HOS-047 — transient mission context, auto-cleared."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.memory_models import WorkingMemory


class WorkingMemoryStore:
    """Thread-safe transient memory for active mission context.

    Auto-cleared when mission completes. Holds conversations, agent states,
    runtime decisions for the current execution.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._memories: dict[str, WorkingMemory] = {}
        self._by_mission: dict[str, str] = {}
        self._by_agent: dict[str, list[str]] = {}

    def create(self, mission_id: str, agent_id: str) -> WorkingMemory:
        """Create working memory for a mission/agent pair."""
        wm = WorkingMemory(mission_id=mission_id, agent_id=agent_id)
        with self._lock:
            self._memories[wm.memory_id] = wm
            self._by_mission[mission_id] = wm.memory_id
            self._by_agent.setdefault(agent_id, []).append(wm.memory_id)
        return wm

    def get_by_mission(self, mission_id: str) -> Optional[WorkingMemory]:
        with self._lock:
            mid = self._by_mission.get(mission_id)
            return self._memories.get(mid) if mid else None

    def get_by_agent(self, agent_id: str) -> list[WorkingMemory]:
        with self._lock:
            ids = self._by_agent.get(agent_id, [])
            return [self._memories[i] for i in ids if i in self._memories]

    def update_conversation(self, memory_id: str, entry: dict) -> bool:
        with self._lock:
            wm = self._memories.get(memory_id)
            if wm is None:
                return False
            wm.conversations.append(entry)
        return True

    def update_agent_state(self, memory_id: str, agent_id: str, state: str) -> bool:
        with self._lock:
            wm = self._memories.get(memory_id)
            if wm is None:
                return False
            wm.agent_states[agent_id] = state
        return True

    def clear(self, mission_id: str) -> bool:
        """Clear working memory when mission completes."""
        with self._lock:
            mid = self._by_mission.pop(mission_id, None)
            if mid and mid in self._memories:
                wm = self._memories.pop(mid)
                for agent_id in wm.agent_states:
                    if agent_id in self._by_agent:
                        self._by_agent[agent_id] = [
                            i for i in self._by_agent[agent_id] if i != mid
                        ]
                return True
        return False

    def stats(self) -> dict:
        with self._lock:
            return {"active_memories": len(self._memories),
                    "active_missions": len(self._by_mission)}
