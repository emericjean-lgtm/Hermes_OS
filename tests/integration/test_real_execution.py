"""Integration tests for real execution (R-001).

These are the counterpart to the hermetic unit suites: they talk to an actual
runtime and an actual MCP server, and they exist to catch the specific failure
the RC2 audit found — a pipeline that reported success without doing any work.

Each test skips, rather than fails, when its dependency is absent, so the suite
stays runnable on a machine with no Ollama. A skip is honest; a pass against a
stub would be the exact problem R-001 removed.

The assertions are chosen to be impossible to satisfy by fabrication:

* a reported duration must track the wall clock (a generated number does not);
* identical requests must produce a *deterministic* success (the old code flipped
  a weighted coin);
* the runtime named in the report must be the one that answered;
* with the runtime removed, the task must fail — not succeed with an invention.
"""

from __future__ import annotations

import collections
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError

REPO_ROOT = Path(__file__).resolve().parents[2]

# A small model keeps these tests to a few seconds each.
TEST_MODEL = "qwen3:1.7b"
PROMPT = "Reply with exactly the word: OK"


def _ollama_url() -> str:
    from backend.core.config import get_settings

    return get_settings().ollama_api_url.rstrip("/")


def _ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{_ollama_url()}/api/tags", timeout=3) as response:
            payload = json.load(response)
    except Exception:
        return []
    return [m.get("name", "") for m in payload.get("models", [])]


AVAILABLE_MODELS = _ollama_models()
needs_ollama = pytest.mark.skipif(
    not AVAILABLE_MODELS,
    reason="no reachable Ollama — real-execution tests need one",
)


def _pick_model() -> str:
    if TEST_MODEL in AVAILABLE_MODELS:
        return TEST_MODEL
    # Prefer the smallest available tag so the test stays quick.
    return sorted(AVAILABLE_MODELS, key=len)[0] if AVAILABLE_MODELS else TEST_MODEL


class _Task:
    """Minimal stand-in for TaskExecution — only what the executor reads."""

    def __init__(self, title: str = PROMPT) -> None:
        self.task_id = "it-task"
        self.node_id = "it-node"
        self.title = title
        self.assigned_agent = "coder"
        self.assigned_runtime = "ollama"
        self.assigned_skills: list[str] = []
        self.assigned_tools: list[str] = []


# ── The executor drives a real runtime ────────────────────────────────


@needs_ollama
class TestRealInference:
    def test_produces_a_real_completion(self):
        executor = RealTaskExecutor(default_model=_pick_model())
        try:
            outcome = executor.execute(_Task(), None)
        finally:
            executor.close()

        assert outcome.result.strip(), "a real runtime must return non-empty content"
        assert outcome.completion_chars == len(outcome.result)
        assert outcome.model, "the model that served the request must be recorded"
        assert outcome.metadata["provider"] == outcome.runtime_id

    def test_duration_is_measured_not_generated(self):
        """The old code reported random.uniform(500, 5000) regardless of work."""
        executor = RealTaskExecutor(default_model=_pick_model())
        try:
            started = time.perf_counter()
            outcome = executor.execute(_Task(), None)
            wall_ms = (time.perf_counter() - started) * 1000
        finally:
            executor.close()

        assert outcome.duration_ms > 0
        # Within 35% of wall clock: a fabricated number would not correlate.
        assert abs(outcome.duration_ms - wall_ms) / wall_ms < 0.35, (
            f"reported {outcome.duration_ms:.0f}ms vs wall {wall_ms:.0f}ms"
        )

    def test_tokens_are_counted(self):
        executor = RealTaskExecutor(default_model=_pick_model())
        try:
            outcome = executor.execute(_Task(), None)
        finally:
            executor.close()
        assert outcome.completion_tokens > 0
        assert outcome.prompt_tokens > 0
        assert outcome.metadata["token_counts"] in {"reported", "estimated"}

    def test_stats_reflect_real_executions(self):
        executor = RealTaskExecutor(default_model=_pick_model())
        try:
            executor.execute(_Task(), None)
            stats = executor.get_stats()
        finally:
            executor.close()
        assert stats["executions"] == 1
        assert stats["failures"] == 0
        assert stats["avg_duration_ms"] > 0
        assert stats["simulated"] is False


# ── Honest failure, no dependency required ───────────────────────────


class TestHonestFailure:
    """These need no runtime: they assert that *absence* of one is reported."""

    def test_unreachable_runtime_raises(self):
        async def refused(**_kwargs):
            raise ConnectionError("connection refused")

        executor = RealTaskExecutor(chat=refused)
        try:
            with pytest.raises(RuntimeUnavailableError) as exc:
                executor.execute(_Task(), None)
        finally:
            executor.close()
        assert "could not execute" in str(exc.value)

    def test_empty_completion_is_a_failure_not_a_success(self):
        """A runtime that answers with nothing has not done the work."""

        async def silent(**_kwargs):
            return ""

        executor = RealTaskExecutor(chat=silent)
        try:
            with pytest.raises(RuntimeUnavailableError, match="empty completion"):
                executor.execute(_Task(), None)
        finally:
            executor.close()

    def test_failures_are_counted(self):
        async def refused(**_kwargs):
            raise ConnectionError("nope")

        executor = RealTaskExecutor(chat=refused)
        try:
            for _ in range(3):
                with pytest.raises(RuntimeUnavailableError):
                    executor.execute(_Task(), None)
            stats = executor.get_stats()
        finally:
            executor.close()
        assert stats["failures"] == 3
        assert stats["executions"] == 0

    def test_mission_task_fails_when_runtime_is_down(self):
        """MissionExecutor must fail the task, not invent a result."""
        from backend.execution.execution_models import (
            ExecutionMeta,
            TaskExecution,
            TaskExecutionStatus,
        )
        from backend.execution.mission_executor import MissionExecutor

        async def refused(**_kwargs):
            raise ConnectionError("connection refused")

        executor = RealTaskExecutor(chat=refused)
        engine = MissionExecutor(task_executor=executor)
        try:
            meta = ExecutionMeta(mission_id="m-down", user_goal="anything")
            task = TaskExecution(task_id="t0", node_id="n0", title="do a thing")
            sm = engine.prepare(meta, [task])
            result = engine.execute_task(sm, "t0")
        finally:
            executor.close()

        assert result["runtime_available"] is False
        assert task.status == TaskExecutionStatus.FAILED
        assert task.result is None, "a failed task must carry no fabricated result"
        assert task.errors


# ── Model Intelligence feedback seam (HOS-065) ───────────────────────
#
# _make_task_executor (backend/core/bootstrap/service_registry.py) wires
# model_for/on_execution to AdaptiveRouter/ModelProfiler so a real task
# execution both picks its model through Model Intelligence and feeds its
# measured outcome back — previously nothing in the mission/task pipeline
# consulted the recommender, and the only thing that ever "trained" the
# profiler (BenchmarkScheduler) fabricated every number with
# random.uniform() and never persisted them. These are hermetic: only the
# wiring contract is under test, not the real router/profiler.


class TestModelIntelligenceFeedback:
    def test_reports_success_with_measured_telemetry(self):
        async def fake_chat(**_kwargs):
            return "a real completion"

        calls = []
        executor = RealTaskExecutor(
            chat=fake_chat,
            on_execution=lambda task, model, duration_ms, tokens, success: calls.append(
                (task.task_id, model, duration_ms, tokens, success)
            ),
        )
        try:
            executor.execute(_Task(), None)
        finally:
            executor.close()

        assert len(calls) == 1
        task_id, model, duration_ms, tokens, success = calls[0]
        assert task_id == "it-task"
        assert model
        assert duration_ms > 0
        assert tokens > 0
        assert success is True

    def test_reports_failure_with_zero_tokens(self):
        async def refused(**_kwargs):
            raise ConnectionError("nope")

        calls = []
        executor = RealTaskExecutor(
            chat=refused,
            on_execution=lambda task, model, duration_ms, tokens, success: calls.append(
                (model, tokens, success)
            ),
        )
        try:
            with pytest.raises(RuntimeUnavailableError):
                executor.execute(_Task(), None)
        finally:
            executor.close()

        assert len(calls) == 1
        model, tokens, success = calls[0]
        assert tokens == 0
        assert success is False

    def test_on_execution_failure_does_not_break_a_successful_task(self):
        """A broken feedback callback must not corrupt the real result —
        the same "must never fail work" discipline as _emit."""

        async def fake_chat(**_kwargs):
            return "ok"

        def broken_feedback(*_args):
            raise RuntimeError("boom")

        executor = RealTaskExecutor(chat=fake_chat, on_execution=broken_feedback)
        try:
            outcome = executor.execute(_Task(), None)
        finally:
            executor.close()
        assert outcome.result == "ok"

    def test_model_for_selects_the_model_actually_used(self):
        """model_for is the seam _make_task_executor uses to ask
        AdaptiveRouter which model to use — this confirms the resolved
        choice is the one that reaches the runtime call, not just computed
        and discarded (the defect model.py's RuntimeRecommender had)."""
        seen_models = []

        async def fake_chat(*, messages, model, num_ctx=None):
            seen_models.append(model)
            return "ok"

        executor = RealTaskExecutor(chat=fake_chat, model_for=lambda task: "picked-model:1b")
        try:
            outcome = executor.execute(_Task(), None)
        finally:
            executor.close()
        assert seen_models == ["picked-model:1b"]
        assert outcome.model == "picked-model:1b"

    def test_num_ctx_for_reaches_the_runtime_call(self):
        """num_ctx_for (HOS-065C) is the seam _make_task_executor uses to
        ask AdaptiveRouter for the model's real, benchmarked context window
        — this confirms the resolved value reaches the chat call, not just
        computed and discarded (the same defect class model_for fixed for
        the model choice itself)."""
        seen_ctx = []

        async def fake_chat(*, messages, model, num_ctx=None):
            seen_ctx.append(num_ctx)
            return "ok"

        executor = RealTaskExecutor(chat=fake_chat, num_ctx_for=lambda task: 24576)
        try:
            executor.execute(_Task(), None)
        finally:
            executor.close()
        assert seen_ctx == [24576]

    def test_num_ctx_for_defaulting_to_none_does_not_break_execution(self):
        """No num_ctx_for injected (every caller before this pass, and
        still every test that doesn't explicitly opt in) must keep working
        exactly as before — None reaches the chat call, same as always."""
        seen_ctx = []

        async def fake_chat(*, messages, model, num_ctx=None):
            seen_ctx.append(num_ctx)
            return "ok"

        executor = RealTaskExecutor(chat=fake_chat)
        try:
            outcome = executor.execute(_Task(), None)
        finally:
            executor.close()
        assert seen_ctx == [None]
        assert outcome.result == "ok"


# ── The autonomous pipeline end to end ───────────────────────────────


@needs_ollama
class TestAutonomousEndToEnd:
    def test_goal_executes_and_reports_measured_facts(self):
        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
        from backend.execution.mission_executor import MissionExecutor

        executor = RealTaskExecutor(default_model=_pick_model())
        orchestrator = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor)
        )
        try:
            started = time.perf_counter()
            goal = orchestrator.start_goal(PROMPT)
            wall_ms = (time.perf_counter() - started) * 1000
            report = orchestrator.get_report(goal.goal_id)
        finally:
            executor.close()

        assert report is not None
        results = report.results
        assert results["success"] is True, report.execution_summary
        assert results["tasks_completed"] == results["tasks_total"] >= 1
        assert results["tokens"] > 0
        # The runtime named must be the one that answered, not a constant.
        assert report.runtimes_used == ["ollama"], report.runtimes_used
        assert abs(report.total_duration_ms - wall_ms) / wall_ms < 0.5

    def test_identical_requests_do_not_flip_outcome(self):
        """The old implementation was `random.random() > 0.15`, so identical
        requests disagreed roughly one time in six."""
        from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
        from backend.execution.mission_executor import MissionExecutor

        executor = RealTaskExecutor(default_model=_pick_model())
        orchestrator = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor)
        )
        try:
            outcomes = []
            for _ in range(3):
                goal = orchestrator.start_goal(PROMPT)
                report = orchestrator.get_report(goal.goal_id)
                outcomes.append(report.results["success"])
        finally:
            executor.close()

        assert len(set(outcomes)) == 1, f"outcome was not deterministic: {outcomes}"
        assert outcomes[0] is True


# ── MCP performs real communication ──────────────────────────────────


class TestMCPTransport:
    """connect() must mean connected."""

    @pytest.mark.parametrize(
        "host,port",
        [("127.0.0.1", 59999), ("169.254.169.254", 80), ("does-not-exist.invalid", 80)],
    )
    def test_unreachable_server_is_not_reported_connected(self, host, port):
        from backend.tools.mcp.mcp_client import MCPClient
        from backend.tools.mcp.mcp_models import MCPServer, MCPStatus, MCPTransport
        from backend.tools.mcp.mcp_registry import MCPRegistry

        server = MCPServer(name="probe", host=host, port=port,
                           transport=MCPTransport.HTTP)
        client = MCPClient(MCPRegistry())

        assert client.connect(server) is False
        assert server.status == MCPStatus.ERROR
        assert server.error, "the failure reason must be recorded"
        assert server.connected_at is None

    def test_call_on_a_dead_server_fails(self):
        from backend.tools.mcp.mcp_client import MCPClient
        from backend.tools.mcp.mcp_models import (
            MCPServer,
            MCPStatus,
            MCPTool,
            MCPTransport,
        )
        from backend.tools.mcp.mcp_registry import MCPRegistry

        server = MCPServer(name="dead", host="127.0.0.1", port=59999,
                           transport=MCPTransport.HTTP,
                           status=MCPStatus.CONNECTED)
        tool = MCPTool(server_id=server.id, name="anything")
        call = MCPClient(MCPRegistry()).call(tool, server, {})

        assert call.success is False
        assert call.error
        assert call.result in (None, {}, {} if call.result == {} else None)

    def test_connects_to_a_real_mcp_server(self):
        """Boot Hermes' own MCP server and complete a real handshake."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        process = subprocess.Popen(  # noqa: S603 - fixed argv, test-only
            [sys.executable, "-m", "uvicorn", "backend.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, shell=False,
        )
        # Nothing read process.stdout during normal operation (only on the
        # failure branch below, reached after the process had already exited).
        # subprocess.PIPE gives the child a small OS buffer; once cumulative
        # log output filled it, the child's next write() to stdout blocked
        # indefinitely — inline with request handling — which is what turned
        # a real MCP handshake into a TimeoutError with the server sitting
        # there alive but unresponsive. Same bug, same fix, as
        # backend/tests/test_smoke_live_server.py: drain continuously.
        output_tail: collections.deque = collections.deque(maxlen=200)

        def _drain() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                output_tail.append(line)

        threading.Thread(target=_drain, daemon=True).start()
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f"server exited: {''.join(output_tail)[:800]}")
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health", timeout=2) as r:
                        if r.status == 200:
                            break
                except Exception:
                    time.sleep(0.5)
            else:
                pytest.fail("MCP host server never became ready")

            from backend.tools.mcp.mcp_client import MCPClient
            from backend.tools.mcp.mcp_models import (
                MCPServer,
                MCPStatus,
                MCPTransport,
            )
            from backend.tools.mcp.mcp_registry import MCPRegistry

            server = MCPServer(name="hermes-self", host="localhost", port=port,
                               transport=MCPTransport.HTTP)
            connected = MCPClient(MCPRegistry()).connect(server)

            assert connected is True, f"handshake failed: {server.error}"
            assert server.status == MCPStatus.CONNECTED
            assert server.connected_at is not None
            assert not server.error
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:  # pragma: no cover
                process.kill()
