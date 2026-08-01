"""Discovers OpenRouter's current free-model pool and keeps ModelProfiler
stocked with it, plus a cached, reserve-aware quota gate (HOS-066C).

Two responsibilities, both read-only/best-effort by design:

* **Catalogue.** ``refresh()`` calls ``GET /models`` and registers every
  model priced at zero (both ``pricing.prompt`` and ``pricing.completion``
  are the string ``"0"`` — the ``:free`` id suffix is a naming convention,
  not verified pricing, so it is not relied on alone) as a ``ModelProfile``
  with ``available_backends=[RuntimeBackend.OPENROUTER]``. This is what lets
  ``AdaptiveRouter`` rank cloud candidates the same way it ranks local ones,
  instead of a second, hand-maintained model list drifting out of date.
* **Quota gate.** ``has_budget()`` answers "is there real, current headroom
  in the shared daily quota right now" via ``GET /key`` — checked *before* a
  cloud call is attempted, not only reactively on a 429. Unreachable/unknown
  is treated as *no* budget: the safe, local-preferring failure mode.

Uses its own small synchronous ``httpx.Client`` for these two lightweight
GETs rather than bridging to :class:`OpenRouterClient`'s async chat
methods — discovery/quota checks are infrequent, cheap requests, not
completions, so they do not need the dedicated event-loop-thread pattern
``RealTaskExecutor``/``BenchmarkScheduler`` use for actual inference.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from .model_intelligence_models import (
    ModelArchitecture,
    ModelProfile,
    Quantization,
    RuntimeBackend,
)
from .model_profiler import ModelProfiler

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# The free pool changes rarely; refreshing every request would be a network
# round trip on every single AdaptiveRouter.recommend() call for no benefit.
_DEFAULT_CATALOG_TTL_S = 6 * 3600.0
# Quota changes with every completion (this app's own or anyone else's using
# the same key); cached briefly so recommend()'s three closures
# (_model_for/_num_ctx_for/_runtime_for, see service_registry.py) don't each
# trigger their own /key round trip for one task.
_DEFAULT_QUOTA_TTL_S = 60.0


def _is_free_pricing(pricing: dict[str, Any]) -> bool:
    return pricing.get("prompt") == "0" and pricing.get("completion") == "0"


def _profile_from_entry(entry: dict[str, Any]) -> ModelProfile:
    model_id = str(entry["id"])
    context_length = int(entry.get("context_length") or 8192)
    output_modalities = (entry.get("architecture") or {}).get("output_modalities") or ["text"]
    return ModelProfile(
        model_id=model_id,
        name=str(entry.get("name") or model_id),
        architecture=ModelArchitecture.OTHER,
        # Runs on OpenRouter's infrastructure, not this machine — 0 is the
        # real local VRAM cost, not a placeholder.
        vram_required_mb=0,
        context_window=context_length,
        available_backends=[RuntimeBackend.OPENROUTER],
        recommended_quantization=Quantization.NONE,
        tags=["cloud", "free"],
        chat_capable="text" in output_modalities,
    )


class CloudModelCatalog:
    """Keeps a ModelProfiler stocked with OpenRouter's real free-model pool
    and answers "is there quota left" for AdaptiveRouter's cloud gate."""

    def __init__(
        self,
        api_key: str,
        profiler: ModelProfiler,
        *,
        base_url: str = DEFAULT_BASE_URL,
        reserve_daily_requests: int = 5,
        catalog_ttl_s: float = _DEFAULT_CATALOG_TTL_S,
        quota_ttl_s: float = _DEFAULT_QUOTA_TTL_S,
        timeout: float = 15.0,
        transport: Any = None,
    ) -> None:
        """``reserve_daily_requests``: never let the automatic escalation
        path spend the last few requests of the day — a safety margin so a
        burst of low-value tasks can't silently exhaust the quota right
        before something that actually needed cloud shows up. Set to 0 to
        use the full quota. ``transport`` is a test seam
        (``httpx.MockTransport``) — never set in production.
        """
        if not api_key:
            raise ValueError("CloudModelCatalog requires a non-empty api_key")
        self._api_key = api_key
        self._profiler = profiler
        self._base_url = base_url.rstrip("/")
        self._reserve = max(0, reserve_daily_requests)
        self._catalog_ttl_s = catalog_ttl_s
        self._quota_ttl_s = quota_ttl_s
        self._timeout = timeout
        self._transport = transport

        self._lock = threading.Lock()
        self._registered_ids: set[str] = set()
        self._catalog_fetched_at: float = 0.0
        self._quota_checked_at: float = 0.0
        self._quota_remaining: Optional[int] = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def refresh(self, *, force: bool = False) -> int:
        """Fetch the current free-model pool and register any new entries.

        Best-effort: a fetch failure logs and leaves whatever was already
        registered in place — catalogue staleness degrades gracefully, it
        does not take recommend() down. Returns the total registered count.
        """
        with self._lock:
            still_fresh = (time.time() - self._catalog_fetched_at) < self._catalog_ttl_s
            if not force and still_fresh and self._registered_ids:
                return len(self._registered_ids)

        try:
            import httpx

            with httpx.Client(
                base_url=self._base_url, timeout=self._timeout, headers=self._headers(),
                transport=self._transport,
            ) as client:
                response = client.get("/models")
                response.raise_for_status()
                entries = response.json().get("data") or []
        except Exception:
            logger.warning("OpenRouter catalogue refresh failed", exc_info=True)
            with self._lock:
                return len(self._registered_ids)

        with self._lock:
            self._catalog_fetched_at = time.time()
            for entry in entries:
                pricing = entry.get("pricing") or {}
                if not _is_free_pricing(pricing):
                    continue
                model_id = entry.get("id")
                if not model_id:
                    continue
                self._profiler.register_model(_profile_from_entry(entry))
                self._registered_ids.add(str(model_id))
            return len(self._registered_ids)

    def has_budget(self) -> bool:
        """Real, current headroom in the shared free-tier quota, cached
        briefly. Unreachable/unparseable is treated as *no* budget — the
        safe, local-preferring failure mode, never an assumption that quota
        is fine."""
        with self._lock:
            fresh = (time.time() - self._quota_checked_at) < self._quota_ttl_s
            if fresh and self._quota_remaining is not None:
                return self._quota_remaining > self._reserve

        remaining = self._fetch_quota_remaining()
        with self._lock:
            self._quota_checked_at = time.time()
            self._quota_remaining = remaining
        return remaining is not None and remaining > self._reserve

    def _fetch_quota_remaining(self) -> Optional[int]:
        try:
            import httpx

            with httpx.Client(
                base_url=self._base_url, timeout=self._timeout, headers=self._headers(),
                transport=self._transport,
            ) as client:
                response = client.get("/key")
                response.raise_for_status()
                data = response.json().get("data") or {}
                remaining = data.get("limit_remaining")
                return int(remaining) if remaining is not None else None
        except Exception:
            logger.warning("OpenRouter quota check failed", exc_info=True)
            return None

    def registered_model_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._registered_ids)

    def status(self) -> dict[str, Any]:
        """Read-only snapshot for GET /models/cloud/status."""
        with self._lock:
            return {
                "catalog_size": len(self._registered_ids),
                "catalog_age_s": (
                    round(time.time() - self._catalog_fetched_at, 1)
                    if self._catalog_fetched_at else None
                ),
                "quota_remaining": self._quota_remaining,
                "quota_checked_age_s": (
                    round(time.time() - self._quota_checked_at, 1)
                    if self._quota_checked_at else None
                ),
                "reserve_daily_requests": self._reserve,
            }
