"""Tests for HOS-068 — Missions real-wiring:

* cross-visibility (register_mission makes an externally-built Mission
  visible to /missions),
* the risk-based Aegis gate (_check_mission_security: allow/review/deny),
* real mission report generation (build_mission_report),
* pause actually interrupting a run / resume actually continuing it,
* resume setting started_at when a mission was paused before ever starting
  (the Aegis-gated path),
* the dead retry loop fix in node_execution.py,
* real bounded parallel execution in GraphExecutor (HOS-068 Phase D),
* the narrowed lock in MissionExecutor.execute_task() allowing genuine
  concurrency across different tasks.

Fully hermetic: fakes stand in for AegisEngine/MemoryManager/EvolutionEngine/
task executors, no real Ollama or filesystem access needed.
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

import pytest

from backend.execution.agent_coordinator import AgentCoordinator
from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import TaskExecutionOutcome
from backend.execution.task_scheduler import TaskScheduler
from backend.execution.validation_engine import ValidationEngine
from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import (
    Mission,
    MissionContext,
    MissionNode,
    MissionStatus,
    NodeStatus,
    build_mission_report,
)
from backend.security.aegis_engine import Verdict


# ── Helpers ──────────────────────────────────────────────────

def _make_node(nid: str, deps: list[str] | None = None) -> MissionNode:
    return MissionNode(node_id=nid, title=nid, depends_on=deps or [])


def _make_mission(node_ids: list[str], deps: dict[str, list[str]] | None = None) -> Mission:
    deps = deps or {}
    m = Mission(title="Test Mission")
    m.nodes = [_make_node(nid, deps.get(nid)) for nid in node_ids]
    return m


# ═══════════════════════════════════════════════════════════════
# register_mission — cross-visibility
# ═══════════════════════════════════════════════════════════════

class TestRegisterMission:
    def test_register_mission_makes_it_visible_to_list(self):
        from backend.mission import routes as mission_routes

        mission_routes._missions.clear()
        m = Mission(title="Built elsewhere")
        mission_routes.register_mission(m)
        assert mission_routes._missions[m.mission_id] is m
        mission_routes._missions.clear()


# ═══════════════════════════════════════════════════════════════
# _check_mission_security — risk-based Aegis gate
# ═══════════════════════════════════════════════════════════════

class _FakeDecision:
    def __init__(self, verdict, reason="fake reason"):
        self.verdict = verdict
        self.reason = reason


class _FakeAegisEngine:
    """`verdict` applies only to the mission_execute check — a real
    AegisEngine never returns REQUIRE_HUMAN_VALIDATION for file_read given
    this repo's config/security.yaml (no autonomy gating configured for
    that category), so the local_path pre-check always ALLOWs here too."""

    def __init__(self, verdict):
        self._verdict = verdict
        self.calls: list[str] = []

    # La signature suit celle d'AegisEngine.evaluate, mots-cles compris.
    # Une doublure qui n'accepte pas les arguments du vrai moteur ne
    # protege plus rien : elle echoue sur un TypeError et non sur ce que le
    # test verifie. `extra_allowed_paths` est arrive avec la liste blanche
    # dynamique et n'a jamais ete repercute ici, parce que pytest.ini
    # n'executait pas ce repertoire.
    def evaluate(self, request, *, project_root=None, extra_allowed_paths=None):
        self.calls.append(request.action_type)
        if request.action_type == "file_read":
            return _FakeDecision(Verdict.ALLOW)
        return _FakeDecision(self._verdict)


def test_la_doublure_aegis_suit_la_signature_du_vrai_moteur():
    """L'incident que ce test empêche.

    `AegisEngine.evaluate` a gagné `extra_allowed_paths` avec la liste
    blanche dynamique. Les doublures de ce fichier ne l'ont pas suivi :
    quatre tests de la porte de sécurité échouaient sur un `TypeError` au
    lieu de vérifier ce qu'ils affirment vérifier. Personne ne l'a vu,
    parce que `pytest.ini` ne déclarait que `backend/tests`.

    Une doublure qui n'accepte pas les arguments du vrai moteur ne protège
    plus rien — et le jour où elle diverge en *comportement* plutôt qu'en
    signature, elle ne lèvera même plus d'erreur.
    """
    import inspect

    from backend.security.aegis_engine import AegisEngine

    def nommes(fn):
        # Seuls les parametres passes par mot-cle doivent correspondre : le
        # premier positionnel s'appelle `action` dans le vrai moteur et
        # `request` dans la doublure, ce qui est sans consequence.
        return {n for n, p in inspect.signature(fn).parameters.items()
                if p.kind is inspect.Parameter.KEYWORD_ONLY}

    manquants = nommes(AegisEngine.evaluate) - nommes(_FakeAegisEngine.evaluate)

    assert not manquants, (
        f"la doublure n'accepte pas {sorted(manquants)} — elle échouera sur "
        "un TypeError au lieu de tester la porte de sécurité"
    )


class TestMissionSecurityGate:
    def _patched(self, monkeypatch, verdict):
        from backend.mission import routes as mission_routes

        fake = _FakeAegisEngine(getattr(Verdict, verdict))
        monkeypatch.setattr(mission_routes, "_get_aegis_engine", lambda: fake)
        return mission_routes, fake

    def test_unbound_mission_skips_gate_entirely(self, monkeypatch):
        mission_routes, fake = self._patched(monkeypatch, "DENY")
        m = Mission(title="No project binding")
        result = mission_routes._check_mission_security(m)
        assert result is None
        assert fake.calls == []

    def test_allow_returns_none(self, monkeypatch):
        mission_routes, fake = self._patched(monkeypatch, "ALLOW")
        m = Mission(title="Bound")
        m.context.local_path = "/some/project"
        result = mission_routes._check_mission_security(m)
        assert result is None
        assert m.status != MissionStatus.FAILED

    def test_deny_fails_the_mission(self, monkeypatch):
        mission_routes, fake = self._patched(monkeypatch, "DENY")
        m = Mission(title="Bound")
        m.context.repository = "owner/repo"
        result = mission_routes._check_mission_security(m)
        assert result is not None
        assert m.status == MissionStatus.FAILED
        assert "error" in result

    def test_require_validation_pauses_not_fails(self, monkeypatch):
        mission_routes, fake = self._patched(monkeypatch, "REQUIRE_HUMAN_VALIDATION")
        m = Mission(title="Bound")
        m.context.local_path = "/some/project"
        result = mission_routes._check_mission_security(m)
        assert result is not None
        assert m.status == MissionStatus.PAUSED
        assert "reason" in result

    def test_local_path_denied_reported_distinctly(self, monkeypatch):
        # First evaluate() call (file_read on local_path) denies; the
        # mission_execute check should never be reached.
        from backend.mission import routes as mission_routes
        from backend.security.aegis_engine import Verdict

        calls: list[str] = []

        class _Engine:
            def evaluate(self, request, *, project_root=None,
                         extra_allowed_paths=None):
                calls.append(request.action_type)
                return _FakeDecision(Verdict.DENY, "path outside whitelist")

        monkeypatch.setattr(mission_routes, "_get_aegis_engine", lambda: _Engine())
        m = Mission(title="Bound")
        m.context.local_path = "/outside/whitelist"
        result = mission_routes._check_mission_security(m)
        assert result is not None
        assert "local_path denied" in result["error"]
        assert calls == ["file_read"]  # mission_execute never evaluated


# ═══════════════════════════════════════════════════════════════
# build_mission_report
# ═══════════════════════════════════════════════════════════════

class TestBuildMissionReport:
    def test_report_reflects_real_node_state(self):
        from datetime import datetime, timezone

        m = _make_mission(["a", "b"])
        m.status = MissionStatus.COMPLETED
        m.started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        m.completed_at = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        m.nodes[0].status = NodeStatus.COMPLETED
        m.nodes[0].result_summary = "did a"
        m.nodes[0].preferred_runtime = "ollama"
        m.nodes[1].status = NodeStatus.COMPLETED
        m.nodes[1].result_summary = "did b"
        m.nodes[1].preferred_runtime = "ollama"

        report = build_mission_report(m)
        assert report.tasks_total == 2
        assert report.tasks_completed == 2
        assert report.tasks_failed == 0
        assert report.success is True
        assert report.total_duration_ms == pytest.approx(1000.0, abs=1.0)
        assert report.runtimes_used == ["ollama"]
        assert {o["task"] for o in report.outputs} == {"a", "b"}

    def test_report_includes_failed_node_errors(self):
        m = _make_mission(["a"])
        m.status = MissionStatus.FAILED
        m.nodes[0].status = NodeStatus.FAILED
        m.nodes[0].result_summary = "failed: timeout"

        report = build_mission_report(m)
        assert report.tasks_failed == 1
        assert report.success is False
        assert report.errors == ["failed: timeout"]

    def test_report_never_started_has_zero_duration(self):
        m = _make_mission(["a"])
        report = build_mission_report(m)
        assert report.total_duration_ms == 0.0
        assert report.summary == "0/1 task(s) completed"


# ═══════════════════════════════════════════════════════════════
# node_execution.py — retry loop actually retries
# ═══════════════════════════════════════════════════════════════

class TestNodeExecutionRetryLoop:
    def test_retry_then_success_actually_reinvokes_execute_task(self):
        from backend.execution.execution_models import TaskExecutionStatus
        from backend.mission.node_execution import make_node_executor

        calls = {"n": 0}

        class _FakeController:
            """Mirrors ExecutionController's shape (HOS-069): start()/
            execute_task(execution_id, task_id)/finalize(), not the raw
            engine's prepare()/execute_task(sm, task_id)."""

            def start(self, meta, tasks):
                self._task = tasks[0]
                return object()

            def execute_task(self, execution_id, task_id):
                calls["n"] += 1
                if calls["n"] < 3:
                    # Mirrors MissionExecutor: RETRY resets status to PENDING.
                    self._task.status = TaskExecutionStatus.PENDING
                    return {"task_id": task_id, "status": "pending"}
                self._task.status = TaskExecutionStatus.COMPLETED
                self._task.result = "done"
                self._task.duration_ms = 5.0
                return {"task_id": task_id, "status": "completed"}

            def finalize(self, execution_id):
                return None

        controller = _FakeController()
        executor = make_node_executor(controller)
        node = MissionNode(node_id="n1", title="Retry me")
        result = executor(node)

        assert result is True
        assert calls["n"] == 3  # retried twice before succeeding
        assert "done" in node.result_summary

    def test_no_controller_reports_failure_not_success(self):
        from backend.mission.node_execution import make_node_executor

        executor = make_node_executor(None)
        node = MissionNode(node_id="n1", title="Orphan node")
        assert executor(node) is False


# ═══════════════════════════════════════════════════════════════
# GraphExecutor — real bounded parallel execution (Phase D)
# ═══════════════════════════════════════════════════════════════

class TestGraphExecutorParallelism:
    def test_two_ready_nodes_run_concurrently_when_bound_allows(self):
        """Two independent ready nodes, each 'executing' for 200ms, must
        overlap in wall-clock time when max_parallel_tasks=2 — proving this
        is genuine thread-pool concurrency, not serialized fake parallelism."""
        starts: dict[str, float] = {}
        lock = threading.Lock()

        def slow_execute(node: MissionNode) -> bool:
            with lock:
                starts[node.node_id] = time.monotonic()
            time.sleep(0.2)
            return True

        executor = GraphExecutor(execute_node=slow_execute, max_parallel_tasks=2)
        mission = _make_mission(["a", "b"])
        executor.build_graph(mission, mission.nodes, [])
        executor.start_mission(mission)

        t0 = time.monotonic()
        count = executor.execute_step(mission)
        elapsed = time.monotonic() - t0

        assert count == 2
        assert mission.status == MissionStatus.COMPLETED
        # Serial execution would take >= 0.4s; concurrent execution should
        # finish close to one 0.2s slot.
        assert elapsed < 0.35
        # Both nodes must have actually started within the same short window.
        assert abs(starts["a"] - starts["b"]) < 0.15

    def test_max_parallel_one_runs_strictly_serially(self):
        starts: list[float] = []

        def slow_execute(node: MissionNode) -> bool:
            starts.append(time.monotonic())
            time.sleep(0.15)
            return True

        executor = GraphExecutor(execute_node=slow_execute, max_parallel_tasks=1)
        mission = _make_mission(["a", "b"])
        executor.build_graph(mission, mission.nodes, [])
        executor.start_mission(mission)

        t0 = time.monotonic()
        executor.execute_step(mission)
        elapsed = time.monotonic() - t0

        assert elapsed >= 0.28  # two 0.15s slots, back to back

    def test_default_max_parallel_reads_settings(self):
        from backend.core.config import get_settings

        executor = GraphExecutor()
        assert executor._max_parallel == get_settings().mission_max_parallel_tasks

    def test_failed_node_among_parallel_batch_marked_failed_not_completed(self):
        def flaky_execute(node: MissionNode) -> bool:
            return node.node_id != "b"

        executor = GraphExecutor(execute_node=flaky_execute, max_parallel_tasks=2)
        mission = _make_mission(["a", "b"])
        executor.build_graph(mission, mission.nodes, [])
        executor.start_mission(mission)
        executor.execute_step(mission)

        by_id = {n.node_id: n for n in mission.nodes}
        assert by_id["a"].status == NodeStatus.COMPLETED
        assert by_id["b"].status == NodeStatus.FAILED
        assert mission.status == MissionStatus.FAILED


# ═══════════════════════════════════════════════════════════════
# resume_mission — sets started_at when paused before ever starting
# ═══════════════════════════════════════════════════════════════

class _FakeExecutorForRoutes:
    """Enough of GraphExecutor's surface for resume_mission()/
    _run_mission_steps() to drive one pass to completion."""

    def __init__(self):
        self.step_calls = 0

    def execute_step(self, mission: Mission) -> int:
        self.step_calls += 1
        stepped = 0
        for n in mission.nodes:
            if n.status == NodeStatus.PENDING:
                n.status = NodeStatus.COMPLETED
                stepped += 1
        if stepped:
            mission.status = MissionStatus.COMPLETED
            mission.completed_at = datetime.now(timezone.utc)
        return stepped

    def get_progress(self, mission: Mission) -> dict:
        return {"completed": mission.completed_nodes(), "total": mission.total_nodes()}


class TestResumeSetsStartedAt:
    def test_resume_after_aegis_pause_sets_started_at(self, monkeypatch):
        """A mission the Aegis gate paused inside _check_mission_security()
        never reaches _executor.start_mission() — the only other place
        that sets started_at — so without this fix build_mission_report()
        would report total_duration_ms: 0.0 for a mission that genuinely
        ran after being resumed (found via manual browser verification)."""
        from backend.mission import routes as mission_routes

        fake_executor = _FakeExecutorForRoutes()
        monkeypatch.setattr(mission_routes, "_executor", fake_executor)
        monkeypatch.setattr(mission_routes, "_memory_manager", None)
        monkeypatch.setattr(mission_routes, "_evolution_engine", None)

        m = _make_mission(["a"])
        m.status = MissionStatus.PAUSED  # as _check_mission_security leaves it
        assert m.started_at is None
        mission_routes._missions[m.mission_id] = m

        result = asyncio.run(mission_routes.resume_mission(m.mission_id))

        assert m.started_at is not None
        assert result["status"] == "completed"
        report = build_mission_report(m)
        assert report.total_duration_ms >= 0.0
        assert report.status == "completed"
        del mission_routes._missions[m.mission_id]

    def test_resume_of_already_started_mission_keeps_original_started_at(self, monkeypatch):
        from backend.mission import routes as mission_routes

        fake_executor = _FakeExecutorForRoutes()
        monkeypatch.setattr(mission_routes, "_executor", fake_executor)
        monkeypatch.setattr(mission_routes, "_memory_manager", None)
        monkeypatch.setattr(mission_routes, "_evolution_engine", None)

        original_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        m = _make_mission(["a"])
        m.status = MissionStatus.PAUSED
        m.started_at = original_start
        mission_routes._missions[m.mission_id] = m

        asyncio.run(mission_routes.resume_mission(m.mission_id))

        assert m.started_at == original_start
        del mission_routes._missions[m.mission_id]


# ═══════════════════════════════════════════════════════════════
# MissionExecutor — narrowed lock allows genuine concurrency
# ═══════════════════════════════════════════════════════════════

class _SlowFakeTaskExecutor:
    """Stands in for RealTaskExecutor: blocks for a fixed duration outside
    any lock, so concurrent execute_task() calls can only overlap if the
    engine's own lock does not wrap this call."""

    def __init__(self, delay_s: float = 0.2):
        self._delay_s = delay_s
        self.start_times: dict[str, float] = {}
        self._lock = threading.Lock()

    def execute(self, task: TaskExecution, assignment) -> TaskExecutionOutcome:
        with self._lock:
            self.start_times[task.task_id] = time.monotonic()
        time.sleep(self._delay_s)
        return TaskExecutionOutcome(
            result=f"result for {task.task_id}",
            runtime_id="fake",
            model="fake-model",
            duration_ms=self._delay_s * 1000.0,
        )


class TestMissionExecutorLockNarrowing:
    def test_concurrent_execute_task_calls_actually_overlap(self):
        """Mirrors how node_execution.py's make_node_executor() really drives
        this engine for concurrent DAG nodes: one prepare() call per task
        (its own ExecutionStateMachine, its own single-task registration),
        not one shared state machine — sm.transition() isn't safe to call
        concurrently from two threads on the same instance, and the real
        code never does that."""
        fake_executor = _SlowFakeTaskExecutor(delay_s=0.2)
        me = MissionExecutor(task_executor=fake_executor)

        results: dict[str, dict] = {}

        def run(task_id: str) -> None:
            task = TaskExecution(task_id=task_id, node_id=f"n-{task_id}", title=task_id)
            sm = me.prepare(ExecutionMeta(user_goal=task_id), [task])
            results[task_id] = me.execute_task(sm, task_id)

        t0 = time.monotonic()
        threads = [threading.Thread(target=run, args=(tid,)) for tid in ("t1", "t2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - t0

        assert results["t1"]["status"] == "completed"
        assert results["t2"]["status"] == "completed"
        # If the slow call were still inside the lock, this would take
        # >= 0.4s (serialized). Genuine concurrency finishes near 0.2s.
        assert elapsed < 0.35
        start_gap = abs(
            fake_executor.start_times["t1"] - fake_executor.start_times["t2"]
        )
        assert start_gap < 0.15
