"""Composition root for Hermes OS (HOS-066B).

This is the piece that was missing. Every subsystem was complete and tested in
isolation, and every one of them exposed an injection seam — ``on_event`` on the
constructor, ``create_*_routes(service)`` on the route module, ``configure(...)``
on the orchestrator — but nothing in production ever called those seams. The
result was 16 endpoints answering ``503 not initialized``, a runtime
orchestrator scoring with null callbacks, and seven subsystems that were islands
with no inbound or outbound edges at all.

:class:`HermesBootstrap` calls them, once, in dependency order:

1. **build** — instantiate every spec in :data:`SERVICE_SPECS`, topologically
   ordered, into a single :class:`DependencyContainer`.
2. **wire** — hand each service the shared event dispatcher (done by the
   factories) and bind each route module to its owning service.
3. **register** — record every service in the
   :class:`ComponentRegistry` and :class:`DependencyGraph` (HOS-056) so the
   integration layer finally describes the running system rather than a
   test fixture.
4. **validate** — reject cycles and dangling dependencies before serving.
5. **health** — expose a uniform ``health``/``ready``/``statistics`` view.

Shutdown runs the reverse of the build order, so nothing is torn down before
its dependents.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.core.bootstrap.dependency_container import DependencyContainer
from backend.core.bootstrap.health import ServiceHealthProbe
from backend.core.bootstrap.service_registry import (
    SERVICE_SPECS,
    SPECS_BY_KEY,
    ServiceSpec,
    resolve_build_order,
)
from backend.core.integration.component_registry import (
    ComponentInfo,
    ComponentRegistry,
    ComponentStatus,
)
from backend.core.integration.dependency_graph import DependencyGraph
from backend.core.integration.health_orchestrator import HealthOrchestrator

logger = logging.getLogger("hermes_os.bootstrap")


@dataclass
class BootstrapReport:
    """What the assembly actually managed to do.

    Deliberately records failures instead of raising on the first one: a single
    unavailable integration (Alexandrie offline, no ``kt_kernel`` installed)
    must not prevent the other twenty subsystems from serving. STEP 10's
    "GO only if startup reaches 100%" is then a property this report can be
    *asked about* — see :meth:`is_complete`.
    """

    built: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    routers_mounted: int = 0
    router_failures: dict[str, str] = field(default_factory=dict)
    event_topics_registered: int = 0
    dependency_cycles: list[list[str]] = field(default_factory=list)
    missing_dependencies: dict[str, list[str]] = field(default_factory=dict)
    isolated_services: list[str] = field(default_factory=list)
    registries: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def total_expected(self) -> int:
        return len(SERVICE_SPECS)

    def is_complete(self) -> bool:
        """True when every subsystem built, wired and validated cleanly."""
        return (
            not self.failed
            and not self.router_failures
            and not self.dependency_cycles
            and not self.missing_dependencies
            and len(self.built) == self.total_expected
        )

    def completion_percent(self) -> float:
        if not self.total_expected:
            return 100.0
        return round(100.0 * len(self.built) / self.total_expected, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete": self.is_complete(),
            "completion_percent": self.completion_percent(),
            "services_expected": self.total_expected,
            "services_built": len(self.built),
            "built": self.built,
            "failed": self.failed,
            "routers_mounted": self.routers_mounted,
            "router_failures": self.router_failures,
            "event_topics_registered": self.event_topics_registered,
            "dependency_cycles": self.dependency_cycles,
            "missing_dependencies": self.missing_dependencies,
            "isolated_services": self.isolated_services,
            "registries": self.registries,
            "duration_ms": round(self.duration_ms, 1),
        }


class HermesBootstrap:
    """Builds, wires, validates and tears down the whole system."""

    def __init__(self, *, specs: tuple[ServiceSpec, ...] = SERVICE_SPECS) -> None:
        self._specs = specs
        self.container = DependencyContainer()
        self.components = ComponentRegistry()
        self.graph = DependencyGraph()
        self.health_orchestrator = HealthOrchestrator(self.components)
        self.probe = ServiceHealthProbe(self.container, self.components)
        self.report = BootstrapReport()
        self._routers: list[Any] = []
        self._started = False

    # ── STEP 1 + 2: build and wire ──────────────────────────────────

    def build(self) -> BootstrapReport:
        """Instantiate and wire every subsystem. Idempotent."""
        if self._started:
            return self.report

        started_at = time.perf_counter()

        self._register_event_topics()

        for spec in resolve_build_order():
            self._build_one(spec)

        self._validate_dependencies()
        self._register_health_checks()
        self._seed_registries()

        self.report.duration_ms = (time.perf_counter() - started_at) * 1000.0
        self._started = True

        if self.report.is_complete():
            logger.info(
                "Hermes OS assembled: %d/%d subsystems, %d routers, %.0fms",
                len(self.report.built),
                self.report.total_expected,
                self.report.routers_mounted,
                self.report.duration_ms,
            )
        else:
            logger.warning(
                "Hermes OS assembled partially: %d/%d subsystems (%.1f%%); failures: %s",
                len(self.report.built),
                self.report.total_expected,
                self.report.completion_percent(),
                ", ".join(self.report.failed) or "none",
            )
        return self.report

    def _register_event_topics(self) -> None:
        """Teach the EventHub every topic the live enums declare (STEP 6)."""
        from backend.core.bootstrap.event_wiring import collect_known_topics
        from backend.core.event_hub import register_event_types

        added = register_event_types(*collect_known_topics())
        self.report.event_topics_registered = len(added)

    def _seed_registries(self) -> None:
        """Fill the registries the Cockpit reads from (R-002 P2).

        Runs after every service exists, because seeding introduces them to each
        other: the agents declared in ``config/agents.yaml`` go to the supervisor,
        the KlaatCode and Oh My Pi tool definitions go to the tool and MCP
        registries, and all of it goes to the assignment coordinator. Best-effort
        by design — a resource that cannot be enumerated must not stop a system
        that is otherwise assembled.
        """
        from backend.core.bootstrap.registry_seeding import seed_registries

        try:
            self.report.registries = seed_registries(self.container).to_dict()
        except Exception as exc:
            self.report.registries = {"error": f"{type(exc).__name__}: {exc}"}
            logger.warning("registry seeding failed", exc_info=True)

    def seed_runtime_registries(self) -> dict[str, Any]:
        """Re-seed the runtime catalogues once the app's lifespan has started them.

        The SDS runtime registry is populated by ``lifespan``, after the whole
        composition root has been built, so at build time it holds nothing and
        the coordinator would keep ``runtimes_available: 0`` for the life of the
        process.
        """
        from backend.core.bootstrap.registry_seeding import seed_registries

        try:
            fresh = seed_registries(self.container, runtimes_only=True)
        except Exception as exc:
            logger.warning("runtime re-seeding failed", exc_info=True)
            return {"error": f"{type(exc).__name__}: {exc}"}

        current = dict(self.report.registries or {})
        current["runtimes"] = fresh.runtimes
        current["orchestrator_runtimes"] = fresh.orchestrator_runtimes
        coordinator = dict(current.get("coordinator") or {})
        coordinator["runtimes"] = fresh.coordinator_runtimes
        current["coordinator"] = coordinator
        self.report.registries = current
        return current

    def _build_one(self, spec: ServiceSpec) -> None:
        # A spec whose dependency failed cannot be built; record it as failed
        # for the same reason rather than raising an opaque MissingServiceError.
        unmet = [d for d in spec.dependencies if not self.container.has(d)]
        if unmet:
            self.report.failed[spec.key] = f"unmet dependencies: {', '.join(unmet)}"
            return

        try:
            instance = spec.factory(self.container)
        except Exception as exc:
            self.report.failed[spec.key] = f"{type(exc).__name__}: {exc}"
            logger.warning("subsystem %s failed to build", spec.key, exc_info=True)
            return

        self.container.register(spec.key, instance)
        self.report.built.append(spec.key)
        self._register_component(spec)

        if spec.route_binder is not None:
            self._bind_routes(spec, instance)

    def _bind_routes(self, spec: ServiceSpec, instance: Any) -> None:
        try:
            routers = spec.route_binder(self.container, instance) or []
        except Exception as exc:
            self.report.router_failures[spec.key] = f"{type(exc).__name__}: {exc}"
            logger.warning("router binding failed for %s", spec.key, exc_info=True)
            return
        for r in routers:
            self._routers.append(r)
            self.report.routers_mounted += 1

    def _register_component(self, spec: ServiceSpec) -> None:
        self.components.register(
            ComponentInfo(
                id=spec.key,
                name=spec.name,
                category=spec.category,
                description=spec.description,
                status=ComponentStatus.HEALTHY,
                dependencies=list(spec.dependencies),
                capabilities=list(spec.capabilities),
                produced_events=list(spec.produced_events),
                consumed_events=list(spec.consumed_events),
                metadata={"adopts_module_singleton": spec.adopts_module_singleton},
            )
        )
        self.graph.add_component(spec.key, list(spec.dependencies))

    # ── STEP 8: dependency validation ───────────────────────────────

    def _validate_dependencies(self) -> None:
        self.report.dependency_cycles = self.graph.has_cycle()

        for spec in self._specs:
            missing = [d for d in spec.dependencies if d not in SPECS_BY_KEY]
            if missing:
                self.report.missing_dependencies[spec.key] = missing

        # A service is isolated when nothing depends on it *and* it depends on
        # nothing — the shape the RC1 audit found for seven whole subsystems.
        # Leaf services that publish events are not isolated: the dispatcher is
        # their outbound edge, so only a service with neither edge nor events
        # counts here.
        for spec in self._specs:
            if spec.dependencies:
                continue
            if self.graph.get_dependents(spec.key):
                continue
            if spec.produced_events or spec.consumed_events:
                continue
            self.report.isolated_services.append(spec.key)

    def dependency_report(self) -> dict[str, Any]:
        """Machine-readable dependency report (STEP 8 deliverable)."""
        fan_in: dict[str, list[str]] = {}
        for spec in self._specs:
            fan_in[spec.key] = sorted(self.graph.get_dependents(spec.key))
        return {
            "summary": self.graph.get_graph_summary(),
            "topological_order": self.graph.get_topological_order(),
            "cycles": self.report.dependency_cycles,
            "missing_dependencies": self.report.missing_dependencies,
            "isolated_services": self.report.isolated_services,
            "services": [
                {
                    "key": spec.key,
                    "name": spec.name,
                    "category": spec.category.value,
                    "built": spec.key in self.report.built,
                    "depends_on": list(spec.dependencies),
                    "depended_on_by": fan_in[spec.key],
                    "publishes": list(spec.produced_events),
                    "subscribes": list(spec.consumed_events),
                    "capabilities": list(spec.capabilities),
                }
                for spec in self._specs
            ],
        }

    # ── STEP 9: health ──────────────────────────────────────────────

    def _register_health_checks(self) -> None:
        for key in self.report.built:
            self.health_orchestrator.register_health_check(
                key, self.probe.status_check(key)
            )

    def health(self) -> dict[str, Any]:
        return self.probe.health()

    def ready(self) -> dict[str, Any]:
        ready = self.report.is_complete()
        return {
            "ready": ready,
            "completion_percent": self.report.completion_percent(),
            "services_built": len(self.report.built),
            "services_expected": self.report.total_expected,
            "blocking": {
                "failed_services": self.report.failed,
                "router_failures": self.report.router_failures,
                "dependency_cycles": self.report.dependency_cycles,
                "missing_dependencies": self.report.missing_dependencies,
            }
            if not ready
            else {},
        }

    def statistics(self) -> dict[str, Any]:
        stats = self.probe.statistics()
        dispatcher = self.container.try_get("event_dispatcher")
        if dispatcher is not None and hasattr(dispatcher, "statistics"):
            stats["events"] = dispatcher.statistics()
        stats["bootstrap"] = self.report.to_dict()
        return stats

    # ── Routers ─────────────────────────────────────────────────────

    @property
    def routers(self) -> list[Any]:
        """Every router produced by a bound subsystem, in build order."""
        return list(self._routers)

    def rebind_routes(self) -> int:
        """Re-assert this bootstrap's ownership of the route modules.

        The ``create_*_routes(service)`` hooks bind by assigning a module-level
        global, so route modules are owned by whichever bootstrap ran last.
        That is harmless in production — one process builds one app — but a test
        interpreter builds many, and the last one built would otherwise answer
        HTTP calls with a *previous* app's services.

        Called from the lifespan so the app that is actually running owns the
        bindings. Idempotent: the binders only assign and return the router.
        """
        rebound = 0
        for spec in self._specs:
            if spec.route_binder is None or spec.key not in self.container:
                continue
            try:
                spec.route_binder(self.container, self.container.get(spec.key))
                rebound += 1
            except Exception:
                logger.warning("rebinding routes for %s failed", spec.key, exc_info=True)
        return rebound

    # ── Shutdown ────────────────────────────────────────────────────

    def shutdown(self) -> dict[str, Any]:
        """Tear down in reverse build order. Never raises.

        Each step is attempted independently: a subsystem that fails to stop
        must not prevent the next one from flushing its state.
        """
        stopped: list[str] = []
        errors: dict[str, str] = {}

        # Method names, in the order we prefer them, that a subsystem may use to
        # release resources. Probing rather than requiring a common interface
        # keeps this from forcing a rewrite of 24 subsystems.
        candidates = ("shutdown", "stop", "close", "flush", "save", "persist")

        def teardown(key: str, svc: Any) -> None:
            for name in candidates:
                fn = getattr(svc, name, None)
                if not callable(fn):
                    continue
                try:
                    fn()
                    stopped.append(f"{key}.{name}()")
                except Exception as exc:
                    errors[key] = f"{name}(): {type(exc).__name__}: {exc}"
                    logger.warning("shutdown of %s via %s failed", key, name, exc_info=True)
                # One teardown call per service: calling stop() *and* close()
                # would double-release for the several subsystems that alias them.
                return

        self.container.for_each_reversed(teardown)

        self._started = False
        logger.info("Hermes OS shutdown: %d subsystems released", len(stopped))
        return {"stopped": stopped, "errors": errors}


# ── Module-level accessor ───────────────────────────────────────────

_bootstrap: Optional[HermesBootstrap] = None


def get_bootstrap() -> HermesBootstrap:
    """The process-wide bootstrap, created on first use."""
    global _bootstrap
    if _bootstrap is None:
        _bootstrap = HermesBootstrap()
    return _bootstrap


def reset_bootstrap() -> None:
    """Drop the process-wide bootstrap.

    For tests, and for ``create_app()`` being called more than once in a single
    interpreter (which the test suite does constantly).
    """
    global _bootstrap
    if _bootstrap is not None:
        _bootstrap.container.clear()
    _bootstrap = None
