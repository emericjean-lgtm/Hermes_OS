"""init_db reconciles columns added to a model after a table was created.

Regression guard for a bug that hid behind a passing test suite:
`memory_long` predated MemoryEntry.project_id, `create_all` never alters
an existing table, and so every project-scoped memory query raised
"no such column" on any real database — while tests, which build a fresh
one each time, saw the current schema and passed.
"""
from __future__ import annotations

import sqlalchemy
from sqlalchemy import text

from backend.memory.db import _add_missing_columns, init_db, make_engine


def _columns(engine, table):
    return {c["name"] for c in sqlalchemy.inspect(engine).get_columns(table)}


def test_column_added_to_a_pre_existing_table(tmp_path):
    """The exact shape of the real bug: an old table missing a column the
    model has since grown."""
    engine = make_engine(str(tmp_path / "old.db"))
    with engine.begin() as connection:
        # memory_long as it existed before project_id — deliberately
        # written out by hand rather than generated, so this test keeps
        # describing the historical schema even if the model changes.
        connection.execute(
            text(
                "CREATE TABLE memory_long ("
                "id VARCHAR PRIMARY KEY, type VARCHAR, content TEXT, "
                "content_hash VARCHAR, tags VARCHAR, confidence FLOAT, "
                "created_at DATETIME)"
            )
        )
    assert "project_id" not in _columns(engine, "memory_long")

    init_db(engine)

    assert "project_id" in _columns(engine, "memory_long")


def test_existing_rows_survive_the_added_column(tmp_path):
    """Additive means additive: nothing already stored may be lost."""
    engine = make_engine(str(tmp_path / "data.db"))
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE memory_long ("
                "id VARCHAR PRIMARY KEY, type VARCHAR, content TEXT, "
                "content_hash VARCHAR, tags VARCHAR, confidence FLOAT, "
                "created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO memory_long VALUES "
                "('id1', 'decision', 'contenu existant', 'h', '', 1.0, '2026-01-01')"
            )
        )

    init_db(engine)

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT content, project_id FROM memory_long WHERE id='id1'")
        ).one()
    assert row[0] == "contenu existant"
    assert row[1] is None  # nullable, so pre-existing rows simply have no value


def test_is_idempotent(tmp_path):
    """Runs on every startup — a second pass must add nothing."""
    engine = make_engine(str(tmp_path / "x.db"))
    init_db(engine)

    assert _add_missing_columns(engine) == []


def test_fresh_database_needs_no_reconciliation(tmp_path):
    engine = make_engine(str(tmp_path / "fresh.db"))

    init_db(engine)

    # create_all already produced the current schema; the second half of
    # init_db should be a no-op, not a source of surprise ALTERs.
    assert _add_missing_columns(engine) == []
    assert "project_id" in _columns(engine, "memory_long")


def test_not_null_column_is_reported_not_improvised(tmp_path, caplog):
    """Adding a NOT NULL column to a populated table needs a default and a
    backfill decision — a real migration. It must be flagged, never
    guessed at during startup."""
    engine = make_engine(str(tmp_path / "notnull.db"))
    with engine.begin() as connection:
        # `type` is NOT NULL in the model; omit it here.
        connection.execute(
            text(
                "CREATE TABLE memory_long ("
                "id VARCHAR PRIMARY KEY, content TEXT, content_hash VARCHAR, "
                "tags VARCHAR, confidence FLOAT, created_at DATETIME)"
            )
        )

    with caplog.at_level("WARNING"):
        added = _add_missing_columns(engine)

    assert "memory_long.type" not in added
    assert "needs a real migration" in caplog.text
    assert "type" not in _columns(engine, "memory_long")
