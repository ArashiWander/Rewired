"""Structured logging configuration with dual-handler support.

Provides two output modes:
  - **text** (default): Human-readable ``Rich``-compatible format for TTY.
  - **json**: JSON-lines format for log aggregation (Loki, ELK, etc.).

A pipeline ``run_id`` (UUID4) can be injected via :func:`set_run_id` so
every log line from a single pipeline invocation is correlated.

Environment variables
---------------------
REWIRED_LOG_LEVEL : str
    Python log level name (default ``"WARNING"``).
REWIRED_LOG_FORMAT : str
    ``"text"`` or ``"json"`` (default ``"text"``).
REWIRED_LOG_FILE : str
    Optional file path for log output. If set and format is ``"json"``,
    JSON-lines are written to this file while TTY gets human-readable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

_run_id: str = ""
_lock = threading.Lock()


def set_run_id(run_id: str) -> None:
    """Set the pipeline run ID for log correlation."""
    global _run_id
    with _lock:
        _run_id = run_id


def get_run_id() -> str:
    """Return the current pipeline run ID."""
    return _run_id


class _RunIdFilter(logging.Filter):
    """Inject ``run_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Emit structured JSON-lines log entries."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        run_id = getattr(record, "run_id", "")
        if run_id:
            entry["run_id"] = run_id
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logging based on environment variables.

    Safe to call multiple times — clears existing handlers on each call.
    """
    level_name = os.environ.get("REWIRED_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    log_format = os.environ.get("REWIRED_LOG_FORMAT", "text").lower()
    log_file = os.environ.get("REWIRED_LOG_FILE", "")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addFilter(_RunIdFilter())

    # Console handler — always human-readable
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(console_handler)

    # File handler — JSON if format=json, otherwise same as console
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        if log_format == "json":
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
        root.addHandler(file_handler)
    elif log_format == "json":
        # No file specified but json requested — use json on console
        console_handler.setFormatter(JsonFormatter())
