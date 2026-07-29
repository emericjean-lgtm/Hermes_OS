"""Episodic Memory for HOS-047 — mission experiences, successes, failures, decisions."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.memory.memory_models import EpisodicMemory


class EpisodicMemoryStore:
    """Thread-safe store of mission experiences.

    Records missions, incidents, successes, failures, benchmarks, decisions.
    Queryable by outcome, tags, mission type, agents used.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._episodes: dict[str, EpisodicMemory] = {}
        self._by_mission: dict[str, str] = {}
        self._by_tag: dict[str, list[str]] = {}

    def record(self, episode: EpisodicMemory) -> EpisodicMemory:
        with self._lock:
            self._episodes[episode.episode_id] = episode
            self._by_mission[episode.mission_id] = episode.episode_id
            for tag in episode.tags:
                self._by_tag.setdefault(tag, []).append(episode.episode_id)

        if self._on_event:
            self._on_event("memory.created", {"type": "episodic", "id": episode.episode_id}, severity="info")
        return episode

    def get_by_mission(self, mission_id: str) -> Optional[EpisodicMemory]:
        with self._lock:
            eid = self._by_mission.get(mission_id)
            return self._episodes.get(eid) if eid else None

    def find_similar(self, tags: list[str], mission_type: str = "", limit: int = 10) -> list[EpisodicMemory]:
        """Find similar missions by tags and type."""
        candidates: dict[str, int] = {}
        with self._lock:
            for tag in tags:
                for eid in self._by_tag.get(tag, []):
                    candidates[eid] = candidates.get(eid, 0) + 1
            results = sorted(candidates, key=candidates.get, reverse=True)[:limit]
            episodes = [self._episodes[eid] for eid in results if eid in self._episodes]
            if mission_type:
                episodes = [e for e in episodes if e.mission_type == mission_type]
        return episodes[:limit]

    def get_successful(self, limit: int = 20) -> list[EpisodicMemory]:
        with self._lock:
            return [e for e in self._episodes.values() if e.success][:limit]

    def get_failed(self, limit: int = 20) -> list[EpisodicMemory]:
        with self._lock:
            return [e for e in self._episodes.values() if not e.success][:limit]

    def get_by_agent(self, agent_id: str) -> list[EpisodicMemory]:
        with self._lock:
            return [e for e in self._episodes.values() if agent_id in e.agents_used]

    def get_all(self) -> list[EpisodicMemory]:
        with self._lock:
            return list(self._episodes.values())

    def stats(self) -> dict:
        with self._lock:
            total = len(self._episodes)
            success = sum(1 for e in self._episodes.values() if e.success)
            return {"total": total, "successful": success, "failed": total - success,
                    "success_rate": round(success / max(total, 1) * 100, 1)}

    def search_by_keyword(self, query: str, limit: int = 10) -> list[EpisodicMemory]:
        q = query.lower()
        with self._lock:
            results = [e for e in self._episodes.values()
                      if q in e.mission_title.lower() or q in e.mission_type.lower()
                      or any(q in t.lower() for t in e.tags)]
        return results[:limit]
