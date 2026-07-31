"""Adaptive Skill Orchestrator (HOS-022).

Intelligently selects and loads skill descriptors relevant to a mission,
avoiding the overhead of loading dozens of SKILL.md files unnecessarily.

The orchestrator uses a configurable :class:`SkillSelectionStrategy` and
respects token budgets, dependency chains and capability matching.

No concrete agent (Hermes, MCP) is imported here.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from collections.abc import Callable
from typing import Any, Optional


class SkillSelectionStrategy(str, Enum):
    """Strategy for selecting which skills to load.

    * ``MINIMAL`` — load only the skills strictly required by the mission.
    * ``BALANCED`` — load required skills plus closely related ones.
    * ``EXHAUSTIVE`` — load all compatible skills regardless of budget.
    * ``PERFORMANCE`` — optimise for minimal token count while meeting
      requirements.
    """

    MINIMAL = "minimal"
    BALANCED = "balanced"
    EXHAUSTIVE = "exhaustive"
    PERFORMANCE = "performance"


class SkillEvent(str, Enum):
    """Events emitted by the orchestrator."""

    LOADED = "skill.loaded"
    UNLOADED = "skill.unloaded"
    SELECTED = "skill.selected"
    REJECTED = "skill.rejected"


class SkillError(Exception):
    """Raised when a skill operation fails."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillDescriptor:
    """Describes a single skill.

    Attributes:
        id: Unique identifier.
        name: Human-readable name.
        description: Extended description.
        capabilities: Set of RAL capabilities this skill provides.
        tags: Tags for filtering and discovery.
        dependencies: Set of skill ids this skill depends on.
        priority: Priority level (higher = more important).
        estimated_tokens: Rough token cost (e.g. size of the SKILL.md).
        metadata: Free-form payload.
    """

    id: str
    name: str
    description: str = ""
    capabilities: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    dependencies: frozenset[str] = frozenset()
    priority: int = 5
    estimated_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillBundle:
    """A named, versioned collection of skills.

    Attributes:
        id: Bundle identifier.
        name: Human-readable name.
        description: Description.
        skill_ids: Skill ids belonging to this bundle.
        metadata: Free-form payload.
    """

    id: str
    name: str
    description: str = ""
    skill_ids: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSelection:
    """Result of a skill selection operation.

    Attributes:
        selected_skills: Skill ids that were selected.
        rejected_skills: Skill ids that were considered but rejected.
        total_tokens: Sum of estimated_tokens of selected skills.
        rejected_reasons: Mapping of rejected skill id → reason.
        explanation: Human-readable explanation of the selection.
        strategy: The strategy used.
        execution_time_ms: Execution time in milliseconds.
    """

    selected_skills: frozenset[str] = frozenset()
    rejected_skills: frozenset[str] = frozenset()
    total_tokens: int = 0
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    explanation: str = ""
    strategy: SkillSelectionStrategy = SkillSelectionStrategy.MINIMAL
    execution_time_ms: float = 0.0


@dataclass(frozen=True)
class SkillStatistics:
    """Aggregated skill usage statistics.

    Attributes:
        total_skills_registered: Number of registered skills.
        total_skills_loaded: Number of skills currently loaded.
        total_selections: Number of selection operations performed.
        avg_selection_time_ms: Average selection duration.
        load_success_rate: Ratio of successful loads (0.0-1.0).
        metadata: Free-form metadata.
    """

    total_skills_registered: int = 0
    total_skills_loaded: int = 0
    total_selections: int = 0
    avg_selection_time_ms: float = 0.0
    load_success_rate: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repository interface
# ---------------------------------------------------------------------------


class SkillRepository(ABC):
    """Abstract interface for skill storage backends."""

    @abstractmethod
    def register(self, skill: SkillDescriptor) -> None:
        """Register a skill."""

    @abstractmethod
    def unregister(self, skill_id: str) -> None:
        """Remove a skill."""

    @abstractmethod
    def get(self, skill_id: str) -> Optional[SkillDescriptor]:
        """Return a skill by id."""

    @abstractmethod
    def search(self, *, tags: Optional[frozenset[str]] = None, text: Optional[str] = None) -> list[SkillDescriptor]:
        """Search skills by tags or text."""

    @abstractmethod
    def list_all(self) -> list[SkillDescriptor]:
        """Return all registered skills."""

    @abstractmethod
    def register_bundle(self, bundle: SkillBundle) -> None:
        """Register a bundle."""

    @abstractmethod
    def get_bundle(self, bundle_id: str) -> Optional[SkillBundle]:
        """Return a bundle by id."""

    @abstractmethod
    def list_bundles(self) -> list[SkillBundle]:
        """Return all bundles."""


class InMemorySkillRepository(SkillRepository):
    """Thread-safe in-memory implementation of :class:`SkillRepository`."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDescriptor] = {}
        self._bundles: dict[str, SkillBundle] = {}
        self._lock = threading.RLock()

    def register(self, skill: SkillDescriptor) -> None:
        with self._lock:
            self._skills[skill.id] = skill

    def unregister(self, skill_id: str) -> None:
        with self._lock:
            self._skills.pop(skill_id, None)

    def get(self, skill_id: str) -> Optional[SkillDescriptor]:
        with self._lock:
            return self._skills.get(skill_id)

    def search(self, *, tags: Optional[frozenset[str]] = None, text: Optional[str] = None) -> list[SkillDescriptor]:
        with self._lock:
            results = list(self._skills.values())
        if tags is not None and tags:
            results = [s for s in results if tags & s.tags]
        if text is not None:
            t = text.lower()
            results = [s for s in results if t in s.name.lower() or t in s.description.lower()]
        return results

    def list_all(self) -> list[SkillDescriptor]:
        with self._lock:
            return list(self._skills.values())

    def register_bundle(self, bundle: SkillBundle) -> None:
        with self._lock:
            self._bundles[bundle.id] = bundle

    def get_bundle(self, bundle_id: str) -> Optional[SkillBundle]:
        with self._lock:
            return self._bundles.get(bundle_id)

    def list_bundles(self) -> list[SkillBundle]:
        with self._lock:
            return list(self._bundles.values())


# ---------------------------------------------------------------------------
# Adaptive Skill Orchestrator
# ---------------------------------------------------------------------------

Handler = Callable[[SkillEvent, SkillDescriptor | SkillBundle | None], None]


class AdaptiveSkillOrchestrator:
    """Intelligent skill selection and lifecycle manager.

    The orchestrator selects skills based on mission context, strategy,
    dependency resolution and token budget.

    Args:
        repository: Skill storage backend.
        strategy: Default selection strategy.
        max_skills: Maximum number of skills to load at once.
        max_tokens: Maximum total token budget for selected skills.
    """

    def __init__(
        self,
        repository: Optional[SkillRepository] = None,
        strategy: SkillSelectionStrategy = SkillSelectionStrategy.BALANCED,
        *,
        max_skills: int = 10,
        max_tokens: int = 50000,
    ) -> None:
        self._repository = repository or InMemorySkillRepository()
        self._strategy = strategy
        self._max_skills = max_skills
        self._max_tokens = max_tokens
        self._loaded: set[str] = set()
        self._lock = threading.RLock()
        self._handlers: list[Handler] = []
        self._selection_count = 0
        self._selection_time_total = 0.0
        self._load_failures = 0
        self._load_total = 0

    def on_event(self, handler: Handler) -> None:
        with self._lock:
            self._handlers.append(handler)

    @property
    def strategy(self) -> SkillSelectionStrategy:
        return self._strategy

    def set_strategy(self, strategy: SkillSelectionStrategy) -> None:
        with self._lock:
            self._strategy = strategy

    # ------------------------------------------------------------------
    # Analysis & selection
    # ------------------------------------------------------------------

    def analyse_mission(
        self,
        mission_description: str,
        *,
        required_capabilities: Optional[frozenset[str]] = None,
        tags: Optional[frozenset[str]] = None,
    ) -> SkillSelection:
        """Analyse a mission description and select matching skills.

        This method simulates matching the mission text against skill
        descriptors. In future versions this may use NLP or embedding
        similarity.

        Args:
            mission_description: Text describing the mission.
            required_capabilities: Capabilities the mission requires.
            tags: Optional skill tags to search.

        Returns:
            A :class:`SkillSelection` with recommended skills.
        """
        start = time.monotonic()
        with self._lock:
            self._strategy  # ensure we hold the lock
        skills = self._repository.list_all()

        # Filter by tags if provided.
        if tags is not None and tags:
            skills = [s for s in skills if tags & s.tags]

        # Score each skill by how well it matches the mission.
        scored = []
        for skill in skills:
            score = self._score_skill(skill, mission_description, required_capabilities or frozenset())
            scored.append((score, skill))

        scored.sort(key=lambda x: (-x[0], x[1].priority, x[1].estimated_tokens))

        selection = self._apply_strategy(scored, mission_description, required_capabilities or frozenset())
        elapsed = (time.monotonic() - start) * 1000

        with self._lock:
            self._selection_count += 1
            self._selection_time_total += elapsed

        return SkillSelection(
            selected_skills=frozenset(selection["selected"]),
            rejected_skills=frozenset(selection["rejected"]),
            total_tokens=selection["total_tokens"],
            rejected_reasons=selection["rejected_reasons"],
            explanation=self._build_explanation(selection["selected"], selection["rejected"],
                                                  selection["rejected_reasons"]),
            strategy=self._strategy,
            execution_time_ms=elapsed,
        )

    def select_skills(
        self,
        *,
        required_capabilities: Optional[frozenset[str]] = None,
        tags: Optional[frozenset[str]] = None,
        preferred_ids: Optional[frozenset[str]] = None,
    ) -> SkillSelection:
        """Select skills by capabilities, tags or explicit ids.

        Args:
            required_capabilities: Capabilities the mission requires.
            tags: Skill tags to search.
            preferred_ids: Explicit skill ids to prefer.

        Returns:
            A selection result.
        """
        start = time.monotonic()
        skills = self._repository.list_all()

        candidates: list[SkillDescriptor] = []
        seen: set[str] = set()

        # Preferred skills first.
        if preferred_ids is not None:
            for sid in preferred_ids:
                skill = self._repository.get(sid)
                if skill is not None and skill.id not in seen:
                    candidates.append(skill)
                    seen.add(skill.id)

        # Skills matching required capabilities.
        if required_capabilities is not None:
            for skill in skills:
                if skill.id not in seen and required_capabilities & skill.capabilities:
                    candidates.append(skill)
                    seen.add(skill.id)

        # Skills matching tags.
        if tags is not None and tags:
            for skill in skills:
                if skill.id not in seen and tags & skill.tags:
                    candidates.append(skill)
                    seen.add(skill.id)

        # Fill remaining with highest-priority skills.
        remaining = sorted(
            [s for s in skills if s.id not in seen],
            key=lambda s: (-s.priority, s.estimated_tokens),
        )
        candidates.extend(remaining)

        # Score based on relevance.
        scored = [(c.priority * 2.0, c) for c in candidates]
        selection = self._apply_strategy(scored, "", required_capabilities or frozenset())
        elapsed = (time.monotonic() - start) * 1000

        with self._lock:
            self._selection_count += 1
            self._selection_time_total += elapsed

        return SkillSelection(
            selected_skills=frozenset(selection["selected"]),
            rejected_skills=frozenset(selection["rejected"]),
            total_tokens=selection["total_tokens"],
            rejected_reasons=selection["rejected_reasons"],
            explanation=self._build_explanation(selection["selected"], selection["rejected"],
                                                  selection["rejected_reasons"]),
            strategy=self._strategy,
            execution_time_ms=elapsed,
        )

    def load_bundle(self, bundle_id: str) -> int:
        """Load all skills belonging to a bundle.

        Args:
            bundle_id: Bundle identifier.

        Returns:
            Number of skills loaded.

        Raises:
            SkillError: If the bundle does not exist.
        """
        bundle = self._repository.get_bundle(bundle_id)
        if bundle is None:
            raise SkillError(f"Bundle '{bundle_id}' not found.")
        count = 0
        for sid in bundle.skill_ids:
            skill = self._repository.get(sid)
            if skill is not None and sid not in self._loaded:
                with self._lock:
                    self._loaded.add(sid)
                    self._load_total += 1
                self._emit(SkillEvent.LOADED, skill)
                count += 1
        return count

    def unload_bundle(self, bundle_id: str) -> int:
        """Unload all skills belonging to a bundle.

        Args:
            bundle_id: Bundle identifier.

        Returns:
            Number of skills unloaded.
        """
        bundle = self._repository.get_bundle(bundle_id)
        if bundle is None:
            return 0
        count = 0
        for sid in bundle.skill_ids:
            if sid in self._loaded:
                with self._lock:
                    self._loaded.discard(sid)
                skill = self._repository.get(sid)
                self._emit(SkillEvent.UNLOADED, skill)
                count += 1
        return count

    def recommend(
        self,
        mission_description: str,
        *,
        max_recommendations: int = 5,
    ) -> list[SkillDescriptor]:
        """Recommend skills for a mission without loading them.

        Args:
            mission_description: Description of the mission.
            max_recommendations: Maximum number of recommendations.

        Returns:
            A list of recommended skill descriptors.
        """
        all_skills = self._repository.list_all()
        scored = []
        for skill in all_skills:
            text = f"{skill.name} {skill.description}".lower()
            mission_lower = mission_description.lower()
            match_count = sum(1 for word in mission_lower.split() if word in text)
            score = match_count + skill.priority * 0.5
            scored.append((score, skill))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:max_recommendations]]

    def explain_selection(self, selection: SkillSelection) -> str:
        """Return a human-readable explanation.

        Args:
            selection: A selection result.

        Returns:
            Explanation string.
        """
        return selection.explanation

    def get_statistics(self) -> SkillStatistics:
        """Return current aggregated statistics."""
        with self._lock:
            reg = len(self._repository.list_all())
            loaded = len(self._loaded)
            avg_time = self._selection_time_total / self._selection_count if self._selection_count else 0.0
            rate = 1.0 - (self._load_failures / max(self._load_total, 1))
        return SkillStatistics(
            total_skills_registered=reg,
            total_skills_loaded=loaded,
            total_selections=self._selection_count,
            avg_selection_time_ms=avg_time,
            load_success_rate=rate,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_skill(
        self,
        skill: SkillDescriptor,
        mission: str,
        capabilities: frozenset[str],
    ) -> float:
        """Score how well a skill matches a mission."""
        score = 0.0
        # Capability match (highest weight).
        if capabilities:
            overlap = len(capabilities & skill.capabilities)
            score += overlap * 10.0
        # Keyword match.
        mission_lower = mission.lower()
        text = f"{skill.name} {skill.description}".lower()
        for word in mission_lower.split():
            if word in text and len(word) > 2:
                score += 1.0
        # Priority bonus.
        score += skill.priority * 0.5
        return score

    def _apply_strategy(
        self,
        scored: list[tuple[float, SkillDescriptor]],
        mission: str,
        capabilities: frozenset[str],
    ) -> dict:
        """Apply the selection strategy to scored candidates."""
        selected: list[str] = []
        rejected: list[str] = []
        rejected_reasons: dict[str, str] = {}
        total_tokens = 0
        selected_set: set[str] = set()

        for score, skill in scored:
            and_children = set()
            skilled = set()
            to_add, and_children_res = self._resolve_dependencies(
                skill, scored, selected_set, capabilities,
            )
            and_children = and_children_res

            # Check limits.
            will_add = len(to_add)
            will_tokens = sum(
                self._repository.get(sid).estimated_tokens
                for sid in to_add
                if self._repository.get(sid) is not None
            )

            if self._strategy == SkillSelectionStrategy.EXHAUSTIVE:
                # Add everything that matches.
                pass
            elif self._strategy == SkillSelectionStrategy.MINIMAL:
                if not (capabilities & skill.capabilities):
                    if skill.id not in selected_set:
                        rejected.append(skill.id)
                        rejected_reasons[skill.id] = "Not required by mission capabilities."
                    continue
            elif self._strategy == SkillSelectionStrategy.PERFORMANCE:
                if score <= 0 and not (capabilities & skill.capabilities):
                    if skill.id not in selected_set:
                        rejected.append(skill.id)
                        rejected_reasons[skill.id] = "Low relevance score."
                    continue

            # Budget limits.
            if len(selected_set) + will_add > self._max_skills:
                rejected.append(skill.id)
                rejected_reasons[skill.id] = f"Would exceed max skills ({self._max_skills})."
                continue
            if total_tokens + will_tokens > self._max_tokens:
                rejected.append(skill.id)
                rejected_reasons[skill.id] = f"Would exceed token budget ({self._max_tokens})."
                continue

            # Add skill and its dependencies.
            for sid in to_add:
                if sid not in selected_set:
                    selected.append(sid)
                    selected_set.add(sid)
                    skill_obj = self._repository.get(sid)
                    if skill_obj is not None:
                        total_tokens += skill_obj.estimated_tokens

        return {
            "selected": selected,
            "rejected": rejected,
            "rejected_reasons": rejected_reasons,
            "total_tokens": total_tokens,
        }

    def _resolve_dependencies(
        self,
        skill: SkillDescriptor,
        scored: list[tuple[float, SkillDescriptor]],
        selected_set: set[str],
        capabilities: frozenset[str],
    ) -> tuple[list[str], set[str]]:
        """Resolve dependencies for a skill. Returns (all_ids, dependency_set)."""
        to_add: list[str] = []
        visited: set[str] = set()
        stack = [skill.id]
        while stack:
            sid = stack.pop()
            if sid in visited or sid in selected_set:
                continue
            visited.add(sid)
            to_add.insert(0, sid if sid != skill.id else skill.id)
            dep_skill = self._repository.get(sid)
            if dep_skill is not None:
                for dep in dep_skill.dependencies:
                    if dep not in visited and dep not in selected_set:
                        stack.append(dep)
        return to_add, visited

    def _build_explanation(
        self,
        selected: list[str],
        rejected: list[str],
        reasons: dict[str, str],
    ) -> str:
        lines = []
        lines.append(f"Selected {len(selected)} skill(s): {', '.join(sorted(selected))}")
        if rejected:
            lines.append(f"Rejected {len(rejected)} skill(s):")
            for sid in sorted(rejected):
                reason = reasons.get(sid, "No reason provided.")
                lines.append(f"  - {sid}: {reason}")
        return "\n".join(lines)

    def _emit(self, event: SkillEvent, payload: Any) -> None:
        for handler in self._handlers:
            try:
                handler(event, payload)
            except Exception:
                pass
