"""Dependency Graph for Hermes OS (HOS-056).

Tracks dependencies between components and allows resolution of
dependency order, cycle detection, and dependency impact analysis.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class DependencyGraph:
    """Directed dependency graph for Hermes OS components."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dependencies: dict[str, set[str]] = defaultdict(set)  # component -> deps
        self._dependents: dict[str, set[str]] = defaultdict(set)    # dep -> components
        self._metadata: dict[str, dict] = {}

    def add_component(self, component_id: str, dependencies: list[str]) -> None:
        with self._lock:
            self._dependencies[component_id] = set(dependencies)
            for dep in dependencies:
                self._dependents[dep].add(component_id)
                if dep not in self._dependencies:
                    self._dependencies[dep] = set()

    def remove_component(self, component_id: str) -> None:
        with self._lock:
            if component_id in self._dependencies:
                deps = self._dependencies.pop(component_id, set())
                for dep in deps:
                    if component_id in self._dependents.get(dep, set()):
                        self._dependents[dep].discard(component_id)
            self._dependents.pop(component_id, None)

    def get_dependencies(self, component_id: str) -> list[str]:
        with self._lock:
            return list(self._dependencies.get(component_id, set()))

    def get_dependents(self, component_id: str) -> list[str]:
        with self._lock:
            return list(self._dependents.get(component_id, set()))

    def has_cycle(self) -> list[list[str]]:
        """Detect cycles in the dependency graph."""
        with self._lock:
            visited: set[str] = set()
            rec_stack: set[str] = set()
            cycles: list[list[str]] = []
            path: list[str] = []

            def dfs(node: str) -> None:
                visited.add(node)
                rec_stack.add(node)
                path.append(node)
                for dep in self._dependencies.get(node, set()):
                    if dep not in visited:
                        dfs(dep)
                    elif dep in rec_stack:
                        cycle_start = path.index(dep)
                        cycles.append(path[cycle_start:] + [dep])
                path.pop()
                rec_stack.discard(node)

            for node in list(self._dependencies.keys()):
                if node not in visited:
                    dfs(node)
            return cycles

    def get_topological_order(self) -> list[str]:
        """Return components in dependency order (deps first)."""
        with self._lock:
            visited: set[str] = set()
            order: list[str] = []

            def dfs(node: str) -> None:
                visited.add(node)
                for dep in self._dependencies.get(node, set()):
                    if dep not in visited:
                        dfs(dep)
                order.append(node)

            for node in list(self._dependencies.keys()):
                if node not in visited:
                    dfs(node)
            return order

    def get_impact_analysis(self, component_id: str) -> dict[str, Any]:
        """Analyze impact if component_id is modified/removed."""
        dependents = self.get_dependents(component_id)
        all_affected = set(dependents)

        # BFS to find all transitive dependents
        queue = list(dependents)
        while queue:
            current = queue.pop(0)
            for dep in self.get_dependents(current):
                if dep not in all_affected:
                    all_affected.add(dep)
                    queue.append(dep)

        return {
            "component_id": component_id,
            "depends_on": self.get_dependencies(component_id),
            "direct_dependents": dependents,
            "all_affected": list(all_affected),
            "impact_count": len(all_affected),
            "is_critical": len(all_affected) > 5,
        }

    def get_graph_summary(self) -> dict[str, Any]:
        with self._lock:
            comps = list(self._dependencies.keys())
            cycles = self.has_cycle()
            return {
                "total_components": len(comps),
                "total_edges": sum(len(deps) for deps in self._dependencies.values()),
                "components": sorted(comps),
                "topological_order": self.get_topological_order(),
                "cycle_count": len(cycles),
                "has_cycles": len(cycles) > 0,
                "cycles": cycles if cycles else [],
            }
