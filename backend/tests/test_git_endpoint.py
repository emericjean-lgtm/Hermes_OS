"""§14 — the /git/* REST surface.

Read routes get one smoke test each; the write routes are tested for the
distinction that matters at this boundary: a *refusal* is a 200 carrying
applied=false plus a verdict the caller must show the user, while a
*fault* (bad path, not a repository) is an error status. Collapsing the
two would either hide a security decision inside an error handler or
dress a real fault up as a policy decision.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, shell=False
    )


@pytest.fixture
def repo_on_main(tmp_path):
    """A repository sitting on a protected branch — the case §14 exists
    for, and the one worth wiring end to end."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    return path


def _allow_aegis(monkeypatch):
    """Neutralise the whitelist so the test exercises the branch rule
    rather than ALLOWED_PATHS, which tmp_path would trip first."""
    from backend.security.aegis_engine import Verdict

    class _Decision:
        verdict = Verdict.ALLOW
        reason = "test"

    class _Aegis:
        def evaluate(self, request):
            return _Decision()

    monkeypatch.setattr("backend.api.routes.git._aegis", lambda: _Aegis())


def test_commit_on_protected_branch_is_a_200_refusal_not_an_error(
    client, repo_on_main, monkeypatch
):
    _allow_aegis(monkeypatch)
    (repo_on_main / "README.md").write_text("modifie\n", encoding="utf-8")

    response = client.post(
        "/git/commit", json={"repo_path": str(repo_on_main), "message": "essai"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["verdict"] == "deny"
    assert "protected branch" in body["reason"]


def test_push_to_protected_branch_is_refused(client, repo_on_main, monkeypatch):
    _allow_aegis(monkeypatch)

    body = client.post(
        "/git/push", json={"repo_path": str(repo_on_main), "branch": "main"}
    ).json()

    assert body["applied"] is False
    assert body["verdict"] == "deny"


def test_creating_a_protected_branch_name_is_refused(client, repo_on_main, monkeypatch):
    _allow_aegis(monkeypatch)

    body = client.post(
        "/git/branch", json={"repo_path": str(repo_on_main), "name": "master"}
    ).json()

    assert body["applied"] is False
    assert "protected branch name" in body["reason"]


def test_aegis_refusal_surfaces_its_verdict(client, repo_on_main, monkeypatch):
    from backend.security.aegis_engine import Verdict

    class _Decision:
        verdict = Verdict.REQUIRE_HUMAN_VALIDATION
        reason = "autonomy level too low"

    class _Aegis:
        def evaluate(self, request):
            return _Decision()

    monkeypatch.setattr("backend.api.routes.git._aegis", lambda: _Aegis())

    body = client.post(
        "/git/branch", json={"repo_path": str(repo_on_main), "name": "feature/x"}
    ).json()

    assert body["applied"] is False
    assert body["verdict"] == "require_human_validation"
    assert "autonomy" in body["reason"]


def test_happy_path_branch_then_commit(client, repo_on_main, monkeypatch):
    _allow_aegis(monkeypatch)

    created = client.post(
        "/git/branch", json={"repo_path": str(repo_on_main), "name": "feature/y"}
    ).json()
    assert created["applied"] is True

    (repo_on_main / "nouveau.txt").write_text("contenu", encoding="utf-8")
    committed = client.post(
        "/git/commit", json={"repo_path": str(repo_on_main), "message": "ajoute"}
    ).json()

    assert committed["applied"] is True
    assert committed["detail"]["branch"] == "feature/y"


# ── faults keep their error codes ────────────────────────────────────
def test_path_outside_allowed_paths_is_403(client, repo_on_main):
    """No monkeypatch here: the real Aegis must refuse tmp_path."""
    response = client.get("/git/status", params={"repo_path": str(repo_on_main)})

    assert response.status_code == 403


def test_non_repository_is_400(client, tmp_path, monkeypatch):
    _allow_aegis(monkeypatch)
    plain = tmp_path / "plain"
    plain.mkdir()

    response = client.get("/git/status", params={"repo_path": str(plain)})

    assert response.status_code == 400


def test_missing_path_is_404(client, tmp_path, monkeypatch):
    _allow_aegis(monkeypatch)

    response = client.get("/git/status", params={"repo_path": str(tmp_path / "absent")})

    assert response.status_code == 404


def test_status_reports_protected_before_anything_is_attempted(
    client, repo_on_main, monkeypatch
):
    """A caller should be able to see it is on main without first being
    refused a write."""
    _allow_aegis(monkeypatch)

    body = client.get("/git/status", params={"repo_path": str(repo_on_main)}).json()

    assert body["branch"] == "main"
    assert body["protected"] is True
