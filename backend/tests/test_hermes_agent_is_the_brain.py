"""Anti-regression guards: Hermes Agent must remain the mission brain (HOS-085).

These exist because the opposite silently happened once. HOS-084 gave
RealTaskExecutor its own workspace tool-calling loop, and that loop was
assigned *after* the Hermes Agent branch in ``execute()``:

    if runtime_id == "hermes-agent" and self._chat is None and not use_cloud:
        chat = self._hermes_agent_chat          # Hermes Agent selected
    if workspace is not None and not use_cloud:
        chat = self._chat_with_tools_for(...)   # ...and immediately replaced

So every workspace-bound mission — the normal production path — ran Hermes
OS's own agentic loop against Ollama while reporting success, and nothing in
the suite noticed: the tool-loop tests asserted the loop worked, never that
it was the thing that *should* have run. The live Mission Center reported
``Runtimes: ollama`` for a mission that was supposed to be driven by Hermes.

The guards below assert the routing decision itself, not just that some
tool loop functions.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import RealTaskExecutor
from backend.tests.test_real_task_executor import _FakeChatResponse, _FakeTask


class _RecordingHermesAgentRuntime:
    """Stands in for the installed Hermes Agent CLI, recording what it got."""

    last_ctx: dict | None = None
    started = False

    def __init__(self, config=None):
        type(self).config = config

    async def start(self) -> None:
        type(self).started = True

    def get(self, capability_name: str):
        if capability_name != "chat":
            return None
        return self

    async def chat(self, messages, *, runtime_ctx=None):
        type(self).last_ctx = runtime_ctx
        return _FakeChatResponse("done", {"provider": "hermes-agent"})


def _forbid_ollama(monkeypatch) -> None:
    """Any construction of OllamaClient here means Hermes OS started doing
    the agentic work itself again — the exact regression this file guards."""

    def _boom(*args, **kwargs):
        raise AssertionError(
            "REGRESSION: Hermes OS ran its own Ollama tool loop for a "
            "hermes-agent mission. Hermes Agent must own tool selection and "
            "execution (it reaches this backend's tools over MCP)."
        )

    monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient", _boom)


@pytest.fixture
def hermes_agent(monkeypatch):
    _RecordingHermesAgentRuntime.last_ctx = None
    _RecordingHermesAgentRuntime.started = False
    monkeypatch.setattr(
        "backend.ral.adapters.hermes_agent_cli.HermesAgentCliRuntime",
        _RecordingHermesAgentRuntime,
    )
    return _RecordingHermesAgentRuntime


def test_workspace_bound_mission_is_executed_by_hermes_agent(
    hermes_agent, monkeypatch, tmp_path,
):
    """The regression itself: a mission bound to a validated Project must
    reach Hermes Agent, not Hermes OS's own tool loop."""
    _forbid_ollama(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-1"))

    assert hermes_agent.started, "Hermes Agent runtime was never started"
    ctx = hermes_agent.last_ctx
    assert ctx is not None, "Hermes Agent was never asked to run the task"
    # The bound Project root is what Hermes Agent works in — Hermes OS
    # supplies the workspace, Hermes decides what to do inside it.
    assert ctx["workspace"] == str(workspace)
    assert ctx["project_id"] == "proj-1"
    assert ctx["mission_id"] == "m-1"
    assert outcome.metadata.get("provider") == "hermes-agent"


def test_unbound_mission_never_gets_the_hermes_os_source_tree(
    hermes_agent, monkeypatch,
):
    """HermesAgentCliConfig falls back to os.getcwd() when handed no
    workspace, and the backend's cwd is the Hermes OS checkout — that would
    give Hermes Agent write access to the codebase running it. A mission
    with no bound Project must get an empty scratch directory instead."""
    _forbid_ollama(monkeypatch)
    import os

    executor = RealTaskExecutor(workspace_project_for=lambda task: None)
    executor.execute(_FakeTask(mission_id="m-unbound"))

    workspace = hermes_agent.last_ctx["workspace"]
    assert workspace, "Hermes Agent must always be given an explicit workspace"
    assert os.path.isdir(workspace)
    assert os.path.realpath(workspace) != os.path.realpath(os.getcwd())
    assert not os.path.samefile(workspace, os.getcwd())


def test_hermes_agent_is_given_tools(hermes_agent, monkeypatch, tmp_path):
    """Verified live: with no toolset Hermes Agent starts at "0 tools · 0
    skills" and merely narrates the work ("Creating the file...") while
    nothing touches the disk. The adapter only passes --toolsets when Hermes
    OS supplies one, so an empty list here silently produces an agent that
    cannot act."""
    _forbid_ollama(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
    )
    executor.execute(_FakeTask(mission_id="m-1"))

    toolsets = hermes_agent.last_ctx.get("toolsets")
    assert toolsets, "Hermes Agent was given no toolsets — it can only narrate"
    assert "coding" in toolsets


def test_task_prompt_carries_the_mission_objective(hermes_agent, monkeypatch, tmp_path):
    """A decomposed node title is not a task. TaskDecomposer emits titles
    like "Create test file" with an empty description, so without the
    Mission objective the agent is told to create a file with no name and
    no content — which is exactly how a mission reached 4/4 "completed"
    while nothing was written to disk."""
    _forbid_ollama(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    objective = "Create HERMES_OS_INTEGRATION_TEST.md with three lines."
    seen: dict = {}

    class _CapturingRuntime(_RecordingHermesAgentRuntime):
        async def chat(self, messages, *, runtime_ctx=None):
            seen["messages"] = messages
            return await super().chat(messages, runtime_ctx=runtime_ctx)

    monkeypatch.setattr(
        "backend.ral.adapters.hermes_agent_cli.HermesAgentCliRuntime", _CapturingRuntime,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
        mission_brief_for=lambda task: objective,
    )
    executor.execute(_FakeTask(mission_id="m-1", title="Create test file"))

    user_turn = [m for m in seen["messages"] if m["role"] == "user"][0]["content"]
    assert objective in user_turn, "the real requirement never reached the agent"
    assert "Create test file" in user_turn


def test_agentic_model_floor(monkeypatch, tmp_path):
    """Measured on this deployment: same prompt, same "coding" toolset, same
    workspace — devstral wrote the file, qwen3.5:2b wrote nothing and
    narrated. ModelRouter optimises a single completion for VRAM/latency and
    picks the 2B model for a short node title, so without this floor the
    whole integration routes correctly and still accomplishes nothing."""
    executor = RealTaskExecutor()
    assert executor._agentic_model("qwen3.5:2b") == "devstral"  # noqa: SLF001
    assert executor._agentic_model("") == "devstral"  # noqa: SLF001
    # A capable pick is left alone — this is a floor, not a hard-coded model.
    assert executor._agentic_model("devstral:latest") == "devstral:latest"  # noqa: SLF001
    assert executor._agentic_model("qwen3-coder:30b") == "qwen3-coder:30b"  # noqa: SLF001


def test_per_task_context_is_not_shared_state(hermes_agent, monkeypatch, tmp_path):
    """Two tasks executed through the same executor must not leak each
    other's workspace. The first implementation stashed this on ``self``,
    which MissionExecutor's concurrent execution would have raced."""
    _forbid_ollama(monkeypatch)
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    roots = {"t-a": ("p-a", str(ws_a)), "t-b": ("p-b", str(ws_b))}

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: roots[task.task_id],
    )

    executor.execute(_FakeTask(task_id="t-a", mission_id="m-a"))
    assert hermes_agent.last_ctx["workspace"] == str(ws_a)
    executor.execute(_FakeTask(task_id="t-b", mission_id="m-b"))
    assert hermes_agent.last_ctx["workspace"] == str(ws_b)


def test_explicit_ollama_runtime_still_gets_hermes_os_tools(monkeypatch, tmp_path):
    """The local-Ollama runtime has no agent of its own, so Hermes OS's tool
    loop remains correct *there* — this guard documents that the HOS-085 fix
    narrowed that loop rather than deleting it."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    constructed: list[str] = []

    class _StubOllama:
        def __init__(self, *args, **kwargs):
            constructed.append("yes")
            raise RuntimeError("stop here — construction is what we assert")

    monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient", _StubOllama)

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
    )
    with pytest.raises(Exception):
        executor.execute(_FakeTask(mission_id="m-1", assigned_runtime="ollama"))

    assert constructed, "explicit ollama runtime should still use the HOS tool loop"
