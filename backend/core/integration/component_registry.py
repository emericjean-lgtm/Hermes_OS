"""Component Registry for Hermes OS (HOS-056).

Tracks all active system components, their dependencies, capabilities,
produced/consumed events, and health status. Provides a unified view
of the entire Hermes OS system.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ComponentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    DISABLED = "disabled"


class ComponentCategory(str, Enum):
    RUNTIME = "runtime"
    MISSION = "mission"
    AGENT = "agent"
    MEMORY = "memory"
    SKILL = "skill"
    TOOL = "tool"
    POLICY = "policy"
    WORKSPACE = "workspace"
    EXECUTION = "execution"
    INTEGRATION = "integration"
    SYSTEM = "system"
    CORE = "core"


@dataclass
class ComponentInfo:
    """Metadata about a registered system component."""
    id: str
    name: str
    category: ComponentCategory
    version: str = "1.0.0"
    description: str = ""
    status: ComponentStatus = ComponentStatus.UNKNOWN
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    produced_events: list[str] = field(default_factory=list)
    consumed_events: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_health_check: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "produced_events": self.produced_events,
            "consumed_events": self.consumed_events,
            "metadata": self.metadata,
            "registered_at": self.registered_at.isoformat(),
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
        }


class ComponentRegistry:
    """Central registry of all Hermes OS components.

    Thread-safe singleton-like structure that tracks every module.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._components: dict[str, ComponentInfo] = {}

    def register(self, info: ComponentInfo) -> bool:
        with self._lock:
            if info.id in self._components:
                return False
            self._components[info.id] = info
            return True

    def unregister(self, component_id: str) -> bool:
        with self._lock:
            if component_id not in self._components:
                return False
            del self._components[component_id]
            return True

    def get(self, component_id: str) -> ComponentInfo | None:
        with self._lock:
            return self._components.get(component_id)

    def update_status(self, component_id: str, status: ComponentStatus) -> bool:
        with self._lock:
            comp = self._components.get(component_id)
            if comp is None:
                return False
            comp.status = status
            comp.last_health_check = datetime.now(timezone.utc)
            return True

    def list_components(self, category: ComponentCategory | None = None) -> list[ComponentInfo]:
        with self._lock:
            comps = list(self._components.values())
            if category:
                comps = [c for c in comps if c.category == category]
            return sorted(comps, key=lambda c: c.name)

    def get_by_category(self) -> dict[str, list[dict]]:
        with self._lock:
            result: dict[str, list[dict]] = {}
            for comp in self._components.values():
                cat = comp.category.value
                if cat not in result:
                    result[cat] = []
                result[cat].append(comp.to_dict())
            return result

    def get_status_summary(self) -> dict[str, Any]:
        with self._lock:
            all_comps = list(self._components.values())
            return {
                "total": len(all_comps),
                "healthy": sum(1 for c in all_comps if c.status == ComponentStatus.HEALTHY),
                "degraded": sum(1 for c in all_comps if c.status == ComponentStatus.DEGRADED),
                "unhealthy": sum(1 for c in all_comps if c.status == ComponentStatus.UNHEALTHY),
                "unknown": sum(1 for c in all_comps if c.status == ComponentStatus.UNKNOWN),
                "disabled": sum(1 for c in all_comps if c.status == ComponentStatus.DISABLED),
                "categories": len(set(c.category.value for c in all_comps)),
                "total_dependencies": sum(len(c.dependencies) for c in all_comps),
                "total_events_produced": sum(len(c.produced_events) for c in all_comps),
                "total_events_consumed": sum(len(c.consumed_events) for c in all_comps),
            }

    def find_dependents(self, component_id: str) -> list[str]:
        """Find all components that depend on the given component."""
        with self._lock:
            return [cid for cid, comp in self._components.items()
                    if component_id in comp.dependencies]

    def get_registered_ids(self) -> list[str]:
        with self._lock:
            return list(self._components.keys())

    def count(self) -> int:
        with self._lock:
            return len(self._components)
