"""Event Store abstraction for the Runtime Event Bus (HOS-034).

Provides a persistence abstraction with a SQLite implementation.
Designed to be swappable for Redis Streams, EventStoreDB, etc.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.runtime.events.event_models import RuntimeEventModel, RuntimeEventSeverity


class EventStore(ABC):
    """Abstract event store.

    All implementations must be thread-safe.
    """

    @abstractmethod
    def store(self, event: RuntimeEventModel) -> None:
        """Persist an event."""
        ...

    @abstractmethod
    def get_recent(self, limit: int = 50) -> list[RuntimeEventModel]:
        """Return the most recent events."""
        ...

    @abstractmethod
    def get_by_runtime(
        self,
        runtime_id: str,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        """Return events for a specific runtime."""
        ...

    @abstractmethod
    def get_by_type(
        self,
        event_type: str,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        """Return events of a specific type."""
        ...

    @abstractmethod
    def get_by_severity(
        self,
        severity: RuntimeEventSeverity,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        """Return events with a minimum severity."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of stored events."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources."""
        ...


class SQLEventStore(EventStore):
    """SQLite-backed event store.

    Uses Write-Ahead Logging (WAL) for better concurrent performance.
    Schema is created automatically on first use.
    """

    def __init__(self, db_path: str = "runtime_events.db") -> None:
        self._db_path = str(Path(db_path).resolve())
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_events (
                id TEXT PRIMARY KEY,
                runtime_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'runtime',
                payload TEXT NOT NULL DEFAULT '{}',
                correlation_id TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_events_runtime_id "
            "ON runtime_events(runtime_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_events_event_type "
            "ON runtime_events(event_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_events_severity "
            "ON runtime_events(severity)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_events_timestamp "
            "ON runtime_events(timestamp)"
        )
        conn.commit()

    def store(self, event: RuntimeEventModel) -> None:
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT OR IGNORE INTO runtime_events
                    (id, runtime_id, event_type, severity, timestamp, source, payload, correlation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.runtime_id,
                    event.event_type,
                    event.severity.value,
                    event.timestamp.isoformat(),
                    event.source,
                    json.dumps(event.payload),
                    event.correlation_id,
                ),
            )
            conn.commit()

    def _row_to_event(self, row: sqlite3.Row) -> RuntimeEventModel:
        return RuntimeEventModel(
            id=row["id"],
            runtime_id=row["runtime_id"],
            event_type=row["event_type"],
            severity=RuntimeEventSeverity(row["severity"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            source=row["source"],
            payload=json.loads(row["payload"]),
            correlation_id=row["correlation_id"],
        )

    def get_recent(self, limit: int = 50) -> list[RuntimeEventModel]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM runtime_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_by_runtime(
        self,
        runtime_id: str,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM runtime_events WHERE runtime_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (runtime_id, limit),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_by_type(
        self,
        event_type: str,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM runtime_events WHERE event_type = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_by_severity(
        self,
        severity: RuntimeEventSeverity,
        limit: int = 50,
    ) -> list[RuntimeEventModel]:
        severity_order = {
            "debug": 0,
            "info": 1,
            "warning": 2,
            "error": 3,
            "critical": 4,
        }
        min_level = severity_order.get(severity.value, 0)
        with self._lock:
            conn = self._get_connection()
            # SQLite doesn't have enum ordering, so we filter in application code
            cursor = conn.execute(
                "SELECT * FROM runtime_events ORDER BY timestamp DESC LIMIT ?",
                (limit * 5,),  # Fetch extra to filter
            )
            results = []
            for row in cursor.fetchall():
                row_severity = severity_order.get(row["severity"], 0)
                if row_severity >= min_level:
                    results.append(self._row_to_event(row))
                    if len(results) >= limit:
                        break
            return results

    def count(self) -> int:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM runtime_events")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
