"""Document cache — HOS-053B.

TTL/LRU cache for synced Alexandrie documents.
Reduces network calls and speeds up hybrid search.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from backend.integrations.alexandrie.alexandrie_models import (
    DocumentMemoryEntry,
)


class DocumentCache:
    """Thread-safe TTL+LRU cache for synced documents.

    Eviction: oldest accessed (LRU) when max entries exceeded,
    or TTL-expired entries are lazily evicted on access.
    """

    def __init__(self, max_entries: int = 1000, ttl_seconds: float = 300.0) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._store: OrderedDict[str, tuple[DocumentMemoryEntry, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[DocumentMemoryEntry]:
        """Get document from cache. Returns None if not found or expired."""
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            entry, cached_at = self._store[key]
            if (time.monotonic() - cached_at) > self._ttl_seconds:
                # Expired
                del self._store[key]
                self._evictions += 1
                self._misses += 1
                return None

            # Move to end for LRU ordering
            self._store.move_to_end(key)
            self._hits += 1
            return entry

    def put(self, key: str, entry: DocumentMemoryEntry) -> None:
        """Add or update cache entry."""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)

            self._store[key] = (entry, time.monotonic())

            # Evict if over capacity
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)
                self._evictions += 1

    def remove(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def contains(self, key: str) -> bool:
        return self.get(key) is not None

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(total, 1),
                "evictions": self._evictions,
            }

    def prune_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired = [k for k, (_, t) in self._store.items() if (now - t) > self._ttl_seconds]
            for k in expired:
                del self._store[k]
                self._evictions += 1
                removed += 1
        return removed
