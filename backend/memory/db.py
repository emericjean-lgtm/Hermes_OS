"""SQLite engine/session plumbing shared by every table under
backend/memory/. Nothing outside this module should call
sqlalchemy.create_engine directly.

`init_db` does two things: create missing tables, then add missing
*columns* to tables that already exist. The second half exists because
`create_all` only ever creates whole tables — it silently leaves an
existing table alone even when the model has since grown a column. That
is not a hypothetical: `memory_long` was created before `project_id` was
added to MemoryEntry, so every project-scoped memory query raised
"no such column: memory_long.project_id" on any database predating that
change, while passing every test (tests build a fresh database, where
create_all does produce the current schema).

The reconciliation is deliberately additive-only: it adds nullable
columns and nothing else. It never drops, renames, retypes, or reorders,
so it cannot lose data — which is what makes it safe to run
unconditionally at startup without a migration tool. Anything beyond
adding a nullable column (a NOT NULL addition, a type change, a
backfill) is a real migration and must stay a deliberate, reviewed step,
not something that happens silently on boot.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def make_engine(sqlite_path: str) -> Engine:
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{sqlite_path}", future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _load_all_models() -> None:
    """Import every module that maps a table, so Base.metadata is complete.

    Imported here rather than at module scope because each of these
    imports `Base` from this very module — a top-level import would be
    circular. By the time anything calls init_db, this module has
    finished loading, so the cycle doesn't exist any more.

    Without this, both create_all and the reconciliation below see only
    whatever models the *caller* happened to import first, which makes
    the resulting schema depend on import order — exactly the kind of
    invisible coupling that let memory_long drift in the first place.
    """
    from backend.memory import episodic, skill_library  # noqa: F401
    from backend.security import approvals  # noqa: F401
    from backend.tasks import task_manager  # noqa: F401
    from backend.workflows import run_store  # noqa: F401

    try:
        from backend.core import message_bus  # noqa: F401
        from backend.projects import project_manager  # noqa: F401
    except ImportError:  # pragma: no cover - defensive, keeps init_db usable
        logger.debug("Optional model module unavailable during schema init", exc_info=True)


def _add_missing_columns(engine: Engine) -> list[str]:
    """Add nullable columns the models declare but the database lacks.

    Returns the "table.column" names it added, so a caller (or a test)
    can assert on what happened rather than inferring it.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all already made it, with every column
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable or column.primary_key:
                # Adding a NOT NULL column to a populated table needs a
                # default and a backfill decision — a real migration, not
                # something to improvise at startup. Flag it loudly and
                # leave the schema untouched.
                logger.warning(
                    "Schema drift needs a real migration: %s.%s is missing and is "
                    "NOT NULL/primary key — not added automatically.",
                    table.name,
                    column.name,
                )
                continue
            type_sql = column.type.compile(engine.dialect)
            with engine.begin() as connection:
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {type_sql}')
                )
            added.append(f"{table.name}.{column.name}")
            logger.info("Added missing column %s.%s", table.name, column.name)

    return added


def init_db(engine: Engine) -> None:
    _load_all_models()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
