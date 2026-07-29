"""Dependency resolver for skills (HOS-048)."""

from __future__ import annotations

import threading
from collections import deque

from .skill_models import DependencyGraph
from .skill_registry import SkillRegistry


class SkillDependencyResolver:
    """Resolves skill dependencies: topological sort, conflict detection, circular dep detection."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()

    def resolve(self, skill_ids: list[str]) -> DependencyGraph:
        """Resolve the full dependency tree for a set of skills."""
        with self._lock:
            graph = DependencyGraph()
            all_ids = self._collect_all(skill_ids)
            graph.skill_ids = all_ids

            # Build adjacency: skill → its deps
            for sid in all_ids:
                skill = self._registry.get(sid)
                if skill:
                    graph.adjacency[sid] = set(skill.dependencies) & all_ids

            # Detect circular dependencies (Kahn's algorithm)
            graph.circular_deps = self._detect_cycles(list(all_ids), graph.adjacency)

            # Topological sort
            graph.resolved_order = self._topological_sort(list(all_ids), graph.adjacency)

            # Detect conflicts (version incompatibilities)
            graph.conflicts = self._detect_conflicts(list(all_ids))

            return graph

    def _collect_all(self, skill_ids: list[str]) -> set[str]:
        """Recursively collect all dependencies."""
        visited: set[str] = set()
        queue = deque(skill_ids)

        while queue:
            sid = queue.popleft()
            if sid in visited:
                continue
            visited.add(sid)
            skill = self._registry.get(sid)
            if skill:
                for dep_id in skill.dependencies:
                    if dep_id not in visited:
                        queue.append(dep_id)

        return visited

    def _topological_sort(self, skill_ids: list[str], adjacency: dict[str, set[str]]) -> list[str]:
        """Kahn's algorithm for topological sort."""
        in_degree: dict[str, int] = {sid: 0 for sid in skill_ids}
        for sid, deps in adjacency.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        queue = deque(sid for sid in skill_ids if in_degree.get(sid, 0) == 0)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for sid, deps in adjacency.items():
                if node in deps and sid in in_degree:
                    in_degree[sid] -= 1
                    if in_degree[sid] == 0:
                        queue.append(sid)

        return result

    def _detect_cycles(self, skill_ids: list[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
        """Find circular dependencies using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {sid: WHITE for sid in skill_ids}
        parent: dict[str, Optional[str]] = {sid: None for sid in skill_ids}
        cycles: list[list[str]] = []

        def dfs(u: str) -> None:
            color[u] = GRAY
            for v in adjacency.get(u, set()):
                if v not in color:
                    continue
                if color[v] == GRAY:
                    # Found a cycle — reconstruct it
                    cycle: list[str] = [v, u]
                    p = parent.get(u)
                    while p and p != v:
                        cycle.append(p)
                        p = parent.get(p)
                    cycles.append(cycle)
                elif color[v] == WHITE:
                    parent[v] = u
                    dfs(v)
            color[u] = BLACK

        for sid in skill_ids:
            if color.get(sid) == WHITE:
                dfs(sid)

        return cycles

    def _detect_conflicts(self, skill_ids: list[str]) -> list[str]:
        """Detect version or dependency conflicts."""
        conflicts: list[str] = []
        names: dict[str, list[str]] = {}

        for sid in skill_ids:
            skill = self._registry.get(sid)
            if skill:
                names.setdefault(skill.name, []).append(sid)

        for name, ids in names.items():
            if len(ids) > 1:
                conflicts.append(f"Multiple versions of '{name}': {ids}")

        return conflicts
