"""Runtime event type catalogue (HOS-034).

All event types are grouped by category for structured filtering.
"""

from __future__ import annotations

from enum import Enum


class RuntimeEventType(str, Enum):
    """Canonical runtime event types."""

    # ── Runtime lifecycle ───────────────────────────────────
    RUNTIME_STARTED = "runtime.started"
    RUNTIME_STOPPED = "runtime.stopped"
    RUNTIME_FAILED = "runtime.failed"
    RUNTIME_RECOVERED = "runtime.recovered"
    RUNTIME_HEALTH_CHANGED = "runtime.health_changed"
    RUNTIME_OVERLOADED = "runtime.overloaded"
    RUNTIME_UNAVAILABLE = "runtime.unavailable"
    #: The runtime is serving less context than agentic work needs. Not a
    #: failure — everything answers normally — which is exactly why it needs
    #: to be an event: an under-served context silently truncates tool
    #: schemas, and the agent then reports having no tools (HOS-090).
    RUNTIME_CONTEXT_DEGRADED = "runtime.context_degraded"

    #: A role in config/models.yaml points at a tag Ollama does not have.
    #: Unlike the one above this *is* a failure — but an invisible one: the
    #: 404 arrives after a streaming response has already committed its 200,
    #: so the client sees an empty answer instead of an error (HOS-108).
    RUNTIME_MODEL_MISSING = "runtime.model_missing"

    #: More roles ask to stay resident than OLLAMA_MAX_LOADED_MODELS allows.
    #: Not a failure either — but the configuration then describes warm
    #: models that are in fact evicted on every switch (HOS-108).
    RUNTIME_RESIDENCY_UNSATISFIABLE = "runtime.residency_unsatisfiable"

    # ── Model lifecycle ─────────────────────────────────────
    MODEL_LOADED = "model.loaded"
    MODEL_UNLOADED = "model.unloaded"
    MODEL_SWITCH_STARTED = "model.switch_started"
    MODEL_SWITCH_COMPLETED = "model.switch_completed"

    # ── Router events ───────────────────────────────────────
    ROUTING_DECISION = "routing.decision"
    ROUTING_FALLBACK = "routing.fallback"
    ROUTING_FAILED = "routing.failed"

    # ── Resource events ─────────────────────────────────────
    MEMORY_WARNING = "memory.warning"
    VRAM_LIMIT_REACHED = "vram.limit_reached"


# Category grouping for structured filtering
RUNTIME_EVENT_CATEGORIES: dict[str, list[str]] = {
    "runtime": [
        RuntimeEventType.RUNTIME_STARTED.value,
        RuntimeEventType.RUNTIME_STOPPED.value,
        RuntimeEventType.RUNTIME_FAILED.value,
        RuntimeEventType.RUNTIME_RECOVERED.value,
        RuntimeEventType.RUNTIME_HEALTH_CHANGED.value,
        RuntimeEventType.RUNTIME_OVERLOADED.value,
        RuntimeEventType.RUNTIME_UNAVAILABLE.value,
    ],
    "model": [
        RuntimeEventType.MODEL_LOADED.value,
        RuntimeEventType.MODEL_UNLOADED.value,
        RuntimeEventType.MODEL_SWITCH_STARTED.value,
        RuntimeEventType.MODEL_SWITCH_COMPLETED.value,
    ],
    "router": [
        RuntimeEventType.ROUTING_DECISION.value,
        RuntimeEventType.ROUTING_FALLBACK.value,
        RuntimeEventType.ROUTING_FAILED.value,
    ],
    "resource": [
        RuntimeEventType.MEMORY_WARNING.value,
        RuntimeEventType.VRAM_LIMIT_REACHED.value,
    ],
}

ALL_RUNTIME_EVENT_TYPES: list[str] = [t.value for t in RuntimeEventType]
