"""§18 — structured audit log, and the metrics §22.1 depends on.

Most of what follows is about redaction. §18 states plainly that no
secret may appear in the logs, and a log is the one place where a leak
is both durable and easy to overlook — so the patterns are tested
individually, and the "it reached both destinations scrubbed" case is
tested separately from "the pattern matches".
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.core import audit_log
from backend.core.audit_log import AuditEntry, Timer, redact
from backend.memory.db import Base, make_engine, make_session_factory


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    from backend.core.config import get_settings

    get_settings.cache_clear()
    engine = make_engine(str(tmp_path / "audit.db"))
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s
    get_settings.cache_clear()


# ── redaction ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "API_KEY=sk-abcdef0123456789abcdef",
        'api_key: "sk-abcdef0123456789abcdef"',
        "password=hunter2000",
        "TELEGRAM_BOT_TOKEN=123456789:AAFakeTokenValueThatIsLongEnough12345",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "client_secret = 9f8e7d6c5b4a3210",
        "ghp_0123456789abcdefghijklmnopqrstuvwx",
    ],
)
def test_credentials_are_scrubbed(text):
    scrubbed = redact(text)

    assert "REDACTED" in scrubbed
    # The actual value must be gone, not merely flagged.
    for leak in ("sk-abcdef0123456789abcdef", "hunter2000", "AAFakeTokenValue",
                 "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "9f8e7d6c5b4a3210",
                 "ghp_0123456789abcdefghijklmnopqrstuvwx"):
        assert leak not in scrubbed


def test_surrounding_context_survives():
    """Replacing the whole line would make the log useless — the point is
    to keep what happened, minus the credential."""
    scrubbed = redact("connexion à https://api.exemple.fr avec api_key=sk-abcdef0123456789")

    assert "api.exemple.fr" in scrubbed
    assert "sk-abcdef0123456789" not in scrubbed


def test_ordinary_text_is_untouched():
    """Over-eager redaction would quietly destroy legitimate content."""
    ordinary = "Refactor du module de paiement, 12 tests passés, durée 8432 ms"

    assert redact(ordinary) == ordinary


def test_redaction_reaches_nested_structures():
    """A secret hidden two levels down is still a secret."""
    payload = {
        "steps": ["appel avec token=abcdef0123456789"],
        "meta": {"headers": {"authorization": "Bearer abcdef0123456789xyz"}},
    }

    scrubbed = redact(payload)

    assert "abcdef0123456789" not in json.dumps(scrubbed)


# ── the record ───────────────────────────────────────────────────────
def test_record_matches_the_spec_shape(session):
    entry = AuditEntry(
        agent="atlas",
        request="refactor du module",
        session_id="sess-1",
        task_id="task-1",
        routing_decision={"task_type": "code", "model_selected": "qwen3-coder:30b",
                          "tier": 3, "reason": "refactoring complexe détecté"},
        context_used=["fichier_A.py"],
        steps_executed=["lecture", "patch"],
        files_modified=["fichier_A.py"],
        tests_run={"status": "passed", "count": 12},
        duration_ms=8432,
        tokens_used=2341,
        tokens_per_second=27.8,
        vram_used_gb=9.2,
    )

    payload = audit_log.to_dict(audit_log.record(session, entry))

    # Every field §18 names, present and typed as specified.
    for key in ("timestamp", "session_id", "task_id", "agent", "request",
                "routing_decision", "context_used", "steps_executed",
                "files_modified", "tests_run", "validation_requested",
                "duration_ms", "tokens_used", "tokens_per_second",
                "vram_used_gb", "result"):
        assert key in payload, key
    assert payload["routing_decision"]["model_selected"] == "qwen3-coder:30b"
    assert payload["tests_run"]["count"] == 12
    assert payload["result"] == "success"


def test_a_secret_never_reaches_either_destination(session, tmp_path):
    """The load-bearing test: scrubbed in the table *and* in the file."""
    audit_log.record(session, AuditEntry(
        agent="atlas",
        request="deploy avec API_KEY=sk-supersecret0123456789",
        steps_executed=["export TELEGRAM_BOT_TOKEN=123456789:AAFakeTokenLongEnoughHere"],
    ))

    stored = audit_log.list_records(session)[0]
    assert "sk-supersecret0123456789" not in stored.request
    assert "AAFakeTokenLongEnoughHere" not in stored.steps_executed

    written = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "logs").glob("*.jsonl"))
    assert "sk-supersecret0123456789" not in written
    assert "AAFakeTokenLongEnoughHere" not in written
    assert "REDACTED" in written


def test_a_json_file_is_written_alongside(session, tmp_path):
    """§18 asks for both a table and files under data/logs/."""
    audit_log.record(session, AuditEntry(agent="veritas", request="revue"))

    files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8").strip())["agent"] == "veritas"


def test_records_are_filterable(session):
    audit_log.record(session, AuditEntry(agent="atlas", session_id="s1"))
    audit_log.record(session, AuditEntry(agent="veritas", session_id="s1"))
    audit_log.record(session, AuditEntry(agent="atlas", session_id="s2", result="failed"))

    assert len(audit_log.list_records(session, session_id="s1")) == 2
    assert len(audit_log.list_records(session, agent="atlas")) == 2
    assert len(audit_log.list_records(session, result="failed")) == 1


def test_a_failure_is_recorded_with_its_error(session):
    audit_log.record(session, AuditEntry(
        agent="atlas", result="failed", error="Ollama unreachable after 3 attempts"
    ))

    stored = audit_log.list_records(session, result="failed")[0]
    assert "3 attempts" in stored.error


# ── the metrics that unlock §22.1 ────────────────────────────────────
async def _stream(*tokens, delay=0.0):
    for token in tokens:
        if delay:
            await asyncio.sleep(delay)
        yield token


def test_timer_counts_tokens_and_measures():
    timer = Timer()

    collected = asyncio.run(_collect(timer.measure(_stream("a", "b", "c"))))

    assert collected == ["a", "b", "c"]
    assert timer.tokens == 3
    assert timer.duration_ms >= 0
    assert timer.first_token_ms is not None


async def _collect(stream):
    return [t async for t in stream]


def test_throughput_is_measured_from_the_first_token():
    """Counting from the request would blame model load time on the
    model's speed — §22.1 budgets the *first token* separately for that
    exact reason."""
    timer = Timer()
    asyncio.run(_collect(timer.measure(_stream("a", "b", delay=0.01))))

    assert timer.tokens_per_second is not None
    assert timer.tokens_per_second > 0


def test_an_empty_stream_reports_nothing_rather_than_zero():
    """A rate of 0 t/s would read as "measured and terrible" instead of
    "never measured"."""
    timer = Timer()
    asyncio.run(_collect(timer.measure(_stream())))

    assert timer.tokens == 0
    assert timer.tokens_per_second is None
    assert timer.first_token_ms is None


def test_latency_stats_say_when_there_is_nothing_to_report(session):
    """An empty average shown as a number would read as a pass."""
    stats = audit_log.latency_stats(session)

    assert stats["samples"] == 0
    assert stats["duration_ms"] is None


def test_latency_stats_aggregate(session):
    for ms, rate in [(500, 30.0), (1500, 20.0), (1000, 25.0)]:
        audit_log.record(session, AuditEntry(
            agent="atlas", duration_ms=ms, tokens_per_second=rate
        ))

    stats = audit_log.latency_stats(session)

    assert stats["samples"] == 3
    assert stats["duration_ms"]["min"] == 500
    assert stats["duration_ms"]["max"] == 1500
    assert stats["duration_ms"]["median"] == 1000
    assert stats["tokens_per_second"]["max"] == 30.0


def test_records_without_a_duration_are_excluded_from_stats(session):
    """Averaging a null as zero would make the system look faster than it
    is — the direction that matters."""
    audit_log.record(session, AuditEntry(agent="atlas", duration_ms=1000))
    audit_log.record(session, AuditEntry(agent="atlas"))  # never measured

    assert audit_log.latency_stats(session)["samples"] == 1


def test_every_entry_field_actually_reaches_the_record(session):
    """Regression guard for a silent-null bug.

    first_token_ms was added to AuditEntry and to the table, but record()
    listed its columns by hand and never copied it. It persisted as null,
    read back as null, and no test failed — the field looked recorded
    while measuring nothing. This pins the mapping itself, so the next
    added field fails loudly here instead of quietly in production.
    """
    from dataclasses import fields

    populated = AuditEntry(
        agent="atlas", request="r", session_id="s", task_id="t", project_id="p",
        routing_decision={"k": "v"}, context_used=["c"], steps_executed=["e"],
        files_modified=["f"], tests_run={"status": "passed"}, validation_requested=True,
        duration_ms=1, first_token_ms=2, tokens_used=3, tokens_per_second=4.0,
        vram_used_gb=5.0, result="failed", error="boom",
    )

    payload = audit_log.to_dict(audit_log.record(session, populated))

    for f in fields(AuditEntry):
        assert payload.get(f.name) not in (None, [], {}), f"{f.name} n'a pas été enregistré"


def test_first_token_is_persisted_not_just_measured(session):
    audit_log.record(session, AuditEntry(agent="atlas", duration_ms=900, first_token_ms=120))

    assert audit_log.list_records(session)[0].first_token_ms == 120
