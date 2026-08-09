"""KlaatCode headless client wrapper (HOS-054B).

Provides a production-grade client for interacting with a KlaatCode installation.
Supports local, workspace, and sandbox environments.

The client communicates with KlaatCode via its CLI interface and manages:
- Installation detection
- Command execution with timeout
- stdout/stderr capture
- Error handling and retries
- Health checks

Thread-safe.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .klaatcode_models import (
    KlaatCodeAction,
    KlaatCodeRequest,
    KlaatCodeResponse,
    KlaatCodeStatus,
)


class KlaatCodeClientError(Exception):
    """Raised when the KlaatCode client encounters an unrecoverable error."""


class KlaatCodeClient:
    """Headless wrapper around the KlaatCode CLI.

    Responsibilities:
        - Detect KlaatCode installation on the system / workspace path.
        - Run KlaatCode commands with timeout and output capture.
        - Translate structured responses between Hermes models and CLI output.
        - Provide health-check and status introspection.
    """

    def __init__(self, klaatcode_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._klaatcode_path = klaatcode_path or self._detect_installation()
        self._version: Optional[str] = None
        self._last_health_check_at: Optional[float] = None
        self._history: list[KlaatCodeResponse] = []
        self._max_history = 500

    # ── Installation detection ───────────────────────────────

    @staticmethod
    def _detect_installation() -> Optional[str]:
        """Auto-detect the KlaatCode CLI on the system.

        Returns the executable path or None.
        """
        # Check PATH first
        path = shutil.which("klaatcode")
        if path:
            return path

        # Check common locations (bun, npm global, npx)
        for candidate in (
            shutil.which("bunx"),
            shutil.which("npx"),
        ):
            if candidate:
                return candidate  # will invoke via `bunx klaatcode` / `npx klaatcode`

        # Check for local project install
        local_candidates = [
            "./node_modules/.bin/klaatcode",
            "../node_modules/.bin/klaatcode",
        ]
        for local in local_candidates:
            if shutil.which(local):
                return local

        return None

    def _candidate_located(self) -> bool:
        """A runner (klaatcode/bunx/npx) exists on PATH — necessary but not
        sufficient. Presence of a package RUNNER is not presence of the
        klaatcode PACKAGE itself (R-006 Phase 6): ``npx``/``bunx`` existing
        proves nothing about whether ``npx klaatcode`` actually resolves."""
        with self._lock:
            if self._klaatcode_path is None:
                self._klaatcode_path = self._detect_installation()
            return self._klaatcode_path is not None

    def is_installed(self) -> bool:
        """True only once a real invocation has actually succeeded.

        Before R-006 this returned True merely because a package runner was
        on PATH, so the Cockpit showed "Installed: yes" for a provider whose
        every real command failed. A candidate runner is required to attempt
        anything, but "installed" now means a genuine health check answered.
        """
        return self.get_version() is not None

    # ── Command execution ────────────────────────────────────

    def execute(self, request: KlaatCodeRequest) -> KlaatCodeResponse:
        """Execute a KlaatCode CLI command and return a structured response.

        Args:
            request: A KlaatCodeRequest specifying the action and parameters.

        Returns:
            A KlaatCodeResponse with status, data, and timing.
        """
        start = time.monotonic()

        response = KlaatCodeResponse(request_id=request.id)

        with self._lock:
            # Not self.is_installed(): that now calls get_version(), which
            # calls health_check(), which calls execute() again — using it
            # here would recurse on the very first health check. A located
            # runner is all a real attempt needs; is_installed() itself is
            # answered by this attempt's own outcome, not asked of it first.
            if not self._candidate_located():
                response.status = KlaatCodeStatus.ERROR
                response.error = "KlaatCode is not installed or not found on PATH"
                response.duration_ms = (time.monotonic() - start) * 1000
                self._record(response)
                return response

            try:
                cmd = self._build_command(request)
                env = {}
                if request.workspace_id:
                    env["WORKSPACE_ID"] = request.workspace_id

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_seconds,
                    env={**env} if env else None,
                )

                response.duration_ms = (time.monotonic() - start) * 1000

                if proc.returncode == 0:
                    response.data = self._parse_output(request.action, proc.stdout)
                    response.status = KlaatCodeStatus.SUCCESS
                else:
                    response.status = KlaatCodeStatus.FAILED
                    response.error = proc.stderr.strip() or f"Exit code {proc.returncode}"

            except subprocess.TimeoutExpired:
                response.status = KlaatCodeStatus.TIMEOUT
                response.error = f"Command timed out after {request.timeout_seconds}s"
                response.duration_ms = request.timeout_seconds * 1000
            except FileNotFoundError:
                response.status = KlaatCodeStatus.ERROR
                response.error = f"KlaatCode executable not found at '{self._klaatcode_path}'"
                response.duration_ms = (time.monotonic() - start) * 1000
            except Exception as e:
                response.status = KlaatCodeStatus.ERROR
                response.error = str(e)
                response.duration_ms = (time.monotonic() - start) * 1000

        response.timestamp = datetime.now(timezone.utc)
        self._record(response)
        return response

    def _build_command(self, request: KlaatCodeRequest) -> list[str]:
        """Build the CLI command list from a request.

        When klaatcode_path is 'bunx' or 'npx', prepend 'klaatcode' as the first arg.
        """
        base = [self._klaatcode_path] if self._klaatcode_path else ["klaatcode"]

        # If using a package runner (bunx, npx), add 'klaatcode' as first arg
        if any(runner in str(self._klaatcode_path) for runner in ("bunx", "npx")):
            base.append("klaatcode")

        params = request.parameters

        if request.action == KlaatCodeAction.ANALYZE_PROJECT:
            return base + ["analyze", "--project", params.get("path", ".")]
        elif request.action == KlaatCodeAction.INSPECT_CODE:
            return base + ["inspect", "--file", params.get("file", "")]
        elif request.action == KlaatCodeAction.GENERATE_CODE_PLAN:
            return base + ["plan", params.get("prompt", "")]
        elif request.action == KlaatCodeAction.EDIT_FILE:
            return base + ["edit", "--file", params.get("file", ""),
                           "--content", params.get("content", "")]
        elif request.action == KlaatCodeAction.SEARCH_CODE:
            return base + ["search", params.get("query", "")]
        elif request.action == KlaatCodeAction.RUN_DIAGNOSTICS:
            return base + ["diagnostics", "--file", params.get("file", ".")]
        elif request.action == KlaatCodeAction.VALIDATE_CHANGES:
            return base + ["validate", "--file", params.get("file", "")]
        elif request.action == KlaatCodeAction.HEALTH_CHECK:
            return base + ["--version"]
        else:
            return base + [request.action]

    # ── Output parsing ───────────────────────────────────────

    def _parse_output(self, action: str, stdout: str) -> Any:
        """Parse CLI stdout into structured data.

        In production this would parse KlaatCode's structured JSON/NDJSON output.
        For now, returns a structured dict that the MCP adapter consumes.
        """
        stripped = stdout.strip()

        if action == KlaatCodeAction.ANALYZE_PROJECT:
            return {
                "project": {
                    "root_path": "",
                    "language": "typescript",
                    "framework": "unknown",
                    "file_count": 0,
                    "dependency_count": 0,
                    "git_enabled": True,
                },
                "raw": stripped,
            }
        elif action == KlaatCodeAction.SEARCH_CODE:
            return {"results": [], "query": "", "raw": stripped}
        elif action == KlaatCodeAction.RUN_DIAGNOSTICS:
            return {"diagnostics": [], "raw": stripped}
        elif action == KlaatCodeAction.VALIDATE_CHANGES:
            return {"valid": True, "errors": [], "warnings": [], "raw": stripped}
        elif action == KlaatCodeAction.HEALTH_CHECK:
            with self._lock:
                self._version = stripped
            return {"version": stripped, "installed": True}
        elif action == KlaatCodeAction.GENERATE_CODE_PLAN:
            return {"plan": stripped, "steps": []}
        elif action == KlaatCodeAction.EDIT_FILE:
            return {"edited": True, "file": "", "raw": stripped}
        elif action == KlaatCodeAction.INSPECT_CODE:
            return {"file": "", "symbols": [], "structure": {}, "raw": stripped}
        else:
            return {"raw": stripped}

    # ── Health check ─────────────────────────────────────────

    def health_check(self) -> KlaatCodeResponse:
        """Run a lightweight health check against the KlaatCode CLI."""
        request = KlaatCodeRequest(
            action=KlaatCodeAction.HEALTH_CHECK,
            timeout_seconds=10.0,
        )
        return self.execute(request)

    # Retry a failing health check at most this often. Without a cooldown, a
    # provider that never succeeds (R-006 Phase 6's is_installed() now calls
    # this on every check) would re-run a real subprocess on every single
    # status poll or is_installed() call — precisely the "every 15s poll
    # retries a failing command forever" behaviour observed for Oh My Pi.
    _HEALTH_CHECK_COOLDOWN_S = 30.0

    def get_version(self) -> Optional[str]:
        """Return the detected KlaatCode version, or None.

        Real subprocess call on first use and thereafter no more often than
        every ``_HEALTH_CHECK_COOLDOWN_S`` — a success caches permanently
        (the version does not change mid-process); a failure is retried on
        a cooldown rather than never or on every call.
        """
        with self._lock:
            now = time.monotonic()
            stale = (
                self._last_health_check_at is None
                or (now - self._last_health_check_at) >= self._HEALTH_CHECK_COOLDOWN_S
            )
            if self._version is None and stale:
                self._last_health_check_at = now
                resp = self.health_check()
                if resp.status == KlaatCodeStatus.SUCCESS and isinstance(resp.data, dict):
                    self._version = resp.data.get("version", "")
            return self._version

    # ── History ──────────────────────────────────────────────

    def _record(self, response: KlaatCodeResponse) -> None:
        with self._lock:
            self._history.append(response)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

    def get_history(self, limit: int = 50) -> list[KlaatCodeResponse]:
        with self._lock:
            return list(self._history[-limit:])

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {"total_executions": 0, "success_rate": 0.0, "installed": self.is_installed(), "version": self._version}
            success = sum(1 for r in self._history if r.status == KlaatCodeStatus.SUCCESS)
            fail = sum(1 for r in self._history if r.status == KlaatCodeStatus.FAILED)
            timeout = sum(1 for r in self._history if r.status == KlaatCodeStatus.TIMEOUT)
            avg_duration = (
                sum(r.duration_ms for r in self._history) / total if total else 0.0
            )
            return {
                "total_executions": total,
                "success_count": success,
                "failure_count": fail,
                "timeout_count": timeout,
                "success_rate": round(success / total, 4),
                "avg_duration_ms": round(avg_duration, 2),
                "installed": self.is_installed(),
                "version": self._version,
            }
