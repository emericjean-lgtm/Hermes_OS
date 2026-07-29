"""Thread-safe skill registry (HOS-048)."""

from __future__ import annotations

import threading
from typing import Optional

from .skill_models import (
    SkillCategory,
    SkillDefinition,
    SkillDomain,
    SkillStatus,
)


class SkillRegistry:
    """Central registry of all known skills. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._skills: dict[str, SkillDefinition] = {}
        self._by_category: dict[SkillCategory, set[str]] = {c: set() for c in SkillCategory}
        self._by_domain: dict[SkillDomain, set[str]] = {d: set() for d in SkillDomain}
        self._by_tag: dict[str, set[str]] = {}  # tag → {skill_ids}
        self._by_status: dict[SkillStatus, set[str]] = {s: set() for s in SkillStatus}

    # ── CRUD ─────────────────────────────────────────────

    def register(self, skill: SkillDefinition) -> SkillDefinition:
        """Register or update a skill."""
        with self._lock:
            self._skills[skill.id] = skill
            self._index(skill)
            return skill

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_all(self) -> list[SkillDefinition]:
        with self._lock:
            return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[SkillDefinition]:
        with self._lock:
            ids = self._by_category.get(category, set())
            return [self._skills[sid] for sid in ids if sid in self._skills]

    def list_by_domain(self, domain: SkillDomain) -> list[SkillDefinition]:
        with self._lock:
            ids = self._by_domain.get(domain, set())
            return [self._skills[sid] for sid in ids if sid in self._skills]

    def list_by_tag(self, tag: str) -> list[SkillDefinition]:
        with self._lock:
            ids = self._by_tag.get(tag, set())
            return [self._skills[sid] for sid in ids if sid in self._skills]

    def list_by_status(self, status: SkillStatus) -> list[SkillDefinition]:
        with self._lock:
            ids = self._by_status.get(status, set())
            return [self._skills[sid] for sid in ids if sid in self._skills]

    def list_active(self) -> list[SkillDefinition]:
        return self.list_by_status(SkillStatus.ACTIVE)

    def delete(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.pop(skill_id, None)
            if skill is None:
                return False
            self._unindex(skill)
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._skills)

    # ── Index helpers ────────────────────────────────────

    def _index(self, skill: SkillDefinition) -> None:
        self._by_category[skill.category].add(skill.id)
        self._by_domain[skill.domain].add(skill.id)
        self._by_status[skill.status].add(skill.id)
        for tag in skill.tags:
            self._by_tag.setdefault(tag, set()).add(skill.id)

    def _unindex(self, skill: SkillDefinition) -> None:
        self._by_category[skill.category].discard(skill.id)
        self._by_domain[skill.domain].discard(skill.id)
        self._by_status[skill.status].discard(skill.id)
        for tag in skill.tags:
            s = self._by_tag.get(tag)
            if s:
                s.discard(skill.id)
                if not s:
                    del self._by_tag[tag]

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._skills),
                "by_category": {c.value: len(ids) for c, ids in self._by_category.items() if ids},
                "by_domain": {d.value: len(ids) for d, ids in self._by_domain.items() if ids},
                "by_status": {s.value: len(ids) for s, ids in self._by_status.items() if ids},
                "unique_tags": len(self._by_tag),
            }
