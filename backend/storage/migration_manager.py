"""Migration Manager for Hermes OS (HOS-062).

Manages schema migrations for both SQLite and PostgreSQL backends.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from .database_manager import DatabaseManager


class MigrationManager:
    """Manages database schema migrations."""

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager
        self._lock = threading.Lock()
        self._migrations: list[dict[str, Any]] = []
        self._load_migrations()

    # ── Public API ──

    def get_current_version(self) -> int:
        row = self._db.fetch_one("SELECT MAX(version) as v FROM _migrations")
        return row["v"] if row and row["v"] else 0

    def get_pending(self) -> list[dict[str, Any]]:
        current = self.get_current_version()
        return [m for m in self._migrations if m["version"] > current]

    def migrate(self, target_version: int | None = None) -> int:
        """Run pending migrations up to target_version (or all)."""
        with self._lock:
            applied = 0
            for migration in sorted(self._migrations, key=lambda m: m["version"]):
                if target_version and migration["version"] > target_version:
                    break
                if migration["version"] <= self.get_current_version():
                    continue
                try:
                    self._apply(migration)
                    applied += 1
                except Exception as e:
                    raise RuntimeError(
                        f"Migration {migration['name']} (v{migration['version']}) failed: {e}"
                    )
            return applied

    def create_migration(self, name: str, up_sql: str, down_sql: str = "") -> dict[str, Any]:
        version = self.get_current_version() + 1
        migration = {
            "version": version,
            "name": name,
            "up": up_sql,
            "down": down_sql,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._migrations.append(migration)
        return migration

    def list_migrations(self) -> list[dict[str, Any]]:
        return sorted(self._migrations, key=lambda m: m["version"])

    def rollback(self, target_version: int = 0) -> int:
        """Rollback to target_version."""
        with self._lock:
            rolled_back = 0
            for migration in sorted(self._migrations, key=lambda m: -m["version"]):
                if migration["version"] <= target_version:
                    break
                if migration["version"] > self.get_current_version():
                    continue
                if migration.get("down"):
                    self._rollback_one(migration)
                    rolled_back += 1
            return rolled_back

    # ── Private ──

    def _load_migrations(self) -> None:
        self._migrations = [
            {"version": 1, "name": "initial_schema", "up": """
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    user_request TEXT,
                    domain TEXT,
                    status TEXT,
                    created_at TIMESTAMP,
                    completed_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT,
                    status TEXT,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    source TEXT,
                    payload TEXT,
                    created_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    value REAL,
                    tags TEXT,
                    timestamp TIMESTAMP
                );
            """, "down": """
                DROP TABLE IF EXISTS goals;
                DROP TABLE IF EXISTS sessions;
                DROP TABLE IF EXISTS events;
                DROP TABLE IF EXISTS metrics;
            """},
        ]

    def _apply(self, migration: dict[str, Any]) -> None:
        conn = self._db.get_connection()
        cursor = conn.cursor()
        try:
            statements = [s.strip() for s in migration["up"].split(";") if s.strip()]
            for stmt in statements:
                cursor.execute(stmt)
            cursor.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (migration["version"], migration["name"]),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _rollback_one(self, migration: dict[str, Any]) -> None:
        conn = self._db.get_connection()
        cursor = conn.cursor()
        try:
            statements = [s.strip() for s in migration["down"].split(";") if s.strip()]
            for stmt in statements:
                cursor.execute(stmt)
            cursor.execute(
                "DELETE FROM _migrations WHERE version = ?",
                (migration["version"],),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
