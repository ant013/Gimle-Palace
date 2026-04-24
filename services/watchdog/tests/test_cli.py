"""Tests for watchdog.__main__ — CLI argparse + dispatch (no system calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from gimle_watchdog import __main__ as cli


def test_main_no_args_prints_help(capsys):
    rc = cli.main(["watchdog"])
    out = capsys.readouterr()
    assert rc == 2
    combined = (out.err + out.out).lower()
    assert "usage" in combined


def test_dispatch_known_commands():
    for cmd in ("install", "uninstall", "run", "tick", "status", "tail", "escalate", "unescalate"):
        parser = cli._build_parser()
        assert cmd in parser.format_help()


def test_dry_run_install_prints_plist_for_macos(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("""
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}
escalation: {post_comment_on_issue: true, comment_marker: "<!-- x -->"}
""")
    monkeypatch.setattr(sys, "platform", "darwin")
    rc = cli.main(["watchdog", "--config", str(cfg_path), "install", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work.ant013.gimle-watchdog" in out


def _minimal_cfg(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "cfg.yaml"
    log_path = tmp_path / "watchdog.log"
    cfg_path.write_text(f"""
version: 1
paperclip: {{base_url: http://x, api_key_source: "inline:k"}}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {{died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: {log_path}, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}}
escalation: {{post_comment_on_issue: true, comment_marker: "<!-- x -->"}}
""")
    return cfg_path


def test_cmd_status(tmp_path: Path, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    # state file doesn't exist yet — that's fine, it initialises empty
    rc = cli.main(["watchdog", "--config", str(cfg_path), "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Companies configured: 1" in out
    assert "Active cooldowns: 0" in out


def test_cmd_tail_no_log(tmp_path: Path, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    rc = cli.main(["watchdog", "--config", str(cfg_path), "tail"])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err


def test_cmd_tail_with_log(tmp_path: Path, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    log_path = tmp_path / "watchdog.log"
    entry = json.dumps(
        {"ts": "2026-04-21T10:00:00Z", "level": "INFO", "name": "watchdog", "message": "hi"}
    )
    log_path.write_text(entry + "\n")
    rc = cli.main(["watchdog", "--config", str(cfg_path), "tail", "-n", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hi" in out


def test_cmd_escalate(tmp_path: Path, capsys):
    import argparse

    state_path = tmp_path / "state.json"
    args = argparse.Namespace(issue="issue-x")
    with patch("gimle_watchdog.__main__.Path") as mock_path_cls:
        mock_path_cls.return_value.expanduser.return_value = state_path
        rc = cli._cmd_escalate(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "permanently escalated" in out


def test_cmd_unescalate(tmp_path: Path, capsys):
    import argparse

    args = argparse.Namespace(issue="issue-y")
    state_path = tmp_path / "state.json"
    with patch("gimle_watchdog.__main__.Path") as mock_path_cls:
        mock_path_cls.return_value.expanduser.return_value = state_path
        rc = cli._cmd_unescalate(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "cleared" in out
