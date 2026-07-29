"""Priority Manager for the Adaptive Runtime Orchestrator (HOS-038).

Adapts orchestration strategy based on task priority.
"""

from __future__ import annotations

from backend.runtime.orchestrator.decision_models import PriorityLevel


class PriorityManager:
    """Adjusts orchestration weights and thresholds by priority level."""

    # Weight profiles: (intelligence, health, resources, penalties)
    _profiles: dict[PriorityLevel, dict[str, float]] = {
        PriorityLevel.CRITICAL: {
            "intelligence": 0.15,    # Trust learned scores less — need immediate success
            "health": 0.35,          # Must be healthy
            "resources": 0.20,       # Resource available is secondary
            "reliability_boost": 0.30,  # Extra weight on proven reliability
            "min_confidence": 0.85,  # High confidence threshold
            "allow_recovering": False, # No recovering runtimes
            "max_resource_load": 0.70, # Lower load tolerance
        },
        PriorityLevel.HIGH: {
            "intelligence": 0.30,
            "health": 0.30,
            "resources": 0.25,
            "reliability_boost": 0.15,
            "min_confidence": 0.70,
            "allow_recovering": False,
            "max_resource_load": 0.85,
        },
        PriorityLevel.NORMAL: {
            "intelligence": 0.40,
            "health": 0.25,
            "resources": 0.25,
            "reliability_boost": 0.10,
            "min_confidence": 0.50,
            "allow_recovering": True,
            "max_resource_load": 0.90,
        },
        PriorityLevel.BACKGROUND: {
            "intelligence": 0.25,
            "health": 0.15,
            "resources": 0.50,        # Prioritize resource efficiency
            "reliability_boost": 0.10,
            "min_confidence": 0.30,
            "allow_recovering": True,
            "max_resource_load": 0.95,
        },
    }

    def get_profile(self, priority: PriorityLevel) -> dict[str, float]:
        """Return the weight profile for a priority level."""
        return dict(self._profiles.get(priority, self._profiles[PriorityLevel.NORMAL]))

    def get_min_confidence(self, priority: PriorityLevel) -> float:
        return self.get_profile(priority)["min_confidence"]

    def get_weights(self, priority: PriorityLevel) -> dict[str, float]:
        p = self.get_profile(priority)
        return {
            "intelligence": p["intelligence"],
            "health": p["health"],
            "resources": p["resources"],
            "reliability_boost": p["reliability_boost"],
        }
