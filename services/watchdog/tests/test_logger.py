"""Tests for watchdog.logger — JSONL format + rotation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gimle_watchdog import logger as wl
from gimle_watchdog.config import LoggingConfig


def _make_cfg(path: Path) -> LoggingConfig:
    return LoggingConfig(
        path=path,
        level="INFO",
        rotate_max_bytes=200,
        rotate_backup_count=2,
    )


def test_jsonl_format(tmp_path: Path):
    log_path = tmp_path / "watchdog.log"
    wl.setup_logging(_make_cfg(log_path))
    logger = logging.getLogger("watchdog.test")
    logger.info("tick_start companies=2 sha=abc")
    wl.shutdown_logging()

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["level"] == "INFO"
    assert entry["name"] == "watchdog.test"
    assert "tick_start" in entry["message"]
    assert "ts" in entry


def test_jsonl_rotation(tmp_path: Path):
    log_path = tmp_path / "watchdog.log"
    wl.setup_logging(_make_cfg(log_path))
    logger = logging.getLogger("watchdog.test")
    for i in range(50):
        logger.info("msg=%03d some padding to reach 200 bytes quickly xxxxxxxxxxxxxxxx", i)
    wl.shutdown_logging()

    files = sorted(tmp_path.glob("watchdog.log*"))
    assert len(files) >= 2
