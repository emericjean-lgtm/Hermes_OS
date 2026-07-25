"""§6 — workflow nodes in the same wave run concurrently.

The hard part to test here is that parallelism is *real*, not merely
claimed: a test that only checks results would pass identically against
the old sequential engine. So the tools below record their own start and
end instants, and the assertions are about overlap — plus one test that
proves the concurrency cap is honoured, since an unbounded fan-out on
this hardware would thrash VRAM rather than go faster.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.workflows.engine import WorkflowEngine
from backend.workflows.schema import WorkflowDefinition

pytestmark = pytest.mark.asyncio


def _wf(nodes, edges, wid="wf-par"):
    return WorkflowDefinition.from_dict({"id": wid, "name": wid, "nodes": nodes, "edges": edges})


class _Recorder:
    """Async tools that log when they start and stop, so overlap is
    observable rather than inferred."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.events: list[tuple[str, str]] = []
        self.concurrent = 0
        self.peak = 0

    def tool(self, name):
        async def _call(**kwargs):
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
            self.events.append(("start", name))
            await asyncio.sleep(self.delay)
            self.events.append(("end", name))
            self.concurrent -= 1
            return {"who": name}

        return _call


def _engine(monkeypatch, tools, max_parallel=4):
    monkeypatch.setattr(WorkflowEngine, "__init__", lambda self: None)
    engine = WorkflowEngine()
    engine._tools = tools
    engine._max_parallel = max_parallel
    engine._save_run = lambda *a, **k: None
    engine._load_run = lambda run_id: None
    return engine


async def test_independent_nodes_actually_overlap(monkeypatch):
    """Three roots with no dependencies must interleave. Against the old
    sequential engine this same test fails, which is what makes it
    meaningful."""
    rec = _Recorder()
    tools = {f"t{i}": rec.tool(f"t{i}") for i in range(3)}
    workflow = _wf([{"id": f"n{i}", "action": f"t{i}"} for i in range(3)], [])

    run = await _engine(monkeypatch, tools).run(workflow)

    assert run.status == "completed"
    assert rec.peak == 3
    # All three started before any finished — genuine overlap, not just
    # a fast sequence.
    assert [e for e, _ in rec.events[:3]] == ["start", "start", "start"]


async def test_dependent_nodes_still_serialize(monkeypatch):
    """Parallelism must not break ordering: b depends on a."""
    rec = _Recorder()
    workflow = _wf(
        [{"id": "a", "action": "ta"}, {"id": "b", "action": "tb"}],
        [{"from": "a", "to": "b"}],
    )

    run = await _engine(monkeypatch, {"ta": rec.tool("a"), "tb": rec.tool("b")}).run(workflow)

    assert run.status == "completed"
    assert rec.peak == 1
    assert rec.events == [("start", "a"), ("end", "a"), ("start", "b"), ("end", "b")]


async def test_concurrency_cap_is_enforced(monkeypatch):
    """Six ready nodes with a cap of 2 must never exceed 2 in flight —
    the setting exists precisely so a wide graph can't ask Ollama to hold
    six models at once."""
    rec = _Recorder()
    tools = {f"t{i}": rec.tool(f"t{i}") for i in range(6)}
    workflow = _wf([{"id": f"n{i}", "action": f"t{i}"} for i in range(6)], [])

    await _engine(monkeypatch, tools, max_parallel=2).run(workflow)

    assert rec.peak == 2


async def test_cap_of_one_is_exactly_sequential(monkeypatch):
    """The documented escape hatch back to the old behaviour."""
    rec = _Recorder()
    tools = {f"t{i}": rec.tool(f"t{i}") for i in range(3)}
    workflow = _wf([{"id": f"n{i}", "action": f"t{i}"} for i in range(3)], [])

    await _engine(monkeypatch, tools, max_parallel=1).run(workflow)

    assert rec.peak == 1


async def test_one_failing_node_does_not_lose_its_siblings(monkeypatch):
    """A wave is not all-or-nothing: the others' results must survive."""
    rec = _Recorder()

    async def boom(**kwargs):
        raise RuntimeError("outil casse")

    tools = {"ok1": rec.tool("ok1"), "bad": boom, "ok2": rec.tool("ok2")}
    workflow = _wf(
        [
            {"id": "a", "action": "ok1"},
            {"id": "b", "action": "bad"},
            {"id": "c", "action": "ok2"},
        ],
        [],
    )

    run = await _engine(monkeypatch, tools).run(workflow)

    assert run.node_results["a"].status == "success"
    assert run.node_results["c"].status == "success"
    assert run.node_results["b"].status == "failed"
    assert "outil casse" in run.node_results["b"].error
    assert run.status == "partially_successful"


async def test_results_order_is_deterministic(monkeypatch):
    """Completion order varies with timing; the persisted dict must not,
    or two identical runs would serialize differently."""

    async def fast(**kwargs):
        return "fast"

    async def slow(**kwargs):
        await asyncio.sleep(0.05)
        return "slow"

    # "a" is slow and "b" is fast, so b finishes first — the recorded key
    # order must still follow the wave, not the finish line.
    workflow = _wf(
        [{"id": "a", "action": "slow"}, {"id": "b", "action": "fast"}], []
    )

    run = await _engine(monkeypatch, {"slow": slow, "fast": fast}).run(workflow)

    assert list(run.node_results) == ["a", "b"]


async def test_validation_gate_still_blocks_its_wave(monkeypatch):
    """A gate must not be swept along by a parallel sibling."""
    rec = _Recorder()
    tools = {"ta": rec.tool("a"), "tg": rec.tool("g"), "td": rec.tool("d")}
    workflow = _wf(
        [
            {"id": "a", "action": "ta"},
            {"id": "gate", "action": "tg", "human_validation": True},
            {"id": "downstream", "action": "td"},
        ],
        [{"from": "gate", "to": "downstream"}],
    )

    run = await _engine(monkeypatch, tools).run(workflow)

    assert run.status == "awaiting_validation"
    assert run.pending_nodes == ["gate"]
    # The independent sibling still ran; the gated branch did not.
    assert run.node_results["a"].status == "success"
    assert run.node_results["gate"].status == "awaiting_validation"
    assert run.node_results["downstream"].status == "skipped"
    assert ("start", "g") not in rec.events
