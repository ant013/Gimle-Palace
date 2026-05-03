"""JSONL log handler with rotation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from gimle_watchdog.config import LoggingConfig


_STDLIB_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        # Promote user-defined extra fields to top level for jq filtering.
        for key, val in record.__dict__.items():
            if key not in _STDLIB_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_installed_handlers: list[logging.Handler] = []


def setup_logging(cfg: LoggingConfig) -> None:
    """Install a rotating JSONL handler on the root 'watchdog' logger."""
    cfg.path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        cfg.path,
        maxBytes=cfg.rotate_max_bytes,
        backupCount=cfg.rotate_backup_count,
    )
    handler.setFormatter(_JSONFormatter())

    root = logging.getLogger("watchdog")
    root.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
    root.addHandler(handler)
    _installed_handlers.append(handler)


def shutdown_logging() -> None:
    """Flush + close all installed handlers (for tests)."""
    root = logging.getLogger("watchdog")
    for handler in _installed_handlers:
        handler.flush()
        handler.close()
        try:
            root.removeHandler(handler)
        except ValueError:
            pass
    _installed_handlers.clear()
