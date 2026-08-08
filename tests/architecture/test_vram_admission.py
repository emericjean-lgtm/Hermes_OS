"""Tests for HOS-069 Phase B — real VRAM admission control in
RealTaskExecutor: before this, GraphExecutor's bounded parallelism
(HOS-068) was the only thing standing between concurrent tasks and VRAM
exhaustion, and it never actually asked what VRAM was available — it just
capped how many tasks could run at once, blind to which models they'd load.

Fully hermetic: a fake ResourceManager stands in for the real one, no real
GPU or Ollama needed.
"""
from __future__ import annotations

import time

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError


class _FakeAllocationResult:
    def __init__(self, success: bool, reason: str = ""):
        self.success = success
        self.reason = reason


class _FakeResourceManager:
    """Returns a scripted sequence of can_allocate() results, one per call,
    then repeats the last one — enough to simulate "denied, then frees up
    after a task finishes" without real GPU telemetry."""

    def __init__(self, results: list[bool]):
        self._results = results
        self.calls: list[tuple[int, str]] = []

    def can_allocate(self, bytes_requested, runtime_id, model_name=None, priority=0):
        self.calls.append((bytes_requested, model_name))
        idx = min(len(self.calls) - 1, len(self._results) - 1)
        ok = self._results[idx]
        return _FakeAllocationResult(ok, reason="" if ok else "VRAM would reach 95%")


def _executor(resource_manager, vram_gb_for, **kwargs) -> RealTaskExecutor:
    return RealTaskExecutor(
        chat=kwargs.pop("chat", None),
        resource_manager=resource_manager,
        vram_gb_for=vram_gb_for,
        vram_wait_s=kwargs.pop("vram_wait_s", 0.3),
        vram_poll_interval_s=kwargs.pop("vram_poll_interval_s", 0.05),
        **kwargs,
    )


class _Task:
    task_id = "t1"
    title = "do the thing"


class TestVramAdmissionNoOp:
    def test_no_resource_manager_is_a_no_op(self):
        ex = RealTaskExecutor(resource_manager=None, vram_gb_for=lambda m: 20.0)
        ex._check_vram_admission("big-model")  # must not raise/wait

    def test_no_vram_gb_for_is_a_no_op(self):
        ex = RealTaskExecutor(resource_manager=_FakeResourceManager([False]), vram_gb_for=None)
        ex._check_vram_admission("big-model")  # must not raise/wait

    def test_unknown_model_with_no_estimate_is_a_no_op(self):
        rm = _FakeResourceManager([False])
        ex = _executor(rm, vram_gb_for=lambda m: None)
        ex._check_vram_admission("unknown-model")
        assert rm.calls == []  # never even asked


class TestVramAdmissionGate:
    def test_immediate_allow_does_not_wait(self):
        rm = _FakeResourceManager([True])
        ex = _executor(rm, vram_gb_for=lambda m: 9.0)
        t0 = time.monotonic()
        ex._check_vram_admission("qwen3.5:14b")
        assert time.monotonic() - t0 < 0.1
        assert rm.calls == [(9 * 1024**3, "qwen3.5:14b")]

    def test_denied_then_freed_up_proceeds_after_waiting(self):
        rm = _FakeResourceManager([False, False, True])
        ex = _executor(rm, vram_gb_for=lambda m: 9.0)
        ex._check_vram_admission("qwen3.5:14b")  # must not raise
        assert len(rm.calls) == 3

    def test_never_freed_up_raises_runtime_unavailable(self):
        rm = _FakeResourceManager([False])
        ex = _executor(rm, vram_gb_for=lambda m: 9.0, vram_wait_s=0.15, vram_poll_interval_s=0.05)
        with pytest.raises(RuntimeUnavailableError, match="VRAM"):
            ex._check_vram_admission("qwen3.5:14b")

class TestActiveVramUnload:
    """HOS-072: past the halfway point of the wait with still no admission,
    _check_vram_admission actively unloads another resident model instead
    of only ever waiting for its own keep_alive timer."""

    def test_unloads_the_largest_other_resident_model_once(self):
        # 11 denied attempts before success, polled every 50ms against a
        # 600ms ceiling: the halfway point (300ms) is crossed by roughly
        # the 7th check, leaving several denied checks afterward before
        # success on the 11th — enough margin against timing jitter that
        # the unload trigger is reliably exercised before it succeeds.
        rm = _FakeResourceManager([False] * 10 + [True])
        resident = [
            {"name": "small-model", "size_vram": 2_000_000_000},
            {"name": "target-model", "size_vram": 9_000_000_000},  # excluded
            {"name": "big-model", "size_vram": 8_000_000_000},
        ]
        unload_calls: list[str] = []

        async def list_running():
            return resident

        async def unload(name: str):
            unload_calls.append(name)

        ex = _executor(
            rm, vram_gb_for=lambda m: 9.0,
            vram_wait_s=0.6, vram_poll_interval_s=0.05,
            list_running_for=list_running, unload_for=unload,
        )
        ex._check_vram_admission("target-model")
        # "big-model" (8GB), not "small-model" (2GB) or "target-model" itself.
        assert unload_calls == ["big-model"]

    def test_never_tries_to_unload_the_target_model_itself(self):
        rm = _FakeResourceManager([False] * 10 + [True])
        resident = [{"name": "target-model", "size_vram": 9_000_000_000}]
        unload_calls: list[str] = []

        async def list_running():
            return resident

        async def unload(name: str):
            unload_calls.append(name)

        ex = _executor(
            rm, vram_gb_for=lambda m: 9.0,
            vram_wait_s=0.6, vram_poll_interval_s=0.05,
            list_running_for=list_running, unload_for=unload,
        )
        ex._check_vram_admission("target-model")
        assert unload_calls == []  # nothing else was resident to unload

    def test_quick_admission_never_attempts_an_unload(self):
        rm = _FakeResourceManager([True])
        unload_calls: list[str] = []

        async def list_running():
            return [{"name": "other", "size_vram": 1}]

        async def unload(name: str):
            unload_calls.append(name)

        ex = _executor(
            rm, vram_gb_for=lambda m: 9.0,
            list_running_for=list_running, unload_for=unload,
        )
        ex._check_vram_admission("target-model")
        assert unload_calls == []

    def test_unload_failure_does_not_break_the_wait(self):
        """Best-effort: a broken list/unload callable must not prevent the
        normal poll-wait from eventually succeeding or failing honestly."""
        rm = _FakeResourceManager([False] * 10 + [True])

        async def list_running():
            raise ConnectionError("ollama unreachable")

        ex = _executor(
            rm, vram_gb_for=lambda m: 9.0,
            vram_wait_s=0.6, vram_poll_interval_s=0.05,
            list_running_for=list_running, unload_for=None,
        )
        ex._check_vram_admission("target-model")  # must not raise

    def test_execute_raises_runtime_unavailable_when_vram_never_frees(self):
        """End-to-end through execute(): the local chat call must never be
        attempted when admission never succeeds — VRAM exhaustion, not a
        runtime failure, is the actual reason this task didn't run."""
        rm = _FakeResourceManager([False])
        chat_called = {"n": 0}

        async def _chat(**kwargs):
            chat_called["n"] += 1
            raise AssertionError("chat should never be called when VRAM is denied")

        ex = _executor(rm, vram_gb_for=lambda m: 9.0, chat=_chat,
                       vram_wait_s=0.1, vram_poll_interval_s=0.03,
                       default_model="qwen3.5:14b")
        with pytest.raises(RuntimeUnavailableError):
            ex.execute(_Task())
        assert chat_called["n"] == 0
