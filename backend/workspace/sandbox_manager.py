"""Sandbox Manager for HOS-045.

Creates isolated execution environments per agent.
Supports read-only mode, network control, tool restrictions, temp storage, and auto-cleanup.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from backend.workspace.workspace_models import Sandbox, SandboxStatus


class SandboxManager:
    """Manages isolated sandboxes for agents.

    Each sandbox provides a controlled environment with:
    - Working directory
    - Environment variables
    - Permission controls (read-only, network, tools)
    - Temporary storage with auto-cleanup
    - Future backends: Docker, Podman, Firecracker, WSL

    Thread-safe.
    """

    def __init__(
        self,
        base_path: str = "/tmp/hermes-sandboxes",
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._base_path = base_path
        self._on_event = on_event
        self._sandboxes: dict[str, Sandbox] = {}
        self._by_workspace: dict[str, list[str]] = {}
        self._by_agent: dict[str, list[str]] = {}

    def create(
        self,
        workspace_id: str,
        agent_id: str,
        env_vars: Optional[dict[str, str]] = None,
        read_only: bool = False,
        network_access: bool = True,
        allowed_tools: Optional[list[str]] = None,
        max_temp_mb: int = 512,
    ) -> Sandbox:
        """Create a new sandbox for an agent."""
        sandbox_path = os.path.join(self._base_path, workspace_id, agent_id)
        temp_path = os.path.join(sandbox_path, "tmp")

        sb = Sandbox(
            workspace_id=workspace_id,
            agent_id=agent_id,
            root_path=sandbox_path,
            env_vars=dict(env_vars or {}),
            read_only=read_only,
            network_access=network_access,
            allowed_tools=allowed_tools or [],
            temp_path=temp_path,
            max_temp_mb=max_temp_mb,
            status=SandboxStatus.CREATED,
        )
        with self._lock:
            self._sandboxes[sb.sandbox_id] = sb
            self._by_workspace.setdefault(workspace_id, []).append(sb.sandbox_id)
            self._by_agent.setdefault(agent_id, []).append(sb.sandbox_id)

        if self._on_event:
            self._on_event("sandbox.created", {
                "sandbox_id": sb.sandbox_id,
                "workspace_id": workspace_id,
                "agent_id": agent_id,
            }, severity="info")
        return sb

    def start(self, sandbox_id: str) -> bool:
        """Start (activate) a sandbox."""
        return self._transition(sandbox_id, SandboxStatus.RUNNING)

    def stop(self, sandbox_id: str) -> bool:
        """Stop a sandbox."""
        return self._transition(sandbox_id, SandboxStatus.STOPPED)

    def destroy(self, sandbox_id: str) -> bool:
        """Destroy a sandbox and clean up."""
        ok = self._transition(sandbox_id, SandboxStatus.DESTROYED)
        if ok and self._on_event:
            self._on_event("sandbox.destroyed", {
                "sandbox_id": sandbox_id,
            }, severity="info")
        return ok

    def get(self, sandbox_id: str) -> Optional[Sandbox]:
        return self._sandboxes.get(sandbox_id)

    def get_by_workspace(self, workspace_id: str) -> list[Sandbox]:
        with self._lock:
            ids = self._by_workspace.get(workspace_id, [])
            return [self._sandboxes[sid] for sid in ids if sid in self._sandboxes]

    def get_by_agent(self, agent_id: str) -> list[Sandbox]:
        with self._lock:
            ids = self._by_agent.get(agent_id, [])
            return [self._sandboxes[sid] for sid in ids if sid in self._sandboxes]

    def get_active(self) -> list[Sandbox]:
        with self._lock:
            return [s for s in self._sandboxes.values() if s.status == SandboxStatus.RUNNING]

    def cleanup(self, agent_id: str = "") -> int:
        """Clean up sandboxes (destroyed or all for agent)."""
        count = 0
        with self._lock:
            to_remove = []
            for sid, sb in self._sandboxes.items():
                if sb.status == SandboxStatus.DESTROYED:
                    to_remove.append(sid)
                    count += 1
                elif agent_id and sb.agent_id == agent_id and sb.status != SandboxStatus.RUNNING:
                    to_remove.append(sid)
                    count += 1
            for sid in to_remove:
                del self._sandboxes[sid]
        return count

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._sandboxes),
                "by_status": {
                    st.value: sum(1 for s in self._sandboxes.values() if s.status == st)
                    for st in SandboxStatus
                },
                "active": len(self.get_active()),
            }

    def _transition(self, sandbox_id: str, new_status: SandboxStatus) -> bool:
        with self._lock:
            sb = self._sandboxes.get(sandbox_id)
            if sb is None:
                return False
            sb.status = new_status
        return True
