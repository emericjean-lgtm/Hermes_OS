"""Threat Detector for Hermes OS (HOS-057).

Real-time threat detection for:
- Unauthorized file access
- Sandbox escape attempts
- Anomalous agent behavior
- Suspicious tool calls
- Excessive resource consumption
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

from .security_models import ThreatDetection, ThreatLevel


class ThreatDetector:
    """Real-time threat detection engine.

    Thread-safe. Maintains incident history and threat rules.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._threats: list[ThreatDetection] = []
        self._incidents: deque[ThreatDetection] = deque(maxlen=500)
        self._resource_usage: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._tool_call_frequency: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._max_resource_per_sec: float = 1000.0

    def check_file_access(self, principal_id: str, file_path: str, allowed_paths: list[str]) -> ThreatDetection | None:
        """Check if file access is within allowed paths."""
        allowed = any(file_path.startswith(p) for p in allowed_paths)
        if not allowed:
            threat = ThreatDetection(
                threat_id=f"threat_{int(time.time())}",
                level=ThreatLevel.MEDIUM,
                source="file_system",
                principal_id=principal_id,
                threat_type="unauthorized_file_access",
                description=f"Unauthorized file access: {file_path}",
                evidence={"file_path": file_path, "allowed_paths": allowed_paths},
                severity_score=0.6,
            )
            self._record_threat(threat)
            return threat
        return None

    def check_resource_usage(self, principal_id: str, resource_type: str, current_usage: float) -> ThreatDetection | None:
        """Check if resource usage exceeds thresholds."""
        with self._lock:
            self._resource_usage[principal_id].append((time.time(), current_usage))
            recent = list(self._resource_usage[principal_id])
            recent_usages = [r[1] for r in recent if time.time() - r[0] < 10]

        if recent_usages and sum(recent_usages) > self._max_resource_per_sec * 3:
            threat = ThreatDetection(
                threat_id=f"threat_{int(time.time())}",
                level=ThreatLevel.HIGH,
                source="resource_monitor",
                principal_id=principal_id,
                threat_type="excessive_resource_usage",
                description=f"Excessive {resource_type} usage: {sum(recent_usages):.0f} in 10s",
                evidence={"resource_type": resource_type, "usage": sum(recent_usages)},
                severity_score=0.8,
            )
            self._record_threat(threat)
            return threat
        return None

    def check_tool_call(self, principal_id: str, tool_name: str, parameters: dict) -> ThreatDetection | None:
        """Check for suspicious tool calls."""
        suspicious_tools = ["exec", "shell", "subprocess", "eval", "compile"]
        suspicious = [t for t in suspicious_tools if t in tool_name.lower()]

        if suspicious:
            # Check frequency
            with self._lock:
                self._tool_call_frequency[principal_id].append(time.time())
                recent = [t for t in self._tool_call_frequency[principal_id]
                         if time.time() - t < 60]

            if len(recent) > 10:
                threat = ThreatDetection(
                    threat_id=f"threat_{int(time.time())}",
                    level=ThreatLevel.HIGH,
                    source="tool_monitor",
                    principal_id=principal_id,
                    threat_type="suspicious_tool_call",
                    description=f"Suspicious tool ({tool_name}) called {len(recent)}x in 60s",
                    evidence={"tool": tool_name, "frequency": len(recent), "parameters": parameters},
                    severity_score=0.7,
                )
                self._record_threat(threat)
                return threat

        # Flag specific suspicious tools
        if "exec" in tool_name.lower() or "shell" in tool_name.lower():
            threat = ThreatDetection(
                threat_id=f"threat_{int(time.time())}",
                level=ThreatLevel.MEDIUM,
                source="tool_monitor",
                principal_id=principal_id,
                threat_type="suspicious_tool_call",
                description=f"Execution tool called: {tool_name}",
                evidence={"tool": tool_name, "parameters": parameters},
                severity_score=0.5,
            )
            self._record_threat(threat)
            return threat
        return None

    def check_sandbox_violation(self, principal_id: str, violation_type: str, details: dict) -> ThreatDetection:
        """Record a sandbox violation."""
        threat = ThreatDetection(
            threat_id=f"threat_{int(time.time())}",
            level=ThreatLevel.CRITICAL,
            source="sandbox",
            principal_id=principal_id,
            threat_type="sandbox_violation",
            description=f"Sandbox violation: {violation_type}",
            evidence=details,
            severity_score=0.95,
        )
        self._record_threat(threat)
        return threat

    def get_threats(
        self, principal_id: str | None = None, level: ThreatLevel | None = None, limit: int = 50
    ) -> list[ThreatDetection]:
        with self._lock:
            threats = list(self._incidents)
            if principal_id:
                threats = [t for t in threats if t.principal_id == principal_id]
            if level:
                threats = [t for t in threats if t.level == level]
            return threats[-limit:]

    def mitigate_threat(self, threat_id: str, action: str) -> bool:
        with self._lock:
            for t in self._threats:
                if t.threat_id == threat_id and not t.mitigated:
                    t.mitigated = True
                    t.mitigation_action = action
                    return True
            for t in self._incidents:
                if t.threat_id == threat_id and not t.mitigated:
                    t.mitigated = True
                    t.mitigation_action = action
                    return True
            return False

    def stats(self) -> dict[str, Any]:
        with self._lock:
            threats = list(self._incidents)
            return {
                "total_threats": len(threats),
                "mitigated": sum(1 for t in threats if t.mitigated),
                "unmitigated": sum(1 for t in threats if not t.mitigated),
                "by_level": {
                    level.value: sum(1 for t in threats if t.level == level)
                    for level in ThreatLevel
                },
                "by_type": self._count_by_type(threats),
            }

    # ── Private ──

    def _record_threat(self, threat: ThreatDetection):
        with self._lock:
            self._threats.append(threat)
            self._incidents.append(threat)

    @staticmethod
    def _count_by_type(threats: list[ThreatDetection]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in threats:
            if t.threat_type not in counts:
                counts[t.threat_type] = 0
            counts[t.threat_type] += 1
        return counts
