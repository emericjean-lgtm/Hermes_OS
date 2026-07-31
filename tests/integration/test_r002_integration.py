"""R-002 end-to-end integration tests.

These assert the properties R-002 was about, against the real assembled app:

* there is exactly **one** task-execution engine, shared by every mission surface;
* a mission created through ``/api/v1/missions`` is decomposed into a DAG and
  actually executed, rather than having its status label flipped to ``running``;
* every registry the Cockpit reads is populated at startup;
* mission lifecycle events reach subscribers;
* the statistics the Cockpit displays match what the backend recorded.

The mission tests drive the real pipeline but replace only the outbound Ollama
call, exactly as ``tests/support/fake_inference`` does elsewhere: seven real
inferences take about two minutes, which is not a unit-test budget. Everything
else — planner, DAG, scheduler, coordinator, validator, event bus — is real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.support.fake_inference import fake_chat


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def container(app, client):
    """The composition root's container, once the app has fully started."""
    return app.state.container


@pytest.fixture
def fast_engine(container):
    """Point the shared engine's task executor at the fake inference call.

    Only the outbound HTTP call to Ollama is replaced. Patching it on the shared
    executor is itself a check that the executor really is shared.
    """
    engine = container.get("execution_engine")
    executor = engine._task_executor
    original = executor._chat
    executor._chat = fake_chat
    try:
        yield engine
    finally:
        executor._chat = original


# ── One pipeline ──────────────────────────────────────────────────────


def test_one_execution_engine_is_shared_by_every_surface(container):
    """The autonomous surface and the DAG must not each build their own engine."""
    shared = container.get("execution_engine")

    autonomous = container.get("autonomous_engine")
    assert autonomous.orchestrator.mission_executor is shared, (
        "the autonomous orchestrator built its own MissionExecutor — "
        "Hermes is back to two pipelines")

    graph_executor = container.get("mission_executor")
    hook = getattr(graph_executor, "_execute_node", None)
    assert hook is not None
    assert getattr(hook, "__name__", "") == "execute_node", (
        "the DAG's execute_node hook is not bound; it falls back to "
        "`lambda n: True`, declaring every node successful without work")


def test_task_executor_is_a_registered_service(container):
    """Both halves of the pipeline are composition-root services, not privates."""
    assert container.has("task_executor")
    assert container.has("execution_engine")
    assert container.get("execution_engine")._task_executor is container.get(
        "task_executor")


# ── Registries ────────────────────────────────────────────────────────


def test_every_cockpit_registry_is_populated(client):
    """A fully assembled Hermes served agents: 0, tools: 0, mcp/servers: 0."""
    assert client.get("/api/v1/agents").json()["total"] > 0, "no agents registered"
    assert client.get("/api/v1/tools").json()["count"] > 0, "no tools registered"
    assert client.get("/api/v1/mcp/servers").json()["count"] > 0, "no MCP servers"
    assert len(client.get("/api/v1/runtimes").json()["runtimes"]) > 0, "no runtimes"
    assert client.get("/api/v1/models").json()["data"]["total_models"] > 0


def test_registered_agents_come_from_the_declared_roster(client):
    """The ten enabled entries of config/agents.yaml, not invented ones."""
    from backend.core.config import load_agents_config

    declared = {k for k, v in load_agents_config()["agents"].items()
                if v.get("enabled")}
    registered = {a["name"] for a in client.get("/api/v1/agents").json()["agents"]}
    assert declared, "config/agents.yaml declares no enabled agent"
    assert declared <= registered, f"missing from registry: {declared - registered}"


def test_tool_names_are_not_enum_reprs(client):
    """`klaatcode.KlaatCodeAction.ANALYZE_PROJECT` is a formatting bug."""
    names = [t["name"] for t in client.get("/api/v1/tools").json()["tools"]]
    assert names, "no tools registered"
    offenders = [n for n in names if "Action." in n]
    assert not offenders, f"enum repr leaked into public tool names: {offenders}"


def test_seeding_is_idempotent(app, client):
    """Registries are module globals that outlive one app; a second app in the
    same process must not double-register."""
    names = [t["name"] for t in client.get("/api/v1/tools").json()["tools"]]
    assert len(names) == len(set(names)), "duplicate tools registered"

    try:
        with TestClient(create_app()) as second:
            again = [t["name"] for t in second.get("/api/v1/tools").json()["tools"]]
    finally:
        # Route modules bind through module-level globals, so building a second
        # app takes ownership of them and closing it does not hand them back.
        # The app under test has to reassert its own bindings or every later
        # test in this module reads the dead app's subsystems. Same reason
        # main.py's lifespan calls rebind_routes() on startup.
        app.state.bootstrap.rebind_routes()

    assert len(again) == len(set(again)), "second app duplicated the tool registry"
    assert set(again) == set(names)


def test_assembly_reports_registry_counts(client):
    """The bootstrap publishes what it seeded, so the gap is visible."""
    registries = client.get("/api/v1/system/assembly").json()["bootstrap"]["registries"]
    assert registries.get("agents", 0) > 0
    assert registries.get("tools", 0) > 0
    # Skills legitimately stay at zero: the repo declares no SkillDefinition.
    assert "skills" in registries


def test_the_coordinator_assigns_against_populated_catalogues(client):
    """It reported agents_registered: 0 while assigning work on a live system."""
    stats = client.get("/api/v1/system/statistics").json()["services"]
    coordinator = stats["execution_engine"]["coordinator"]
    assert coordinator["agents_registered"] > 0
    assert coordinator["tools_available"] > 0


# ── A mission actually executes ───────────────────────────────────────


def test_mission_is_decomposed_into_a_dag(client, fast_engine):
    """POST /missions used to require the caller to supply nodes and edges."""
    created = client.post("/api/v1/missions", json={
        "title": "R-002 decomposition",
        "description": "Analyse the authentication module and list its entry points",
    }).json()

    assert created["planned"] is True, "the Mission Planner was never invoked"
    assert created["nodes"] > 1, f"no DAG produced: {created}"
    assert created["validation_issues"] == []


def test_starting_a_mission_executes_it(client, fast_engine):
    """/start only flipped the status label; execute_step() was never called."""
    mid = client.post("/api/v1/missions", json={
        "title": "R-002 execution",
        "description": "Analyse the authentication module and list its entry points",
    }).json()["mission_id"]

    started = client.post(f"/api/v1/missions/{mid}/start").json()
    assert started["nodes_executed"] > 0, "no node was executed"
    assert started["status"] == "completed", f"mission did not finish: {started}"
    assert started["progress"]["progress_pct"] == 100.0

    after = client.get(f"/api/v1/missions/{mid}").json()
    assert after["status"] == "completed"
    assert after["progress"]["completed"] == after["progress"]["total"] > 0


def test_the_graph_exposes_what_each_node_actually_did(client, fast_engine):
    """The graph view could not tell a node that ran from one that never did."""
    mid = client.post("/api/v1/missions", json={
        "title": "R-002 graph detail",
        "description": "Analyse the authentication module",
    }).json()["mission_id"]
    client.post(f"/api/v1/missions/{mid}/start")

    nodes = client.get(f"/api/v1/missions/{mid}/graph").json()["nodes"]
    assert nodes
    for node in nodes:
        assert "duration_ms" in node
        assert "result_summary" in node
    assert any(n["status"] == "completed" for n in nodes)


def test_execution_is_recorded_by_the_task_executor(client, fast_engine, container):
    """The proof that work happened is the executor's own counter.

    Read straight off the shared executor rather than through
    /system/statistics: that endpoint closes over the bootstrap of whichever app
    built it, and this module deliberately builds a second one.
    """
    executor = container.get("task_executor")
    before = executor.get_stats()["executions"]

    mid = client.post("/api/v1/missions", json={
        "title": "R-002 counters",
        "description": "Analyse the authentication module",
    }).json()["mission_id"]
    client.post(f"/api/v1/missions/{mid}/start")

    after = executor.get_stats()
    assert after["executions"] > before, (
        "no task reached the executor — the mission reported progress it did not make")
    assert after["simulated"] is False


def test_mission_completion_writes_an_episode(client, fast_engine, container):
    """/missions used to leave episodic.total unmoved no matter how many
    missions completed through it — only /autonomous fed episodic memory
    (RC3 P2 fixed that surface; this is the same gap on the other one)."""
    memory_manager = container.get("memory_manager")
    before = memory_manager.stats()["episodic"]["total"]

    mid = client.post("/api/v1/missions", json={
        "title": "R-002 episodic write-back",
        "description": "Analyse the authentication module",
    }).json()["mission_id"]
    client.post(f"/api/v1/missions/{mid}/start")

    after = memory_manager.stats()["episodic"]["total"]
    assert after > before, "mission completed but no episode was recorded"

    episode = memory_manager.get_episode(mid)
    assert episode is not None
    assert episode.success is True
    assert episode.total_nodes > 0


def test_autonomous_surface_uses_the_same_engine(client, fast_engine, container):
    """Both surfaces must move the one shared counter."""
    executor = container.get("task_executor")
    before = executor.get_stats()["executions"]

    goal = client.post("/api/v1/autonomous/start",
                       json={"user_request": "Summarise the repository layout"}).json()

    assert goal["status"] == "completed"
    assert executor.get_stats()["executions"] > before


# ── Events reach the Cockpit ──────────────────────────────────────────


def test_mission_lifecycle_events_are_published(client, fast_engine, container):
    """MissionExecutor stored its dispatcher and never called it."""
    engine = container.get("execution_engine")
    seen: list[str] = []
    original = engine._on_event

    def capture(topic, payload=None, **kw):
        seen.append(topic)
        if original is not None:
            original(topic, payload, **kw)

    engine._on_event = capture
    try:
        mid = client.post("/api/v1/missions", json={
            "title": "R-002 events",
            "description": "Analyse the authentication module",
        }).json()["mission_id"]
        client.post(f"/api/v1/missions/{mid}/start")
    finally:
        engine._on_event = original

    for expected in ("execution.started", "execution.task_started",
                     "execution.completed"):
        assert expected in seen, (
            f"{expected} never reached a subscriber — the Cockpit's live feed "
            f"cannot see missions. Saw: {sorted(set(seen))}")


# ── Displayed statistics match the backend ────────────────────────────


def test_reported_duration_is_measured_not_fabricated(fast_engine):
    """ExecutionReport.total_duration_ms was `42.0 * total_tasks`."""
    from backend.execution.execution_models import (
        ExecutionMeta,
        TaskExecution,
        TaskExecutionStatus,
    )

    tasks = [TaskExecution(task_id=f"r002-{i}", title=f"task {i}",
                           status=TaskExecutionStatus.PENDING) for i in range(3)]
    sm = fast_engine.prepare(ExecutionMeta(mission_id="r002", user_goal="probe"), tasks)
    for task in tasks:
        fast_engine.execute_task(sm, task.task_id)

    report = fast_engine.finalize(sm)
    measured = sum(t.duration_ms or 0.0 for t in tasks)
    assert report.total_duration_ms == pytest.approx(measured, rel=1e-6)
    assert report.total_duration_ms != pytest.approx(42.0 * len(tasks)), (
        "the fabricated 42ms-per-task constant is back")
    assert report.runtimes_used, "runtimes_used was hard-coded empty"
