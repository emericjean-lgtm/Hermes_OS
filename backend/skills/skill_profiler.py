"""Skill runtime profiler — measures load time, memory, tokens, success rate (HOS-048)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .skill_models import SkillProfile


class SkillProfiler:
    """Profiles skill performance at runtime."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, SkillProfile] = {}

    def start_profile(self, skill_id: str) -> float:
        """Record start time, returns timestamp."""
        return time.monotonic()

    def end_profile(
        self,
        skill_id: str,
        start_time: float,
        *,
        memory_mb: float = 0.0,
        tokens: int = 0,
        success: bool = True,
    ) -> SkillProfile:
        """Complete a profile sample."""
        elapsed_ms = (time.monotonic() - start_time) * 1000

        with self._lock:
            profile = self._profiles.get(skill_id)
            if profile is None:
                profile = SkillProfile(skill_id=skill_id)
                self._profiles[skill_id] = profile

            n = profile.sample_count
            # Exponential moving average
            alpha = 2.0 / (n + 2)  # Weight for new sample
            profile.avg_load_time_ms = profile.avg_load_time_ms * (1 - alpha) + elapsed_ms * alpha
            profile.avg_memory_mb = profile.avg_memory_mb * (1 - alpha) + memory_mb * alpha
            profile.avg_tokens = int(profile.avg_tokens * (1 - alpha) + tokens * alpha)
            profile.avg_duration_ms = profile.avg_duration_ms * (1 - alpha) + elapsed_ms * alpha
            profile.max_memory_mb = max(profile.max_memory_mb, memory_mb)

            if not success:
                profile.failure_rate = profile.failure_rate * (1 - alpha) + 1.0 * alpha
            else:
                profile.failure_rate = profile.failure_rate * (1 - alpha)

            profile.sample_count += 1
            profile.last_profiled = datetime.now(timezone.utc)

            return profile

    def get(self, skill_id: str) -> Optional[SkillProfile]:
        with self._lock:
            return self._profiles.get(skill_id)

    def get_all(self) -> list[SkillProfile]:
        with self._lock:
            return list(self._profiles.values())

    def clear(self) -> int:
        with self._lock:
            count = len(self._profiles)
            self._profiles.clear()
            return count

    def stats(self) -> dict:
        with self._lock:
            return {
                "profiled_skills": len(self._profiles),
                "avg_load_ms": round(
                    sum(p.avg_load_time_ms for p in self._profiles.values()) / max(len(self._profiles), 1), 2
                ),
                "total_samples": sum(p.sample_count for p in self._profiles.values()),
            }
