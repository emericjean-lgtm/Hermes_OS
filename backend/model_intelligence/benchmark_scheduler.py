"""Benchmark Scheduler for Hermes OS (HOS-065).

Runs a real, representative prompt against a real model through Ollama and
measures what actually happened — latency, tokens/second, and VRAM — using
Ollama's own reported counters (``eval_count``/``eval_duration``/
``prompt_eval_count`` from a non-streaming ``/api/chat`` response) rather
than estimating from wall-clock time and character counts.

This replaced a version where every field was ``random.uniform()`` around
the model's own static profile numbers, without a single real call to
Ollama, and ``get_latest_benchmarks()`` regenerated a fresh set of random
numbers on every call instead of returning anything that had actually run.
Found while verifying Model Intelligence end to end (see CHANGELOG) — the
"benchmark" a user could trigger from the Models Center had never measured
a single real model.

Design constraints, same reasoning as ``RealTaskExecutor`` (backend/
execution/task_executor.py):

* **Never fabricate.** If Ollama cannot be reached, ``run_benchmark`` raises
  rather than returning invented numbers.
* **Sync entry point, async work.** Called from the same places
  ``RealTaskExecutor``/``TaskDecomposer`` are (FastAPI's threadpool,
  background schedulers), so it owns its own background event loop rather
  than using ``asyncio.run()``, which raises when the calling thread
  already has one.
* **Quality is a completion signal, not a grade.** There is no evaluation
  harness here — ``quality_score`` is 1.0 if the model produced a
  non-empty, non-error response and 0.0 otherwise. It is deliberately not
  dressed up as a nuanced quality assessment nobody validated.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .model_intelligence_models import (
    BenchmarkResult,
    ModelProfile,
    TaskType,
)
from .model_profiler import ModelProfiler
from .performance_analyzer import PerformanceAnalyzer

logger = logging.getLogger(__name__)

# One short, representative, real prompt per task type — real enough to
# produce a genuine completion (so latency/tps reflect actual generation),
# short enough that a 12-model sweep stays a few minutes, not hours.
_PROMPTS_BY_TASK_TYPE: dict[TaskType, str] = {
    TaskType.CODE_GENERATION: "Write a Python function that returns the factorial of a non-negative integer n.",
    TaskType.CODE_REVIEW: "Review this Python function for bugs, in two sentences: def add(a, b): return a - b",
    TaskType.DEBUG: "This Python code raises IndexError: lst = [1, 2, 3]; print(lst[3]). Explain why in one sentence and give the fix.",
    TaskType.REFACTOR: "Refactor this for readability, showing only the new code: def f(x): return x*x*x if x>0 else -1*x*x*x",
    TaskType.ANALYSIS: "In two sentences, analyze the time complexity of binary search.",
    TaskType.CHAT: "In one sentence, what is the capital of France?",
    TaskType.DOCUMENTATION: "Write a one-sentence docstring for a function that reverses a string.",
    TaskType.OPTIMIZATION: "In one sentence, suggest one way to optimize a Python loop that appends to a list a million times.",
    TaskType.REASONING: "If all cats are animals and some animals are pets, can we conclude all cats are pets? Answer yes or no and explain in one sentence.",
    TaskType.GENERAL: "In one sentence, summarize why the sky is blue.",
}
_DEFAULT_PROMPT = "In one sentence, introduce yourself."

# Applied when a caller doesn't pass one — matches the num_ctx a task
# actually running through this role would use before HOS-065C's per-role
# context work (see CHANGELOG); callers benchmarking a specific candidate
# context should pass num_ctx explicitly.
_DEFAULT_BENCHMARK_NUM_CTX = 8192


def _extract_content(raw: dict[str, Any]) -> str:
    message = raw.get("message") or {}
    return str(message.get("content") or "")


class BenchmarkScheduler:
    """Runs and records real model benchmarks."""

    def __init__(
        self,
        profiler: Optional[ModelProfiler] = None,
        analyzer: Optional[PerformanceAnalyzer] = None,
        *,
        chat: Optional[Callable[..., Any]] = None,
        timeout_s: float = 180.0,
    ) -> None:
        """``chat`` is ``async (*, messages, model, num_ctx) -> dict`` —
        Ollama's raw, non-streaming ``/api/chat`` JSON (``message.content``,
        ``eval_count``, ``eval_duration``, ``prompt_eval_count``, ...).
        Defaults to a real call against the configured Ollama endpoint;
        tests inject a fake to stay hermetic, the same pattern
        ``RealTaskExecutor``/``TaskDecomposer`` use.
        """
        self._profiler = profiler or ModelProfiler()
        self._analyzer = analyzer or PerformanceAnalyzer()
        self._chat = chat
        self._timeout_s = timeout_s

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._scheduled_benchmarks: list[dict[str, Any]] = []
        self._regression_history: list[dict[str, Any]] = []
        # Real results, keyed by (model_id, task_type) — replaces the old
        # get_latest_benchmarks(), which invented a fresh set of numbers on
        # every single call instead of remembering anything.
        self._results: dict[tuple[str, str], BenchmarkResult] = {}

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

    # ── async/sync bridge — same pattern as RealTaskExecutor/TaskDecomposer ──

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._loop is not None and not self._loop.is_closed():
                return self._loop

            ready = threading.Event()

            def runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(
                target=runner, name="hermes-benchmark-scheduler", daemon=True
            )
            self._loop_thread.start()
            ready.wait(timeout=10)
            if self._loop is None:  # pragma: no cover - thread start failure
                raise RuntimeError("could not start the benchmark scheduler event loop")
            return self._loop

    def _run_coro(self, coro: Any, timeout: float) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        with self._loop_lock:
            loop, thread = self._loop, self._loop_thread
            self._loop, self._loop_thread = None, None
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)

    shutdown = close

    # ── real inference ──────────────────────────────────────────────

    async def _default_chat(self, *, messages: list[dict[str, Any]], model: str,
                             num_ctx: int) -> dict[str, Any]:
        """Non-streaming ``/api/chat`` call, built the same way
        RealTaskExecutor._default_chat builds its client — from
        get_settings(), so this talks to whatever endpoint the rest of
        Hermes talks to. Non-streaming (not chat_events) specifically to
        get Ollama's own final-summary counters in one response instead of
        estimating from wall-clock time and character counts.
        """
        import httpx

        from backend.core.config import get_settings

        settings = get_settings()
        async with httpx.AsyncClient(
            base_url=settings.ollama_api_url.rstrip("/"), timeout=self._timeout_s,
        ) as client:
            response = await client.post("/api/chat", json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": num_ctx},
            })
            response.raise_for_status()
            return response.json()

    def _measured_vram_mb(self, model_id: str) -> tuple[int, int]:
        """Real VRAM/RAM split for a currently-loaded model, from Ollama's
        own /api/ps (``size_vram`` vs ``size`` — the difference is what
        spilled to CPU/RAM). Best-effort: returns (0, 0) rather than raising
        if Ollama's process list can't be reached, since a benchmark that
        already got its real chat measurement should not be discarded over
        a second, non-essential call failing.
        """
        try:
            import httpx

            from backend.core.config import get_settings

            settings = get_settings()
            with httpx.Client(
                base_url=settings.ollama_api_url.rstrip("/"), timeout=10.0,
            ) as client:
                response = client.get("/api/ps")
                response.raise_for_status()
                for entry in response.json().get("models", []):
                    if entry.get("name") == model_id or entry.get("model") == model_id:
                        size = int(entry.get("size") or 0)
                        size_vram = int(entry.get("size_vram") or 0)
                        return size_vram // 1_000_000, max(0, size - size_vram) // 1_000_000
        except Exception:
            logger.debug("could not read real VRAM for %s", model_id, exc_info=True)
        return 0, 0

    def run_benchmark(self, model_id: str, task_type: TaskType,
                       num_ctx: int = _DEFAULT_BENCHMARK_NUM_CTX) -> BenchmarkResult:
        """Run one real benchmark for a model on a specific task.

        Raises:
            ValueError: ``model_id`` isn't a known profile.
            RuntimeError: Ollama could not be reached — a benchmark that
                could not run must say so, not report invented numbers.
        """
        profile = self._profiler.get_profile(model_id)
        if not profile:
            raise ValueError(f"Unknown model: {model_id}")

        prompt = _PROMPTS_BY_TASK_TYPE.get(task_type, _DEFAULT_PROMPT)
        messages = [{"role": "user", "content": prompt}]
        chat = self._chat or self._default_chat

        try:
            raw = self._run_coro(
                chat(messages=messages, model=model_id, num_ctx=num_ctx),
                self._timeout_s,
            )
        except Exception as exc:
            raise RuntimeError(
                f"benchmark for {model_id!r} could not reach Ollama: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        content = _extract_content(raw)
        eval_count = int(raw.get("eval_count") or 0)
        eval_duration_ns = int(raw.get("eval_duration") or 0)
        prompt_eval_count = int(raw.get("prompt_eval_count") or 0)
        total_duration_ns = int(raw.get("total_duration") or 0)

        tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0.0
        latency_ms = total_duration_ns / 1e6

        vram_mb, ram_mb = self._measured_vram_mb(model_id)
        # A response is the completion signal available without a real
        # evaluation harness — see the module docstring.
        quality = 1.0 if content.strip() else 0.0

        result = BenchmarkResult(
            benchmark_id=f"bm_{int(time.time())}_{model_id[:8]}",
            model_id=model_id,
            task_type=task_type,
            latency_ms=round(latency_ms, 1),
            tokens_per_second=round(tps, 1),
            vram_usage_mb=vram_mb or profile.vram_required_mb,
            ram_usage_mb=ram_mb,
            quality_score=quality,
            temperature=0.2,
        )

        self._analyzer.add_benchmark(result)
        with self._lock:
            self._results[(model_id, task_type.value)] = result

        # Feeds the same learning signal a real task execution does
        # (ModelProfiler.update_performance, see _make_task_executor) —
        # a deliberately-triggered real call is not fundamentally
        # different from an organic one.
        from .model_intelligence_models import ModelPerformanceRecord

        self._profiler.update_performance(ModelPerformanceRecord(
            model_id=model_id, task_type=task_type,
            duration_ms=round(latency_ms), tokens_used=eval_count + prompt_eval_count,
            success=quality > 0,
        ))
        # task_scores was never populated by anything — every recommend()
        # ranking read profile.task_scores.get(type, 0.5), the neutral
        # default, for every model on every task. A real benchmark is
        # exactly what this field is for.
        profile.task_scores[task_type.value] = quality

        self._check_regression(result, profile)
        return result

    def run_full_benchmark(self, task_types: Optional[list[TaskType]] = None) -> list[BenchmarkResult]:
        """Benchmark all models on all specified task types. Real work now:
        each combination is a real Ollama call, so this is slow by
        construction — callers wanting a quick sweep should pass a small
        task_types list or call run_benchmark() directly per (model, type)."""
        if task_types is None:
            task_types = list(TaskType)

        profiles = self._profiler.list_profiles()
        results = []
        for profile in profiles:
            for task_type in task_types:
                try:
                    result = self.run_benchmark(profile.model_id, task_type)
                    results.append(result)
                except (ValueError, RuntimeError):
                    continue
        return results

    def get_latest_benchmarks(self, model_id: Optional[str] = None,
                               limit: int = 20) -> list[dict[str, Any]]:
        """Real, stored results — previously regenerated a fresh batch of
        random.uniform() numbers on every call regardless of whether
        anything had ever actually run."""
        with self._lock:
            results = list(self._results.values())
        if model_id:
            results = [r for r in results if r.model_id == model_id]
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return [
            {
                "benchmark_id": r.benchmark_id,
                "model_id": r.model_id,
                "task_type": r.task_type.value,
                "latency_ms": r.latency_ms,
                "tokens_per_second": r.tokens_per_second,
                "vram_usage_mb": r.vram_usage_mb,
                "quality_score": r.quality_score,
            }
            for r in results[:limit]
        ]

    def get_regressions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return self._regression_history[-limit:]

    def start(self, interval_h: int = 24) -> None:
        """Start periodic benchmarking."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop_runner, args=(interval_h,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop_runner(self, interval_h: int) -> None:
        while self._running:
            try:
                self.run_full_benchmark()
            except Exception:
                logger.warning("Benchmark run failed", exc_info=True)
            time.sleep(interval_h * 3600)

    def _check_regression(self, result: BenchmarkResult,
                          profile: ModelProfile) -> None:
        expected_q = profile.task_scores.get(result.task_type.value, 0.5)
        if result.quality_score < expected_q * 0.7:
            regression = {
                "model_id": result.model_id,
                "task_type": result.task_type.value,
                "previous_score": expected_q,
                "current_score": result.quality_score,
                "drop_pct": round((1 - result.quality_score / expected_q) * 100, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with self._lock:
                self._regression_history.append(regression)
