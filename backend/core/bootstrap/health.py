"""Uniform health/ready/statistics view over every subsystem (HOS-066B).

STEP 9 asks that every subsystem expose ``health()``, ``ready()`` and
``statistics()``. They do not, and adding three methods to 24 classes would be
the "rewrite existing subsystems" the brief forbids — so the uniformity is
provided here instead, by adapting what each subsystem already offers.

In practice they expose one of a small set of conventional accessors
(``get_status``, ``get_stats``, ``stats``, ``statistics``, ``get_statistics``),
which is enough to answer all three questions:

* **statistics** — whichever accessor the subsystem has, verbatim.
* **health** — a subsystem that answers its own accessor without raising is
  healthy; one that raises is unhealthy; one with no accessor at all is
  reported ``unknown`` rather than silently assumed fine.
* **ready** — built, registered, and health not unhealthy.

Probing is deliberately read-only and defensive: a health endpoint that can be
made to fail by the thing it monitors is worse than no health endpoint.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from typing import Any, Callable, Optional

from backend.core.integration.component_registry import ComponentStatus

logger = logging.getLogger("hermes_os.health")

#: Accessors tried in order. The first callable one wins.
_STATS_ACCESSORS: tuple[str, ...] = (
    "statistics",
    "get_statistics",
    "get_stats",
    "stats",
    "get_status",
    "status",
    "get_summary",
)


#: Seconds a probe result stays usable. Health is a sampled quantity, and some
#: accessors reach the network: the KlaatCode and Oh My Pi status calls probe
#: their external service, so with those down /api/v1/system/health took ~2s and
#: serialised every concurrent request (measured 1 req/s under 16 threads).
#: Caching is what AlexandrieClient already does for the same reason.
DEFAULT_TTL_SECONDS = 5.0


class ServiceHealthProbe:
    """Adapts each subsystem's own accessors into one health surface."""

    def __init__(self, container: Any, components: Any = None,
                 *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._container = container
        self._components = components
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ── Per-service ─────────────────────────────────────────────────

    @staticmethod
    def _takes_no_required_args(fn: Callable[..., Any]) -> bool:
        """True when ``fn`` can be called with no arguments.

        Necessary because the accessor names are not a contract: several
        subsystems have a same-named method that is *parameterised*
        (``LearningEngine.get_stats(runtime_id)``). Calling it blind raised
        TypeError and the probe scored a perfectly healthy subsystem as
        unhealthy. A health check must never invent arguments.
        """
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):  # pragma: no cover - C-level callables
            return False
        for param in sig.parameters.values():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if param.default is param.empty:
                return False
        return True

    @classmethod
    def _find_accessor(cls, service: Any) -> Optional[tuple[str, Callable[[], Any]]]:
        for name in _STATS_ACCESSORS:
            fn = getattr(service, name, None)
            if callable(fn) and cls._takes_no_required_args(fn):
                return name, fn
            # A property that already evaluated to a dict is just as usable.
            if isinstance(fn, dict):
                return name, (lambda value=fn: value)
        return None

    def probe(self, key: str, *, force: bool = False) -> dict[str, Any]:
        """Health of one subsystem: ``{status, accessor, detail?}``.

        Cached for :data:`DEFAULT_TTL_SECONDS`. Pass ``force=True`` to bypass —
        used when a caller needs a fresh reading rather than a recent one.
        """
        if not force:
            with self._lock:
                cached = self._cache.get(key)
            if cached is not None and (time.monotonic() - cached[0]) < self._ttl:
                return cached[1]

        result = self._probe_uncached(key)
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
        return result

    def _probe_uncached(self, key: str) -> dict[str, Any]:
        service = self._container.try_get(key)
        if service is None:
            return {"status": ComponentStatus.DISABLED.value, "detail": "not registered"}

        found = self._find_accessor(service)
        if found is None:
            return {
                "status": ComponentStatus.UNKNOWN.value,
                "detail": "no statistics accessor exposed",
            }

        name, fn = found
        try:
            payload = fn()
        except Exception as exc:
            return {
                "status": ComponentStatus.UNHEALTHY.value,
                "accessor": name,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        return {
            "status": ComponentStatus.HEALTHY.value,
            "accessor": name,
            "payload": payload if isinstance(payload, dict) else {"value": payload},
        }

    def status_check(self, key: str) -> Callable[[], ComponentStatus]:
        """A zero-arg check for :class:`HealthOrchestrator.register_health_check`."""

        def check() -> ComponentStatus:
            raw = self.probe(key).get("status", ComponentStatus.UNKNOWN.value)
            try:
                return ComponentStatus(raw)
            except ValueError:  # pragma: no cover - statuses come from the enum
                return ComponentStatus.UNKNOWN

        return check

    # ── Aggregate ───────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        per_service = {key: self.probe(key) for key in self._container.keys()}
        counts: dict[str, int] = {}
        for entry in per_service.values():
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1

        unhealthy = [k for k, v in per_service.items()
                     if v["status"] == ComponentStatus.UNHEALTHY.value]
        silent = [k for k, v in per_service.items()
                  if v["status"] == ComponentStatus.UNKNOWN.value]

        # "unknown" means the subsystem exposes no zero-argument telemetry
        # accessor — an absence of reporting, not a fault. It is surfaced as
        # `silent` so it stays visible without degrading the whole system.
        overall = (
            ComponentStatus.UNHEALTHY.value if unhealthy
            else ComponentStatus.HEALTHY.value
        )

        return {
            "status": overall,
            "services": len(per_service),
            "by_status": counts,
            "unhealthy": unhealthy,
            "silent": silent,
            "detail": {
                k: {"status": v["status"], **({"detail": v["detail"]} if "detail" in v else {})}
                for k, v in per_service.items()
            },
        }

    def ready(self) -> dict[str, Any]:
        health = self.health()
        return {
            "ready": health["status"] != ComponentStatus.UNHEALTHY.value,
            "status": health["status"],
            "services": health["services"],
            "unhealthy": health["unhealthy"],
        }

    def statistics(self) -> dict[str, Any]:
        out: dict[str, Any] = {"services": {}}
        for key in self._container.keys():
            entry = self.probe(key)
            if "payload" in entry:
                out["services"][key] = entry["payload"]
        out["service_count"] = len(self._container.keys())
        out["reporting_count"] = len(out["services"])
        return out
