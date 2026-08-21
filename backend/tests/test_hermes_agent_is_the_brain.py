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
            "HERMES_AGENT_BYPASS_DETECTED: Hermes OS ran its own Ollama tool "
            "loop for a hermes-agent mission. Hermes Agent must own tool "
            "selection and execution (it reaches this backend's tools over "
            "MCP). See HOS-085."
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


def test_agentic_model_floor():
    """ModelRouter optimises a single completion for VRAM and latency, so it
    picks a 2B model for a short node title — without this floor the whole
    integration routes correctly to Hermes Agent and still accomplishes
    nothing, because that model narrates instead of calling tools.

    Asserts the *policy*, not which model currently wins it: capable through,
    incapable and unknown substituted. The fallback itself comes from
    measured probe data (HOS-095) and already moved from devstral to
    qwen3.5:9b-128k the first time real numbers arrived — a test naming the
    model would break on every honest re-measurement."""
    from backend.execution.task_executor import _HERMES_AGENT_FALLBACK_MODEL as FALLBACK

    capable = {"a-capable-model:9b": True, "qwen3.5:2b": False}
    executor = RealTaskExecutor(agentic_capable_for=capable.get)

    assert executor._agentic_model("a-capable-model:9b") == "a-capable-model:9b"  # noqa: SLF001
    assert executor._agentic_model("qwen3.5:2b") == FALLBACK  # noqa: SLF001
    # Unknown is not treated as capable: an unprobeable model that cannot
    # call tools yields a mission that reports success and does nothing.
    assert executor._agentic_model("something-new:8b") == FALLBACK  # noqa: SLF001
    assert executor._agentic_model("") == FALLBACK  # noqa: SLF001


def test_agentic_capability_is_measured_not_named():
    """Only a measurement qualifies a model; structure can only disqualify.

    Every structural signal was tried and refuted by the next measurement
    (HOS-096, three trials each): parameter count inverts — lfm2.5-2.6b
    passes 3/3 while gemma4:12b fails 0/3 — a "tools" declaration is made
    even by qwen3-embedding:0.6b, and neither 64k of served context nor
    fitting in VRAM saved gemma4:12b. So an unmeasured model is unproven,
    never assumed capable."""
    from backend.model_intelligence.model_intelligence_models import ModelProfile

    def profile(**kw):
        return ModelProfile(model_id="m", name="m", **kw)

    # Unproven, whatever the size: guessing was wrong about half the time.
    assert not profile(parameters_b=2.3, declares_tools=True).agentic_capable
    assert not profile(parameters_b=23.6, declares_tools=True).agentic_capable
    # Structural disqualifiers still rule a model out immediately.
    assert not profile(parameters_b=30.0, declares_tools=False).agentic_capable
    assert not profile(
        parameters_b=30.0, declares_tools=True, chat_capable=False,
    ).agentic_capable
    # A measured run is the only thing that qualifies — and it does so for a
    # 2.7B model that every heuristic would have rejected.
    assert profile(
        parameters_b=2.7, declares_tools=True, measured_agentic_success=True,
    ).agentic_capable
    assert not profile(
        parameters_b=30.0, declares_tools=True, measured_agentic_success=False,
    ).agentic_capable


def test_a_model_spilling_out_of_vram_is_not_agentically_capable():
    """Measured on this 16 GB card (HOS-096): devstral given the 65536 of
    context that stops tool schemas being truncated needs 25.52 GB, so
    10.75 GB — 42% of the model — runs on CPU. Nothing errors; it just takes
    ~300s per task and calls tools erratically, which reads as an unreliable
    model until you look at the split. Raising the context is precisely what
    causes the overflow, so the two cannot be judged separately."""
    from backend.model_intelligence.model_intelligence_models import ModelProfile

    def profile(**kw):
        return ModelProfile(
            model_id="m", name="m", parameters_b=23.6, declares_tools=True,
            served_context=65536, measured_agentic_success=True, **kw,
        )

    # Fitting entirely in VRAM keeps a measured-good model usable.
    assert profile(cpu_offload_bytes=0).agentic_capable
    assert profile(cpu_offload_bytes=None).agentic_capable  # never measured
    # Overflow disqualifies even a model that measured well: it is the same
    # weights, running far slower and erratically on this hardware.
    assert not profile(cpu_offload_bytes=10_750_000_000).agentic_capable
    # Even a sliver of offload disqualifies: partial CPU execution is what
    # makes the model slow and erratic, not the size of the spill.
    assert not profile(cpu_offload_bytes=1).agentic_capable


def test_served_context_gates_agentic_capability():
    """Hermes Agent's own guidance, corroborated by measurement here: below
    ~64k of *served* context, tool calling degrades badly. The distinction
    between served and supported is the whole point — devstral advertises
    131072 while Ollama was handing out 8192, which is not enough for a tool
    schema plus a mission brief, so the tools were truncated away and the
    agent truthfully reported having no file access."""
    from backend.model_intelligence.model_intelligence_models import ModelProfile

    def profile(served):
        return ModelProfile(
            model_id="m", name="m", parameters_b=23.6, declares_tools=True,
            served_context=served, measured_agentic_success=True,
        )

    assert profile(65536).agentic_capable
    assert profile(131072).agentic_capable
    assert profile(None).agentic_capable  # never probed for context
    # A starved runtime disqualifies even a model that measured well: the
    # tool schema gets truncated regardless of how the model once scored.
    assert not profile(8192).agentic_capable
    # Supported context is explicitly NOT the gate — a model can advertise
    # 131072 and still be served 8192, which is exactly what happened.
    starved = ModelProfile(
        model_id="m", name="m", parameters_b=23.6, declares_tools=True,
        context_window=131072, served_context=8192, measured_agentic_success=True,
    )
    assert not starved.agentic_capable


def test_agent_loop_gets_its_own_timeout_budget(hermes_agent, monkeypatch, tmp_path):
    """An agent loop is not a completion. With the 180s completion budget, a
    real mission ran for 12 minutes and finished 0/5 tasks, every one of
    them failing with "runtime 'hermes-agent' timed out after 180s" — while
    the mission still reported a duration as though work had happened."""
    _forbid_ollama(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    seen: dict = {}

    class _TimeoutRecordingRuntime(_RecordingHermesAgentRuntime):
        def __init__(self, config=None):
            seen["timeout"] = getattr(config, "timeout_seconds", None)
            super().__init__(config)

    monkeypatch.setattr(
        "backend.ral.adapters.hermes_agent_cli.HermesAgentCliRuntime", _TimeoutRecordingRuntime,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
    )
    executor.execute(_FakeTask(mission_id="m-1"))

    assert seen["timeout"] > 180.0, (
        "Hermes Agent inherited the single-completion timeout; a real "
        "multi-step task cannot finish inside it"
    )


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


def test_the_agent_is_invoked_with_its_own_interpreter():
    """Hermes OS and Hermes Agent must not share a Python environment.

    Until HOS-103 they did: `python` on PATH was the agent's venv
    interpreter, so `hermes update` resynchronised Hermes OS's dependencies
    without saying so. On 2026-08-13 one such update left
    opentelemetry-exporter-otlp-proto-grpc at 1.44.0 against a 1.39.1
    family and eight Hermes OS test modules stopped importing, with no
    change to Hermes OS at all.

    The failure mode this guards is a plausible, well-meaning edit:
    replacing the absolute path below with `sys.executable`, which reads
    like removing a hardcoded path but would launch cli.py under an
    interpreter that has none of the agent's dependencies.

    Asserted as a property rather than as a literal path, so it holds on
    any machine: whatever the adapter points at, it is not the interpreter
    Hermes OS is running under.
    """
    import sys
    from pathlib import Path

    from backend.ral.adapters.hermes_agent_cli import HermesAgentCliConfig

    configured = Path(HermesAgentCliConfig().python_exe)

    assert configured != Path(sys.executable), (
        "the adapter is launching Hermes Agent with Hermes OS's own "
        "interpreter — the two environments are separate on purpose"
    )
    assert "hermes-agent" in configured.as_posix(), (
        f"expected an interpreter inside the Hermes Agent install, got {configured}"
    )


def test_un_runtime_non_choisi_va_quand_meme_a_hermes_agent(
    hermes_agent, monkeypatch, tmp_path,
):
    """La seconde porte du meme contournement (HOS-142).

    `agent_coordinator._select_runtime` rend litteralement `"default"` quand
    son registre de runtimes est vide — et il l'etait sur cette machine,
    l'avertissement `registries still empty after seeding: runtimes` le
    disait a chaque demarrage.

    `execute()` ne reconnaissait que la chaine exacte `"hermes-agent"` : avec
    `"default"`, il tombait sur sa propre boucle d'outils. Le test ci-dessus
    ne l'attrapait pas, parce qu'il ne fournit aucun `assigned_runtime` et
    beneficie donc du defaut cable en dur.

    Mesure du 2026-08-21, en plein deroulement d'un cahier : le harnais
    annoncait `pret`, **aucun processus d'agent n'existait** — ni session ni
    mode jetable — et des fichiers etaient pourtant crees, par Hermes OS
    lui-meme. Ni le journal, ni le bilan, ni le rapport de mission ne
    l'auraient dit : les sections etaient « faites ».
    """
    _forbid_ollama(monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: ("proj-1", str(workspace)),
    )
    outcome = executor.execute(
        _FakeTask(mission_id="m-1", assigned_runtime="default"))

    assert hermes_agent.started, (
        "HERMES_AGENT_BYPASS_DETECTED: un runtime non choisi a fait "
        "contourner Hermes Agent au profit de la boucle d'outils de Hermes OS"
    )
    assert outcome.metadata.get("provider") == "hermes-agent"
