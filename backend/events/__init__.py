"""System Event Bus (HOS-025).

Central publish/subscribe event bus that unifies events from all
Hermes OS subsystems:

* Runtime (HOS-013)
* Agent Lifecycle (HOS-019)
* Supervisor / Mission (HOS-020)
* Memory (HOS-021)
* Skills (HOS-022)
* Execution Engine (HOS-024)

The bus is thread-safe, supports filtered subscriptions, configurable
history, and is designed to be extended with WebSocket, Redis, Kafka
etc. without changing the public API.
"""

from backend.events.system_event_bus import (
    EventFilter,
    EventHistory,
    EventStatistics,
    EventSubscriber,
    SystemEvent,
    SystemEventBus,
    SystemEventBusError,
    SystemEventType,
)

__all__ = [
    "SystemEvent",
    "SystemEventBus",
    "SystemEventBusError",
    "SystemEventType",
    "EventSubscriber",
    "EventFilter",
    "EventHistory",
    "EventStatistics",
]
