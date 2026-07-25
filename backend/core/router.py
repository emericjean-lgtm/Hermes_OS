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
    # Whether to let the model reason before answering (§22.1). Carried on
    # the decision rather than resolved by each caller, so it lands in the
    # audit log's routing_decision alongside the model it applies to.
    thinking: bool = False


class UnknownTaskTypeError(ValueError):
    pass


class ModelRouter:
    def __init__(self, models_config: dict | None = None) -> None:
        config = models_config or load_models_config()
        self._roles: dict[str, dict] = config["roles"]
        self._routing: dict[str, list[str]] = config["routing"]
        thinking = config.get("thinking") or {}
        self._thinking_default: bool = bool(thinking.get("default", False))
        self._thinking_by_task: dict[str, bool] = dict(thinking.get("by_task_type") or {})

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
                return self._decide(
                    task_type, role_name, role,
                    "model already loaded in VRAM, reused to avoid reload",
                )

        # 2. Otherwise, first candidate (priority order) that fits available VRAM.
        if available_vram_gb is not None:
            for role_name in candidates:
                role = self._roles[role_name]
                if role.get("vram_gb", 0) <= available_vram_gb:
                    return self._decide(
                        task_type, role_name, role,
                        f"fits available VRAM ({available_vram_gb} GB)",
                    )

            # 3. Nothing fits: downgrade to the smallest candidate and flag it.
            smallest_role_name = min(candidates, key=lambda r: self._roles[r].get("vram_gb", 0))
            role = self._roles[smallest_role_name]
            return self._decide(
                task_type, smallest_role_name, role,
                f"no candidate fits available VRAM ({available_vram_gb} GB); "
                "downgraded to smallest candidate, expect CPU offload",
            )

        # No VRAM info available (e.g. GPU monitor not wired up yet): default priority order.
        default_role_name = candidates[0]
        role = self._roles[default_role_name]
        return self._decide(
            task_type, default_role_name, role,
            "no VRAM constraint provided, using default priority order",
        )

    def _decide(self, task_type: str, role_name: str, role: dict, reason: str) -> RoutingDecision:
        """Single construction point for a decision.

        select_model has four exit paths, and each used to build the
        dataclass by hand. Adding `thinking` to three of the four would
        have shipped a field that is correct only sometimes — the same
        shape of bug as the audit log's silently-null first_token_ms.
        """
        return RoutingDecision(
            task_type=task_type,
            role=role_name,
            model=role["model"],
            tier=role["tier"],
            reason=reason,
            thinking=self.thinking_for(task_type),
        )

    def thinking_for(self, task_type: str) -> bool:
        """§22.1 — reasoning costs ~3.5 s of silence before the first
        visible word (measured on qwen3.5:9b, RX 6800: 4 223 ms to first
        content token with reasoning, 675 ms without). It is worth that on
        code, planning and verification; it is not on conversation or
        extraction. Anything absent from the map takes the default, and
        the choice is recorded on the decision so it shows up in the audit
        log rather than being invisible."""
        return self._thinking_by_task.get(task_type, self._thinking_default)

    def running_model_tags(self, running_models: list[dict]) -> list[str]:
        """Extract model tags from an /api/ps response for use as `loaded_models`."""
        return [m["name"] for m in running_models if "name" in m]

    def model_for_role(self, role_name: str) -> str:
        """Resolve a role's configured model directly, bypassing the
        task_type/candidate-list routing above — for callers that are
        deterministically bound to one specific role rather than picking
        among ranked candidates (e.g. Aegis's own advisory pass, always
        the `security` role, never competing against `reasoning`)."""
        return self._roles[role_name]["model"]
