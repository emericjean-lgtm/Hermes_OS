"""Resource models for the Runtime Resource Manager (HOS-035)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class ResourceType(str, Enum):
    """Types of resources that can be tracked."""

    VRAM = "vram"
    RAM = "ram"
    CPU = "cpu"
    GPU_TEMP = "gpu_temp"
    MODEL_WEIGHT = "model_weight"


class ResourceStatus(str, Enum):
    """Health status of a resource."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class GPUInfo:
    """GPU hardware information snapshot.

    All memory values in bytes.
    """

    name: str = "unknown"
    vendor: str = "unknown"
    vram_total_bytes: int = 0
    vram_used_bytes: int = 0
    vram_free_bytes: int = 0
    temperature_celsius: Optional[float] = None
    utilization_pct: Optional[float] = None
    available: bool = True


@dataclass
class ResourceLimit:
    """Configuration limits for a resource type."""

    resource_type: ResourceType
    total_bytes: int
    warning_threshold_pct: float = 0.85   # Publish warning above this
    critical_threshold_pct: float = 0.95  # Publish critical above this


@dataclass
class ResourceSnapshot:
    """Current state of a tracked resource."""

    resource_type: ResourceType
    total_bytes: int
    used_bytes: int
    free_bytes: int
    status: ResourceStatus = ResourceStatus.HEALTHY
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def usage_pct(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.used_bytes / self.total_bytes

    def with_limits(self, limit: ResourceLimit) -> ResourceStatus:
        """Evaluate status against configured thresholds."""
        pct = self.usage_pct
        if pct >= limit.critical_threshold_pct:
            return ResourceStatus.CRITICAL
        if pct >= limit.warning_threshold_pct:
            return ResourceStatus.WARNING
        return ResourceStatus.HEALTHY


@dataclass
class ResourceAllocation:
    """Represents an active resource allocation for a runtime."""

    allocation_id: str = field(default_factory=lambda: uuid4().hex)
    runtime_id: str = ""
    resource_type: ResourceType = ResourceType.VRAM
    bytes_requested: int = 0
    bytes_allocated: int = 0
    model_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released: bool = False
    priority: int = 0  # Higher = more important

    def release(self) -> None:
        self.released = True


@dataclass
class ResourceAllocationResult:
    """Result of an allocation attempt."""

    success: bool
    allocation: Optional[ResourceAllocation] = None
    reason: str = ""
    fallback_runtime: Optional[str] = None
    suggested_model: Optional[str] = None
