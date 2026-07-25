"""The hermes-ollama-cmd Telegram plugin, tested with a fake ctx.

This file closes a blind spot that cost three bugs in one day. The plugin
runs inside Hermes Agent's process, not this one, so nothing in the suite
touched it — and every failure it produced looked like success:

  - `/attente` said "rien en attente" while an approval was queued,
    because approvals_list was missing from the MCP include list.
  - Then it said the same thing again, because dispatch_tool returns a
    JSON *string* and a single record arrives unwrapped, not as a
    one-element list.
  - Then it failed on {"result": "<json string>"} — double-encoded, the
    envelope's value being JSON text rather than a list.

None of those raised. All three answered confidently and wrongly, which
is the worst failure mode for a security queue.

The plugin only needs a `ctx` exposing `dispatch_tool` and
`register_command`, so a fake is enough — no Hermes Agent required. What
matters is that every serialisation shape FastMCP actually produced is
represented below, including the ones that broke it.
"""
from __future__ import annotations

import importlib.util
import json
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


class FakeCtx:
    """Records dispatch_tool calls and replays a scripted response."""

    def __init__(self, response=None, responses=None):
        self._response = response
        self._responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    def dispatch_tool(self, name, args, **kwargs):
        self.calls.append((name, args))
        if name in self._responses:
            return self._responses[name]
        return self._response

    def register_command(self, name, handler, description=""):
        self.calls.append(("register_command", {"name": name}))


# ── every shape FastMCP was observed to produce ──────────────────────
@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("bare list", [_entry()]),
        ("result envelope", {"result": [_entry()]}),
        # The shape that broke it in production: envelope whose value is
        # JSON *text*, holding a single object rather than a list.
        ("double-encoded object", {"result": json.dumps(_entry())}),
        ("double-encoded list", {"result": json.dumps([_entry()])}),
        ("lone object as JSON", json.dumps(_entry())),
        ("json string of envelope", json.dumps({"result": [_entry()]})),
    ],
)
def test_attente_reads_every_observed_shape(cmd, label, payload):
    ctx = FakeCtx(payload)

    output = cmd.handle_attente(ctx, "")

    assert "1 action(s) en attente" in output, f"{label} not understood"
    assert "Run ruff (lint)" in output
    # The reason Aegis gave must be shown: approving without it is
    # rubber-stamping, and a phone screen is where that temptation peaks.
    assert "autonomy level 'high'" in output


@pytest.mark.parametrize("payload", [[], "[]", {"result": []}, {"result": "[]"}])
def test_a_genuinely_empty_queue_says_so(cmd, payload):
    assert "Rien en attente" in cmd.handle_attente(FakeCtx(payload), "")


@pytest.mark.parametrize("payload", ["pas du json", None, 42, {"unexpected": "shape"}])
def test_unreadable_answers_never_masquerade_as_empty(cmd, payload):
    """The core lesson of the day: "I could not read this" must never be
    reported as "there is nothing"."""
    output = cmd.handle_attente(FakeCtx(payload), "")

    assert "Impossible de lire" in output
    assert "Rien en attente" not in output
    # And it must say what to check, not just that something went wrong.
    assert "include" in output


# ── ordering, because indices are what the user types ────────────────
def test_queue_is_ordered_oldest_first(cmd):
    """Newest-first would renumber the whole list every time a refusal
    arrives, so /ok 1 could approve something the user never read."""
    old = _entry(id="aaa", description="ANCIENNE", created_at="2026-07-25T10:00:00")
    new = _entry(id="bbb", description="RECENTE", created_at="2026-07-25T18:00:00")

    output = cmd.handle_attente(FakeCtx([new, old]), "")

    assert output.index("ANCIENNE") < output.index("RECENTE")


# ── deciding ─────────────────────────────────────────────────────────
def test_ok_approves_the_numbered_entry(cmd):
    entry = _entry()
    ctx = FakeCtx(
        responses={
            "mcp__hermes_ollama__approvals_list": [entry],
            "mcp__hermes_ollama__approvals_decide": {"status": "approved"},
        }
    )

    output = cmd.handle_ok(ctx, "1")

    decided = [c for c in ctx.calls if c[0] == "mcp__hermes_ollama__approvals_decide"]
    assert decided == [("mcp__hermes_ollama__approvals_decide",
                        {"approval_id": entry["id"], "approved": True})]
    # Echoing the description back is what makes a shifted queue visible.
    assert "Run ruff (lint)" in output
    assert "une seule fois" in output


def test_non_refuses(cmd):
    entry = _entry()
    ctx = FakeCtx(
        responses={
            "mcp__hermes_ollama__approvals_list": [entry],
            "mcp__hermes_ollama__approvals_decide": {"status": "refused"},
        }
    )

    output = cmd.handle_non(ctx, "1")

    assert ("mcp__hermes_ollama__approvals_decide",
            {"approval_id": entry["id"], "approved": False}) in ctx.calls
    assert "Refusé" in output


def test_an_id_prefix_works_too(cmd):
    entry = _entry()
    ctx = FakeCtx(
        responses={
            "mcp__hermes_ollama__approvals_list": [entry],
            "mcp__hermes_ollama__approvals_decide": {},
        }
    )

    cmd.handle_ok(ctx, "8eadb0a6")

    assert any(c[1].get("approval_id") == entry["id"] for c in ctx.calls if c[0].endswith("decide"))


@pytest.mark.parametrize("token", ["", "9", "0", "zzzz"])
def test_a_bad_selector_decides_nothing(cmd, token):
    """Silently approving the wrong entry would be a security bug, so an
    unresolvable selector must decide nothing at all."""
    ctx = FakeCtx(
        responses={
            "mcp__hermes_ollama__approvals_list": [_entry()],
            "mcp__hermes_ollama__approvals_decide": {},
        }
    )

    output = cmd.handle_ok(ctx, token)

    assert not [c for c in ctx.calls if c[0].endswith("approvals_decide")]
    assert "Usage" in output


def test_an_ambiguous_id_prefix_decides_nothing(cmd):
    ctx = FakeCtx(
        responses={
            "mcp__hermes_ollama__approvals_list": [
                _entry(id="ab111"), _entry(id="ab222")
            ],
            "mcp__hermes_ollama__approvals_decide": {},
        }
    )

    cmd.handle_ok(ctx, "ab")

    assert not [c for c in ctx.calls if c[0].endswith("approvals_decide")]


def test_deciding_on_an_unreadable_queue_decides_nothing(cmd):
    ctx = FakeCtx("pas du json")

    output = cmd.handle_ok(ctx, "1")

    assert not [c for c in ctx.calls if c[0].endswith("approvals_decide")]
    assert "Impossible de lire" in output


# ── /tache, and the registration surface ─────────────────────────────
def test_tache_creates_a_task(cmd):
    ctx = FakeCtx({"id": "task-1", "title": "Faire le café"})

    output = cmd.handle_tache(ctx, "Faire le café")

    assert ("mcp__hermes_ollama__tasks_create", {"title": "Faire le café"}) in ctx.calls
    assert "task-1" in output


def test_tache_without_a_title_calls_nothing(cmd):
    ctx = FakeCtx({})

    assert "Usage" in cmd.handle_tache(ctx, "   ")
    assert not [c for c in ctx.calls if c[0].startswith("mcp__")]


def test_every_command_is_registered(cmd):
    ctx = FakeCtx()

    cmd.register(ctx)

    registered = {c[1]["name"] for c in ctx.calls if c[0] == "register_command"}
    assert registered == {"tache", "attente", "ok", "non"}
