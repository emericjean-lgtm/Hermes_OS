"""RealTaskExecutor (execution/task_executor.py) — no pre-existing test
file covered this class at all before the Workspace/Filesystem tool
layer's Mission integration; these tests cover both the untouched
baseline behavior (no workspace_project_for, or one that resolves
nothing — must behave exactly as before) and the new real, Aegis-gated
tool-calling loop (workspace_project_for resolves a validated Project).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError


@dataclass
class _FakeTask:
    task_id: str = "task-1"
    title: str = "Do the thing"
    mission_id: str = ""
    assigned_agent: str = ""
    # HOS-085: "" resolves to the "hermes-agent" runtime, which owns its own
    # tool loop. The tests below that exercise Hermes OS's *own* local tool
    # loop therefore pin this to "ollama" explicitly — that loop is now the
    # local-Ollama path only, not what a default mission does.
    assigned_runtime: str = ""
    assigned_skills: list = field(default_factory=list)
    assigned_tools: list = field(default_factory=list)
    retries: int = 0


class _FakeChatResponse:
    def __init__(self, content: str, metadata: dict | None = None):
        self.content = content
        self.metadata = metadata or {}


# ── Baseline: unchanged behavior when no workspace is resolved ─────


@pytest.mark.asyncio
async def test_execute_without_workspace_project_for_uses_plain_chat():
    async def fake_chat(*, messages, model, num_ctx=None):
        return _FakeChatResponse("plain answer", {"model": model})

    executor = RealTaskExecutor(chat=fake_chat, default_model="test-model")
    outcome = executor.execute(_FakeTask())

    assert outcome.result == "plain answer"
    assert outcome.model == "test-model"


@pytest.mark.asyncio
async def test_execute_with_workspace_resolver_returning_none_uses_plain_chat():
    calls = []

    async def fake_chat(*, messages, model, num_ctx=None):
        calls.append(messages)
        return _FakeChatResponse("plain answer")

    executor = RealTaskExecutor(
        chat=fake_chat, workspace_project_for=lambda task: None,
    )
    outcome = executor.execute(_FakeTask())

    assert outcome.result == "plain answer"
    # No workspace paragraph leaked into the prompt when nothing resolved.
    assert not any("filesystem access" in m.get("content", "") for m in calls[0])


def test_resolve_workspace_swallows_resolver_exceptions():
    def broken_resolver(task):
        raise RuntimeError("boom")

    executor = RealTaskExecutor(workspace_project_for=broken_resolver)
    assert executor._resolve_workspace(_FakeTask()) is None  # noqa: SLF001


def test_resolve_workspace_returns_resolver_result():
    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", "C:\\ws"),
    )
    assert executor._resolve_workspace(_FakeTask()) == ("proj-1", "C:\\ws")  # noqa: SLF001


# ── _build_messages: workspace context paragraph ────────────────


def test_build_messages_without_workspace_has_no_filesystem_mention():
    messages = RealTaskExecutor()._build_messages(_FakeTask(), None)  # noqa: SLF001
    assert not any("filesystem access" in m["content"] for m in messages)


def test_build_messages_with_workspace_mentions_real_tools_and_root():
    messages = RealTaskExecutor()._build_messages(  # noqa: SLF001
        _FakeTask(), None, ("proj-1", "C:\\Users\\emeri\\Skill360 Industry"),
    )
    system = messages[0]["content"]
    assert "workspace_read" in system
    assert "Skill360 Industry" in system


# ── Cloud path: tool-calling is intentionally skipped ────────────


@pytest.mark.asyncio
async def test_execute_uses_plain_cloud_chat_even_with_workspace_resolved():
    """Tool-calling is scoped to local execution only (module docstring)
    — a resolved workspace must not change cloud behavior."""
    local_calls = []
    cloud_calls = []

    async def fake_chat(*, messages, model, num_ctx=None):
        local_calls.append(1)
        return _FakeChatResponse("should not be used")

    # `racines` (HOS-227) : le contrat d'un chat **cloud** les porte,
    # parce que le pare-feu de données en a besoin pour masquer une
    # racine de workspace en entier. Absorbées ici : ce test mesure le
    # choix du chemin, pas le caviardage.
    async def fake_cloud_chat(*, messages, model, num_ctx=None, **_):
        cloud_calls.append(1)
        return _FakeChatResponse("cloud answer")

    executor = RealTaskExecutor(
        chat=fake_chat,
        cloud_chat=fake_cloud_chat,
        runtime_for=lambda task: "openrouter",
        workspace_project_for=lambda task: ("proj-1", "C:\\ws"),
    )
    outcome = executor.execute(_FakeTask())

    assert outcome.result == "cloud answer"
    assert cloud_calls == [1]
    assert local_calls == []


# ── Real tool-calling loop, against a real temp workspace + Aegis ──


class _ScriptedStreamChunk:
    def __init__(self, kind, text="", tool_calls=None):
        self.kind = kind
        self.text = text
        self.tool_calls = tool_calls


class _FakeOllamaClientForToolLoop:
    """Scripted: first chat_events() call asks for a workspace_read tool
    call; second call (after the real tool result is fed back) answers
    with the file's real content quoted back — proving the loop actually
    round-trips a real tool result, not a canned string."""

    instances: list = []

    def __init__(self, *args, **kwargs):
        self.round = 0
        self.seen_messages: list = []
        _FakeOllamaClientForToolLoop.instances.append(self)

    def chat_events(self, model, messages, **kwargs):
        self.seen_messages.append(list(messages))
        self.round += 1
        current_round = self.round

        async def _gen():
            if current_round == 1:
                yield _ScriptedStreamChunk(
                    "tool_calls", tool_calls=[
                        {"function": {"name": "workspace_read", "arguments": {"path": "AGENTS.md"}}},
                    ],
                )
            else:
                last_tool_msg = next(
                    m for m in reversed(messages) if m.get("role") == "tool"
                )
                yield _ScriptedStreamChunk(
                    "content", text=f"The file says: {last_tool_msg['content']}",
                )
        return _gen()

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_tool_loop_reads_real_file_and_returns_real_content(
    monkeypatch, tmp_path, security_config,
):
    """End-to-end for the loop itself: a real workspace, a real Aegis
    check (validated Project, no project_id narrowing needed since the
    dynamic whitelist widens for it), a real file_tools.read_file call —
    only the Ollama transport is faked, and even that is scripted to
    prove the real tool result (not a guess) flows back into the
    model's next turn."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    # Aegis (reached via workspace_chat_tools._aegis()) is resolved through
    # the process-wide get_agent_registry() lru_cache singleton. If that
    # singleton's first-ever construction in this process happened while
    # OllamaClient below is monkeypatched, the fake would get baked into
    # the cached registry forever, breaking unrelated tests later in the
    # same session. Force a real warm-up first so the monkeypatch below
    # can never poison it.
    get_agent_registry()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated"))
    (tmp_path / "_unrelated").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Real agent instructions.")
    project = get_project_store().create(name="ws", root_path=str(workspace))
    get_project_store().validate(project.id)

    _FakeOllamaClientForToolLoop.instances.clear()
    monkeypatch.setattr(
        "backend.connectors.ollama_client.OllamaClient", _FakeOllamaClientForToolLoop,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: (project.id, str(workspace)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-1", assigned_runtime="ollama"))

    assert "Real agent instructions." in outcome.result
    assert outcome.metadata.get("tool_calls_made") == 1

    get_settings.cache_clear()
    get_project_store.cache_clear()


@pytest.mark.asyncio
async def test_tool_loop_reports_aegis_refusal_without_fabricating_success(
    monkeypatch, tmp_path,
):
    """The workspace resolver can, in principle, hand back a path the
    dynamic whitelist doesn't actually cover (e.g. a race with
    archival) — the loop must relay Aegis's real refusal as the tool
    result, never silently invent a successful read."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    # See test_tool_loop_reads_real_file_and_returns_real_content for why
    # this warm-up must happen before the OllamaClient monkeypatch below.
    get_agent_registry()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated"))
    (tmp_path / "_unrelated").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()

    outside = tmp_path / "never_registered"
    outside.mkdir()

    _FakeOllamaClientForToolLoop.instances.clear()
    monkeypatch.setattr(
        "backend.connectors.ollama_client.OllamaClient", _FakeOllamaClientForToolLoop,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("not-a-real-project", str(outside)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-2", assigned_runtime="ollama"))

    assert "Refusé par Aegis" in outcome.result or "refusé" in outcome.result.lower()

    get_settings.cache_clear()
    get_project_store.cache_clear()


@pytest.mark.asyncio
async def test_tool_loop_bounded_rounds_forces_final_answer(monkeypatch, tmp_path):
    """A model that keeps asking for tools without ever answering must
    still terminate with a real, if forced, answer rather than hang."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    # See test_tool_loop_reads_real_file_and_returns_real_content for why
    # this warm-up must happen before the OllamaClient monkeypatch below.
    get_agent_registry()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated"))
    (tmp_path / "_unrelated").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()

    workspace = tmp_path / "ws"
    workspace.mkdir()
    project = get_project_store().create(name="ws", root_path=str(workspace))
    get_project_store().validate(project.id)

    class _NeverStopsClient:
        def __init__(self, *a, **kw):
            self.calls = 0

        def chat_events(self, model, messages, **kwargs):
            self.calls += 1
            forced = self.calls > 3  # beyond _MAX_TOOL_ROUNDS

            async def _gen():
                if forced:
                    yield _ScriptedStreamChunk("content", text="forced final answer")
                else:
                    yield _ScriptedStreamChunk(
                        "tool_calls", tool_calls=[
                            {"function": {"name": "workspace_exists", "arguments": {"path": "."}}},
                        ],
                    )
            return _gen()

        async def aclose(self):
            pass

    monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient", _NeverStopsClient)

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: (project.id, str(workspace)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-3", assigned_runtime="ollama"))

    assert outcome.result == "forced final answer"

    get_settings.cache_clear()
    get_project_store.cache_clear()
