"""Unified event dispatch for Hermes OS (HOS-066B).

Every subsystem was built with the same seam: an optional ``on_event`` callback
invoked as ``on_event(event_type, payload)`` or
``on_event(event_type, payload, severity=...)``. Nothing ever passed one, so
each subsystem was an island that emitted nowhere.

:class:`EventDispatcher` is the single callable handed to all of them. It
forwards to the :class:`~backend.events.system_event_bus.SystemEventBus`
(the durable, queryable bus) and to the legacy
:class:`~backend.core.event_hub.EventHub` (which fans out to WebSocket
clients), so one publish reaches both history and the Cockpit.

It never raises: a dashboard notification must never be able to fail the real
work that produced it. That contract already existed in ``EventHub.publish``;
it is repeated here because the dispatcher sits in front of it.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("hermes_os.events")


class EventDispatcher:
    """Fan one subsystem event out to the system bus and the WebSocket hub."""

    def __init__(
        self,
        system_bus: Any = None,
        event_hub: Any = None,
        *,
        source: str = "hermes_os",
    ) -> None:
        self._system_bus = system_bus
        self._event_hub = event_hub
        self._source = source
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._failures = 0

    # ── The seam every subsystem receives ───────────────────────────

    def __call__(
        self,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        severity: str = "info",
        **extra: Any,
    ) -> None:
        """Publish one event. Accepts both call shapes used in the codebase."""
        body = dict(payload or {})
        if extra:
            body.setdefault("metadata", {}).update(extra)

        with self._lock:
            self._counts[event_type] = self._counts.get(event_type, 0) + 1

        if self._system_bus is not None:
            try:
                self._system_bus.publish(
                    event_type,
                    self._source,
                    payload=body,
                    severity=severity,
                )
            except Exception:
                self._note_failure("system_bus", event_type)

        if self._event_hub is not None:
            try:
                self._event_hub.publish(event_type, body)
            except Exception:
                self._note_failure("event_hub", event_type)

    def _note_failure(self, sink: str, event_type: str) -> None:
        with self._lock:
            self._failures += 1
        logger.warning("event %r could not be delivered to %s", event_type, sink, exc_info=True)

    # ── Scoping ─────────────────────────────────────────────────────

    def scoped(self, source: str) -> "EventDispatcher":
        """A dispatcher that tags its events with a specific subsystem name.

        Shares the sinks and the counters with its parent — this is a relabel,
        not a second dispatcher.
        """
        child = EventDispatcher.__new__(EventDispatcher)
        child._system_bus = self._system_bus
        child._event_hub = self._event_hub
        child._source = source
        child._lock = self._lock
        child._counts = self._counts
        child._failures = self._failures
        return child

    # ── Introspection ───────────────────────────────────────────────

    def statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_published": sum(self._counts.values()),
                "distinct_types": len(self._counts),
                "delivery_failures": self._failures,
                "by_type": dict(sorted(self._counts.items(), key=lambda kv: -kv[1])[:25]),
                "sinks": {
                    "system_bus": self._system_bus is not None,
                    "event_hub": self._event_hub is not None,
                },
            }


def collect_known_topics() -> set[str]:
    """Every event type the system can legitimately emit.

    Assembled from the declared catalogues rather than hand-listed, so the
    ``EventHub`` allow-list cannot drift from its producers again — that drift
    is what silently dropped 26 of 28 RAL topics before HOS-066B.
    """
    topics: set[str] = set()

    try:
        from backend.ral.event_bus import Topic

        topics.update(t.value for t in Topic)
    except Exception:  # pragma: no cover - optional at import time
        logger.debug("RAL Topic enum unavailable", exc_info=True)

    try:
        from backend.runtime.events.event_types import ALL_RUNTIME_EVENT_TYPES

        topics.update(ALL_RUNTIME_EVENT_TYPES)
    except Exception:  # pragma: no cover
        logger.debug("runtime event types unavailable", exc_info=True)

    # Name -> dotted-topic mappings. The topics are the *values*: updating from
    # a dict directly would register the short keys ("threat_detected") instead
    # of the topics ("security.threat.detected").
    #
    # All of them, not just SECURITY_EVENTS. Emitters reference these as
    # `AUTONOMOUS_EVENTS["goal_received"]`, which no static scan of string
    # literals can see — the RC2 audit found 8 topics being dropped for exactly
    # that reason after HOS-066B claimed the drift was fixed.
    catalogues = (
        ("backend.security.security_models", "SECURITY_EVENTS"),
        ("backend.autonomous.autonomous_models", "AUTONOMOUS_EVENTS"),
        ("backend.evolution.evolution_models", "EVOLUTION_EVENTS"),
        ("backend.agents.specialized.code_intelligence.capabilities", "CI_EVENTS"),
        ("backend.agents.specialized.klaatcode.klaatcode_agent", "KLATCODE_EVENTS"),
        ("backend.agents.specialized.ohmypi.ohmypi_agent", "OHMYPI_EVENTS"),
        # HOS-181. Ces huit-la publiaient sans etre declares : 35 topics
        # partaient a la poubelle, dont la totalite de `filesystem.*` et de
        # `execution.*`. Le Cockpit ne pouvait donc voir ni une ecriture sur
        # disque, ni une mission demarrer. Le garde est
        # `backend/tests/test_topics_publies_sont_autorises.py`.
        ("backend.tools.file_tools", "FILESYSTEM_EVENTS"),
        ("backend.tools.verification", "VERIFICATION_EVENTS"),
        ("backend.execution.mission_executor", "EXECUTION_EVENTS"),
        ("backend.projects.project_manager", "PROJECT_EVENTS"),
        ("backend.integrations.alexandrie.hermes_alexandrie_adapter", "ALEXANDRIE_EVENTS"),
        ("backend.runtime.ktransformers.integrations.resources", "KT_EVENTS"),
        ("backend.security.approvals", "APPROVAL_EVENTS"),
        # HOS-227 : la decision du pare-feu de donnees.
        ("backend.security.pare_feu", "PARE_FEU_EVENTS"),
        # HOS-228 : le courtier de quotas.
        ("backend.ral.courtier", "COURTIER_EVENTS"),
        # HOS-230 : la boucle contrat/execution/verification/reparation.
        ("backend.mission.boucle", "BOUCLE_EVENTS"),
        ("backend.agents.kronos", "KRONOS_EVENTS"),
        ("backend.api.routes.chat", "CHAT_EVENTS"),
    )
    for module_path, attr in catalogues:
        try:
            module = __import__(module_path, fromlist=[attr])
            mapping = getattr(module, attr, None)
            if isinstance(mapping, dict):
                topics.update(v for v in mapping.values() if isinstance(v, str) and "." in v)
        except Exception:  # pragma: no cover - optional subsystems
            logger.debug("%s.%s unavailable", module_path, attr, exc_info=True)

    # Note: SystemEventType is deliberately not consulted. Its members are
    # event *categories* ("runtime", "agent", "memory", ...), not topics, and
    # feeding them to the allow-list would let bare category names through.
    return topics
