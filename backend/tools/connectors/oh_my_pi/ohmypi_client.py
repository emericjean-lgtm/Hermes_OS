"""Oh My Pi headless client wrapper (HOS-055B).

Wraps the omp CLI for headless operation within Hermes.
Supports installation detection, RPC command execution, health checks.
Thread-safe.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .ohmypi_models import (
    OhMyPiAction,
    OhMyPiRequest,
    OhMyPiResponse,
    OhMyPiStatus,
)


class OhMyPiClientError(Exception):
    pass


class OhMyPiClient:
    """Headless wrapper for Oh My Pi CLI (omp).

    Communicates via omp RPC mode or direct CLI invocations.
    """

    def __init__(self, omp_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._omp_path = omp_path or self._detect_installation()
        self._version: Optional[str] = None
        self._last_health_check_at: Optional[float] = None
        self._history: list[OhMyPiResponse] = []
        self._max_history = 500

    @staticmethod
    def _detect_installation() -> Optional[str]:
        path = shutil.which("omp")
        if path:
            return path
        for candidate in (shutil.which("bunx"), shutil.which("npx")):
            if candidate:
                return candidate
        return None

    def _candidate_located(self) -> bool:
        """A runner (omp/bunx/npx) exists on PATH — necessary but not
        sufficient (R-006 Phase 6): the real ``omp`` npm package can be
        published but not resolve to a runnable executable via npx, exactly
        what's observed on this machine ("could not determine executable to
        run") despite a runner being present."""
        with self._lock:
            if self._omp_path is None:
                self._omp_path = self._detect_installation()
            return self._omp_path is not None

    def is_installed(self) -> bool:
        """True only once a real invocation has actually succeeded — see
        KlaatCodeClient.is_installed()'s identical reasoning."""
        return self.get_version() is not None

    def execute(self, request: OhMyPiRequest) -> OhMyPiResponse:
        start = time.monotonic()
        response = OhMyPiResponse(request_id=request.id)

        with self._lock:
            # Not self.is_installed(): see KlaatCodeClient.execute()'s
            # identical comment — that would recurse through
            # get_version()/health_check()/execute() on the first call.
            if not self._candidate_located():
                response.status = OhMyPiStatus.ERROR
                response.error = "Oh My Pi (omp) is not installed"
                response.duration_ms = (time.monotonic() - start) * 1000
                self._record(response)
                return response

            try:
                cmd = self._build_command(request)
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=request.timeout_seconds,
                )
                response.duration_ms = (time.monotonic() - start) * 1000
                if proc.returncode == 0:
                    response.data = self._parse_output(request.action, proc.stdout)
                    response.status = OhMyPiStatus.SUCCESS
                else:
                    response.status = OhMyPiStatus.FAILED
                    response.error = proc.stderr.strip() or f"Exit {proc.returncode}"
            except subprocess.TimeoutExpired:
                response.status = OhMyPiStatus.TIMEOUT
                response.error = f"Timeout after {request.timeout_seconds}s"
                response.duration_ms = request.timeout_seconds * 1000
            except FileNotFoundError:
                response.status = OhMyPiStatus.ERROR
                response.error = f"omp not found at '{self._omp_path}'"
                response.duration_ms = (time.monotonic() - start) * 1000
            except Exception as e:
                response.status = OhMyPiStatus.ERROR
                response.error = str(e)
                response.duration_ms = (time.monotonic() - start) * 1000

        response.timestamp = datetime.now(timezone.utc)
        self._record(response)
        return response

    def _build_command(self, request: OhMyPiRequest) -> list[str]:
        base = [self._omp_path] if self._omp_path else ["omp"]
        if any(r in str(self._omp_path) for r in ("bunx", "npx")):
            base.append("omp")
        params = request.parameters
        action = request.action

        cmd_map = {
            OhMyPiAction.LSP_OPEN_FILE: base + ["--lsp-open", params.get("file", "")],
            OhMyPiAction.LSP_EDIT: base + ["--lsp-edit", params.get("file", ""), params.get("edit", "")],
            OhMyPiAction.AST_TRANSFORM: base + ["--ast", params.get("transform", ""), params.get("file", "")],
            OhMyPiAction.DEBUG_START: base + ["--debug", params.get("program", "")],
            OhMyPiAction.DEBUG_STEP: base + ["--debug-step"],
            OhMyPiAction.EXECUTE_PYTHON: base + ["--exec", "python", "-c", params.get("code", "")],
            OhMyPiAction.EXECUTE_JAVASCRIPT: base + ["--exec", "javascript", "-c", params.get("code", "")],
            OhMyPiAction.GIT_OPERATION: base + [params.get("op", "status")],
            OhMyPiAction.CODE_SEARCH: base + ["--search", params.get("query", "")],
            OhMyPiAction.HEALTH_CHECK: base + ["--version"],
        }
        return cmd_map.get(action, base + [action])

    def _parse_output(self, action: str, stdout: str) -> Any:
        stripped = stdout.strip()
        if action == OhMyPiAction.HEALTH_CHECK:
            self._version = stripped
            return {"version": stripped, "installed": True}
        return {"result": stripped, "action": action}

    def health_check(self) -> OhMyPiResponse:
        return self.execute(OhMyPiRequest(action=OhMyPiAction.HEALTH_CHECK, timeout_seconds=10.0))

    # Same reasoning as KlaatCodeClient's identical constant: without a
    # cooldown, is_installed() now calling this on every check would re-run
    # a real subprocess on every single poll for a provider that never
    # succeeds (R-006 Phase 6) — exactly the observed "every 15s poll
    # retries a failing omp invocation forever" behaviour.
    _HEALTH_CHECK_COOLDOWN_S = 30.0

    def get_version(self) -> Optional[str]:
        with self._lock:
            now = time.monotonic()
            stale = (
                self._last_health_check_at is None
                or (now - self._last_health_check_at) >= self._HEALTH_CHECK_COOLDOWN_S
            )
            if self._version is None and stale:
                self._last_health_check_at = now
                resp = self.health_check()
                if resp.status == OhMyPiStatus.SUCCESS and isinstance(resp.data, dict):
                    self._version = resp.data.get("version", "")
            return self._version

    def _record(self, response: OhMyPiResponse) -> None:
        self._history.append(response)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 50) -> list[OhMyPiResponse]:
        return list(self._history[-limit:])

    def stats(self) -> dict:
        total = len(self._history)
        if total == 0:
            return {"total_executions": 0, "success_rate": 0.0, "installed": self.is_installed(), "version": self._version}
        success = sum(1 for r in self._history if r.status == OhMyPiStatus.SUCCESS)
        return {
            "total_executions": total, "success_count": success,
            "failure_count": sum(1 for r in self._history if r.status == OhMyPiStatus.FAILED),
            "timeout_count": sum(1 for r in self._history if r.status == OhMyPiStatus.TIMEOUT),
            "success_rate": round(success / total, 4),
            "avg_duration_ms": round(sum(r.duration_ms for r in self._history) / max(total, 1), 2),
            "installed": self.is_installed(), "version": self._version,
        }
