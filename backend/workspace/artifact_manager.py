"""Artifact Manager for HOS-045.

Manages versioned artifacts: files, patches, reports, logs, docs, test results.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Callable, Optional

from backend.workspace.workspace_models import Artifact, ArtifactType


class ArtifactManager:
    """Manages versioned artifacts produced within workspaces.

    Supports versioning, checksum verification, and querying by workspace/agent/type.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._artifacts: dict[str, list[Artifact]] = {}  # name → versions
        self._by_workspace: dict[str, list[str]] = {}
        self._by_agent: dict[str, list[str]] = {}

    def create(
        self,
        workspace_id: str,
        agent_id: str,
        name: str,
        path: str,
        artifact_type: ArtifactType = ArtifactType.FILE,
        content: str = "",
        mime_type: str = "",
    ) -> Artifact:
        """Create a new artifact (version 1) or new version."""
        size_bytes = len(content.encode()) if content else 0
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16] if content else ""

        # Check for previous version
        previous_id = ""
        version = 1
        if name in self._artifacts and self._artifacts[name]:
            prev = self._artifacts[name][-1]
            previous_id = prev.artifact_id
            version = prev.version + 1

        artifact = Artifact(
            workspace_id=workspace_id,
            agent_id=agent_id,
            name=name,
            path=path,
            type=artifact_type,
            size_bytes=size_bytes,
            mime_type=mime_type,
            version=version,
            previous_version_id=previous_id,
            checksum=checksum,
        )

        with self._lock:
            self._artifacts.setdefault(name, []).append(artifact)
            self._by_workspace.setdefault(workspace_id, []).append(artifact.artifact_id)
            self._by_agent.setdefault(agent_id, []).append(artifact.artifact_id)

        if self._on_event:
            ev = "artifact.created" if version == 1 else "artifact.updated"
            self._on_event(ev, {
                "artifact_id": artifact.artifact_id,
                "name": name,
                "version": version,
                "workspace_id": workspace_id,
            }, severity="info")
        return artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        with self._lock:
            for versions in self._artifacts.values():
                for a in versions:
                    if a.artifact_id == artifact_id:
                        return a
        return None

    def get_versions(self, name: str) -> list[Artifact]:
        with self._lock:
            return list(self._artifacts.get(name, []))

    def get_latest(self, name: str) -> Optional[Artifact]:
        versions = self.get_versions(name)
        return versions[-1] if versions else None

    def get_by_workspace(self, workspace_id: str) -> list[Artifact]:
        with self._lock:
            ids = set(self._by_workspace.get(workspace_id, []))
            results = []
            for versions in self._artifacts.values():
                for a in versions:
                    if a.artifact_id in ids:
                        results.append(a)
            return results

    def get_by_agent(self, agent_id: str) -> list[Artifact]:
        with self._lock:
            ids = set(self._by_agent.get(agent_id, []))
            results = []
            for versions in self._artifacts.values():
                for a in versions:
                    if a.artifact_id in ids:
                        results.append(a)
            return results

    def get_by_type(self, workspace_id: str, artifact_type: ArtifactType) -> list[Artifact]:
        return [
            a for a in self.get_by_workspace(workspace_id)
            if a.type == artifact_type
        ]

    def list_names(self, workspace_id: str = "") -> list[str]:
        with self._lock:
            if workspace_id:
                return list(set(
                    a.name for a in self.get_by_workspace(workspace_id)
                ))
            return list(self._artifacts.keys())

    def stats(self) -> dict:
        with self._lock:
            total_versions = sum(len(v) for v in self._artifacts.values())
            return {
                "total_artifacts": len(self._artifacts),
                "total_versions": total_versions,
                "by_type": {
                    t.value: sum(
                        1 for v in self._artifacts.values()
                        for a in v if a.type == t
                    )
                    for t in ArtifactType
                },
            }
