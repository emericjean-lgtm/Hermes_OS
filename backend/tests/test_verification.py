"""§16 — whitelisted lint / build / test runners.

This is the module that executes code, so most of what follows is about
what it *refuses* to do. The load-bearing claim is that a caller can name
a runner but cannot supply a command, an argument, or a shell — and that
claim deserves tests that would fail loudly if a future edit added an
"args" passthrough for convenience.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from backend.security.aegis_engine import Verdict
from backend.tools import verification
from backend.tools.verification import UnknownRunnerError


class _Aegis:
    def __init__(self, verdict=Verdict.ALLOW, reason="test"):
        self._verdict, self._reason = verdict, reason
        self.seen: list[str] = []

    def evaluate(self, request):
        self.seen.append(request.action_type)
        outer = self

        class _Decision:
            verdict = outer._verdict
            reason = outer._reason

        return _Decision()


# ── the whitelist is the security boundary ───────────────────────────
def test_unknown_runner_is_refused(tmp_path):
    with pytest.raises(UnknownRunnerError, match="Unknown runner"):
        verification.run(_Aegis(), str(tmp_path), "rm_minus_rf")


def test_error_message_lists_what_is_allowed(tmp_path):
    """A caller that guessed wrong should learn the real options rather
    than start probing."""
    with pytest.raises(UnknownRunnerError, match="pytest"):
        verification.run(_Aegis(), str(tmp_path), "inconnu")


def test_run_takes_no_command_or_argument_parameter():
    """The core claim of this module. A future `args` or `command`
    parameter would turn a whitelist into a shell, so assert the
    signature itself."""
    import inspect

    params = set(inspect.signature(verification.run).parameters)

    assert params == {"aegis", "repo_path", "runner_name", "timeout", "project_id"}
    for forbidden in ("args", "argv", "command", "cmd", "shell", "env", "extra"):
        assert forbidden not in params


def test_no_shipped_runner_invokes_a_shell_or_evaluates_text():
    """Rule 2 of config/verification.yaml, enforced rather than trusted."""
    dangerous = {"-c", "-e", "--eval", "sh", "bash", "cmd", "powershell", "zsh"}
    for runner in verification.list_runners():
        tokens = set(runner.argv)
        assert not (tokens & dangerous), f"{runner.name} contains a shell/eval token"


def test_npm_build_pins_its_script_name():
    """`npm run <caller-supplied>` would make every package.json script
    reachable — rule 1 of the whitelist."""
    build = next(r for r in verification.list_runners() if r.name == "npm_build")

    assert build.argv == ("npm", "run", "build")


def test_list_runners_reports_kinds(tmp_path):
    kinds = {r.kind for r in verification.list_runners()}

    # §16 names lint, build and tests explicitly.
    assert {"lint", "build", "test"} <= kinds


# ── the Aegis gate ───────────────────────────────────────────────────
def test_uses_the_verification_run_category(tmp_path):
    aegis = _Aegis(verdict=Verdict.DENY, reason="nope")

    verification.run(aegis, str(tmp_path), "pytest")

    assert aegis.seen == ["verification_run"]


def test_refusal_returns_a_result_and_runs_nothing(tmp_path, monkeypatch):
    called = False

    def spy(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("subprocess ran despite refusal")

    monkeypatch.setattr(subprocess, "run", spy)
    aegis = _Aegis(verdict=Verdict.REQUIRE_HUMAN_VALIDATION, reason="autonomy too low")

    result = verification.run(aegis, str(tmp_path), "pytest")

    assert result.ran is False
    assert result.verdict == "require_human_validation"
    assert "autonomy" in result.reason
    assert called is False


def test_shipped_policy_requires_validation_at_default_autonomy():
    """The safe default is the whole reason min_autonomy is "high": at the
    shipped autonomy_level this must never auto-allow."""
    import yaml
    from pathlib import Path

    from backend.security.permission_matrix import PermissionMatrix

    config = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "config" / "security.yaml").read_text(
            encoding="utf-8"
        )
    )
    matrix = PermissionMatrix(config)
    policy = matrix.get_category("verification_run")

    assert policy is not None
    assert policy.mandatory_validation is False
    # mutating matters: a non-mutating category is auto-allowed at every
    # autonomy level, and a test run absolutely writes (caches, coverage).
    assert policy.mutating is True
    assert policy.path_based is True
    assert policy.min_autonomy_for_auto_allow == "high"
    # HOS-077 deliberately raised the shipped default from "low" to
    # "medium" — still below verification_run's own "high" gate, so the
    # property this test guards (never auto-allow at the shipped default)
    # still holds. Pinned to the literal value on purpose: if this ever
    # silently becomes "high", this test must catch that verification_run
    # would then auto-allow.
    assert matrix.autonomy_level == "medium"


# ── real execution ───────────────────────────────────────────────────
def test_runs_a_real_passing_suite(tmp_path):
    pytest_available = pytest is not None
    assert pytest_available
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = verification.run(_Aegis(), str(tmp_path), "pytest")

    assert result.ran is True
    assert result.exit_code == 0
    assert result.passed is True
    assert result.kind == "test"
    assert result.duration_seconds >= 0


def test_a_failing_suite_is_reported_not_raised(tmp_path):
    """A red suite is a normal outcome to report, not an exception."""
    (tmp_path / "test_ko.py").write_text(
        "def test_ko():\n    assert 1 == 2\n", encoding="utf-8"
    )

    result = verification.run(_Aegis(), str(tmp_path), "pytest")

    assert result.ran is True
    assert result.passed is False
    assert result.exit_code != 0
    assert "test_ko" in result.output


def test_uses_this_interpreter_not_whatever_is_on_path(tmp_path):
    """{python} must resolve to sys.executable — on Windows a bare
    "python" is often a Store stub that exits non-zero."""
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    seen = {}
    real = subprocess.run

    def spy(argv, **kwargs):
        seen["argv"] = argv
        seen["shell"] = kwargs.get("shell")
        return real(argv, **kwargs)

    import backend.tools.verification as mod

    mod.subprocess.run = spy
    try:
        verification.run(_Aegis(), str(tmp_path), "pytest")
    finally:
        mod.subprocess.run = real

    assert seen["argv"][0] == sys.executable
    assert seen["shell"] is False


def test_timeout_is_reported_distinctly_from_failure(tmp_path, monkeypatch):
    """A timeout and a red suite need different reactions, so they must
    not both look like exit_code != 0."""

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)

    result = verification.run(_Aegis(), str(tmp_path), "pytest", timeout=1)

    assert result.ran is False
    assert result.timed_out is True
    assert result.exit_code is None
    assert "exceeded" in result.reason


def test_missing_tool_is_reported_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    )

    result = verification.run(_Aegis(), str(tmp_path), "npm_test")

    assert result.ran is False
    assert result.timed_out is False
    assert "not found" in result.reason


def test_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        verification.run(_Aegis(), str(tmp_path / "absent"), "pytest")


def test_file_instead_of_directory(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        verification.run(_Aegis(), str(target), "pytest")


# ── output handling ──────────────────────────────────────────────────
def test_truncation_keeps_the_tail_not_just_the_head():
    """A suite's summary line — how many failed — is at the very bottom.
    Naive head-only truncation throws away the one line that matters."""
    text = "DEBUT" + ("x" * 50000) + "FIN: 3 failed"

    out = verification._truncate(text, limit=1000)

    assert out.startswith("DEBUT")
    assert out.endswith("FIN: 3 failed")
    assert "truncated" in out
    assert len(out) < 1300


def test_short_output_is_untouched():
    assert verification._truncate("court") == "court"
