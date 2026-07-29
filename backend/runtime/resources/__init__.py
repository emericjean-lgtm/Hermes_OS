"""Runtime Resource Manager (HOS-035).

Intelligent resource management for runtime execution:
- GPU/VRAM monitoring
- Memory allocation & deallocation
- Model loading/unloading with priority
- Resource threshold-based event publishing
"""

from backend.runtime.resources.resource_models import (
    ResourceType,
    ResourceStatus,
    ResourceSnapshot,
    ResourceAllocation,
    ResourceLimit,
    ResourceAllocationResult,
    GPUInfo,
)
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.allocation_policy import (
    AllocationPolicy,
    DefaultAllocationPolicy,
    VramAwareAllocationPolicy,
)
from backend.runtime.resources.gpu_monitor import GPUMonitor, NoopGPUMonitor
from backend.runtime.resources.memory_manager import MemoryManager

__all__ = [
    "ResourceType",
    "ResourceStatus",
    "ResourceSnapshot",
    "ResourceAllocation",
    "ResourceLimit",
    "ResourceAllocationResult",
    "GPUInfo",
    "ResourceManager",
    "AllocationPolicy",
    "DefaultAllocationPolicy",
    "VramAwareAllocationPolicy",
    "GPUMonitor",
    "NoopGPUMonitor",
    "MemoryManager",
]
