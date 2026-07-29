"""Database Manager for Hermes OS (HOS-062).

Manages database connections, initializations, and lifecycle
for both SQLite (dev) and PostgreSQL (production).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from backend.config.config_models import DatabaseConfig, StorageBackend


class DatabaseManager:
    """Manages database connections and lifecycle."""

    def __init__(self, config: DatabaseConfig | None = None):
        self._config = config or DatabaseConfig()
        self._connections: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._initialized = False
        self._migration_version = 0

    # ── Public API ──

    @property
    def config(self) -> DatabaseConfig:
        return self._config

    def initialize(self) -> bool:
        """Initialize the database and run pending migrations."""
        with self._lock:
            if self._initialized:
                return True
            try:
                if self._config.backend == StorageBackend.SQLITE:
                    self._init_sqlite()
                else:
                    self._init_postgresql()
                self._initialized = True
                return True
            except Exception as e:
                print(f"Database initialization failed: {e}")
                return False

    def get_connection(self) -> Any:
        """Get a database connection."""
        if not self._initialized:
            self.initialize()
        with self._lock:
            if self._config.backend == StorageBackend.SQLITE:
                # Use the main connection created during initialization
                if "main" in self._connections:
                    return self._connections["main"]
                # Fallback: create per-thread connection
                conn_id = threading.get_ident()
                if conn_id not in self._connections:
                    db_path = self._config.connection_string.replace("sqlite:///", "")
                    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
                    conn = sqlite3.connect(db_path, check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
                    self._connections[conn_id] = conn
                return self._connections[conn_id]
            return self._connections.get("pg")

    def close_all(self) -> None:
        """Close all database connections."""
        with self._lock:
            for conn_id, conn in self._connections.items():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
            self._initialized = False

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query and return cursor."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as dict."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as list of dicts."""
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def is_healthy(self) -> bool:
        """Check if database is reachable."""
        try:
            self.fetch_one("SELECT 1")
            return True
        except Exception:
            return False

    # ── Private ──

    def _init_sqlite(self) -> None:
        db_path = self._config.connection_string.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._connections["main"] = conn
        self._ensure_schema(conn)

    def _init_postgresql(self) -> None:
        try:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(
                host=self._config.host,
                port=self._config.port,
                dbname=self._config.name,
                user=self._config.user,
                password=self._config.password,
                sslmode=self._config.ssl_mode,
            )
            conn.autocommit = True
            self._connections["pg"] = conn
            self._ensure_schema(conn)
        except ImportError:
            raise RuntimeError("psycopg2 not installed. Install with: pip install psycopg2-binary")

    def _ensure_schema(self, conn: Any) -> None:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                name TEXT
            )
        """)
        conn.commit()
        row = cursor.execute("SELECT MAX(version) FROM _migrations").fetchone()
        self._migration_version = row[0] if row[0] else 0
