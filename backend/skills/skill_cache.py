"""LRU/TTL skill cache (HOS-048)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from .skill_models import CacheStrategy, SkillCacheEntry


class SkillCache:
    """Caches loaded skills to avoid repeated loading.

    Strategies: LRU eviction, TTL expiration, priority-based retention.
    """

    def __init__(self, max_size: int = 50, default_ttl: float = 300.0) -> None:
        self._lock = threading.RLock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._entries: dict[str, SkillCacheEntry] = {}
        self._strategy = CacheStrategy.LRU

    def set_strategy(self, strategy: CacheStrategy) -> None:
        with self._lock:
            self._strategy = strategy

    def put(self, skill_id: str, ttl: Optional[float] = None) -> SkillCacheEntry:
        with self._lock:
            self._evict_if_needed()

            if skill_id in self._entries:
                entry = self._entries[skill_id]
                entry.use_count += 1
                entry.last_used = datetime.now(timezone.utc)
                return entry

            entry = SkillCacheEntry(
                skill_id=skill_id,
                loaded_at=datetime.now(timezone.utc),
                last_used=datetime.now(timezone.utc),
                use_count=1,
                ttl_seconds=ttl if ttl is not None else self._default_ttl,
            )
            self._entries[skill_id] = entry
            return entry

    def get(self, skill_id: str) -> Optional[SkillCacheEntry]:
        with self._lock:
            entry = self._entries.get(skill_id)
            if entry is None:
                return None
            if self._is_expired(entry):
                self._entries.pop(skill_id, None)
                return None
            entry.use_count += 1
            entry.last_used = datetime.now(timezone.utc)
            return entry

    def evict(self, skill_id: str) -> bool:
        with self._lock:
            return self._entries.pop(skill_id, None) is not None

    def invalidate(self) -> int:
        """Remove all expired entries, return count removed."""
        with self._lock:
            expired = [sid for sid, e in self._entries.items() if self._is_expired(e)]
            for sid in expired:
                del self._entries[sid]
            return len(expired)

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def _evict_if_needed(self) -> None:
        while len(self._entries) >= self._max_size:
            self._evict_one()

    def _evict_one(self) -> None:
        if not self._entries:
            return

        # First try to evict expired
        for sid, entry in list(self._entries.items()):
            if self._is_expired(entry):
                del self._entries[sid]
                return

        # LRU: evict least recently used
        if self._strategy == CacheStrategy.LRU:
            lru_id = min(self._entries.keys(), key=lambda sid: self._entries[sid].last_used)
            del self._entries[lru_id]
        elif self._strategy == CacheStrategy.PRIORITY:
            lp_id = min(self._entries.keys(), key=lambda sid: self._entries[sid].priority)
            del self._entries[lp_id]
        else:
            # TTL: already handled by expired check above
            # Fallback to LRU
            lru_id = min(self._entries.keys(), key=lambda sid: self._entries[sid].last_used)
            del self._entries[lru_id]

    def _is_expired(self, entry: SkillCacheEntry) -> bool:
        if entry.ttl_seconds <= 0:
            return False  # No TTL
        elapsed = (datetime.now(timezone.utc) - entry.last_used).total_seconds()
        return elapsed > entry.ttl_seconds

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def hit_rate(self) -> float:
        with self._lock:
            total_uses = sum(e.use_count for e in self._entries.values())
            if total_uses == 0:
                return 0.0
            return (total_uses - len(self._entries)) / total_uses  # hits / (hits + misses)

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._entries),
                "max_size": self._max_size,
                "strategy": self._strategy.value,
                "hit_rate": round(self.hit_rate(), 4),
                "entries": {sid: {"uses": e.use_count, "ttl": e.ttl_seconds} for sid, e in self._entries.items()},
            }
