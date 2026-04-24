"""Tests for watchdog.service — renderers only (no system calls)."""

from __future__ import annotations

from pathlib import Path

from gimle_watchdog import service


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_render_plist_matches_fixture():
    rendered = service.render_plist(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    expected = (FIXTURE_DIR / "plist_expected.xml").read_text()
    assert rendered.strip() == expected.strip()


def test_render_systemd_matches_fixture():
    rendered = service.render_systemd_unit(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    expected = (FIXTURE_DIR / "systemd_unit_expected.service").read_text()
    assert rendered.strip() == expected.strip()


def test_render_cron_entry():
    entry = service.render_cron_entry(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        poll_interval_seconds=120,
    )
    assert entry.startswith("*/2 * * * *")
    assert "/path/to/.venv/bin/python" in entry
    assert "watchdog" in entry
    assert "tick" in entry
    assert "/home/user/.paperclip/watchdog-config.yaml" in entry


def test_render_cron_entry_custom_interval():
    entry = service.render_cron_entry(
        venv_python=Path("/p/py"),
        config_path=Path("/c.yaml"),
        poll_interval_seconds=300,
    )
    assert entry.startswith("*/5 * * * *")
