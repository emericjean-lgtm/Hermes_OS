"""KTransformers cache — LRU with TTL, invalidation, stats (HOS-052)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.runtime.ktransformers.kt_models import KTCacheStats


@dataclass
class _CacheEntry:
    model_id: str
    size_gb: float = 0.0
    added_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    priority: int = 0  # Higher = keep longer


class KTCache:
    """LRU/TTL cache for KTransformers models.

    Supports LRU eviction, TTL-based expiry, priority-based retention,
    and full cache statistics.
    """

    def __init__(self, max_entries: int = 16, default_ttl_s: float = 600.0):
        self._lock = threading.RLock()
        self._entries: dict[str, _CacheEntry] = {}
        self._max_entries = max_entries
        self._default_ttl_s = default_ttl_s
        self._hit_count = 0
        self._miss_count = 0
        self._evicted_count = 0

    # ── CRUD ──────────────────────────────────────────

    def add(self, model_id: str, size_gb: float = 0.0, priority: int = 0) -> bool:
        """Add a model to cache. Evicts if full."""
        with self._lock:
            if model_id in self._entries:
                self._entries[model_id].last_access = time.time()
                return True

            # Evict if full
            while len(self._entries) >= self._max_entries:
                if not self._evict_one():
                    return False

            self._entries[model_id] = _CacheEntry(
                model_id=model_id,
                size_gb=size_gb,
                priority=priority,
            )
            return True

    def get(self, model_id: str) -> Optional[_CacheEntry]:
        """Get a cache entry. Updates access time and hit/miss counters."""
        with self._lock:
            entry = self._entries.get(model_id)
            if entry is None:
                self._miss_count += 1
                return None
            # Check TTL
            if time.time() - entry.added_at > self._default_ttl_s:
                self._entries.pop(model_id, None)
                self._evicted_count += 1
                self._miss_count += 1
                return None
            entry.last_access = time.time()
            entry.access_count += 1
            self._hit_count += 1
            return entry

    def remove(self, model_id: str) -> bool:
        """Remove a model from cache."""
        with self._lock:
            if model_id not in self._entries:
                return False
            del self._entries[model_id]
            return True

    def contains(self, model_id: str) -> bool:
        """Check if a model is cached."""
        return self.get(model_id) is not None

    # ── Eviction ──────────────────────────────────────

    def _evict_one(self) -> bool:
        """Evict one entry: expired TTL first, then LRU among lowest priority."""
        now = time.time()
        # 1. Evict expired
        for mid, entry in list(self._entries.items()):
            if now - entry.added_at > self._default_ttl_s:
                del self._entries[mid]
                self._evicted_count += 1
                return True
        # 2. Evict lowest priority, least recently accessed
        if not self._entries:
            return False
        candidates = sorted(
            self._entries.items(),
            key=lambda kv: (kv[1].priority, kv[1].last_access)
        )
        del self._entries[candidates[0][0]]
        self._evicted_count += 1
        return True

    def evict_expired(self) -> int:
        """Explicitly evict all expired entries. Returns count."""
        now = time.time()
        count = 0
        with self._lock:
            for mid, entry in list(self._entries.items()):
                if now - entry.added_at > self._default_ttl_s:
                    del self._entries[mid]
                    self._evicted_count += 1
                    count += 1
        return count

    def clear(self) -> int:
        """Clear all entries. Returns count cleared."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    # ── Statistics ────────────────────────────────────

    def stats(self) -> KTCacheStats:
        """Get cache statistics."""
        with self._lock:
            total_req = self._hit_count + self._miss_count
            return KTCacheStats(
                total_entries=len(self._entries),
                active_entries=sum(1 for e in self._entries.values() if e.last_access > time.time() - 300),
                evicted_entries=self._evicted_count,
                hit_count=self._hit_count,
                miss_count=self._miss_count,
                hit_rate=self._hit_count / max(1, total_req),
            )

    def size(self) -> int:
        """Current number of cached entries."""
        with self._lock:
            return len(self._entries)
