"""Structured audit log — cahier des charges §18.

Every important action produces one record with the exact shape §18
specifies: who acted, what was asked, which model the router picked and
why, what was touched, and what it cost (duration, tokens, tokens/s,
VRAM). Stored twice, as the spec asks: a queryable `audit_log` table and
a JSON file under `data/logs/`.

**Why the metrics matter beyond bookkeeping.** §22.1 sets latency targets
and §28's T1/T3/T5 test them — but nothing in this codebase measured a
duration or a token rate, so those criteria were not failing, they were
*unverifiable*. `Timer` below is what makes them measurable.

**Redaction happens on write, never on read.** A secret that reached the
disk has already leaked; filtering it at display time would be theatre.
§18 says "aucun secret ne doit apparaître dans les logs", so the record
is scrubbed before it is stored, in both destinations.

**Recording is an explicit call.** No decorator on respond(), no hidden
hook. That is the rule this project applies to every cross-cutting effect
(see self_evolution/pipeline.py and agents/aegis.py for the same
reasoning): a caller that did not ask to be logged is not logged, and a
reader can see where records come from.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.core.config import get_settings
from backend.memory.db import Base

# Patterns scrubbed before anything is written. Deliberately conservative:
# each targets a shape that is *only* ever a credential, so a false
# positive costs a redacted log line, never a leaked one. The value is
# replaced rather than the whole line — the surrounding context is what
# makes a log useful.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Bearer FIRST, and it must run before the key=value rule below.
    # Otherwise "Authorization: Bearer <token>" matches that rule with
    # "Bearer" as the *value*, redacting the word and leaving the token
    # in the log — a leak that looks like a redaction, which is worse
    # than no redaction at all. Found by the tests, not by review.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [REDACTED]"),
    # key=value / "key": "value" for anything *named* like a credential.
    # The leading [\w-]* matters: \b does not fire between "_" and "T",
    # so TELEGRAM_BOT_TOKEN would not have matched a bare \btoken.
    (re.compile(
        r'(?i)\b[\w-]*?(api[_-]?key|secret|token|password|passwd|authorization'
        r'|access[_-]?key|private[_-]?key|client[_-]?secret)'
        r'(\s*[:=]\s*)(["\']?)([^\s"\',;}]{4,})',
    ), r"\g<0>"),  # replaced by _redact_keyed below, which keeps the key
    # Common provider key shapes, matched on their own.
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "[REDACTED]"),
    # Telegram bot tokens: <digits>:<base64-ish>. The suffix is normally
    # 35 chars; the threshold is 20 so a shortened or test token is
    # scrubbed too — under-matching here costs a leak.
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED]"),
)

# The keyed rule needs a function, not a template: it must keep the key
# and the separator while replacing only the value.
_KEYED_PATTERN = _SECRET_PATTERNS[1][0]


def _redact_keyed(match: re.Match[str]) -> str:
    whole = match.group(0)
    value = match.group(4)
    return whole[: len(whole) - len(value)] + REDACTED

REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Scrub secrets from a string, or recursively from a structure.

    Also used by callers that want to sanitise something before it goes
    anywhere else — this is the closest thing the project has to §17.1's
    `secret_scanner`, and reusing it beats a second, divergent copy.
    """
    if isinstance(value, str):
        scrubbed = value
        for pattern, replacement in _SECRET_PATTERNS:
            if pattern is _KEYED_PATTERN:
                scrubbed = pattern.sub(_redact_keyed, scrubbed)
            else:
                scrubbed = pattern.sub(replacement, scrubbed)
        return scrubbed
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class AuditRecord(Base):
    """§18's record. Scalar fields are columns so they can be filtered in
    SQL; the nested blocks stay JSON text, because their shape belongs to
    the spec rather than to this table."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String, index=True)
    request: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(String, index=True, default="success")

    routing_decision: Mapped[str] = mapped_column(Text, default="null")  # JSON
    context_used: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    steps_executed: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    files_modified: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    tests_run: Mapped[str] = mapped_column(Text, default="null")  # JSON dict | null

    validation_requested: Mapped[bool] = mapped_column(default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Split out from duration on purpose: §22.1 budgets time-to-first-token
    # separately from throughput, because a slow *load* and a slow *model*
    # need opposite fixes and a single total cannot tell them apart.
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_thinking_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    vram_used_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass
class AuditEntry:
    """What a caller fills in. Everything optional except the agent —
    a record that cannot say who acted is not worth keeping."""

    agent: str
    request: str = ""
    result: str = "success"
    session_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    routing_decision: dict | None = None
    context_used: list[str] = field(default_factory=list)
    steps_executed: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    tests_run: dict | None = None
    validation_requested: bool = False
    duration_ms: int | None = None
    first_token_ms: int | None = None
    first_thinking_ms: int | None = None
    tokens_used: int | None = None
    tokens_per_second: float | None = None
    vram_used_gb: float | None = None
    error: str | None = None


# Stored as JSON text: their shape belongs to §18, not to this table.
_JSON_FIELDS = frozenset({
    "routing_decision", "context_used", "steps_executed", "files_modified", "tests_run",
})


def _logs_dir() -> Path:
    directory = Path(get_settings().logs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def to_dict(record: AuditRecord) -> dict:
    """§18's JSON shape, exactly."""
    return {
        "id": record.id,
        "timestamp": record.timestamp.isoformat(),
        "session_id": record.session_id,
        "task_id": record.task_id,
        "project_id": record.project_id,
        "agent": record.agent,
        "request": record.request,
        "routing_decision": json.loads(record.routing_decision),
        "context_used": json.loads(record.context_used),
        "steps_executed": json.loads(record.steps_executed),
        "files_modified": json.loads(record.files_modified),
        "tests_run": json.loads(record.tests_run),
        "validation_requested": record.validation_requested,
        "duration_ms": record.duration_ms,
        "first_token_ms": record.first_token_ms,
        "first_thinking_ms": record.first_thinking_ms,
        "tokens_used": record.tokens_used,
        "tokens_per_second": record.tokens_per_second,
        "vram_used_gb": record.vram_used_gb,
        "result": record.result,
        "error": record.error,
    }


def record(session: Session, entry: AuditEntry) -> AuditRecord:
    """Write one audit record — scrubbed, to both destinations.

    The JSON file is written after the commit and its failure is
    swallowed: losing a log line is bad, but failing the *action* that was
    being logged because the disk is full would be worse.
    """
    clean = {k: redact(v) for k, v in asdict(entry).items()}

    # Derived from the dataclass rather than listed by hand. The hand-written
    # version omitted first_token_ms when that field was added: it persisted
    # as null, read back as null, and nothing failed — the field looked
    # recorded while measuring nothing. Building the row from asdict() makes
    # the next added field persist by default instead of by remembering.
    row = AuditRecord(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC),
        **{
            key: json.dumps(value) if key in _JSON_FIELDS else value
            for key, value in clean.items()
        },
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    try:
        day = row.timestamp.strftime("%Y-%m-%d")
        with (_logs_dir() / f"{day}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(to_dict(row), ensure_ascii=False) + "\n")
    except OSError:
        pass

    return row



@contextmanager
def open_session() -> Iterator[Session]:
    """A session with the audit table guaranteed to exist.

    Callers used to build their own engine and rely on some *other*
    component (Kronos, Echo, Aegis) having called init_db first. On a
    fresh install where /chat is the first thing touched, that had not
    happened, so the write failed with "no such table" — and since
    record() swallows its own errors on purpose, it failed silently and
    permanently. init_db is idempotent, so owning it here costs nothing
    and removes the hidden ordering dependency.
    """
    from backend.core.config import get_settings
    from backend.memory.db import init_db, make_engine, make_session_factory

    engine = make_engine(get_settings().sqlite_path)
    init_db(engine)
    with make_session_factory(engine)() as session:
        yield session


def list_records(
    session: Session,
    *,
    session_id: str | None = None,
    agent: str | None = None,
    result: str | None = None,
    limit: int = 100,
) -> list[AuditRecord]:
    stmt = select(AuditRecord).order_by(AuditRecord.timestamp.desc())
    if session_id:
        stmt = stmt.where(AuditRecord.session_id == session_id)
    if agent:
        stmt = stmt.where(AuditRecord.agent == agent)
    if result:
        stmt = stmt.where(AuditRecord.result == result)
    return list(session.execute(stmt.limit(max(1, min(limit, 1000)))).scalars())


def latency_stats(session: Session, *, agent: str | None = None) -> dict:
    """Aggregates over what has been recorded — the answer to §22.1's
    targets and T1/T3/T5, which could not be checked before because
    nothing measured anything.

    Reports `samples`, and reports it even when zero: an empty average
    presented as a number would read as "0 ms", i.e. as a pass.
    """
    records = [r for r in list_records(session, agent=agent, limit=1000) if r.duration_ms]
    if not records:
        return {"samples": 0, "duration_ms": None, "tokens_per_second": None}

    durations = sorted(r.duration_ms for r in records)
    rates = [r.tokens_per_second for r in records if r.tokens_per_second]
    return {
        "samples": len(records),
        "duration_ms": {
            "min": durations[0],
            "median": durations[len(durations) // 2],
            "max": durations[-1],
            "mean": round(sum(durations) / len(durations)),
        },
        "tokens_per_second": (
            {
                "min": round(min(rates), 1),
                "mean": round(sum(rates) / len(rates), 1),
                "max": round(max(rates), 1),
            }
            if rates
            else None
        ),
    }


class Timer:
    """Measures one generation: wall-clock duration and token throughput.

    Wraps the token stream rather than asking callers to count, because a
    caller that has to remember will eventually forget — and an
    unmeasured metric silently becomes a null in the record.
    """

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._first_token_at: float | None = None
        self._first_thinking_at: float | None = None
        self.tokens = 0

    async def measure(self, stream):
        """Pass a token stream through, counting and timing it."""
        async for token in stream:
            if self._first_token_at is None:
                self._first_token_at = time.monotonic()
            self.tokens += 1
            yield token

    async def measure_events(self, stream):
        """Same, for a stream of tagged chunks.

        `tokens` and `tokens_per_second` keep counting **content only**.
        Letting reasoning chunks into that count would leave the field
        named the same, typed the same, and quietly measuring something
        else — the throughput would look better precisely on the requests
        that made the user wait longest.
        """
        async for chunk in stream:
            now = time.monotonic()
            if chunk.kind == "thinking":
                if self._first_thinking_at is None:
                    self._first_thinking_at = now
            else:
                if self._first_token_at is None:
                    self._first_token_at = now
                self.tokens += 1
            yield chunk

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)

    @property
    def first_token_ms(self) -> int | None:
        """What §22.1 actually budgets — the targets are on the *first*
        token, not on the whole answer."""
        if self._first_token_at is None:
            return None
        return int((self._first_token_at - self._start) * 1000)

    @property
    def first_thinking_ms(self) -> int | None:
        """When the reasoning phase began streaming. `first_token_ms`
        keeps meaning the first *content* token — the two together say
        whether a slow answer was thinking or merely late."""
        if self._first_thinking_at is None:
            return None
        return int((self._first_thinking_at - self._start) * 1000)

    @property
    def tokens_per_second(self) -> float | None:
        """Measured from the first token, not from the request: the model
        load time that precedes it would otherwise be blamed on the
        model's speed."""
        if self._first_token_at is None or not self.tokens:
            return None
        elapsed = time.monotonic() - self._first_token_at
        return round(self.tokens / elapsed, 1) if elapsed > 0 else None
