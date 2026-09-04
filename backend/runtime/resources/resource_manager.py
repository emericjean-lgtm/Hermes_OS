"""Runtime Resource Manager (HOS-035).

Central orchestrator for resource monitoring, allocation, and event publishing.
"""

from __future__ import annotations

import dataclasses

import threading
from typing import Callable, Optional

from backend.runtime.resources.allocation_policy import (
    AllocationPolicy,
    DefaultAllocationPolicy,
)
from backend.runtime.resources.gpu_monitor import GPUMonitor, NoopGPUMonitor
from backend.runtime.resources.memory_manager import MemoryManager
from backend.runtime.resources.resource_models import (
    GPUInfo,
    ResourceAllocation,
    ResourceAllocationResult,
    ResourceLimit,
    ResourceSnapshot,
    ResourceStatus,
    ResourceType,
)


class ResourceManager:
    """Manages runtime resources (VRAM, RAM, CPU).

    Integrates with:
    - GPUMonitor for hardware telemetry
    - MemoryManager for system RAM
    - AllocationPolicy for allocation decisions
    - RuntimeEventBus for threshold-based alerts

    Thread-safe.
    """

    def __init__(
        self,
        gpu_monitor: Optional[GPUMonitor] = None,
        memory_manager: Optional[MemoryManager] = None,
        policy: Optional[AllocationPolicy] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._gpu = gpu_monitor or NoopGPUMonitor()
        self._memory = memory_manager or MemoryManager()
        self._policy = policy or DefaultAllocationPolicy()
        self._on_event = on_event  # Callback: on_event(event_type, payload)

        # Track active allocations
        self._allocations: dict[str, ResourceAllocation] = {}

        # Resource limits (configurable)
        self._limits: dict[ResourceType, ResourceLimit] = {
            ResourceType.VRAM: ResourceLimit(
                resource_type=ResourceType.VRAM,
                total_bytes=16 * 1024 * 1024 * 1024,  # 16 GB default
                warning_threshold_pct=0.85,
                critical_threshold_pct=0.95,
            ),
            ResourceType.RAM: ResourceLimit(
                resource_type=ResourceType.RAM,
                total_bytes=32 * 1024 * 1024 * 1024,  # 32 GB default
                warning_threshold_pct=0.85,
                critical_threshold_pct=0.95,
            ),
        }

    # ── Monitoring ─────────────────────────────────────────

    def get_gpu_info(self) -> GPUInfo:
        """Get current GPU state."""
        return self._gpu.poll()

    def get_memory_snapshot(self) -> ResourceSnapshot:
        """Get current RAM state."""
        return self._memory.poll()

    def get_status(self) -> dict:
        """Return a comprehensive status dictionary."""
        gpu = self.get_gpu_info()
        mem = self.get_memory_snapshot()
        with self._lock:
            allocations = [a for a in self._allocations.values() if not a.released]
        return {
            "gpu": {
                "name": gpu.name,
                "vendor": gpu.vendor,
                "vram_total_bytes": gpu.vram_total_bytes,
                "vram_used_bytes": gpu.vram_used_bytes,
                "vram_free_bytes": gpu.vram_free_bytes,
                "temperature_celsius": gpu.temperature_celsius,
                "utilization_pct": gpu.utilization_pct,
                "available": gpu.available,
            },
            "ram": {
                "total_bytes": mem.total_bytes,
                "used_bytes": mem.used_bytes,
                "free_bytes": mem.free_bytes,
                "usage_pct": round(mem.usage_pct * 100, 1),
                "status": mem.status.value,
            },
            "allocations": len(allocations),
            "allocated_bytes": sum(a.bytes_allocated for a in allocations),
        }

    # ── Allocation ─────────────────────────────────────────

    def _octets_reserves(self, resource_type: ResourceType) -> int:
        """Ce qui est promis et pas encore visible sur le compteur physique.

        Lu sans verrou : `reserve_resources` tient déjà `self._lock` quand
        il appelle `can_allocate`, et ce verrou n'est pas réentrant. La
        lecture d'un `dict` sous le GIL ne corrompt rien, et la décision
        qui compte — celle qui enregistre — est bien sérialisée.
        """
        return sum(a.bytes_requested for a in self._allocations.values()
                   if not a.released and a.resource_type is resource_type)

    def can_allocate(
        self,
        bytes_requested: int,
        runtime_id: str,
        resource_type: ResourceType = ResourceType.VRAM,
        model_name: Optional[str] = None,
        priority: int = 0,
    ) -> ResourceAllocationResult:
        """Cette allocation est-elle possible, réservations comprises ?

        ## Le défaut que ce compte corrige (§6.2, A-13)

        La décision se prenait sur le **seul compteur physique**, sans
        jamais regarder `self._allocations`. Mesuré sur une carte simulée
        de 16 Gio dont 2 déjà pris : deux réservations de 8 Gio passaient
        toutes les deux — 18 Gio promis sur 16 disponibles.

        `reserve_resources` tient pourtant un verrou. Le verrou n'était pas
        le problème : il sérialisait deux décisions qui, chacune, lisaient
        un compteur que la première n'avait pas encore fait bouger. Un
        modèle réservé n'occupe la VRAM qu'une fois **chargé**, et le
        chargement vient après.

        ## Ce que le compte coûte, et dans quel sens

        Une fois le modèle chargé, sa consommation apparaît sur le compteur
        physique **et** reste comptée dans la réservation : elle est donc
        comptée deux fois jusqu'à la libération. On refuse ainsi parfois
        une allocation qui aurait tenu — **jamais l'inverse**. C'est la
        même prudence assumée que `_check_vram_admission` : « occasionally
        waiting when the model was already loaded, never the other way
        around ».
        """
        gpu = self.get_gpu_info()
        reserves = self._octets_reserves(resource_type)

        if resource_type == ResourceType.RAM:
            base = self.get_memory_snapshot()
            snapshot = ResourceSnapshot(
                resource_type=ResourceType.RAM,
                total_bytes=base.total_bytes,
                used_bytes=base.used_bytes + reserves,
                free_bytes=max(0, base.free_bytes - reserves),
            )
        else:
            snapshot = ResourceSnapshot(
                resource_type=ResourceType.VRAM,
                total_bytes=gpu.vram_total_bytes,
                used_bytes=gpu.vram_used_bytes + reserves,
                free_bytes=max(0, gpu.vram_free_bytes - reserves),
            )
            # La politique lit la VRAM sur `gpu_info`, pas sur le snapshot :
            # il faut donc lui présenter la même vue augmentée, sans quoi
            # le compte des réservations resterait sans effet.
            gpu = dataclasses.replace(
                gpu,
                vram_used_bytes=gpu.vram_used_bytes + reserves,
                vram_free_bytes=max(0, gpu.vram_free_bytes - reserves),
            )

        return self._policy.can_allocate(
            snapshot, gpu, bytes_requested, runtime_id, model_name, priority
        )

    def reserve_resources(
        self,
        bytes_requested: int,
        runtime_id: str,
        resource_type: ResourceType = ResourceType.VRAM,
        model_name: Optional[str] = None,
        priority: int = 0,
    ) -> ResourceAllocationResult:
        """Attempt to allocate resources. Thread-safe."""
        with self._lock:
            result = self.can_allocate(
                bytes_requested, runtime_id, resource_type, model_name, priority
            )
            if result.success and result.allocation is not None:
                self._allocations[result.allocation.allocation_id] = result.allocation

                # Publish allocation event
                if self._on_event:
                    self._on_event(
                        f"{resource_type.value}.allocated",
                        {
                            "allocation_id": result.allocation.allocation_id,
                            "runtime_id": runtime_id,
                            "model_name": model_name,
                            "bytes": bytes_requested,
                        },
                        severity="info",
                    )
            elif not result.success and self._on_event:
                # Publish allocation failure
                self._on_event(
                    "resource.allocation_failed",
                    {
                        "runtime_id": runtime_id,
                        "reason": result.reason,
                        "resource_type": resource_type.value,
                        "bytes_requested": bytes_requested,
                    },
                    severity="warning",
                )

            return result

    def release_resources(self, allocation_id: str) -> Optional[int]:
        """Release an allocation. Returns bytes released or None."""
        with self._lock:
            alloc = self._allocations.get(allocation_id)
            if alloc is None or alloc.released:
                return None
            alloc.release()

            if self._on_event:
                self._on_event(
                    "resource.released",
                    {
                        "allocation_id": allocation_id,
                        "runtime_id": alloc.runtime_id,
                        "bytes": alloc.bytes_allocated,
                    },
                    severity="info",
                )

            return alloc.bytes_allocated

    def get_current_allocations(self) -> list[ResourceAllocation]:
        """Return all active (unreleased) allocations."""
        with self._lock:
            return [a for a in self._allocations.values() if not a.released]

    # ── Threshold Monitoring ───────────────────────────────

    def check_thresholds(self) -> list[tuple[str, str]]:
        """Check all resource thresholds. Returns [(event_type, severity), ...].

        Should be called periodically (e.g., every 5 seconds).
        Publishes events through the on_event callback.
        """
        alerts: list[tuple[str, str]] = []

        # GPU/VRAM
        gpu = self.get_gpu_info()
        if gpu.available and gpu.vram_total_bytes > 0:
            vram_pct = gpu.vram_used_bytes / gpu.vram_total_bytes
            vram_limit = self._limits.get(ResourceType.VRAM)

            status = ResourceStatus.HEALTHY
            if vram_limit and vram_pct >= vram_limit.critical_threshold_pct:
                status = ResourceStatus.CRITICAL
                alerts.append(("vram.limit_reached", "critical"))
            elif vram_limit and vram_pct >= vram_limit.warning_threshold_pct:
                status = ResourceStatus.WARNING
                alerts.append(("memory.warning", "warning"))

            # GPU temperature
            if gpu.temperature_celsius is not None and gpu.temperature_celsius > 85.0:
                alerts.append(("resource.warning", "warning"))

        # RAM
        mem = self.get_memory_snapshot()
        if mem.total_bytes > 0:
            ram_limit = self._limits.get(ResourceType.RAM)
            if ram_limit and mem.usage_pct >= ram_limit.critical_threshold_pct:
                alerts.append(("memory.warning", "critical"))
            elif ram_limit and mem.usage_pct >= ram_limit.warning_threshold_pct:
                alerts.append(("memory.warning", "warning"))

        # Publish events
        if self._on_event:
            for event_type, severity in alerts:
                self._on_event(
                    event_type,
                    {
                        "gpu_vram_pct": (
                            round(gpu.vram_used_bytes / max(gpu.vram_total_bytes, 1) * 100, 1)
                            if gpu.vram_total_bytes > 0
                            else 0
                        ),
                        "ram_pct": round(mem.usage_pct * 100, 1),
                        "gpu_temp": gpu.temperature_celsius,
                    },
                    severity=severity,
                )

        return alerts

    # ── Configuration ──────────────────────────────────────

    def set_limit(self, resource_type: ResourceType, limit: ResourceLimit) -> None:
        """Override a resource limit."""
        with self._lock:
            self._limits[resource_type] = limit

    def set_policy(self, policy: AllocationPolicy) -> None:
        """Change the allocation policy."""
        with self._lock:
            self._policy = policy

    def set_event_callback(self, callback: Optional[Callable]) -> None:
        """Set or clear the event publishing callback."""
        self._on_event = callback
