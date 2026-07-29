"""KTransformers scheduler — concurrency, batching, priority (HOS-052)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from backend.runtime.ktransformers.kt_models import (
    KTInferenceRequest,
    KTInferenceResult,
    KTSchedulerStats,
)


class KTScheduler:
    """Thread-safe inference scheduler with priority queues and batching.

    Four priority levels: CRITICAL(3) > HIGH(2) > NORMAL(1) > LOW(0).
    Supports max concurrency control and request timeout.
    """

    def __init__(self, max_concurrent: int = 4, request_timeout_s: float = 120.0):
        self._lock = threading.RLock()
        self._max_concurrent = max_concurrent
        self._request_timeout_s = request_timeout_s

        # Priority queues (higher index = higher priority)
        self._queues: list[deque[KTInferenceRequest]] = [
            deque(),  # 0 = LOW
            deque(),  # 1 = NORMAL
            deque(),  # 2 = HIGH
            deque(),  # 3 = CRITICAL
        ]

        self._active: dict[str, KTInferenceRequest] = {}
        self._results: dict[str, KTInferenceResult] = {}
        self._completed_count = 0
        self._failed_count = 0
        self._total_tokens = 0
        self._total_duration_ms = 0.0
        self._total_wait_ms = 0.0

    # ── Enqueue ───────────────────────────────────────

    def enqueue(self, request: KTInferenceRequest, priority: int = 1) -> bool:
        """Enqueue an inference request with given priority (0-3)."""
        with self._lock:
            level = max(0, min(3, priority))
            self._queues[level].append(request)
            return True

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending or active request."""
        with self._lock:
            # Remove from queues
            for q in self._queues:
                for i, req in enumerate(q):
                    if req.id == request_id:
                        del q[i]
                        return True
            # Remove from active
            if request_id in self._active:
                del self._active[request_id]
                self._failed_count += 1
                return True
            return False

    # ── Dequeue (simulated execution) ─────────────────

    def dequeue_next(self) -> Optional[KTInferenceRequest]:
        """Get the next request to process (highest priority, FIFO per level)."""
        with self._lock:
            if len(self._active) >= self._max_concurrent:
                return None
            for level in range(3, -1, -1):
                if self._queues[level]:
                    req = self._queues[level].popleft()
                    self._active[req.id] = req
                    return req
            return None

    def complete(self, request_id: str, result: KTInferenceResult) -> bool:
        """Mark a request as completed and store its result."""
        with self._lock:
            if request_id not in self._active:
                return False
            del self._active[request_id]
            self._results[request_id] = result
            self._completed_count += 1
            self._total_tokens += result.tokens_generated
            self._total_duration_ms += result.duration_ms
            return True

    def fail(self, request_id: str, error: str = "") -> bool:
        """Mark a request as failed."""
        with self._lock:
            if request_id not in self._active:
                return False
            del self._active[request_id]
            self._failed_count += 1
            return True

    # ── Batch execution (simulated) ───────────────────

    def process_batch(self, max_batch: int = 4) -> list[KTInferenceResult]:
        """Simulate processing a batch of requests. Returns results.

        Each request gets a simulated inference result with realistic timing.
        """
        results: list[KTInferenceResult] = []
        for _ in range(max_batch):
            req = self.dequeue_next()
            if req is None:
                break
            # Simulate inference
            tokens = min(req.max_tokens, 128)
            duration_ms = tokens * 15.0  # ~15ms per token
            tokens_per_sec = 1000.0 * tokens / max(1.0, duration_ms)

            result = KTInferenceResult(
                request_id=req.id,
                model_id=req.model_id,
                text=f"[KTransformers response for: {req.prompt[:50]}...]",
                tokens_generated=tokens,
                tokens_per_second=tokens_per_sec,
                duration_ms=duration_ms,
            )
            self.complete(req.id, result)
            results.append(result)
        return results

    # ── Statistics ────────────────────────────────────

    def stats(self) -> KTSchedulerStats:
        """Get scheduler statistics."""
        with self._lock:
            total_queue = sum(len(q) for q in self._queues)
            total_completed = self._completed_count
            avg_dur = self._total_duration_ms / max(1, total_completed)
            return KTSchedulerStats(
                queue_length=total_queue,
                active_requests=len(self._active),
                completed_requests=self._completed_count,
                failed_requests=self._failed_count,
                avg_wait_ms=self._total_wait_ms / max(1, total_completed),
                avg_duration_ms=avg_dur,
                total_tokens=self._total_tokens,
            )

    def queue_length(self) -> int:
        """Total number of requests in all queues."""
        with self._lock:
            return sum(len(q) for q in self._queues)

    def active_count(self) -> int:
        """Number of currently active requests."""
        with self._lock:
            return len(self._active)

    def cancel_all(self) -> int:
        """Cancel all queued requests. Active ones continue."""
        count = 0
        with self._lock:
            for q in self._queues:
                count += len(q)
                q.clear()
        return count
