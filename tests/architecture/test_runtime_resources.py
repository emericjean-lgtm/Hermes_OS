"""Tests for the Runtime Resource Manager (HOS-035)."""

from __future__ import annotations

import threading

import pytest

from backend.runtime.resources.allocation_policy import (
    DefaultAllocationPolicy,
    VramAwareAllocationPolicy,
)
from backend.runtime.resources.gpu_monitor import GPUMonitor, NoopGPUMonitor
from backend.runtime.resources.memory_manager import MemoryManager
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import (
    GPUInfo,
    ResourceAllocation,
    ResourceAllocationResult,
    ResourceLimit,
    ResourceSnapshot,
    ResourceStatus,
    ResourceType,
)


# ─── Mock GPU for VRAM threshold testing ───────────────────

class _MockGPUMonitor(GPUMonitor):
    """GPU monitor that reports fixed VRAM values for testing."""

    def __init__(self, total: int, used: int, temp: float = 65.0, util: float = 40.0) -> None:
        super().__init__()
        self._total = total
        self._used = used
        self._temp = temp
        self._util = util

    def _poll_now(self) -> GPUInfo:
        return GPUInfo(
            name="Mock GPU",
            vendor="Test",
            vram_total_bytes=self._total,
            vram_used_bytes=self._used,
            vram_free_bytes=max(0, self._total - self._used),
            temperature_celsius=self._temp,
            utilization_pct=self._util,
            available=True,
        )


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def manager() -> ResourceManager:
    """Manager with no GPU (CI/testing safe)."""
    return ResourceManager(
        gpu_monitor=NoopGPUMonitor(),
        memory_manager=MemoryManager(),
        policy=DefaultAllocationPolicy(),
    )


@pytest.fixture
def manager_with_gpu() -> ResourceManager:
    """Manager with a simulated 16 GB GPU, 4 GB used."""
    return ResourceManager(
        gpu_monitor=_MockGPUMonitor(
            total=16 * 1024 * 1024 * 1024,
            used=4 * 1024 * 1024 * 1024,
        ),
        memory_manager=MemoryManager(),
        policy=DefaultAllocationPolicy(),
    )


@pytest.fixture
def vram_aware_manager() -> ResourceManager:
    return ResourceManager(
        gpu_monitor=NoopGPUMonitor(),
        policy=VramAwareAllocationPolicy(),
    )


@pytest.fixture
def sample_gpu() -> GPUInfo:
    return GPUInfo(
        name="AMD 6800",
        vendor="AMD",
        vram_total_bytes=16 * 1024 * 1024 * 1024,
        vram_used_bytes=4 * 1024 * 1024 * 1024,
        vram_free_bytes=12 * 1024 * 1024 * 1024,
        temperature_celsius=65.0,
        utilization_pct=40.0,
        available=True,
    )


# ─── 1. Resource Allocation Tests ──────────────────────────


class TestResourceAllocation:
    def test_can_allocate_under_limit(self, manager_with_gpu: ResourceManager):
        """Allocation succeeds when resources are available."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        result = manager_with_gpu.can_allocate(
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="test-runtime",
        )
        assert result.success
        assert result.allocation is not None
        assert result.allocation.runtime_id == "test-runtime"

    def test_can_allocate_over_limit(self, manager_with_gpu: ResourceManager):
        """Allocation is refused when it would exceed thresholds."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
            warning_threshold_pct=0.50,
            critical_threshold_pct=0.90,
        ))
        manager_with_gpu.set_policy(DefaultAllocationPolicy(max_vram_usage_pct=0.60))
        result = manager_with_gpu.can_allocate(
            bytes_requested=16 * 1024 * 1024 * 1024,  # Would exceed 60%
            runtime_id="test-runtime",
        )
        assert not result.success
        assert result.reason

    def test_ci_safe_can_allocate(self, manager: ResourceManager):
        """With no GPU, allocations always succeed (CI-safe)."""
        result = manager.can_allocate(
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="test-runtime",
        )
        assert result.success
        assert "no gpu detected" in result.reason.lower()

    def test_reserve_resources_tracks_allocation(self, manager_with_gpu: ResourceManager):
        """reserve_resources tracks the allocation."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        result = manager_with_gpu.reserve_resources(
            bytes_requested=4 * 1024 * 1024 * 1024,
            runtime_id="runtime-1",
            model_name="qwen3:14b",
        )
        assert result.success
        assert result.allocation is not None

        allocs = manager_with_gpu.get_current_allocations()
        assert len(allocs) == 1
        assert allocs[0].model_name == "qwen3:14b"

    def test_release_resources_frees_allocation(self, manager_with_gpu: ResourceManager):
        """Release correctly frees an allocation."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        result = manager_with_gpu.reserve_resources(
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="runtime-1",
        )
        aid = result.allocation.allocation_id

        released = manager_with_gpu.release_resources(aid)
        assert released == 2 * 1024 * 1024 * 1024

        allocs = manager_with_gpu.get_current_allocations()
        assert len(allocs) == 0

    def test_release_nonexistent_allocation(self, manager: ResourceManager):
        """Releasing a non-existent allocation returns None."""
        assert manager.release_resources("fake-id") is None

    def test_double_release(self, manager: ResourceManager):
        """Double release is idempotent."""
        manager.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        result = manager.reserve_resources(
            bytes_requested=1 * 1024 * 1024 * 1024,
            runtime_id="r1",
        )
        aid = result.allocation.allocation_id

        assert manager.release_resources(aid) is not None
        assert manager.release_resources(aid) is None  # Already released

    def test_get_status(self, manager: ResourceManager):
        """get_status returns a valid dictionary."""
        status = manager.get_status()
        assert "gpu" in status
        assert "ram" in status
        assert "allocations" in status
        assert "allocated_bytes" in status


# ─── 2. Allocation Policy Tests ────────────────────────────


class TestAllocationPolicy:
    def test_default_policy_under_limit(self, sample_gpu: GPUInfo):
        """Default policy allows allocation under limit."""
        policy = DefaultAllocationPolicy(max_vram_usage_pct=0.90)
        snapshot = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=sample_gpu.vram_total_bytes,
            used_bytes=sample_gpu.vram_used_bytes,
            free_bytes=sample_gpu.vram_free_bytes,
        )
        result = policy.can_allocate(
            snapshot, sample_gpu,
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="test",
        )
        assert result.success

    def test_default_policy_over_limit(self, sample_gpu: GPUInfo):
        """Default policy refuses allocation over limit."""
        policy = DefaultAllocationPolicy(max_vram_usage_pct=0.30)
        snapshot = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=sample_gpu.vram_total_bytes,
            used_bytes=sample_gpu.vram_used_bytes,
            free_bytes=sample_gpu.vram_free_bytes,
        )
        result = policy.can_allocate(
            snapshot, sample_gpu,
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="test",
        )
        assert not result.success
        assert result.suggested_model is not None

    def test_vram_aware_temperature_over_limit(self, sample_gpu: GPUInfo):
        """VramAware policy refuses when GPU is too hot."""
        policy = VramAwareAllocationPolicy(max_gpu_temp_c=60.0)
        snapshot = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=sample_gpu.vram_total_bytes,
            used_bytes=sample_gpu.vram_used_bytes,
            free_bytes=sample_gpu.vram_free_bytes,
        )
        result = policy.can_allocate(
            snapshot, sample_gpu,
            bytes_requested=2 * 1024 * 1024 * 1024,
            runtime_id="test",
        )
        assert not result.success
        assert "temperature" in result.reason.lower()

    def test_vram_aware_utilisation_over_limit(self, sample_gpu: GPUInfo):
        """VramAware policy refuses when GPU is too busy."""
        policy = VramAwareAllocationPolicy(max_gpu_util_pct=30.0)
        snapshot = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=sample_gpu.vram_total_bytes,
            used_bytes=sample_gpu.vram_used_bytes,
            free_bytes=sample_gpu.vram_free_bytes,
        )
        result = policy.can_allocate(
            snapshot, sample_gpu,
            bytes_requested=1 * 1024 * 1024 * 1024,
            runtime_id="test",
        )
        assert not result.success
        assert "util" in result.reason.lower()


# ─── 3. Event Publishing Tests ─────────────────────────────


class TestEventPublishing:
    def test_event_on_successful_allocation(self, manager_with_gpu: ResourceManager):
        """Successful allocation publishes an event."""
        events: list[dict] = []

        def on_event(event_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": event_type, "payload": payload, "severity": severity})

        manager_with_gpu.set_event_callback(on_event)
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))

        manager_with_gpu.reserve_resources(
            bytes_requested=4 * 1024 * 1024 * 1024,
            runtime_id="runtime-1",
            model_name="qwen3:14b",
        )
        assert len(events) == 1
        assert events[0]["type"] == "vram.allocated"
        assert events[0]["severity"] == "info"

    def test_event_on_failed_allocation(self, manager_with_gpu: ResourceManager):
        """Failed allocation publishes a warning event."""
        events: list[dict] = []

        def on_event(event_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": event_type, "payload": payload, "severity": severity})

        manager_with_gpu.set_event_callback(on_event)
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        manager_with_gpu.set_policy(DefaultAllocationPolicy(max_vram_usage_pct=0.20))

        manager_with_gpu.reserve_resources(
            bytes_requested=16 * 1024 * 1024 * 1024,
            runtime_id="runtime-1",
        )
        assert len(events) == 1
        assert events[0]["type"] == "resource.allocation_failed"
        assert events[0]["severity"] == "warning"

    def test_event_on_release(self, manager_with_gpu: ResourceManager):
        """Resource release publishes an event."""
        events: list[dict] = []

        def on_event(event_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": event_type, "payload": payload, "severity": severity})

        manager_with_gpu.set_event_callback(on_event)
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))

        result = manager_with_gpu.reserve_resources(
            bytes_requested=4 * 1024 * 1024 * 1024,
            runtime_id="r1",
        )
        manager_with_gpu.release_resources(result.allocation.allocation_id)

        release_events = [e for e in events if e["type"] == "resource.released"]
        assert len(release_events) == 1
        assert release_events[0]["severity"] == "info"


# ─── 4. Threshold Tests ────────────────────────────────────


class TestThresholds:
    def test_check_thresholds_healthy(self, manager: ResourceManager):
        """No alerts when resources are healthy."""
        manager.set_limit(ResourceType.RAM, ResourceLimit(
            resource_type=ResourceType.RAM,
            total_bytes=32 * 1024 * 1024 * 1024,
            warning_threshold_pct=0.99,
            critical_threshold_pct=1.0,
        ))
        alerts = manager.check_thresholds()
        assert len(alerts) == 0  # GPU not available, RAM under limit


# ─── 5. Thread Safety ──────────────────────────────────────


class TestResourceManagerThreadSafety:
    def test_concurrent_allocations(self, manager_with_gpu: ResourceManager):
        """Multiple threads can allocate simultaneously."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        errors: list[Exception] = []
        results: list[ResourceAllocationResult] = []

        def allocate(idx: int) -> None:
            try:
                r = manager_with_gpu.reserve_resources(
                    bytes_requested=1 * 1024 * 1024 * 1024,
                    runtime_id=f"r{idx}",
                    priority=idx,
                )
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=allocate, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        successful = [r for r in results if r.success]
        assert len(successful) >= 1

    def test_concurrent_release(self, manager_with_gpu: ResourceManager):
        """Multiple threads can release simultaneously."""
        manager_with_gpu.set_limit(ResourceType.VRAM, ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=16 * 1024 * 1024 * 1024,
        ))
        ids = []
        for i in range(10):
            r = manager_with_gpu.reserve_resources(
                bytes_requested=1 * 1024 * 1024 * 1024,
                runtime_id=f"r{i}",
            )
            if r.success:
                ids.append(r.allocation.allocation_id)

        errors: list[Exception] = []

        def release(aid: str) -> None:
            try:
                manager_with_gpu.release_resources(aid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=release, args=(aid,)) for aid in ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(manager_with_gpu.get_current_allocations()) == 0


# ─── 6. Resource Models ────────────────────────────────────


class TestResourceModels:
    def test_snapshot_usage_pct(self):
        """usage_pct is computed correctly."""
        snap = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=100,
            used_bytes=42,
            free_bytes=58,
        )
        assert snap.usage_pct == 0.42

    def test_snapshot_with_limits(self):
        """with_limits evaluates threshold correctly."""
        snap = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=100,
            used_bytes=88,
            free_bytes=12,
        )
        limit = ResourceLimit(
            resource_type=ResourceType.VRAM,
            total_bytes=100,
            warning_threshold_pct=0.85,
            critical_threshold_pct=0.95,
        )
        assert snap.with_limits(limit) == ResourceStatus.WARNING

        snap2 = ResourceSnapshot(
            resource_type=ResourceType.VRAM,
            total_bytes=100,
            used_bytes=96,
            free_bytes=4,
        )
        assert snap2.with_limits(limit) == ResourceStatus.CRITICAL

    def test_allocation_release(self):
        """Allocation.release() marks as released."""
        alloc = ResourceAllocation(
            runtime_id="test",
            resource_type=ResourceType.VRAM,
            bytes_requested=100,
            bytes_allocated=100,
        )
        assert not alloc.released
        alloc.release()
        assert alloc.released
