"""Production logging for Hermes OS (HOS-062).

Structured JSON logging with correlation IDs, log rotation,
and integration with Hermes OS EventBus events.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class CorrelationFilter(logging.Filter):
    """Adds correlation_id to log records."""

    _local = threading.local()

    @classmethod
    def set_correlation_id(cls, cid: str) -> None:
        cls._local.correlation_id = cid

    @classmethod
    def get_correlation_id(cls) -> str:
        return getattr(cls._local, "correlation_id", "")

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self.get_correlation_id()
        return True


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "correlation_id": getattr(record, "correlation_id", ""),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_tb(record.exc_info[2])),
            }
        if hasattr(record, "mission_id"):
            log_entry["mission_id"] = record.mission_id
        if hasattr(record, "agent_id"):
            log_entry["agent_id"] = record.agent_id
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data
        return json.dumps(log_entry, default=str)


class ProductionLogger:
    """Structured production logger for Hermes OS."""

    def __init__(self, name: str = "hermes_os", log_dir: str = "logs",
                 level: str = "INFO", json_format: bool = True,
                 max_size_mb: int = 100, backup_count: int = 10):
        self._name = name
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self._logger.handlers.clear()
        self._logger.addFilter(CorrelationFilter())

        if json_format:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s "
                "[%(module)s:%(lineno)d]"
            )

        # File handler with rotation
        file_handler = RotatingFileHandler(
            self._log_dir / f"{name}.log",
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        self._logger.addHandler(console)

    # ── Public API ──

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def set_correlation_id(self, cid: str) -> None:
        CorrelationFilter.set_correlation_id(cid)

    def mission_log(self, mission_id: str, message: str, level: str = "INFO",
                    extra: dict | None = None) -> None:
        extra = extra or {}
        self._logger.log(
            getattr(logging, level.upper(), logging.INFO),
            message,
            extra={"mission_id": mission_id, "extra_data": extra},
        )

    def agent_log(self, agent_id: str, message: str, level: str = "INFO",
                  extra: dict | None = None) -> None:
        extra = extra or {}
        self._logger.log(
            getattr(logging, level.upper(), logging.INFO),
            message,
            extra={"agent_id": agent_id, "extra_data": extra},
        )

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._logger.debug(msg, extra={"extra_data": kwargs} if kwargs else None)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._logger.info(msg, extra={"extra_data": kwargs} if kwargs else None)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._logger.warning(msg, extra={"extra_data": kwargs} if kwargs else None)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._logger.error(msg, exc_info=kwargs.pop("exc_info", False),
                          extra={"extra_data": kwargs} if kwargs else None)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._logger.critical(msg, exc_info=kwargs.pop("exc_info", False),
                             extra={"extra_data": kwargs} if kwargs else None)

    def event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        self._logger.info(
            f"[EVENT] {event_type}",
            extra={"extra_data": {"event_type": event_type, **payload}},
        )


# Global singleton
_production_logger: ProductionLogger | None = None
_logger_lock = threading.Lock()


def get_logger(name: str = "hermes_os") -> ProductionLogger:
    global _production_logger
    if _production_logger is None:
        with _logger_lock:
            if _production_logger is None:
                _production_logger = ProductionLogger(name)
    return _production_logger
