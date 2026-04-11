"""Structured logging configuration for RPA Architect."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    """JSON log formatter with contextual fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra context fields if set on the record.
        for key in ("stage", "file", "iteration"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure the root ``rpa_architect`` logger with a JSON formatter.

    Calling this multiple times is safe — subsequent calls update the level but
    do not add duplicate handlers.

    Args:
        level: Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    global _configured  # noqa: PLW0603

    root_logger = logging.getLogger("rpa_architect")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        root_logger.addHandler(handler)
        root_logger.propagate = False
        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``rpa_architect`` namespace.

    Args:
        name: Dotted logger name (e.g. ``"maestro.bpmn"``).

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(f"rpa_architect.{name}")
