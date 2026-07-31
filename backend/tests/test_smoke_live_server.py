"""End-to-end smoke test against a REAL uvicorn server.

Why this file exists, concretely. On 2026-07-25 four bugs shipped past a
green suite of 500+ tests, and every one of them was found by running the
thing rather than by testing it:

  - `_aegis()` was called by two routes and defined nowhere. Both would
    have raised NameError on first contact. Nothing exercised them.
  - `memory_long` was missing the `project_id` column on any pre-existing
    database, so project-scoped queries raised OperationalError in
    production — while tests, which build a fresh database each run,
    always saw the current schema.
  - A workflow node referenced `$steps.review.raw`, a key verify_output
    does not return, failing that node on every single run.
  - The permanent-memory view listed a project's entries, because
    `project_id=None` means "don't filter", not "no project".

The common thread is that the suite never touched the real HTTP surface:
everything went through FastAPI's in-process TestClient, which shares the
test's own imports and fixtures. So this file boots an actual server as a
subprocess, over a real socket, against a real (temporary) database, and
talks to it with a real HTTP client.

The generalising assertion is `test_no_route_returns_5xx`: it enumerates
the app's own routes rather than a hand-written list, so a route added
later is covered without anyone remembering to add it here. A 4xx is a
pass — 422 for a missing query parameter means the route is wired
correctly and validating its input. Only 5xx means "this is broken".
"""
from __future__ import annotations

import collections
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT = 90


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _drain_in_background(process: subprocess.Popen, *, keep_last: int) -> collections.deque:
    """Continuously read a subprocess's stdout so it never blocks on write().

    ``stdout=PIPE`` gives the child a pipe with a small OS-level buffer
    (Windows: a few KB). Nothing in this file used to read that pipe except in
    the failure branch — reached only after the process had already exited —
    so during normal operation nobody drained it. Once cumulative log output
    (as little as ~50 lines of this app's multi-line, box-drawn logging)
    filled the buffer, the child's *next* write() call to stdout blocked
    indefinitely, and because that call happens inline with request handling,
    it froze every HTTP request the server was in the middle of or about to
    serve — observed as an httpx.ReadTimeout on requests whose own handlers
    did nothing slow at all. A background thread that keeps reading for the
    whole lifetime of the process is the standard fix for this subprocess.PIPE
    footgun; the bounded deque still gives failure messages something to show.
    """
    tail: collections.deque = collections.deque(maxlen=keep_last)

    def _drain() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            tail.append(line)

    threading.Thread(target=_drain, daemon=True).start()
    return tail


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """A real uvicorn process, isolated from the developer's own data.

    Module-scoped: booting the app imports chromadb and sqlalchemy and
    builds the agent registry, which costs seconds — paying that per test
    would make the file slow enough that it stops being run, and a smoke
    test nobody runs catches nothing.
    """
    workdir = tmp_path_factory.mktemp("smoke")
    allowed = workdir / "allowed"
    allowed.mkdir()

    env = {
        **os.environ,
        "SQLITE_PATH": str(workdir / "smoke.db"),
        "CHROMA_PATH": str(workdir / "chroma"),
        "ALLOWED_PATHS": str(allowed),
    }
    port = _free_port()
    process = subprocess.Popen(  # noqa: S603 - fixed argv, test-only
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
    )
    output_tail = _drain_in_background(process, keep_last=200)

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"server exited during startup:\n{''.join(output_tail)}")
        try:
            if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        process.terminate()
        pytest.fail(f"server did not become ready within {STARTUP_TIMEOUT}s")

    yield base, allowed

    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="module")
def base_url(live_server):
    return live_server[0]


def _parameterless_get_routes() -> list[str]:
    """Read the routes off the app itself, so this list cannot drift out
    of date the way a hand-maintained one would."""
    from backend.main import create_app

    skip = {"/openapi.json", "/redoc", "/docs"}
    routes = []
    for route in create_app().routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" in methods and "{" not in path and path not in skip:
            routes.append(path)
    return sorted(set(routes))


@pytest.mark.parametrize("path", _parameterless_get_routes())
def test_no_route_returns_5xx(base_url, path):
    """The assertion that would have caught the undefined _aegis() helper
    the moment it shipped.

    4xx passes on purpose: 422 for a missing required query parameter
    means the route is wired and validating. Only a 5xx says the code
    behind it is broken.
    """
    response = httpx.get(f"{base_url}{path}", timeout=30)

    assert response.status_code < 500, (
        f"GET {path} -> {response.status_code}\n{response.text[:500]}"
    )


def test_health(base_url):
    assert httpx.get(f"{base_url}/health", timeout=10).json()["status"] == "ok"


# ── the four escaped bugs, each pinned over real HTTP ────────────────
def test_project_scoped_memory_works_on_a_real_database(base_url):
    """Schema drift bug: this raised OperationalError in production while
    every in-process test passed."""
    project = httpx.post(
        f"{base_url}/projects", json={"name": "Smoke"}, timeout=30
    ).json()

    created = httpx.post(
        f"{base_url}/memory",
        json={"type": "decision", "content": "portee projet", "project_id": project["id"]},
        timeout=30,
    )
    assert created.status_code == 200

    brief = httpx.get(f"{base_url}/memory/project/{project['id']}", timeout=30)
    assert brief.status_code == 200
    assert brief.json()["by_type"]["decision"][0]["content"] == "portee projet"


def test_permanent_and_project_memory_stay_separate(base_url):
    """Level-mixing bug: only visible by looking at what came back."""
    project = httpx.post(f"{base_url}/projects", json={"name": "Sep"}, timeout=30).json()
    httpx.post(
        f"{base_url}/memory",
        json={"type": "architecture", "content": "SECRET-PROJET", "project_id": project["id"]},
        timeout=30,
    )
    httpx.post(
        f"{base_url}/memory",
        json={"type": "preference", "content": "GLOBALE"},
        timeout=30,
    )

    permanent = httpx.get(f"{base_url}/memory/permanent", timeout=30).json()
    contents = {e["content"] for e in permanent}

    assert "GLOBALE" in contents
    assert "SECRET-PROJET" not in contents


def test_approval_routes_actually_execute(base_url):
    """NameError bug: these two routes called a helper that did not exist,
    and no test called them."""
    refused = httpx.post(
        f"{base_url}/security/evaluate",
        json={
            "action_type": "git_critical",
            "description": "smoke: force push",
            "requesting_agent": "smoke",
        },
        timeout=30,
    )
    assert refused.json()["verdict"] == "require_human_validation"

    queue = httpx.get(f"{base_url}/security/approvals", params={"status": "pending"}, timeout=30)
    assert queue.status_code == 200
    entry = next(a for a in queue.json() if a["description"] == "smoke: force push")

    decided = httpx.post(
        f"{base_url}/security/approvals/{entry['id']}", json={"approved": False}, timeout=30
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "refused"


def test_shipped_workflows_reference_only_real_result_keys(base_url):
    """Placeholder bug: $steps.review.raw failed its node on every run,
    because verify_output does not return `raw`. Simulating each shipped
    workflow over HTTP proves the graph loads; the placeholder check
    itself lives in test_workflow_schema.py, which can inspect the tool
    registry directly."""
    workflows = httpx.get(f"{base_url}/workflows", timeout=30).json()
    assert workflows, "no workflows shipped — this test would pass vacuously"

    for workflow in workflows:
        result = httpx.post(
            f"{base_url}/workflows/{workflow['id']}/simulate", timeout=30
        )
        assert result.status_code == 200, f"{workflow['id']} failed to simulate"
        assert result.json()["execution_order"], f"{workflow['id']} has no executable order"


# ── the security boundary, over a real socket ────────────────────────
def test_allowed_paths_is_enforced_by_the_running_server(base_url):
    """The hard boundary, checked against the real process rather than an
    in-process engine a test could have configured differently."""
    response = httpx.get(
        f"{base_url}/files", params={"path": "C:/Windows" if os.name == "nt" else "/etc"},
        timeout=30,
    )

    assert response.status_code in (400, 403)
    assert "ALLOWED_PATHS" in response.text


def test_verification_refuses_an_unknown_runner(base_url, live_server):
    _, allowed = live_server
    response = httpx.post(
        f"{base_url}/verification/run",
        json={"repo_path": str(allowed), "runner": "rm -rf /"},
        timeout=30,
    )

    assert response.status_code == 400
    assert "Unknown runner" in response.text
