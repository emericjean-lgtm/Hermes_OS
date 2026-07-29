"""Isolation Manager for Hermes OS (HOS-057).

Manages enhanced sandbox isolation profiles for agents:
- Filesystem isolation
- Network policy
- Environment isolation
- Tool restrictions
- Resource limits
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from .security_models import IsolationLevel, IsolationProfile


class IsolationManager:
    """Manages sandbox isolation profiles.

    Thread-safe. Creates and manages isolation profiles with
    configurable filesystem, network, tool, and resource policies.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, IsolationProfile] = {}
        self._active_sessions: dict[str, str] = {}  # session_id → profile_id
        self._violations: deque[dict] = deque(maxlen=200)

    def create_profile(
        self,
        level: IsolationLevel = IsolationLevel.LOW,
        allowed_files: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        blocked_networks: list[str] | None = None,
        max_memory_mb: int = 512,
        max_cpu_percent: float = 50.0,
        max_duration_s: int = 3600,
    ) -> IsolationProfile:
        import uuid
        profile = IsolationProfile(
            profile_id=f"iso_{uuid.uuid4().hex[:8]}",
            level=level,
            allowed_files=allowed_files or [],
            allowed_tools=allowed_tools or [],
            network_blocked=len(blocked_networks or []) > 0,
            max_memory_mb=max_memory_mb,
            max_cpu_percent=max_cpu_percent,
            max_duration_s=max_duration_s,
            write_paths=allowed_files or [],
        )
        with self._lock:
            self._profiles[profile.profile_id] = profile
        return profile

    def get_profile(self, profile_id: str) -> IsolationProfile | None:
        with self._lock:
            return self._profiles.get(profile_id)

    def get_profile_for_level(self, level: IsolationLevel) -> IsolationProfile:
        """Get or create a default profile for a given isolation level."""
        with self._lock:
            for p in self._profiles.values():
                if p.level == level:
                    return p

        # Create a default profile for this level
        if level == IsolationLevel.LOW:
            return self.create_profile(level, ["/tmp", "/home"], ["*"], max_memory_mb=1024)
        elif level == IsolationLevel.MEDIUM:
            return self.create_profile(level, ["/tmp/workspace"], ["read", "write"],
                                       max_memory_mb=512, max_cpu_percent=50)
        elif level == IsolationLevel.HIGH:
            return self.create_profile(level, ["/tmp/workspace/project"], ["read"],
                                       max_memory_mb=256, max_cpu_percent=25, blocked_networks=["*"])
        elif level == IsolationLevel.MAXIMUM:
            return self.create_profile(level, [], [],
                                       max_memory_mb=128, max_cpu_percent=10,
                                       blocked_networks=["*"], max_duration_s=300)
        return self.create_profile(level, [], [], max_memory_mb=64)

    def start_session(self, session_id: str, profile_id: str) -> bool:
        with self._lock:
            if profile_id not in self._profiles:
                return False
            self._active_sessions[session_id] = profile_id
            return True

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            return self._active_sessions.pop(session_id, None) is not None

    def get_session_profile(self, session_id: str) -> IsolationProfile | None:
        with self._lock:
            pid = self._active_sessions.get(session_id)
            if pid is None:
                return None
            return self._profiles.get(pid)

    def validate_operation(self, session_id: str, operation: str, target: str) -> bool:
        """Validate if an operation is allowed for a session."""
        profile = self.get_session_profile(session_id)
        if profile is None:
            return False

        if operation == "file_read":
            return any(target.startswith(p) for p in profile.allowed_files)
        elif operation == "file_write":
            return any(target.startswith(p) for p in profile.write_paths)
        elif operation == "network":
            return not profile.network_blocked
        elif operation == "tool":
            if "*" in profile.allowed_tools:
                return True
            return target in profile.allowed_tools
        elif operation == "resource":
            return True  # Resource limits enforced by the environment
        return True

    def record_violation(self, session_id: str, operation: str, target: str, details: str = "") -> None:
        with self._lock:
            self._violations.append({
                "session_id": session_id,
                "operation": operation,
                "target": target,
                "details": details,
                "timestamp": __import__("time").time(),
            })

    def get_violations(self, session_id: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            violations = list(self._violations)
            if session_id:
                violations = [v for v in violations if v["session_id"] == session_id]
            return violations[-limit:]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_profiles": len(self._profiles),
                "active_sessions": len(self._active_sessions),
                "total_violations": len(self._violations),
                "profiles_by_level": {
                    level.value: sum(1 for p in self._profiles.values() if p.level == level)
                    for level in IsolationLevel
                },
            }
