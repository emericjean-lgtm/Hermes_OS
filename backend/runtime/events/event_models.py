"""Event models for the Runtime Event Bus (HOS-034)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RuntimeEventSeverity(str, Enum):
    """Severity levels for runtime events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RuntimeEventModel(BaseModel):
    """Immutable runtime event representation.

    Fields:
        id: Unique event identifier (UUID hex).
        runtime_id: The runtime that produced the event.
        event_type: Machine-readable event type string.
        severity: Severity level.
        timestamp: ISO-8601 UTC timestamp.
        source: Component or subsystem that published the event.
        payload: Arbitrary JSON-serialisable data.
        correlation_id: Optional grouping key for related events.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    runtime_id: str
    event_type: str
    severity: RuntimeEventSeverity = RuntimeEventSeverity.INFO
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "runtime"
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None

    def dict_safe(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary (timestamp as string)."""
        return {
            "id": self.id,
            "runtime_id": self.runtime_id,
            "event_type": self.event_type,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }


class RuntimeEventCreateRequest(BaseModel):
    """Request model for creating an event via API."""

    runtime_id: str
    event_type: str
    severity: RuntimeEventSeverity = RuntimeEventSeverity.INFO
    source: str = "api"
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class RuntimeEventResponse(BaseModel):
    """Response model for a single event."""

    id: str
    runtime_id: str
    event_type: str
    severity: str
    timestamp: str
    source: str
    payload: dict[str, Any]
    correlation_id: Optional[str] = None


class RuntimeEventListResponse(BaseModel):
    """Response model for a list of events."""

    events: list[RuntimeEventResponse]
    total: int
    runtime_id: Optional[str] = None
