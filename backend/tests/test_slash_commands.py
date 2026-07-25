"""The hermes-ollama-cmd Telegram plugin.

This file closes a blind spot that cost three bugs in one day. The plugin
runs inside Hermes Agent's process, so nothing in the suite ever imported
it — and every failure it produced looked like success: "rien en attente"
while an approval was queued, twice for different reasons.

The plugin now talks HTTP to the backend rather than going through
dispatch_tool (see its docstring for why: the MCP tool budget is sized
for the *model*, and slash commands never involve one). So the fake here
patches urllib at the plugin's own module level, which keeps these tests
fast and offline while still exercising the real request-building and
response-handling code.
"""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

PLUGIN = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "hermes_agent_plugins"
    / "hermes-ollama-cmd"
    / "__init__.py"
)


@pytest.fixture(scope="module")
def cmd():
    spec = importlib.util.spec_from_file_location("hermes_ollama_cmd", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def http(cmd, monkeypatch):
    """Scripted backend: maps "METHOD /path" to a response (or an
    exception to raise). Records every call so a test can assert that a
    decision really was — or really was not — sent."""

    class Recorder:
        def __init__(self):
            self.routes: dict[str, object] = {}
            self.calls: list[tuple[str, str, object]] = []

        def route(self, key, value):
            self.routes[key] = value
            return self

        def _handle(self, method, path, body=None):
            self.calls.append((method, path, body))
            key = f"{method} {path}"
            if key not in self.routes:
                raise AssertionError(f"unscripted call: {key}")
            value = self.routes[key]
            if isinstance(value, Exception):
                raise value
            return value

        @property
        def posted(self):
            return [c for c in self.calls if c[0] == "POST"]

    recorder = Recorder()
    monkeypatch.setattr(cmd, "_request", recorder._handle)
    return recorder


def _entry(**overrides):
    entry = {
        "id": "8eadb0a6-7091-4347-886b-1c26fc3c20b4",
        "action_type": "verification_run",
        "description": "Run ruff (lint) in C:/repo",
        "reason": "needs autonomy level 'high'; current level is 'low'.",
        "requesting_agent": "veritas",
        "created_at": "2026-07-25T17:20:10",
    }
    entry.update(overrides)
    return entry


PENDING = "GET /security/approvals?status=pending"


# ── /attente ─────────────────────────────────────────────────────────
def test_attente_lists_the_queue(cmd, http):
    http.route(PENDING, [_entry()])

    output = cmd.handle_attente("")

    assert "1 action(s) en attente" in output
    assert "Run ruff (lint)" in output
    # The reason Aegis gave must be shown: approving without it is
    # rubber-stamping, and a phone screen is where that temptation peaks.
    assert "autonomy level 'high'" in output


def test_empty_queue_says_so(cmd, http):
    http.route(PENDING, [])

    assert "Rien en attente" in cmd.handle_attente("")


def test_backend_down_is_never_reported_as_an_empty_queue(cmd, http):
    """The lesson that cost three bugs: "I could not read this" must
    never render as "there is nothing"."""
    http.route(PENDING, cmd.BackendError("backend injoignable sur http://127.0.0.1:8000"))

    output = cmd.handle_attente("")

    assert "Échec" in output
    assert "Rien en attente" not in output
    assert "injoignable" in output


def test_queue_is_ordered_oldest_first(cmd, http):
    """Newest-first would renumber the list whenever a refusal arrives,
    so /ok 1 could approve something the user never read."""
    http.route(PENDING, [
        _entry(id="bbb", description="RECENTE", created_at="2026-07-25T18:00:00"),
        _entry(id="aaa", description="ANCIENNE", created_at="2026-07-25T10:00:00"),
    ])

    output = cmd.handle_attente("")

    assert output.index("ANCIENNE") < output.index("RECENTE")


# ── /ok and /non ─────────────────────────────────────────────────────
def test_ok_approves_the_numbered_entry(cmd, http):
    entry = _entry()
    http.route(PENDING, [entry]).route(
        f"POST /security/approvals/{entry['id']}", {"status": "approved"}
    )

    output = cmd.handle_ok("1")

    assert http.posted == [("POST", f"/security/approvals/{entry['id']}", {"approved": True})]
    # Echoing the description back is what makes a shifted queue visible.
    assert "Run ruff (lint)" in output
    assert "une seule fois" in output


def test_non_refuses(cmd, http):
    entry = _entry()
    http.route(PENDING, [entry]).route(
        f"POST /security/approvals/{entry['id']}", {"status": "refused"}
    )

    output = cmd.handle_non("1")

    assert http.posted[0][2] == {"approved": False}
    assert "Refusé" in output


def test_an_id_prefix_works_too(cmd, http):
    entry = _entry()
    http.route(PENDING, [entry]).route(f"POST /security/approvals/{entry['id']}", {})

    cmd.handle_ok("8eadb0a6")

    assert http.posted


@pytest.mark.parametrize("token", ["", "9", "0", "zzzz"])
def test_a_bad_selector_decides_nothing(cmd, http, token):
    """Silently approving the wrong entry would be a security bug, so an
    unresolvable selector must decide nothing at all."""
    http.route(PENDING, [_entry()])

    output = cmd.handle_ok(token)

    assert not http.posted
    assert "Usage" in output


def test_an_ambiguous_id_prefix_decides_nothing(cmd, http):
    http.route(PENDING, [_entry(id="ab111"), _entry(id="ab222")])

    cmd.handle_ok("ab")

    assert not http.posted


def test_deciding_when_the_backend_is_down_decides_nothing(cmd, http):
    http.route(PENDING, cmd.BackendError("injoignable"))

    output = cmd.handle_ok("1")

    assert not http.posted
    assert "Échec" in output


# ── /tache ───────────────────────────────────────────────────────────
def test_tache_creates_a_task(cmd, http):
    http.route("POST /tasks", {"id": "task-1234", "title": "Faire le café"})

    output = cmd.handle_tache("Faire le café")

    assert http.posted == [("POST", "/tasks", {"title": "Faire le café"})]
    assert "task-123" in output


def test_tache_without_a_title_calls_nothing(cmd, http):
    assert "Usage" in cmd.handle_tache("   ")
    assert not http.calls


# ── /projet ──────────────────────────────────────────────────────────
def test_projet_without_argument_lists(cmd, http):
    http.route("GET /projects", [{"id": "p1234567", "name": "Alpha", "status": "active"}])

    output = cmd.handle_projet("")

    assert "Alpha" in output and "active" in output
    assert not http.posted  # listing must never create


def test_projet_with_a_name_creates(cmd, http):
    http.route("POST /projects", {"id": "p9999999", "name": "Beta"})

    output = cmd.handle_projet("Beta")

    assert http.posted == [("POST", "/projects", {"name": "Beta"})]
    assert "Beta" in output


def test_projet_reports_an_empty_list_usefully(cmd, http):
    http.route("GET /projects", [])

    assert "Aucun projet" in cmd.handle_projet("")


# ── /verif ───────────────────────────────────────────────────────────
def test_verif_without_argument_lists_the_whitelist(cmd, http):
    """The whitelist is the only discovery surface — there is no way to
    pass a command through, so listing it is how a user learns what runs."""
    http.route("GET /verification/runners", [
        {"name": "pytest", "kind": "test", "description": ""},
        {"name": "ruff", "kind": "lint", "description": ""},
    ])

    output = cmd.handle_verif("")

    assert "pytest" in output and "ruff" in output
    assert not http.posted


def test_verif_runs_and_reports_success(cmd, http):
    http.route("POST /verification/run", {
        "ran": True, "passed": True, "exit_code": 0,
        "duration_seconds": 1.2, "output": "5 passed", "verdict": "allow", "reason": "",
    })

    output = cmd.handle_verif("pytest")

    assert "réussi" in output
    assert "5 passed" in output


def test_verif_reports_a_failure_as_a_result_not_an_error(cmd, http):
    http.route("POST /verification/run", {
        "ran": True, "passed": False, "exit_code": 1,
        "duration_seconds": 0.4, "output": "1 failed, 4 passed",
        "verdict": "allow", "reason": "",
    })

    output = cmd.handle_verif("pytest")

    assert "échoué" in output
    assert "1 failed" in output


def test_verif_pending_validation_points_at_the_unblocking_command(cmd, http):
    """At the shipped autonomy level this is the *expected* outcome, so it
    must not read as a malfunction."""
    http.route("POST /verification/run", {
        "ran": False, "passed": False, "exit_code": None, "duration_seconds": 0.0,
        "output": "", "verdict": "require_human_validation",
        "reason": "verification_run needs autonomy level 'high'",
    })

    output = cmd.handle_verif("ruff")

    assert "en attente de ta validation" in output
    assert "/attente" in output and "/ok" in output


def test_verif_uses_the_default_repo_when_none_given(cmd, http):
    http.route("POST /verification/run", {
        "ran": True, "passed": True, "exit_code": 0,
        "duration_seconds": 0.1, "output": "", "verdict": "allow", "reason": "",
    })

    cmd.handle_verif("ruff")

    assert http.posted[0][2]["repo_path"] == cmd.DEFAULT_REPO


def test_verif_accepts_an_explicit_path(cmd, http):
    http.route("POST /verification/run", {
        "ran": True, "passed": True, "exit_code": 0,
        "duration_seconds": 0.1, "output": "", "verdict": "allow", "reason": "",
    })

    cmd.handle_verif("ruff C:/autre/depot")

    assert http.posted[0][2]["repo_path"] == "C:/autre/depot"


# ── /statut ──────────────────────────────────────────────────────────
def _statut_routes(http, pending=()):
    return (
        http.route("GET /system/status", {
            "gpu": {"vram_used_gb": 1.4, "vram_total_gb": 17.2},
            "ram_used_gb": 9.8, "ram_total_gb": 33.3, "cpu_load_pct": 12, "alerts": [],
        })
        .route("GET /system/models", {"loaded_count": 1, "always_loaded_count": 2})
        .route("GET /tasks", [{"status": "todo"}, {"status": "todo"}, {"status": "done"}])
        .route(PENDING, list(pending))
    )


def test_statut_summarises(cmd, http):
    _statut_routes(http)

    output = cmd.handle_statut("")

    assert "1.4 / 17.2 GB" in output
    assert "todo: 2" in output and "done: 1" in output
    assert "épinglés 2" in output


def test_statut_flags_pending_validations(cmd, http):
    _statut_routes(http, pending=[_entry()])

    output = cmd.handle_statut("")

    assert "1 action(s) attendent ta validation" in output
    assert "/attente" in output


def test_statut_surfaces_alerts(cmd, http):
    _statut_routes(http)
    http.routes["GET /system/status"]["alerts"] = ["VRAM presque pleine"]

    assert "VRAM presque pleine" in cmd.handle_statut("")


# ── error handling shared by every command ───────────────────────────
@pytest.mark.parametrize(
    ("handler", "arg", "route"),
    [
        ("handle_tache", "x", "POST /tasks"),
        ("handle_projet", "", "GET /projects"),
        ("handle_verif", "", "GET /verification/runners"),
        ("handle_statut", "", "GET /system/status"),
        ("handle_attente", "", PENDING),
    ],
)
def test_every_command_survives_a_dead_backend(cmd, http, handler, arg, route):
    http.route(route, cmd.BackendError("backend injoignable"))

    output = getattr(cmd, handler)(arg)

    assert "Échec" in output
    assert "injoignable" in output


def test_http_error_detail_is_surfaced(cmd, monkeypatch):
    """A 400 from the backend carries the reason — showing it beats a
    generic failure message."""
    def raise_http_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://x", 400, "Bad Request", {},
            __import__("io").BytesIO(json.dumps({"detail": "Unknown runner 'nope'"}).encode()),
        )

    monkeypatch.setattr(cmd.urllib.request, "urlopen", raise_http_error)

    assert "Unknown runner" in cmd.handle_verif("nope")


def test_every_command_is_registered(cmd):
    registered = []

    class Ctx:
        def register_command(self, name, handler, description=""):
            registered.append(name)

    cmd.register(Ctx())

    assert set(registered) == {"tache", "projet", "verif", "statut", "attente", "ok", "non"}
