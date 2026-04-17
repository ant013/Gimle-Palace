"""JSON structured logging configuration.

Attach `pythonjsonlogger.jsonlogger.JsonFormatter` to stdout. Called once
at service startup (or ingest CLI startup) before any log.info().
"""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_json_logging(level: int = logging.INFO) -> None:
    """Replace root logger handlers with a JSON stdout formatter.

    Events emitted with `logger.info("event.name", extra={...})` become
    `{"message":"event.name", ...extra fields}` on stdout.
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level", "name": "logger", "message": "event"},
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Remove existing stdout StreamHandlers to avoid duplicate output,
    # but preserve other handlers (e.g. pytest's LogCaptureHandler which
    # streams to its own in-memory buffer, not sys.stdout).
    root.handlers = [
        h for h in root.handlers
        if not (isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout)
    ]
    root.addHandler(handler)
    root.setLevel(level)
