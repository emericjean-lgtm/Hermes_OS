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
    assert measured_success_for("devstral:latest") is True


def test_siblings_in_a_family_do_not_share_a_verdict(store):
    """A family name is not a model. Matching on it made qwen3.5:2b inherit
    qwen3.5:9b-128k's 3/3 and be reported capable although it had never been
    probed and is known to narrate instead of calling tools — a measured
    verdict promoting a model that was never measured."""
    for _ in range(3):
        save_result(_result(model="qwen3.5:9b-128k", success=True))

    assert measured_success_for("qwen3.5:2b") is None
    assert measured_success_for("qwen3.5:4b") is None
    assert measured_success_for("qwen3.5:9b-128k") is True


def test_run_history_is_bounded(store):
    """Kept for diagnosis, not as an ever-growing log."""
    for _ in range(15):
        save_result(_result(success=True))

    entry = json.loads(store.read_text(encoding="utf-8"))["m"]
    assert entry["trials"] == 15
    assert len(entry["runs"]) <= 10


def test_two_probes_cannot_run_at_once(monkeypatch, tmp_path):
    """Two probes at once put two models in VRAM, and on a 16 GB card that
    measures the contention rather than the model. gemma4:12b was first
    recorded 0/3 while an lfm2.5 probe happened to be running alongside it;
    re-measured alone it was still 0/3, so that verdict survived — by luck.
    A benchmark whose result depends on what else is running is not one."""
    monkeypatch.setattr(agentic_probe, "_lock_file", lambda: tmp_path / "probe.lock")

    with agentic_probe._exclusive_probe():  # noqa: SLF001
        with pytest.raises(RuntimeError, match="already running"):
            with agentic_probe._exclusive_probe():  # noqa: SLF001
                pass

    # Released afterwards, so a serial sequence of probes still works.
    with agentic_probe._exclusive_probe():  # noqa: SLF001
        pass


def test_a_stale_lock_does_not_wedge_the_probe(monkeypatch, tmp_path):
    """A crashed probe leaves its lock behind; refusing forever afterwards
    would be worse than the contention it guards against."""
    import os
    import time

    lock = tmp_path / "probe.lock"
    monkeypatch.setattr(agentic_probe, "_lock_file", lambda: lock)
    lock.write_text("")
    ancient = time.time() - (agentic_probe._PROBE_TIMEOUT_S + 3600)  # noqa: SLF001
    os.utime(lock, (ancient, ancient))

    with agentic_probe._exclusive_probe():  # noqa: SLF001
        pass  # must not raise


def test_current_fingerprint_none_when_model_absent_from_catalogue(monkeypatch):
    """No matching entry on /api/tags: cannot verify freshness, and this
    must not be confused with an error worth crashing on."""
    import httpx

    class _Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": []}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Reponse()

    monkeypatch.setattr(httpx, "Client", _Client)
    assert agentic_probe.current_fingerprint("nowhere") is None


def test_current_fingerprint_none_when_ollama_unreachable(monkeypatch):
    import httpx

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise ConnectionError("refused")

    monkeypatch.setattr(httpx, "Client", _Client)
    assert agentic_probe.current_fingerprint("m") is None


def _empreinte(monkeypatch, valeur):
    monkeypatch.setattr(agentic_probe, "current_fingerprint", lambda _m: valeur)


def test_verdict_valid_without_a_fingerprint_change(store, monkeypatch):
    """A. Same fingerprint at measurement and at read time: the verdict
    stands, checked on every read rather than assumed."""
    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))

    assert measured_success_for("m") is True


def test_weight_change_invalidates_the_verdict(store, monkeypatch):
    """B. `ollama pull` under the same tag: a verdict measured against the
    old weights must not answer for the new ones."""
    _empreinte(monkeypatch, {"digest": "poids-v1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))
    assert measured_success_for("m") is True

    _empreinte(monkeypatch, {"digest": "poids-v2", "num_ctx": 131072})
    assert measured_success_for("m") is None


def test_num_ctx_change_invalidates_the_verdict(store, monkeypatch):
    """B (variant). Same weights, a Modelfile edit changing what context is
    served — the other condition CLAUDE.md and the roadmap name for G-15."""
    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))
    assert measured_success_for("m") is True

    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 8192})
    assert measured_success_for("m") is None


def test_returning_to_an_identical_fingerprint_keeps_the_verdict(store, monkeypatch):
    """C. A real change reverted to a bit-identical state, with no probe
    saved while it was different, is indistinguishable from never having
    changed — the contract is the fingerprint, not a generation counter
    this store does not keep."""
    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))
    assert measured_success_for("m") is True

    _empreinte(monkeypatch, {"digest": "d2", "num_ctx": 131072})
    assert measured_success_for("m") is None

    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    assert measured_success_for("m") is True


def test_a_stale_series_is_not_blended_into_a_fresh_one(store, monkeypatch):
    """D. 3 successes under the old fingerprint plus 1 failure under the
    new one must never read as 3/4 (75%, above threshold) — the old series
    answers for a model that no longer exists under this tag."""
    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))

    _empreinte(monkeypatch, {"digest": "d2", "num_ctx": 131072})
    save_result(_result(success=False))

    entry = json.loads(store.read_text(encoding="utf-8"))["m"]
    assert entry["trials"] == 1, "the 3 old trials must have been discarded"
    assert entry["successes"] == 0
    assert entry["fingerprint"] == {"digest": "d2", "num_ctx": 131072}


def test_an_unverifiable_fingerprint_fails_open(store, monkeypatch):
    """Ollama unreachable or the tag gone from its catalogue is 'cannot
    verify', never 'changed' — failing closed here would turn a network
    hiccup into a fabricated capability regression."""
    _empreinte(monkeypatch, {"digest": "d1", "num_ctx": 131072})
    for _ in range(3):
        save_result(_result(success=True))

    _empreinte(monkeypatch, None)
    assert measured_success_for("m") is True


def test_legacy_entries_without_a_stored_fingerprint_are_not_retroactively_invalidated(
    store, monkeypatch,
):
    """Entries written before G-15 carry no `fingerprint` key. They must
    keep answering exactly as they did — this feature only starts
    verifying freshness for verdicts it recorded a fingerprint for."""
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps({"m": {"trials": 3, "successes": 3,
                                       "success_rate": 1.0, "runs": []}}),
                     encoding="utf-8")
    _empreinte(monkeypatch, {"digest": "peu-importe", "num_ctx": 131072})

    assert measured_success_for("m") is True


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
