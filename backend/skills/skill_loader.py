"""Lazy skill loader with hot reload (HOS-048)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .skill_models import LoadState, SkillInstance
from .skill_registry import SkillRegistry


class SkillLoader:
    """Loads and unloads skills on demand.

    Supports:
    - Lazy loading (load when first needed)
    - Hot reload (reload without restart)
    - Unload (free resources)
    - Version tracking
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._instances: dict[str, SkillInstance] = {}  # instance_id → instance
        self._by_skill: dict[str, list[str]] = {}  # skill_id → [instance_ids]
        self._load_hooks: dict[str, Callable] = {}  # skill_id → init_fn

    def register_hook(self, skill_id: str, init_fn: Callable[[], None]) -> None:
        """Register an initialization function for a skill."""
        with self._lock:
            self._load_hooks[skill_id] = init_fn

    def load(self, skill_id: str, agent_id: str = "", mission_id: str = "") -> Optional[SkillInstance]:
        """Load a skill, creating a new instance."""
        with self._lock:
            skill = self._registry.get(skill_id)
            if skill is None:
                return None

            instance = SkillInstance(
                skill_id=skill_id,
                load_state=LoadState.LOADING,
                agent_id=agent_id,
                mission_id=mission_id,
            )
            self._instances[instance.id] = instance
            self._by_skill.setdefault(skill_id, []).append(instance.id)

            try:
                # Run registered init hook if any
                hook = self._load_hooks.get(skill_id)
                if hook:
                    hook()

                instance.load_state = LoadState.LOADED
                instance.loaded_at = datetime.now(timezone.utc)
                instance.current_memory_mb = skill.memory_cost_mb
                instance.current_tokens = skill.token_cost_estimate
            except Exception:
                instance.load_state = LoadState.ERROR
                raise

            return instance

    def unload(self, instance_id: str) -> bool:
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False

            instance.load_state = LoadState.UNLOADING
            instance.load_state = LoadState.UNLOADED
            instance.unloaded_at = datetime.now(timezone.utc)
            return True

    def unload_all(self) -> int:
        with self._lock:
            count = 0
            for instance in self._instances.values():
                if instance.load_state == LoadState.LOADED:
                    instance.load_state = LoadState.UNLOADED
                    instance.unloaded_at = datetime.now(timezone.utc)
                    count += 1
            return count

    def hot_reload(self, skill_id: str) -> list[SkillInstance]:
        """Unload then reload all instances of a skill."""
        with self._lock:
            instance_ids = list(self._by_skill.get(skill_id, []))
            # Unload
            for iid in instance_ids:
                inst = self._instances.get(iid)
                if inst:
                    inst.load_state = LoadState.UNLOADED
                    inst.unloaded_at = datetime.now(timezone.utc)

            # Reload
            reloaded: list[SkillInstance] = []
            for iid in instance_ids:
                inst = self._instances.get(iid)
                if inst:
                    inst.load_state = LoadState.LOADED
                    inst.loaded_at = datetime.now(timezone.utc)
                    reloaded.append(inst)

            return reloaded

    def get_instance(self, instance_id: str) -> Optional[SkillInstance]:
        with self._lock:
            return self._instances.get(instance_id)

    def get_loaded(self, skill_id: str) -> list[SkillInstance]:
        with self._lock:
            instance_ids = self._by_skill.get(skill_id, [])
            return [
                self._instances[iid]
                for iid in instance_ids
                if iid in self._instances and self._instances[iid].load_state == LoadState.LOADED
            ]

    def get_all_loaded(self) -> list[SkillInstance]:
        with self._lock:
            return [i for i in self._instances.values() if i.load_state == LoadState.LOADED]

    def count_loaded(self) -> int:
        return len(self.get_all_loaded())

    def stats(self) -> dict:
        with self._lock:
            total = len(self._instances)
            loaded = sum(1 for i in self._instances.values() if i.load_state == LoadState.LOADED)
            errors = sum(1 for i in self._instances.values() if i.load_state == LoadState.ERROR)
            return {"total_instances": total, "loaded": loaded, "unloaded": total - loaded - errors, "errors": errors}
