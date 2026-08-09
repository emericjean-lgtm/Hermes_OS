"""Tests for real installation detection (R-006 Phase 6).

Before this, ``is_installed()`` returned True merely because a package
runner (klaatcode/omp/bunx/npx) existed on PATH — never because the actual
package was confirmed to run. Real subprocess calls are monkeypatched here;
no real klaatcode/omp CLI is required for these tests to be meaningful.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from backend.tools.connectors.klaatcode.klaatcode_client import KlaatCodeClient
from backend.tools.connectors.oh_my_pi.ohmypi_client import OhMyPiClient


def _fake_run(*, returncode: int, stdout: str = "", stderr: str = ""):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


class TestKlaatCodeRealInstallDetection:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/npx" if name in ("npx", "bunx") else None)
        return KlaatCodeClient()

    def test_candidate_present_is_not_installed_by_itself(self, client, monkeypatch):
        """A runner is located, but nothing has actually been confirmed to
        run yet — this is exactly the pre-Phase-6 false positive."""
        assert client._candidate_located() is True
        monkeypatch.setattr(subprocess, "run", _fake_run(returncode=1, stderr="unknown command"))
        assert client.is_installed() is False

    def test_real_successful_probe_marks_installed(self, client, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout="2.4.4\n"))
        assert client.is_installed() is True
        assert client.get_version() == "2.4.4"

    def test_no_candidate_at_all_is_not_installed(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        client = KlaatCodeClient()
        assert client._candidate_located() is False
        assert client.is_installed() is False

    def test_failing_probe_is_retried_only_after_cooldown(self, client, monkeypatch):
        """The bug this guards: without a cooldown, is_installed() calling
        get_version() on every poll re-ran a real (failing) subprocess call
        every single time — the observed "runs climbing every 15s" symptom."""
        calls = {"n": 0}

        def counting_run(cmd, **kwargs):
            calls["n"] += 1
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")

        monkeypatch.setattr(subprocess, "run", counting_run)
        client._HEALTH_CHECK_COOLDOWN_S = 9999  # never expires within the test

        for _ in range(20):
            assert client.is_installed() is False

        assert calls["n"] == 1, "one real attempt, not one per is_installed() call"

    def test_execute_does_not_recurse_through_is_installed(self, client, monkeypatch):
        """execute() must gate on candidate presence, not is_installed() —
        the latter now calls get_version() -> health_check() -> execute(),
        which would recurse forever if execute() called is_installed()."""
        monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout="2.4.4\n"))
        # No RecursionError, no hang: proves the guard uses _candidate_located().
        assert client.is_installed() is True


class TestOhMyPiRealInstallDetection:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/npx" if name in ("npx", "bunx") else None)
        return OhMyPiClient()

    def test_real_npm_resolution_failure_is_not_installed(self, client, monkeypatch):
        """Mirrors the actual observed failure: `omp` is a real npm package,
        `npx omp` exists as a runner, but the package has no runnable
        executable — "could not determine executable to run"."""
        monkeypatch.setattr(
            subprocess, "run",
            _fake_run(returncode=1, stderr="npm error could not determine executable to run"),
        )
        assert client._candidate_located() is True
        assert client.is_installed() is False

    def test_real_successful_probe_marks_installed(self, client, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout="1.0.0\n"))
        assert client.is_installed() is True
        assert client.get_version() == "1.0.0"

    def test_failing_probe_is_retried_only_after_cooldown(self, client, monkeypatch):
        calls = {"n": 0}

        def counting_run(cmd, **kwargs):
            calls["n"] += 1
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")

        monkeypatch.setattr(subprocess, "run", counting_run)
        client._HEALTH_CHECK_COOLDOWN_S = 9999

        for _ in range(20):
            assert client.is_installed() is False

        assert calls["n"] == 1
