"""The agentic capability probe (HOS-095).

``ModelProfile.agentic_capable`` was built to rank evidence — a measured run
beats a declaration, a declaration beats a name — but nothing ever produced
the measurement, so every answer came from the size heuristic. This module
is the missing producer, and these tests pin the part that matters: how many
trials it takes before a measurement is allowed to override the heuristic.

That threshold is not a style choice. The first probes run on this
deployment contradicted each other: devstral, which had passed manual runs
all day, made 0 tool calls in 305s, while qwen3.5:9b-128k, which had failed
a manual run, passed in 45s with 2 tool calls. Agentic success here is not
deterministic, and a routing decision built on one sample is how a narrator
gets promoted to mission brain.
"""
from __future__ import annotations

import json

import pytest

from backend.model_intelligence import agentic_probe
from backend.model_intelligence.agentic_probe import (
    AgenticProbeResult,
    measured_success_for,
    save_result,
)


@pytest.fixture
def store(monkeypatch, tmp_path):
    path = tmp_path / "probe.json"
    monkeypatch.setattr(agentic_probe, "_probe_store_path", lambda: path)
    return path


def _result(model="m", success=True):
    return AgenticProbeResult(
        model=model, success=success, tool_calls=2 if success else 0,
        duration_s=40.0, artifact_verified=success,
    )


def test_never_probed_returns_none(store):
    """None keeps the size/context heuristic in charge rather than asserting
    an answer nobody measured."""
    assert measured_success_for("never-seen") is None


def test_a_single_trial_is_not_a_verdict(store):
    """One sample flipped both ways on real models — treating it as an
    answer is the failure this guards."""
    save_result(_result(success=True))

    assert measured_success_for("m") is None


def test_consistent_success_is_trusted(store):
    for _ in range(3):
        save_result(_result(success=True))

    assert measured_success_for("m") is True


def test_consistent_failure_is_trusted(store):
    for _ in range(3):
        save_result(_result(success=False))

    assert measured_success_for("m") is False


def test_one_lucky_run_does_not_promote_an_unreliable_model(store):
    save_result(_result(success=True))
    for _ in range(3):
        save_result(_result(success=False))

    assert measured_success_for("m") is False


def test_trials_accumulate_rather_than_overwrite(store):
    save_result(_result(success=True))
    save_result(_result(success=False))

    entry = json.loads(store.read_text(encoding="utf-8"))["m"]
    assert entry["trials"] == 2
    assert entry["successes"] == 1
    assert entry["success_rate"] == 0.5


def test_tag_variants_resolve_to_the_same_model(store):
    """devstral and devstral:latest are one model to Ollama; measuring one
    must answer for the other."""
    for _ in range(3):
        save_result(_result(model="devstral:latest", success=True))

    assert measured_success_for("devstral") is True


def test_run_history_is_bounded(store):
    """Kept for diagnosis, not as an ever-growing log."""
    for _ in range(15):
        save_result(_result(success=True))

    entry = json.loads(store.read_text(encoding="utf-8"))["m"]
    assert entry["trials"] == 15
    assert len(entry["runs"]) <= 10


def test_a_broken_store_never_breaks_the_caller(monkeypatch, tmp_path):
    """This feeds model routing; losing a diagnostic must not fail a task."""
    monkeypatch.setattr(
        agentic_probe, "_probe_store_path", lambda: tmp_path / "nope" / "x" / "p.json",
    )
    monkeypatch.setattr(
        agentic_probe.Path, "mkdir",
        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")),
    )

    save_result(_result())  # must not raise
    assert measured_success_for("m") is None
