"""Runtime Event Bus (HOS-034).

Thread-safe publish/subscribe bus for runtime events.
Supports multiple subscribers per event type and configurable history retention.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.runtime.events.event_models import RuntimeEventModel

# Type alias for event handlers
EventHandler = Callable[[RuntimeEventModel], None]


class RuntimeEventBus:
    """Central event bus for runtime observability.

    Responsibilities:
        - publish(event) — dispatch to all matching subscribers
        - subscribe(handler, event_types) — register a handler
        - unsubscribe(handler) — remove a handler
        - get_recent_events(limit) — retrieve recent in-memory events
        - get_runtime_history(runtime_id, limit) — per-runtime history

    Thread-safe via RLock.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._lock = threading.RLock()
        self._subscribers: list[tuple[Optional[set[str]], EventHandler]] = []
        self._history: list[RuntimeEventModel] = []
        self._max_history = max_history

    # ── Publish ─────────────────────────────────────────────

    def publish(self, event: RuntimeEventModel) -> None:
        """Dispatch an event to all matching subscribers and store it."""
        with self._lock:
            # Store in history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            # Dispatch to subscribers
            for event_types, handler in self._subscribers:
                if event_types is None or event.event_type in event_types:
                    try:
                        handler(event)
                    except Exception:
                        pass  # Isolate subscriber failures

    # ── Subscribe / Unsubscribe ─────────────────────────────

    def subscribe(
        self,
        handler: EventHandler,
        event_types: Optional[list[str]] = None,
    ) -> EventHandler:
        """Register a handler.

        Args:
            handler: Callable receiving RuntimeEventModel.
            event_types: If provided, only receive these event types.
                         If None, receive all events.

        Returns:
            The handler (for use as a subscription token).
        """
        with self._lock:
            types_set: Optional[set[str]] = (
                set(event_types) if event_types is not None else None
            )
            self._subscribers.append((types_set, handler))
        return handler

    def unsubscribe(self, handler: EventHandler) -> bool:
        """Remove a handler from all subscriptions.

        Returns:
            True if the handler was found and removed.
        """
        with self._lock:
            before = len(self._subscribers)
            self._subscribers = [
                (t, h) for t, h in self._subscribers if h is not handler
            ]
            return len(self._subscribers) < before

    # ── Query ───────────────────────────────────────────────

    def get_recent_events(self, limit: int = 50) -> list[RuntimeEventModel]:
        """Return the most recent events from in-memory history."""
        with self._lock:
            return list(self._history[-limit:])

    def get_runtime_history(
        self,
        runtime_id: str,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        """Return recent events for a specific runtime."""
        with self._lock:
            filtered = [e for e in self._history if e.runtime_id == runtime_id]
            return filtered[-limit:]

    def clear(self) -> None:
        """Clear all in-memory history. Subscribers are preserved."""
        with self._lock:
            self._history.clear()

    # ── Stats ───────────────────────────────────────────────

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._history)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
