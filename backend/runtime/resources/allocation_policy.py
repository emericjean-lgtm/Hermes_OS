"""Allocation Policy Engine for the Runtime Resource Manager (HOS-035).

Defines allocation strategies:
- Default: first-fit, priority-aware
- VramAware: respects VRAM thresholds, suggests fallback models
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Optional

from backend.runtime.resources.resource_models import (
    GPUInfo,
    ResourceAllocation,
    ResourceAllocationResult,
    ResourceSnapshot,
    ResourceStatus,
    ResourceType,
)


class AllocationPolicy(ABC):
    """Abstract allocation policy."""

    @abstractmethod
    def can_allocate(
        self,
        snapshot: ResourceSnapshot,
        gpu_info: GPUInfo,
        bytes_requested: int,
        runtime_id: str,
        model_name: Optional[str] = None,
        priority: int = 0,
    ) -> ResourceAllocationResult:
        """Determine if a resource allocation can proceed."""
        ...


class DefaultAllocationPolicy(AllocationPolicy):
    """Simple first-fit policy with priority."""

    def __init__(
        self,
        max_vram_usage_pct: float = 0.90,
        max_ram_usage_pct: float = 0.85,
    ) -> None:
        self.max_vram_usage_pct = max_vram_usage_pct
        self.max_ram_usage_pct = max_ram_usage_pct

    def can_allocate(
        self,
        snapshot: ResourceSnapshot,
        gpu_info: GPUInfo,
        bytes_requested: int,
        runtime_id: str = "",
        model_name: Optional[str] = None,
        priority: int = 0,
    ) -> ResourceAllocationResult:
        """Check if allocation is possible."""
        if snapshot.resource_type == ResourceType.VRAM:
            if gpu_info.vram_total_bytes == 0:
                # No GPU detected — skip VRAM check, allow allocation
                allocation = ResourceAllocation(
                    runtime_id=runtime_id,
                    resource_type=snapshot.resource_type,
                    bytes_requested=bytes_requested,
                    bytes_allocated=bytes_requested,
                    model_name=model_name,
                    priority=priority,
                )
                return ResourceAllocationResult(
                    success=True,
                    allocation=allocation,
                    reason="no gpu detected — skip vram check",
                )

            after = gpu_info.vram_used_bytes + bytes_requested
            pct = after / gpu_info.vram_total_bytes

            if pct > self.max_vram_usage_pct:
                suggested = self._suggest_smaller_model(
                    bytes_requested,
                    gpu_info.vram_free_bytes,
                )
                return ResourceAllocationResult(
                    success=False,
                    reason=f"VRAM would reach {pct*100:.0f}% > {self.max_vram_usage_pct*100:.0f}%",
                    suggested_model=suggested,
                )

        if snapshot.resource_type == ResourceType.RAM:
            after = snapshot.used_bytes + bytes_requested
            pct = after / max(snapshot.total_bytes, 1)

            if pct > self.max_ram_usage_pct:
                return ResourceAllocationResult(
                    success=False,
                    reason=f"RAM would reach {pct*100:.0f}% > {self.max_ram_usage_pct*100:.0f}%",
                )

        allocation = ResourceAllocation(
            runtime_id=runtime_id,
            resource_type=snapshot.resource_type,
            bytes_requested=bytes_requested,
            bytes_allocated=bytes_requested,
            model_name=model_name,
            priority=priority,
        )
        return ResourceAllocationResult(success=True, allocation=allocation)

    def _suggest_smaller_model(
        self,
        requested_bytes: int,
        available_bytes: int,
    ) -> Optional[str]:
        """Suggest a smaller model tier if available."""
        tiers: list[tuple[str, int]] = [
            ("Tier 1 (1B)", 1024 * 1024 * 1024),       # ~1 GB
            ("Tier 2 (3B)", 3 * 1024 * 1024 * 1024),   # ~3 GB
            ("Tier 3 (7B)", 7 * 1024 * 1024 * 1024),   # ~7 GB
            ("Tier 4 (14B)", 14 * 1024 * 1024 * 1024), # ~14 GB
            ("Tier 5 (32B)", 32 * 1024 * 1024 * 1024), # ~32 GB
        ]
        for name, size in tiers:
            if size <= available_bytes:
                return name
        return None


class VramAwareAllocationPolicy(DefaultAllocationPolicy):
    """Extended policy that also checks GPU temperature and utilisation."""

    def __init__(
        self,
        max_vram_usage_pct: float = 0.90,
        max_ram_usage_pct: float = 0.85,
        max_gpu_temp_c: float = 85.0,
        max_gpu_util_pct: float = 95.0,
    ) -> None:
        super().__init__(max_vram_usage_pct, max_ram_usage_pct)
        self.max_gpu_temp_c = max_gpu_temp_c
        self.max_gpu_util_pct = max_gpu_util_pct

    def can_allocate(
        self,
        snapshot: ResourceSnapshot,
        gpu_info: GPUInfo,
        bytes_requested: int,
        runtime_id: str = "",
        model_name: Optional[str] = None,
        priority: int = 0,
    ) -> ResourceAllocationResult:
        # Temperature check
        if (
            gpu_info.temperature_celsius is not None
            and gpu_info.temperature_celsius > self.max_gpu_temp_c
        ):
            return ResourceAllocationResult(
                success=False,
                reason=(
                    f"GPU temperature {gpu_info.temperature_celsius:.0f}°C "
                    f"> {self.max_gpu_temp_c:.0f}°C — throttling"
                ),
                fallback_runtime="cpu",
            )

        # Utilisation check
        if (
            gpu_info.utilization_pct is not None
            and gpu_info.utilization_pct > self.max_gpu_util_pct
        ):
            return ResourceAllocationResult(
                success=False,
                reason=(
                    f"GPU utilisation {gpu_info.utilization_pct:.0f}% "
                    f"> {self.max_gpu_util_pct:.0f}% — busy"
                ),
            )

        return super().can_allocate(
            snapshot, gpu_info, bytes_requested, runtime_id, model_name, priority
        )
