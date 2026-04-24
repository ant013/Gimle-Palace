"""Tests for watchdog.service — renderers only (no system calls)."""

from __future__ import annotations

import re
from pathlib import Path

from gimle_watchdog import service
from gimle_watchdog.__main__ import _build_parser


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


# GIM-69 regression: rendered args must round-trip through _build_parser


def test_rendered_plist_args_parse_cleanly():
    """Rendered plist ProgramArguments must be parseable by _build_parser."""
    rendered = service.render_plist(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    # Extract only the strings inside <array> (ProgramArguments), not StandardOut/Error paths
    array_match = re.search(r"<array>(.*?)</array>", rendered, re.DOTALL)
    assert array_match, "ProgramArguments <array> not found"
    program_args = re.findall(r"<string>(.*?)</string>", array_match.group(1))
    idx = program_args.index("gimle_watchdog")
    args_after_module = program_args[idx + 1 :]
    # Must not raise SystemExit; if argparse rejects args it calls sys.exit(2)
    _build_parser().parse_args(args_after_module)


def test_rendered_systemd_args_parse_cleanly():
    """Rendered systemd ExecStart args must be parseable by _build_parser."""
    rendered = service.render_systemd_unit(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    for line in rendered.splitlines():
        if line.startswith("ExecStart="):
            parts = line.split()
            idx = next(i for i, p in enumerate(parts) if "gimle_watchdog" in p)
            args_after_module = parts[idx + 1 :]
            _build_parser().parse_args(args_after_module)
            return
    raise AssertionError("ExecStart line not found in systemd unit")


def test_rendered_cron_args_parse_cleanly() -> None:
    """Rendered cron entry args must be parseable by _build_parser."""
    entry = service.render_cron_entry(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        poll_interval_seconds=120,
    )
    # Cron entry: `*/2 * * * * /path/python -m gimle_watchdog tick --config /path/cfg.yaml`
    parts = entry.split()
    idx = next(i for i, p in enumerate(parts) if "gimle_watchdog" in p)
    args_after_module = parts[idx + 1 :]
    _build_parser().parse_args(args_after_module)
