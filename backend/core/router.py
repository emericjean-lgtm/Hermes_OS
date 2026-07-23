"""Model router: picks which Ollama model to use for a given task type.

Implements the routing rules from the cahier des charges §10:
  1. Prefer a model that is already loaded in VRAM (avoid reload cost).
  2. Otherwise prefer the highest-priority candidate that fits the
     currently available VRAM.
  3. If nothing fits, fall back to the smallest candidate and flag it —
     the caller is expected to handle the resulting OOM/offload per §19.1.

All model names and routing priorities come from config/models.yaml —
this module never hardcodes a model tag.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import load_models_config


@dataclass(frozen=True)
class RoutingDecision:
    task_type: str
    role: str
    model: str
    tier: str
    reason: str


class UnknownTaskTypeError(ValueError):
    pass


class ModelRouter:
    def __init__(self, models_config: dict | None = None) -> None:
        config = models_config or load_models_config()
        self._roles: dict[str, dict] = config["roles"]
        self._routing: dict[str, list[str]] = config["routing"]

    def select_model(
        self,
        task_type: str,
        *,
        loaded_models: list[str] | None = None,
        available_vram_gb: float | None = None,
    ) -> RoutingDecision:
        candidates = self._routing.get(task_type)
        if candidates is None:
            raise UnknownTaskTypeError(
                f"No routing entry for task_type={task_type!r}. "
                f"Known types: {sorted(self._routing)}"
            )

        loaded = set(loaded_models or [])

        # 1. Already-loaded model wins regardless of tier preference order,
        #    as long as it's one of the valid candidates for this task.
        for role_name in candidates:
            role = self._roles[role_name]
            if role["model"] in loaded:
                return RoutingDecision(
                    task_type=task_type,
                    role=role_name,
                    model=role["model"],
                    tier=role["tier"],
                    reason="model already loaded in VRAM, reused to avoid reload",
                )

        # 2. Otherwise, first candidate (priority order) that fits available VRAM.
        if available_vram_gb is not None:
            for role_name in candidates:
                role = self._roles[role_name]
                if role.get("vram_gb", 0) <= available_vram_gb:
                    return RoutingDecision(
                        task_type=task_type,
                        role=role_name,
                        model=role["model"],
                        tier=role["tier"],
                        reason=f"fits available VRAM ({available_vram_gb} GB)",
                    )

            # 3. Nothing fits: downgrade to the smallest candidate and flag it.
            smallest_role_name = min(candidates, key=lambda r: self._roles[r].get("vram_gb", 0))
            role = self._roles[smallest_role_name]
            return RoutingDecision(
                task_type=task_type,
                role=smallest_role_name,
                model=role["model"],
                tier=role["tier"],
                reason=(
                    f"no candidate fits available VRAM ({available_vram_gb} GB); "
                    "downgraded to smallest candidate, expect CPU offload"
                ),
            )

        # No VRAM info available (e.g. GPU monitor not wired up yet): default priority order.
        default_role_name = candidates[0]
        role = self._roles[default_role_name]
        return RoutingDecision(
            task_type=task_type,
            role=default_role_name,
            model=role["model"],
            tier=role["tier"],
            reason="no VRAM constraint provided, using default priority order",
        )

    def running_model_tags(self, running_models: list[dict]) -> list[str]:
        """Extract model tags from an /api/ps response for use as `loaded_models`."""
        return [m["name"] for m in running_models if "name" in m]
